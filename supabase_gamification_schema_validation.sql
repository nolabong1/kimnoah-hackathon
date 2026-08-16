-- supabase_gamification_schema.sql 실행 후 사용하는 읽기 전용 검증입니다.
begin;

do $$
declare
  required_table text;
  required_constraint text;
  required_index text;
  exp_event_constraint_definition text;
begin
  foreach required_table in array array[
    'user_achievements',
    'user_challenges',
    'user_badge_showcase'
  ]
  loop
    if to_regclass('public.' || required_table) is null then
      raise exception '필수 게임화 테이블이 없습니다: %', required_table;
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

    if has_table_privilege(
      'anon',
      'public.' || required_table,
      'SELECT'
    ) or has_table_privilege(
      'anon',
      'public.' || required_table,
      'INSERT'
    ) or has_table_privilege(
      'anon',
      'public.' || required_table,
      'UPDATE'
    ) or has_table_privilege(
      'anon',
      'public.' || required_table,
      'DELETE'
    ) then
      raise exception 'anon 권한이 남아 있습니다: %', required_table;
    end if;

    if has_table_privilege(
      'authenticated',
      'public.' || required_table,
      'INSERT'
    ) or has_table_privilege(
      'authenticated',
      'public.' || required_table,
      'UPDATE'
    ) or has_table_privilege(
      'authenticated',
      'public.' || required_table,
      'DELETE'
    ) then
      raise exception '직접 쓰기 권한이 남아 있습니다: %', required_table;
    end if;
  end loop;

  foreach required_constraint in array array[
    'user_achievements_user_key_unique',
    'user_achievements_reward_requires_unlock',
    'user_challenges_valid_period',
    'user_challenges_valid_display_order',
    'user_challenges_progress_not_above_target',
    'user_challenges_status_progress',
    'user_challenges_completion_state',
    'user_challenges_completion_timing',
    'user_challenges_user_template_period_unique',
    'user_challenges_user_period_order_unique',
    'user_badge_showcase_user_achievement_unique',
    'user_badge_showcase_owned_achievement_fk'
  ]
  loop
    if not exists (
      select 1
      from pg_catalog.pg_constraint
      where conname = required_constraint
        and connamespace = 'public'::regnamespace
    ) then
      raise exception '필수 제약조건이 없습니다: %', required_constraint;
    end if;
  end loop;

  foreach required_index in array array[
    'user_achievements_user_unlocked_idx',
    'user_challenges_user_period_idx',
    'user_challenges_user_claimable_idx'
  ]
  loop
    if to_regclass('public.' || required_index) is null then
      raise exception '필수 인덱스가 없습니다: %', required_index;
    end if;
  end loop;

  select pg_get_constraintdef(oid)
  into exp_event_constraint_definition
  from pg_catalog.pg_constraint
  where conname = 'exp_events_event_type_check'
    and conrelid = 'public.exp_events'::regclass;

  if exp_event_constraint_definition is null
    or position('achievement' in exp_event_constraint_definition) = 0
    or position('daily_challenge' in exp_event_constraint_definition) = 0
    or position('weekly_challenge' in exp_event_constraint_definition) = 0
  then
    raise exception 'exp_events 게임화 이벤트 유형 제약이 올바르지 않습니다.';
  end if;
end;
$$;

select 'gamification schema validation: success' as validation_result;

rollback;
