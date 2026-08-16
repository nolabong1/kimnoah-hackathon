-- supabase_gamification_actions.sql 실행 후 사용하는 읽기 전용 검증입니다.
begin;
set transaction read only;

do $$
declare
  public_function regprocedure;
  internal_function regprocedure;
begin
  foreach public_function in array array[
    pg_catalog.to_regprocedure('public.sync_gamification_state()'),
    pg_catalog.to_regprocedure(
      'public.complete_study_task_with_gamification(uuid)'
    ),
    pg_catalog.to_regprocedure(
      'public.submit_quiz_attempt_with_gamification(uuid,timestamptz,jsonb,uuid)'
    ),
    pg_catalog.to_regprocedure(
      'public.claim_gamification_challenge(uuid)'
    ),
    pg_catalog.to_regprocedure(
      'public.equip_gamification_badge(text,integer)'
    ),
    pg_catalog.to_regprocedure(
      'public.remove_gamification_badge(integer)'
    )
  ]
  loop
    if public_function is null then
      raise exception '필수 게임화 공개 RPC가 없습니다.';
    end if;

    if not exists (
      select 1
      from pg_catalog.pg_proc as procedure
      where procedure.oid = public_function
        and procedure.prosecdef
        and coalesce(procedure.proconfig::text, '') like '%search_path=%'
    ) then
      raise exception '공개 RPC 보안 설정이 올바르지 않습니다: %',
        public_function;
    end if;

    if not pg_catalog.has_function_privilege(
      'authenticated', public_function, 'EXECUTE'
    ) then
      raise exception 'authenticated 실행 권한이 없습니다: %',
        public_function;
    end if;

    if pg_catalog.has_function_privilege(
      'anon', public_function, 'EXECUTE'
    ) then
      raise exception 'anon 실행 권한이 남아 있습니다: %', public_function;
    end if;
  end loop;

  foreach internal_function in array array[
    pg_catalog.to_regprocedure(
      'public.get_gamification_achievement_catalog()'
    ),
    pg_catalog.to_regprocedure(
      'public.get_gamification_challenge_catalog()'
    ),
    pg_catalog.to_regprocedure(
      'public.get_user_gamification_metric(uuid,text,timestamptz,timestamptz)'
    ),
    pg_catalog.to_regprocedure(
      'public.sync_user_gamification(uuid,timestamptz)'
    )
  ]
  loop
    if internal_function is null then
      raise exception '필수 게임화 내부 함수가 없습니다.';
    end if;

    if pg_catalog.has_function_privilege(
      'authenticated', internal_function, 'EXECUTE'
    ) or pg_catalog.has_function_privilege(
      'anon', internal_function, 'EXECUTE'
    ) then
      raise exception '게임화 내부 함수가 공개돼 있습니다: %',
        internal_function;
    end if;
  end loop;

  if pg_catalog.has_function_privilege(
    'authenticated',
    'public.complete_study_task(uuid)',
    'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'authenticated',
    'public.submit_quiz_attempt(uuid,timestamptz,jsonb,uuid)',
    'EXECUTE'
  ) then
    raise exception '게임화를 우회하는 기존 학습 행동 RPC 권한이 남아 있습니다.';
  end if;
end;
$$;

do $$
begin
  if (
    select count(*)
    from public.get_gamification_achievement_catalog()
  ) <> 13 then
    raise exception '서버 업적 카탈로그 수가 올바르지 않습니다.';
  end if;

  if (
    select count(*)
    from public.get_gamification_challenge_catalog()
  ) <> 11 then
    raise exception '서버 도전과제 카탈로그 수가 올바르지 않습니다.';
  end if;

  if exists (
    select achievement.achievement_key
    from public.user_achievements as achievement
    left join public.get_gamification_achievement_catalog() as catalog
      on catalog.achievement_key = achievement.achievement_key
    where catalog.achievement_key is null
  ) then
    raise exception '서버 카탈로그에 없는 사용자 업적이 저장돼 있습니다.';
  end if;

  if exists (
    select challenge.id
    from public.user_challenges as challenge
    left join public.get_gamification_challenge_catalog() as catalog
      on catalog.template_key = challenge.template_key
     and catalog.period_type = challenge.period_type
    where catalog.template_key is null
       or catalog.target_value <> challenge.target_value
       or catalog.reward_exp <> challenge.reward_exp
  ) then
    raise exception '저장된 도전과제가 서버 카탈로그와 다릅니다.';
  end if;
end;
$$;

do $$
begin
  if exists (
    select 1
    from public.user_achievements as achievement
    where achievement.rewarded_at is not null
      and not exists (
        select 1
        from public.exp_events as event
        where event.user_id = achievement.user_id
          and event.event_type = 'achievement'
          and event.source_key =
            'achievement:' || achievement.achievement_key
      )
  ) then
    raise exception '보상 원장이 없는 지급 완료 업적이 있습니다.';
  end if;

  if exists (
    select 1
    from public.exp_events as event
    join public.get_gamification_achievement_catalog() as catalog
      on event.source_key = 'achievement:' || catalog.achievement_key
    where event.event_type = 'achievement'
      and event.amount <> catalog.reward_exp
  ) then
    raise exception '업적 EXP 금액이 서버 카탈로그와 다릅니다.';
  end if;

  if exists (
    select 1
    from public.user_challenges as challenge
    where challenge.status = 'claimed'
      and not exists (
        select 1
        from public.exp_events as event
        where event.user_id = challenge.user_id
          and event.event_type = case challenge.period_type
            when 'daily' then 'daily_challenge'
            else 'weekly_challenge'
          end
          and event.source_key = 'challenge:' || challenge.id::text
          and event.amount = challenge.reward_exp
      )
  ) then
    raise exception '보상 원장이 없는 수령 완료 도전과제가 있습니다.';
  end if;

  if exists (
    select 1
    from public.exp_events as event
    where event.event_type in (
      'achievement',
      'daily_challenge',
      'weekly_challenge'
    )
    group by event.user_id, event.source_key
    having count(*) > 1
  ) then
    raise exception '게임화 EXP source_key가 중복됐습니다.';
  end if;

  if exists (
    select 1
    from public.user_badge_showcase as showcase
    left join public.user_achievements as achievement
      on achievement.user_id = showcase.user_id
     and achievement.achievement_key = showcase.achievement_key
     and achievement.unlocked_at is not null
    where achievement.id is null
  ) then
    raise exception '해금하지 않은 대표 배지가 장착돼 있습니다.';
  end if;
end;
$$;

select 'gamification actions validation: success' as validation_result;

rollback;
