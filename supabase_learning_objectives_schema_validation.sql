begin;

set local statement_timeout = '10s';
set transaction read only;

do $$
declare
  v_required_column_count integer;
begin
  if pg_catalog.to_regclass('public.learning_objectives') is null then
    raise exception 'public.learning_objectives 테이블이 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_class as relation
    join pg_catalog.pg_namespace as namespace
      on namespace.oid = relation.relnamespace
    where namespace.nspname = 'public'
      and relation.relname = 'learning_objectives'
      and relation.relrowsecurity
  ) then
    raise exception 'learning_objectives RLS가 활성화되지 않았습니다.';
  end if;

  if pg_catalog.has_table_privilege(
    'anon', 'public.learning_objectives', 'SELECT'
  ) or pg_catalog.has_table_privilege(
    'anon', 'public.learning_objectives', 'INSERT'
  ) or pg_catalog.has_table_privilege(
    'anon', 'public.learning_objectives', 'UPDATE'
  ) or pg_catalog.has_table_privilege(
    'anon', 'public.learning_objectives', 'DELETE'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.learning_objectives', 'SELECT'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.learning_objectives', 'INSERT'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.learning_objectives', 'UPDATE'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.learning_objectives', 'DELETE'
  ) then
    raise exception '3단계 전 learning_objectives 테이블이 API 역할에 열려 있습니다.';
  end if;

  select count(*)
  into v_required_column_count
  from information_schema.columns
  where table_schema = 'public'
    and (
      (table_name = 'study_tasks' and column_name = 'learning_objective_id')
      or (
        table_name = 'learning_materials'
        and column_name = 'learning_objective_id'
      )
      or (
        table_name = 'review_materials'
        and column_name in (
          'learning_objective_id',
          'objective_snapshot',
          'objective_contract_hash'
        )
      )
      or (
        table_name = 'quizzes'
        and column_name in (
          'learning_objective_id',
          'objective_snapshot',
          'objective_contract_hash',
          'reference_learning_material_id',
          'reference_review_material_id'
        )
      )
    );

  if v_required_column_count <> 10 then
    raise exception '학습목표 연결 열이 모두 생성되지 않았습니다.';
  end if;

  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and column_name in (
        'learning_objective_id',
        'objective_snapshot',
        'objective_contract_hash',
        'reference_learning_material_id',
        'reference_review_material_id'
      )
      and table_name in (
        'study_tasks',
        'learning_materials',
        'review_materials',
        'quizzes'
      )
      and is_nullable <> 'YES'
  ) then
    raise exception '호환 단계의 새 연결 열은 nullable이어야 합니다.';
  end if;

  if exists (
    select 1
    from public.study_plans as plan
    left join public.learning_objectives as objective
      on objective.plan_id = plan.id
     and objective.user_id = plan.user_id
     and objective.objective_key = 'legacy_primary'
     and objective.origin = 'legacy_backfill'
    where objective.id is null
  ) then
    raise exception '기존 계획의 호환 학습목표가 누락되었습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    join public.study_plans as plan
      on plan.id = task.plan_id
     and plan.user_id = task.user_id
    left join public.learning_objectives as objective
      on objective.id = task.learning_objective_id
     and objective.plan_id = task.plan_id
     and objective.user_id = task.user_id
    where objective.id is null
  ) then
    raise exception '기존 과제의 호환 학습목표 연결이 누락되었습니다.';
  end if;

  if exists (
    select 1
    from public.learning_objectives as objective
    where objective.origin = 'legacy_backfill'
      and (
        objective.objective_key <> 'legacy_primary'
        or objective.contract_hash is not null
        or objective.sort_order <> 1
      )
  ) then
    raise exception '기존 계획 호환 목표가 과거 계약을 허위로 표현합니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_constraint as constraint_record
    where constraint_record.conrelid = 'public.learning_objectives'::regclass
      and constraint_record.conname = 'learning_objectives_plan_owner_fk'
  ) then
    raise exception '학습목표와 계획의 기본 소유권 외래 키가 없습니다.';
  end if;
end;
$$;

select 'learning objectives schema validation: success'
as validation_result;

rollback;
