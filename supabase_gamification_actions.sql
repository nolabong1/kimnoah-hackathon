-- 게임화 카탈로그, 진행도 동기화, 보상 수령과 학습 행동 래퍼 RPC
-- supabase_gamification_schema.sql 적용 후 SQL Editor에서 수동 실행합니다.
begin;

create or replace function public.get_gamification_achievement_catalog()
returns table (
  achievement_key text,
  metric_key text,
  target_value integer,
  reward_exp integer
)
language sql
immutable
set search_path = ''
as $$
  values
    ('first_task_completed', 'completed_tasks', 1, 10),
    ('tasks_completed_10', 'completed_tasks', 10, 20),
    ('tasks_completed_50', 'completed_tasks', 50, 30),
    ('tasks_completed_100', 'completed_tasks', 100, 50),
    ('streak_3_days', 'longest_streak', 3, 10),
    ('streak_7_days', 'longest_streak', 7, 20),
    ('streak_14_days', 'longest_streak', 14, 30),
    ('streak_30_days', 'longest_streak', 30, 50),
    ('first_plan_completed', 'completed_plans', 1, 20),
    ('review_tasks_completed_1', 'completed_review_tasks', 1, 10),
    ('first_quiz_submitted', 'quiz_submissions', 1, 10),
    ('first_perfect_quiz', 'perfect_quizzes', 1, 20),
    ('balanced_plan_completed', 'balanced_completed_plans', 1, 30);
$$;

create or replace function public.get_gamification_challenge_catalog()
returns table (
  template_key text,
  period_type text,
  metric_key text,
  target_value integer,
  reward_exp integer
)
language sql
immutable
set search_path = ''
as $$
  values
    ('daily_complete_1_task', 'daily', 'completed_tasks', 1, 5),
    ('daily_complete_2_tasks', 'daily', 'completed_tasks', 2, 10),
    ('daily_complete_1_review', 'daily', 'completed_review_tasks', 1, 5),
    ('daily_submit_1_quiz', 'daily', 'distinct_quizzes', 1, 5),
    ('daily_complete_all_tasks', 'daily', 'all_scheduled_tasks_completed', 1, 5),
    ('weekly_complete_5_tasks', 'weekly', 'completed_tasks', 5, 15),
    ('weekly_complete_10_tasks', 'weekly', 'completed_tasks', 10, 20),
    ('weekly_study_4_days', 'weekly', 'study_days', 4, 15),
    ('weekly_complete_1_review', 'weekly', 'completed_review_tasks', 1, 10),
    ('weekly_submit_1_quiz', 'weekly', 'distinct_quizzes', 1, 10),
    ('weekly_complete_1_plan', 'weekly', 'completed_plans', 1, 15);
$$;

create or replace function public.get_user_gamification_metric(
  p_user_id uuid,
  p_metric_key text,
  p_period_start timestamptz default null,
  p_period_end timestamptz default null
)
returns integer
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_value integer := 0;
begin
  if p_user_id is null then
    raise exception '게임화 지표 사용자 ID가 필요합니다.';
  end if;

  if (p_period_start is null) is distinct from (p_period_end is null) then
    raise exception '게임화 지표 기간의 시작과 종료가 모두 필요합니다.';
  end if;

  if p_period_start is not null and p_period_end <= p_period_start then
    raise exception '게임화 지표 기간이 올바르지 않습니다.';
  end if;

  if p_metric_key = 'completed_tasks' then
    select count(distinct event.source_key)::integer
    into v_value
    from public.exp_events as event
    where event.user_id = p_user_id
      and event.event_type = 'task_completion'
      and (p_period_start is null or event.created_at >= p_period_start)
      and (p_period_end is null or event.created_at < p_period_end);

  elsif p_metric_key = 'completed_review_tasks' then
    select count(distinct task.id)::integer
    into v_value
    from public.study_tasks as task
    join public.exp_events as event
      on event.user_id = task.user_id
     and event.source_key = 'task:' || task.id::text
     and event.event_type = 'task_completion'
    where task.user_id = p_user_id
      and task.task_type = 'review'
      and (p_period_start is null or event.created_at >= p_period_start)
      and (p_period_end is null or event.created_at < p_period_end);

  elsif p_metric_key in ('quiz_submissions', 'distinct_quizzes', 'perfect_quizzes') then
    if p_metric_key = 'distinct_quizzes' then
      select count(distinct attempt.quiz_id)::integer
      into v_value
      from public.quiz_attempts as attempt
      where attempt.user_id = p_user_id
        and (p_period_start is null or attempt.submitted_at >= p_period_start)
        and (p_period_end is null or attempt.submitted_at < p_period_end)
        and exists (
          select 1
          from public.concept_mastery_events as event
          where event.user_id = p_user_id
            and event.quiz_attempt_id = attempt.id
        );
    elsif p_metric_key = 'perfect_quizzes' then
      select count(distinct attempt.id)::integer
      into v_value
      from public.quiz_attempts as attempt
      where attempt.user_id = p_user_id
        and attempt.total_questions > 0
        and attempt.correct_count = attempt.total_questions
        and (p_period_start is null or attempt.submitted_at >= p_period_start)
        and (p_period_end is null or attempt.submitted_at < p_period_end)
        and exists (
          select 1
          from public.concept_mastery_events as event
          where event.user_id = p_user_id
            and event.quiz_attempt_id = attempt.id
        );
    else
      select count(distinct attempt.id)::integer
      into v_value
      from public.quiz_attempts as attempt
      where attempt.user_id = p_user_id
        and (p_period_start is null or attempt.submitted_at >= p_period_start)
        and (p_period_end is null or attempt.submitted_at < p_period_end)
        and exists (
          select 1
          from public.concept_mastery_events as event
          where event.user_id = p_user_id
            and event.quiz_attempt_id = attempt.id
        );
    end if;

  elsif p_metric_key = 'longest_streak' then
    select profile.longest_streak
    into v_value
    from public.profiles as profile
    where profile.id = p_user_id;

  elsif p_metric_key in ('completed_plans', 'balanced_completed_plans') then
    select count(*)::integer
    into v_value
    from (
      select
        plan.id,
        max(event.created_at) as completed_at,
        count(distinct task.task_type) as completed_task_type_count
      from public.study_plans as plan
      join public.study_tasks as task
        on task.plan_id = plan.id
       and task.user_id = plan.user_id
      join public.exp_events as event
        on event.user_id = task.user_id
       and event.source_key = 'task:' || task.id::text
       and event.event_type = 'task_completion'
      where plan.user_id = p_user_id
      group by plan.id
      having count(distinct task.id) > 0
        and count(distinct task.id) = (
          select count(*)
          from public.study_tasks as all_task
          where all_task.user_id = p_user_id
            and all_task.plan_id = plan.id
        )
    ) as completed_plan
    where (
        p_metric_key = 'completed_plans'
        or completed_plan.completed_task_type_count = 3
      )
      and (
        p_period_start is null
        or completed_plan.completed_at >= p_period_start
      )
      and (
        p_period_end is null
        or completed_plan.completed_at < p_period_end
      );

  elsif p_metric_key = 'study_days' then
    if p_period_start is null then
      raise exception '학습일 지표에는 기간이 필요합니다.';
    end if;

    select count(*)::integer
    into v_value
    from (
      select (event.created_at at time zone 'Asia/Seoul')::date as study_date
      from public.exp_events as event
      where event.user_id = p_user_id
        and event.event_type = 'task_completion'
        and event.created_at >= p_period_start
        and event.created_at < p_period_end
      union
      select (attempt.submitted_at at time zone 'Asia/Seoul')::date
      from public.quiz_attempts as attempt
      where attempt.user_id = p_user_id
        and attempt.submitted_at >= p_period_start
        and attempt.submitted_at < p_period_end
        and exists (
          select 1
          from public.concept_mastery_events as event
          where event.user_id = p_user_id
            and event.quiz_attempt_id = attempt.id
        )
    ) as study_day;

  elsif p_metric_key = 'all_scheduled_tasks_completed' then
    if p_period_start is null then
      raise exception '전체 과제 완료 지표에는 기간이 필요합니다.';
    end if;

    select case
      when count(*) > 0
       and count(*) = count(event.id)
      then 1
      else 0
    end
    into v_value
    from public.study_tasks as task
    join public.study_plans as plan
      on plan.id = task.plan_id
     and plan.user_id = task.user_id
     and plan.status = 'active'
    left join public.exp_events as event
      on event.user_id = task.user_id
     and event.source_key = 'task:' || task.id::text
     and event.event_type = 'task_completion'
     and event.created_at >= p_period_start
     and event.created_at < p_period_end
    where task.user_id = p_user_id
      and task.scheduled_date >= (
        p_period_start at time zone 'Asia/Seoul'
      )::date
      and task.scheduled_date < (
        p_period_end at time zone 'Asia/Seoul'
      )::date;

  else
    raise exception '지원하지 않는 게임화 지표입니다: %', p_metric_key;
  end if;

  return coalesce(v_value, 0);
end;
$$;

create or replace function public.sync_user_gamification(
  p_user_id uuid,
  p_now timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_profile public.profiles%rowtype;
  v_definition record;
  v_achievement public.user_achievements%rowtype;
  v_challenge public.user_challenges%rowtype;
  v_period_type text;
  v_period_start timestamptz;
  v_period_end timestamptz;
  v_period_start_date date;
  v_period_end_date date;
  v_limit integer;
  v_display_order integer;
  v_available_task_count integer;
  v_available_task_ids jsonb;
  v_available_review_count integer;
  v_available_quiz_count integer;
  v_available_study_day_count integer;
  v_completable_plan_count integer;
  v_eligibility_snapshot jsonb;
  v_progress integer;
  v_event_amount integer;
  v_event_created_at timestamptz;
  v_achievement_exp integer := 0;
  v_new_unlocks jsonb := '[]'::jsonb;
  v_new_challenge_completions jsonb := '[]'::jsonb;
  v_was_unlocked boolean;
begin
  if p_user_id is null or p_now is null then
    raise exception '게임화 동기화 사용자와 시각이 필요합니다.';
  end if;

  select profile.*
  into v_profile
  from public.profiles as profile
  where profile.id = p_user_id
  for update;

  if not found then
    raise exception '사용자 프로필을 찾을 수 없습니다.';
  end if;

  for v_definition in
    select *
    from public.get_gamification_achievement_catalog()
  loop
    v_progress := public.get_user_gamification_metric(
      p_user_id,
      v_definition.metric_key
    );

    insert into public.user_achievements (
      user_id,
      achievement_key,
      progress_value,
      progress_snapshot
    )
    values (
      p_user_id,
      v_definition.achievement_key,
      least(v_progress, v_definition.target_value),
      pg_catalog.jsonb_build_object(
        'metric_key', v_definition.metric_key,
        'metric_value', v_progress,
        'target_value', v_definition.target_value
      )
    )
    on conflict (user_id, achievement_key) do nothing;

    select achievement.*
    into v_achievement
    from public.user_achievements as achievement
    where achievement.user_id = p_user_id
      and achievement.achievement_key = v_definition.achievement_key
    for update;

    v_was_unlocked := v_achievement.unlocked_at is not null;

    update public.user_achievements
    set
      progress_value = least(v_progress, v_definition.target_value),
      progress_snapshot = pg_catalog.jsonb_build_object(
        'metric_key', v_definition.metric_key,
        'metric_value', v_progress,
        'target_value', v_definition.target_value
      )
    where id = v_achievement.id;

    if v_progress >= v_definition.target_value
       and (
         v_achievement.unlocked_at is null
         or v_achievement.rewarded_at is null
       )
    then
      v_event_amount := null;
      v_event_created_at := null;

      insert into public.exp_events (
        user_id,
        event_type,
        source_key,
        amount,
        created_at
      )
      values (
        p_user_id,
        'achievement',
        'achievement:' || v_definition.achievement_key,
        v_definition.reward_exp,
        p_now
      )
      on conflict (user_id, source_key) do nothing
      returning amount, created_at
      into v_event_amount, v_event_created_at;

      if v_event_amount is null then
        select event.amount, event.created_at
        into v_event_amount, v_event_created_at
        from public.exp_events as event
        where event.user_id = p_user_id
          and event.source_key =
            'achievement:' || v_definition.achievement_key;

        if v_event_amount is distinct from v_definition.reward_exp then
          raise exception '기존 업적 EXP 원장이 서버 카탈로그와 다릅니다.';
        end if;

        v_event_amount := 0;
      else
        v_achievement_exp := v_achievement_exp + v_event_amount;
      end if;

      update public.user_achievements
      set
        unlocked_at = coalesce(unlocked_at, v_event_created_at, p_now),
        rewarded_at = coalesce(
          rewarded_at,
          greatest(
            coalesce(unlocked_at, v_event_created_at, p_now),
            coalesce(v_event_created_at, p_now)
          )
        )
      where id = v_achievement.id;

      if not v_was_unlocked and v_event_amount > 0 then
        v_new_unlocks := v_new_unlocks || pg_catalog.jsonb_build_array(
          pg_catalog.jsonb_build_object(
            'achievement_key', v_definition.achievement_key,
            'reward_exp', v_definition.reward_exp
          )
        );
      end if;
    end if;
  end loop;

  if v_achievement_exp > 0 then
    update public.profiles
    set
      total_exp = total_exp + v_achievement_exp,
      level = ((total_exp + v_achievement_exp) / 100) + 1
    where id = p_user_id
    returning * into v_profile;

    insert into public.learning_activity (
      user_id,
      activity_date,
      completed_task_count,
      quiz_submission_count,
      earned_exp,
      all_tasks_completed
    )
    values (
      p_user_id,
      (p_now at time zone 'Asia/Seoul')::date,
      0,
      0,
      v_achievement_exp,
      false
    )
    on conflict (user_id, activity_date)
    do update set
      earned_exp = public.learning_activity.earned_exp + excluded.earned_exp,
      updated_at = p_now;
  end if;

  for v_period_type in
    select unnest(array['daily'::text, 'weekly'::text])
  loop
    if v_period_type = 'daily' then
      v_period_start := pg_catalog.date_trunc(
        'day',
        p_now at time zone 'Asia/Seoul'
      ) at time zone 'Asia/Seoul';
      v_period_end := v_period_start + interval '1 day';
      v_limit := 3;
    else
      v_period_start := pg_catalog.date_trunc(
        'week',
        p_now at time zone 'Asia/Seoul'
      ) at time zone 'Asia/Seoul';
      v_period_end := v_period_start + interval '7 days';
      v_limit := 2;
    end if;

    v_period_start_date := (
      v_period_start at time zone 'Asia/Seoul'
    )::date;
    v_period_end_date := (
      v_period_end at time zone 'Asia/Seoul'
    )::date;

    if not exists (
      select 1
      from public.user_challenges as challenge
      where challenge.user_id = p_user_id
        and challenge.period_type = v_period_type
        and challenge.period_start = v_period_start
    ) then
      select
        count(distinct task.id)::integer,
        count(distinct task.id) filter (
          where task.task_type = 'review'
        )::integer,
        count(distinct task.scheduled_date)::integer
      into
        v_available_task_count,
        v_available_review_count,
        v_available_study_day_count
      from public.study_tasks as task
      join public.study_plans as plan
        on plan.id = task.plan_id
       and plan.user_id = task.user_id
       and plan.status = 'active'
      where task.user_id = p_user_id
        and task.scheduled_date >= v_period_start_date
        and task.scheduled_date < v_period_end_date;

      select coalesce(
        pg_catalog.jsonb_agg(
          task.id::text order by task.scheduled_date, task.id
        ),
        '[]'::jsonb
      )
      into v_available_task_ids
      from public.study_tasks as task
      join public.study_plans as plan
        on plan.id = task.plan_id
       and plan.user_id = task.user_id
       and plan.status = 'active'
      where task.user_id = p_user_id
        and task.scheduled_date >= v_period_start_date
        and task.scheduled_date < v_period_end_date;

      select count(distinct quiz.id)::integer
      into v_available_quiz_count
      from public.quizzes as quiz
      join public.study_tasks as task
        on task.id = quiz.task_id
       and task.user_id = quiz.user_id
      join public.study_plans as plan
        on plan.id = task.plan_id
       and plan.user_id = task.user_id
       and plan.status = 'active'
      where quiz.user_id = p_user_id
        and task.scheduled_date >= v_period_start_date
        and task.scheduled_date < v_period_end_date;

      select count(*)::integer
      into v_completable_plan_count
      from public.study_plans as plan
      where plan.user_id = p_user_id
        and plan.status = 'active'
        and plan.target_date >= v_period_start_date
        and plan.target_date < v_period_end_date
        and exists (
          select 1
          from public.study_tasks as task
          where task.user_id = p_user_id
            and task.plan_id = plan.id
        );

      v_eligibility_snapshot := pg_catalog.jsonb_build_object(
        'available_task_count', coalesce(v_available_task_count, 0),
        'scheduled_task_ids', coalesce(v_available_task_ids, '[]'::jsonb),
        'available_review_task_count', coalesce(v_available_review_count, 0),
        'available_quiz_count', coalesce(v_available_quiz_count, 0),
        'available_study_day_count', coalesce(v_available_study_day_count, 0),
        'completable_plan_count', coalesce(v_completable_plan_count, 0)
      );

      v_display_order := 0;
      for v_definition in
        select catalog.*
        from public.get_gamification_challenge_catalog() as catalog
        where catalog.period_type = v_period_type
          and case catalog.metric_key
            when 'completed_tasks' then
              v_available_task_count >= catalog.target_value
            when 'completed_review_tasks' then
              v_available_review_count >= catalog.target_value
            when 'distinct_quizzes' then
              v_available_quiz_count >= catalog.target_value
            when 'study_days' then
              v_available_study_day_count >= catalog.target_value
            when 'completed_plans' then
              v_completable_plan_count >= catalog.target_value
            when 'all_scheduled_tasks_completed' then
              v_available_task_count > 0
            else false
          end
        order by pg_catalog.md5(
          p_user_id::text || '|' || v_period_type || '|'
          || v_period_start_date::text || '|' || catalog.template_key
        ), catalog.template_key
        limit v_limit
      loop
        v_display_order := v_display_order + 1;
        insert into public.user_challenges (
          user_id,
          template_key,
          period_type,
          period_start,
          period_end,
          display_order,
          target_value,
          reward_exp,
          eligibility_snapshot
        )
        values (
          p_user_id,
          v_definition.template_key,
          v_period_type,
          v_period_start,
          v_period_end,
          v_display_order,
          v_definition.target_value,
          v_definition.reward_exp,
          v_eligibility_snapshot
        )
        on conflict do nothing;
      end loop;
    end if;
  end loop;

  for v_challenge in
    select challenge.*
    from public.user_challenges as challenge
    where challenge.user_id = p_user_id
      and challenge.status = 'active'
    order by challenge.period_start, challenge.display_order
    for update
  loop
    select catalog.*
    into v_definition
    from public.get_gamification_challenge_catalog() as catalog
    where catalog.template_key = v_challenge.template_key
      and catalog.period_type = v_challenge.period_type;

    if not found
       or v_definition.target_value <> v_challenge.target_value
       or v_definition.reward_exp <> v_challenge.reward_exp
    then
      raise exception '저장된 도전과제 정의가 서버 카탈로그와 다릅니다.';
    end if;

    if v_definition.metric_key = 'all_scheduled_tasks_completed' then
      select case
        when pg_catalog.jsonb_array_length(
          v_challenge.eligibility_snapshot -> 'scheduled_task_ids'
        ) > 0
         and not exists (
          select 1
          from pg_catalog.jsonb_array_elements_text(
            v_challenge.eligibility_snapshot -> 'scheduled_task_ids'
          ) as scheduled(task_id)
          where not exists (
            select 1
            from public.exp_events as event
            where event.user_id = p_user_id
              and event.event_type = 'task_completion'
              and event.source_key = 'task:' || scheduled.task_id
              and event.created_at >= v_challenge.period_start
              and event.created_at < v_challenge.period_end
          )
        )
        then 1
        else 0
      end
      into v_progress;
    else
      v_progress := public.get_user_gamification_metric(
        p_user_id,
        v_definition.metric_key,
        v_challenge.period_start,
        v_challenge.period_end
      );
    end if;

    if v_progress >= v_challenge.target_value then
      update public.user_challenges
      set
        progress_value = target_value,
        status = 'completed',
        completed_at = least(
          p_now,
          v_challenge.period_end - interval '1 microsecond'
        )
      where id = v_challenge.id;

      v_new_challenge_completions :=
        v_new_challenge_completions || pg_catalog.jsonb_build_array(
          pg_catalog.jsonb_build_object(
            'challenge_id', v_challenge.id,
            'template_key', v_challenge.template_key
          )
        );
    elsif p_now >= v_challenge.period_end then
      update public.user_challenges
      set
        progress_value = least(v_progress, target_value),
        status = 'expired'
      where id = v_challenge.id;
    else
      update public.user_challenges
      set progress_value = least(v_progress, target_value)
      where id = v_challenge.id;
    end if;
  end loop;

  select profile.*
  into v_profile
  from public.profiles as profile
  where profile.id = p_user_id;

  return pg_catalog.jsonb_build_object(
    'total_exp', v_profile.total_exp,
    'level', v_profile.level,
    'current_streak', v_profile.current_streak,
    'achievement_exp_awarded', v_achievement_exp,
    'newly_unlocked', v_new_unlocks,
    'newly_completed_challenges', v_new_challenge_completions
  );
end;
$$;

create or replace function public.sync_gamification_state()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  return public.sync_user_gamification(v_user_id, now());
end;
$$;

create or replace function public.complete_study_task_with_gamification(
  p_task_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_result jsonb;
  v_gamification jsonb;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  v_result := public.complete_study_task(p_task_id);
  v_gamification := public.sync_user_gamification(v_user_id, now());

  return v_result || pg_catalog.jsonb_build_object(
    'total_exp', v_gamification -> 'total_exp',
    'level', v_gamification -> 'level',
    'current_streak', v_gamification -> 'current_streak',
    'gamification', v_gamification
  );
end;
$$;

create or replace function public.submit_quiz_attempt_with_gamification(
  p_quiz_id uuid,
  p_quiz_updated_at timestamptz,
  p_answers jsonb,
  p_submission_key uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_result jsonb;
  v_gamification jsonb;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  v_result := public.submit_quiz_attempt(
    p_quiz_id,
    p_quiz_updated_at,
    p_answers,
    p_submission_key
  );
  v_gamification := public.sync_user_gamification(v_user_id, now());

  return v_result || pg_catalog.jsonb_build_object(
    'gamification', v_gamification
  );
end;
$$;

create or replace function public.claim_gamification_challenge(
  p_challenge_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_now timestamptz := now();
  v_today date := (now() at time zone 'Asia/Seoul')::date;
  v_profile public.profiles%rowtype;
  v_challenge public.user_challenges%rowtype;
  v_definition record;
  v_sync_result jsonb;
  v_awarded_exp integer := 0;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  select profile.*
  into v_profile
  from public.profiles as profile
  where profile.id = v_user_id
  for update;

  if not found then
    raise exception '사용자 프로필을 찾을 수 없습니다.';
  end if;

  v_sync_result := public.sync_user_gamification(v_user_id, v_now);

  select challenge.*
  into v_challenge
  from public.user_challenges as challenge
  where challenge.id = p_challenge_id
    and challenge.user_id = v_user_id
  for update;

  if not found then
    raise exception '도전과제를 찾을 수 없습니다.';
  end if;

  select catalog.*
  into v_definition
  from public.get_gamification_challenge_catalog() as catalog
  where catalog.template_key = v_challenge.template_key
    and catalog.period_type = v_challenge.period_type;

  if not found
     or v_definition.target_value <> v_challenge.target_value
     or v_definition.reward_exp <> v_challenge.reward_exp
  then
    raise exception '저장된 도전과제 보상이 서버 카탈로그와 다릅니다.';
  end if;

  if v_challenge.status = 'claimed' then
    if not exists (
      select 1
      from public.exp_events as event
      where event.user_id = v_user_id
        and event.event_type = case v_challenge.period_type
          when 'daily' then 'daily_challenge'
          else 'weekly_challenge'
        end
        and event.source_key = 'challenge:' || v_challenge.id::text
        and event.amount = v_definition.reward_exp
    ) then
      raise exception '수령 완료 도전과제의 EXP 원장이 올바르지 않습니다.';
    end if;

    select profile.*
    into v_profile
    from public.profiles as profile
    where profile.id = v_user_id;

    return pg_catalog.jsonb_build_object(
      'challenge_id', v_challenge.id,
      'status', 'claimed',
      'reward_exp', 0,
      'total_exp', v_profile.total_exp,
      'level', v_profile.level,
      'already_claimed', true
    );
  end if;

  if v_challenge.status = 'expired' then
    raise exception '기간 안에 완료하지 못한 도전과제입니다.';
  end if;

  if v_challenge.status <> 'completed' then
    raise exception '아직 완료하지 않은 도전과제입니다.';
  end if;

  insert into public.exp_events (
    user_id,
    event_type,
    source_key,
    amount,
    created_at
  )
  values (
    v_user_id,
    case v_challenge.period_type
      when 'daily' then 'daily_challenge'
      else 'weekly_challenge'
    end,
    'challenge:' || v_challenge.id::text,
    v_definition.reward_exp,
    v_now
  )
  on conflict (user_id, source_key) do nothing
  returning amount into v_awarded_exp;

  v_awarded_exp := coalesce(v_awarded_exp, 0);

  if v_awarded_exp = 0 and not exists (
    select 1
    from public.exp_events as event
    where event.user_id = v_user_id
      and event.event_type = case v_challenge.period_type
        when 'daily' then 'daily_challenge'
        else 'weekly_challenge'
      end
      and event.source_key = 'challenge:' || v_challenge.id::text
      and event.amount = v_definition.reward_exp
  ) then
    raise exception '기존 도전과제 EXP 원장이 서버 카탈로그와 다릅니다.';
  end if;

  if v_awarded_exp > 0 then
    update public.profiles
    set
      total_exp = total_exp + v_awarded_exp,
      level = ((total_exp + v_awarded_exp) / 100) + 1
    where id = v_user_id
    returning * into v_profile;

    insert into public.learning_activity (
      user_id,
      activity_date,
      completed_task_count,
      quiz_submission_count,
      earned_exp,
      all_tasks_completed
    )
    values (
      v_user_id,
      v_today,
      0,
      0,
      v_awarded_exp,
      false
    )
    on conflict (user_id, activity_date)
    do update set
      earned_exp = public.learning_activity.earned_exp + excluded.earned_exp,
      updated_at = v_now;
  else
    select profile.*
    into v_profile
    from public.profiles as profile
    where profile.id = v_user_id;
  end if;

  update public.user_challenges
  set
    status = 'claimed',
    claimed_at = coalesce(claimed_at, v_now)
  where id = v_challenge.id;

  return pg_catalog.jsonb_build_object(
    'challenge_id', v_challenge.id,
    'status', 'claimed',
    'reward_exp', v_awarded_exp,
    'total_exp', v_profile.total_exp,
    'level', v_profile.level,
    'already_claimed', v_awarded_exp = 0
  );
end;
$$;

create or replace function public.equip_gamification_badge(
  p_achievement_key text,
  p_slot integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_badge public.user_badge_showcase%rowtype;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  if p_slot is null or p_slot not between 1 and 3 then
    raise exception '대표 배지 슬롯은 1부터 3 사이여야 합니다.';
  end if;

  if p_achievement_key is null
     or char_length(btrim(p_achievement_key)) = 0
  then
    raise exception '장착할 업적 배지가 필요합니다.';
  end if;

  perform 1
  from public.profiles as profile
  where profile.id = v_user_id
  for update;

  if not found then
    raise exception '사용자 프로필을 찾을 수 없습니다.';
  end if;

  perform 1
  from public.user_achievements as achievement
  where achievement.user_id = v_user_id
    and achievement.achievement_key = p_achievement_key
    and achievement.unlocked_at is not null
  for update;

  if not found then
    raise exception '아직 획득하지 않은 배지입니다.';
  end if;

  if exists (
    select 1
    from public.user_badge_showcase as showcase
    where showcase.user_id = v_user_id
      and showcase.achievement_key = p_achievement_key
      and showcase.slot <> p_slot
  ) then
    raise exception '같은 배지를 여러 슬롯에 장착할 수 없습니다.';
  end if;

  insert into public.user_badge_showcase (
    user_id,
    slot,
    achievement_key,
    equipped_at
  )
  values (
    v_user_id,
    p_slot,
    p_achievement_key,
    now()
  )
  on conflict (user_id, slot)
  do update set
    achievement_key = excluded.achievement_key,
    equipped_at = excluded.equipped_at
  returning * into v_badge;

  return pg_catalog.to_jsonb(v_badge);
end;
$$;

create or replace function public.remove_gamification_badge(
  p_slot integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_removed_count integer;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  if p_slot is null or p_slot not between 1 and 3 then
    raise exception '대표 배지 슬롯은 1부터 3 사이여야 합니다.';
  end if;

  perform 1
  from public.profiles as profile
  where profile.id = v_user_id
  for update;

  if not found then
    raise exception '사용자 프로필을 찾을 수 없습니다.';
  end if;

  delete from public.user_badge_showcase
  where user_id = v_user_id
    and slot = p_slot;

  get diagnostics v_removed_count = row_count;

  return pg_catalog.jsonb_build_object(
    'slot', p_slot,
    'removed', v_removed_count > 0
  );
end;
$$;

revoke all on function public.get_gamification_achievement_catalog()
from public, anon, authenticated;
revoke all on function public.get_gamification_challenge_catalog()
from public, anon, authenticated;
revoke all on function public.get_user_gamification_metric(
  uuid, text, timestamptz, timestamptz
) from public, anon, authenticated;
revoke all on function public.sync_user_gamification(uuid, timestamptz)
from public, anon, authenticated;

revoke execute on function public.complete_study_task(uuid)
from authenticated;
revoke execute on function public.submit_quiz_attempt(
  uuid, timestamptz, jsonb, uuid
) from authenticated;

revoke all on function public.sync_gamification_state()
from public, anon;
revoke all on function public.complete_study_task_with_gamification(uuid)
from public, anon;
revoke all on function public.submit_quiz_attempt_with_gamification(
  uuid, timestamptz, jsonb, uuid
) from public, anon;
revoke all on function public.claim_gamification_challenge(uuid)
from public, anon;
revoke all on function public.equip_gamification_badge(text, integer)
from public, anon;
revoke all on function public.remove_gamification_badge(integer)
from public, anon;

grant execute on function public.sync_gamification_state()
to authenticated;
grant execute on function public.complete_study_task_with_gamification(uuid)
to authenticated;
grant execute on function public.submit_quiz_attempt_with_gamification(
  uuid, timestamptz, jsonb, uuid
) to authenticated;
grant execute on function public.claim_gamification_challenge(uuid)
to authenticated;
grant execute on function public.equip_gamification_badge(text, integer)
to authenticated;
grant execute on function public.remove_gamification_badge(integer)
to authenticated;

commit;
