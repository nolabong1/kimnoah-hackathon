-- 새 7일 계획을 계획·학습목표·과제까지 한 트랜잭션으로 저장합니다.
begin;

set local lock_timeout = '10s';
set local statement_timeout = '60s';

create or replace function public.save_weekly_study_plan_with_tasks(
  p_title text,
  p_course_name text,
  p_goal text,
  p_current_level smallint,
  p_start_date date,
  p_available_schedule jsonb,
  p_weekly_overview jsonb,
  p_learning_objectives jsonb,
  p_tasks jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_plan public.study_plans%rowtype;
  v_schedule_entry record;
  v_day_offset integer;
  v_allowed_minutes integer;
  v_task_minutes integer;
  v_overview_minutes integer;
  v_schedule_count integer;
  v_objective_count integer;
  v_total_available_minutes integer := 0;
begin
  if v_user_id is null then
    raise exception using
      errcode = '42501',
      message = '로그인이 필요합니다.';
  end if;

  if p_title is null
     or char_length(btrim(p_title)) not between 1 and 100
  then
    raise exception '학습계획 제목은 1자 이상 100자 이하여야 합니다.';
  end if;

  if p_course_name is null
     or char_length(btrim(p_course_name)) not between 1 and 100
  then
    raise exception '과목명은 1자 이상 100자 이하여야 합니다.';
  end if;

  if p_goal is null
     or char_length(btrim(p_goal)) not between 1 and 1000
  then
    raise exception '학습 목표는 1자 이상 1,000자 이하여야 합니다.';
  end if;

  if p_current_level is null or p_current_level not between 1 and 10 then
    raise exception '현재 수준은 1부터 10 사이여야 합니다.';
  end if;

  if p_start_date is null then
    raise exception '학습계획 시작일이 필요합니다.';
  end if;

  if p_available_schedule is null
     or pg_catalog.jsonb_typeof(p_available_schedule) <> 'object'
  then
    raise exception '7일 학습 가능 시간 형식이 올바르지 않습니다.';
  end if;

  select count(*)
  into v_schedule_count
  from pg_catalog.jsonb_object_keys(p_available_schedule);

  if v_schedule_count <> 7
     or exists (
       select 1
       from pg_catalog.jsonb_each(p_available_schedule) as schedule(key, value)
       where schedule.key !~ '^[0-6]일차$'
          or pg_catalog.jsonb_typeof(schedule.value) <> 'number'
          or schedule.value::text !~ '^[0-9]+$'
     )
  then
    raise exception '학습 가능 시간은 0일차부터 6일차까지 정수로 입력해야 합니다.';
  end if;

  for v_schedule_entry in
    select schedule.key, schedule.value
    from pg_catalog.jsonb_each(p_available_schedule) as schedule(key, value)
  loop
    v_allowed_minutes := v_schedule_entry.value::text::integer;
    if v_allowed_minutes not between 0 and 480 then
      raise exception '하루 학습 가능 시간은 0분부터 480분 사이여야 합니다.';
    end if;
    v_total_available_minutes :=
      v_total_available_minutes + v_allowed_minutes;
  end loop;

  if v_total_available_minutes = 0 then
    raise exception '최소 하루 이상의 학습 시간이 필요합니다.';
  end if;

  if p_weekly_overview is null
     or pg_catalog.jsonb_typeof(p_weekly_overview) <> 'array'
     or pg_catalog.jsonb_array_length(p_weekly_overview) <> 7
  then
    raise exception '주간 개요는 정확히 7일이어야 합니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_weekly_overview) as overview(value)
    where pg_catalog.jsonb_typeof(overview.value) <> 'object'
       or pg_catalog.jsonb_typeof(overview.value -> 'day_offset') <> 'number'
       or (overview.value -> 'day_offset')::text !~ '^[0-6]$'
       or pg_catalog.jsonb_typeof(overview.value -> 'daily_focus') <> 'string'
       or char_length(btrim(overview.value ->> 'daily_focus'))
            not between 1 and 500
       or pg_catalog.jsonb_typeof(overview.value -> 'total_minutes') <> 'number'
       or (overview.value -> 'total_minutes')::text !~ '^[0-9]+$'
  ) then
    raise exception '주간 개요 항목 형식이 올바르지 않습니다.';
  end if;

  if exists (
    select overview.value ->> 'day_offset'
    from pg_catalog.jsonb_array_elements(p_weekly_overview) as overview(value)
    group by overview.value ->> 'day_offset'
    having count(*) > 1
  ) then
    raise exception '주간 개요 날짜가 중복되었습니다.';
  end if;

  if p_learning_objectives is null
     or pg_catalog.jsonb_typeof(p_learning_objectives) <> 'array'
  then
    raise exception '학습목표 목록 형식이 올바르지 않습니다.';
  end if;

  if pg_catalog.jsonb_array_length(p_learning_objectives) not between 2 and 5
  then
    raise exception '새 학습계획의 학습목표는 2개 이상 5개 이하여야 합니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_learning_objectives) as objective(value)
    where pg_catalog.jsonb_typeof(objective.value) is distinct from 'object'
       or pg_catalog.jsonb_typeof(objective.value -> 'objective_key')
            is distinct from 'string'
       or objective.value ->> 'objective_key'
            !~ '^[a-z0-9]+(_[a-z0-9]+)*$'
       or char_length(objective.value ->> 'objective_key') not between 1 and 100
       or pg_catalog.jsonb_typeof(objective.value -> 'title')
            is distinct from 'string'
       or char_length(btrim(objective.value ->> 'title')) not between 1 and 200
       or pg_catalog.jsonb_typeof(objective.value -> 'description')
            is distinct from 'string'
       or char_length(btrim(objective.value ->> 'description'))
            not between 1 and 1000
       or pg_catalog.jsonb_typeof(objective.value -> 'target_depth')
            is distinct from 'string'
       or objective.value ->> 'target_depth'
            not in ('foundation', 'developing', 'advanced')
       or objective.value ->> 'target_depth' is distinct from (
            case
              when p_current_level <= 3 then 'foundation'
              when p_current_level <= 7 then 'developing'
              else 'advanced'
            end
          )
       or case
            when pg_catalog.jsonb_typeof(
              objective.value -> 'evidence_requirements'
            ) = 'array'
            then pg_catalog.jsonb_array_length(
              objective.value -> 'evidence_requirements'
            ) <> 3
            else true
          end
       or objective.value #>> '{evidence_requirements,0,key}'
            is distinct from 'explain'
       or objective.value #>> '{evidence_requirements,1,key}'
            is distinct from 'apply'
       or objective.value #>> '{evidence_requirements,2,key}'
            is distinct from 'differentiate'
       or pg_catalog.jsonb_typeof(
            objective.value #> '{evidence_requirements,0,description}'
          ) is distinct from 'string'
       or pg_catalog.jsonb_typeof(
            objective.value #> '{evidence_requirements,1,description}'
          ) is distinct from 'string'
       or pg_catalog.jsonb_typeof(
            objective.value #> '{evidence_requirements,2,description}'
          ) is distinct from 'string'
       or char_length(btrim(
            objective.value #>> '{evidence_requirements,0,description}'
          )) not between 1 and 300
       or char_length(btrim(
            objective.value #>> '{evidence_requirements,1,description}'
          )) not between 1 and 300
       or char_length(btrim(
            objective.value #>> '{evidence_requirements,2,description}'
          )) not between 1 and 300
       or pg_catalog.jsonb_typeof(objective.value -> 'contract_hash')
            is distinct from 'string'
       or objective.value ->> 'contract_hash' !~ '^[0-9a-f]{64}$'
  ) then
    raise exception '학습목표 계약 형식이 올바르지 않습니다.';
  end if;

  if exists (
    select objective.value ->> 'objective_key'
    from pg_catalog.jsonb_array_elements(p_learning_objectives) as objective(value)
    group by objective.value ->> 'objective_key'
    having count(*) > 1
  ) then
    raise exception '학습목표 키가 중복되었습니다.';
  end if;

  if p_tasks is null
     or pg_catalog.jsonb_typeof(p_tasks) <> 'array'
     or pg_catalog.jsonb_array_length(p_tasks) not between 1 and 100
  then
    raise exception '학습 과제는 1개 이상 100개 이하여야 합니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_tasks) as task(value)
    where pg_catalog.jsonb_typeof(task.value) is distinct from 'object'
       or pg_catalog.jsonb_typeof(task.value -> 'day_offset')
            is distinct from 'number'
       or (task.value -> 'day_offset')::text !~ '^[0-6]$'
       or pg_catalog.jsonb_typeof(task.value -> 'objective_key')
            is distinct from 'string'
       or task.value ->> 'objective_key' !~ '^[a-z0-9]+(_[a-z0-9]+)*$'
       or pg_catalog.jsonb_typeof(task.value -> 'title')
            is distinct from 'string'
       or char_length(btrim(task.value ->> 'title')) not between 1 and 200
       or pg_catalog.jsonb_typeof(task.value -> 'description')
            is distinct from 'string'
       or char_length(task.value ->> 'description') > 4000
       or pg_catalog.jsonb_typeof(task.value -> 'task_type')
            is distinct from 'string'
       or task.value ->> 'task_type' not in ('learn', 'review', 'quiz')
       or pg_catalog.jsonb_typeof(task.value -> 'estimated_minutes')
            is distinct from 'number'
       or (task.value -> 'estimated_minutes')::text !~ '^[0-9]+$'
  ) then
    raise exception '학습 과제 항목 형식이 올바르지 않습니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_tasks) as task(value)
    where (task.value ->> 'estimated_minutes')::integer not between 1 and 480
  ) then
    raise exception '과제 예상 시간은 1분부터 480분 사이여야 합니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_tasks) as task(value)
    where not exists (
      select 1
      from pg_catalog.jsonb_array_elements(p_learning_objectives)
        as objective(value)
      where objective.value ->> 'objective_key'
            = task.value ->> 'objective_key'
    )
  ) then
    raise exception '과제가 존재하지 않는 학습목표를 참조합니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_learning_objectives)
      as objective(value)
    where not exists (
      select 1
      from pg_catalog.jsonb_array_elements(p_tasks) as task(value)
      where task.value ->> 'objective_key'
            = objective.value ->> 'objective_key'
    )
  ) then
    raise exception '연결된 과제가 없는 학습목표가 있습니다.';
  end if;

  for v_day_offset in 0..6 loop
    v_allowed_minutes := (
      p_available_schedule ->> (v_day_offset::text || '일차')
    )::integer;

    select coalesce(
      sum((task.value ->> 'estimated_minutes')::integer),
      0
    )
    into v_task_minutes
    from pg_catalog.jsonb_array_elements(p_tasks) as task(value)
    where (task.value ->> 'day_offset')::integer = v_day_offset;

    select (overview.value ->> 'total_minutes')::integer
    into v_overview_minutes
    from pg_catalog.jsonb_array_elements(p_weekly_overview) as overview(value)
    where (overview.value ->> 'day_offset')::integer = v_day_offset;

    if v_overview_minutes is null then
      raise exception '주간 개요에 %일차가 없습니다.', v_day_offset;
    end if;

    if v_task_minutes <> v_overview_minutes then
      raise exception '주간 개요와 실제 과제 시간이 일치하지 않습니다.';
    end if;

    if v_task_minutes > v_allowed_minutes then
      raise exception '%일차 과제가 학습 가능 시간을 초과했습니다.', v_day_offset;
    end if;
  end loop;

  insert into public.study_plans (
    user_id,
    title,
    course_name,
    goal,
    current_level,
    start_date,
    target_date,
    available_schedule,
    weekly_overview,
    status
  )
  values (
    v_user_id,
    btrim(p_title),
    btrim(p_course_name),
    btrim(p_goal),
    p_current_level,
    p_start_date,
    p_start_date + 6,
    p_available_schedule,
    p_weekly_overview,
    'active'
  )
  returning * into v_plan;

  insert into public.learning_objectives (
    user_id,
    plan_id,
    objective_key,
    title,
    description,
    target_depth,
    evidence_requirements,
    contract_hash,
    sort_order,
    origin
  )
  select
    v_user_id,
    v_plan.id,
    objective.value ->> 'objective_key',
    btrim(objective.value ->> 'title'),
    btrim(objective.value ->> 'description'),
    objective.value ->> 'target_depth',
    objective.value -> 'evidence_requirements',
    objective.value ->> 'contract_hash',
    objective.ordinality::smallint,
    'generated'
  from pg_catalog.jsonb_array_elements(p_learning_objectives)
    with ordinality as objective(value, ordinality);

  get diagnostics v_objective_count = row_count;

  insert into public.study_tasks (
    user_id,
    plan_id,
    learning_objective_id,
    scheduled_date,
    title,
    description,
    task_type,
    estimated_minutes,
    status
  )
  select
    v_user_id,
    v_plan.id,
    objective.id,
    p_start_date + (task.value ->> 'day_offset')::integer,
    btrim(task.value ->> 'title'),
    task.value ->> 'description',
    task.value ->> 'task_type',
    (task.value ->> 'estimated_minutes')::integer,
    'pending'
  from pg_catalog.jsonb_array_elements(p_tasks) as task(value)
  join public.learning_objectives as objective
    on objective.plan_id = v_plan.id
   and objective.user_id = v_user_id
   and objective.objective_key = task.value ->> 'objective_key';

  return pg_catalog.to_jsonb(v_plan) || pg_catalog.jsonb_build_object(
    'learning_objective_count',
    v_objective_count
  );
end;
$$;

-- 이전 8인자 함수는 남겨 과거 migration 이력을 보존하되 API 실행은 차단합니다.
revoke all on function public.save_weekly_study_plan_with_tasks(
  text,
  text,
  text,
  smallint,
  date,
  jsonb,
  jsonb,
  jsonb
) from public, anon, authenticated;

revoke all on function public.save_weekly_study_plan_with_tasks(
  text,
  text,
  text,
  smallint,
  date,
  jsonb,
  jsonb,
  jsonb,
  jsonb
) from public, anon, authenticated;

grant execute on function public.save_weekly_study_plan_with_tasks(
  text,
  text,
  text,
  smallint,
  date,
  jsonb,
  jsonb,
  jsonb,
  jsonb
) to authenticated;

commit;
