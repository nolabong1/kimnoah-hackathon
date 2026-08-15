-- supabase_concept_mastery_upgrade.sql 실행 후 사용하는 읽기 전용 검증입니다.
-- 모든 검사가 통과하면 마지막 SELECT가 success를 반환합니다.
begin;

do $$
declare
  required_table text;
begin
  foreach required_table in array array[
    'learning_concepts',
    'concept_aliases',
    'concept_mastery',
    'concept_mastery_events'
  ]
  loop
    if to_regclass('public.' || required_table) is null then
      raise exception '필수 테이블이 없습니다: %', required_table;
    end if;
  end loop;
end;
$$;


do $$
declare
  required_constraint text;
begin
  foreach required_constraint in array array[
    'learning_concepts_user_course_key_unique',
    'concept_aliases_user_course_alias_unique',
    'quiz_attempts_submission_key_unique',
    'quiz_attempts_id_user_unique',
    'quiz_attempts_id_quiz_user_unique',
    'quizzes_id_plan_user_unique',
    'concept_mastery_concept_owner_fk',
    'concept_mastery_last_attempt_owner_fk',
    'concept_mastery_events_attempt_quiz_owner_fk',
    'concept_mastery_events_attempt_question_unique',
    'study_tasks_concept_owner_fk',
    'study_tasks_source_quiz_plan_owner_fk',
    'study_tasks_source_attempt_quiz_owner_fk',
    'study_tasks_source_metadata_check'
  ]
  loop
    if not exists (
      select 1
      from pg_catalog.pg_constraint
      where conname = required_constraint
        and connamespace = 'public'::regnamespace
    ) then
      raise exception
        '필수 제약조건이 없습니다: %', required_constraint;
    end if;
  end loop;
end;
$$;


do $$
declare
  required_index text;
begin
  foreach required_index in array array[
    'study_tasks_pending_weakness_review_unique',
    'learning_concepts_user_course_idx',
    'concept_aliases_concept_idx',
    'concept_mastery_concept_idx',
    'concept_mastery_last_attempt_idx',
    'concept_mastery_user_score_idx',
    'concept_mastery_events_concept_idx',
    'concept_mastery_events_user_concept_created_idx',
    'study_tasks_concept_idx',
    'study_tasks_source_quiz_idx',
    'study_tasks_source_attempt_idx'
  ]
  loop
    if to_regclass('public.' || required_index) is null then
      raise exception '필수 인덱스가 없습니다: %', required_index;
    end if;

    if not exists (
      select 1
      from pg_catalog.pg_index as index_state
      where index_state.indexrelid = (
        'public.' || required_index
      )::regclass
        and index_state.indisvalid
        and index_state.indisready
    ) then
      raise exception '인덱스가 유효하지 않습니다: %', required_index;
    end if;
  end loop;

  if not exists (
    select 1
    from pg_catalog.pg_index as index_state
    where index_state.indexrelid = (
      'public.study_tasks_pending_weakness_review_unique'
    )::regclass
      and index_state.indisunique
      and index_state.indpred is not null
  ) then
    raise exception
      '자동 복습 중복 방지 인덱스가 부분 유일 인덱스가 아닙니다.';
  end if;
end;
$$;


do $$
declare
  protected_table text;
  rls_enabled boolean;
begin
  foreach protected_table in array array[
    'learning_concepts',
    'concept_aliases',
    'concept_mastery',
    'concept_mastery_events'
  ]
  loop
    select class.relrowsecurity
    into rls_enabled
    from pg_catalog.pg_class as class
    where class.oid = (
      'public.' || protected_table
    )::regclass;

    if rls_enabled is distinct from true then
      raise exception 'RLS가 비활성화되어 있습니다: %', protected_table;
    end if;

    if not exists (
      select 1
      from pg_catalog.pg_policies as policy
      where policy.schemaname = 'public'
        and policy.tablename = protected_table
        and policy.cmd = 'SELECT'
        and 'authenticated' = any(policy.roles)
        and position('auth.uid' in policy.qual) > 0
    ) then
      raise exception
        'auth.uid 소유권 SELECT 정책이 없습니다: %', protected_table;
    end if;

    if exists (
      select 1
      from pg_catalog.pg_policies as policy
      where policy.schemaname = 'public'
        and policy.tablename = protected_table
        and policy.cmd <> 'SELECT'
    ) then
      raise exception
        '읽기 이외의 RLS 정책이 존재합니다: %', protected_table;
    end if;

    if not has_table_privilege(
      'authenticated',
      'public.' || protected_table,
      'SELECT'
    ) then
      raise exception
        'authenticated SELECT 권한이 없습니다: %', protected_table;
    end if;

    if has_table_privilege(
      'authenticated',
      'public.' || protected_table,
      'INSERT'
    ) or has_table_privilege(
      'authenticated',
      'public.' || protected_table,
      'UPDATE'
    ) or has_table_privilege(
      'authenticated',
      'public.' || protected_table,
      'DELETE'
    ) then
      raise exception
        'authenticated 직접 쓰기 권한이 남아 있습니다: %',
        protected_table;
    end if;

    if has_table_privilege(
      'anon',
      'public.' || protected_table,
      'SELECT'
    ) or has_table_privilege(
      'anon',
      'public.' || protected_table,
      'INSERT'
    ) or has_table_privilege(
      'anon',
      'public.' || protected_table,
      'UPDATE'
    ) or has_table_privilege(
      'anon',
      'public.' || protected_table,
      'DELETE'
    ) then
      raise exception 'anon 권한이 남아 있습니다: %', protected_table;
    end if;
  end loop;
end;
$$;


do $$
begin
  if exists (
    select 1
    from public.quiz_attempts
    where submission_key is null
  ) then
    raise exception 'submission_key가 없는 기존 응시가 있습니다.';
  end if;

  if exists (
    select 1
    from public.quiz_attempts
    group by user_id, quiz_id, submission_key
    having count(*) > 1
  ) then
    raise exception '중복 submission_key 응시가 있습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks
    where not (
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
    )
  ) then
    raise exception '과제 출처 메타데이터가 일관되지 않습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks
    where source_type = 'weakness_review'
      and status = 'pending'
    group by user_id, plan_id, concept_id
    having count(*) > 1
  ) then
    raise exception '중복된 미완료 자동 복습 과제가 있습니다.';
  end if;
end;
$$;


select 'concept mastery schema validation: success'
  as validation_result;

rollback;
