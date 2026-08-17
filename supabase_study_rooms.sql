-- 사용자별 고정 슬롯 학습방과 소유권 검증 저장 RPC입니다.
-- supabase_shop_inventory.sql 적용 후 한 번 실행합니다.
begin;

create table public.user_study_rooms (
  user_id uuid primary key,
  background_item_key text,
  floor_item_key text,
  desk_item_key text,
  chair_item_key text,
  decor_left_item_key text,
  decor_right_item_key text,
  accent_item_key text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_study_rooms_profile_fk
    foreign key (user_id)
    references public.profiles(id) on delete cascade,
  constraint user_study_rooms_background_fk
    foreign key (background_item_key)
    references public.shop_items(item_key) on delete restrict,
  constraint user_study_rooms_floor_fk
    foreign key (floor_item_key)
    references public.shop_items(item_key) on delete restrict,
  constraint user_study_rooms_desk_fk
    foreign key (desk_item_key)
    references public.shop_items(item_key) on delete restrict,
  constraint user_study_rooms_chair_fk
    foreign key (chair_item_key)
    references public.shop_items(item_key) on delete restrict,
  constraint user_study_rooms_decor_left_fk
    foreign key (decor_left_item_key)
    references public.shop_items(item_key) on delete restrict,
  constraint user_study_rooms_decor_right_fk
    foreign key (decor_right_item_key)
    references public.shop_items(item_key) on delete restrict,
  constraint user_study_rooms_accent_fk
    foreign key (accent_item_key)
    references public.shop_items(item_key) on delete restrict,
  constraint user_study_rooms_decor_distinct
    check (
      decor_left_item_key is null
      or decor_right_item_key is null
      or decor_left_item_key <> decor_right_item_key
    )
);

create index user_study_rooms_updated_idx
on public.user_study_rooms(user_id, updated_at desc);

create trigger user_study_rooms_set_updated_at
before update on public.user_study_rooms
for each row execute function public.set_updated_at();

alter table public.user_study_rooms enable row level security;

create policy "user_study_rooms_select_own"
on public.user_study_rooms
for select
to authenticated
using ((select auth.uid()) = user_id);

revoke all on public.user_study_rooms from anon, authenticated;
grant select on public.user_study_rooms to authenticated;

create or replace function public.save_user_study_room(
  p_background_item_key text default null,
  p_floor_item_key text default null,
  p_desk_item_key text default null,
  p_chair_item_key text default null,
  p_decor_left_item_key text default null,
  p_decor_right_item_key text default null,
  p_accent_item_key text default null
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
  v_index integer;
  v_room public.user_study_rooms%rowtype;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
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
    accent_item_key
  )
  values (
    v_user_id,
    v_item_keys[1],
    v_item_keys[2],
    v_item_keys[3],
    v_item_keys[4],
    v_item_keys[5],
    v_item_keys[6],
    v_item_keys[7]
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
    'created_at', v_room.created_at,
    'updated_at', v_room.updated_at
  );
end;
$$;

revoke all on function public.save_user_study_room(
  text, text, text, text, text, text, text
) from public, anon;

grant execute on function public.save_user_study_room(
  text, text, text, text, text, text, text
) to authenticated;

commit;
