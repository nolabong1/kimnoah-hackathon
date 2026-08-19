-- supabase_coin_test_reset.sql 실행 후 사용하는 읽기 전용 검증입니다.
begin;
set transaction read only;

do $$
declare
  reversal_function regprocedure;
  reset_function regprocedure;
  reset_core_function regprocedure;
begin
  reversal_function := pg_catalog.to_regprocedure(
    'public.reverse_coins_for_deleted_exp_event()'
  );
  reset_function := pg_catalog.to_regprocedure(
    'public.reset_today_test_progress()'
  );
  reset_core_function := pg_catalog.to_regprocedure(
    'public.reset_today_test_progress_without_coin_reversal()'
  );

  if reversal_function is null then
    raise exception '코인 취소 트리거 함수가 없습니다.';
  end if;

  if reset_function is null then
    raise exception '오늘 기록 초기화 RPC가 없습니다.';
  end if;

  if reset_core_function is null then
    raise exception '기존 적응형 학습 초기화 본문이 보존되지 않았습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    where procedure.oid = reversal_function
      and procedure.prosecdef
      and coalesce(procedure.proconfig::text, '') like '%search_path=%'
  ) then
    raise exception '코인 취소 함수의 보안 설정이 올바르지 않습니다.';
  end if;

  if not pg_catalog.has_function_privilege(
    'authenticated', reset_function, 'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'anon', reset_function, 'EXECUTE'
  ) then
    raise exception '오늘 기록 초기화 공개 RPC 권한이 올바르지 않습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'authenticated', reset_core_function, 'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'anon', reset_core_function, 'EXECUTE'
  ) then
    raise exception '기존 초기화 내부 함수가 클라이언트에 공개돼 있습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'anon', reversal_function, 'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'authenticated', reversal_function, 'EXECUTE'
  ) then
    raise exception '내부 코인 취소 함수가 클라이언트에 공개돼 있습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_trigger
    where tgname = 'exp_events_reverse_coins_before_delete'
      and tgrelid = 'public.exp_events'::regclass
      and tgenabled <> 'D'
      and not tgisinternal
  ) then
    raise exception 'EXP 원장 삭제의 코인 취소 트리거가 연결되지 않았습니다.';
  end if;

  if position(
    'delete from public.exp_events' in
    pg_catalog.pg_get_functiondef(reset_core_function)
  ) = 0 then
    raise exception '초기화 RPC의 EXP 원장 삭제 흐름을 확인할 수 없습니다.';
  end if;

  if position(
    'app.coin_test_reset' in
    pg_catalog.pg_get_functiondef(reset_function)
  ) = 0 or position(
    'app.coin_test_reset' in
    pg_catalog.pg_get_functiondef(reversal_function)
  ) = 0 then
    raise exception '코인 취소 범위를 제한하는 트랜잭션 플래그가 없습니다.';
  end if;
end;
$$;

do $$
begin
  if exists (
    select 1
    from public.coin_transactions as reversal
    left join public.coin_transactions as reward
      on reward.id = reversal.related_entity_id
     and reward.user_id = reversal.user_id
     and reward.amount = -reversal.amount
     and reward.transaction_type in (
       'task_completion',
       'daily_completion',
       'daily_challenge',
       'weekly_challenge'
     )
    where reversal.transaction_type = 'test_reset_reversal'
      and (
        reward.id is null
        or reversal.source_key <> 'reversal:' || reward.id::text
      )
  ) then
    raise exception '원본 보상과 일치하지 않는 코인 취소 원장이 있습니다.';
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
    raise exception 'EXP 삭제 후 취소되지 않은 코인 보상 원장이 있습니다.';
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
    raise exception '테스트 초기화 후 코인 지갑과 원장 합계가 다릅니다.';
  end if;
end;
$$;

select 'coin test reset validation: success' as validation_result;

rollback;
