begin;

-- 사용자별·과목별 개념 사전입니다.
-- concept_key는 AI가 기존 개념을 재사용할 때 사용하는 안정적인 키입니다.
create table public.learning_concepts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null
    references public.profiles(id) on delete cascade,
  course_key text not null
    check (char_length(btrim(course_key)) between 1 and 120),
  course_name text not null
    check (char_length(btrim(course_name)) between 1 and 100),
  concept_key text not null
    check (
      char_length(concept_key) between 1 and 100
      and concept_key ~ '^[a-z0-9]+(_[a-z0-9]+)*$'
    ),
  canonical_name text not null
    check (char_length(btrim(canonical_name)) between 1 and 100),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint learning_concepts_id_user_unique
    unique (id, user_id),
  constraint learning_concepts_id_user_course_unique
    unique (id, user_id, course_key),
  constraint learning_concepts_user_course_key_unique
    unique (user_id, course_key, concept_key)
);


-- 같은 개념을 가리키는 여러 표현을 정규 개념에 연결합니다.
create table public.concept_aliases (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  concept_id uuid not null,
  course_key text not null
    check (char_length(btrim(course_key)) between 1 and 120),
  alias_name text not null
    check (char_length(btrim(alias_name)) between 1 and 100),
  normalized_alias text not null
    check (char_length(btrim(normalized_alias)) between 1 and 120),
  created_at timestamptz not null default now(),
  constraint concept_aliases_concept_owner_course_fk
    foreign key (concept_id, user_id, course_key)
    references public.learning_concepts(id, user_id, course_key)
    on delete cascade,
  constraint concept_aliases_user_course_alias_unique
    unique (user_id, course_key, normalized_alias)
);


-- 기존 응시 기록에는 자동 키를 부여해 현재 제출 RPC와 호환합니다.
-- 이후 RPC는 클라이언트가 보낸 키를 사용해 동일 제출을 식별합니다.
alter table public.quiz_attempts
add column submission_key uuid
not null default gen_random_uuid();

alter table public.quiz_attempts
add constraint quiz_attempts_submission_key_unique
unique (user_id, quiz_id, submission_key);

alter table public.quiz_attempts
add constraint quiz_attempts_id_user_unique
unique (id, user_id);

alter table public.quiz_attempts
add constraint quiz_attempts_id_quiz_user_unique
unique (id, quiz_id, user_id);

alter table public.quizzes
add constraint quizzes_id_plan_user_unique
unique (id, plan_id, user_id);


-- 사용자별 개념 숙련도의 현재값입니다.
create table public.concept_mastery (
  user_id uuid not null,
  concept_id uuid not null,
  mastery_score smallint not null default 50
    check (mastery_score between 0 and 100),
  correct_count integer not null default 0
    check (correct_count >= 0),
  incorrect_count integer not null default 0
    check (incorrect_count >= 0),
  consecutive_incorrect_count integer not null default 0
    check (consecutive_incorrect_count >= 0),
  last_answer_correct boolean,
  last_attempt_id uuid,
  last_assessed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, concept_id),
  constraint concept_mastery_concept_owner_fk
    foreign key (concept_id, user_id)
    references public.learning_concepts(id, user_id)
    on delete cascade,
  constraint concept_mastery_last_attempt_owner_fk
    foreign key (last_attempt_id, user_id)
    references public.quiz_attempts(id, user_id)
    on delete set null (last_attempt_id)
);


-- 문항별 숙련도 변경 원장입니다.
-- attempt와 question_index의 유일 제약이 중복 갱신을 차단합니다.
create table public.concept_mastery_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  concept_id uuid not null,
  quiz_id uuid not null,
  quiz_attempt_id uuid not null,
  question_index smallint not null
    check (question_index between 0 and 19),
  is_correct boolean not null,
  score_before smallint not null
    check (score_before between 0 and 100),
  score_delta smallint not null
    check (score_delta between -100 and 100),
  score_after smallint not null
    check (score_after between 0 and 100),
  created_at timestamptz not null default now(),
  constraint concept_mastery_events_score_change_check
    check (score_after = score_before + score_delta),
  constraint concept_mastery_events_concept_owner_fk
    foreign key (concept_id, user_id)
    references public.learning_concepts(id, user_id)
    on delete cascade,
  constraint concept_mastery_events_attempt_quiz_owner_fk
    foreign key (quiz_attempt_id, quiz_id, user_id)
    references public.quiz_attempts(id, quiz_id, user_id)
    on delete cascade,
  constraint concept_mastery_events_attempt_question_unique
    unique (quiz_attempt_id, question_index)
);


-- 자동 복습 과제가 어떤 개념과 응시 결과에서 생성됐는지 기록합니다.
alter table public.study_tasks
add column source_type text not null default 'weekly_plan'
check (source_type in ('weekly_plan', 'weakness_review'));

alter table public.study_tasks
add column concept_id uuid;

alter table public.study_tasks
add column source_quiz_id uuid;

alter table public.study_tasks
add column source_quiz_attempt_id uuid;

alter table public.study_tasks
add constraint study_tasks_concept_owner_fk
foreign key (concept_id, user_id)
references public.learning_concepts(id, user_id)
on delete cascade;

alter table public.study_tasks
add constraint study_tasks_source_quiz_plan_owner_fk
foreign key (source_quiz_id, plan_id, user_id)
references public.quizzes(id, plan_id, user_id)
on delete cascade;

alter table public.study_tasks
add constraint study_tasks_source_attempt_quiz_owner_fk
foreign key (
  source_quiz_attempt_id,
  source_quiz_id,
  user_id
)
references public.quiz_attempts(id, quiz_id, user_id)
on delete cascade;

alter table public.study_tasks
add constraint study_tasks_source_metadata_check
check (
  (
    source_type = 'weekly_plan'
    and concept_id is null
    and source_quiz_id is null
    and source_quiz_attempt_id is null
  )
  or
  (
    source_type = 'weakness_review'
    and task_type = 'review'
    and concept_id is not null
    and source_quiz_id is not null
    and source_quiz_attempt_id is not null
  )
);


-- 같은 계획·개념에 미완료 자동 복습 과제를 하나만 허용합니다.
create unique index study_tasks_pending_weakness_review_unique
on public.study_tasks(user_id, plan_id, concept_id)
where source_type = 'weakness_review'
  and status = 'pending';

create index learning_concepts_user_course_idx
on public.learning_concepts(user_id, course_key);

create index concept_aliases_concept_idx
on public.concept_aliases(concept_id);

create index concept_mastery_concept_idx
on public.concept_mastery(concept_id, user_id);

create index concept_mastery_last_attempt_idx
on public.concept_mastery(last_attempt_id, user_id)
where last_attempt_id is not null;

create index concept_mastery_user_score_idx
on public.concept_mastery(user_id, mastery_score);

create index concept_mastery_events_concept_idx
on public.concept_mastery_events(concept_id, user_id);

create index concept_mastery_events_user_concept_created_idx
on public.concept_mastery_events(
  user_id,
  concept_id,
  created_at desc
);

create index study_tasks_concept_idx
on public.study_tasks(concept_id, user_id)
where concept_id is not null;

create index study_tasks_source_quiz_idx
on public.study_tasks(source_quiz_id, plan_id, user_id)
where source_quiz_id is not null;

create index study_tasks_source_attempt_idx
on public.study_tasks(
  source_quiz_attempt_id,
  source_quiz_id,
  user_id
)
where source_quiz_attempt_id is not null;


create trigger learning_concepts_set_updated_at
before update on public.learning_concepts
for each row execute function public.set_updated_at();

create trigger concept_mastery_set_updated_at
before update on public.concept_mastery
for each row execute function public.set_updated_at();


-- 새 사용자 소유 테이블은 생성 즉시 RLS를 활성화합니다.
alter table public.learning_concepts enable row level security;
alter table public.concept_aliases enable row level security;
alter table public.concept_mastery enable row level security;
alter table public.concept_mastery_events enable row level security;

create policy "learning_concepts_select_own"
on public.learning_concepts
for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "concept_aliases_select_own"
on public.concept_aliases
for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "concept_mastery_select_own"
on public.concept_mastery
for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "concept_mastery_events_select_own"
on public.concept_mastery_events
for select
to authenticated
using ((select auth.uid()) = user_id);

revoke all on public.learning_concepts from anon, authenticated;
revoke all on public.concept_aliases from anon, authenticated;
revoke all on public.concept_mastery from anon, authenticated;
revoke all on public.concept_mastery_events from anon, authenticated;

grant select on public.learning_concepts to authenticated;
grant select on public.concept_aliases to authenticated;
grant select on public.concept_mastery to authenticated;
grant select on public.concept_mastery_events to authenticated;

commit;
