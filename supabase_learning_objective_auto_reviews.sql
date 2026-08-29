-- 자동 복습 과제가 원인 퀴즈 과제의 학습목표를 항상 상속하게 합니다.
begin;

set local lock_timeout = '10s';
set local statement_timeout = '60s';

do $$
begin
  if pg_catalog.to_regclass('public.learning_objectives') is null
     or pg_catalog.to_regclass('public.study_tasks') is null
     or pg_catalog.to_regclass('public.quizzes') is null
     or pg_catalog.to_regclass('public.quiz_attempts') is null
  then
    raise exception '037_learning_objective_quiz_links migration이 먼저 필요합니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as review_task
    left join public.quizzes as quiz
      on quiz.id = review_task.source_quiz_id
     and quiz.plan_id = review_task.plan_id
     and quiz.user_id = review_task.user_id
    left join public.study_tasks as quiz_task
      on quiz_task.id = quiz.task_id
     and quiz_task.plan_id = quiz.plan_id
     and quiz_task.user_id = quiz.user_id
     and quiz_task.task_type = 'quiz'
    left join public.quiz_attempts as attempt
      on attempt.id = review_task.source_quiz_attempt_id
     and attempt.quiz_id = quiz.id
     and attempt.user_id = review_task.user_id
    left join public.learning_objectives as objective
      on objective.id = coalesce(
        quiz.learning_objective_id,
        quiz_task.learning_objective_id
      )
     and objective.plan_id = review_task.plan_id
     and objective.user_id = review_task.user_id
    where review_task.source_type = 'weakness_review'
      and (
        quiz.id is null
        or quiz_task.id is null
        or attempt.id is null
        or objective.id is null
        or (
          quiz.learning_objective_id is not null
          and quiz.learning_objective_id
              is distinct from quiz_task.learning_objective_id
        )
      )
  ) then
    raise exception '학습목표를 안전하게 계산할 수 없는 기존 자동 복습 과제가 있습니다.';
  end if;
end;
$$;

create function public.sync_auto_review_learning_objective()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_quiz_objective_id uuid;
  v_quiz_task_objective_id uuid;
  v_learning_objective_id uuid;
begin
  if new.source_type is distinct from 'weakness_review' then
    return new;
  end if;

  select
    quiz.learning_objective_id,
    quiz_task.learning_objective_id
  into
    v_quiz_objective_id,
    v_quiz_task_objective_id
  from public.quizzes as quiz
  join public.study_tasks as quiz_task
    on quiz_task.id = quiz.task_id
   and quiz_task.plan_id = quiz.plan_id
   and quiz_task.user_id = quiz.user_id
   and quiz_task.task_type = 'quiz'
  join public.quiz_attempts as attempt
    on attempt.id = new.source_quiz_attempt_id
   and attempt.quiz_id = quiz.id
   and attempt.user_id = quiz.user_id
  where quiz.id = new.source_quiz_id
    and quiz.plan_id = new.plan_id
    and quiz.user_id = new.user_id;

  if not found then
    raise exception '자동 복습과 같은 사용자·계획의 원인 퀴즈 응시를 찾을 수 없습니다.';
  end if;

  if v_quiz_objective_id is not null
     and v_quiz_objective_id is distinct from v_quiz_task_objective_id
  then
    raise exception '원인 퀴즈와 퀴즈 과제의 학습목표가 일치하지 않습니다.';
  end if;

  v_learning_objective_id := coalesce(
    v_quiz_objective_id,
    v_quiz_task_objective_id
  );

  if v_learning_objective_id is null then
    raise exception '자동 복습에 상속할 퀴즈 학습목표가 없습니다.';
  end if;

  if not exists (
    select 1
    from public.learning_objectives as objective
    where objective.id = v_learning_objective_id
      and objective.plan_id = new.plan_id
      and objective.user_id = new.user_id
  ) then
    raise exception '자동 복습과 같은 사용자·계획의 학습목표를 찾을 수 없습니다.';
  end if;

  -- 클라이언트나 이전 함수의 값을 신뢰하지 않고 원인 관계에서 다시 계산합니다.
  new.learning_objective_id := v_learning_objective_id;
  return new;
end;
$$;

revoke all on function public.sync_auto_review_learning_objective()
from public, anon, authenticated;

drop trigger if exists study_tasks_sync_auto_review_objective_insert
on public.study_tasks;

create trigger study_tasks_sync_auto_review_objective_insert
before insert
on public.study_tasks
for each row
execute function public.sync_auto_review_learning_objective();

drop trigger if exists study_tasks_sync_auto_review_objective_update
on public.study_tasks;

create trigger study_tasks_sync_auto_review_objective_update
before update of
  source_type,
  source_quiz_id,
  source_quiz_attempt_id,
  plan_id,
  user_id
on public.study_tasks
for each row
execute function public.sync_auto_review_learning_objective();

-- 기존 자동 복습도 원인 퀴즈 또는 퀴즈 과제의 목표로 정규화합니다.
update public.study_tasks as review_task
set learning_objective_id = coalesce(
  quiz.learning_objective_id,
  quiz_task.learning_objective_id
)
from public.quizzes as quiz
join public.study_tasks as quiz_task
  on quiz_task.id = quiz.task_id
 and quiz_task.plan_id = quiz.plan_id
 and quiz_task.user_id = quiz.user_id
 and quiz_task.task_type = 'quiz'
join public.quiz_attempts as attempt
  on attempt.quiz_id = quiz.id
 and attempt.user_id = quiz.user_id
where review_task.source_type = 'weakness_review'
  and quiz.id = review_task.source_quiz_id
  and quiz.plan_id = review_task.plan_id
  and quiz.user_id = review_task.user_id
  and attempt.id = review_task.source_quiz_attempt_id;

comment on function public.sync_auto_review_learning_objective() is
  '자동 복습 목표를 소유권이 확인된 원인 퀴즈 또는 퀴즈 과제에서 계산';

commit;
