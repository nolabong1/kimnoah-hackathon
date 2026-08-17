-- supabase_coin_economy_schema.sql 실행 후 사용하는 읽기 전용 검증입니다.
begin;
set transaction read only;

do $$
declare
  required_table text;
  required_constraint text;
  required_index text;
  trigger_function regprocedure;
begin
  foreach required_table in array array[
    'user_coin_wallets',
    'coin_transactions'
  ]
  loop
    if to_regclass('public.' || required_table) is null then
      raise exception '필수 코인 테이블이 없습니다: %', required_table;
    end if;

    if not exists (
      select 1
      from pg_catalog.pg_class
      where oid = ('public.' || required_table)::regclass
        and relrowsecurity
    ) then
      raise exception 'RLS가 비활성화되어 있습니다: %', required_table;
    end if;

    if not exists (
      select 1
      from pg_catalog.pg_policies
      where schemaname = 'public'
        and tablename = required_table
        and cmd = 'SELECT'
        and 'authenticated' = any(roles)
        and position('auth.uid' in coalesce(qual, '')) > 0
    ) then
      raise exception '본인 조회 정책이 없습니다: %', required_table;
    end if;

    if not has_table_privilege(
      'authenticated',
      'public.' || required_table,
      'SELECT'
    ) then
      raise exception 'authenticated 조회 권한이 없습니다: %', required_table;
    end if;

    if has_table_privilege('anon', 'public.' || required_table, 'SELECT')
      or has_table_privilege('anon', 'public.' || required_table, 'INSERT')
      or has_table_privilege('anon', 'public.' || required_table, 'UPDATE')
      or has_table_privilege('anon', 'public.' || required_table, 'DELETE')
    then
      raise exception 'anon 권한이 남아 있습니다: %', required_table;
    end if;

    if has_table_privilege(
      'authenticated', 'public.' || required_table, 'INSERT'
    ) or has_table_privilege(
      'authenticated', 'public.' || required_table, 'UPDATE'
    ) or has_table_privilege(
      'authenticated', 'public.' || required_table, 'DELETE'
    ) then
      raise exception '클라이언트 직접 쓰기 권한이 남아 있습니다: %',
        required_table;
    end if;
  end loop;

  foreach required_constraint in array array[
    'user_coin_wallets_profile_fk',
    'user_coin_wallets_balance_nonnegative',
    'user_coin_wallets_lifetime_earned_nonnegative',
    'user_coin_wallets_lifetime_spent_nonnegative',
    'user_coin_wallets_totals_match',
    'coin_transactions_wallet_fk',
    'coin_transactions_user_source_unique',
    'coin_transactions_amount_direction'
  ]
  loop
    if not exists (
      select 1
      from pg_catalog.pg_constraint
      where conname = required_constraint
        and connamespace = 'public'::regnamespace
    ) then
      raise exception '필수 코인 제약조건이 없습니다: %',
        required_constraint;
    end if;
  end loop;

  foreach required_index in array array[
    'coin_transactions_user_created_idx',
    'coin_transactions_user_type_created_idx',
    'coin_transactions_user_related_entity_idx'
  ]
  loop
    if to_regclass('public.' || required_index) is null then
      raise exception '필수 코인 인덱스가 없습니다: %', required_index;
    end if;
  end loop;

  if not exists (
    select 1
    from pg_catalog.pg_trigger
    where tgname = 'on_profile_coin_wallet_created'
      and tgrelid = 'public.profiles'::regclass
      and not tgisinternal
  ) then
    raise exception '신규 프로필 코인 지갑 트리거가 없습니다.';
  end if;

  trigger_function := pg_catalog.to_regprocedure(
    'public.initialize_coin_wallet_for_profile()'
  );

  if trigger_function is null then
    raise exception '코인 지갑 초기화 함수가 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    where procedure.oid = trigger_function
      and procedure.prosecdef
      and coalesce(procedure.proconfig::text, '') like '%search_path=%'
  ) then
    raise exception '코인 지갑 초기화 함수 보안 설정이 올바르지 않습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'anon', trigger_function, 'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'authenticated', trigger_function, 'EXECUTE'
  ) then
    raise exception '내부 코인 지갑 초기화 함수가 공개돼 있습니다.';
  end if;
end;
$$;

do $$
begin
  if exists (
    select profile.id
    from public.profiles as profile
    left join public.user_coin_wallets as wallet
      on wallet.user_id = profile.id
    where wallet.user_id is null
  ) then
    raise exception '코인 지갑이 없는 기존 사용자가 있습니다.';
  end if;

  if exists (
    select wallet.user_id
    from public.user_coin_wallets as wallet
    where not exists (
      select 1
      from public.coin_transactions as transaction
      where transaction.user_id = wallet.user_id
        and transaction.transaction_type = 'onboarding'
        and transaction.source_key = 'onboarding:shop_v1'
        and transaction.amount = 30
        and transaction.balance_after = 30
    )
  ) then
    raise exception '시작 코인 원장이 없는 지갑이 있습니다.';
  end if;

  if exists (
    select transaction.user_id, transaction.source_key
    from public.coin_transactions as transaction
    group by transaction.user_id, transaction.source_key
    having count(*) > 1
  ) then
    raise exception '코인 source_key가 중복됐습니다.';
  end if;

  if exists (
    select wallet.user_id
    from public.user_coin_wallets as wallet
    left join lateral (
      select
        coalesce(sum(transaction.amount), 0)::integer as balance,
        coalesce(
          sum(transaction.amount) filter (
            where transaction.transaction_type <> 'purchase'
          ),
          0
        )::integer as earned,
        coalesce(
          sum(-transaction.amount) filter (
            where transaction.transaction_type = 'purchase'
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
    raise exception '코인 지갑과 거래 원장 합계가 일치하지 않습니다.';
  end if;
end;
$$;

select 'coin economy schema validation: success' as validation_result;

rollback;
