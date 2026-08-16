-- supabase_weekly_learning_reviews.sql 실행 후 사용하는 읽기 전용 검증입니다.
begin;

do $$
declare
  required_constraint text;
  required_index text;
  required_command text;
begin
  if to_regclass('public.weekly_learning_reviews') is null then
    raise exception 'weekly_learning_reviews 테이블이 없습니다.';
  end if;

  foreach required_constraint in array array[
    'weekly_learning_reviews_plan_owner_fk',
    'weekly_learning_reviews_valid_week',
    'weekly_learning_reviews_user_plan_unique'
  ]
  loop
    if not exists (
      select 1
      from pg_catalog.pg_constraint
      where conname = required_constraint
        and connamespace = 'public'::regnamespace
    ) then
      raise exception '필수 제약조건이 없습니다: %', required_constraint;
    end if;
  end loop;

  foreach required_index in array array[
    'weekly_learning_reviews_user_recent_idx',
    'weekly_learning_reviews_plan_idx'
  ]
  loop
    if to_regclass('public.' || required_index) is null then
      raise exception '필수 인덱스가 없습니다: %', required_index;
    end if;
  end loop;

  if not exists (
    select 1
    from pg_catalog.pg_class
    where oid = 'public.weekly_learning_reviews'::regclass
      and relrowsecurity
  ) then
    raise exception 'weekly_learning_reviews RLS가 비활성화되어 있습니다.';
  end if;

  foreach required_command in array array[
    'SELECT',
    'INSERT',
    'UPDATE',
    'DELETE'
  ]
  loop
    if not exists (
      select 1
      from pg_catalog.pg_policies
      where schemaname = 'public'
        and tablename = 'weekly_learning_reviews'
        and cmd = required_command
        and 'authenticated' = any(roles)
        and (
          position('auth.uid' in coalesce(qual, '')) > 0
          or position('auth.uid' in coalesce(with_check, '')) > 0
        )
    ) then
      raise exception '본인 소유권 정책이 없습니다: %', required_command;
    end if;

    if has_table_privilege(
      'anon',
      'public.weekly_learning_reviews',
      required_command
    ) then
      raise exception 'anon 역할에 테이블 권한이 남아 있습니다: %',
        required_command;
    end if;

    if not has_table_privilege(
      'authenticated',
      'public.weekly_learning_reviews',
      required_command
    ) then
      raise exception 'authenticated 역할에 테이블 권한이 없습니다: %',
        required_command;
    end if;
  end loop;
end;
$$;

select 'weekly learning reviews validation: success'
as validation_result;

rollback;
