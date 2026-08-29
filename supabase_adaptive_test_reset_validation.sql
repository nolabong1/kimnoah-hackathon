-- supabase_adaptive_test_reset.sql 실행 후 사용하는 읽기 전용 검증입니다.
begin;

do $$
declare
  reset_function regprocedure := pg_catalog.to_regprocedure(
    'public.reset_today_test_progress()'
  );
  reset_implementation regprocedure;
begin
  if reset_function is null then
    raise exception '테스트 초기화 RPC가 없습니다.';
  end if;

  reset_implementation := coalesce(
    pg_catalog.to_regprocedure(
      'public.reset_today_test_progress_unchecked()'
    ),
    reset_function
  );

  if not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    where procedure.oid = reset_function
      and procedure.prosecdef
      and coalesce(procedure.proconfig::text, '')
        like '%search_path=%'
  ) then
    raise exception '테스트 초기화 RPC 보안 설정이 올바르지 않습니다.';
  end if;

  if not pg_catalog.has_function_privilege(
    'authenticated',
    reset_function,
    'EXECUTE'
  ) then
    raise exception 'authenticated 초기화 권한이 없습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'anon',
    reset_function,
    'EXECUTE'
  ) then
    raise exception 'anon 초기화 권한이 남아 있습니다.';
  end if;

  if reset_implementation <> reset_function
     and (
       pg_catalog.has_function_privilege(
         'authenticated', reset_implementation, 'EXECUTE'
       )
       or pg_catalog.has_function_privilege(
         'anon', reset_implementation, 'EXECUTE'
       )
     )
  then
    raise exception '비공개 초기화 구현에 직접 실행 권한이 남아 있습니다.';
  end if;

  if pg_catalog.pg_get_functiondef(reset_implementation)
       not like '%removed_mastery_event_count%'
  then
    raise exception '적응형 학습 초기화 버전이 적용되지 않았습니다.';
  end if;
end;
$$;


-- 계획 삭제로 이벤트 이력이 압축될 수 있으므로 남아 있는 이벤트가 현재
-- 숙련도에 포함되는지와 유효한 마지막 응시 연결만 확인합니다.
do $$
begin
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


do $$
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
    raise exception '원본 응시가 없는 자동 복습 과제가 있습니다.';
  end if;

  if exists (
    select 1
    from public.study_plans as plan
    join public.study_tasks as task
      on task.plan_id = plan.id
     and task.user_id = plan.user_id
    where plan.target_date < task.scheduled_date
  ) then
    raise exception '계획 종료일 이후에 과제가 남아 있습니다.';
  end if;

  if exists (
    select 1
    from public.study_plans as plan
    join lateral pg_catalog.generate_series(
      0,
      plan.target_date - plan.start_date
    ) as day(day_offset) on true
    left join lateral (
      select coalesce(
        sum(task.estimated_minutes),
        0
      )::integer as total_minutes
      from public.study_tasks as task
      where task.user_id = plan.user_id
        and task.plan_id = plan.id
        and task.scheduled_date = (
          plan.start_date + day.day_offset
        )
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
    where overview_total.total_minutes
      is distinct from actual_total.total_minutes
  ) then
    raise exception 'weekly_overview와 실제 과제 시간이 일치하지 않습니다.';
  end if;
end;
$$;


select
  (now() at time zone 'Asia/Seoul')::date
    as seoul_date,
  count(*) as remaining_today_quiz_attempts
from public.quiz_attempts as attempt
where (
  attempt.submitted_at at time zone 'Asia/Seoul'
)::date = (
  now() at time zone 'Asia/Seoul'
)::date;

select 'adaptive test reset validation: success'
  as validation_result;

rollback;
