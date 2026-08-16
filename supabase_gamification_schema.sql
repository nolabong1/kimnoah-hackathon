-- 업적·배지·일간/주간 도전과제 저장 구조
-- 원격 Supabase SQL Editor에서 수동 실행해야 합니다.
begin;

alter table public.exp_events
drop constraint if exists exp_events_event_type_check;

alter table public.exp_events
add constraint exp_events_event_type_check
check (
  event_type in (
    'task_completion',
    'quiz_submission',
    'quiz_score_bonus',
    'daily_completion',
    'achievement',
    'daily_challenge',
    'weekly_challenge'
  )
);

create table public.user_achievements (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  achievement_key text not null
    check (char_length(btrim(achievement_key)) between 1 and 100),
  progress_value integer not null default 0
    check (progress_value >= 0),
  unlocked_at timestamptz,
  rewarded_at timestamptz,
  progress_snapshot jsonb not null default '{}'::jsonb
    check (jsonb_typeof(progress_snapshot) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_achievements_user_key_unique
    unique (user_id, achievement_key),
  constraint user_achievements_reward_requires_unlock
    check (
      rewarded_at is null
      or (unlocked_at is not null and rewarded_at >= unlocked_at)
    )
);

create table public.user_challenges (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  template_key text not null
    check (char_length(btrim(template_key)) between 1 and 100),
  period_type text not null
    check (period_type in ('daily', 'weekly')),
  period_start timestamptz not null,
  period_end timestamptz not null,
  display_order smallint not null,
  target_value integer not null check (target_value > 0),
  progress_value integer not null default 0
    check (progress_value >= 0),
  reward_exp integer not null check (reward_exp > 0),
  status text not null default 'active'
    check (status in ('active', 'completed', 'claimed', 'expired')),
  completed_at timestamptz,
  claimed_at timestamptz,
  eligibility_snapshot jsonb not null default '{}'::jsonb
    check (jsonb_typeof(eligibility_snapshot) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_challenges_valid_period
    check (period_end > period_start),
  constraint user_challenges_valid_display_order
    check (
      (period_type = 'daily' and display_order between 1 and 3)
      or (period_type = 'weekly' and display_order between 1 and 2)
    ),
  constraint user_challenges_progress_not_above_target
    check (progress_value <= target_value),
  constraint user_challenges_status_progress
    check (
      (status in ('active', 'expired') and progress_value < target_value)
      or (status in ('completed', 'claimed') and progress_value = target_value)
    ),
  constraint user_challenges_completion_state
    check (
      (status = 'active' and completed_at is null and claimed_at is null)
      or (status = 'completed' and completed_at is not null and claimed_at is null)
      or (status = 'claimed' and completed_at is not null and claimed_at is not null)
      or (status = 'expired' and completed_at is null and claimed_at is null)
    ),
  constraint user_challenges_completion_timing
    check (
      (
        completed_at is null
        or (
          completed_at >= period_start
          and completed_at < period_end
        )
      )
      and (
        claimed_at is null
        or (completed_at is not null and claimed_at >= completed_at)
      )
    ),
  constraint user_challenges_user_template_period_unique
    unique (user_id, template_key, period_type, period_start),
  constraint user_challenges_user_period_order_unique
    unique (user_id, period_type, period_start, display_order)
);

create table public.user_badge_showcase (
  user_id uuid not null references public.profiles(id) on delete cascade,
  slot smallint not null check (slot between 1 and 3),
  achievement_key text not null
    check (char_length(btrim(achievement_key)) between 1 and 100),
  equipped_at timestamptz not null default now(),
  constraint user_badge_showcase_pkey primary key (user_id, slot),
  constraint user_badge_showcase_user_achievement_unique
    unique (user_id, achievement_key),
  constraint user_badge_showcase_owned_achievement_fk
    foreign key (user_id, achievement_key)
    references public.user_achievements(user_id, achievement_key)
    on delete cascade
);

create index user_achievements_user_unlocked_idx
on public.user_achievements(user_id, unlocked_at desc)
where unlocked_at is not null;

create index user_challenges_user_period_idx
on public.user_challenges(user_id, period_type, period_start desc);

create index user_challenges_user_claimable_idx
on public.user_challenges(user_id, completed_at desc)
where status = 'completed';

create trigger user_achievements_set_updated_at
before update on public.user_achievements
for each row execute function public.set_updated_at();

create trigger user_challenges_set_updated_at
before update on public.user_challenges
for each row execute function public.set_updated_at();

alter table public.user_achievements enable row level security;
alter table public.user_challenges enable row level security;
alter table public.user_badge_showcase enable row level security;

create policy "user_achievements_select_own"
on public.user_achievements
for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "user_challenges_select_own"
on public.user_challenges
for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "user_badge_showcase_select_own"
on public.user_badge_showcase
for select
to authenticated
using ((select auth.uid()) = user_id);

-- 진행도, 보상, 장착 상태는 Phase C의 소유권 검증 RPC만 변경합니다.
revoke all on public.user_achievements from anon, authenticated;
revoke all on public.user_challenges from anon, authenticated;
revoke all on public.user_badge_showcase from anon, authenticated;

grant select on public.user_achievements to authenticated;
grant select on public.user_challenges to authenticated;
grant select on public.user_badge_showcase to authenticated;

commit;
