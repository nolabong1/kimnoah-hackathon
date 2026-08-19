-- 기존 상점 데이터를 보존하는 인증 사용자별 상점 테스트 세션입니다.
-- 코인·상점·학습방·직접 편집 마이그레이션 적용 후 SQL Editor에서 실행합니다.
begin;

alter table public.coin_transactions
drop constraint if exists coin_transactions_transaction_type_check;

alter table public.coin_transactions
drop constraint if exists coin_transactions_amount_direction;

alter table public.coin_transactions
add constraint coin_transactions_transaction_type_check
check (
  transaction_type in (
    'onboarding',
    'task_completion',
    'daily_completion',
    'daily_challenge',
    'weekly_challenge',
    'purchase',
    'test_reset_reversal',
    'shop_test_credit',
    'shop_test_purchase_refund'
  )
);

alter table public.coin_transactions
add constraint coin_transactions_amount_direction
check (
  (
    transaction_type in (
      'onboarding',
      'task_completion',
      'daily_completion',
      'daily_challenge',
      'weekly_challenge',
      'shop_test_credit',
      'shop_test_purchase_refund'
    )
    and amount > 0
  )
  or (
    transaction_type in ('purchase', 'test_reset_reversal')
    and amount < 0
  )
);

create table public.shop_test_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  status text not null default 'active',
  credit_amount integer not null default 1200,
  credit_transaction_id uuid not null,
  inventory_snapshot jsonb not null default '[]'::jsonb,
  room_snapshot jsonb,
  refunded_purchase_count integer not null default 0,
  refunded_coin_amount integer not null default 0,
  removed_inventory_count integer not null default 0,
  balance_after_reset integer,
  started_at timestamptz not null default now(),
  reset_at timestamptz,
  constraint shop_test_sessions_profile_fk
    foreign key (user_id)
    references public.profiles(id) on delete cascade,
  constraint shop_test_sessions_credit_owner_fk
    foreign key (credit_transaction_id, user_id)
    references public.coin_transactions(id, user_id) on delete restrict,
  constraint shop_test_sessions_status_check
    check (status in ('active', 'reset')),
  constraint shop_test_sessions_credit_positive
    check (credit_amount > 0),
  constraint shop_test_sessions_counts_nonnegative
    check (
      refunded_purchase_count >= 0
      and refunded_coin_amount >= 0
      and removed_inventory_count >= 0
    ),
  constraint shop_test_sessions_snapshot_array
    check (jsonb_typeof(inventory_snapshot) = 'array'),
  constraint shop_test_sessions_reset_state_check
    check (
      (
        status = 'active'
        and reset_at is null
        and balance_after_reset is null
      )
      or (
        status = 'reset'
        and reset_at is not null
        and balance_after_reset is not null
      )
    )
);

create unique index shop_test_sessions_one_active_user_idx
on public.shop_test_sessions(user_id)
where status = 'active';

create index shop_test_sessions_user_started_idx
on public.shop_test_sessions(user_id, started_at desc);

alter table public.shop_test_sessions enable row level security;

create policy "shop_test_sessions_select_own"
on public.shop_test_sessions
for select
to authenticated
using ((select auth.uid()) = user_id);

revoke all on public.shop_test_sessions from anon, authenticated;
grant select on public.shop_test_sessions to authenticated;

create or replace function public.start_shop_test_session()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_credit_amount constant integer := 1200;
  v_session_id uuid := gen_random_uuid();
  v_credit_transaction_id uuid := gen_random_uuid();
  v_wallet public.user_coin_wallets%rowtype;
  v_session public.shop_test_sessions%rowtype;
  v_inventory_snapshot jsonb;
  v_room_snapshot jsonb;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  select wallet.*
  into v_wallet
  from public.user_coin_wallets as wallet
  where wallet.user_id = v_user_id
  for update;

  if not found then
    raise exception '코인 지갑을 찾을 수 없습니다.';
  end if;

  select session.*
  into v_session
  from public.shop_test_sessions as session
  where session.user_id = v_user_id
    and session.status = 'active';

  if found then
    return pg_catalog.jsonb_build_object(
      'session_id', v_session.id,
      'credit_amount', v_session.credit_amount,
      'balance', v_wallet.balance,
      'already_active', true,
      'started_at', v_session.started_at
    );
  end if;

  select coalesce(
    pg_catalog.jsonb_agg(inventory.item_key order by inventory.item_key),
    '[]'::jsonb
  )
  into v_inventory_snapshot
  from public.user_inventory as inventory
  where inventory.user_id = v_user_id;

  select pg_catalog.jsonb_build_object(
    'background_item_key', room.background_item_key,
    'floor_item_key', room.floor_item_key,
    'desk_item_key', room.desk_item_key,
    'chair_item_key', room.chair_item_key,
    'decor_left_item_key', room.decor_left_item_key,
    'decor_right_item_key', room.decor_right_item_key,
    'accent_item_key', room.accent_item_key,
    'item_transforms', room.item_transforms
  )
  into v_room_snapshot
  from public.user_study_rooms as room
  where room.user_id = v_user_id;

  insert into public.coin_transactions (
    id,
    user_id,
    transaction_type,
    amount,
    balance_after,
    source_key,
    related_entity_id,
    metadata
  )
  values (
    v_credit_transaction_id,
    v_user_id,
    'shop_test_credit',
    v_credit_amount,
    v_wallet.balance + v_credit_amount,
    'shop_test:' || v_session_id::text || ':credit',
    v_session_id,
    pg_catalog.jsonb_build_object(
      'shop_test_session_id', v_session_id,
      'purpose', 'shop_test_credit'
    )
  );

  update public.user_coin_wallets
  set
    balance = balance + v_credit_amount,
    lifetime_earned = lifetime_earned + v_credit_amount,
    updated_at = now()
  where user_id = v_user_id
  returning * into v_wallet;

  insert into public.shop_test_sessions (
    id,
    user_id,
    credit_amount,
    credit_transaction_id,
    inventory_snapshot,
    room_snapshot
  )
  values (
    v_session_id,
    v_user_id,
    v_credit_amount,
    v_credit_transaction_id,
    v_inventory_snapshot,
    v_room_snapshot
  )
  returning * into v_session;

  return pg_catalog.jsonb_build_object(
    'session_id', v_session.id,
    'credit_amount', v_session.credit_amount,
    'balance', v_wallet.balance,
    'already_active', false,
    'started_at', v_session.started_at
  );
end;
$$;

revoke all on function public.start_shop_test_session()
from public, anon;

grant execute on function public.start_shop_test_session()
to authenticated;

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
  v_test_session_id uuid;
  v_purchase_source_key text;
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

  select session.id
  into v_test_session_id
  from public.shop_test_sessions as session
  where session.user_id = v_user_id
    and session.status = 'active';

  v_purchase_source_key := case
    when v_test_session_id is null
      then 'purchase:' || v_item.item_key
    else
      'shop_test:' || v_test_session_id::text
      || ':purchase:' || v_item.item_key
  end;

  insert into public.coin_transactions (
    user_id,
    transaction_type,
    amount,
    balance_after,
    source_key,
    related_entity_id,
    metadata
  )
  values (
    v_user_id,
    'purchase',
    -v_item.price,
    v_wallet.balance - v_item.price,
    v_purchase_source_key,
    v_test_session_id,
    pg_catalog.jsonb_strip_nulls(
      pg_catalog.jsonb_build_object(
        'item_key', v_item.item_key,
        'price', v_item.price,
        'name_ko', v_item.name_ko,
        'shop_test_session_id', v_test_session_id
      )
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

create or replace function public.reset_shop_test_session(
  p_session_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_session public.shop_test_sessions%rowtype;
  v_wallet public.user_coin_wallets%rowtype;
  v_purchase_count integer := 0;
  v_refund_amount integer := 0;
  v_removed_inventory_count integer := 0;
  v_reset_at timestamptz := now();
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  if p_session_id is null then
    raise exception '초기화할 상점 테스트 세션이 필요합니다.';
  end if;

  select session.*
  into v_session
  from public.shop_test_sessions as session
  where session.id = p_session_id
    and session.user_id = v_user_id
  for update;

  if not found then
    raise exception '본인의 상점 테스트 세션을 찾을 수 없습니다.';
  end if;

  if v_session.status = 'reset' then
    return pg_catalog.jsonb_build_object(
      'session_id', v_session.id,
      'refunded_purchase_count', v_session.refunded_purchase_count,
      'refunded_coin_amount', v_session.refunded_coin_amount,
      'removed_inventory_count', v_session.removed_inventory_count,
      'balance', v_session.balance_after_reset,
      'already_reset', true,
      'reset_at', v_session.reset_at
    );
  end if;

  select wallet.*
  into v_wallet
  from public.user_coin_wallets as wallet
  where wallet.user_id = v_user_id
  for update;

  if not found then
    raise exception '코인 지갑을 찾을 수 없습니다.';
  end if;

  select
    count(*)::integer,
    coalesce(sum(-purchase.amount), 0)::integer
  into v_purchase_count, v_refund_amount
  from public.coin_transactions as purchase
  where purchase.user_id = v_user_id
    and purchase.transaction_type = 'purchase'
    and purchase.related_entity_id = v_session.id
    and purchase.source_key like
      'shop_test:' || v_session.id::text || ':purchase:%';

  if v_session.room_snapshot is null then
    delete from public.user_study_rooms
    where user_id = v_user_id;
  else
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
      v_session.room_snapshot ->> 'background_item_key',
      v_session.room_snapshot ->> 'floor_item_key',
      v_session.room_snapshot ->> 'desk_item_key',
      v_session.room_snapshot ->> 'chair_item_key',
      v_session.room_snapshot ->> 'decor_left_item_key',
      v_session.room_snapshot ->> 'decor_right_item_key',
      v_session.room_snapshot ->> 'accent_item_key',
      coalesce(
        v_session.room_snapshot -> 'item_transforms',
        '{}'::jsonb
      )
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
      updated_at = v_reset_at;
  end if;

  delete from public.user_inventory as inventory
  using public.coin_transactions as purchase
  where inventory.user_id = v_user_id
    and purchase.id = inventory.purchase_transaction_id
    and purchase.user_id = inventory.user_id
    and purchase.transaction_type = 'purchase'
    and purchase.related_entity_id = v_session.id
    and purchase.source_key like
      'shop_test:' || v_session.id::text || ':purchase:%';

  get diagnostics v_removed_inventory_count = row_count;

  if v_removed_inventory_count <> v_purchase_count then
    raise exception '테스트 구매와 제거할 인벤토리 수가 일치하지 않습니다.';
  end if;

  if v_refund_amount > 0 then
    insert into public.coin_transactions (
      user_id,
      transaction_type,
      amount,
      balance_after,
      source_key,
      related_entity_id,
      metadata
    )
    values (
      v_user_id,
      'shop_test_purchase_refund',
      v_refund_amount,
      v_wallet.balance + v_refund_amount,
      'shop_test:' || v_session.id::text || ':purchase_refund',
      v_session.id,
      pg_catalog.jsonb_build_object(
        'shop_test_session_id', v_session.id,
        'refunded_purchase_count', v_purchase_count
      )
    );

    update public.user_coin_wallets
    set
      balance = balance + v_refund_amount,
      lifetime_spent = lifetime_spent - v_refund_amount,
      updated_at = v_reset_at
    where user_id = v_user_id
    returning * into v_wallet;
  end if;

  if v_wallet.balance < v_session.credit_amount then
    raise exception '테스트 코인을 안전하게 회수할 수 없습니다.';
  end if;

  insert into public.coin_transactions (
    user_id,
    transaction_type,
    amount,
    balance_after,
    source_key,
    related_entity_id,
    metadata
  )
  values (
    v_user_id,
    'test_reset_reversal',
    -v_session.credit_amount,
    v_wallet.balance - v_session.credit_amount,
    'shop_test:' || v_session.id::text || ':credit_reversal',
    v_session.credit_transaction_id,
    pg_catalog.jsonb_build_object(
      'shop_test_session_id', v_session.id,
      'reversed_coin_transaction_id', v_session.credit_transaction_id
    )
  );

  update public.user_coin_wallets
  set
    balance = balance - v_session.credit_amount,
    lifetime_earned = lifetime_earned - v_session.credit_amount,
    updated_at = v_reset_at
  where user_id = v_user_id
  returning * into v_wallet;

  update public.shop_test_sessions
  set
    status = 'reset',
    refunded_purchase_count = v_purchase_count,
    refunded_coin_amount = v_refund_amount,
    removed_inventory_count = v_removed_inventory_count,
    balance_after_reset = v_wallet.balance,
    reset_at = v_reset_at
  where id = v_session.id
    and user_id = v_user_id
  returning * into v_session;

  return pg_catalog.jsonb_build_object(
    'session_id', v_session.id,
    'refunded_purchase_count', v_session.refunded_purchase_count,
    'refunded_coin_amount', v_session.refunded_coin_amount,
    'removed_inventory_count', v_session.removed_inventory_count,
    'balance', v_session.balance_after_reset,
    'already_reset', false,
    'reset_at', v_session.reset_at
  );
end;
$$;

revoke all on function public.reset_shop_test_session(uuid)
from public, anon;

grant execute on function public.reset_shop_test_session(uuid)
to authenticated;

commit;
