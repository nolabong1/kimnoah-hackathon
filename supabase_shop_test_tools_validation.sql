-- supabase_shop_test_tools.sql 적용 후 실행하는 읽기 전용 검증입니다.
begin;
set transaction read only;

do $$
declare
  required_constraint text;
  required_index text;
  required_function regprocedure;
  function_definition text;
begin
  if pg_catalog.to_regclass('public.shop_test_sessions') is null then
    raise exception '상점 테스트 세션 테이블이 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_class
    where oid = 'public.shop_test_sessions'::regclass
      and relrowsecurity
  ) then
    raise exception '상점 테스트 세션 RLS가 비활성화돼 있습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename = 'shop_test_sessions'
      and policyname = 'shop_test_sessions_select_own'
      and cmd = 'SELECT'
      and 'authenticated' = any(roles)
      and position('auth.uid' in coalesce(qual, '')) > 0
  ) then
    raise exception '본인 상점 테스트 세션 조회 정책이 없습니다.';
  end if;

  if not pg_catalog.has_table_privilege(
    'authenticated', 'public.shop_test_sessions', 'SELECT'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.shop_test_sessions', 'INSERT'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.shop_test_sessions', 'UPDATE'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.shop_test_sessions', 'DELETE'
  ) or pg_catalog.has_table_privilege(
    'anon', 'public.shop_test_sessions', 'SELECT'
  ) then
    raise exception '상점 테스트 세션 테이블 권한이 올바르지 않습니다.';
  end if;

  foreach required_constraint in array array[
    'shop_test_sessions_profile_fk',
    'shop_test_sessions_credit_owner_fk',
    'shop_test_sessions_status_check',
    'shop_test_sessions_credit_positive',
    'shop_test_sessions_counts_nonnegative',
    'shop_test_sessions_snapshot_array',
    'shop_test_sessions_reset_state_check',
    'coin_transactions_transaction_type_check',
    'coin_transactions_amount_direction'
  ]
  loop
    if not exists (
      select 1
      from pg_catalog.pg_constraint
      where conname = required_constraint
        and connamespace = 'public'::regnamespace
    ) then
      raise exception '상점 테스트 필수 제약조건이 없습니다: %',
        required_constraint;
    end if;
  end loop;

  foreach required_index in array array[
    'shop_test_sessions_one_active_user_idx',
    'shop_test_sessions_user_started_idx'
  ]
  loop
    if pg_catalog.to_regclass('public.' || required_index) is null then
      raise exception '상점 테스트 필수 인덱스가 없습니다: %', required_index;
    end if;
  end loop;

  foreach required_function in array array[
    pg_catalog.to_regprocedure('public.start_shop_test_session()'),
    pg_catalog.to_regprocedure('public.reset_shop_test_session(uuid)')
  ]
  loop
    if required_function is null then
      raise exception '상점 테스트 공개 RPC가 없습니다.';
    end if;

    if not exists (
      select 1
      from pg_catalog.pg_proc as procedure
      where procedure.oid = required_function
        and procedure.prosecdef
        and coalesce(procedure.proconfig::text, '') like '%search_path=%'
    ) then
      raise exception '상점 테스트 RPC 보안 설정이 올바르지 않습니다.';
    end if;

    if not pg_catalog.has_function_privilege(
      'authenticated', required_function, 'EXECUTE'
    ) or pg_catalog.has_function_privilege(
      'anon', required_function, 'EXECUTE'
    ) then
      raise exception '상점 테스트 RPC 실행 권한이 올바르지 않습니다.';
    end if;
  end loop;

  required_function := pg_catalog.to_regprocedure(
    'public.purchase_shop_item(text)'
  );
  function_definition := pg_catalog.pg_get_functiondef(required_function);

  if position('shop_test_sessions' in function_definition) = 0
     or position('shop_test_session_id' in function_definition) = 0
     or position('for update' in function_definition) = 0
     or position('v_wallet.balance < v_item.price' in function_definition) = 0
  then
    raise exception '구매 RPC에 상점 테스트 세션 추적이 연결되지 않았습니다.';
  end if;
end;
$$;

do $$
begin
  if exists (
    select user_id
    from public.shop_test_sessions
    where status = 'active'
    group by user_id
    having count(*) > 1
  ) then
    raise exception '사용자에게 활성 상점 테스트 세션이 중복됐습니다.';
  end if;

  if exists (
    select 1
    from public.shop_test_sessions as session
    join public.coin_transactions as credit
      on credit.id = session.credit_transaction_id
     and credit.user_id = session.user_id
    where credit.transaction_type <> 'shop_test_credit'
       or credit.amount <> session.credit_amount
       or credit.related_entity_id <> session.id
       or credit.source_key <>
         'shop_test:' || session.id::text || ':credit'
  ) then
    raise exception '상점 테스트 세션과 테스트 코인 원장이 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.shop_test_sessions as session
    where session.status = 'reset'
      and not exists (
        select 1
        from public.coin_transactions as reversal
        where reversal.user_id = session.user_id
          and reversal.transaction_type = 'test_reset_reversal'
          and reversal.amount = -session.credit_amount
          and reversal.related_entity_id = session.credit_transaction_id
          and reversal.source_key =
            'shop_test:' || session.id::text || ':credit_reversal'
      )
  ) then
    raise exception '초기화된 테스트 세션의 코인 회수 원장이 없습니다.';
  end if;

  if exists (
    select 1
    from public.coin_transactions as purchase
    left join public.shop_test_sessions as session
      on session.id = purchase.related_entity_id
     and session.user_id = purchase.user_id
    where purchase.transaction_type = 'purchase'
      and purchase.source_key like 'shop_test:%'
      and (
        session.id is null
        or purchase.source_key not like
          'shop_test:' || session.id::text || ':purchase:%'
      )
  ) then
    raise exception '세션과 연결되지 않은 상점 테스트 구매 원장이 있습니다.';
  end if;

  if exists (
    select 1
    from public.shop_test_sessions as session
    where session.status = 'reset'
      and (
        select coalesce(sum(-purchase.amount), 0)::integer
        from public.coin_transactions as purchase
        where purchase.user_id = session.user_id
          and purchase.transaction_type = 'purchase'
          and purchase.related_entity_id = session.id
      ) <> session.refunded_coin_amount
  ) then
    raise exception '테스트 구매 금액과 저장된 환급 금액이 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.shop_test_sessions as session
    where session.status = 'reset'
      and session.refunded_coin_amount > 0
      and not exists (
        select 1
        from public.coin_transactions as refund
        where refund.user_id = session.user_id
          and refund.transaction_type = 'shop_test_purchase_refund'
          and refund.amount = session.refunded_coin_amount
          and refund.related_entity_id = session.id
          and refund.source_key =
            'shop_test:' || session.id::text || ':purchase_refund'
      )
  ) then
    raise exception '초기화된 테스트 구매의 환급 원장이 없습니다.';
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
    raise exception '상점 테스트 반영 후 지갑과 원장 합계가 일치하지 않습니다.';
  end if;
end;
$$;

select
  'shop test tools validation: success' as validation_result,
  (select count(*) from public.shop_test_sessions) as test_sessions,
  (
    select count(*)
    from public.shop_test_sessions
    where status = 'active'
  ) as active_sessions;

rollback;
