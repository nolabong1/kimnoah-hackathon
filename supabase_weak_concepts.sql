begin;

-- 현재 숙련도가 낮거나 최근 오답이 반복된 개념을 취약 개념으로 봅니다.
create function public.is_concept_weak(
  p_mastery_score smallint,
  p_consecutive_incorrect_count integer
)
returns boolean
language sql
immutable
strict
set search_path = ''
as $$
  select p_mastery_score < 60
    or p_consecutive_incorrect_count >= 2;
$$;

revoke all on function public.is_concept_weak(
  smallint,
  integer
) from public, anon, authenticated;


-- 한 응시에서 발생한 문항별 숙련도 변경에 현재 취약 여부를 붙입니다.
create function public.build_mastery_changes(
  p_user_id uuid,
  p_quiz_attempt_id uuid
)
returns jsonb
language sql
stable
set search_path = ''
as $$
  select coalesce(
    pg_catalog.jsonb_agg(
      pg_catalog.jsonb_build_object(
        'concept_id', event.concept_id,
        'concept_key', concept.concept_key,
        'concept_name', concept.canonical_name,
        'question_index', event.question_index,
        'is_correct', event.is_correct,
        'score_before', event.score_before,
        'score_delta', event.score_delta,
        'score_after', event.score_after,
        'is_weak', public.is_concept_weak(
          mastery.mastery_score,
          mastery.consecutive_incorrect_count
        )
      )
      order by event.question_index
    ),
    '[]'::jsonb
  )
  from public.concept_mastery_events as event
  join public.learning_concepts as concept
    on concept.id = event.concept_id
   and concept.user_id = event.user_id
  join public.concept_mastery as mastery
    on mastery.concept_id = event.concept_id
   and mastery.user_id = event.user_id
  where event.user_id = p_user_id
    and event.quiz_attempt_id = p_quiz_attempt_id;
$$;

revoke all on function public.build_mastery_changes(
  uuid,
  uuid
) from public, anon, authenticated;


-- 사용자 전체 또는 특정 응시에서 확인된 현재 취약 개념을 반환합니다.
create function public.build_weak_concepts(
  p_user_id uuid,
  p_quiz_attempt_id uuid
)
returns jsonb
language sql
stable
set search_path = ''
as $$
  select coalesce(
    pg_catalog.jsonb_agg(
      pg_catalog.jsonb_build_object(
        'concept_id', concept.id,
        'course_key', concept.course_key,
        'concept_key', concept.concept_key,
        'concept_name', concept.canonical_name,
        'mastery_score', mastery.mastery_score,
        'correct_count', mastery.correct_count,
        'incorrect_count', mastery.incorrect_count,
        'consecutive_incorrect_count',
          mastery.consecutive_incorrect_count,
        'last_answer_correct', mastery.last_answer_correct,
        'last_assessed_at', mastery.last_assessed_at
      )
      order by
        mastery.mastery_score,
        mastery.consecutive_incorrect_count desc,
        mastery.last_assessed_at desc,
        concept.canonical_name
    ),
    '[]'::jsonb
  )
  from public.concept_mastery as mastery
  join public.learning_concepts as concept
    on concept.id = mastery.concept_id
   and concept.user_id = mastery.user_id
  where mastery.user_id = p_user_id
    and public.is_concept_weak(
      mastery.mastery_score,
      mastery.consecutive_incorrect_count
    )
    and (
      p_quiz_attempt_id is null
      or exists (
        select 1
        from public.concept_mastery_events as event
        where event.user_id = p_user_id
          and event.quiz_attempt_id = p_quiz_attempt_id
          and event.concept_id = mastery.concept_id
      )
    );
$$;

revoke all on function public.build_weak_concepts(
  uuid,
  uuid
) from public, anon, authenticated;


-- 기존 원자적 채점·숙련도 처리를 내부 함수로 보존합니다.
alter function public.submit_quiz_attempt(
  uuid,
  timestamptz,
  jsonb,
  uuid
) rename to process_quiz_attempt_mastery;

revoke all on function public.process_quiz_attempt_mastery(
  uuid,
  timestamptz,
  jsonb,
  uuid
) from public, anon, authenticated;


-- 공개 제출 RPC는 내부 원자적 처리 결과에 취약 분석을 결합합니다.
create function public.submit_quiz_attempt(
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

  return v_result || pg_catalog.jsonb_build_object(
    'mastery_changes', v_mastery_changes,
    'weak_concepts', v_weak_concepts,
    'auto_review_tasks', '[]'::jsonb
  );
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


-- 이후 대시보드에서 사용할 로그인 사용자의 현재 취약 개념 조회 RPC입니다.
create function public.get_current_weak_concepts()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  return public.build_weak_concepts(
    v_user_id,
    null
  );
end;
$$;

revoke all on function public.get_current_weak_concepts()
from public, anon;

grant execute on function public.get_current_weak_concepts()
to authenticated;

commit;
