-- 개발용 테스트 RPC를 명시적으로 허용된 사용자에게만 공개합니다.
-- 기존 테스트 기능 SQL을 모두 적용한 뒤 이 마이그레이션을 마지막에 실행합니다.
begin;

create table if not exists public.test_tool_access (
  user_id uuid primary key
    references auth.users(id) on delete cascade,
  granted_at timestamptz not null default now(),
  granted_by uuid references auth.users(id) on delete set null,
  note text,
  constraint test_tool_access_note_length_check
    check (note is null or char_length(note) <= 500)
);

alter table public.test_tool_access enable row level security;

revoke all on public.test_tool_access from public, anon, authenticated;

comment on table public.test_tool_access is
  '운영 사용자에게 숨겨야 하는 개발용 테스트 RPC의 명시적 사용자 허용 목록';

create or replace function public.can_use_test_tools()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select auth.uid() is not null
    and exists (
      select 1
      from public.test_tool_access as access
      where access.user_id = auth.uid()
    );
$$;

create or replace function public.require_test_tool_access()
returns uuid
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
begin
  if v_user_id is null then
    raise exception using
      errcode = '42501',
      message = '로그인이 필요합니다.';
  end if;

  if not exists (
    select 1
    from public.test_tool_access as access
    where access.user_id = v_user_id
  ) then
    raise exception using
      errcode = '42501',
      message = '테스트 도구 사용 권한이 없습니다.';
  end if;

  return v_user_id;
end;
$$;

revoke all on function public.can_use_test_tools()
from public, anon, authenticated;
grant execute on function public.can_use_test_tools()
to authenticated;

revoke all on function public.require_test_tool_access()
from public, anon, authenticated;

-- 기존 구현은 비공개 내부 함수로 한 번만 이동합니다. 이 파일은 재실행할 수 있습니다.
do $$
begin
  if pg_catalog.to_regprocedure(
    'public.reset_today_test_progress_unchecked()'
  ) is null then
    if pg_catalog.to_regprocedure(
      'public.reset_today_test_progress()'
    ) is null then
      raise exception 'reset_today_test_progress()가 먼저 필요합니다.';
    end if;
    alter function public.reset_today_test_progress()
      rename to reset_today_test_progress_unchecked;
  end if;

  if pg_catalog.to_regprocedure(
    'public.complete_study_plan_for_weekly_review_test_unchecked(uuid)'
  ) is null then
    if pg_catalog.to_regprocedure(
      'public.complete_study_plan_for_weekly_review_test(uuid)'
    ) is null then
      raise exception
        'complete_study_plan_for_weekly_review_test(uuid)가 먼저 필요합니다.';
    end if;
    alter function public.complete_study_plan_for_weekly_review_test(uuid)
      rename to complete_study_plan_for_weekly_review_test_unchecked;
  end if;

  if pg_catalog.to_regprocedure(
    'public.start_shop_test_session_unchecked()'
  ) is null then
    if pg_catalog.to_regprocedure(
      'public.start_shop_test_session()'
    ) is null then
      raise exception 'start_shop_test_session()이 먼저 필요합니다.';
    end if;
    alter function public.start_shop_test_session()
      rename to start_shop_test_session_unchecked;
  end if;

  if pg_catalog.to_regprocedure(
    'public.reset_shop_test_session_unchecked(uuid)'
  ) is null then
    if pg_catalog.to_regprocedure(
      'public.reset_shop_test_session(uuid)'
    ) is null then
      raise exception 'reset_shop_test_session(uuid)가 먼저 필요합니다.';
    end if;
    alter function public.reset_shop_test_session(uuid)
      rename to reset_shop_test_session_unchecked;
  end if;
end;
$$;

revoke all on function public.reset_today_test_progress_unchecked()
from public, anon, authenticated;
revoke all on function
  public.complete_study_plan_for_weekly_review_test_unchecked(uuid)
from public, anon, authenticated;
revoke all on function public.start_shop_test_session_unchecked()
from public, anon, authenticated;
revoke all on function public.reset_shop_test_session_unchecked(uuid)
from public, anon, authenticated;

create or replace function public.reset_today_test_progress()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform public.require_test_tool_access();
  return public.reset_today_test_progress_unchecked();
end;
$$;

create or replace function
public.complete_study_plan_for_weekly_review_test(
  p_plan_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform public.require_test_tool_access();
  return public.complete_study_plan_for_weekly_review_test_unchecked(
    p_plan_id
  );
end;
$$;

create or replace function public.start_shop_test_session()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform public.require_test_tool_access();
  return public.start_shop_test_session_unchecked();
end;
$$;

create or replace function public.reset_shop_test_session(
  p_session_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform public.require_test_tool_access();
  return public.reset_shop_test_session_unchecked(p_session_id);
end;
$$;

revoke all on function public.reset_today_test_progress()
from public, anon, authenticated;
revoke all on function
  public.complete_study_plan_for_weekly_review_test(uuid)
from public, anon, authenticated;
revoke all on function public.start_shop_test_session()
from public, anon, authenticated;
revoke all on function public.reset_shop_test_session(uuid)
from public, anon, authenticated;

grant execute on function public.reset_today_test_progress()
to authenticated;
grant execute on function
  public.complete_study_plan_for_weekly_review_test(uuid)
to authenticated;
grant execute on function public.start_shop_test_session()
to authenticated;
grant execute on function public.reset_shop_test_session(uuid)
to authenticated;

commit;
