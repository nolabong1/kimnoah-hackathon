-- supabase_weak_concepts.sql 실행 후 사용하는 읽기 전용 검증입니다.
begin;

do $$
declare
  submit_function regprocedure := pg_catalog.to_regprocedure(
    'public.submit_quiz_attempt(uuid,timestamptz,jsonb,uuid)'
  );
  processor_function regprocedure := pg_catalog.to_regprocedure(
    'public.process_quiz_attempt_mastery(uuid,timestamptz,jsonb,uuid)'
  );
  weak_query_function regprocedure := pg_catalog.to_regprocedure(
    'public.get_current_weak_concepts()'
  );
  weak_rule_function regprocedure := pg_catalog.to_regprocedure(
    'public.is_concept_weak(smallint,integer)'
  );
  changes_builder_function regprocedure := pg_catalog.to_regprocedure(
    'public.build_mastery_changes(uuid,uuid)'
  );
  weakness_builder_function regprocedure := pg_catalog.to_regprocedure(
    'public.build_weak_concepts(uuid,uuid)'
  );
begin
  if submit_function is null then
    raise exception '취약 분석이 연결된 퀴즈 제출 RPC가 없습니다.';
  end if;

  if processor_function is null then
    raise exception '내부 숙련도 처리 함수가 없습니다.';
  end if;

  if weak_query_function is null then
    raise exception '현재 취약 개념 조회 RPC가 없습니다.';
  end if;

  if weak_rule_function is null
     or changes_builder_function is null
     or weakness_builder_function is null
  then
    raise exception '취약 판정 내부 함수가 없습니다.';
  end if;

  if (
    select count(*)
    from pg_catalog.pg_proc as procedure
    where procedure.oid in (
      submit_function,
      processor_function,
      weak_query_function
    )
      and procedure.prosecdef
      and coalesce(procedure.proconfig::text, '')
        like '%search_path=%'
  ) <> 3 then
    raise exception '취약 분석 RPC의 보안 설정이 올바르지 않습니다.';
  end if;

  if not pg_catalog.has_function_privilege(
    'authenticated',
    submit_function,
    'EXECUTE'
  ) or not pg_catalog.has_function_privilege(
    'authenticated',
    weak_query_function,
    'EXECUTE'
  ) then
    raise exception 'authenticated 공개 RPC 실행 권한이 없습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'authenticated',
    processor_function,
    'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'authenticated',
    weak_rule_function,
    'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'authenticated',
    changes_builder_function,
    'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'authenticated',
    weakness_builder_function,
    'EXECUTE'
  ) then
    raise exception '내부 취약 분석 함수가 외부에 공개되어 있습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'anon',
    submit_function,
    'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'anon',
    weak_query_function,
    'EXECUTE'
  ) then
    raise exception 'anon RPC 실행 권한이 남아 있습니다.';
  end if;
end;
$$;


do $$
begin
  if public.is_concept_weak(59::smallint, 0) is distinct from true then
    raise exception '숙련도 하한 취약 판정이 올바르지 않습니다.';
  end if;

  if public.is_concept_weak(60::smallint, 1) is distinct from false then
    raise exception '정상 숙련도 경계 판정이 올바르지 않습니다.';
  end if;

  if public.is_concept_weak(100::smallint, 2) is distinct from true then
    raise exception '연속 오답 취약 판정이 올바르지 않습니다.';
  end if;

  if public.is_concept_weak(100::smallint, 1) is distinct from false then
    raise exception '고숙련 단일 오답 판정이 올바르지 않습니다.';
  end if;
end;
$$;


do $$
begin
  if exists (
    select 1
    from public.concept_mastery as mastery
    where public.is_concept_weak(
      mastery.mastery_score,
      mastery.consecutive_incorrect_count
    ) is null
  ) then
    raise exception '숙련도 데이터에서 취약 판정이 누락됐습니다.';
  end if;

  if exists (
    select 1
    from public.concept_mastery_events as event
    left join public.concept_mastery as mastery
      on mastery.user_id = event.user_id
     and mastery.concept_id = event.concept_id
    where mastery.concept_id is null
  ) then
    raise exception '현재값이 없는 숙련도 변경 이력이 있습니다.';
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
  public.is_concept_weak(
    mastery.mastery_score,
    mastery.consecutive_incorrect_count
  ) as is_weak,
  mastery.last_assessed_at
from public.concept_mastery as mastery
join public.learning_concepts as concept
  on concept.id = mastery.concept_id
 and concept.user_id = mastery.user_id
order by
  is_weak desc,
  mastery.mastery_score,
  mastery.last_assessed_at desc;

select 'weak concept validation: success'
  as validation_result;

rollback;
