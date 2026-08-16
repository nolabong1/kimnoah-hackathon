begin;

-- 자동 복습 과제에 1·3·7일 간격 반복 단계를 기록합니다.
alter table public.study_tasks
add column review_stage smallint;

alter table public.study_tasks
add column review_interval_days smallint;

update public.study_tasks
set
  review_stage = 1,
  review_interval_days = 1
where source_type = 'weakness_review';

alter table public.study_tasks
add constraint study_tasks_spaced_review_metadata_check
check (
  (
    source_type = 'weekly_plan'
    and review_stage is null
    and review_interval_days is null
  )
  or
  (
    source_type = 'weakness_review'
    and review_stage is not null
    and review_interval_days is not null
    and review_stage between 1 and 3
    and review_interval_days = case review_stage
      when 1 then 1
      when 2 then 3
      when 3 then 7
    end
  )
);


-- 같은 개념의 1·3·7일 단계는 함께 예약하되 같은 단계는 중복하지 않습니다.
drop index public.study_tasks_pending_weakness_review_unique;

create unique index study_tasks_pending_weakness_review_unique
on public.study_tasks(
  user_id,
  plan_id,
  concept_id,
  review_stage
)
where source_type = 'weakness_review'
  and status = 'pending';

drop index public.study_tasks_weakness_source_attempt_unique;

create unique index study_tasks_weakness_source_attempt_unique
on public.study_tasks(
  user_id,
  source_quiz_attempt_id,
  concept_id,
  review_stage
)
where source_type = 'weakness_review';


-- 취약 개념마다 1일·3일·7일 목표의 복습을 순서대로 배치합니다.
create or replace function public.create_auto_review_tasks(
  p_user_id uuid,
  p_quiz_attempt_id uuid
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
  v_today date := (
    now() at time zone 'Asia/Seoul'
  )::date;
  v_plan record;
  v_weak_concept record;
  v_existing_task record;
  v_candidate_date date;
  v_previous_scheduled_date date;
  v_search_end_date date;
  v_day_offset integer;
  v_schedule_offset integer;
  v_allowed_minutes integer;
  v_scheduled_minutes integer;
  v_created_task_id uuid;
  v_stage smallint;
  v_interval_days smallint;
  v_created_any boolean := false;
  v_auto_review_tasks jsonb := '[]'::jsonb;
  v_unscheduled_concepts jsonb := '[]'::jsonb;
begin
  if p_user_id is null or p_quiz_attempt_id is null then
    raise exception '사용자와 퀴즈 응시 ID가 필요합니다.';
  end if;

  select
    plan.id,
    plan.start_date,
    plan.target_date,
    plan.available_schedule,
    plan.status,
    quiz.id as quiz_id,
    (
      attempt.submitted_at at time zone 'Asia/Seoul'
    )::date as attempt_date
  into v_plan
  from public.quiz_attempts as attempt
  join public.quizzes as quiz
    on quiz.id = attempt.quiz_id
   and quiz.user_id = attempt.user_id
  join public.study_plans as plan
    on plan.id = quiz.plan_id
   and plan.user_id = quiz.user_id
  where attempt.id = p_quiz_attempt_id
    and attempt.user_id = p_user_id
  for update of plan;

  if not found then
    raise exception '소유한 퀴즈 응시와 학습계획을 찾을 수 없습니다.';
  end if;

  if v_plan.status <> 'active' then
    select coalesce(
      pg_catalog.jsonb_agg(
        pg_catalog.jsonb_build_object(
          'concept_id', concept.id,
          'concept_name', concept.canonical_name,
          'reason', 'inactive_plan'
        )
        order by mastery.mastery_score,
          concept.canonical_name
      ),
      '[]'::jsonb
    )
    into v_unscheduled_concepts
    from public.concept_mastery as mastery
    join public.learning_concepts as concept
      on concept.id = mastery.concept_id
     and concept.user_id = mastery.user_id
    where mastery.user_id = p_user_id
      and mastery.incorrect_count >= 2
      and public.is_concept_weak(
        mastery.mastery_score,
        mastery.consecutive_incorrect_count
      )
      and exists (
        select 1
        from public.concept_mastery_events as event
        where event.user_id = p_user_id
          and event.quiz_attempt_id = p_quiz_attempt_id
          and event.concept_id = mastery.concept_id
          and not event.is_correct
      );

    return pg_catalog.jsonb_build_object(
      'auto_review_tasks', '[]'::jsonb,
      'unscheduled_weak_concepts', v_unscheduled_concepts
    );
  end if;

  -- 원래 7일 계획 이후에는 같은 요일 가능 시간을 한 번만 반복합니다.
  v_search_end_date := v_plan.start_date + 13;

  for v_weak_concept in
    select
      concept.id,
      concept.canonical_name,
      mastery.mastery_score,
      mastery.incorrect_count,
      mastery.consecutive_incorrect_count
    from public.concept_mastery as mastery
    join public.learning_concepts as concept
      on concept.id = mastery.concept_id
     and concept.user_id = mastery.user_id
    where mastery.user_id = p_user_id
      and mastery.incorrect_count >= 2
      and public.is_concept_weak(
        mastery.mastery_score,
        mastery.consecutive_incorrect_count
      )
      and exists (
        select 1
        from public.concept_mastery_events as event
        where event.user_id = p_user_id
          and event.quiz_attempt_id = p_quiz_attempt_id
          and event.concept_id = mastery.concept_id
          and not event.is_correct
      )
    order by
      mastery.mastery_score,
      mastery.consecutive_incorrect_count desc,
      concept.canonical_name
  loop
    -- 다른 응시에서 시작된 미완료 복습 묶음이 있으면 새 묶음을 만들지 않습니다.
    if exists (
      select 1
      from public.study_tasks as task
      where task.user_id = p_user_id
        and task.plan_id = v_plan.id
        and task.concept_id = v_weak_concept.id
        and task.source_type = 'weakness_review'
        and task.status = 'pending'
        and task.source_quiz_attempt_id
          <> p_quiz_attempt_id
    ) then
      v_unscheduled_concepts := v_unscheduled_concepts
        || pg_catalog.jsonb_build_array(
          pg_catalog.jsonb_build_object(
            'concept_id', v_weak_concept.id,
            'concept_name', v_weak_concept.canonical_name,
            'reason', 'existing_review_series'
          )
        );
      continue;
    end if;

    v_previous_scheduled_date := null;

    for v_stage in 1..3
    loop
      v_interval_days := case v_stage
        when 1 then 1
        when 2 then 3
        when 3 then 7
      end;

      select
        task.id,
        task.scheduled_date
      into v_existing_task
      from public.study_tasks as task
      where task.user_id = p_user_id
        and task.plan_id = v_plan.id
        and task.concept_id = v_weak_concept.id
        and task.source_quiz_attempt_id = p_quiz_attempt_id
        and task.source_type = 'weakness_review'
        and task.review_stage = v_stage
      limit 1;

      if found then
        v_previous_scheduled_date :=
          v_existing_task.scheduled_date;
        continue;
      end if;

      v_candidate_date := greatest(
        v_plan.attempt_date + v_interval_days,
        v_today + 1,
        v_plan.start_date,
        coalesce(
          v_previous_scheduled_date + 1,
          v_plan.start_date
        )
      );
      v_created_task_id := null;

      while v_candidate_date <= v_search_end_date loop
        v_day_offset := (
          v_candidate_date - v_plan.start_date
        );
        v_schedule_offset := mod(v_day_offset, 7);

        if v_plan.available_schedule
             ->> (v_schedule_offset::text || '일차')
             ~ '^\d+$'
        then
          v_allowed_minutes := (
            v_plan.available_schedule
              ->> (v_schedule_offset::text || '일차')
          )::integer;
        else
          v_allowed_minutes := 0;
        end if;

        select coalesce(
          sum(task.estimated_minutes),
          0
        )::integer
        into v_scheduled_minutes
        from public.study_tasks as task
        where task.user_id = p_user_id
          and task.plan_id = v_plan.id
          and task.scheduled_date = v_candidate_date;

        if v_scheduled_minutes + 20 <= v_allowed_minutes then
          insert into public.study_tasks (
            user_id,
            plan_id,
            scheduled_date,
            title,
            description,
            task_type,
            estimated_minutes,
            status,
            source_type,
            concept_id,
            source_quiz_id,
            source_quiz_attempt_id,
            review_stage,
            review_interval_days
          )
          values (
            p_user_id,
            v_plan.id,
            v_candidate_date,
            '[간격 복습 '
              || v_stage::text
              || '/3] '
              || v_weak_concept.canonical_name,
            v_weak_concept.canonical_name
              || ' 개념을 '
              || v_interval_days::text
              || '일 간격으로 다시 확인합니다. 현재 숙련도는 '
              || v_weak_concept.mastery_score::text
              || '점입니다. 핵심 내용을 기억에서 꺼내 설명하고 '
              || '짧은 예시에 적용해보세요.',
            'review',
            20,
            'pending',
            'weakness_review',
            v_weak_concept.id,
            v_plan.quiz_id,
            p_quiz_attempt_id,
            v_stage,
            v_interval_days
          )
          on conflict do nothing
          returning id into v_created_task_id;

          exit;
        end if;

        v_candidate_date := v_candidate_date + 1;
      end loop;

      if v_created_task_id is null then
        v_unscheduled_concepts := v_unscheduled_concepts
          || pg_catalog.jsonb_build_array(
            pg_catalog.jsonb_build_object(
              'concept_id', v_weak_concept.id,
              'concept_name', v_weak_concept.canonical_name,
              'reason', 'no_available_time',
              'review_stage', v_stage
            )
          );
        exit;
      end if;

      v_created_any := true;
      v_previous_scheduled_date := v_candidate_date;

      if v_candidate_date > v_plan.target_date then
        update public.study_plans as plan
        set target_date = v_candidate_date
        where plan.id = v_plan.id
          and plan.user_id = p_user_id;

        v_plan.target_date := v_candidate_date;
      end if;
    end loop;
  end loop;

  if v_created_any then
    perform public.refresh_study_plan_weekly_overview(
      p_user_id,
      v_plan.id
    );
  end if;

  select coalesce(
    pg_catalog.jsonb_agg(
      pg_catalog.jsonb_build_object(
        'task_id', task.id,
        'plan_id', task.plan_id,
        'concept_id', task.concept_id,
        'concept_name', concept.canonical_name,
        'title', task.title,
        'scheduled_date', task.scheduled_date,
        'estimated_minutes', task.estimated_minutes,
        'review_stage', task.review_stage,
        'review_interval_days', task.review_interval_days
      )
      order by task.review_stage, task.scheduled_date
    ),
    '[]'::jsonb
  )
  into v_auto_review_tasks
  from public.study_tasks as task
  join public.learning_concepts as concept
    on concept.id = task.concept_id
   and concept.user_id = task.user_id
  where task.user_id = p_user_id
    and task.plan_id = v_plan.id
    and task.source_type = 'weakness_review'
    and task.source_quiz_attempt_id = p_quiz_attempt_id;

  return pg_catalog.jsonb_build_object(
    'auto_review_tasks', v_auto_review_tasks,
    'unscheduled_weak_concepts', v_unscheduled_concepts
  );
end;
$$;

revoke all on function public.create_auto_review_tasks(
  uuid,
  uuid
) from public, anon, authenticated;


-- 이미 존재하는 자동 복습 묶음도 가능한 범위에서 3단계까지 보완합니다.
do $$
declare
  review_source record;
begin
  for review_source in
    select distinct
      task.user_id,
      task.source_quiz_attempt_id
    from public.study_tasks as task
    join public.study_plans as plan
      on plan.id = task.plan_id
     and plan.user_id = task.user_id
    where task.source_type = 'weakness_review'
      and plan.status = 'active'
    order by task.user_id, task.source_quiz_attempt_id
  loop
    perform public.create_auto_review_tasks(
      review_source.user_id,
      review_source.source_quiz_attempt_id
    );
  end loop;
end;
$$;

select
  'spaced repetition migration: success'
    as migration_result;

commit;
