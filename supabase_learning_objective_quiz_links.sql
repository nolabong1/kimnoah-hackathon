-- 퀴즈를 과제 학습목표와 선택 참고자료에 원자적으로 연결합니다.
begin;

set local lock_timeout = '10s';
set local statement_timeout = '60s';

do $$
begin
  if pg_catalog.to_regprocedure(
    'public.save_quiz_with_concepts(uuid,uuid,text,text,text,jsonb,jsonb)'
  ) is null then
    raise exception '기존 7인자 퀴즈 저장 RPC가 먼저 필요합니다.';
  end if;

  if pg_catalog.to_regclass('public.learning_objectives') is null
     or pg_catalog.to_regclass('public.learning_materials') is null
     or pg_catalog.to_regclass('public.review_materials') is null
     or pg_catalog.to_regclass('public.quizzes') is null
  then
    raise exception '036_learning_objective_material_links migration이 먼저 필요합니다.';
  end if;

  if pg_catalog.to_regprocedure(
    'public.save_quiz_with_concepts(uuid,uuid,text,text,text,jsonb,jsonb,uuid,uuid)'
  ) is not null then
    raise exception '새 9인자 퀴즈 저장 RPC가 이미 존재합니다.';
  end if;
end;
$$;

create function public.save_quiz_with_concepts(
  p_plan_id uuid,
  p_task_id uuid,
  p_course_key text,
  p_course_name text,
  p_title text,
  p_questions jsonb,
  p_concepts jsonb,
  p_reference_learning_material_id uuid,
  p_reference_review_material_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_task_objective_id uuid;
  v_reference_objective_id uuid;
  v_objective public.learning_objectives%rowtype;
  v_saved_quiz jsonb;
  v_quiz_id uuid;
  v_quiz public.quizzes%rowtype;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  if p_reference_learning_material_id is not null
     and p_reference_review_material_id is not null
  then
    raise exception '퀴즈 참고자료는 하나만 선택할 수 있습니다.';
  end if;

  select task.learning_objective_id
  into v_task_objective_id
  from public.study_tasks as task
  join public.study_plans as plan
    on plan.id = task.plan_id
   and plan.user_id = task.user_id
  where task.id = p_task_id
    and task.plan_id = p_plan_id
    and task.user_id = v_user_id
    and task.task_type = 'quiz'
  for update of task, plan;

  if not found then
    raise exception '소유한 학습계획의 퀴즈 과제를 찾을 수 없습니다.';
  end if;

  if v_task_objective_id is null then
    raise exception '퀴즈 과제에 연결된 학습목표가 없습니다.';
  end if;

  select objective.*
  into v_objective
  from public.learning_objectives as objective
  where objective.id = v_task_objective_id
    and objective.plan_id = p_plan_id
    and objective.user_id = v_user_id
  for key share;

  if not found then
    raise exception '퀴즈 과제와 같은 사용자·계획의 학습목표를 찾을 수 없습니다.';
  end if;

  if p_reference_learning_material_id is not null then
    select material.learning_objective_id
    into v_reference_objective_id
    from public.learning_materials as material
    where material.id = p_reference_learning_material_id
      and material.plan_id = p_plan_id
      and material.user_id = v_user_id
    for key share;

    if not found then
      raise exception '소유한 계획의 원본 참고자료를 찾을 수 없습니다.';
    end if;
  elsif p_reference_review_material_id is not null then
    select material.learning_objective_id
    into v_reference_objective_id
    from public.review_materials as material
    where material.id = p_reference_review_material_id
      and material.plan_id = p_plan_id
      and material.user_id = v_user_id
    for key share;

    if not found then
      raise exception '소유한 계획의 AI 참고자료를 찾을 수 없습니다.';
    end if;
  end if;

  if (
       p_reference_learning_material_id is not null
       or p_reference_review_material_id is not null
     )
     and v_reference_objective_id is distinct from v_task_objective_id
  then
    raise exception '퀴즈와 참고자료의 학습목표가 일치하지 않습니다.';
  end if;

  -- 개념 사전과 문항 저장은 검증된 기존 구현을 같은 트랜잭션에서 재사용합니다.
  v_saved_quiz := public.save_quiz_with_concepts(
    p_plan_id,
    p_task_id,
    p_course_key,
    p_course_name,
    p_title,
    p_questions,
    p_concepts
  );

  begin
    v_quiz_id := (v_saved_quiz ->> 'id')::uuid;
  exception
    when others then
      raise exception '기존 퀴즈 저장 RPC 응답의 ID 형식이 올바르지 않습니다.';
  end;

  update public.quizzes as quiz
  set
    learning_objective_id = v_task_objective_id,
    objective_snapshot = case
      when v_objective.origin = 'generated'
      then pg_catalog.jsonb_build_object(
        'objective_key', v_objective.objective_key,
        'title', v_objective.title,
        'description', v_objective.description,
        'target_depth', v_objective.target_depth,
        'evidence_requirements', v_objective.evidence_requirements
      )
      else null
    end,
    objective_contract_hash = case
      when v_objective.origin = 'generated'
      then v_objective.contract_hash
      else null
    end,
    reference_learning_material_id = p_reference_learning_material_id,
    reference_review_material_id = p_reference_review_material_id
  where quiz.id = v_quiz_id
    and quiz.task_id = p_task_id
    and quiz.plan_id = p_plan_id
    and quiz.user_id = v_user_id
  returning * into v_quiz;

  if not found then
    raise exception '저장된 퀴즈의 사용자·계획·과제 연결이 올바르지 않습니다.';
  end if;

  return pg_catalog.to_jsonb(v_quiz);
end;
$$;

-- 이전 공개 함수는 새 목표·자료 검증을 우회할 수 없도록 내부 전용으로 닫습니다.
revoke all on function public.save_quiz_with_concepts(
  uuid,
  uuid,
  text,
  text,
  text,
  jsonb,
  jsonb
) from public, anon, authenticated;

revoke all on function public.save_quiz_with_concepts(
  uuid,
  uuid,
  text,
  text,
  text,
  jsonb,
  jsonb,
  uuid,
  uuid
) from public, anon, authenticated;

grant execute on function public.save_quiz_with_concepts(
  uuid,
  uuid,
  text,
  text,
  text,
  jsonb,
  jsonb,
  uuid,
  uuid
) to authenticated;

comment on function public.save_quiz_with_concepts(
  uuid,
  uuid,
  text,
  text,
  text,
  jsonb,
  jsonb,
  uuid,
  uuid
) is '과제 목표와 같은 사용자·계획·목표의 참고자료만 허용하는 퀴즈 저장 RPC';

commit;
