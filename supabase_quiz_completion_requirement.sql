begin;

create or replace function
public.enforce_quiz_completion_requirement()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
begin
  if new.status = 'completed'
     and old.status is distinct from new.status
     and new.task_type = 'quiz'
  then
    if v_user_id is null then
      raise exception '로그인이 필요합니다.';
    end if;

    if new.user_id <> v_user_id then
      raise exception '본인의 과제만 완료할 수 있습니다.';
    end if;

    perform 1
    from public.quizzes as quiz
    where quiz.task_id = new.id
      and quiz.user_id = v_user_id
    for share;

    if not found then
      raise exception
        '퀴즈를 생성하고 모든 문항을 맞힌 후 완료해주세요.';
    end if;

    if not exists (
      select 1
      from public.quizzes as quiz
      join public.quiz_attempts as attempt
        on attempt.quiz_id = quiz.id
       and attempt.user_id = quiz.user_id
       and attempt.quiz_updated_at = quiz.updated_at
      where quiz.task_id = new.id
        and quiz.user_id = v_user_id
        and attempt.correct_count = quiz.question_count
        and attempt.total_questions = quiz.question_count
    ) then
      raise exception
        '현재 퀴즈의 모든 문항을 맞힌 후 완료해주세요.';
    end if;
  end if;

  return new;
end;
$$;

drop trigger if exists
study_tasks_enforce_quiz_completion
on public.study_tasks;

create trigger study_tasks_enforce_quiz_completion
before update of status
on public.study_tasks
for each row
execute function
public.enforce_quiz_completion_requirement();

revoke all
on function public.enforce_quiz_completion_requirement()
from public, anon, authenticated;


commit;
