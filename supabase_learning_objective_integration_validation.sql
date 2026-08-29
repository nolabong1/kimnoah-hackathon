-- 계획 목표부터 자동 복습까지 전체 연결을 읽기 전용으로 최종 확인합니다.
begin;

set transaction read only;

do $$
begin
  if exists (
    select 1
    from public.study_tasks as task
    where task.source_type = 'weekly_plan'
      and task.learning_objective_id is null
  ) then
    raise exception '학습목표가 없는 주간 계획 과제가 있습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    left join public.learning_objectives as objective
      on objective.id = task.learning_objective_id
     and objective.plan_id = task.plan_id
     and objective.user_id = task.user_id
    where task.learning_objective_id is not null
      and objective.id is null
  ) then
    raise exception '과제와 학습목표의 사용자·계획 소유권이 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.review_materials as material
    join public.study_tasks as task
      on task.id = material.task_id
     and task.plan_id = material.plan_id
     and task.user_id = material.user_id
    where material.learning_objective_id
          is distinct from task.learning_objective_id
  ) then
    raise exception '과제 기반 AI 자료와 과제의 학습목표가 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.review_materials as material
    join public.learning_materials as source
      on source.id = material.source_material_id
     and source.plan_id = material.plan_id
     and source.user_id = material.user_id
    where material.learning_objective_id
          is distinct from source.learning_objective_id
  ) then
    raise exception '원본 기반 AI 자료와 원본의 학습목표가 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.quizzes as quiz
    join public.study_tasks as task
      on task.id = quiz.task_id
     and task.plan_id = quiz.plan_id
     and task.user_id = quiz.user_id
    where quiz.learning_objective_id is not null
      and quiz.learning_objective_id
          is distinct from task.learning_objective_id
  ) then
    raise exception '퀴즈와 퀴즈 과제의 학습목표가 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.quizzes as quiz
    join public.learning_materials as material
      on material.id = quiz.reference_learning_material_id
     and material.plan_id = quiz.plan_id
     and material.user_id = quiz.user_id
    where quiz.learning_objective_id
          is distinct from material.learning_objective_id
  ) then
    raise exception '퀴즈와 선택 원본의 학습목표가 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.quizzes as quiz
    join public.review_materials as material
      on material.id = quiz.reference_review_material_id
     and material.plan_id = quiz.plan_id
     and material.user_id = quiz.user_id
    where quiz.learning_objective_id
          is distinct from material.learning_objective_id
  ) then
    raise exception '퀴즈와 선택 AI 자료의 학습목표가 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as review_task
    join public.quizzes as quiz
      on quiz.id = review_task.source_quiz_id
     and quiz.plan_id = review_task.plan_id
     and quiz.user_id = review_task.user_id
    join public.study_tasks as quiz_task
      on quiz_task.id = quiz.task_id
     and quiz_task.plan_id = quiz.plan_id
     and quiz_task.user_id = quiz.user_id
     and quiz_task.task_type = 'quiz'
    where review_task.source_type = 'weakness_review'
      and review_task.learning_objective_id is distinct from coalesce(
        quiz.learning_objective_id,
        quiz_task.learning_objective_id
      )
  ) then
    raise exception '자동 복습과 원인 퀴즈 과제의 학습목표가 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.learning_objectives as objective
    where objective.origin = 'generated'
      and not exists (
        select 1
        from public.study_tasks as task
        where task.user_id = objective.user_id
          and task.plan_id = objective.plan_id
          and task.learning_objective_id = objective.id
      )
  ) then
    raise exception '연결된 과제가 없는 생성 학습목표가 있습니다.';
  end if;
end;
$$;

select 'learning objective integration validation: success'
as validation_result;

rollback;
