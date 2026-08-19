-- 코인·상점·학습방·컬렉션·상점 테스트 도구의 최종 읽기 전용 검증입니다.
-- 관련 마이그레이션과 개별 validation SQL 적용 후 한 번 실행합니다.
begin;
set transaction read only;

do $$
declare
  required_table text;
  required_function regprocedure;
begin
  foreach required_table in array array[
    'exp_events',
    'user_coin_wallets',
    'coin_transactions',
    'shop_items',
    'user_inventory',
    'user_study_rooms',
    'shop_test_sessions'
  ]
  loop
    if pg_catalog.to_regclass('public.' || required_table) is null then
      raise exception '통합 검증 필수 테이블이 없습니다: %', required_table;
    end if;
  end loop;

  if not exists (
    select 1
    from pg_catalog.pg_trigger
    where tgname = 'exp_events_award_coins'
      and tgrelid = 'public.exp_events'::regclass
      and tgenabled <> 'D'
      and not tgisinternal
  ) then
    raise exception 'EXP 원장과 코인 보상 트리거가 연결되지 않았습니다.';
  end if;

  foreach required_function in array array[
    pg_catalog.to_regprocedure('public.purchase_shop_item(text)'),
    pg_catalog.to_regprocedure(
      'public.save_user_study_room(text,text,text,text,text,text,text,jsonb)'
    ),
    pg_catalog.to_regprocedure('public.start_shop_test_session()'),
    pg_catalog.to_regprocedure('public.reset_shop_test_session(uuid)')
  ]
  loop
    if required_function is null then
      raise exception '상점 또는 학습방 공개 RPC가 없습니다.';
    end if;
    if not pg_catalog.has_function_privilege(
      'authenticated', required_function, 'EXECUTE'
    ) or pg_catalog.has_function_privilege(
      'anon', required_function, 'EXECUTE'
    ) then
      raise exception '상점 또는 학습방 RPC 권한이 올바르지 않습니다.';
    end if;
  end loop;

  if not exists (
    select 1
    from pg_catalog.pg_attribute
    where attrelid = 'public.user_study_rooms'::regclass
      and attname = 'item_transforms'
      and not attisdropped
  ) then
    raise exception '학습방 직접 배치 열이 없습니다.';
  end if;
end;
$$;

do $$
begin
  if (select count(*) from public.shop_items where is_active) <> 15
    or (select sum(price) from public.shop_items where is_active) <> 1170
  then
    raise exception '활성 상점 15종 또는 총 가격 1170코인이 일치하지 않습니다.';
  end if;

  if exists (
    select wallet.user_id
    from public.user_coin_wallets as wallet
    left join lateral (
      select
        coalesce(sum(transaction.amount), 0)::integer as balance,
        coalesce(
          sum(transaction.amount) filter (
            where transaction.transaction_type in (
              'onboarding',
              'task_completion',
              'daily_completion',
              'daily_challenge',
              'weekly_challenge',
              'shop_test_credit',
              'test_reset_reversal'
            )
          ),
          0
        )::integer as earned,
        coalesce(
          sum(-transaction.amount) filter (
            where transaction.transaction_type = 'purchase'
          ),
          0
        )::integer
        - coalesce(
          sum(transaction.amount) filter (
            where transaction.transaction_type = 'shop_test_purchase_refund'
          ),
          0
        )::integer as spent
      from public.coin_transactions as transaction
      where transaction.user_id = wallet.user_id
    ) as totals on true
    where wallet.balance <> totals.balance
      or wallet.lifetime_earned <> totals.earned
      or wallet.lifetime_spent <> totals.spent
  ) then
    raise exception '코인 지갑과 전체 원장 합계가 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.coin_transactions as reward
    where reward.transaction_type in (
      'task_completion',
      'daily_completion',
      'daily_challenge',
      'weekly_challenge'
    )
      and not exists (
        select 1
        from public.exp_events as event
        where event.user_id = reward.user_id
          and event.source_key = reward.source_key
          and event.event_type = reward.transaction_type
      )
      and not exists (
        select 1
        from public.coin_transactions as reversal
        where reversal.user_id = reward.user_id
          and reversal.transaction_type = 'test_reset_reversal'
          and reversal.related_entity_id = reward.id
          and reversal.amount = -reward.amount
      )
  ) then
    raise exception 'EXP 근거나 테스트 취소가 없는 코인 보상이 있습니다.';
  end if;

  if exists (
    select
      transaction.user_id,
      (transaction.created_at at time zone 'Asia/Seoul')::date
    from public.coin_transactions as transaction
    where transaction.transaction_type = 'task_completion'
    group by
      transaction.user_id,
      (transaction.created_at at time zone 'Asia/Seoul')::date
    having sum(transaction.amount) > 25
  ) then
    raise exception '서울 날짜 기준 과제 코인 일일 상한을 초과했습니다.';
  end if;
end;
$$;

do $$
begin
  if exists (
    select 1
    from public.user_inventory as inventory
    join public.coin_transactions as purchase
      on purchase.id = inventory.purchase_transaction_id
     and purchase.user_id = inventory.user_id
    where purchase.transaction_type <> 'purchase'
       or (
         purchase.source_key <> 'purchase:' || inventory.item_key
         and not exists (
           select 1
           from public.shop_test_sessions as session
           where session.id = purchase.related_entity_id
             and session.user_id = purchase.user_id
             and purchase.source_key =
               'shop_test:' || session.id::text
               || ':purchase:' || inventory.item_key
         )
       )
       or purchase.amount <> -inventory.price_paid
  ) then
    raise exception '인벤토리와 구매 코인 원장이 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.coin_transactions as purchase
    where purchase.transaction_type = 'purchase'
      and not exists (
        select 1
        from public.user_inventory as inventory
        where inventory.user_id = purchase.user_id
          and inventory.purchase_transaction_id = purchase.id
      )
      and not exists (
        select 1
        from public.shop_test_sessions as session
        join public.coin_transactions as refund
          on refund.user_id = session.user_id
         and refund.related_entity_id = session.id
         and refund.transaction_type = 'shop_test_purchase_refund'
        where session.id = purchase.related_entity_id
          and session.user_id = purchase.user_id
          and session.status = 'reset'
      )
  ) then
    raise exception '인벤토리가 없는 구매 코인 원장이 있습니다.';
  end if;

  if exists (
    select 1
    from public.user_study_rooms as room
    cross join lateral (
      values
        (room.background_item_key, 'background'),
        (room.floor_item_key, 'floor'),
        (room.desk_item_key, 'desk'),
        (room.chair_item_key, 'chair'),
        (room.decor_left_item_key, 'decor_left'),
        (room.decor_right_item_key, 'decor_right'),
        (room.accent_item_key, 'accent')
    ) as equipped(item_key, slot_key)
    where equipped.item_key is not null
      and not exists (
        select 1
        from public.user_inventory as inventory
        join public.shop_items as item
          on item.item_key = inventory.item_key
        where inventory.user_id = room.user_id
          and inventory.item_key = equipped.item_key
          and item.is_active
          and equipped.slot_key = any(item.allowed_slots)
      )
  ) then
    raise exception '보유·활성·슬롯 규칙과 맞지 않는 학습방 장착이 있습니다.';
  end if;

  if exists (
    select inventory.user_id
    from public.user_inventory as inventory
    join public.shop_items as item
      on item.item_key = inventory.item_key
     and item.is_active
    group by inventory.user_id
    having count(distinct inventory.item_key) > 15
  ) then
    raise exception '사용자 컬렉션 수가 활성 카탈로그 수를 초과했습니다.';
  end if;
end;
$$;

select
  'shop room integration validation: success' as validation_result,
  (select count(*) from public.shop_items where is_active) as active_items,
  (select sum(price) from public.shop_items where is_active) as total_price,
  (select count(*) from public.user_inventory) as owned_rows,
  (select count(*) from public.user_study_rooms) as saved_rooms;

rollback;
