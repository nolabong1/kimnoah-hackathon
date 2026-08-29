begin;

set local statement_timeout = '10s';
set transaction read only;

do $$
declare
  v_definition text;
begin
  if pg_catalog.to_regprocedure(
    'public.save_weekly_study_plan_with_tasks(text,text,text,smallint,date,jsonb,jsonb,jsonb,jsonb)'
  ) is null then
    raise exception '학습목표 포함 계획 저장 RPC가 없습니다.';
  end if;

  if not pg_catalog.has_function_privilege(
    'authenticated',
    'public.save_weekly_study_plan_with_tasks(text,text,text,smallint,date,jsonb,jsonb,jsonb,jsonb)',
    'EXECUTE'
  ) then
    raise exception 'authenticated에 새 계획 저장 RPC 실행 권한이 없습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'anon',
    'public.save_weekly_study_plan_with_tasks(text,text,text,smallint,date,jsonb,jsonb,jsonb,jsonb)',
    'EXECUTE'
  ) then
    raise exception 'anon이 새 계획 저장 RPC를 실행할 수 있습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'authenticated',
    'public.save_weekly_study_plan_with_tasks(text,text,text,smallint,date,jsonb,jsonb,jsonb)',
    'EXECUTE'
  ) then
    raise exception '학습목표를 저장하지 않는 이전 RPC 실행 권한이 남아 있습니다.';
  end if;

  select pg_catalog.pg_get_functiondef(
    'public.save_weekly_study_plan_with_tasks(text,text,text,smallint,date,jsonb,jsonb,jsonb,jsonb)'::regprocedure
  )
  into v_definition;

  if position('security definer' in lower(v_definition)) = 0
     or position('auth.uid()' in v_definition) = 0
     or position('insert into public.study_plans' in v_definition) = 0
     or position('insert into public.learning_objectives' in v_definition) = 0
     or position('insert into public.study_tasks' in v_definition) = 0
     or position('learning_objective_id' in v_definition) = 0
     or position('contract_hash' in v_definition) = 0
     or position('learning_objective_count' in v_definition) = 0
  then
    raise exception '학습목표 포함 계획 저장 RPC의 원자성 또는 보안 경계가 올바르지 않습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace
      on namespace.oid = procedure.pronamespace
    cross join lateral unnest(procedure.proconfig) as config(value)
    where namespace.nspname = 'public'
      and procedure.oid = (
        'public.save_weekly_study_plan_with_tasks(text,text,text,smallint,date,jsonb,jsonb,jsonb,jsonb)'::regprocedure
      )
      and procedure.prosecdef
      and config.value like 'search_path=%'
  ) then
    raise exception '새 계획 저장 RPC의 안전한 search_path가 없습니다.';
  end if;

  if exists (
    select 1
    from public.learning_objectives as objective
    where objective.origin = 'generated'
      and objective.contract_hash is null
  ) then
    raise exception '해시가 없는 생성 학습목표가 있습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    join public.learning_objectives as objective
      on objective.id = task.learning_objective_id
    where objective.origin = 'generated'
      and (
        objective.plan_id <> task.plan_id
        or objective.user_id <> task.user_id
      )
  ) then
    raise exception '생성 과제와 학습목표의 소유권이 일치하지 않습니다.';
  end if;
end;
$$;

select 'learning objective plan save validation: success'
as validation_result;

rollback;
