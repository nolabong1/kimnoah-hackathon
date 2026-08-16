begin;

-- 오늘의 테스트 과제·보상·퀴즈 응시·숙련도·자동 복습을 함께 되돌립니다.
create or replace function public.reset_today_test_progress()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_today date := (
    now() at time zone 'Asia/Seoul'
  )::date;

  v_task_ids uuid[] := array[]::uuid[];
  v_attempt_ids uuid[] := array[]::uuid[];
  v_affected_concept_ids uuid[] := array[]::uuid[];
  v_affected_plan_ids uuid[] := array[]::uuid[];

  v_reset_task_count integer := 0;
  v_removed_quiz_attempt_count integer := 0;
  v_removed_mastery_event_count integer := 0;
  v_removed_auto_review_task_count integer := 0;
  v_restored_plan_count integer := 0;

  v_removed_task_exp integer := 0;
  v_removed_daily_bonus_exp integer := 0;
  v_new_total_exp integer := 0;

  v_plan_id uuid;
  v_restored_target_date date;
  v_last_activity_date date;
  v_check_date date;
  v_new_streak integer := 0;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      v_user_id::text || ':' || v_today::text,
      0
    )
  );

  -- 퀴즈 제출 RPC와 같은 사용자 잠금을 사용해 동시 처리를 직렬화합니다.
  perform 1
  from public.profiles as profile
  where profile.id = v_user_id
  for update;

  if not found then
    raise exception '사용자 프로필을 찾을 수 없습니다.';
  end if;

  select
    coalesce(
      pg_catalog.array_agg(task.id),
      array[]::uuid[]
    ),
    count(*)::integer
  into
    v_task_ids,
    v_reset_task_count
  from public.study_tasks as task
  where task.user_id = v_user_id
    and task.status = 'completed'
    and task.completed_at is not null
    and (
      task.completed_at at time zone 'Asia/Seoul'
    )::date = v_today;

  if v_reset_task_count > 0 then
    select
      coalesce(sum(event.amount), 0)::integer
    into v_removed_task_exp
    from public.exp_events as event
    where event.user_id = v_user_id
      and event.source_key in (
        select
          'task:' || reset_task.task_id::text
        from pg_catalog.unnest(
          v_task_ids
        ) as reset_task(task_id)
      );

    delete from public.exp_events as event
    where event.user_id = v_user_id
      and event.source_key in (
        select
          'task:' || reset_task.task_id::text
        from pg_catalog.unnest(
          v_task_ids
        ) as reset_task(task_id)
      );

    update public.study_tasks
    set
      status = 'pending',
      completed_at = null
    where user_id = v_user_id
      and id = any(v_task_ids);
  end if;

  select
    coalesce(sum(event.amount), 0)::integer
  into v_removed_daily_bonus_exp
  from public.exp_events as event
  where event.user_id = v_user_id
    and event.source_key = (
      'daily:' || v_today::text
    );

  delete from public.exp_events
  where user_id = v_user_id
    and source_key = (
      'daily:' || v_today::text
    );

  -- 오늘 생성된 응시만 수집하며 다른 날짜와 사용자의 응시는 보존합니다.
  select coalesce(
    pg_catalog.array_agg(attempt.id),
    array[]::uuid[]
  )
  into v_attempt_ids
  from public.quiz_attempts as attempt
  where attempt.user_id = v_user_id
    and (
      attempt.submitted_at at time zone 'Asia/Seoul'
    )::date = v_today;

  if pg_catalog.cardinality(v_attempt_ids) > 0 then
    select coalesce(
      pg_catalog.array_agg(distinct event.concept_id),
      array[]::uuid[]
    )
    into v_affected_concept_ids
    from public.concept_mastery_events as event
    where event.user_id = v_user_id
      and event.quiz_attempt_id = any(v_attempt_ids);

    select count(*)::integer
    into v_removed_mastery_event_count
    from public.concept_mastery_events as event
    where event.user_id = v_user_id
      and event.quiz_attempt_id = any(v_attempt_ids);

    select
      coalesce(
        pg_catalog.array_agg(distinct task.plan_id),
        array[]::uuid[]
      ),
      count(*)::integer
    into
      v_affected_plan_ids,
      v_removed_auto_review_task_count
    from public.study_tasks as task
    where task.user_id = v_user_id
      and task.source_type = 'weakness_review'
      and task.source_quiz_attempt_id = any(v_attempt_ids);

    -- 연결 이벤트와 자동 복습 과제는 소유권 외래 키로 함께 삭제됩니다.
    delete from public.quiz_attempts as attempt
    where attempt.user_id = v_user_id
      and attempt.id = any(v_attempt_ids);

    get diagnostics v_removed_quiz_attempt_count = row_count;

    if pg_catalog.cardinality(v_affected_concept_ids) > 0 then
      -- 남은 이력이 없는 개념의 현재 숙련도 행은 제거합니다.
      delete from public.concept_mastery as mastery
      where mastery.user_id = v_user_id
        and mastery.concept_id = any(v_affected_concept_ids)
        and not exists (
          select 1
          from public.concept_mastery_events as event
          where event.user_id = mastery.user_id
            and event.concept_id = mastery.concept_id
        );

      -- 남은 이벤트를 기준으로 현재값, 누적 횟수, 연속 오답을 재계산합니다.
      with event_rows as (
        select
          event.user_id,
          event.concept_id,
          event.quiz_attempt_id,
          event.question_index,
          event.is_correct,
          event.score_after,
          event.created_at as event_created_at,
          attempt.submitted_at
        from public.concept_mastery_events as event
        join public.quiz_attempts as attempt
          on attempt.id = event.quiz_attempt_id
         and attempt.quiz_id = event.quiz_id
         and attempt.user_id = event.user_id
        where event.user_id = v_user_id
          and event.concept_id = any(v_affected_concept_ids)
      ),
      latest as (
        select distinct on (
          event_row.user_id,
          event_row.concept_id
        )
          event_row.user_id,
          event_row.concept_id,
          event_row.score_after as mastery_score,
          event_row.is_correct as last_answer_correct,
          event_row.quiz_attempt_id as last_attempt_id,
          event_row.submitted_at as last_assessed_at
        from event_rows as event_row
        order by
          event_row.user_id,
          event_row.concept_id,
          event_row.submitted_at desc,
          event_row.question_index desc,
          event_row.event_created_at desc
      ),
      totals as (
        select
          event_row.user_id,
          event_row.concept_id,
          count(*) filter (
            where event_row.is_correct
          )::integer as correct_count,
          count(*) filter (
            where not event_row.is_correct
          )::integer as incorrect_count
        from event_rows as event_row
        group by event_row.user_id, event_row.concept_id
      ),
      reverse_ranked as (
        select
          event_row.user_id,
          event_row.concept_id,
          event_row.is_correct,
          row_number() over (
            partition by
              event_row.user_id,
              event_row.concept_id
            order by
              event_row.submitted_at desc,
              event_row.question_index desc,
              event_row.event_created_at desc
          ) as reverse_rank
        from event_rows as event_row
      ),
      first_recent_correct as (
        select
          ranked.user_id,
          ranked.concept_id,
          min(ranked.reverse_rank) filter (
            where ranked.is_correct
          ) as first_correct_rank
        from reverse_ranked as ranked
        group by ranked.user_id, ranked.concept_id
      ),
      streaks as (
        select
          ranked.user_id,
          ranked.concept_id,
          count(*) filter (
            where not ranked.is_correct
              and (
                recent_correct.first_correct_rank is null
                or ranked.reverse_rank
                  < recent_correct.first_correct_rank
              )
          )::integer as consecutive_incorrect_count
        from reverse_ranked as ranked
        join first_recent_correct as recent_correct
          on recent_correct.user_id = ranked.user_id
         and recent_correct.concept_id = ranked.concept_id
        group by ranked.user_id, ranked.concept_id
      )
      insert into public.concept_mastery (
        user_id,
        concept_id,
        mastery_score,
        correct_count,
        incorrect_count,
        consecutive_incorrect_count,
        last_answer_correct,
        last_attempt_id,
        last_assessed_at
      )
      select
        latest.user_id,
        latest.concept_id,
        latest.mastery_score,
        totals.correct_count,
        totals.incorrect_count,
        streaks.consecutive_incorrect_count,
        latest.last_answer_correct,
        latest.last_attempt_id,
        latest.last_assessed_at
      from latest
      join totals
        on totals.user_id = latest.user_id
       and totals.concept_id = latest.concept_id
      join streaks
        on streaks.user_id = latest.user_id
       and streaks.concept_id = latest.concept_id
      on conflict (user_id, concept_id)
      do update set
        mastery_score = excluded.mastery_score,
        correct_count = excluded.correct_count,
        incorrect_count = excluded.incorrect_count,
        consecutive_incorrect_count =
          excluded.consecutive_incorrect_count,
        last_answer_correct = excluded.last_answer_correct,
        last_attempt_id = excluded.last_attempt_id,
        last_assessed_at = excluded.last_assessed_at;
    end if;

    -- 삭제된 자동 복습만큼 계획 범위와 일별 요약을 다시 줄입니다.
    foreach v_plan_id in array v_affected_plan_ids
    loop
      select greatest(
        plan.start_date + 6,
        coalesce(
          max(task.scheduled_date),
          plan.start_date + 6
        )
      )
      into v_restored_target_date
      from public.study_plans as plan
      left join public.study_tasks as task
        on task.plan_id = plan.id
       and task.user_id = plan.user_id
      where plan.id = v_plan_id
        and plan.user_id = v_user_id
      group by plan.start_date;

      if found then
        update public.study_plans as plan
        set target_date = v_restored_target_date
        where plan.id = v_plan_id
          and plan.user_id = v_user_id;

        perform public.refresh_study_plan_weekly_overview(
          v_user_id,
          v_plan_id
        );

        v_restored_plan_count := v_restored_plan_count + 1;
      end if;
    end loop;
  end if;

  update public.learning_activity
  set
    completed_task_count = greatest(
      completed_task_count - v_reset_task_count,
      0
    ),
    quiz_submission_count = greatest(
      quiz_submission_count - v_removed_quiz_attempt_count,
      0
    ),
    earned_exp = greatest(
      earned_exp
      - v_removed_task_exp
      - v_removed_daily_bonus_exp,
      0
    ),
    all_tasks_completed = false,
    updated_at = now()
  where user_id = v_user_id
    and activity_date = v_today;

  delete from public.learning_activity
  where user_id = v_user_id
    and activity_date = v_today
    and completed_task_count = 0
    and quiz_submission_count = 0
    and earned_exp = 0;

  select
    coalesce(sum(event.amount), 0)::integer
  into v_new_total_exp
  from public.exp_events as event
  where event.user_id = v_user_id;

  select max(activity.activity_date)
  into v_last_activity_date
  from public.learning_activity as activity
  where activity.user_id = v_user_id
    and (
      activity.completed_task_count > 0
      or activity.quiz_submission_count > 0
      or activity.earned_exp > 0
    );

  v_check_date := v_last_activity_date;

  while v_check_date is not null
    and exists (
      select 1
      from public.learning_activity as activity
      where activity.user_id = v_user_id
        and activity.activity_date = v_check_date
        and (
          activity.completed_task_count > 0
          or activity.quiz_submission_count > 0
          or activity.earned_exp > 0
        )
    )
  loop
    v_new_streak := v_new_streak + 1;
    v_check_date := v_check_date - 1;
  end loop;

  update public.profiles
  set
    total_exp = v_new_total_exp,
    level = (v_new_total_exp / 100) + 1,
    current_streak = v_new_streak,
    last_activity_date = v_last_activity_date
  where id = v_user_id;

  return pg_catalog.jsonb_build_object(
    'reset_task_count', v_reset_task_count,
    'removed_quiz_attempt_count',
      v_removed_quiz_attempt_count,
    'removed_mastery_event_count',
      v_removed_mastery_event_count,
    'removed_auto_review_task_count',
      v_removed_auto_review_task_count,
    'restored_plan_count', v_restored_plan_count,
    'removed_task_exp', v_removed_task_exp,
    'removed_daily_bonus_exp',
      v_removed_daily_bonus_exp,
    'removed_total_exp',
      v_removed_task_exp
      + v_removed_daily_bonus_exp,
    'total_exp', v_new_total_exp,
    'level', (v_new_total_exp / 100) + 1,
    'current_streak', v_new_streak,
    'reset_date', v_today
  );
end;
$$;

revoke all
on function public.reset_today_test_progress()
from public, anon;

grant execute
on function public.reset_today_test_progress()
to authenticated;

commit;
