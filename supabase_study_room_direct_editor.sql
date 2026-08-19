-- 기존 학습방에 직접 조작한 가구 위치·크기·회전·반전값을 추가합니다.
-- supabase_study_rooms.sql 적용 후 Supabase SQL Editor에서 한 번 실행합니다.
begin;

create or replace function public.is_valid_study_room_transforms(
  p_transforms jsonb
)
returns boolean
language plpgsql
immutable
set search_path = ''
as $$
declare
  v_slot record;
  v_property text;
  v_number integer;
begin
  if p_transforms is null or pg_catalog.jsonb_typeof(p_transforms) <> 'object' then
    return false;
  end if;

  for v_slot in
    select entry.key, entry.value
    from pg_catalog.jsonb_each(p_transforms) as entry
  loop
    if v_slot.key <> all(array[
      'desk',
      'chair',
      'decor_left',
      'decor_right',
      'accent'
    ]) then
      return false;
    end if;

    if pg_catalog.jsonb_typeof(v_slot.value) <> 'object' then
      return false;
    end if;

    if exists (
      select 1
      from pg_catalog.jsonb_object_keys(v_slot.value) as property(key)
      where property.key <> all(array[
        'x',
        'y',
        'scale',
        'rotation',
        'flip_horizontal'
      ])
    ) then
      return false;
    end if;

    foreach v_property in array array['x', 'y', 'scale', 'rotation']
    loop
      if v_slot.value ? v_property then
        if pg_catalog.jsonb_typeof(v_slot.value -> v_property) <> 'number'
           or v_slot.value ->> v_property !~ '^-?[0-9]+$'
        then
          return false;
        end if;
        v_number := (v_slot.value ->> v_property)::integer;
        if (v_property = 'x' and (v_number < -800 or v_number > 800))
           or (v_property = 'y' and (v_number < -450 or v_number > 450))
           or (v_property = 'scale' and (v_number < 25 or v_number > 200))
           or (v_property = 'rotation' and (v_number < -180 or v_number > 180))
        then
          return false;
        end if;
      end if;
    end loop;

    if v_slot.value ? 'flip_horizontal'
       and pg_catalog.jsonb_typeof(
         v_slot.value -> 'flip_horizontal'
       ) <> 'boolean'
    then
      return false;
    end if;
  end loop;

  return true;
exception
  when others then
    return false;
end;
$$;

revoke all on function public.is_valid_study_room_transforms(jsonb)
from public, anon, authenticated;

alter table public.user_study_rooms
add column if not exists item_transforms jsonb not null default '{}'::jsonb;

alter table public.user_study_rooms
drop constraint if exists user_study_rooms_item_transforms_check;

alter table public.user_study_rooms
add constraint user_study_rooms_item_transforms_check
check (public.is_valid_study_room_transforms(item_transforms));

drop function if exists public.save_user_study_room(
  text, text, text, text, text, text, text
);

create or replace function public.save_user_study_room(
  p_background_item_key text default null,
  p_floor_item_key text default null,
  p_desk_item_key text default null,
  p_chair_item_key text default null,
  p_decor_left_item_key text default null,
  p_decor_right_item_key text default null,
  p_accent_item_key text default null,
  p_item_transforms jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_slot_names constant text[] := array[
    'background',
    'floor',
    'desk',
    'chair',
    'decor_left',
    'decor_right',
    'accent'
  ];
  v_item_keys text[] := array[
    nullif(btrim(p_background_item_key), ''),
    nullif(btrim(p_floor_item_key), ''),
    nullif(btrim(p_desk_item_key), ''),
    nullif(btrim(p_chair_item_key), ''),
    nullif(btrim(p_decor_left_item_key), ''),
    nullif(btrim(p_decor_right_item_key), ''),
    nullif(btrim(p_accent_item_key), '')
  ];
  v_item_transforms jsonb := coalesce(p_item_transforms, '{}'::jsonb);
  v_index integer;
  v_room public.user_study_rooms%rowtype;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  if not public.is_valid_study_room_transforms(v_item_transforms) then
    raise exception '학습방 가구 배치 정보가 올바르지 않습니다.';
  end if;

  if v_item_keys[5] is not null
     and v_item_keys[5] = v_item_keys[6]
  then
    raise exception '같은 소품을 좌우 슬롯에 동시에 장착할 수 없습니다.';
  end if;

  for v_index in 1..pg_catalog.array_length(v_item_keys, 1)
  loop
    if v_item_keys[v_index] is null then
      continue;
    end if;

    if v_item_keys[v_index] !~ '^[a-z0-9_]{1,100}$' then
      raise exception '학습방 아이템 키가 올바르지 않습니다.';
    end if;

    if not exists (
      select 1
      from public.shop_items as item
      join public.user_inventory as inventory
        on inventory.item_key = item.item_key
       and inventory.user_id = v_user_id
      where item.item_key = v_item_keys[v_index]
        and item.is_active
        and v_slot_names[v_index] = any(item.allowed_slots)
    ) then
      raise exception '보유하지 않았거나 슬롯에 맞지 않는 아이템입니다: %',
        v_item_keys[v_index];
    end if;
  end loop;

  insert into public.user_study_rooms (
    user_id,
    background_item_key,
    floor_item_key,
    desk_item_key,
    chair_item_key,
    decor_left_item_key,
    decor_right_item_key,
    accent_item_key,
    item_transforms
  )
  values (
    v_user_id,
    v_item_keys[1],
    v_item_keys[2],
    v_item_keys[3],
    v_item_keys[4],
    v_item_keys[5],
    v_item_keys[6],
    v_item_keys[7],
    v_item_transforms
  )
  on conflict (user_id) do update
  set
    background_item_key = excluded.background_item_key,
    floor_item_key = excluded.floor_item_key,
    desk_item_key = excluded.desk_item_key,
    chair_item_key = excluded.chair_item_key,
    decor_left_item_key = excluded.decor_left_item_key,
    decor_right_item_key = excluded.decor_right_item_key,
    accent_item_key = excluded.accent_item_key,
    item_transforms = excluded.item_transforms,
    updated_at = now()
  returning * into v_room;

  return pg_catalog.jsonb_build_object(
    'user_id', v_room.user_id,
    'background_item_key', v_room.background_item_key,
    'floor_item_key', v_room.floor_item_key,
    'desk_item_key', v_room.desk_item_key,
    'chair_item_key', v_room.chair_item_key,
    'decor_left_item_key', v_room.decor_left_item_key,
    'decor_right_item_key', v_room.decor_right_item_key,
    'accent_item_key', v_room.accent_item_key,
    'item_transforms', v_room.item_transforms,
    'created_at', v_room.created_at,
    'updated_at', v_room.updated_at
  );
end;
$$;

revoke all on function public.save_user_study_room(
  text, text, text, text, text, text, text, jsonb
) from public, anon;

grant execute on function public.save_user_study_room(
  text, text, text, text, text, text, text, jsonb
) to authenticated;

create or replace function public.capture_shop_test_room_transforms()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  v_item_transforms jsonb;
begin
  if new.room_snapshot is null then
    return new;
  end if;
  select room.item_transforms
  into v_item_transforms
  from public.user_study_rooms as room
  where room.user_id = new.user_id;

  new.room_snapshot := new.room_snapshot || pg_catalog.jsonb_build_object(
    'item_transforms', coalesce(v_item_transforms, '{}'::jsonb)
  );
  return new;
end;
$$;

create or replace function public.restore_shop_test_room_transforms()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if old.status = 'active'
     and new.status = 'reset'
     and old.room_snapshot is not null
  then
    update public.user_study_rooms
    set item_transforms = coalesce(
      old.room_snapshot -> 'item_transforms',
      '{}'::jsonb
    )
    where user_id = old.user_id;
  end if;
  return new;
end;
$$;

revoke all on function public.capture_shop_test_room_transforms()
from public, anon, authenticated;
revoke all on function public.restore_shop_test_room_transforms()
from public, anon, authenticated;

do $$
begin
  if pg_catalog.to_regclass('public.shop_test_sessions') is not null then
    execute 'drop trigger if exists shop_test_sessions_capture_room_transforms on public.shop_test_sessions';
    execute 'create trigger shop_test_sessions_capture_room_transforms before insert on public.shop_test_sessions for each row execute function public.capture_shop_test_room_transforms()';

    execute 'drop trigger if exists shop_test_sessions_restore_room_transforms on public.shop_test_sessions';
    execute 'create trigger shop_test_sessions_restore_room_transforms after update of status on public.shop_test_sessions for each row execute function public.restore_shop_test_room_transforms()';
  end if;
end;
$$;

commit;
