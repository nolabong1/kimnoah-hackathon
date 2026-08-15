begin;

-- 퀴즈가 재생성되어도 과거 응시 내용을 정확히 보존합니다.
alter table public.quiz_attempts
add column questions_snapshot jsonb;

alter table public.quiz_attempts
add column quiz_updated_at timestamptz;

-- 기존 응시 기록이 있다면 현재 연결된 퀴즈를 기준으로 보완합니다.
-- 기존 점수, 답안, 제출 시각은 변경하지 않습니다.
update public.quiz_attempts as attempt
set
  questions_snapshot = quiz.questions,
  quiz_updated_at = quiz.updated_at
from public.quizzes as quiz
where quiz.id = attempt.quiz_id
  and quiz.user_id = attempt.user_id;

do $$
begin
  if exists (
    select 1
    from public.quiz_attempts
    where questions_snapshot is null
       or quiz_updated_at is null
       or total_questions
          <> jsonb_array_length(questions_snapshot)
       or total_questions
          <> jsonb_array_length(answers)
  ) then
    raise exception
      '기존 응시 기록의 퀴즈 연결 또는 문항 수가 올바르지 않습니다.';
  end if;
end;
$$;

alter table public.quiz_attempts
alter column questions_snapshot set not null;

alter table public.quiz_attempts
alter column quiz_updated_at set not null;

alter table public.quiz_attempts
add constraint quiz_attempts_snapshot_array_check
check (
  jsonb_typeof(questions_snapshot) = 'array'
);

alter table public.quiz_attempts
add constraint quiz_attempts_snapshot_count_matches
check (
  total_questions = jsonb_array_length(questions_snapshot)
);

alter table public.quiz_attempts
add constraint quiz_attempts_answer_count_matches
check (
  total_questions = jsonb_array_length(answers)
);


create or replace function public.submit_quiz_attempt(
  p_quiz_id uuid,
  p_quiz_updated_at timestamptz,
  p_answers jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_quiz record;
  v_attempt_id uuid;
  v_attempt_number integer;
  v_correct_count integer;
  v_score smallint;
  v_submitted_at timestamptz;
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

  if p_answers is null
     or pg_catalog.jsonb_typeof(p_answers) <> 'array'
  then
    raise exception '답안은 JSON 배열이어야 합니다.';
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

  return pg_catalog.jsonb_build_object(
    'attempt_id', v_attempt_id,
    'quiz_id', v_quiz.id,
    'attempt_number', v_attempt_number,
    'answers', p_answers,
    'questions_snapshot', v_quiz.questions,
    'quiz_updated_at', v_quiz.updated_at,
    'correct_count', v_correct_count,
    'total_questions', v_quiz.question_count,
    'score', v_score,
    'exp_awarded', 0,
    'submitted_at', v_submitted_at
  );
end;
$$;


-- 응시 기록은 채점 RPC만 생성할 수 있도록 직접 삽입을 차단합니다.
drop policy if exists "quiz_attempts_insert_own"
on public.quiz_attempts;

revoke insert
on public.quiz_attempts
from authenticated;

revoke all
on function public.submit_quiz_attempt(
  uuid,
  timestamptz,
  jsonb
)
from public, anon;

grant execute
on function public.submit_quiz_attempt(
  uuid,
  timestamptz,
  jsonb
)
to authenticated;

commit;
