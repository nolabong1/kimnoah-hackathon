-- 승인된 상점 카탈로그, 사용자 인벤토리와 원자적 구매 RPC입니다.
-- 코인 경제와 테스트 초기화 SQL 적용 후 한 번 실행합니다.
begin;

alter table public.coin_transactions
add constraint coin_transactions_id_user_unique
unique (id, user_id);

create table public.shop_items (
  item_key text primary key,
  name_ko text not null,
  category text not null,
  allowed_slots text[] not null,
  rarity text not null,
  price integer not null,
  layer integer not null,
  overlay_path text not null,
  thumbnail_path text not null,
  sort_order integer not null unique,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint shop_items_key_format
    check (item_key ~ '^[a-z0-9_]{1,100}$'),
  constraint shop_items_name_length
    check (char_length(btrim(name_ko)) between 1 and 100),
  constraint shop_items_category_valid
    check (
      category in (
        'background', 'floor', 'desk', 'chair', 'decoration', 'accent'
      )
    ),
  constraint shop_items_rarity_valid
    check (rarity in ('common', 'uncommon', 'rare')),
  constraint shop_items_price_positive
    check (price > 0),
  constraint shop_items_paths_present
    check (
      char_length(btrim(overlay_path)) between 1 and 300
      and char_length(btrim(thumbnail_path)) between 1 and 300
    ),
  constraint shop_items_category_slot_layer_match
    check (
      (
        category = 'background'
        and allowed_slots = array['background']::text[]
        and layer = 0
      ) or (
        category = 'floor'
        and allowed_slots = array['floor']::text[]
        and layer = 10
      ) or (
        category = 'desk'
        and allowed_slots = array['desk']::text[]
        and layer = 30
      ) or (
        category = 'chair'
        and allowed_slots = array['chair']::text[]
        and layer = 40
      ) or (
        category = 'decoration'
        and allowed_slots = array['decor_left', 'decor_right']::text[]
        and layer = 50
      ) or (
        category = 'accent'
        and allowed_slots = array['accent']::text[]
        and layer = 60
      )
    )
);

create table public.user_inventory (
  user_id uuid not null,
  item_key text not null,
  purchase_transaction_id uuid not null,
  price_paid integer not null,
  acquired_at timestamptz not null default now(),
  primary key (user_id, item_key),
  constraint user_inventory_profile_fk
    foreign key (user_id)
    references public.profiles(id) on delete cascade,
  constraint user_inventory_shop_item_fk
    foreign key (item_key)
    references public.shop_items(item_key) on delete restrict,
  constraint user_inventory_purchase_owner_fk
    foreign key (purchase_transaction_id, user_id)
    references public.coin_transactions(id, user_id) on delete cascade,
  constraint user_inventory_purchase_transaction_unique
    unique (purchase_transaction_id),
  constraint user_inventory_price_paid_positive
    check (price_paid > 0)
);

create index shop_items_active_category_sort_idx
on public.shop_items(is_active, category, sort_order);

create index user_inventory_user_acquired_idx
on public.user_inventory(user_id, acquired_at desc);

create trigger shop_items_set_updated_at
before update on public.shop_items
for each row execute function public.set_updated_at();

insert into public.shop_items (
  item_key,
  name_ko,
  category,
  allowed_slots,
  rarity,
  price,
  layer,
  overlay_path,
  thumbnail_path,
  sort_order
)
values
  ('wall_morning_sky', '아침 하늘 벽지', 'background', array['background'],
   'common', 40, 0,
   'assets/study_room/items/backgrounds/wall_morning_sky.png',
   'assets/study_room/thumbnails/wall_morning_sky.webp', 10),
  ('wall_warm_cream', '따뜻한 크림 벽지', 'background', array['background'],
   'common', 40, 0,
   'assets/study_room/items/backgrounds/wall_warm_cream.png',
   'assets/study_room/thumbnails/wall_warm_cream.webp', 20),
  ('wall_night_focus', '밤의 집중 벽지', 'background', array['background'],
   'rare', 160, 0,
   'assets/study_room/items/backgrounds/wall_night_focus.png',
   'assets/study_room/thumbnails/wall_night_focus.webp', 30),
  ('floor_light_wood', '밝은 원목 바닥', 'floor', array['floor'],
   'common', 35, 10,
   'assets/study_room/items/floors/floor_light_wood.png',
   'assets/study_room/thumbnails/floor_light_wood.webp', 40),
  ('floor_soft_gray', '부드러운 회색 바닥', 'floor', array['floor'],
   'common', 35, 10,
   'assets/study_room/items/floors/floor_soft_gray.png',
   'assets/study_room/thumbnails/floor_soft_gray.webp', 50),
  ('floor_starry_rug', '별빛 러그 바닥', 'floor', array['floor'],
   'uncommon', 80, 10,
   'assets/study_room/items/floors/floor_starry_rug.png',
   'assets/study_room/thumbnails/floor_starry_rug.webp', 60),
  ('desk_oak_basic', '원목 학습 책상', 'desk', array['desk'],
   'common', 60, 30,
   'assets/study_room/items/desks/desk_oak_basic.png',
   'assets/study_room/thumbnails/desk_oak_basic.webp', 70),
  ('desk_white_clean', '화이트 학습 책상', 'desk', array['desk'],
   'uncommon', 85, 30,
   'assets/study_room/items/desks/desk_white_clean.png',
   'assets/study_room/thumbnails/desk_white_clean.webp', 80),
  ('desk_neon_coder', '네온 코딩 책상', 'desk', array['desk'],
   'rare', 170, 30,
   'assets/study_room/items/desks/desk_neon_coder.png',
   'assets/study_room/thumbnails/desk_neon_coder.webp', 90),
  ('chair_blue_basic', '블루 학습 의자', 'chair', array['chair'],
   'common', 50, 40,
   'assets/study_room/items/chairs/chair_blue_basic.png',
   'assets/study_room/thumbnails/chair_blue_basic.webp', 100),
  ('chair_ergonomic', '집중 인체공학 의자', 'chair', array['chair'],
   'uncommon', 100, 40,
   'assets/study_room/items/chairs/chair_ergonomic.png',
   'assets/study_room/thumbnails/chair_ergonomic.webp', 110),
  ('decor_green_plant', '작은 초록 식물', 'decoration',
   array['decor_left', 'decor_right'], 'common', 30, 50,
   'assets/study_room/items/decorations/decor_green_plant.png',
   'assets/study_room/thumbnails/decor_green_plant.webp', 120),
  ('decor_focus_lamp', '집중 스탠드', 'decoration',
   array['decor_left', 'decor_right'], 'common', 45, 50,
   'assets/study_room/items/decorations/decor_focus_lamp.png',
   'assets/study_room/thumbnails/decor_focus_lamp.webp', 130),
  ('decor_bookshelf', '미니 학습 책장', 'decoration',
   array['decor_left', 'decor_right'], 'uncommon', 90, 50,
   'assets/study_room/items/decorations/decor_bookshelf.png',
   'assets/study_room/thumbnails/decor_bookshelf.webp', 140),
  ('accent_study_cat', '공부하는 고양이', 'accent', array['accent'],
   'rare', 150, 60,
   'assets/study_room/items/accents/accent_study_cat.png',
   'assets/study_room/thumbnails/accent_study_cat.webp', 150);

alter table public.shop_items enable row level security;
alter table public.user_inventory enable row level security;

create policy "shop_items_select_authenticated"
on public.shop_items
for select
to authenticated
using (true);

create policy "user_inventory_select_own"
on public.user_inventory
for select
to authenticated
using ((select auth.uid()) = user_id);

revoke all on public.shop_items from anon, authenticated;
revoke all on public.user_inventory from anon, authenticated;

grant select on public.shop_items to authenticated;
grant select on public.user_inventory to authenticated;

create or replace function public.purchase_shop_item(
  p_item_key text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_normalized_item_key text := btrim(p_item_key);
  v_item public.shop_items%rowtype;
  v_wallet public.user_coin_wallets%rowtype;
  v_inventory public.user_inventory%rowtype;
  v_purchase_transaction_id uuid;
  v_acquired_at timestamptz := now();
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  if v_normalized_item_key is null
     or v_normalized_item_key !~ '^[a-z0-9_]{1,100}$'
  then
    raise exception '상점 아이템 키가 올바르지 않습니다.';
  end if;

  select item.*
  into v_item
  from public.shop_items as item
  where item.item_key = v_normalized_item_key
    and item.is_active;

  if not found then
    raise exception '구매할 수 있는 상점 아이템을 찾을 수 없습니다.';
  end if;

  select wallet.*
  into v_wallet
  from public.user_coin_wallets as wallet
  where wallet.user_id = v_user_id
  for update;

  if not found then
    raise exception '코인 지갑을 찾을 수 없습니다.';
  end if;

  select inventory.*
  into v_inventory
  from public.user_inventory as inventory
  where inventory.user_id = v_user_id
    and inventory.item_key = v_item.item_key;

  if found then
    return pg_catalog.jsonb_build_object(
      'item_key', v_item.item_key,
      'price', v_item.price,
      'coins_spent', 0,
      'balance', v_wallet.balance,
      'already_owned', true,
      'purchase_transaction_id', v_inventory.purchase_transaction_id,
      'acquired_at', v_inventory.acquired_at
    );
  end if;

  if v_wallet.balance < v_item.price then
    raise exception '코인이 부족합니다. 필요한 코인: %, 현재 코인: %',
      v_item.price,
      v_wallet.balance;
  end if;

  insert into public.coin_transactions (
    user_id,
    transaction_type,
    amount,
    balance_after,
    source_key,
    metadata
  )
  values (
    v_user_id,
    'purchase',
    -v_item.price,
    v_wallet.balance - v_item.price,
    'purchase:' || v_item.item_key,
    pg_catalog.jsonb_build_object(
      'item_key', v_item.item_key,
      'price', v_item.price,
      'name_ko', v_item.name_ko
    )
  )
  returning id into v_purchase_transaction_id;

  update public.user_coin_wallets
  set
    balance = balance - v_item.price,
    lifetime_spent = lifetime_spent + v_item.price,
    updated_at = v_acquired_at
  where user_id = v_user_id
  returning * into v_wallet;

  insert into public.user_inventory (
    user_id,
    item_key,
    purchase_transaction_id,
    price_paid,
    acquired_at
  )
  values (
    v_user_id,
    v_item.item_key,
    v_purchase_transaction_id,
    v_item.price,
    v_acquired_at
  )
  returning * into v_inventory;

  return pg_catalog.jsonb_build_object(
    'item_key', v_item.item_key,
    'price', v_item.price,
    'coins_spent', v_item.price,
    'balance', v_wallet.balance,
    'already_owned', false,
    'purchase_transaction_id', v_inventory.purchase_transaction_id,
    'acquired_at', v_inventory.acquired_at
  );
end;
$$;

revoke all on function public.purchase_shop_item(text)
from public, anon;

grant execute on function public.purchase_shop_item(text)
to authenticated;

commit;
