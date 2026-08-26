begin;

-- 오늘 학습 화면의 반복 조회를 인증 사용자 기준 단일 읽기 RPC로 묶습니다.
create or replace function public.get_dashboard_snapshot(
  p_plan_id uuid,
  p_course_key text
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_snapshot jsonb;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  if p_plan_id is null then
    raise exception '학습계획 ID가 필요합니다.';
  end if;

  if p_course_key is null
     or char_length(btrim(p_course_key)) not between 1 and 120 then
    raise exception '과목 키가 올바르지 않습니다.';
  end if;

  if not exists (
    select 1
    from public.study_plans as plan
    where plan.id = p_plan_id
      and plan.user_id = v_user_id
  ) then
    raise exception '학습계획을 찾을 수 없습니다.';
  end if;

  select pg_catalog.jsonb_build_object(
    'user_id', v_user_id,
    'plan_id', p_plan_id,
    'plan_tasks', coalesce(
      (
        select pg_catalog.jsonb_agg(
          pg_catalog.jsonb_build_object(
            'id', task.id,
            'scheduled_date', task.scheduled_date,
            'title', task.title,
            'description', task.description,
            'task_type', task.task_type,
            'estimated_minutes', task.estimated_minutes,
            'status', task.status,
            'source_type', task.source_type,
            'concept_id', task.concept_id,
            'review_stage', task.review_stage,
            'review_interval_days', task.review_interval_days
          )
          order by task.scheduled_date, task.created_at, task.id
        )
        from public.study_tasks as task
        where task.user_id = v_user_id
          and task.plan_id = p_plan_id
      ),
      '[]'::jsonb
    ),
    'concept_masteries', coalesce(
      (
        select pg_catalog.jsonb_agg(
          pg_catalog.jsonb_build_object(
            'concept_id', concept.id,
            'course_key', concept.course_key,
            'course_name', concept.course_name,
            'concept_key', concept.concept_key,
            'concept_name', concept.canonical_name,
            'mastery_score', mastery.mastery_score,
            'correct_count', mastery.correct_count,
            'incorrect_count', mastery.incorrect_count,
            'consecutive_incorrect_count',
              mastery.consecutive_incorrect_count,
            'last_answer_correct', mastery.last_answer_correct,
            'last_assessed_at', mastery.last_assessed_at,
            'is_weak', public.is_concept_weak(
              mastery.mastery_score,
              mastery.consecutive_incorrect_count
            )
          )
          order by
            public.is_concept_weak(
              mastery.mastery_score,
              mastery.consecutive_incorrect_count
            ) desc,
            mastery.mastery_score,
            mastery.consecutive_incorrect_count desc,
            concept.canonical_name
        )
        from public.learning_concepts as concept
        join public.concept_mastery as mastery
          on mastery.user_id = concept.user_id
         and mastery.concept_id = concept.id
        where concept.user_id = v_user_id
          and concept.course_key = btrim(p_course_key)
      ),
      '[]'::jsonb
    ),
    'achievements', coalesce(
      (
        select pg_catalog.jsonb_agg(
          pg_catalog.to_jsonb(achievement)
          order by achievement.created_at, achievement.id
        )
        from public.user_achievements as achievement
        where achievement.user_id = v_user_id
      ),
      '[]'::jsonb
    ),
    'challenges', coalesce(
      (
        select pg_catalog.jsonb_agg(
          pg_catalog.to_jsonb(challenge)
          order by
            challenge.period_start desc,
            challenge.display_order,
            challenge.id
        )
        from public.user_challenges as challenge
        where challenge.user_id = v_user_id
      ),
      '[]'::jsonb
    ),
    'badge_showcase', coalesce(
      (
        select pg_catalog.jsonb_agg(
          pg_catalog.to_jsonb(showcase)
          order by showcase.slot
        )
        from public.user_badge_showcase as showcase
        where showcase.user_id = v_user_id
      ),
      '[]'::jsonb
    )
  )
  into v_snapshot;

  return v_snapshot;
end;
$$;

revoke all on function public.get_dashboard_snapshot(uuid, text)
from public, anon, authenticated;

grant execute on function public.get_dashboard_snapshot(uuid, text)
to authenticated;

commit;
