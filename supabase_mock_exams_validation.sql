do $$
declare
  v_table text;
  v_function regprocedure;
  v_rls_enabled boolean;
  v_security_definer boolean;
  v_proconfig text;
begin
  foreach v_table in array array['mock_exams', 'mock_exam_attempts'] loop
    select class.relrowsecurity into v_rls_enabled
    from pg_catalog.pg_class as class
    join pg_catalog.pg_namespace as namespace on namespace.oid = class.relnamespace
    where namespace.nspname = 'public' and class.relname = v_table;
    if not coalesce(v_rls_enabled, false) then
      raise exception '% 테이블에 RLS가 활성화되지 않았습니다.', v_table;
    end if;
    if (
      select count(*) from pg_catalog.pg_policies as policy
      where policy.schemaname = 'public'
        and policy.tablename = v_table
        and policy.roles = array['authenticated']::name[]
        and policy.cmd in ('SELECT', 'INSERT', 'UPDATE', 'DELETE')
    ) <> 4 then
      raise exception '% 테이블의 사용자 소유권 정책이 없습니다.', v_table;
    end if;
    if pg_catalog.has_table_privilege('authenticated', 'public.' || v_table, 'SELECT')
       or pg_catalog.has_table_privilege('authenticated', 'public.' || v_table, 'INSERT')
       or pg_catalog.has_table_privilege('authenticated', 'public.' || v_table, 'UPDATE')
       or pg_catalog.has_table_privilege('authenticated', 'public.' || v_table, 'DELETE') then
      raise exception '% 테이블의 authenticated 직접 권한이 남아 있습니다.', v_table;
    end if;
  end loop;

  foreach v_function in array array[
    'public.save_mock_exam(uuid,uuid,text,integer,jsonb,text,text,uuid,uuid)'::regprocedure,
    'public.get_mock_exams_by_plan(uuid)'::regprocedure,
    'public.get_mock_exam_state(uuid)'::regprocedure,
    'public.submit_mock_exam_attempt(uuid,jsonb,uuid)'::regprocedure
  ] loop
    select procedure.prosecdef,
           coalesce(pg_catalog.array_to_string(procedure.proconfig, ','), '')
    into v_security_definer, v_proconfig
    from pg_catalog.pg_proc as procedure
    where procedure.oid = v_function;
    if not coalesce(v_security_definer, false)
       or v_proconfig not in ('search_path=', 'search_path=""') then
      raise exception '모의 평가 RPC의 security definer 또는 search_path가 안전하지 않습니다.';
    end if;
    if not pg_catalog.has_function_privilege('authenticated', v_function, 'EXECUTE')
       or pg_catalog.has_function_privilege('anon', v_function, 'EXECUTE') then
      raise exception '모의 평가 RPC 실행 권한이 올바르지 않습니다.';
    end if;
  end loop;

  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conname = 'mock_exams_plan_owner_fk'
  ) or not exists (
    select 1 from pg_catalog.pg_constraint
    where conname = 'mock_exam_attempts_exam_owner_fk'
  ) or not exists (
    select 1 from pg_catalog.pg_constraint
    where conname = 'mock_exams_generation_unique'
  ) or not exists (
    select 1 from pg_catalog.pg_constraint
    where conname = 'mock_exam_attempts_submission_unique'
  ) then
    raise exception '모의 평가 소유권 또는 중복 방지 제약이 누락되었습니다.';
  end if;
end;
$$;

select 'mock exam validation: success' as validation_result;
