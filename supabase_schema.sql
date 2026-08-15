-- AI 학습 코치: Supabase PostgreSQL 초기 스키마
-- 대상: 대학생 자기주도학습 MVP
-- 작성 기준: 2026-08-14

begin;

-- ---------------------------------------------------------------------------
-- 공통 함수
-- ---------------------------------------------------------------------------

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. 사용자 프로필
-- 인증 정보는 Supabase Auth의 auth.users가 관리한다.
-- ---------------------------------------------------------------------------

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  nickname text not null check (char_length(btrim(nickname)) between 1 and 30),
  total_exp integer not null default 0 check (total_exp >= 0),
  level integer not null default 1 check (level >= 1),
  current_streak integer not null default 0 check (current_streak >= 0),
  longest_streak integer not null default 0 check (longest_streak >= 0),
  last_activity_date date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- 2. 학습계획
-- 학습계획 하나는 과목 또는 학습목표 하나를 담당한다.
-- ---------------------------------------------------------------------------

create table public.study_plans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  title text not null check (char_length(btrim(title)) between 1 and 100),
  course_name text not null check (char_length(btrim(course_name)) between 1 and 100),
  goal text not null check (char_length(btrim(goal)) between 1 and 1000),
  current_level smallint not null check (current_level between 1 and 10),
  start_date date not null,
  target_date date not null,
  available_schedule jsonb not null default '{}'::jsonb
    check (jsonb_typeof(available_schedule) = 'object'),
  weekly_overview jsonb not null default '[]'::jsonb
    check (jsonb_typeof(weekly_overview) = 'array'),
  status text not null default 'active'
    check (status in ('active', 'completed', 'archived')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint study_plans_valid_date_range check (target_date >= start_date),
  constraint study_plans_id_user_unique unique (id, user_id)
);

-- ---------------------------------------------------------------------------
-- 3. 사용자가 제공한 원본 학습자료
-- MVP는 text를 사용하고, 추후 PDF 파일과 추출 텍스트를 함께 저장한다.
-- ---------------------------------------------------------------------------

create table public.learning_materials (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  plan_id uuid not null,
  title text not null check (char_length(btrim(title)) between 1 and 200),
  material_type text not null default 'text'
    check (material_type in ('text', 'pdf')),
  content_text text,
  storage_path text,
  created_at timestamptz not null default now(),
  constraint learning_materials_plan_owner_fk
    foreign key (plan_id, user_id)
    references public.study_plans(id, user_id)
    on delete cascade,
  constraint learning_materials_text_content_check
    check (material_type <> 'text' or content_text is not null)
);

-- ---------------------------------------------------------------------------
-- 4. 7일 단위 상세 학습과제
-- ---------------------------------------------------------------------------

create table public.study_tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  plan_id uuid not null,
  scheduled_date date not null,
  title text not null check (char_length(btrim(title)) between 1 and 200),
  description text not null default '',
  task_type text not null check (task_type in ('learn', 'review', 'quiz')),
  estimated_minutes smallint not null
    check (estimated_minutes between 1 and 1440),
  status text not null default 'pending'
    check (status in ('pending', 'completed', 'skipped')),
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint study_tasks_plan_owner_fk
    foreign key (plan_id, user_id)
    references public.study_plans(id, user_id)
    on delete cascade,
  constraint study_tasks_completion_check
    check (status <> 'completed' or completed_at is not null)
);

-- ---------------------------------------------------------------------------
-- 5. AI가 생성한 요약·복습자료
-- ---------------------------------------------------------------------------

create table public.review_materials (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  plan_id uuid not null,
  source_material_id uuid references public.learning_materials(id) on delete set null,
  title text not null check (char_length(btrim(title)) between 1 and 200),
  content_markdown text not null,
  created_at timestamptz not null default now(),
  constraint review_materials_plan_owner_fk
    foreign key (plan_id, user_id)
    references public.study_plans(id, user_id)
    on delete cascade
);

-- ---------------------------------------------------------------------------
-- 6. 객관식 퀴즈
-- questions는 문제, 선택지 4개, 정답 번호, 해설을 담는 JSON 배열이다.
-- ---------------------------------------------------------------------------

create table public.quizzes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  plan_id uuid not null,
  task_id uuid references public.study_tasks(id) on delete set null,
  title text not null check (char_length(btrim(title)) between 1 and 200),
  questions jsonb not null check (jsonb_typeof(questions) = 'array'),
  question_count smallint not null default 5
    check (question_count between 1 and 20),
  created_at timestamptz not null default now(),
  constraint quizzes_plan_owner_fk
    foreign key (plan_id, user_id)
    references public.study_plans(id, user_id)
    on delete cascade,
  constraint quizzes_id_user_unique unique (id, user_id)
);

-- ---------------------------------------------------------------------------
-- 7. 퀴즈 응시 기록
-- 재응시를 허용하며 가장 최근 submitted_at의 결과를 계획 조정에 사용한다.
-- ---------------------------------------------------------------------------

create table public.quiz_attempts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  quiz_id uuid not null,
  attempt_number integer not null check (attempt_number >= 1),
  answers jsonb not null check (jsonb_typeof(answers) = 'array'),
  correct_count smallint not null check (correct_count >= 0),
  total_questions smallint not null check (total_questions >= 1),
  score smallint not null check (score between 0 and 100),
  exp_awarded integer not null default 0 check (exp_awarded >= 0),
  submitted_at timestamptz not null default now(),
  constraint quiz_attempts_quiz_owner_fk
    foreign key (quiz_id, user_id)
    references public.quizzes(id, user_id)
    on delete cascade,
  constraint quiz_attempts_score_count_check
    check (correct_count <= total_questions),
  constraint quiz_attempts_number_unique
    unique (user_id, quiz_id, attempt_number)
);

-- ---------------------------------------------------------------------------
-- 8. EXP 지급 원장
-- source_key 중복 방지로 동일 행동에 대한 EXP 재지급을 막는다.
-- ---------------------------------------------------------------------------

create table public.exp_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  event_type text not null check (
    event_type in (
      'task_completion',
      'quiz_submission',
      'quiz_score_bonus',
      'daily_completion'
    )
  ),
  source_key text not null check (char_length(btrim(source_key)) between 1 and 200),
  amount integer not null check (amount > 0),
  created_at timestamptz not null default now(),
  constraint exp_events_source_unique unique (user_id, source_key)
);

-- ---------------------------------------------------------------------------
-- 9. 날짜별 학습 기록
-- activity_date는 앱에서 Asia/Seoul 기준 날짜로 계산해 전달한다.
-- ---------------------------------------------------------------------------

create table public.learning_activity (
  user_id uuid not null references public.profiles(id) on delete cascade,
  activity_date date not null,
  completed_task_count integer not null default 0
    check (completed_task_count >= 0),
  quiz_submission_count integer not null default 0
    check (quiz_submission_count >= 0),
  earned_exp integer not null default 0 check (earned_exp >= 0),
  all_tasks_completed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, activity_date)
);

-- ---------------------------------------------------------------------------
-- 조회 성능을 위한 인덱스
-- ---------------------------------------------------------------------------

create index study_plans_user_status_idx
  on public.study_plans(user_id, status);

create index learning_materials_plan_created_idx
  on public.learning_materials(plan_id, created_at desc);

create index study_tasks_plan_date_status_idx
  on public.study_tasks(plan_id, scheduled_date, status);

create index review_materials_plan_created_idx
  on public.review_materials(plan_id, created_at desc);

create index quizzes_plan_created_idx
  on public.quizzes(plan_id, created_at desc);

create index quiz_attempts_quiz_submitted_idx
  on public.quiz_attempts(quiz_id, submitted_at desc);

create index exp_events_user_created_idx
  on public.exp_events(user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- updated_at 자동 갱신 트리거
-- ---------------------------------------------------------------------------

create trigger profiles_set_updated_at
before update on public.profiles
for each row execute function public.set_updated_at();

create trigger study_plans_set_updated_at
before update on public.study_plans
for each row execute function public.set_updated_at();

create trigger study_tasks_set_updated_at
before update on public.study_tasks
for each row execute function public.set_updated_at();

create trigger learning_activity_set_updated_at
before update on public.learning_activity
for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 신규 회원 프로필 자동 생성
-- 회원가입 시 user_metadata에 nickname을 전달한다.
-- ---------------------------------------------------------------------------

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, nickname)
  values (
    new.id,
    coalesce(nullif(btrim(new.raw_user_meta_data ->> 'nickname'), ''), '학습자')
  )
  on conflict (id) do nothing;

  return new;
end;
$$;

create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------

alter table public.profiles enable row level security;
alter table public.study_plans enable row level security;
alter table public.learning_materials enable row level security;
alter table public.study_tasks enable row level security;
alter table public.review_materials enable row level security;
alter table public.quizzes enable row level security;
alter table public.quiz_attempts enable row level security;
alter table public.exp_events enable row level security;
alter table public.learning_activity enable row level security;

create policy "profiles_select_own"
on public.profiles
for select
to authenticated
using ((select auth.uid()) = id);

create policy "profiles_update_own"
on public.profiles
for update
to authenticated
using ((select auth.uid()) = id)
with check ((select auth.uid()) = id);

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'study_plans',
    'learning_materials',
    'study_tasks',
    'review_materials',
    'quizzes'
  ]
  loop
    execute format(
      'create policy "select_own" on public.%I for select to authenticated using ((select auth.uid()) = user_id)',
      table_name
    );
    execute format(
      'create policy "insert_own" on public.%I for insert to authenticated with check ((select auth.uid()) = user_id)',
      table_name
    );
    execute format(
      'create policy "update_own" on public.%I for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id)',
      table_name
    );
    execute format(
      'create policy "delete_own" on public.%I for delete to authenticated using ((select auth.uid()) = user_id)',
      table_name
    );
  end loop;
end;
$$;

create policy "quiz_attempts_select_own"
on public.quiz_attempts
for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "quiz_attempts_insert_own"
on public.quiz_attempts
for insert
to authenticated
with check ((select auth.uid()) = user_id);

create policy "exp_events_select_own"
on public.exp_events
for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "learning_activity_select_own"
on public.learning_activity
for select
to authenticated
using ((select auth.uid()) = user_id);

-- ---------------------------------------------------------------------------
-- API 권한
-- EXP와 날짜별 활동 기록은 이후 보상용 DB 함수만 변경하도록 읽기 전용으로 둔다.
-- ---------------------------------------------------------------------------

revoke all on public.profiles from anon, authenticated;
revoke all on public.study_plans from anon, authenticated;
revoke all on public.learning_materials from anon, authenticated;
revoke all on public.study_tasks from anon, authenticated;
revoke all on public.review_materials from anon, authenticated;
revoke all on public.quizzes from anon, authenticated;
revoke all on public.quiz_attempts from anon, authenticated;
revoke all on public.exp_events from anon, authenticated;
revoke all on public.learning_activity from anon, authenticated;

grant select on public.profiles to authenticated;
grant update (nickname) on public.profiles to authenticated;

grant select, insert, update, delete
on public.study_plans,
   public.learning_materials,
   public.study_tasks,
   public.review_materials,
   public.quizzes
to authenticated;

grant select, insert on public.quiz_attempts to authenticated;
grant select on public.exp_events to authenticated;
grant select on public.learning_activity to authenticated;

commit;
