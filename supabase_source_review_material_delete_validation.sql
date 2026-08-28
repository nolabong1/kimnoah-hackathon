begin;

set local statement_timeout = '10s';
set transaction read only;

do $$
declare
  v_definition text;
begin
  if pg_catalog.to_regprocedure(
    'public.delete_source_review_material(uuid,uuid,uuid)'
  ) is null then
    raise exception 'delete_source_review_material RPC가 없습니다.';
  end if;

  if not pg_catalog.has_function_privilege(
    'authenticated',
    'public.delete_source_review_material(uuid,uuid,uuid)',
    'EXECUTE'
  ) then
    raise exception '인증 사용자의 복습자료 삭제 RPC 실행 권한이 없습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'anon',
    'public.delete_source_review_material(uuid,uuid,uuid)',
    'EXECUTE'
  ) then
    raise exception '익명 사용자가 복습자료 삭제 RPC를 실행할 수 있습니다.';
  end if;

  if not pg_catalog.has_table_privilege(
    'authenticated', 'public.review_materials', 'DELETE'
  ) or not pg_catalog.has_table_privilege(
    'authenticated', 'public.learning_materials', 'DELETE'
  ) then
    raise exception 'security invoker 삭제에 필요한 테이블 권한이 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_class as relation
    join pg_catalog.pg_namespace as namespace
      on namespace.oid = relation.relnamespace
    where namespace.nspname = 'public'
      and relation.relname in ('review_materials', 'learning_materials')
      and relation.relrowsecurity
    group by namespace.nspname
    having count(*) = 2
  ) then
    raise exception '복습자료 삭제 대상 테이블의 RLS가 올바르지 않습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace
      on namespace.oid = procedure.pronamespace
    cross join lateral unnest(procedure.proconfig) as config(value)
    where namespace.nspname = 'public'
      and procedure.proname = 'delete_source_review_material'
      and not procedure.prosecdef
      and config.value like 'search_path=%'
  ) then
    raise exception '복습자료 삭제 RPC의 실행 권한 또는 search_path가 안전하지 않습니다.';
  end if;

  select pg_catalog.pg_get_functiondef(
    'public.delete_source_review_material(uuid,uuid,uuid)'::regprocedure
  ) into v_definition;

  if position('auth.uid()' in v_definition) = 0
     or position('delete from public.review_materials' in lower(v_definition)) = 0
     or position('delete from public.learning_materials' in lower(v_definition)) = 0
     or position('task_id is null' in lower(v_definition)) = 0
  then
    raise exception '복습자료 삭제 RPC의 소유권 또는 대상 제한이 올바르지 않습니다.';
  end if;
end;
$$;

select 'source review material delete validation: success'
as validation_result;

rollback;
