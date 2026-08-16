-- supabase_spaced_repetition.sql 실행 후 사용하는 읽기 전용 검증입니다.
begin;
set transaction read only;


do $$
declare
  review_function regprocedure := pg_catalog.to_regprocedure(
    'public.create_auto_review_tasks(uuid,uuid)'
  );
  pending_index text;
  source_index text;
begin
  if not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'study_tasks'
      and column_name = 'review_stage'
      and data_type = 'smallint'
  ) or not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'study_tasks'
      and column_name = 'review_interval_days'
      and data_type = 'smallint'
  ) then
    raise exception '간격 반복 단계 열이 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_constraint as constraint_state
    where constraint_state.conname
      = 'study_tasks_spaced_review_metadata_check'
      and constraint_state.contype = 'c'
  ) then
    raise exception '간격 반복 메타데이터 제약이 없습니다.';
  end if;

  select pg_catalog.pg_get_indexdef(index_state.indexrelid)
  into pending_index
  from pg_catalog.pg_index as index_state
  where index_state.indexrelid = pg_catalog.to_regclass(
    'public.study_tasks_pending_weakness_review_unique'
  )
    and index_state.indisunique
    and index_state.indpred is not null;

  select pg_catalog.pg_get_indexdef(index_state.indexrelid)
  into source_index
  from pg_catalog.pg_index as index_state
  where index_state.indexrelid = pg_catalog.to_regclass(
    'public.study_tasks_weakness_source_attempt_unique'
  )
    and index_state.indisunique
    and index_state.indpred is not null;

  if pending_index is null
     or pending_index not like '%review_stage%'
     or source_index is null
     or source_index not like '%review_stage%'
  then
    raise exception '간격 반복 단계별 중복 방지 인덱스가 올바르지 않습니다.';
  end if;

  if review_function is null then
    raise exception '자동 복습 생성 함수가 없습니다.';
  end if;

  if pg_catalog.pg_get_functiondef(review_function)
       not like '%for v_stage in 1..3%'
     or pg_catalog.pg_get_functiondef(review_function)
       not like '%when 2 then 3%'
     or pg_catalog.pg_get_functiondef(review_function)
       not like '%when 3 then 7%'
     or pg_catalog.pg_get_functiondef(review_function)
       not like '%Asia/Seoul%'
  then
    raise exception '1·3·7일 자동 복습 함수 버전이 적용되지 않았습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'authenticated', review_function, 'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'anon', review_function, 'EXECUTE'
  ) then
    raise exception '내부 자동 복습 함수가 클라이언트에 공개돼 있습니다.';
  end if;
end;
$$;


do $$
begin
  if exists (
    select 1
    from public.study_tasks as task
    where (
        task.source_type = 'weekly_plan'
        and (
          task.review_stage is not null
          or task.review_interval_days is not null
        )
      )
      or (
        task.source_type = 'weakness_review'
        and (
          task.review_stage is null
          or task.review_interval_days is null
          or task.review_stage not between 1 and 3
          or task.review_interval_days <> case task.review_stage
            when 1 then 1
            when 2 then 3
            when 3 then 7
          end
        )
      )
  ) then
    raise exception '과제의 간격 반복 단계 데이터가 올바르지 않습니다.';
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
    raise exception '같은 응시·개념·반복 단계 과제가 중복됐습니다.';
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
    raise exception '같은 계획·개념·반복 단계의 미완료 과제가 중복됐습니다.';
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
end;
$$;


do $$
begin
  if exists (
    with ordered_tasks as (
      select
        task.user_id,
        task.source_quiz_attempt_id,
        task.concept_id,
        task.review_stage,
        task.scheduled_date,
        lag(task.review_stage) over (
          partition by
            task.user_id,
            task.source_quiz_attempt_id,
            task.concept_id
          order by task.review_stage
        ) as previous_stage,
        lag(task.scheduled_date) over (
          partition by
            task.user_id,
            task.source_quiz_attempt_id,
            task.concept_id
          order by task.review_stage
        ) as previous_date
      from public.study_tasks as task
      where task.source_type = 'weakness_review'
    )
    select 1
    from ordered_tasks as task
    where task.review_stage > 1
      and (
        task.previous_stage
          is distinct from task.review_stage - 1
        or task.previous_date is null
        or task.scheduled_date <= task.previous_date
      )
  ) then
    raise exception '간격 반복 단계가 빠졌거나 예정일 순서가 올바르지 않습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    join public.quiz_attempts as attempt
      on attempt.id = task.source_quiz_attempt_id
     and attempt.quiz_id = task.source_quiz_id
     and attempt.user_id = task.user_id
    join public.study_plans as plan
      on plan.id = task.plan_id
     and plan.user_id = task.user_id
    where task.source_type = 'weakness_review'
      and (
        task.scheduled_date < (
          attempt.submitted_at at time zone 'Asia/Seoul'
        )::date + task.review_interval_days
        or task.scheduled_date > plan.start_date + 13
        or task.scheduled_date > plan.target_date
      )
  ) then
    raise exception '간격 목표일 또는 계획 경계를 벗어난 복습이 있습니다.';
  end if;
end;
$$;


do $$
begin
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
            mod(task.scheduled_date - plan.start_date, 7)::text
            || '일차'
          ) ~ '^\d+$'
        then (
          plan.available_schedule
            ->> (
              mod(task.scheduled_date - plan.start_date, 7)::text
              || '일차'
            )
        )::integer
        else 0
      end,
      0
    )
  ) then
    raise exception '간격 반복 일정이 일일 가능 시간을 초과했습니다.';
  end if;
end;
$$;


select
  task.id as task_id,
  concept.canonical_name as concept_name,
  task.review_stage,
  task.review_interval_days,
  task.scheduled_date,
  task.status,
  task.source_quiz_attempt_id
from public.study_tasks as task
join public.learning_concepts as concept
  on concept.id = task.concept_id
 and concept.user_id = task.user_id
where task.source_type = 'weakness_review'
order by
  task.created_at desc,
  task.concept_id,
  task.review_stage;

select
  'spaced repetition validation: success'
    as validation_result;

rollback;
