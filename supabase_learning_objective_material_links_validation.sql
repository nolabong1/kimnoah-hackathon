-- 036_learning_objective_material_links 적용 결과를 읽기 전용으로 검증합니다.
begin;

set transaction read only;

do $$
declare
  v_function_definition text;
begin
  if pg_catalog.to_regprocedure(
    'public.sync_review_material_learning_objective()'
  ) is null then
    raise exception '학습자료 목표 동기화 함수가 없습니다.';
  end if;

  select pg_catalog.pg_get_functiondef(routine.oid)
  into v_function_definition
  from pg_catalog.pg_proc as routine
  join pg_catalog.pg_namespace as namespace
    on namespace.oid = routine.pronamespace
  where namespace.nspname = 'public'
    and routine.proname = 'sync_review_material_learning_objective'
    and routine.pronargs = 0;

  if not exists (
    select 1
    from pg_catalog.pg_proc as routine
    join pg_catalog.pg_namespace as namespace
      on namespace.oid = routine.pronamespace
    cross join lateral pg_catalog.unnest(routine.proconfig) as config(value)
    where namespace.nspname = 'public'
      and routine.proname = 'sync_review_material_learning_objective'
      and routine.pronargs = 0
      and config.value in ('search_path=', 'search_path=""')
  ) then
    raise exception '학습자료 목표 동기화 함수의 search_path가 안전하지 않습니다.';
  end if;

  if pg_catalog.has_function_privilege(
       'authenticated',
       'public.sync_review_material_learning_objective()',
       'EXECUTE'
     )
     or v_function_definition not like '%study_tasks%'
     or v_function_definition not like '%learning_materials%'
     or v_function_definition not like '%objective_snapshot%'
  then
    raise exception '학습자료 목표 동기화 함수의 권한 또는 핵심 검증이 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_trigger as trigger
    join pg_catalog.pg_class as relation
      on relation.oid = trigger.tgrelid
    join pg_catalog.pg_namespace as namespace
      on namespace.oid = relation.relnamespace
    where namespace.nspname = 'public'
      and relation.relname = 'review_materials'
      and trigger.tgname = 'review_materials_sync_learning_objective'
      and not trigger.tgisinternal
      and trigger.tgenabled <> 'D'
  ) then
    raise exception '복습자료 목표 동기화 트리거가 없습니다.';
  end if;

  if exists (
    select 1
    from public.review_materials as material
    join public.study_tasks as task
      on task.id = material.task_id
     and task.plan_id = material.plan_id
     and task.user_id = material.user_id
    where material.learning_objective_id
          is distinct from task.learning_objective_id
  ) then
    raise exception '과제와 복습자료의 학습목표가 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.review_materials as material
    join public.learning_materials as source
      on source.id = material.source_material_id
     and source.plan_id = material.plan_id
     and source.user_id = material.user_id
    where material.learning_objective_id
          is distinct from source.learning_objective_id
  ) then
    raise exception '원본과 복습자료의 학습목표가 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.review_materials as material
    join public.learning_objectives as objective
      on objective.id = material.learning_objective_id
     and objective.plan_id = material.plan_id
     and objective.user_id = material.user_id
    where objective.origin = 'generated'
      and (
        material.objective_contract_hash is distinct from objective.contract_hash
        or material.objective_snapshot is distinct from
          pg_catalog.jsonb_build_object(
            'objective_key', objective.objective_key,
            'title', objective.title,
            'description', objective.description,
            'target_depth', objective.target_depth,
            'evidence_requirements', objective.evidence_requirements
          )
      )
  ) then
    raise exception '생성 학습목표의 자료 스냅샷 또는 해시가 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.review_materials as material
    join public.learning_objectives as objective
      on objective.id = material.learning_objective_id
     and objective.plan_id = material.plan_id
     and objective.user_id = material.user_id
    where objective.origin = 'legacy_backfill'
      and (
        material.objective_snapshot is not null
        or material.objective_contract_hash is not null
      )
  ) then
    raise exception '기존 계획 호환 목표에 거짓 계약 스냅샷이 저장됐습니다.';
  end if;
end;
$$;

select 'learning objective material links validation: success'
as validation_result;

rollback;
