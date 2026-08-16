begin;

-- 같은 응시가 재처리돼도 개념별 자동 복습 과제를 한 번만 기록합니다.
create unique index study_tasks_weakness_source_attempt_unique
on public.study_tasks(
  user_id,
  source_quiz_attempt_id,
  concept_id
)
where source_type = 'weakness_review';


-- weekly_overview의 일별 시간 합계를 실제 study_tasks와 다시 맞춥니다.
create function public.refresh_study_plan_weekly_overview(
  p_user_id uuid,
  p_plan_id uuid
)
returns void
language plpgsql
set search_path = ''
as $$
declare
  v_plan public.study_plans%rowtype;
  v_weekly_overview jsonb;
begin
  select plan.*
  into v_plan
  from public.study_plans as plan
  where plan.id = p_plan_id
    and plan.user_id = p_user_id
  for update;

  if not found then
    raise exception '학습계획을 찾을 수 없습니다.';
  end if;

  select coalesce(
    pg_catalog.jsonb_agg(
      pg_catalog.jsonb_build_object(
        'day_offset', day_offset,
        'daily_focus', coalesce(
          existing_day.daily_focus,
          '취약 개념 자동 복습'
        ),
        'total_minutes', coalesce(
          task_total.total_minutes,
          0
        )
      )
      order by day_offset
    ),
    '[]'::jsonb
  )
  into v_weekly_overview
  from pg_catalog.generate_series(
    0,
    v_plan.target_date - v_plan.start_date
  ) as day(day_offset)
  left join lateral (
    select nullif(
      btrim(overview.value ->> 'daily_focus'),
      ''
    ) as daily_focus
    from pg_catalog.jsonb_array_elements(
      v_plan.weekly_overview
    ) as overview(value)
    where overview.value ->> 'day_offset' ~ '^\d+$'
      and (overview.value ->> 'day_offset')::integer
        = day.day_offset
    limit 1
  ) as existing_day on true
  left join lateral (
    select coalesce(
      sum(task.estimated_minutes),
      0
    )::integer as total_minutes
    from public.study_tasks as task
    where task.user_id = p_user_id
      and task.plan_id = p_plan_id
      and task.scheduled_date = (
        v_plan.start_date + day.day_offset
      )
  ) as task_total on true;

  update public.study_plans as plan
  set weekly_overview = v_weekly_overview
  where plan.id = p_plan_id
    and plan.user_id = p_user_id;
end;
$$;

revoke all on function public.refresh_study_plan_weekly_overview(
  uuid,
  uuid
) from public, anon, authenticated;


-- 현재 응시에서 반복 오답으로 확인된 취약 개념을 복습 과제로 배치합니다.
create function public.create_auto_review_tasks(
  p_user_id uuid,
  p_quiz_attempt_id uuid
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
  v_today date := (
    now() at time zone 'Asia/Seoul'
  )::date;
  v_plan record;
  v_weak_concept record;
  v_candidate_date date;
  v_search_end_date date;
  v_day_offset integer;
  v_schedule_offset integer;
  v_allowed_minutes integer;
  v_scheduled_minutes integer;
  v_created_task_id uuid;
  v_created_any boolean := false;
  v_auto_review_tasks jsonb := '[]'::jsonb;
  v_unscheduled_concepts jsonb := '[]'::jsonb;
begin
  if p_user_id is null or p_quiz_attempt_id is null then
    raise exception '사용자와 퀴즈 응시 ID가 필요합니다.';
  end if;

  select
    plan.id,
    plan.start_date,
    plan.target_date,
    plan.available_schedule,
    plan.status,
    quiz.id as quiz_id
  into v_plan
  from public.quiz_attempts as attempt
  join public.quizzes as quiz
    on quiz.id = attempt.quiz_id
   and quiz.user_id = attempt.user_id
  join public.study_plans as plan
    on plan.id = quiz.plan_id
   and plan.user_id = quiz.user_id
  where attempt.id = p_quiz_attempt_id
    and attempt.user_id = p_user_id
  for update of plan;

  if not found then
    raise exception '소유한 퀴즈 응시와 학습계획을 찾을 수 없습니다.';
  end if;

  if v_plan.status <> 'active' then
    select coalesce(
      pg_catalog.jsonb_agg(
        pg_catalog.jsonb_build_object(
          'concept_id', concept.id,
          'concept_name', concept.canonical_name,
          'reason', 'inactive_plan'
        )
        order by mastery.mastery_score,
          concept.canonical_name
      ),
      '[]'::jsonb
    )
    into v_unscheduled_concepts
    from public.concept_mastery as mastery
    join public.learning_concepts as concept
      on concept.id = mastery.concept_id
     and concept.user_id = mastery.user_id
    where mastery.user_id = p_user_id
      and mastery.incorrect_count >= 2
      and public.is_concept_weak(
        mastery.mastery_score,
        mastery.consecutive_incorrect_count
      )
      and exists (
        select 1
        from public.concept_mastery_events as event
        where event.user_id = p_user_id
          and event.quiz_attempt_id = p_quiz_attempt_id
          and event.concept_id = mastery.concept_id
          and not event.is_correct
      );

    return pg_catalog.jsonb_build_object(
      'auto_review_tasks', '[]'::jsonb,
      'unscheduled_weak_concepts', v_unscheduled_concepts
    );
  end if;

  -- 원래 7일 계획 이후에는 같은 요일 가능 시간을 한 번만 반복합니다.
  v_search_end_date := v_plan.start_date + 13;

  for v_weak_concept in
    select
      concept.id,
      concept.canonical_name,
      mastery.mastery_score,
      mastery.incorrect_count,
      mastery.consecutive_incorrect_count
    from public.concept_mastery as mastery
    join public.learning_concepts as concept
      on concept.id = mastery.concept_id
     and concept.user_id = mastery.user_id
    where mastery.user_id = p_user_id
      and mastery.incorrect_count >= 2
      and public.is_concept_weak(
        mastery.mastery_score,
        mastery.consecutive_incorrect_count
      )
      and exists (
        select 1
        from public.concept_mastery_events as event
        where event.user_id = p_user_id
          and event.quiz_attempt_id = p_quiz_attempt_id
          and event.concept_id = mastery.concept_id
          and not event.is_correct
      )
    order by
      mastery.mastery_score,
      mastery.consecutive_incorrect_count desc,
      concept.canonical_name
  loop
    -- 같은 응시·개념을 이미 처리했거나 미완료 복습이 있으면 건너뜁니다.
    if exists (
      select 1
      from public.study_tasks as task
      where task.user_id = p_user_id
        and task.concept_id = v_weak_concept.id
        and task.source_type = 'weakness_review'
        and (
          task.source_quiz_attempt_id = p_quiz_attempt_id
          or (
            task.plan_id = v_plan.id
            and task.status = 'pending'
          )
        )
    ) then
      continue;
    end if;

    v_candidate_date := greatest(
      v_today + 1,
      v_plan.start_date
    );
    v_created_task_id := null;

    while v_candidate_date <= v_search_end_date loop
      v_day_offset := (
        v_candidate_date - v_plan.start_date
      );
      v_schedule_offset := mod(v_day_offset, 7);

      if v_plan.available_schedule
           ->> (v_schedule_offset::text || '일차')
           ~ '^\d+$'
      then
        v_allowed_minutes := (
          v_plan.available_schedule
            ->> (v_schedule_offset::text || '일차')
        )::integer;
      else
        v_allowed_minutes := 0;
      end if;

      select coalesce(
        sum(task.estimated_minutes),
        0
      )::integer
      into v_scheduled_minutes
      from public.study_tasks as task
      where task.user_id = p_user_id
        and task.plan_id = v_plan.id
        and task.scheduled_date = v_candidate_date;

      if v_scheduled_minutes + 20 <= v_allowed_minutes then
        insert into public.study_tasks (
          user_id,
          plan_id,
          scheduled_date,
          title,
          description,
          task_type,
          estimated_minutes,
          status,
          source_type,
          concept_id,
          source_quiz_id,
          source_quiz_attempt_id
        )
        values (
          p_user_id,
          v_plan.id,
          v_candidate_date,
          '[자동 복습] ' || v_weak_concept.canonical_name,
          v_weak_concept.canonical_name
            || ' 개념의 현재 숙련도는 '
            || v_weak_concept.mastery_score::text
            || '점입니다. 핵심 개념을 다시 확인하고 '
            || '예시를 직접 설명한 뒤 짧게 적용해보세요.',
          'review',
          20,
          'pending',
          'weakness_review',
          v_weak_concept.id,
          v_plan.quiz_id,
          p_quiz_attempt_id
        )
        on conflict do nothing
        returning id into v_created_task_id;

        exit;
      end if;

      v_candidate_date := v_candidate_date + 1;
    end loop;

    if v_created_task_id is not null then
      v_created_any := true;

      if v_candidate_date > v_plan.target_date then
        update public.study_plans as plan
        set target_date = v_candidate_date
        where plan.id = v_plan.id
          and plan.user_id = p_user_id;

        v_plan.target_date := v_candidate_date;
      end if;
    elsif not exists (
      select 1
      from public.study_tasks as task
      where task.user_id = p_user_id
        and task.plan_id = v_plan.id
        and task.concept_id = v_weak_concept.id
        and task.source_type = 'weakness_review'
        and (
          task.status = 'pending'
          or task.source_quiz_attempt_id = p_quiz_attempt_id
        )
    ) then
      v_unscheduled_concepts := v_unscheduled_concepts
        || pg_catalog.jsonb_build_array(
          pg_catalog.jsonb_build_object(
            'concept_id', v_weak_concept.id,
            'concept_name', v_weak_concept.canonical_name,
            'reason', 'no_available_time'
          )
        );
    end if;
  end loop;

  if v_created_any then
    perform public.refresh_study_plan_weekly_overview(
      p_user_id,
      v_plan.id
    );
  end if;

  select coalesce(
    pg_catalog.jsonb_agg(
      pg_catalog.jsonb_build_object(
        'task_id', task.id,
        'plan_id', task.plan_id,
        'concept_id', task.concept_id,
        'concept_name', concept.canonical_name,
        'title', task.title,
        'scheduled_date', task.scheduled_date,
        'estimated_minutes', task.estimated_minutes
      )
      order by task.scheduled_date, task.created_at
    ),
    '[]'::jsonb
  )
  into v_auto_review_tasks
  from public.study_tasks as task
  join public.learning_concepts as concept
    on concept.id = task.concept_id
   and concept.user_id = task.user_id
  where task.user_id = p_user_id
    and task.plan_id = v_plan.id
    and task.source_type = 'weakness_review'
    and (
      task.source_quiz_attempt_id = p_quiz_attempt_id
      or (
        task.status = 'pending'
        and exists (
          select 1
          from public.concept_mastery_events as event
          join public.concept_mastery as mastery
            on mastery.user_id = event.user_id
           and mastery.concept_id = event.concept_id
          where event.user_id = p_user_id
            and event.quiz_attempt_id = p_quiz_attempt_id
            and event.concept_id = task.concept_id
            and not event.is_correct
            and mastery.incorrect_count >= 2
            and public.is_concept_weak(
              mastery.mastery_score,
              mastery.consecutive_incorrect_count
            )
        )
      )
    );

  return pg_catalog.jsonb_build_object(
    'auto_review_tasks', v_auto_review_tasks,
    'unscheduled_weak_concepts', v_unscheduled_concepts
  );
end;
$$;

revoke all on function public.create_auto_review_tasks(
  uuid,
  uuid
) from public, anon, authenticated;


-- 기존 제출·숙련도·취약 판정과 자동 복습 생성을 한 트랜잭션으로 묶습니다.
create or replace function public.submit_quiz_attempt(
  p_quiz_id uuid,
  p_quiz_updated_at timestamptz,
  p_answers jsonb,
  p_submission_key uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_result jsonb;
  v_attempt_id uuid;
  v_mastery_changes jsonb;
  v_weak_concepts jsonb;
  v_review_result jsonb;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  v_result := public.process_quiz_attempt_mastery(
    p_quiz_id,
    p_quiz_updated_at,
    p_answers,
    p_submission_key
  );

  v_attempt_id := nullif(
    v_result ->> 'attempt_id',
    ''
  )::uuid;

  if v_attempt_id is null then
    raise exception '처리된 퀴즈 응시 ID가 없습니다.';
  end if;

  v_mastery_changes := public.build_mastery_changes(
    v_user_id,
    v_attempt_id
  );
  v_weak_concepts := public.build_weak_concepts(
    v_user_id,
    v_attempt_id
  );
  v_review_result := public.create_auto_review_tasks(
    v_user_id,
    v_attempt_id
  );

  return v_result || pg_catalog.jsonb_build_object(
    'mastery_changes', v_mastery_changes,
    'weak_concepts', v_weak_concepts
  ) || v_review_result;
end;
$$;

revoke all on function public.submit_quiz_attempt(
  uuid,
  timestamptz,
  jsonb,
  uuid
) from public, anon;

grant execute on function public.submit_quiz_attempt(
  uuid,
  timestamptz,
  jsonb,
  uuid
) to authenticated;

commit;
