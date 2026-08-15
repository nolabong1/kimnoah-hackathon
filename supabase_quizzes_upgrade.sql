begin;

-- 기존 퀴즈 행을 삭제하거나 임의로 변경하지 않습니다.
-- 새 제약조건과 충돌하는 데이터가 있으면 전체 작업을 중단합니다.
do $$
begin
  if exists (
    select 1
    from public.quizzes
    where task_id is null
  ) then
    raise exception
      'quizzes.task_id가 비어 있는 기존 행이 있습니다.';
  end if;

  if exists (
    select 1
    from public.quizzes as quiz
    left join public.study_tasks as task
      on task.id = quiz.task_id
     and task.plan_id = quiz.plan_id
     and task.user_id = quiz.user_id
    where task.id is null
  ) then
    raise exception
      '과제, 계획, 사용자가 일치하지 않는 기존 퀴즈가 있습니다.';
  end if;

  if exists (
    select task_id
    from public.quizzes
    group by task_id
    having count(*) > 1
  ) then
    raise exception
      '같은 과제에 여러 퀴즈가 연결된 기존 행이 있습니다.';
  end if;

  if exists (
    select 1
    from public.quizzes
    where question_count <> jsonb_array_length(questions)
  ) then
    raise exception
      'question_count와 실제 문항 수가 다른 기존 퀴즈가 있습니다.';
  end if;
end;
$$;


-- 기존 단일 과제 외래 키를 복합 소유권 외래 키로 교체합니다.
alter table public.quizzes
drop constraint if exists quizzes_task_id_fkey;

alter table public.quizzes
alter column task_id set not null;

alter table public.quizzes
add constraint quizzes_task_owner_fk
foreign key (task_id, plan_id, user_id)
references public.study_tasks(id, plan_id, user_id)
on delete cascade;


-- 현재 MVP 정책은 과제당 퀴즈 하나이며 재생성 시 기존 행을 갱신합니다.
alter table public.quizzes
add constraint quizzes_task_unique
unique (task_id);

alter table public.quizzes
add constraint quizzes_question_count_matches
check (question_count = jsonb_array_length(questions));


-- 퀴즈 재생성 시 마지막 갱신 시각을 기록합니다.
alter table public.quizzes
add column updated_at timestamptz
not null default now();

create index quizzes_user_plan_idx
on public.quizzes(user_id, plan_id);

create or replace function
public.set_quiz_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create trigger quizzes_set_updated_at
before update
on public.quizzes
for each row
execute function public.set_quiz_updated_at();

commit;
