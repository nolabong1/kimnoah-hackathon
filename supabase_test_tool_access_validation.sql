begin;

set local statement_timeout = '10s';
set transaction read only;

do $$
declare
  v_definition text;
begin
  if pg_catalog.to_regclass('public.test_tool_access') is null then
    raise exception 'test_tool_access 테이블이 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_class as relation
    join pg_catalog.pg_namespace as namespace
      on namespace.oid = relation.relnamespace
    where namespace.nspname = 'public'
      and relation.relname = 'test_tool_access'
      and relation.relrowsecurity
  ) then
    raise exception 'test_tool_access RLS가 활성화되지 않았습니다.';
  end if;

  if pg_catalog.has_table_privilege(
    'authenticated',
    'public.test_tool_access',
    'SELECT'
  ) or pg_catalog.has_table_privilege(
    'authenticated',
    'public.test_tool_access',
    'INSERT'
  ) or pg_catalog.has_table_privilege(
    'authenticated',
    'public.test_tool_access',
    'UPDATE'
  ) or pg_catalog.has_table_privilege(
    'authenticated',
    'public.test_tool_access',
    'DELETE'
  ) then
    raise exception 'authenticated가 test_tool_access에 직접 접근할 수 있습니다.';
  end if;

  if not pg_catalog.has_function_privilege(
    'authenticated',
    'public.can_use_test_tools()',
    'EXECUTE'
  ) then
    raise exception '테스트 도구 권한 확인 RPC 실행 권한이 없습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'authenticated',
    'public.require_test_tool_access()',
    'EXECUTE'
  ) then
    raise exception '내부 테스트 권한 함수가 직접 공개되어 있습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'authenticated',
    'public.start_shop_test_session_unchecked()',
    'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'authenticated',
    'public.reset_shop_test_session_unchecked(uuid)',
    'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'authenticated',
    'public.reset_today_test_progress_unchecked()',
    'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'authenticated',
    'public.complete_study_plan_for_weekly_review_test_unchecked(uuid)',
    'EXECUTE'
  ) then
    raise exception '권한 검사 전 테스트 구현이 직접 공개되어 있습니다.';
  end if;

  select pg_catalog.pg_get_functiondef(
    'public.start_shop_test_session()'::regprocedure
  ) into v_definition;
  if position('require_test_tool_access' in v_definition) = 0 then
    raise exception '상점 테스트 시작 RPC에 권한 검사가 없습니다.';
  end if;

  select pg_catalog.pg_get_functiondef(
    'public.reset_shop_test_session(uuid)'::regprocedure
  ) into v_definition;
  if position('require_test_tool_access' in v_definition) = 0 then
    raise exception '상점 테스트 초기화 RPC에 권한 검사가 없습니다.';
  end if;

  select pg_catalog.pg_get_functiondef(
    'public.reset_today_test_progress()'::regprocedure
  ) into v_definition;
  if position('require_test_tool_access' in v_definition) = 0 then
    raise exception '오늘 테스트 초기화 RPC에 권한 검사가 없습니다.';
  end if;

  select pg_catalog.pg_get_functiondef(
    'public.complete_study_plan_for_weekly_review_test(uuid)'::regprocedure
  ) into v_definition;
  if position('require_test_tool_access' in v_definition) = 0 then
    raise exception '계획 테스트 완료 RPC에 권한 검사가 없습니다.';
  end if;
end;
$$;

select 'test tool access validation: success' as validation_result;

rollback;
