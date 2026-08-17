-- 코인 지갑과 멱등 거래 원장 저장 구조
-- 원격 Supabase SQL Editor에서 수동 실행해야 합니다.
begin;

create table public.user_coin_wallets (
  user_id uuid primary key,
  balance integer not null default 0,
  lifetime_earned integer not null default 0
    constraint user_coin_wallets_lifetime_earned_nonnegative
    check (lifetime_earned >= 0),
  lifetime_spent integer not null default 0
    constraint user_coin_wallets_lifetime_spent_nonnegative
    check (lifetime_spent >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_coin_wallets_profile_fk
    foreign key (user_id) references public.profiles(id) on delete cascade,
  constraint user_coin_wallets_balance_nonnegative
    check (balance >= 0),
  constraint user_coin_wallets_totals_match
    check (balance = lifetime_earned - lifetime_spent)
);

create table public.coin_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  transaction_type text not null
    check (
      transaction_type in (
        'onboarding',
        'task_completion',
        'daily_completion',
        'daily_challenge',
        'weekly_challenge',
        'purchase',
        'test_reset_reversal'
      )
    ),
  amount integer not null check (amount <> 0),
  balance_after integer not null check (balance_after >= 0),
  source_key text not null
    check (char_length(btrim(source_key)) between 1 and 200),
  related_entity_id uuid,
  metadata jsonb not null default '{}'::jsonb
    check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  constraint coin_transactions_wallet_fk
    foreign key (user_id)
    references public.user_coin_wallets(user_id) on delete cascade,
  constraint coin_transactions_user_source_unique
    unique (user_id, source_key),
  constraint coin_transactions_amount_direction
    check (
      (
        transaction_type in (
          'onboarding',
          'task_completion',
          'daily_completion',
          'daily_challenge',
          'weekly_challenge'
        )
        and amount > 0
      )
      or (
        transaction_type in ('purchase', 'test_reset_reversal')
        and amount < 0
      )
    )
);

create index coin_transactions_user_created_idx
on public.coin_transactions(user_id, created_at desc);

create index coin_transactions_user_type_created_idx
on public.coin_transactions(user_id, transaction_type, created_at desc);

create index coin_transactions_user_related_entity_idx
on public.coin_transactions(user_id, related_entity_id)
where related_entity_id is not null;

create trigger user_coin_wallets_set_updated_at
before update on public.user_coin_wallets
for each row execute function public.set_updated_at();

create or replace function public.initialize_coin_wallet_for_profile()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.user_coin_wallets (
    user_id,
    balance,
    lifetime_earned,
    lifetime_spent
  )
  values (new.id, 30, 30, 0)
  on conflict (user_id) do nothing;

  if found then
    insert into public.coin_transactions (
      user_id,
      transaction_type,
      amount,
      balance_after,
      source_key,
      metadata
    )
    values (
      new.id,
      'onboarding',
      30,
      30,
      'onboarding:shop_v1',
      pg_catalog.jsonb_build_object('reason', 'shop_v1_initial_grant')
    );
  end if;

  return new;
end;
$$;

create trigger on_profile_coin_wallet_created
after insert on public.profiles
for each row execute function public.initialize_coin_wallet_for_profile();

-- 마이그레이션 시점에 이미 존재하는 사용자도 신규 사용자와 같은
-- 시작 코인과 원장을 한 번만 받습니다.
with inserted_wallets as (
  insert into public.user_coin_wallets (
    user_id,
    balance,
    lifetime_earned,
    lifetime_spent
  )
  select profile.id, 30, 30, 0
  from public.profiles as profile
  on conflict (user_id) do nothing
  returning user_id
)
insert into public.coin_transactions (
  user_id,
  transaction_type,
  amount,
  balance_after,
  source_key,
  metadata
)
select
  wallet.user_id,
  'onboarding',
  30,
  30,
  'onboarding:shop_v1',
  pg_catalog.jsonb_build_object('reason', 'shop_v1_initial_grant')
from inserted_wallets as wallet;

alter table public.user_coin_wallets enable row level security;
alter table public.coin_transactions enable row level security;

create policy "user_coin_wallets_select_own"
on public.user_coin_wallets
for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "coin_transactions_select_own"
on public.coin_transactions
for select
to authenticated
using ((select auth.uid()) = user_id);

revoke all on public.user_coin_wallets from anon, authenticated;
revoke all on public.coin_transactions from anon, authenticated;

grant select on public.user_coin_wallets to authenticated;
grant select on public.coin_transactions to authenticated;

revoke all on function public.initialize_coin_wallet_for_profile()
from public, anon, authenticated;

commit;
