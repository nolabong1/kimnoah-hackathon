-- supabase_shop_inventory.sql 실행 후 사용하는 읽기 전용 검증입니다.
begin;
set transaction read only;

do $$
declare
  required_table text;
  required_constraint text;
  required_index text;
  purchase_function regprocedure;
  purchase_definition text;
begin
  foreach required_table in array array['shop_items', 'user_inventory']
  loop
    if to_regclass('public.' || required_table) is null then
      raise exception '필수 상점 테이블이 없습니다: %', required_table;
    end if;

    if not exists (
      select 1
      from pg_catalog.pg_class
      where oid = ('public.' || required_table)::regclass
        and relrowsecurity
    ) then
      raise exception '상점 테이블 RLS가 비활성화돼 있습니다: %', required_table;
    end if;

    if not has_table_privilege(
      'authenticated', 'public.' || required_table, 'SELECT'
    ) then
      raise exception '상점 조회 권한이 없습니다: %', required_table;
    end if;

    if has_table_privilege('anon', 'public.' || required_table, 'SELECT')
      or has_table_privilege('anon', 'public.' || required_table, 'INSERT')
      or has_table_privilege('anon', 'public.' || required_table, 'UPDATE')
      or has_table_privilege('anon', 'public.' || required_table, 'DELETE')
      or has_table_privilege('authenticated', 'public.' || required_table, 'INSERT')
      or has_table_privilege('authenticated', 'public.' || required_table, 'UPDATE')
      or has_table_privilege('authenticated', 'public.' || required_table, 'DELETE')
    then
      raise exception '상점 테이블에 허용하지 않은 권한이 있습니다: %',
        required_table;
    end if;
  end loop;

  if not exists (
    select 1
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename = 'shop_items'
      and policyname = 'shop_items_select_authenticated'
      and cmd = 'SELECT'
      and 'authenticated' = any(roles)
  ) then
    raise exception '인증 사용자 상점 조회 정책이 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename = 'user_inventory'
      and policyname = 'user_inventory_select_own'
      and cmd = 'SELECT'
      and 'authenticated' = any(roles)
      and position('auth.uid' in coalesce(qual, '')) > 0
  ) then
    raise exception '본인 인벤토리 조회 정책이 없습니다.';
  end if;

  foreach required_constraint in array array[
    'coin_transactions_id_user_unique',
    'shop_items_key_format',
    'shop_items_category_slot_layer_match',
    'user_inventory_profile_fk',
    'user_inventory_shop_item_fk',
    'user_inventory_purchase_owner_fk',
    'user_inventory_purchase_transaction_unique',
    'user_inventory_price_paid_positive'
  ]
  loop
    if not exists (
      select 1
      from pg_catalog.pg_constraint
      where conname = required_constraint
        and connamespace = 'public'::regnamespace
    ) then
      raise exception '필수 상점 제약조건이 없습니다: %', required_constraint;
    end if;
  end loop;

  foreach required_index in array array[
    'shop_items_active_category_sort_idx',
    'user_inventory_user_acquired_idx'
  ]
  loop
    if to_regclass('public.' || required_index) is null then
      raise exception '필수 상점 인덱스가 없습니다: %', required_index;
    end if;
  end loop;

  purchase_function := pg_catalog.to_regprocedure(
    'public.purchase_shop_item(text)'
  );

  if purchase_function is null then
    raise exception '상점 구매 RPC가 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    where procedure.oid = purchase_function
      and procedure.prosecdef
      and coalesce(procedure.proconfig::text, '') like '%search_path=%'
  ) then
    raise exception '상점 구매 RPC의 보안 설정이 올바르지 않습니다.';
  end if;

  if not pg_catalog.has_function_privilege(
    'authenticated', purchase_function, 'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'anon', purchase_function, 'EXECUTE'
  ) then
    raise exception '상점 구매 RPC 실행 권한이 올바르지 않습니다.';
  end if;

  purchase_definition := pg_catalog.pg_get_functiondef(purchase_function);

  if position('for update' in purchase_definition) = 0
     or position(
       '''purchase:'' || v_item.item_key' in purchase_definition
     ) = 0
     or position('v_wallet.balance < v_item.price' in purchase_definition) = 0
     or position('p_price' in purchase_definition) > 0
  then
    raise exception '상점 구매 RPC의 서버 가격·잠금 규칙이 올바르지 않습니다.';
  end if;
end;
$$;

do $$
begin
  if (select count(*) from public.shop_items) <> 15 then
    raise exception '초기 상점 카탈로그는 정확히 15종이어야 합니다.';
  end if;

  if exists (
    select 1
    from public.shop_items
    where not is_active
  ) then
    raise exception '초기 상점 카탈로그에 비활성 아이템이 있습니다.';
  end if;

  if (select sum(price) from public.shop_items) <> 1170 then
    raise exception '초기 상점 카탈로그 가격 합계가 승인안과 다릅니다.';
  end if;

  if (
    select pg_catalog.jsonb_agg(
      pg_catalog.jsonb_build_array(item_key, price)
      order by sort_order
    )
    from public.shop_items
  ) <> '[
    ["wall_morning_sky", 40],
    ["wall_warm_cream", 40],
    ["wall_night_focus", 160],
    ["floor_light_wood", 35],
    ["floor_soft_gray", 35],
    ["floor_starry_rug", 80],
    ["desk_oak_basic", 60],
    ["desk_white_clean", 85],
    ["desk_neon_coder", 170],
    ["chair_blue_basic", 50],
    ["chair_ergonomic", 100],
    ["decor_green_plant", 30],
    ["decor_focus_lamp", 45],
    ["decor_bookshelf", 90],
    ["accent_study_cat", 150]
  ]'::jsonb then
    raise exception '초기 상점 아이템 키와 가격이 승인안과 다릅니다.';
  end if;

  if exists (
    select 1
    from public.user_inventory as inventory
    join public.coin_transactions as transaction
      on transaction.id = inventory.purchase_transaction_id
     and transaction.user_id = inventory.user_id
    where transaction.transaction_type <> 'purchase'
       or (
         transaction.source_key <> 'purchase:' || inventory.item_key
         and transaction.source_key not like
           'shop_test:%:purchase:' || inventory.item_key
       )
       or transaction.amount <> -inventory.price_paid
  ) then
    raise exception '인벤토리와 구매 코인 원장이 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.coin_transactions as transaction
    where transaction.transaction_type = 'purchase'
      and transaction.source_key like 'purchase:%'
      and not exists (
        select 1
        from public.user_inventory as inventory
        where inventory.purchase_transaction_id = transaction.id
          and inventory.user_id = transaction.user_id
      )
  ) then
    raise exception '인벤토리가 없는 상점 구매 원장이 있습니다.';
  end if;
end;
$$;

select 'shop inventory validation: success' as validation_result;

rollback;
