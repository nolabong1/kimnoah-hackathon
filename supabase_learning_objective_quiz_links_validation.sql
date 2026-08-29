-- 037_learning_objective_quiz_links 적용 결과를 읽기 전용으로 검증합니다.
begin;

set transaction read only;

do $$
declare
  v_new_function regprocedure := pg_catalog.to_regprocedure(
    'public.save_quiz_with_concepts(uuid,uuid,text,text,text,jsonb,jsonb,uuid,uuid)'
  );
  v_old_function regprocedure := pg_catalog.to_regprocedure(
    'public.save_quiz_with_concepts(uuid,uuid,text,text,text,jsonb,jsonb)'
  );
  v_definition text;
begin
  if v_new_function is null or v_old_function is null then
    raise exception '신규 또는 내부 퀴즈 저장 함수가 없습니다.';
  end if;

  if not pg_catalog.has_function_privilege(
       'authenticated', v_new_function, 'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'anon', v_new_function, 'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'authenticated', v_old_function, 'EXECUTE'
     )
  then
    raise exception '퀴즈 저장 함수의 공개 실행 권한이 올바르지 않습니다.';
  end if;

  select pg_catalog.pg_get_functiondef(v_new_function)
  into v_definition;

  if position('security definer' in lower(v_definition)) = 0
     or position('auth.uid()' in v_definition) = 0
     or position('learning_objective_id' in v_definition) = 0
     or position('reference_learning_material_id' in v_definition) = 0
     or position('reference_review_material_id' in v_definition) = 0
     or position('is distinct from v_task_objective_id' in v_definition) = 0
  then
    raise exception '퀴즈 저장 함수의 인증·목표·참고자료 검증이 올바르지 않습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    cross join lateral pg_catalog.unnest(procedure.proconfig) as config(value)
    where procedure.oid = v_new_function
      and procedure.prosecdef
      and config.value in ('search_path=', 'search_path=""')
  ) then
    raise exception '퀴즈 저장 함수의 search_path가 안전하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.quizzes as quiz
    join public.study_tasks as task
      on task.id = quiz.task_id
     and task.plan_id = quiz.plan_id
     and task.user_id = quiz.user_id
    where quiz.learning_objective_id is not null
      and quiz.learning_objective_id is distinct from task.learning_objective_id
  ) then
    raise exception '퀴즈와 과제의 학습목표가 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.quizzes as quiz
    join public.learning_materials as material
      on material.id = quiz.reference_learning_material_id
     and material.plan_id = quiz.plan_id
     and material.user_id = quiz.user_id
    where material.learning_objective_id
          is distinct from quiz.learning_objective_id
  ) then
    raise exception '퀴즈와 원본 참고자료의 학습목표가 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.quizzes as quiz
    join public.review_materials as material
      on material.id = quiz.reference_review_material_id
     and material.plan_id = quiz.plan_id
     and material.user_id = quiz.user_id
    where material.learning_objective_id
          is distinct from quiz.learning_objective_id
  ) then
    raise exception '퀴즈와 AI 참고자료의 학습목표가 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.quizzes as quiz
    join public.learning_objectives as objective
      on objective.id = quiz.learning_objective_id
     and objective.plan_id = quiz.plan_id
     and objective.user_id = quiz.user_id
    where objective.origin = 'generated'
      and (
        quiz.objective_contract_hash is distinct from objective.contract_hash
        or quiz.objective_snapshot is distinct from
          pg_catalog.jsonb_build_object(
            'objective_key', objective.objective_key,
            'title', objective.title,
            'description', objective.description,
            'target_depth', objective.target_depth,
            'evidence_requirements', objective.evidence_requirements
          )
      )
  ) then
    raise exception '생성 목표 퀴즈의 계약 스냅샷 또는 해시가 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.quizzes as quiz
    join public.learning_objectives as objective
      on objective.id = quiz.learning_objective_id
     and objective.plan_id = quiz.plan_id
     and objective.user_id = quiz.user_id
    where objective.origin = 'legacy_backfill'
      and (
        quiz.objective_snapshot is not null
        or quiz.objective_contract_hash is not null
      )
  ) then
    raise exception '기존 계획 호환 목표 퀴즈에 거짓 계약 스냅샷이 저장됐습니다.';
  end if;
end;
$$;

select 'learning objective quiz links validation: success'
as validation_result;

rollback;
