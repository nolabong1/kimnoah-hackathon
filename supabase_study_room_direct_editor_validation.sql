-- 직접 조작 학습방 마이그레이션 적용 후 실행하는 읽기 전용 검증입니다.
begin;
set transaction read only;

do $$
declare
  room_function regprocedure;
  room_definition text;
begin
  if not exists (
    select 1
    from pg_catalog.pg_attribute
    where attrelid = 'public.user_study_rooms'::regclass
      and attname = 'item_transforms'
      and not attisdropped
  ) then
    raise exception '학습방 가구 배치 열이 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_constraint
    where conname = 'user_study_rooms_item_transforms_check'
      and connamespace = 'public'::regnamespace
  ) then
    raise exception '학습방 가구 배치 검증 제약조건이 없습니다.';
  end if;

  if public.is_valid_study_room_transforms(
    '{
      "desk": {
        "x": -120,
        "y": 30,
        "scale": 85,
        "rotation": 12,
        "flip_horizontal": true
      }
    }'::jsonb
  ) is not true then
    raise exception '정상 학습방 가구 배치값이 거부됐습니다.';
  end if;

  if public.is_valid_study_room_transforms(
    '{"desk": {"scale": 1000}}'::jsonb
  ) is not false
     or public.is_valid_study_room_transforms(
       '{"background": {"x": 10}}'::jsonb
     ) is not false
  then
    raise exception '허용 범위를 벗어난 학습방 가구 배치값이 승인됐습니다.';
  end if;

  room_function := pg_catalog.to_regprocedure(
    'public.save_user_study_room(text,text,text,text,text,text,text,jsonb)'
  );
  if room_function is null then
    raise exception '직접 배치를 저장하는 학습방 RPC가 없습니다.';
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
     or position('is_valid_study_room_transforms' in room_definition) = 0
     or position('item_transforms = excluded.item_transforms' in room_definition) = 0
  then
    raise exception '학습방 저장 RPC의 소유권·배치 검증이 부족합니다.';
  end if;

  if pg_catalog.to_regclass('public.shop_test_sessions') is not null
     and (
       not exists (
         select 1
         from pg_catalog.pg_trigger
         where tgrelid = 'public.shop_test_sessions'::regclass
           and tgname = 'shop_test_sessions_capture_room_transforms'
           and tgenabled <> 'D'
           and not tgisinternal
       )
       or not exists (
         select 1
         from pg_catalog.pg_trigger
         where tgrelid = 'public.shop_test_sessions'::regclass
           and tgname = 'shop_test_sessions_restore_room_transforms'
           and tgenabled <> 'D'
           and not tgisinternal
       )
     )
  then
    raise exception '상점 테스트 세션의 학습방 배치 복원 트리거가 없습니다.';
  end if;
end;
$$;

select 'study room direct editor validation: success' as validation_result;
rollback;
