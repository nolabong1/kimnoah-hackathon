-- supabase_concept_mastery_processing.sql 실행 후 사용하는 읽기 전용 검증입니다.
begin;

do $$
declare
  function_oid regprocedure := pg_catalog.to_regprocedure(
    'public.submit_quiz_attempt(uuid,timestamptz,jsonb,uuid)'
  );
begin
  if function_oid is null then
    raise exception '4개 인자 퀴즈 제출 RPC가 없습니다.';
  end if;

  if pg_catalog.to_regprocedure(
    'public.submit_quiz_attempt(uuid,timestamptz,jsonb)'
  ) is not null then
    raise exception '기존 3개 인자 퀴즈 제출 RPC가 남아 있습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    where procedure.oid = function_oid
      and procedure.prosecdef
      and coalesce(procedure.proconfig::text, '')
        like '%search_path=%'
  ) then
    raise exception '퀴즈 제출 RPC 보안 설정이 올바르지 않습니다.';
  end if;

  if not pg_catalog.has_function_privilege(
    'authenticated',
    function_oid,
    'EXECUTE'
  ) then
    raise exception 'authenticated RPC 실행 권한이 없습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'anon',
    function_oid,
    'EXECUTE'
  ) then
    raise exception 'anon RPC 실행 권한이 남아 있습니다.';
  end if;

  if pg_catalog.has_table_privilege(
    'authenticated',
    'public.quizzes',
    'INSERT'
  ) or pg_catalog.has_table_privilege(
    'authenticated',
    'public.quizzes',
    'UPDATE'
  ) then
    raise exception '퀴즈 테이블 직접 생성·갱신 권한이 남아 있습니다.';
  end if;
end;
$$;


do $$
begin
  if exists (
    select 1
    from public.quiz_attempts as attempt
    group by attempt.user_id, attempt.quiz_id, attempt.submission_key
    having count(*) > 1
  ) then
    raise exception '중복 제출 식별 키가 존재합니다.';
  end if;

  if exists (
    select 1
    from public.concept_mastery_events as event
    group by event.quiz_attempt_id, event.question_index
    having count(*) > 1
  ) then
    raise exception '한 응시 문항의 숙련도 변경이 중복 저장됐습니다.';
  end if;

  if exists (
    select 1
    from public.concept_mastery_events as event
    where event.score_after
      <> event.score_before + event.score_delta
       or event.score_after not between 0 and 100
       or event.score_before not between 0 and 100
  ) then
    raise exception '숙련도 변경 이력의 점수 계산이 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from public.concept_mastery_events as event
    join public.quiz_attempts as attempt
      on attempt.id = event.quiz_attempt_id
     and attempt.quiz_id = event.quiz_id
     and attempt.user_id = event.user_id
    where attempt.questions_snapshot
      -> event.question_index
      ->> 'concept_id'
      is distinct from event.concept_id::text
  ) then
    raise exception '숙련도 이력과 응시 문항의 개념 연결이 다릅니다.';
  end if;
end;
$$;


select
  concept.course_name,
  concept.canonical_name as concept_name,
  mastery.mastery_score,
  mastery.correct_count,
  mastery.incorrect_count,
  mastery.consecutive_incorrect_count,
  mastery.last_answer_correct,
  mastery.last_assessed_at
from public.concept_mastery as mastery
join public.learning_concepts as concept
  on concept.id = mastery.concept_id
 and concept.user_id = mastery.user_id
order by mastery.last_assessed_at desc nulls last;

select
  event.quiz_attempt_id,
  event.question_index,
  concept.canonical_name as concept_name,
  event.is_correct,
  event.score_before,
  event.score_delta,
  event.score_after,
  event.created_at
from public.concept_mastery_events as event
join public.learning_concepts as concept
  on concept.id = event.concept_id
 and concept.user_id = event.user_id
order by event.created_at desc, event.question_index desc
limit 50;

select 'concept mastery processing validation: success'
  as validation_result;

rollback;
