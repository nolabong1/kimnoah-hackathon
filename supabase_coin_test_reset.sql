-- 테스트 초기화 등으로 EXP 원장이 삭제될 때 대응 코인을 취소합니다.
-- 기존 코인 보상 행은 보존하고 별도의 음수 취소 행을 기록합니다.
begin;

alter function public.reset_today_test_progress()
rename to reset_today_test_progress_without_coin_reversal;

revoke all
on function public.reset_today_test_progress_without_coin_reversal()
from public, anon, authenticated;

create or replace function public.reset_today_test_progress()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_result jsonb;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  perform pg_catalog.set_config(
    'app.coin_test_reset',
    'on',
    true
  );

  v_result := public.reset_today_test_progress_without_coin_reversal();

  if not (v_result ? 'removed_mastery_event_count') then
    raise exception '적응형 학습 초기화 결과가 올바르지 않습니다.';
  end if;

  return v_result;
end;
$$;

revoke all on function public.reset_today_test_progress()
from public, anon;

grant execute on function public.reset_today_test_progress()
to authenticated;

create or replace function public.reverse_coins_for_deleted_exp_event()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_auth_user_id uuid := auth.uid();
  v_reward_transaction public.coin_transactions%rowtype;
  v_wallet public.user_coin_wallets%rowtype;
  v_reversal_source_key text;
  v_reversal_amount integer;
  v_inserted_amount integer := 0;
begin
  if coalesce(
    pg_catalog.current_setting('app.coin_test_reset', true) = 'on',
    false
  ) is false then
    return old;
  end if;

  if v_auth_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  if old.user_id <> v_auth_user_id then
    raise exception '본인의 학습 보상만 초기화할 수 있습니다.';
  end if;

  select transaction.*
  into v_reward_transaction
  from public.coin_transactions as transaction
  where transaction.user_id = old.user_id
    and transaction.source_key = old.source_key
    and transaction.transaction_type in (
      'task_completion',
      'daily_completion',
      'daily_challenge',
      'weekly_challenge'
    )
    and transaction.amount > 0;

  if not found then
    return old;
  end if;

  v_reversal_source_key :=
    'reversal:' || v_reward_transaction.id::text;
  v_reversal_amount := -v_reward_transaction.amount;

  select wallet.*
  into v_wallet
  from public.user_coin_wallets as wallet
  where wallet.user_id = old.user_id
  for update;

  if not found then
    raise exception '코인 지갑을 찾을 수 없습니다.';
  end if;

  if exists (
    select 1
    from public.coin_transactions as transaction
    where transaction.user_id = old.user_id
      and transaction.source_key = v_reversal_source_key
      and transaction.transaction_type = 'test_reset_reversal'
      and transaction.amount = v_reversal_amount
      and transaction.related_entity_id = v_reward_transaction.id
  ) then
    return old;
  end if;

  if v_wallet.balance < v_reward_transaction.amount then
    raise exception
      '지급된 코인이 이미 사용되어 오늘 기록을 안전하게 초기화할 수 없습니다.';
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
    old.user_id,
    'test_reset_reversal',
    v_reversal_amount,
    v_wallet.balance + v_reversal_amount,
    v_reversal_source_key,
    v_reward_transaction.id,
    pg_catalog.jsonb_build_object(
      'reversed_coin_transaction_id', v_reward_transaction.id,
      'removed_exp_event_id', old.id,
      'original_source_key', old.source_key
    )
  )
  on conflict (user_id, source_key) do nothing
  returning amount into v_inserted_amount;

  v_inserted_amount := coalesce(v_inserted_amount, 0);

  if v_inserted_amount = 0 then
    if not exists (
      select 1
      from public.coin_transactions as transaction
      where transaction.user_id = old.user_id
        and transaction.source_key = v_reversal_source_key
        and transaction.transaction_type = 'test_reset_reversal'
        and transaction.amount = v_reversal_amount
        and transaction.related_entity_id = v_reward_transaction.id
    ) then
      raise exception '기존 코인 취소 원장이 원본 보상과 일치하지 않습니다.';
    end if;

    return old;
  end if;

  update public.user_coin_wallets
  set
    balance = balance + v_inserted_amount,
    lifetime_earned = lifetime_earned + v_inserted_amount,
    updated_at = now()
  where user_id = old.user_id;

  return old;
end;
$$;

drop trigger if exists exp_events_reverse_coins_before_delete
on public.exp_events;

create trigger exp_events_reverse_coins_before_delete
before delete on public.exp_events
for each row execute function public.reverse_coins_for_deleted_exp_event();

revoke all on function public.reverse_coins_for_deleted_exp_event()
from public, anon, authenticated;

commit;
