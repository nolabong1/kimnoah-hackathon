begin;

set local statement_timeout = '10s';
set transaction read only;

do $$
declare
  v_definition text;
begin
  if pg_catalog.has_table_privilege(
    'authenticated', 'public.study_plans', 'INSERT'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.study_plans', 'UPDATE'
  ) then
    raise exception 'study_plans 직접 생성 또는 수정 권한이 남아 있습니다.';
  end if;

  if not pg_catalog.has_table_privilege(
    'authenticated', 'public.study_plans', 'SELECT'
  ) or not pg_catalog.has_table_privilege(
    'authenticated', 'public.study_plans', 'DELETE'
  ) then
    raise exception 'study_plans 조회 또는 본인 계획 삭제 권한이 없습니다.';
  end if;

  if pg_catalog.has_table_privilege(
    'authenticated', 'public.study_tasks', 'INSERT'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.study_tasks', 'UPDATE'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.study_tasks', 'DELETE'
  ) then
    raise exception 'study_tasks 직접 쓰기 권한이 남아 있습니다.';
  end if;

  if pg_catalog.has_table_privilege(
    'authenticated', 'public.quizzes', 'INSERT'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.quizzes', 'UPDATE'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.quizzes', 'DELETE'
  ) then
    raise exception 'quizzes 직접 쓰기 권한이 남아 있습니다.';
  end if;

  if not pg_catalog.has_table_privilege(
    'authenticated', 'public.study_tasks', 'SELECT'
  ) or not pg_catalog.has_table_privilege(
    'authenticated', 'public.quizzes', 'SELECT'
  ) then
    raise exception '과제 또는 퀴즈 조회 권한이 없습니다.';
  end if;

  if not pg_catalog.has_function_privilege(
    'authenticated',
    'public.save_weekly_study_plan_with_tasks(text,text,text,smallint,date,jsonb,jsonb,jsonb)',
    'EXECUTE'
  ) then
    raise exception '원자적 학습계획 저장 RPC 권한이 없습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'anon',
    'public.save_weekly_study_plan_with_tasks(text,text,text,smallint,date,jsonb,jsonb,jsonb)',
    'EXECUTE'
  ) then
    raise exception '익명 사용자가 학습계획 저장 RPC를 실행할 수 있습니다.';
  end if;

  if not (
    pg_catalog.has_function_privilege(
      'authenticated',
      'public.save_quiz_with_concepts(uuid,uuid,text,text,text,jsonb,jsonb)',
      'EXECUTE'
    )
    or (
      pg_catalog.to_regprocedure(
        'public.save_quiz_with_concepts(uuid,uuid,text,text,text,jsonb,jsonb,uuid,uuid)'
      ) is not null
      and pg_catalog.has_function_privilege(
        'authenticated',
        'public.save_quiz_with_concepts(uuid,uuid,text,text,text,jsonb,jsonb,uuid,uuid)',
        'EXECUTE'
      )
      and not pg_catalog.has_function_privilege(
        'authenticated',
        'public.save_quiz_with_concepts(uuid,uuid,text,text,text,jsonb,jsonb)',
        'EXECUTE'
      )
    )
  ) then
    raise exception '사용자에게 현재 퀴즈 저장 RPC 권한이 없습니다.';
  end if;

  select pg_catalog.pg_get_functiondef(
    'public.save_weekly_study_plan_with_tasks(text,text,text,smallint,date,jsonb,jsonb,jsonb)'::regprocedure
  ) into v_definition;

  if position('security definer' in lower(v_definition)) = 0
     or position('auth.uid()' in v_definition) = 0
     or position('''pending''' in v_definition) = 0
  then
    raise exception '학습계획 저장 RPC의 보안 경계가 올바르지 않습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace
      on namespace.oid = procedure.pronamespace
    cross join lateral unnest(procedure.proconfig) as config(value)
    where namespace.nspname = 'public'
      and procedure.proname = 'save_weekly_study_plan_with_tasks'
      and procedure.prosecdef
      and config.value like 'search_path=%'
  ) then
    raise exception '학습계획 저장 RPC의 안전한 search_path가 없습니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.pg_policies as policy
    where policy.schemaname = 'public'
      and policy.tablename in ('study_plans', 'study_tasks', 'quizzes')
      and policy.policyname in ('insert_own', 'update_own')
  ) then
    raise exception '핵심 테이블의 직접 생성·수정 RLS 정책이 남아 있습니다.';
  end if;
end;
$$;

select 'core write boundary validation: success' as validation_result;

rollback;
