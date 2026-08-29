-- 약점 분석·간격 반복·자동 재계획을 최종 확인하는 읽기 전용 검증입니다.
-- 관련 마이그레이션을 모두 적용한 뒤 Supabase SQL Editor에서 실행하세요.
begin;
set transaction read only;


-- 1. 공개 RPC와 내부 함수의 권한·보안 설정을 확인합니다.
do $$
declare
  submit_function regprocedure := pg_catalog.to_regprocedure(
    'public.submit_quiz_attempt_with_gamification(uuid,timestamptz,jsonb,uuid)'
  );
  complete_function regprocedure := pg_catalog.to_regprocedure(
    'public.complete_study_task_with_gamification(uuid)'
  );
  reset_function regprocedure := pg_catalog.to_regprocedure(
    'public.reset_today_test_progress()'
  );
  reset_implementation regprocedure := pg_catalog.to_regprocedure(
    'public.reset_today_test_progress_unchecked()'
  );
  internal_function regprocedure;
begin
  if submit_function is null
     or complete_function is null
     or reset_function is null
     or reset_implementation is null
  then
    raise exception '필수 공개 RPC가 없습니다.';
  end if;

  if (
    select count(*)
    from pg_catalog.pg_proc as procedure
    where procedure.oid in (
      submit_function,
      complete_function,
      reset_function
    )
      and procedure.prosecdef
      and coalesce(procedure.proconfig::text, '')
        like '%search_path=%'
  ) <> 3 then
    raise exception '공개 RPC의 security definer 또는 search_path 설정이 올바르지 않습니다.';
  end if;

  if not pg_catalog.has_function_privilege(
    'authenticated', submit_function, 'EXECUTE'
  ) or not pg_catalog.has_function_privilege(
    'authenticated', complete_function, 'EXECUTE'
  ) or not pg_catalog.has_function_privilege(
    'authenticated', reset_function, 'EXECUTE'
  ) then
    raise exception 'authenticated 역할에 필요한 RPC 실행 권한이 없습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'anon', submit_function, 'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'anon', complete_function, 'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'anon', reset_function, 'EXECUTE'
  ) then
    raise exception 'anon 역할에 공개 RPC 실행 권한이 남아 있습니다.';
  end if;

  foreach internal_function in array array[
    reset_implementation,
    pg_catalog.to_regprocedure(
      'public.submit_quiz_attempt(uuid,timestamptz,jsonb,uuid)'
    ),
    pg_catalog.to_regprocedure(
      'public.complete_study_task(uuid)'
    ),
    pg_catalog.to_regprocedure(
      'public.process_quiz_attempt_mastery(uuid,timestamptz,jsonb,uuid)'
    ),
    pg_catalog.to_regprocedure(
      'public.build_mastery_changes(uuid,uuid)'
    ),
    pg_catalog.to_regprocedure(
      'public.build_weak_concepts(uuid,uuid)'
    ),
    pg_catalog.to_regprocedure(
      'public.create_auto_review_tasks(uuid,uuid)'
    ),
    pg_catalog.to_regprocedure(
      'public.refresh_study_plan_weekly_overview(uuid,uuid)'
    ),
    pg_catalog.to_regprocedure(
      'public.is_concept_weak(smallint,integer)'
    )
  ]
  loop
    if internal_function is null then
      raise exception '필수 내부 함수가 없습니다.';
    end if;

    if pg_catalog.has_function_privilege(
      'authenticated', internal_function, 'EXECUTE'
    ) or pg_catalog.has_function_privilege(
      'anon', internal_function, 'EXECUTE'
    ) then
      raise exception '내부 함수가 클라이언트 역할에 공개돼 있습니다: %',
        internal_function;
    end if;
  end loop;
end;
$$;


-- 2. 사용자 소유 테이블의 RLS와 소유권 외래 키를 확인합니다.
do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'learning_concepts',
    'concept_aliases',
    'concept_mastery',
    'concept_mastery_events',
    'study_plans',
    'study_tasks',
    'quizzes',
    'quiz_attempts',
    'exp_events'
  ]
  loop
    if not exists (
      select 1
      from pg_catalog.pg_class as relation
      join pg_catalog.pg_namespace as namespace
        on namespace.oid = relation.relnamespace
      where namespace.nspname = 'public'
        and relation.relname = table_name
        and relation.relrowsecurity
    ) then
      raise exception 'RLS가 활성화되지 않은 테이블입니다: %', table_name;
    end if;

    if not exists (
      select 1
      from pg_catalog.pg_policies as policy
      where policy.schemaname = 'public'
        and policy.tablename = table_name
        and policy.cmd = 'SELECT'
        and 'authenticated' = any(policy.roles)
        and coalesce(policy.qual, '') like '%auth.uid()%'
    ) then
      raise exception '본인 행만 조회하는 정책을 찾을 수 없습니다: %', table_name;
    end if;
  end loop;

  if exists (
    select required.constraint_name
    from unnest(array[
      'concept_aliases_concept_owner_course_fk',
      'concept_mastery_concept_owner_fk',
      'concept_mastery_events_concept_owner_fk',
      'concept_mastery_events_attempt_quiz_owner_fk',
      'study_tasks_plan_owner_fk',
      'study_tasks_concept_owner_fk',
      'study_tasks_source_quiz_plan_owner_fk',
      'study_tasks_source_attempt_quiz_owner_fk',
      'quiz_attempts_quiz_owner_fk'
    ]) as required(constraint_name)
    where not exists (
      select 1
      from pg_catalog.pg_constraint as constraint_state
      where constraint_state.conname = required.constraint_name
        and constraint_state.contype = 'f'
    )
  ) then
    raise exception '사용자 소유권 외래 키가 누락됐습니다.';
  end if;
end;
$$;


-- 3. 숙련도 계산식과 문항별 변경 원장의 일관성을 확인합니다.
-- 계획 삭제 시 연결된 응시와 이벤트는 삭제되지만 사용자 누적 숙련도는
-- 보존됩니다. 따라서 남아 있는 이벤트가 현재값에 포함되는지와 유효한
-- 마지막 응시 연결만 검사하며, 전체 누적값과 이벤트 수가 같다고 가정하지 않습니다.
do $$
begin
  if exists (
    select 1
    from public.concept_mastery_events as event
    where (
        event.is_correct
        and event.score_after
          <> least(100, event.score_before + 10)
      )
      or (
        not event.is_correct
        and event.score_after
          <> greatest(0, event.score_before - 15)
      )
      or event.score_delta
        <> event.score_after - event.score_before
  ) then
    raise exception '숙련도 +10/-15 결정론적 계산식과 다른 이벤트가 있습니다.';
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
    raise exception '응시 문항의 개념과 숙련도 이벤트의 개념이 다릅니다.';
  end if;

  if exists (
    select 1
    from public.concept_mastery_events as event
    left join public.concept_mastery as mastery
      on mastery.user_id = event.user_id
     and mastery.concept_id = event.concept_id
    where mastery.user_id is null
  ) then
    raise exception '현재값이 없는 숙련도 이벤트가 있습니다.';
  end if;

  if exists (
    with event_totals as (
      select
        event.user_id,
        event.concept_id,
        count(*) filter (where event.is_correct)::integer
          as correct_count,
        count(*) filter (where not event.is_correct)::integer
          as incorrect_count
      from public.concept_mastery_events as event
      group by event.user_id, event.concept_id
    )
    select 1
    from public.concept_mastery as mastery
    join event_totals as totals
      on totals.user_id = mastery.user_id
     and totals.concept_id = mastery.concept_id
    where mastery.correct_count < totals.correct_count
       or mastery.incorrect_count < totals.incorrect_count
  ) then
    raise exception '현재 숙련도 누적 횟수보다 남아 있는 이벤트 수가 많습니다.';
  end if;

  if exists (
    select 1
    from public.concept_mastery as mastery
    where mastery.last_attempt_id is not null
      and not exists (
        select 1
        from public.concept_mastery_events as event
        join public.quiz_attempts as attempt
          on attempt.id = event.quiz_attempt_id
         and attempt.quiz_id = event.quiz_id
         and attempt.user_id = event.user_id
        where event.user_id = mastery.user_id
          and event.concept_id = mastery.concept_id
          and event.quiz_attempt_id = mastery.last_attempt_id
          and not exists (
            select 1
            from public.concept_mastery_events as later_event
            where later_event.user_id = event.user_id
              and later_event.concept_id = event.concept_id
              and later_event.quiz_attempt_id = event.quiz_attempt_id
              and later_event.question_index > event.question_index
          )
          and event.score_after = mastery.mastery_score
          and event.is_correct = mastery.last_answer_correct
          and attempt.submitted_at = mastery.last_assessed_at
      )
  ) then
    raise exception '현재 숙련도의 마지막 응시 연결이 이벤트와 일치하지 않습니다.';
  end if;
end;
$$;


-- 4. 재응시와 중복 처리 방지 상태를 확인합니다.
do $$
begin
  if exists (
    select 1
    from public.quiz_attempts as attempt
    group by attempt.user_id, attempt.quiz_id, attempt.submission_key
    having count(*) > 1
  ) then
    raise exception '같은 제출 식별 키의 응시가 중복 저장됐습니다.';
  end if;

  if exists (
    select 1
    from public.quiz_attempts as attempt
    group by attempt.user_id, attempt.quiz_id, attempt.attempt_number
    having count(*) > 1
  ) then
    raise exception '재응시 번호가 중복됐습니다.';
  end if;

  if exists (
    select 1
    from public.quiz_attempts as attempt
    where attempt.attempt_number < 1
       or attempt.exp_awarded <> 0
  ) then
    raise exception '재응시 번호 또는 현재 퀴즈 EXP 정책과 다른 응시가 있습니다.';
  end if;

  if exists (
    select 1
    from public.concept_mastery_events as event
    group by event.quiz_attempt_id, event.question_index
    having count(*) > 1
  ) then
    raise exception '같은 응시 문항의 숙련도 이벤트가 중복됐습니다.';
  end if;

  if pg_catalog.to_regclass(
    'public.study_tasks_pending_weakness_review_unique'
  ) is null or pg_catalog.to_regclass(
    'public.study_tasks_weakness_source_attempt_unique'
  ) is null then
    raise exception '자동 복습 중복 방지 인덱스가 없습니다.';
  end if;
end;
$$;


-- 5. 취약 개념에서 생성된 자동 복습의 형식·원인·일정을 확인합니다.
do $$
begin
  if exists (
    select 1
    from public.study_tasks as task
    where task.source_type = 'weakness_review'
      and (
        task.task_type <> 'review'
        or task.estimated_minutes <> 20
        or task.learning_objective_id is null
        or task.concept_id is null
        or task.source_quiz_id is null
        or task.source_quiz_attempt_id is null
        or task.review_stage is null
        or task.review_interval_days is null
        or task.review_stage not between 1 and 3
        or task.review_interval_days <> case task.review_stage
          when 1 then 1
          when 2 then 3
          when 3 then 7
        end
      )
  ) then
    raise exception '자동 복습 과제의 필수 메타데이터가 올바르지 않습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    join public.quiz_attempts as attempt
      on attempt.id = task.source_quiz_attempt_id
     and attempt.quiz_id = task.source_quiz_id
     and attempt.user_id = task.user_id
    join public.study_plans as plan
      on plan.id = task.plan_id
     and plan.user_id = task.user_id
    where task.source_type = 'weakness_review'
      and (
        task.scheduled_date < (
          attempt.submitted_at at time zone 'Asia/Seoul'
        )::date + task.review_interval_days
        or task.scheduled_date > plan.start_date + 13
        or task.scheduled_date > plan.target_date
      )
  ) then
    raise exception '자동 복습 과제의 서울 날짜 또는 계획 종료일 경계가 올바르지 않습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    where task.source_type = 'weakness_review'
      and not exists (
        select 1
        from public.concept_mastery_events as event
        where event.user_id = task.user_id
          and event.quiz_attempt_id = task.source_quiz_attempt_id
          and event.concept_id = task.concept_id
          and not event.is_correct
      )
  ) then
    raise exception '오답이 없는 응시에서 자동 복습 과제가 생성됐습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    where task.source_type = 'weakness_review'
    group by
      task.user_id,
      task.source_quiz_attempt_id,
      task.concept_id,
      task.review_stage
    having count(*) > 1
  ) then
    raise exception '같은 응시·개념·단계의 자동 복습 과제가 중복됐습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    where task.source_type = 'weakness_review'
      and task.status = 'pending'
    group by
      task.user_id,
      task.plan_id,
      task.concept_id,
      task.review_stage
    having count(*) > 1
  ) then
    raise exception '같은 계획·개념·단계의 미완료 자동 복습 과제가 중복됐습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    where task.source_type = 'weakness_review'
      and task.status = 'pending'
    group by task.user_id, task.plan_id, task.concept_id
    having count(distinct task.source_quiz_attempt_id) > 1
  ) then
    raise exception '같은 개념에 서로 다른 미완료 복습 묶음이 겹칩니다.';
  end if;
end;
$$;


-- 6. 일일 가능 시간과 weekly_overview 일관성을 확인합니다.
do $$
begin
  if exists (
    select 1
    from public.study_plans as plan
    join public.study_tasks as task
      on task.plan_id = plan.id
     and task.user_id = plan.user_id
    where exists (
      select 1
      from public.study_tasks as weakness_task
      where weakness_task.user_id = plan.user_id
        and weakness_task.plan_id = plan.id
        and weakness_task.source_type = 'weakness_review'
    )
    group by
      plan.id,
      plan.user_id,
      plan.start_date,
      plan.available_schedule,
      task.scheduled_date
    having sum(task.estimated_minutes) > coalesce(
      case
        when plan.available_schedule
          ->> (
            mod(task.scheduled_date - plan.start_date, 7)::text
            || '일차'
          ) ~ '^\d+$'
        then (
          plan.available_schedule
            ->> (
              mod(task.scheduled_date - plan.start_date, 7)::text
              || '일차'
            )
        )::integer
        else 0
      end,
      0
    )
  ) then
    raise exception '자동 복습이 포함된 계획에서 일일 가능 시간을 초과했습니다.';
  end if;

  if exists (
    select 1
    from public.study_plans as plan
    join lateral pg_catalog.generate_series(
      0,
      plan.target_date - plan.start_date
    ) as day(day_offset) on true
    left join lateral (
      select coalesce(sum(task.estimated_minutes), 0)::integer
        as total_minutes
      from public.study_tasks as task
      where task.user_id = plan.user_id
        and task.plan_id = plan.id
        and task.scheduled_date = plan.start_date + day.day_offset
    ) as actual_total on true
    left join lateral (
      select (overview.value ->> 'total_minutes')::integer
        as total_minutes
      from pg_catalog.jsonb_array_elements(
        plan.weekly_overview
      ) as overview(value)
      where overview.value ->> 'day_offset' ~ '^\d+$'
        and overview.value ->> 'total_minutes' ~ '^\d+$'
        and (overview.value ->> 'day_offset')::integer
          = day.day_offset
      limit 1
    ) as overview_total on true
    where exists (
      select 1
      from public.study_tasks as weakness_task
      where weakness_task.user_id = plan.user_id
        and weakness_task.plan_id = plan.id
        and weakness_task.source_type = 'weakness_review'
    )
      and overview_total.total_minutes
        is distinct from actual_total.total_minutes
  ) then
    raise exception 'weekly_overview와 실제 과제 시간이 일치하지 않습니다.';
  end if;
end;
$$;


-- 7. 기존 EXP 규칙과 자동 복습 완료 보상을 확인합니다.
do $$
begin
  if exists (
    select 1
    from public.exp_events as event
    where (event.event_type = 'task_completion' and event.amount <> 10)
       or (event.event_type = 'daily_completion' and event.amount <> 20)
  ) then
    raise exception '과제 10 EXP 또는 일일 완료 20 EXP 규칙과 다른 이벤트가 있습니다.';
  end if;

  if exists (
    select 1
    from public.exp_events as event
    group by event.user_id, event.source_key
    having count(*) > 1
  ) then
    raise exception 'EXP source_key가 중복됐습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    where task.source_type = 'weakness_review'
      and task.status = 'pending'
      and exists (
        select 1
        from public.exp_events as event
        where event.user_id = task.user_id
          and event.source_key = 'task:' || task.id::text
      )
  ) then
    raise exception '미완료 자동 복습 과제에 EXP가 지급됐습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    where task.source_type = 'weakness_review'
      and task.status = 'completed'
      and not exists (
        select 1
        from public.exp_events as event
        where event.user_id = task.user_id
          and event.event_type = 'task_completion'
          and event.source_key = 'task:' || task.id::text
          and event.amount = 10
      )
  ) then
    raise exception '완료한 자동 복습 과제의 10 EXP 이벤트가 없습니다.';
  end if;
end;
$$;


-- 8. 테스트 초기화 이후 남은 데이터의 참조 무결성을 확인합니다.
-- 공개 함수는 접근 허용 목록을 검사하는 래퍼이며 실제 초기화 구현은
-- authenticated가 직접 실행할 수 없는 unchecked 함수에 보존됩니다.
do $$
declare
  reset_implementation regprocedure := pg_catalog.to_regprocedure(
    'public.reset_today_test_progress_unchecked()'
  );
begin
  if exists (
    select 1
    from public.study_tasks as task
    left join public.quiz_attempts as attempt
      on attempt.id = task.source_quiz_attempt_id
     and attempt.quiz_id = task.source_quiz_id
     and attempt.user_id = task.user_id
    where task.source_type = 'weakness_review'
      and attempt.id is null
  ) then
    raise exception '원본 응시가 없는 자동 복습 과제가 남아 있습니다.';
  end if;

  if exists (
    select 1
    from public.concept_mastery_events as event
    left join public.quiz_attempts as attempt
      on attempt.id = event.quiz_attempt_id
     and attempt.quiz_id = event.quiz_id
     and attempt.user_id = event.user_id
    where attempt.id is null
  ) then
    raise exception '원본 응시가 없는 숙련도 이벤트가 남아 있습니다.';
  end if;

  if reset_implementation is null
     or pg_catalog.pg_get_functiondef(reset_implementation)
       not like '%removed_mastery_event_count%'
  then
    raise exception '적응형 학습 데이터를 되돌리는 초기화 RPC 버전이 아닙니다.';
  end if;
end;
$$;


select
  'adaptive learning integration validation: success'
    as validation_result;

rollback;
