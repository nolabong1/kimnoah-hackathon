-- supabase_study_rooms.sql 실행 후 사용하는 읽기 전용 검증입니다.
begin;
set transaction read only;

do $$
declare
  required_constraint text;
  room_function regprocedure;
  room_definition text;
begin
  if to_regclass('public.user_study_rooms') is null then
    raise exception '사용자 학습방 테이블이 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_class
    where oid = 'public.user_study_rooms'::regclass
      and relrowsecurity
  ) then
    raise exception '사용자 학습방 RLS가 비활성화돼 있습니다.';
  end if;

  if not has_table_privilege(
    'authenticated', 'public.user_study_rooms', 'SELECT'
  ) then
    raise exception '인증 사용자의 학습방 조회 권한이 없습니다.';
  end if;

  if has_table_privilege('anon', 'public.user_study_rooms', 'SELECT')
    or has_table_privilege('anon', 'public.user_study_rooms', 'INSERT')
    or has_table_privilege('anon', 'public.user_study_rooms', 'UPDATE')
    or has_table_privilege('anon', 'public.user_study_rooms', 'DELETE')
    or has_table_privilege('authenticated', 'public.user_study_rooms', 'INSERT')
    or has_table_privilege('authenticated', 'public.user_study_rooms', 'UPDATE')
    or has_table_privilege('authenticated', 'public.user_study_rooms', 'DELETE')
  then
    raise exception '학습방 테이블에 허용하지 않은 직접 쓰기 권한이 있습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename = 'user_study_rooms'
      and policyname = 'user_study_rooms_select_own'
      and cmd = 'SELECT'
      and 'authenticated' = any(roles)
      and position('auth.uid' in coalesce(qual, '')) > 0
  ) then
    raise exception '본인 학습방 조회 정책이 없습니다.';
  end if;

  foreach required_constraint in array array[
    'user_study_rooms_profile_fk',
    'user_study_rooms_background_fk',
    'user_study_rooms_floor_fk',
    'user_study_rooms_desk_fk',
    'user_study_rooms_chair_fk',
    'user_study_rooms_decor_left_fk',
    'user_study_rooms_decor_right_fk',
    'user_study_rooms_accent_fk',
    'user_study_rooms_decor_distinct'
  ]
  loop
    if not exists (
      select 1
      from pg_catalog.pg_constraint
      where conname = required_constraint
        and connamespace = 'public'::regnamespace
    ) then
      raise exception '필수 학습방 제약조건이 없습니다: %', required_constraint;
    end if;
  end loop;

  if to_regclass('public.user_study_rooms_updated_idx') is null then
    raise exception '학습방 최근 저장 조회 인덱스가 없습니다.';
  end if;

  room_function := coalesce(
    pg_catalog.to_regprocedure(
      'public.save_user_study_room(text,text,text,text,text,text,text,jsonb)'
    ),
    pg_catalog.to_regprocedure(
      'public.save_user_study_room(text,text,text,text,text,text,text)'
    )
  );
  if room_function is null then
    raise exception '학습방 저장 RPC가 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    where procedure.oid = room_function
      and procedure.prosecdef
      and coalesce(procedure.proconfig::text, '') like '%search_path=%'
  ) then
    raise exception '학습방 저장 RPC의 보안 설정이 올바르지 않습니다.';
  end if;

  if not has_function_privilege(
    'authenticated', room_function, 'EXECUTE'
  ) or has_function_privilege('anon', room_function, 'EXECUTE')
  then
    raise exception '학습방 저장 RPC 실행 권한이 올바르지 않습니다.';
  end if;

  select pg_catalog.pg_get_functiondef(room_function)
  into room_definition;

  if position('auth.uid()' in room_definition) = 0
     or position('public.user_inventory' in room_definition) = 0
     or position('item.allowed_slots' in room_definition) = 0
     or position('on conflict (user_id)' in lower(room_definition)) = 0
  then
    raise exception '학습방 저장 RPC의 소유권·슬롯·upsert 검증이 부족합니다.';
  end if;
end;
$$;

select 'study room validation: success' as validation_result;
rollback;
