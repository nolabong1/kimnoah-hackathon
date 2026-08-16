-- supabase_adaptive_test_reset.sql 실행 후 사용하는 읽기 전용 검증입니다.
begin;

do $$
declare
  reset_function regprocedure := pg_catalog.to_regprocedure(
    'public.reset_today_test_progress()'
  );
begin
  if reset_function is null then
    raise exception '테스트 초기화 RPC가 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    where procedure.oid = reset_function
      and procedure.prosecdef
      and coalesce(procedure.proconfig::text, '')
        like '%search_path=%'
  ) then
    raise exception '테스트 초기화 RPC 보안 설정이 올바르지 않습니다.';
  end if;

  if not pg_catalog.has_function_privilege(
    'authenticated',
    reset_function,
    'EXECUTE'
  ) then
    raise exception 'authenticated 초기화 권한이 없습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'anon',
    reset_function,
    'EXECUTE'
  ) then
    raise exception 'anon 초기화 권한이 남아 있습니다.';
  end if;

  if pg_catalog.pg_get_functiondef(reset_function)
       not like '%removed_mastery_event_count%'
  then
    raise exception '적응형 학습 초기화 버전이 적용되지 않았습니다.';
  end if;
end;
$$;


do $$
begin
  if exists (
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
    ),
    expected as (
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
    )
    select 1
    from public.concept_mastery as mastery
    full join expected
      on expected.user_id = mastery.user_id
     and expected.concept_id = mastery.concept_id
    where mastery.user_id is null
       or expected.user_id is null
       or mastery.mastery_score
         is distinct from expected.mastery_score
       or mastery.correct_count
         is distinct from expected.correct_count
       or mastery.incorrect_count
         is distinct from expected.incorrect_count
       or mastery.consecutive_incorrect_count
         is distinct from expected.consecutive_incorrect_count
       or mastery.last_answer_correct
         is distinct from expected.last_answer_correct
       or mastery.last_attempt_id
         is distinct from expected.last_attempt_id
       or mastery.last_assessed_at
         is distinct from expected.last_assessed_at
  ) then
    raise exception '숙련도 현재값과 변경 이력이 일치하지 않습니다.';
  end if;
end;
$$;


do $$
begin
  if exists (
    select 1
    from public.study_tasks as task
    left join public.quiz_attempts as attempt
      on attempt.id = task.source_quiz_attempt_id
     and attempt.quiz_id = task.source_quiz_id
     and attempt.user_id = task.user_id
    where task.source_type = 'weakness_review'
      and attempt.id is null
  ) then
    raise exception '원본 응시가 없는 자동 복습 과제가 있습니다.';
  end if;

  if exists (
    select 1
    from public.study_plans as plan
    join public.study_tasks as task
      on task.plan_id = plan.id
     and task.user_id = plan.user_id
    where plan.target_date < task.scheduled_date
  ) then
    raise exception '계획 종료일 이후에 과제가 남아 있습니다.';
  end if;

  if exists (
    select 1
    from public.study_plans as plan
    join lateral pg_catalog.generate_series(
      0,
      plan.target_date - plan.start_date
    ) as day(day_offset) on true
    left join lateral (
      select coalesce(
        sum(task.estimated_minutes),
        0
      )::integer as total_minutes
      from public.study_tasks as task
      where task.user_id = plan.user_id
        and task.plan_id = plan.id
        and task.scheduled_date = (
          plan.start_date + day.day_offset
        )
    ) as actual_total on true
    left join lateral (
      select (overview.value ->> 'total_minutes')::integer
        as total_minutes
      from pg_catalog.jsonb_array_elements(
        plan.weekly_overview
      ) as overview(value)
      where overview.value ->> 'day_offset' ~ '^\d+$'
        and overview.value ->> 'total_minutes' ~ '^\d+$'
        and (overview.value ->> 'day_offset')::integer
          = day.day_offset
      limit 1
    ) as overview_total on true
    where overview_total.total_minutes
      is distinct from actual_total.total_minutes
  ) then
    raise exception 'weekly_overview와 실제 과제 시간이 일치하지 않습니다.';
  end if;
end;
$$;


select
  (now() at time zone 'Asia/Seoul')::date
    as seoul_date,
  count(*) as remaining_today_quiz_attempts
from public.quiz_attempts as attempt
where (
  attempt.submitted_at at time zone 'Asia/Seoul'
)::date = (
  now() at time zone 'Asia/Seoul'
)::date;

select 'adaptive test reset validation: success'
  as validation_result;

rollback;
