-- 기존 EXP 원장을 신뢰 기준으로 사용해 학습 행동 코인을 원자적으로 지급합니다.
-- supabase_coin_economy_schema.sql 적용 후 한 번 실행합니다.
begin;

create or replace function public.award_coins_for_exp_event()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_auth_user_id uuid := auth.uid();
  v_event_date date := (
    new.created_at at time zone 'Asia/Seoul'
  )::date;
  v_transaction_type text;
  v_coin_amount integer := 0;
  v_task_coins_awarded_today integer := 0;
  v_inserted_amount integer := 0;
  v_wallet public.user_coin_wallets%rowtype;
begin
  if v_auth_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  if new.user_id <> v_auth_user_id then
    raise exception '본인의 학습 보상만 처리할 수 있습니다.';
  end if;

  case new.event_type
    when 'task_completion' then
      v_transaction_type := 'task_completion';
      v_coin_amount := 5;
    when 'daily_completion' then
      v_transaction_type := 'daily_completion';
      v_coin_amount := 10;
    when 'daily_challenge' then
      v_transaction_type := 'daily_challenge';
      v_coin_amount := 10;
    when 'weekly_challenge' then
      v_transaction_type := 'weekly_challenge';
      v_coin_amount := 30;
    else
      return new;
  end case;

  select wallet.*
  into v_wallet
  from public.user_coin_wallets as wallet
  where wallet.user_id = new.user_id
  for update;

  if not found then
    raise exception '코인 지갑을 찾을 수 없습니다.';
  end if;

  if new.event_type = 'task_completion' then
    select coalesce(sum(transaction.amount), 0)::integer
    into v_task_coins_awarded_today
    from public.coin_transactions as transaction
    where transaction.user_id = new.user_id
      and transaction.transaction_type = 'task_completion'
      and (
        transaction.created_at at time zone 'Asia/Seoul'
      )::date = v_event_date;

    if v_task_coins_awarded_today >= 25 then
      return new;
    end if;

    v_coin_amount := least(
      v_coin_amount,
      25 - v_task_coins_awarded_today
    );
  end if;

  insert into public.coin_transactions (
    user_id,
    transaction_type,
    amount,
    balance_after,
    source_key,
    related_entity_id,
    metadata,
    created_at
  )
  values (
    new.user_id,
    v_transaction_type,
    v_coin_amount,
    v_wallet.balance + v_coin_amount,
    new.source_key,
    new.id,
    pg_catalog.jsonb_build_object(
      'exp_event_id', new.id,
      'exp_event_type', new.event_type,
      'exp_amount', new.amount
    ),
    new.created_at
  )
  on conflict (user_id, source_key) do nothing
  returning amount into v_inserted_amount;

  v_inserted_amount := coalesce(v_inserted_amount, 0);

  if v_inserted_amount = 0 then
    if not exists (
      select 1
      from public.coin_transactions as transaction
      where transaction.user_id = new.user_id
        and transaction.source_key = new.source_key
        and transaction.transaction_type = v_transaction_type
        and transaction.amount = v_coin_amount
    ) then
      raise exception '기존 코인 원장이 학습 보상과 일치하지 않습니다.';
    end if;

    return new;
  end if;

  update public.user_coin_wallets
  set
    balance = balance + v_inserted_amount,
    lifetime_earned = lifetime_earned + v_inserted_amount,
    updated_at = now()
  where user_id = new.user_id;

  return new;
end;
$$;

drop trigger if exists exp_events_award_coins
on public.exp_events;

create trigger exp_events_award_coins
after insert on public.exp_events
for each row execute function public.award_coins_for_exp_event();

revoke all on function public.award_coins_for_exp_event()
from public, anon, authenticated;

commit;
