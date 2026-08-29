-- 038_learning_objective_auto_reviews 적용 결과를 읽기 전용으로 검증합니다.
begin;

set transaction read only;

do $$
declare
  v_function regprocedure := pg_catalog.to_regprocedure(
    'public.sync_auto_review_learning_objective()'
  );
  v_definition text;
begin
  if v_function is null then
    raise exception '자동 복습 학습목표 동기화 함수가 없습니다.';
  end if;

  if pg_catalog.has_function_privilege(
       'authenticated', v_function, 'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'anon', v_function, 'EXECUTE'
     )
  then
    raise exception '자동 복습 학습목표 동기화 함수가 클라이언트에 공개돼 있습니다.';
  end if;

  select pg_catalog.pg_get_functiondef(v_function)
  into v_definition;

  if position('security definer' in lower(v_definition)) = 0
     or position('coalesce(' in lower(v_definition)) = 0
     or position('quiz.learning_objective_id' in v_definition) = 0
     or position('quiz_task.learning_objective_id' in v_definition) = 0
     or position('v_quiz_objective_id is distinct from v_quiz_task_objective_id' in v_definition) = 0
     or position('attempt.id = new.source_quiz_attempt_id' in v_definition) = 0
  then
    raise exception '자동 복습 목표 계산 함수의 소유권·상속 경계가 올바르지 않습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    cross join lateral pg_catalog.unnest(procedure.proconfig) as config(value)
    where procedure.oid = v_function
      and procedure.prosecdef
      and config.value in ('search_path=', 'search_path=""')
  ) then
    raise exception '자동 복습 목표 계산 함수의 search_path가 안전하지 않습니다.';
  end if;

  if (
    select count(*)
    from pg_catalog.pg_trigger as trigger
    join pg_catalog.pg_class as relation
      on relation.oid = trigger.tgrelid
    join pg_catalog.pg_namespace as namespace
      on namespace.oid = relation.relnamespace
    where namespace.nspname = 'public'
      and relation.relname = 'study_tasks'
      and trigger.tgname in (
        'study_tasks_sync_auto_review_objective_insert',
        'study_tasks_sync_auto_review_objective_update'
      )
      and not trigger.tgisinternal
      and trigger.tgenabled <> 'D'
  ) <> 2 then
    raise exception '자동 복습 목표 동기화 trigger 두 개가 올바르게 연결되지 않았습니다.';
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
    where review_task.source_type = 'weakness_review'
      and (
        attempt.id is null
        or review_task.learning_objective_id is null
        or review_task.learning_objective_id is distinct from coalesce(
          quiz.learning_objective_id,
          quiz_task.learning_objective_id
        )
      )
  ) then
    raise exception '자동 복습 과제와 원인 퀴즈의 학습목표가 일치하지 않습니다.';
  end if;
end;
$$;

select 'learning objective auto reviews validation: success'
as validation_result;

rollback;
