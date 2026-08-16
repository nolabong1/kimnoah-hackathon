-- supabase_auto_review_tasks.sql과 supabase_spaced_repetition.sql 실행 후
-- 사용하는 읽기 전용 검증입니다.
begin;

do $$
declare
  submit_function regprocedure := pg_catalog.to_regprocedure(
    'public.submit_quiz_attempt(uuid,timestamptz,jsonb,uuid)'
  );
  review_function regprocedure := pg_catalog.to_regprocedure(
    'public.create_auto_review_tasks(uuid,uuid)'
  );
  overview_function regprocedure := pg_catalog.to_regprocedure(
    'public.refresh_study_plan_weekly_overview(uuid,uuid)'
  );
begin
  if submit_function is null
     or review_function is null
     or overview_function is null
  then
    raise exception '자동 복습 처리 함수가 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    where procedure.oid = submit_function
      and procedure.prosecdef
      and coalesce(procedure.proconfig::text, '')
        like '%search_path=%'
  ) then
    raise exception '퀴즈 제출 RPC 보안 설정이 올바르지 않습니다.';
  end if;

  if not pg_catalog.has_function_privilege(
    'authenticated',
    submit_function,
    'EXECUTE'
  ) then
    raise exception 'authenticated 퀴즈 제출 권한이 없습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'authenticated',
    review_function,
    'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'authenticated',
    overview_function,
    'EXECUTE'
  ) then
    raise exception '자동 복습 내부 함수가 외부에 공개되어 있습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'anon',
    submit_function,
    'EXECUTE'
  ) then
    raise exception 'anon 퀴즈 제출 권한이 남아 있습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_index as index_state
    where index_state.indexrelid = (
      'public.study_tasks_weakness_source_attempt_unique'
    )::regclass
      and index_state.indisunique
      and index_state.indpred is not null
  ) then
    raise exception '응시별 자동 복습 중복 방지 인덱스가 올바르지 않습니다.';
  end if;
end;
$$;


do $$
begin
  if exists (
    select 1
    from public.study_tasks as task
    where task.source_type = 'weakness_review'
      and (
        task.task_type <> 'review'
        or task.estimated_minutes <> 20
        or task.concept_id is null
        or task.source_quiz_id is null
        or task.source_quiz_attempt_id is null
        or task.review_stage is null
        or task.review_interval_days is null
        or task.review_stage not between 1 and 3
        or task.review_interval_days <> case task.review_stage
          when 1 then 1
          when 2 then 3
          when 3 then 7
        end
      )
  ) then
    raise exception '자동 복습 과제 형식이 올바르지 않습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    join public.quiz_attempts as attempt
      on attempt.id = task.source_quiz_attempt_id
     and attempt.quiz_id = task.source_quiz_id
     and attempt.user_id = task.user_id
    where task.source_type = 'weakness_review'
      and task.scheduled_date < (
        attempt.submitted_at at time zone 'Asia/Seoul'
      )::date + task.review_interval_days
  ) then
    raise exception '자동 복습 과제가 응시 당일 이전에 배치됐습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    join public.study_plans as plan
      on plan.id = task.plan_id
     and plan.user_id = task.user_id
    where task.source_type = 'weakness_review'
      and task.scheduled_date > plan.start_date + 13
  ) then
    raise exception '자동 복습 과제가 최대 연장 범위를 넘었습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    where task.source_type = 'weakness_review'
    group by
      task.user_id,
      task.source_quiz_attempt_id,
      task.concept_id,
      task.review_stage
    having count(*) > 1
  ) then
    raise exception '같은 응시·개념·단계의 자동 복습 과제가 중복됐습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    where task.source_type = 'weakness_review'
      and task.status = 'pending'
    group by
      task.user_id,
      task.plan_id,
      task.concept_id,
      task.review_stage
    having count(*) > 1
  ) then
    raise exception '같은 계획·개념·단계의 미완료 복습 과제가 중복됐습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    where task.source_type = 'weakness_review'
      and task.status = 'pending'
    group by task.user_id, task.plan_id, task.concept_id
    having count(distinct task.source_quiz_attempt_id) > 1
  ) then
    raise exception '같은 개념에 서로 다른 미완료 복습 묶음이 겹칩니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    where task.source_type = 'weakness_review'
      and not exists (
        select 1
        from public.concept_mastery_events as event
        where event.user_id = task.user_id
          and event.quiz_attempt_id = task.source_quiz_attempt_id
          and event.concept_id = task.concept_id
          and not event.is_correct
      )
  ) then
    raise exception '오답이 없는 응시에서 자동 복습 과제가 생성됐습니다.';
  end if;
end;
$$;


do $$
begin
  if exists (
    select 1
    from public.study_plans as plan
    join public.study_tasks as weakness_task
      on weakness_task.plan_id = plan.id
     and weakness_task.user_id = plan.user_id
     and weakness_task.source_type = 'weakness_review'
    where plan.target_date < weakness_task.scheduled_date
  ) then
    raise exception '계획 종료일이 자동 복습 예정일보다 빠릅니다.';
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
    where exists (
      select 1
      from public.study_tasks as task
      where task.user_id = plan.user_id
        and task.plan_id = plan.id
        and task.source_type = 'weakness_review'
    )
      and overview_total.total_minutes
        is distinct from actual_total.total_minutes
  ) then
    raise exception 'weekly_overview와 실제 과제 시간이 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.study_plans as plan
    join public.study_tasks as task
      on task.plan_id = plan.id
     and task.user_id = plan.user_id
    where exists (
      select 1
      from public.study_tasks as weakness_task
      where weakness_task.user_id = plan.user_id
        and weakness_task.plan_id = plan.id
        and weakness_task.source_type = 'weakness_review'
    )
    group by
      plan.id,
      plan.user_id,
      plan.start_date,
      plan.available_schedule,
      task.scheduled_date
    having sum(task.estimated_minutes) > coalesce(
      case
        when plan.available_schedule
          ->> (
            mod(
              task.scheduled_date - plan.start_date,
              7
            )::text || '일차'
          ) ~ '^\d+$'
        then (
          plan.available_schedule
            ->> (
              mod(
                task.scheduled_date - plan.start_date,
                7
              )::text || '일차'
            )
        )::integer
        else 0
      end,
      0
    )
  ) then
    raise exception '일일 학습 가능 시간을 초과한 계획이 있습니다.';
  end if;
end;
$$;


select
  task.id as task_id,
  plan.title as plan_title,
  concept.canonical_name as concept_name,
  task.scheduled_date,
  task.estimated_minutes,
  task.review_stage,
  task.review_interval_days,
  task.status,
  task.source_quiz_attempt_id
from public.study_tasks as task
join public.study_plans as plan
  on plan.id = task.plan_id
 and plan.user_id = task.user_id
join public.learning_concepts as concept
  on concept.id = task.concept_id
 and concept.user_id = task.user_id
where task.source_type = 'weakness_review'
order by task.created_at desc;

select 'auto review task validation: success'
  as validation_result;

rollback;
