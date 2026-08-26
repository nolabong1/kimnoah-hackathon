begin;
set transaction read only;

do $$
declare
  v_function_oid regprocedure :=
    to_regprocedure('public.get_dashboard_snapshot(uuid,text)');
  v_is_security_definer boolean;
  v_config text[];
begin
  if v_function_oid is null then
    raise exception 'get_dashboard_snapshot RPC가 없습니다.';
  end if;

  select procedure.prosecdef, procedure.proconfig
  into v_is_security_definer, v_config
  from pg_catalog.pg_proc as procedure
  where procedure.oid = v_function_oid;

  if v_is_security_definer is distinct from true then
    raise exception 'get_dashboard_snapshot은 security definer여야 합니다.';
  end if;

  if not exists (
    select 1
    from unnest(coalesce(v_config, array[]::text[])) as config(value)
    where config.value in ('search_path=', 'search_path=""')
  ) then
    raise exception 'get_dashboard_snapshot의 search_path가 안전하지 않습니다.';
  end if;

  if not pg_catalog.has_function_privilege(
    'authenticated',
    'public.get_dashboard_snapshot(uuid,text)',
    'execute'
  ) then
    raise exception 'authenticated 실행 권한이 없습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'anon',
    'public.get_dashboard_snapshot(uuid,text)',
    'execute'
  ) then
    raise exception 'anon은 get_dashboard_snapshot을 실행할 수 없어야 합니다.';
  end if;

end;
$$;

select 'dashboard snapshot validation: success' as validation_result;

rollback;
