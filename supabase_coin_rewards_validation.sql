-- supabase_coin_rewards.sql 실행 후 사용하는 읽기 전용 검증입니다.
begin;
set transaction read only;

do $$
declare
  reward_function regprocedure;
  reward_function_definition text;
begin
  reward_function := pg_catalog.to_regprocedure(
    'public.award_coins_for_exp_event()'
  );

  if reward_function is null then
    raise exception '코인 보상 트리거 함수가 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    where procedure.oid = reward_function
      and procedure.prosecdef
      and coalesce(procedure.proconfig::text, '') like '%search_path=%'
  ) then
    raise exception '코인 보상 트리거 함수의 보안 설정이 올바르지 않습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'anon', reward_function, 'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'authenticated', reward_function, 'EXECUTE'
  ) then
    raise exception '내부 코인 보상 함수가 클라이언트에 공개돼 있습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_trigger
    where tgname = 'exp_events_award_coins'
      and tgrelid = 'public.exp_events'::regclass
      and tgenabled <> 'D'
      and not tgisinternal
  ) then
    raise exception 'EXP 원장의 코인 보상 트리거가 연결되지 않았습니다.';
  end if;

  reward_function_definition := pg_catalog.pg_get_functiondef(
    reward_function
  );

  if position(
       'when ''task_completion''' in reward_function_definition
     ) = 0
     or position('v_coin_amount := 5' in reward_function_definition) = 0
     or position(
       'when ''daily_completion''' in reward_function_definition
     ) = 0
     or position(
       'when ''daily_challenge''' in reward_function_definition
     ) = 0
     or position(
       'when ''weekly_challenge''' in reward_function_definition
     ) = 0
     or position('v_task_coins_awarded_today >= 25' in reward_function_definition) = 0
  then
    raise exception '승인된 코인 보상 또는 일일 상한 정의가 누락됐습니다.';
  end if;
end;
$$;

do $$
begin
  if exists (
    select 1
    from public.coin_transactions as transaction
    where transaction.transaction_type in (
      'task_completion',
      'daily_completion',
      'daily_challenge',
      'weekly_challenge'
    )
      and not exists (
        select 1
        from public.exp_events as event
        where event.user_id = transaction.user_id
          and event.source_key = transaction.source_key
          and event.event_type = transaction.transaction_type
      )
      and not exists (
        select 1
        from public.coin_transactions as reversal
        where reversal.user_id = transaction.user_id
          and reversal.transaction_type = 'test_reset_reversal'
          and reversal.related_entity_id = transaction.id
          and reversal.amount = -transaction.amount
      )
  ) then
    raise exception 'EXP 이벤트 또는 취소 원장이 없는 코인 보상이 있습니다.';
  end if;

  if exists (
    select 1
    from public.coin_transactions as transaction
    where (
      transaction.transaction_type = 'task_completion'
      and transaction.amount <> 5
    ) or (
      transaction.transaction_type in (
        'daily_completion',
        'daily_challenge'
      )
      and transaction.amount <> 10
    ) or (
      transaction.transaction_type = 'weekly_challenge'
      and transaction.amount <> 30
    )
  ) then
    raise exception '승인된 기준과 다른 코인 보상 금액이 있습니다.';
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
    raise exception '과제 완료 코인의 서울 날짜 기준 일일 상한을 초과했습니다.';
  end if;
end;
$$;

select 'coin rewards validation: success' as validation_result;

rollback;
