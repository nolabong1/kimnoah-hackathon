begin;

-- 기존 3개 인자 제출 RPC를 멱등성 키를 받는 원자적 처리 RPC로 교체합니다.
drop function if exists public.submit_quiz_attempt(
  uuid,
  timestamptz,
  jsonb
);

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
  v_quiz record;
  v_existing_attempt public.quiz_attempts%rowtype;
  v_attempt_id uuid;
  v_attempt_number integer;
  v_correct_count integer;
  v_score smallint;
  v_submitted_at timestamptz;
  v_question record;
  v_concept record;
  v_mastery public.concept_mastery%rowtype;
  v_is_correct boolean;
  v_score_before smallint;
  v_score_after smallint;
  v_score_delta smallint;
  v_mastery_changes jsonb := '[]'::jsonb;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  if p_quiz_id is null then
    raise exception '퀴즈 ID가 필요합니다.';
  end if;

  if p_quiz_updated_at is null then
    raise exception '퀴즈 버전 정보가 필요합니다.';
  end if;

  if p_submission_key is null then
    raise exception '퀴즈 제출 식별 키가 필요합니다.';
  end if;

  if p_answers is null
     or pg_catalog.jsonb_typeof(p_answers) <> 'array'
  then
    raise exception '답안은 JSON 배열이어야 합니다.';
  end if;

  -- 같은 사용자의 동시 제출은 숙련도 갱신 순서를 확정하기 위해 직렬화합니다.
  perform 1
  from public.profiles as profile
  where profile.id = v_user_id
  for update;

  if not found then
    raise exception '사용자 프로필을 찾을 수 없습니다.';
  end if;

  select
    quiz.id,
    quiz.questions,
    quiz.question_count,
    quiz.updated_at
  into v_quiz
  from public.quizzes as quiz
  where quiz.id = p_quiz_id
    and quiz.user_id = v_user_id
  for update;

  if not found then
    raise exception '퀴즈를 찾을 수 없습니다.';
  end if;

  -- 같은 제출 키가 이미 처리됐다면 숙련도를 다시 변경하지 않습니다.
  select attempt.*
  into v_existing_attempt
  from public.quiz_attempts as attempt
  where attempt.user_id = v_user_id
    and attempt.quiz_id = v_quiz.id
    and attempt.submission_key = p_submission_key;

  if found then
    if v_existing_attempt.quiz_updated_at
         is distinct from p_quiz_updated_at
       or v_existing_attempt.answers is distinct from p_answers
    then
      raise exception
        '같은 제출 식별 키를 다른 퀴즈 내용에 사용할 수 없습니다.';
    end if;

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
          'score_after', event.score_after
        )
        order by event.question_index
      ),
      '[]'::jsonb
    )
    into v_mastery_changes
    from public.concept_mastery_events as event
    join public.learning_concepts as concept
      on concept.id = event.concept_id
     and concept.user_id = event.user_id
    where event.quiz_attempt_id = v_existing_attempt.id
      and event.user_id = v_user_id;

    return pg_catalog.jsonb_build_object(
      'attempt_id', v_existing_attempt.id,
      'quiz_id', v_existing_attempt.quiz_id,
      'submission_key', v_existing_attempt.submission_key,
      'attempt_number', v_existing_attempt.attempt_number,
      'answers', v_existing_attempt.answers,
      'questions_snapshot', v_existing_attempt.questions_snapshot,
      'quiz_updated_at', v_existing_attempt.quiz_updated_at,
      'correct_count', v_existing_attempt.correct_count,
      'total_questions', v_existing_attempt.total_questions,
      'score', v_existing_attempt.score,
      'exp_awarded', v_existing_attempt.exp_awarded,
      'submitted_at', v_existing_attempt.submitted_at,
      'mastery_changes', v_mastery_changes,
      'already_processed', true
    );
  end if;

  if v_quiz.updated_at is distinct from p_quiz_updated_at then
    raise exception
      '퀴즈가 새 문제로 갱신되었습니다. 다시 열고 응시해주세요.';
  end if;

  if pg_catalog.jsonb_array_length(p_answers)
       <> v_quiz.question_count
  then
    raise exception '모든 문항에 답해주세요.';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_answers)
      as answer(value)
    where pg_catalog.jsonb_typeof(answer.value) <> 'number'
       or answer.value::text !~ '^[0-3]$'
  ) then
    raise exception
      '각 답안은 0부터 3 사이의 정수여야 합니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(v_quiz.questions)
      as question(value)
    where pg_catalog.jsonb_typeof(
      question.value -> 'correct_answer_index'
    ) <> 'number'
       or (
         question.value -> 'correct_answer_index'
       )::text !~ '^[0-3]$'
  ) then
    raise exception
      '저장된 퀴즈의 정답 형식이 올바르지 않습니다.';
  end if;

  -- 태그 없는 기존 문항은 허용하지만 부분적으로 저장된 태그는 거부합니다.
  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(v_quiz.questions)
      as question(value)
    where (
      question.value ? 'concept_id'
      or question.value ? 'concept_key'
      or question.value ? 'concept_name'
    )
    and (
      pg_catalog.jsonb_typeof(question.value -> 'concept_id')
        is distinct from 'string'
      or (question.value ->> 'concept_id') !~* (
        '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-'
        || '[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
      )
      or pg_catalog.jsonb_typeof(question.value -> 'concept_key')
        is distinct from 'string'
      or (question.value ->> 'concept_key')
        !~ '^[a-z0-9]+(_[a-z0-9]+)*$'
      or pg_catalog.jsonb_typeof(question.value -> 'concept_name')
        is distinct from 'string'
      or char_length(btrim(question.value ->> 'concept_name'))
        not between 1 and 100
    )
  ) then
    raise exception '저장된 문항의 개념 태그 형식이 올바르지 않습니다.';
  end if;

  select count(*)::integer
  into v_correct_count
  from pg_catalog.jsonb_array_elements(
    v_quiz.questions
  ) with ordinality as question(value, position)
  where p_answers ->> (
    (question.position - 1)::integer
  ) = question.value ->> 'correct_answer_index';

  v_score := pg_catalog.round(
    v_correct_count * 100.0
    / v_quiz.question_count
  )::smallint;

  -- 퀴즈 행 잠금으로 같은 퀴즈의 응시 번호 계산을 직렬화합니다.
  select coalesce(
    max(attempt.attempt_number),
    0
  ) + 1
  into v_attempt_number
  from public.quiz_attempts as attempt
  where attempt.user_id = v_user_id
    and attempt.quiz_id = v_quiz.id;

  insert into public.quiz_attempts (
    user_id,
    quiz_id,
    submission_key,
    attempt_number,
    answers,
    questions_snapshot,
    quiz_updated_at,
    correct_count,
    total_questions,
    score,
    exp_awarded
  )
  values (
    v_user_id,
    v_quiz.id,
    p_submission_key,
    v_attempt_number,
    p_answers,
    v_quiz.questions,
    v_quiz.updated_at,
    v_correct_count,
    v_quiz.question_count,
    v_score,
    0
  )
  returning id, submitted_at
  into v_attempt_id, v_submitted_at;

  for v_question in
    select
      question.value,
      (question.position - 1)::smallint as question_index
    from pg_catalog.jsonb_array_elements(
      v_quiz.questions
    ) with ordinality as question(value, position)
    order by question.position
  loop
    if not (v_question.value ? 'concept_id') then
      continue;
    end if;

    select
      concept.id,
      concept.concept_key,
      concept.canonical_name
    into v_concept
    from public.learning_concepts as concept
    where concept.id = (
        v_question.value ->> 'concept_id'
      )::uuid
      and concept.user_id = v_user_id
      and concept.concept_key
        = v_question.value ->> 'concept_key';

    if not found then
      raise exception '문항에 연결된 소유 개념을 찾을 수 없습니다.';
    end if;

    v_is_correct := p_answers ->> v_question.question_index
      = v_question.value ->> 'correct_answer_index';

    -- 동시에 다른 퀴즈가 같은 개념을 갱신해도 행 잠금으로 직렬화합니다.
    insert into public.concept_mastery (
      user_id,
      concept_id
    )
    values (
      v_user_id,
      v_concept.id
    )
    on conflict (user_id, concept_id)
    do nothing;

    select mastery.*
    into v_mastery
    from public.concept_mastery as mastery
    where mastery.user_id = v_user_id
      and mastery.concept_id = v_concept.id
    for update;

    v_score_before := v_mastery.mastery_score;

    if v_is_correct then
      v_score_after := least(
        100,
        v_score_before + 10
      )::smallint;
    else
      v_score_after := greatest(
        0,
        v_score_before - 15
      )::smallint;
    end if;

    v_score_delta := (
      v_score_after - v_score_before
    )::smallint;

    update public.concept_mastery as mastery
    set
      mastery_score = v_score_after,
      correct_count = mastery.correct_count
        + case when v_is_correct then 1 else 0 end,
      incorrect_count = mastery.incorrect_count
        + case when v_is_correct then 0 else 1 end,
      consecutive_incorrect_count = case
        when v_is_correct then 0
        else mastery.consecutive_incorrect_count + 1
      end,
      last_answer_correct = v_is_correct,
      last_attempt_id = v_attempt_id,
      last_assessed_at = v_submitted_at
    where mastery.user_id = v_user_id
      and mastery.concept_id = v_concept.id;

    insert into public.concept_mastery_events (
      user_id,
      concept_id,
      quiz_id,
      quiz_attempt_id,
      question_index,
      is_correct,
      score_before,
      score_delta,
      score_after
    )
    values (
      v_user_id,
      v_concept.id,
      v_quiz.id,
      v_attempt_id,
      v_question.question_index,
      v_is_correct,
      v_score_before,
      v_score_delta,
      v_score_after
    );

    v_mastery_changes := v_mastery_changes
      || pg_catalog.jsonb_build_array(
        pg_catalog.jsonb_build_object(
          'concept_id', v_concept.id,
          'concept_key', v_concept.concept_key,
          'concept_name', v_concept.canonical_name,
          'question_index', v_question.question_index,
          'is_correct', v_is_correct,
          'score_before', v_score_before,
          'score_delta', v_score_delta,
          'score_after', v_score_after
        )
      );
  end loop;

  return pg_catalog.jsonb_build_object(
    'attempt_id', v_attempt_id,
    'quiz_id', v_quiz.id,
    'submission_key', p_submission_key,
    'attempt_number', v_attempt_number,
    'answers', p_answers,
    'questions_snapshot', v_quiz.questions,
    'quiz_updated_at', v_quiz.updated_at,
    'correct_count', v_correct_count,
    'total_questions', v_quiz.question_count,
    'score', v_score,
    'exp_awarded', 0,
    'submitted_at', v_submitted_at,
    'mastery_changes', v_mastery_changes,
    'already_processed', false
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

-- 퀴즈 본문과 정답은 개념 검증 RPC를 통해서만 생성·갱신합니다.
revoke insert, update
on public.quizzes
from authenticated;

commit;
