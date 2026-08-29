begin;

set local statement_timeout = '10s';
set transaction read only;

do $$
declare
  v_required_constraint_count integer;
  v_required_index_count integer;
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

  if not exists (
    select 1
    from pg_catalog.pg_policies as policy
    where policy.schemaname = 'public'
      and policy.tablename = 'learning_objectives'
      and policy.policyname = 'learning_objectives_select_own'
      and policy.cmd = 'SELECT'
      and policy.roles @> array['authenticated'::name]
      and position('auth.uid()' in policy.qual) > 0
      and position('user_id' in policy.qual) > 0
  ) then
    raise exception '본인 학습목표 SELECT RLS 정책이 올바르지 않습니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.pg_policies as policy
    where policy.schemaname = 'public'
      and policy.tablename = 'learning_objectives'
      and policy.cmd <> 'SELECT'
  ) then
    raise exception 'learning_objectives에 클라이언트 쓰기 정책이 열려 있습니다.';
  end if;

  if not pg_catalog.has_table_privilege(
    'authenticated', 'public.learning_objectives', 'SELECT'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.learning_objectives', 'INSERT'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.learning_objectives', 'UPDATE'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.learning_objectives', 'DELETE'
  ) then
    raise exception 'authenticated의 학습목표 권한 경계가 올바르지 않습니다.';
  end if;

  if pg_catalog.has_table_privilege(
    'anon', 'public.learning_objectives', 'SELECT'
  ) or pg_catalog.has_table_privilege(
    'anon', 'public.learning_objectives', 'INSERT'
  ) or pg_catalog.has_table_privilege(
    'anon', 'public.learning_objectives', 'UPDATE'
  ) or pg_catalog.has_table_privilege(
    'anon', 'public.learning_objectives', 'DELETE'
  ) then
    raise exception 'anon에 learning_objectives 권한이 남아 있습니다.';
  end if;

  select count(*)
  into v_required_constraint_count
  from pg_catalog.pg_constraint as constraint_record
  where constraint_record.conname in (
      'review_materials_id_plan_user_unique',
      'study_tasks_objective_owner_fk',
      'learning_materials_objective_owner_fk',
      'review_materials_objective_owner_fk',
      'quizzes_objective_owner_fk',
      'quizzes_reference_learning_material_owner_fk',
      'quizzes_reference_review_material_owner_fk'
    )
    and constraint_record.connamespace = 'public'::regnamespace
    and constraint_record.convalidated;

  if v_required_constraint_count <> 7 then
    raise exception '학습목표 소유권 제약조건이 누락되었거나 검증되지 않았습니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.pg_constraint as constraint_record
    where constraint_record.conname in (
      'study_tasks_objective_owner_fk',
      'learning_materials_objective_owner_fk',
      'review_materials_objective_owner_fk',
      'quizzes_objective_owner_fk',
      'quizzes_reference_learning_material_owner_fk',
      'quizzes_reference_review_material_owner_fk'
    )
      and constraint_record.connamespace = 'public'::regnamespace
      and constraint_record.confdeltype <> 'n'
  ) then
    raise exception '선택 연결의 삭제 동작이 SET NULL이 아닙니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_constraint as constraint_record
    where constraint_record.conrelid = 'public.learning_objectives'::regclass
      and constraint_record.conname = 'learning_objectives_plan_key_unique'
      and constraint_record.contype = 'u'
  ) or not exists (
    select 1
    from pg_catalog.pg_constraint as constraint_record
    where constraint_record.conrelid = 'public.learning_objectives'::regclass
      and constraint_record.conname = 'learning_objectives_plan_order_unique'
      and constraint_record.contype = 'u'
  ) or not exists (
    select 1
    from pg_catalog.pg_constraint as constraint_record
    where constraint_record.conrelid = 'public.quizzes'::regclass
      and constraint_record.conname = 'quizzes_single_reference_material_check'
      and constraint_record.contype = 'c'
      and constraint_record.convalidated
  ) or not exists (
    select 1
    from pg_catalog.pg_constraint as constraint_record
    where constraint_record.conrelid = 'public.review_materials'::regclass
      and constraint_record.conname = 'review_materials_task_unique'
      and constraint_record.contype = 'u'
  ) then
    raise exception '학습목표·참고자료·과제자료 중복 방지 제약조건이 없습니다.';
  end if;

  select count(*)
  into v_required_index_count
  from pg_catalog.pg_indexes as index_record
  where index_record.schemaname = 'public'
    and index_record.indexname in (
      'learning_objectives_user_plan_order_idx',
      'study_tasks_plan_objective_date_idx',
      'learning_materials_plan_objective_created_idx',
      'review_materials_plan_objective_updated_idx',
      'quizzes_plan_objective_updated_idx',
      'quizzes_reference_learning_material_idx',
      'quizzes_reference_review_material_idx'
    );

  if v_required_index_count <> 7 then
    raise exception '학습목표 또는 참고자료 조회 인덱스가 누락되었습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    left join public.learning_objectives as objective
      on objective.id = task.learning_objective_id
     and objective.plan_id = task.plan_id
     and objective.user_id = task.user_id
    where task.learning_objective_id is not null
      and objective.id is null
  ) or exists (
    select 1
    from public.learning_materials as material
    left join public.learning_objectives as objective
      on objective.id = material.learning_objective_id
     and objective.plan_id = material.plan_id
     and objective.user_id = material.user_id
    where material.learning_objective_id is not null
      and objective.id is null
  ) or exists (
    select 1
    from public.review_materials as material
    left join public.learning_objectives as objective
      on objective.id = material.learning_objective_id
     and objective.plan_id = material.plan_id
     and objective.user_id = material.user_id
    where material.learning_objective_id is not null
      and objective.id is null
  ) or exists (
    select 1
    from public.quizzes as quiz
    left join public.learning_objectives as objective
      on objective.id = quiz.learning_objective_id
     and objective.plan_id = quiz.plan_id
     and objective.user_id = quiz.user_id
    where quiz.learning_objective_id is not null
      and objective.id is null
  ) then
    raise exception '학습목표 연결 중 사용자 또는 계획 소유권 불일치가 있습니다.';
  end if;

  if exists (
    select 1
    from public.quizzes as quiz
    left join public.learning_materials as material
      on material.id = quiz.reference_learning_material_id
     and material.plan_id = quiz.plan_id
     and material.user_id = quiz.user_id
    where quiz.reference_learning_material_id is not null
      and material.id is null
  ) or exists (
    select 1
    from public.quizzes as quiz
    left join public.review_materials as material
      on material.id = quiz.reference_review_material_id
     and material.plan_id = quiz.plan_id
     and material.user_id = quiz.user_id
    where quiz.reference_review_material_id is not null
      and material.id is null
  ) then
    raise exception '퀴즈 참고자료 연결 중 사용자 또는 계획 소유권 불일치가 있습니다.';
  end if;
end;
$$;

select 'learning objectives security validation: success'
as validation_result;

rollback;
