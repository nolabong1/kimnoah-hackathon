do $$
declare
  v_table_name text;
  v_policy_count integer;
  v_function_name text;
  v_function_oid oid;
begin
  foreach v_table_name in array array[
    'learning_assessments',
    'learning_assessment_attempts'
  ] loop
    if pg_catalog.to_regclass('public.' || v_table_name) is null then
      raise exception '% 테이블이 없습니다.', v_table_name;
    end if;

    if not exists (
      select 1
      from pg_catalog.pg_class as table_info
      join pg_catalog.pg_namespace as namespace
        on namespace.oid = table_info.relnamespace
      where namespace.nspname = 'public'
        and table_info.relname = v_table_name
        and table_info.relrowsecurity
    ) then
      raise exception '% 테이블의 RLS가 활성화되지 않았습니다.', v_table_name;
    end if;

    select count(*) into v_policy_count
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename = v_table_name
      and 'authenticated' = any (roles);

    if v_policy_count < 4 then
      raise exception '% 테이블의 사용자 소유권 정책이 부족합니다.', v_table_name;
    end if;

    if pg_catalog.has_table_privilege(
      'authenticated',
      'public.' || v_table_name,
      'SELECT'
    ) or pg_catalog.has_table_privilege(
      'authenticated',
      'public.' || v_table_name,
      'INSERT'
    ) then
      raise exception '% 테이블에 직접 접근 권한이 남아 있습니다.', v_table_name;
    end if;
  end loop;

  foreach v_function_name in array array[
    'public.save_learning_assessment_pair(uuid,uuid,text,jsonb,text,jsonb,text,text)',
    'public.get_learning_assessment_state(uuid)',
    'public.submit_learning_assessment_attempt(uuid,jsonb,uuid)'
  ] loop
    v_function_oid := pg_catalog.to_regprocedure(v_function_name);
    if v_function_oid is null then
      raise exception '% RPC가 없습니다.', v_function_name;
    end if;
    if not pg_catalog.has_function_privilege(
      'authenticated',
      v_function_name,
      'EXECUTE'
    ) then
      raise exception '% RPC의 authenticated 실행 권한이 없습니다.', v_function_name;
    end if;
    if not exists (
      select 1
      from pg_catalog.pg_proc as procedure
      cross join lateral pg_catalog.unnest(
        coalesce(procedure.proconfig, array[]::text[])
      ) as config(value)
      where procedure.oid = v_function_oid
        and procedure.prosecdef
        and config.value in ('search_path=', 'search_path=""')
    ) then
      raise exception '% RPC의 security definer 또는 search_path가 안전하지 않습니다.',
        v_function_name;
    end if;
  end loop;

  if not exists (
    select 1
    from pg_catalog.pg_constraint
    where conname = 'learning_assessments_plan_owner_fk'
  ) or not exists (
    select 1
    from pg_catalog.pg_constraint
    where conname = 'learning_assessment_attempts_assessment_owner_fk'
  ) then
    raise exception '평가 소유권 복합 외래 키가 없습니다.';
  end if;

  raise notice 'learning assessment schema validation: success';
end;
$$;
