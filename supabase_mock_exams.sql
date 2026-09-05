begin;

create table public.mock_exams (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  plan_id uuid not null,
  generation_key uuid not null,
  title text not null check (char_length(btrim(title)) between 1 and 200),
  objective_snapshot jsonb not null
    check (jsonb_typeof(objective_snapshot) = 'array'),
  questions jsonb not null check (jsonb_typeof(questions) = 'array'),
  question_count smallint not null default 15
    check (question_count = 15),
  recommended_minutes smallint not null
    check (recommended_minutes between 10 and 90),
  reference_learning_material_id uuid,
  reference_review_material_id uuid,
  prompt_version text not null
    check (char_length(btrim(prompt_version)) between 1 and 100),
  model_name text not null
    check (char_length(btrim(model_name)) between 1 and 100),
  created_at timestamptz not null default now(),
  constraint mock_exams_plan_owner_fk
    foreign key (plan_id, user_id)
    references public.study_plans(id, user_id)
    on delete cascade,
  constraint mock_exams_reference_learning_material_owner_fk
    foreign key (reference_learning_material_id, plan_id, user_id)
    references public.learning_materials(id, plan_id, user_id)
    on delete set null (reference_learning_material_id),
  constraint mock_exams_reference_review_material_owner_fk
    foreign key (reference_review_material_id, plan_id, user_id)
    references public.review_materials(id, plan_id, user_id)
    on delete set null (reference_review_material_id),
  constraint mock_exams_id_user_unique unique (id, user_id),
  constraint mock_exams_generation_unique unique (user_id, generation_key),
  constraint mock_exams_question_length_check
    check (jsonb_array_length(questions) = question_count),
  constraint mock_exams_objective_count_check
    check (jsonb_array_length(objective_snapshot) between 2 and 5),
  constraint mock_exams_single_reference_check
    check (
      reference_learning_material_id is null
      or reference_review_material_id is null
    )
);

create table public.mock_exam_attempts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  mock_exam_id uuid not null,
  submission_key uuid not null,
  attempt_number integer not null check (attempt_number >= 1),
  answers jsonb not null check (jsonb_typeof(answers) = 'array'),
  correct_count smallint not null check (correct_count between 0 and 15),
  total_questions smallint not null check (total_questions = 15),
  score smallint not null check (score between 0 and 100),
  objective_scores jsonb not null
    check (jsonb_typeof(objective_scores) = 'array'),
  question_results jsonb not null
    check (jsonb_typeof(question_results) = 'array'),
  submitted_at timestamptz not null default now(),
  constraint mock_exam_attempts_exam_owner_fk
    foreign key (mock_exam_id, user_id)
    references public.mock_exams(id, user_id)
    on delete cascade,
  constraint mock_exam_attempts_number_unique
    unique (user_id, mock_exam_id, attempt_number),
  constraint mock_exam_attempts_submission_unique
    unique (user_id, submission_key),
  constraint mock_exam_attempts_count_check
    check (
      correct_count <= total_questions
      and jsonb_array_length(answers) = total_questions
      and jsonb_array_length(question_results) = total_questions
      and jsonb_array_length(objective_scores) between 2 and 5
    )
);

create index mock_exams_user_plan_created_idx
  on public.mock_exams(user_id, plan_id, created_at desc);

create index mock_exam_attempts_user_exam_submitted_idx
  on public.mock_exam_attempts(user_id, mock_exam_id, submitted_at desc);

alter table public.mock_exams enable row level security;
alter table public.mock_exam_attempts enable row level security;

create policy "mock_exams_select_own"
on public.mock_exams for select to authenticated
using ((select auth.uid()) = user_id);

create policy "mock_exams_insert_own"
on public.mock_exams for insert to authenticated
with check ((select auth.uid()) = user_id);

create policy "mock_exams_update_own"
on public.mock_exams for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy "mock_exams_delete_own"
on public.mock_exams for delete to authenticated
using ((select auth.uid()) = user_id);

create policy "mock_exam_attempts_select_own"
on public.mock_exam_attempts for select to authenticated
using ((select auth.uid()) = user_id);

create policy "mock_exam_attempts_insert_own"
on public.mock_exam_attempts for insert to authenticated
with check ((select auth.uid()) = user_id);

create policy "mock_exam_attempts_update_own"
on public.mock_exam_attempts for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy "mock_exam_attempts_delete_own"
on public.mock_exam_attempts for delete to authenticated
using ((select auth.uid()) = user_id);

revoke all on public.mock_exams from public, anon, authenticated;
revoke all on public.mock_exam_attempts from public, anon, authenticated;

create function public.save_mock_exam(
  p_plan_id uuid,
  p_generation_key uuid,
  p_title text,
  p_recommended_minutes integer,
  p_questions jsonb,
  p_prompt_version text,
  p_model_name text,
  p_reference_learning_material_id uuid default null,
  p_reference_review_material_id uuid default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_plan public.study_plans%rowtype;
  v_existing public.mock_exams%rowtype;
  v_saved public.mock_exams%rowtype;
  v_objective_snapshot jsonb;
  v_objective_count integer;
  v_reference_title text;
  v_reference_content text;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;
  if p_plan_id is null or p_generation_key is null then
    raise exception '학습계획과 생성 식별자가 필요합니다.';
  end if;
  if p_title is null or char_length(btrim(p_title)) not between 1 and 200 then
    raise exception '모의 평가 제목은 1자 이상 200자 이하여야 합니다.';
  end if;
  if p_recommended_minutes not between 10 and 90 then
    raise exception '모의 평가 권장 시간은 10분 이상 90분 이하여야 합니다.';
  end if;
  if p_prompt_version is null
     or char_length(btrim(p_prompt_version)) not between 1 and 100
     or p_model_name is null
     or char_length(btrim(p_model_name)) not between 1 and 100 then
    raise exception '모의 평가 생성 버전 정보가 올바르지 않습니다.';
  end if;
  if p_reference_learning_material_id is not null
     and p_reference_review_material_id is not null then
    raise exception '모의 평가 참고자료는 하나만 선택할 수 있습니다.';
  end if;

  select plan.* into v_plan
  from public.study_plans as plan
  where plan.id = p_plan_id
    and plan.user_id = v_user_id
  for key share;
  if not found then
    raise exception '학습계획을 찾을 수 없습니다.';
  end if;

  select
    count(*)::integer,
    coalesce(
      pg_catalog.jsonb_agg(
        pg_catalog.jsonb_build_object(
          'id', objective.id,
          'objective_key', objective.objective_key,
          'title', objective.title,
          'description', objective.description,
          'target_depth', objective.target_depth,
          'evidence_requirements', objective.evidence_requirements,
          'contract_hash', objective.contract_hash,
          'sort_order', objective.sort_order
        ) order by objective.sort_order
      ),
      '[]'::jsonb
    )
  into v_objective_count, v_objective_snapshot
  from public.learning_objectives as objective
  where objective.plan_id = p_plan_id
    and objective.user_id = v_user_id;
  if v_objective_count not between 2 and 5 then
    raise exception '모의 평가에는 2개 이상 5개 이하의 학습목표가 필요합니다.';
  end if;

  if p_reference_learning_material_id is not null then
    select material.title, material.content_text
    into v_reference_title, v_reference_content
    from public.learning_materials as material
    where material.id = p_reference_learning_material_id
      and material.plan_id = p_plan_id
      and material.user_id = v_user_id;
    if not found then
      raise exception '선택한 원본 참고자료를 찾을 수 없습니다.';
    end if;
  elsif p_reference_review_material_id is not null then
    select material.title, material.content_markdown
    into v_reference_title, v_reference_content
    from public.review_materials as material
    where material.id = p_reference_review_material_id
      and material.plan_id = p_plan_id
      and material.user_id = v_user_id;
    if not found then
      raise exception '선택한 AI 참고자료를 찾을 수 없습니다.';
    end if;
  end if;

  select exam.* into v_existing
  from public.mock_exams as exam
  where exam.user_id = v_user_id
    and exam.generation_key = p_generation_key;
  if found then
    if v_existing.plan_id is distinct from p_plan_id
       or v_existing.title is distinct from btrim(p_title)
       or v_existing.recommended_minutes is distinct from p_recommended_minutes
       or v_existing.questions is distinct from p_questions
       or v_existing.prompt_version is distinct from btrim(p_prompt_version)
       or v_existing.model_name is distinct from btrim(p_model_name)
       or v_existing.reference_learning_material_id
            is distinct from p_reference_learning_material_id
       or v_existing.reference_review_material_id
            is distinct from p_reference_review_material_id then
      raise exception '같은 생성 식별자를 다른 모의 평가에 사용할 수 없습니다.';
    end if;
    return pg_catalog.jsonb_build_object(
      'id', v_existing.id,
      'user_id', v_existing.user_id,
      'plan_id', v_existing.plan_id,
      'generation_key', v_existing.generation_key,
      'already_processed', true
    );
  end if;

  if p_questions is null
     or pg_catalog.jsonb_typeof(p_questions) <> 'array'
     or pg_catalog.jsonb_array_length(p_questions) <> 15 then
    raise exception '모의 평가는 정확히 15문항이어야 합니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_questions) as item(question)
    where pg_catalog.jsonb_typeof(item.question) <> 'object'
       or pg_catalog.jsonb_typeof(item.question -> 'question') <> 'string'
       or char_length(btrim(item.question ->> 'question')) not between 1 and 500
       or pg_catalog.jsonb_typeof(item.question -> 'choices') <> 'array'
       or pg_catalog.jsonb_array_length(item.question -> 'choices') <> 4
       or pg_catalog.jsonb_typeof(item.question -> 'correct_answer_index') <> 'number'
       or (item.question -> 'correct_answer_index')::text !~ '^[0-3]$'
       or pg_catalog.jsonb_typeof(item.question -> 'explanation') <> 'string'
       or char_length(btrim(item.question ->> 'explanation')) not between 1 and 1000
       or pg_catalog.jsonb_typeof(item.question -> 'objective_key') <> 'string'
       or (item.question ->> 'objective_key') !~ '^[a-z0-9]+(?:_[a-z0-9]+)*$'
       or item.question ->> 'evidence_key' not in ('explain', 'apply', 'differentiate')
       or item.question ->> 'difficulty' not in ('easy', 'medium', 'hard')
       or ((item.question ->> 'source_title') is null)
            <> ((item.question ->> 'source_evidence') is null)
       or (
         item.question ? 'source_title'
         and pg_catalog.jsonb_typeof(item.question -> 'source_title')
           not in ('string', 'null')
       )
       or (
         item.question ? 'source_evidence'
         and pg_catalog.jsonb_typeof(item.question -> 'source_evidence')
           not in ('string', 'null')
       )
       or (
         item.question ->> 'source_title' is not null
         and char_length(btrim(item.question ->> 'source_title')) not between 1 and 200
       )
       or (
         item.question ->> 'source_evidence' is not null
         and char_length(btrim(item.question ->> 'source_evidence')) not between 1 and 500
       )
       or exists (
         select 1
         from pg_catalog.jsonb_array_elements(item.question -> 'choices') as choice(value)
         where pg_catalog.jsonb_typeof(choice.value) <> 'string'
            or char_length(btrim(choice.value #>> '{}')) not between 1 and 300
       )
       or (
         select count(distinct pg_catalog.lower(btrim(choice.value #>> '{}')))
         from pg_catalog.jsonb_array_elements(item.question -> 'choices') as choice(value)
       ) <> 4
  ) then
    raise exception '모의 평가 문항 또는 선택지 형식이 올바르지 않습니다.';
  end if;

  if (
    select count(distinct pg_catalog.lower(btrim(item.question ->> 'question')))
    from pg_catalog.jsonb_array_elements(p_questions) as item(question)
  ) <> 15 then
    raise exception '모의 평가 문항은 서로 달라야 합니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_questions)
      with ordinality as item(question, position)
    join public.learning_objectives as objective
      on objective.user_id = v_user_id
     and objective.plan_id = p_plan_id
     and objective.objective_key = item.question ->> 'objective_key'
    where objective.sort_order <> ((item.position - 1) % v_objective_count) + 1
       or item.question ->> 'evidence_key' <> case
         ((item.position - 1) / v_objective_count) % 3
         when 0 then 'explain'
         when 1 then 'apply'
         else 'differentiate'
       end
  ) or exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_questions) as item(question)
    left join public.learning_objectives as objective
      on objective.user_id = v_user_id
     and objective.plan_id = p_plan_id
     and objective.objective_key = item.question ->> 'objective_key'
    where objective.id is null
  ) then
    raise exception '모의 평가 문항 배분이 계획의 학습목표와 일치하지 않습니다.';
  end if;

  if (
    select count(*) filter (where item.question ->> 'difficulty' = 'easy')
    from pg_catalog.jsonb_array_elements(p_questions) as item(question)
  ) <> 4 or (
    select count(*) filter (where item.question ->> 'difficulty' = 'medium')
    from pg_catalog.jsonb_array_elements(p_questions) as item(question)
  ) <> 7 or (
    select count(*) filter (where item.question ->> 'difficulty' = 'hard')
    from pg_catalog.jsonb_array_elements(p_questions) as item(question)
  ) <> 4 then
    raise exception '모의 평가 난이도 배분이 올바르지 않습니다.';
  end if;

  if v_reference_content is null and exists (
    select 1 from pg_catalog.jsonb_array_elements(p_questions) as item(question)
    where item.question ->> 'source_evidence' is not null
  ) then
    raise exception '참고자료가 없는데 원문 근거가 포함됐습니다.';
  end if;
  if v_reference_content is not null and exists (
    select 1 from pg_catalog.jsonb_array_elements(p_questions) as item(question)
    where item.question ->> 'source_evidence' is not null
      and (
        item.question ->> 'source_title' is distinct from v_reference_title
        or pg_catalog.strpos(
          v_reference_content,
          item.question ->> 'source_evidence'
        ) = 0
      )
  ) then
    raise exception '모의 평가의 원문 근거가 선택 자료와 일치하지 않습니다.';
  end if;

  insert into public.mock_exams (
    user_id, plan_id, generation_key, title, objective_snapshot, questions,
    question_count, recommended_minutes, reference_learning_material_id,
    reference_review_material_id, prompt_version, model_name
  ) values (
    v_user_id, p_plan_id, p_generation_key, btrim(p_title),
    v_objective_snapshot, p_questions, 15, p_recommended_minutes,
    p_reference_learning_material_id, p_reference_review_material_id,
    btrim(p_prompt_version), btrim(p_model_name)
  ) returning * into v_saved;

  return pg_catalog.jsonb_build_object(
    'id', v_saved.id,
    'user_id', v_saved.user_id,
    'plan_id', v_saved.plan_id,
    'generation_key', v_saved.generation_key,
    'already_processed', false
  );
end;
$$;

create function public.get_mock_exams_by_plan(p_plan_id uuid)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_result jsonb;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;
  if not exists (
    select 1 from public.study_plans as plan
    where plan.id = p_plan_id and plan.user_id = v_user_id
  ) then
    raise exception '학습계획을 찾을 수 없습니다.';
  end if;

  select coalesce(
    pg_catalog.jsonb_agg(
      pg_catalog.jsonb_build_object(
        'id', exam.id,
        'user_id', exam.user_id,
        'plan_id', exam.plan_id,
        'title', exam.title,
        'question_count', exam.question_count,
        'recommended_minutes', exam.recommended_minutes,
        'attempt_count', stats.attempt_count,
        'best_score', stats.best_score,
        'latest_score', stats.latest_score,
        'created_at', exam.created_at
      ) order by exam.created_at desc
    ),
    '[]'::jsonb
  ) into v_result
  from public.mock_exams as exam
  left join lateral (
    select
      count(attempt.id)::integer as attempt_count,
      max(attempt.score)::integer as best_score,
      (array_agg(attempt.score order by attempt.attempt_number desc))[1]::integer
        as latest_score
    from public.mock_exam_attempts as attempt
    where attempt.user_id = v_user_id
      and attempt.mock_exam_id = exam.id
  ) as stats on true
  where exam.user_id = v_user_id
    and exam.plan_id = p_plan_id;
  return v_result;
end;
$$;

create function public.get_mock_exam_state(p_mock_exam_id uuid)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_exam public.mock_exams%rowtype;
  v_latest public.mock_exam_attempts%rowtype;
  v_attempt_count integer;
  v_best_score integer;
  v_public_questions jsonb;
  v_attempt_history jsonb;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;
  select exam.* into v_exam
  from public.mock_exams as exam
  where exam.id = p_mock_exam_id
    and exam.user_id = v_user_id;
  if not found then
    raise exception '모의 평가를 찾을 수 없습니다.';
  end if;

  select count(*)::integer, max(attempt.score)::integer
  into v_attempt_count, v_best_score
  from public.mock_exam_attempts as attempt
  where attempt.user_id = v_user_id
    and attempt.mock_exam_id = v_exam.id;

  select attempt.* into v_latest
  from public.mock_exam_attempts as attempt
  where attempt.user_id = v_user_id
    and attempt.mock_exam_id = v_exam.id
  order by attempt.attempt_number desc
  limit 1;

  select coalesce(
    pg_catalog.jsonb_agg(
      pg_catalog.jsonb_build_object(
        'attempt_number', recent.attempt_number,
        'correct_count', recent.correct_count,
        'score', recent.score,
        'submitted_at', recent.submitted_at
      ) order by recent.attempt_number
    ),
    '[]'::jsonb
  ) into v_attempt_history
  from (
    select
      attempt.attempt_number,
      attempt.correct_count,
      attempt.score,
      attempt.submitted_at
    from public.mock_exam_attempts as attempt
    where attempt.user_id = v_user_id
      and attempt.mock_exam_id = v_exam.id
    order by attempt.attempt_number desc
    limit 10
  ) as recent;

  select pg_catalog.jsonb_agg(
    item.question
      - 'correct_answer_index'
      - 'explanation'
      - 'source_title'
      - 'source_evidence'
    order by item.position
  ) into v_public_questions
  from pg_catalog.jsonb_array_elements(v_exam.questions)
    with ordinality as item(question, position);

  return pg_catalog.jsonb_build_object(
    'user_id', v_user_id,
    'plan_id', v_exam.plan_id,
    'exam_id', v_exam.id,
    'title', v_exam.title,
    'recommended_minutes', v_exam.recommended_minutes,
    'objective_snapshot', v_exam.objective_snapshot,
    'questions', v_public_questions,
    'attempt_count', v_attempt_count,
    'best_score', v_best_score,
    'attempt_history', v_attempt_history,
    'latest_attempt', case when v_latest.id is null then null else
      pg_catalog.to_jsonb(v_latest) - 'user_id' - 'id'
      || pg_catalog.jsonb_build_object(
        'attempt_id', v_latest.id,
        'already_processed', true
      )
    end,
    'created_at', v_exam.created_at
  );
end;
$$;

create function public.submit_mock_exam_attempt(
  p_mock_exam_id uuid,
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
  v_exam public.mock_exams%rowtype;
  v_existing public.mock_exam_attempts%rowtype;
  v_saved public.mock_exam_attempts%rowtype;
  v_attempt_number integer;
  v_correct_count integer;
  v_score smallint;
  v_question_results jsonb;
  v_objective_scores jsonb;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;
  if p_mock_exam_id is null or p_submission_key is null then
    raise exception '모의 평가와 제출 식별자가 필요합니다.';
  end if;
  if p_answers is null
     or pg_catalog.jsonb_typeof(p_answers) <> 'array'
     or pg_catalog.jsonb_array_length(p_answers) <> 15
     or exists (
       select 1 from pg_catalog.jsonb_array_elements(p_answers) as answer(value)
       where pg_catalog.jsonb_typeof(answer.value) <> 'number'
          or answer.value::text !~ '^[0-3]$'
     ) then
    raise exception '모든 모의 평가 문항에 0부터 3 사이의 답을 선택해주세요.';
  end if;

  select exam.* into v_exam
  from public.mock_exams as exam
  where exam.id = p_mock_exam_id
    and exam.user_id = v_user_id
  for update;
  if not found then
    raise exception '응시할 모의 평가를 찾을 수 없습니다.';
  end if;

  select attempt.* into v_existing
  from public.mock_exam_attempts as attempt
  where attempt.user_id = v_user_id
    and attempt.submission_key = p_submission_key;
  if found then
    if v_existing.mock_exam_id is distinct from p_mock_exam_id
       or v_existing.answers is distinct from p_answers then
      raise exception '같은 제출 식별자를 다른 모의 평가 답안에 사용할 수 없습니다.';
    end if;
    return pg_catalog.to_jsonb(v_existing) - 'user_id' - 'id'
      || pg_catalog.jsonb_build_object(
        'attempt_id', v_existing.id,
        'already_processed', true
      );
  end if;

  select coalesce(max(attempt.attempt_number), 0) + 1
  into v_attempt_number
  from public.mock_exam_attempts as attempt
  where attempt.user_id = v_user_id
    and attempt.mock_exam_id = v_exam.id;

  select
    count(*) filter (
      where p_answers -> ((item.position - 1)::integer)
        = item.question -> 'correct_answer_index'
    )::integer,
    pg_catalog.jsonb_agg(
      pg_catalog.jsonb_build_object(
        'question_index', item.position - 1,
        'objective_key', item.question ->> 'objective_key',
        'evidence_key', item.question ->> 'evidence_key',
        'difficulty', item.question ->> 'difficulty',
        'selected_answer_index',
          (p_answers ->> ((item.position - 1)::integer))::integer,
        'correct_answer_index',
          (item.question ->> 'correct_answer_index')::integer,
        'is_correct', p_answers -> ((item.position - 1)::integer)
          = item.question -> 'correct_answer_index',
        'explanation', item.question ->> 'explanation',
        'source_title', item.question -> 'source_title',
        'source_evidence', item.question -> 'source_evidence'
      ) order by item.position
    )
  into v_correct_count, v_question_results
  from pg_catalog.jsonb_array_elements(v_exam.questions)
    with ordinality as item(question, position);

  v_score := pg_catalog.round(v_correct_count * 100.0 / 15)::smallint;

  select pg_catalog.jsonb_agg(
    pg_catalog.jsonb_build_object(
      'objective_key', grouped.objective_key,
      'correct_count', grouped.correct_count,
      'total_questions', grouped.total_questions,
      'score', pg_catalog.round(
        grouped.correct_count * 100.0 / grouped.total_questions
      )::smallint
    ) order by grouped.first_position
  ) into v_objective_scores
  from (
    select
      item.question ->> 'objective_key' as objective_key,
      count(*) filter (
        where p_answers -> ((item.position - 1)::integer)
          = item.question -> 'correct_answer_index'
      )::integer as correct_count,
      count(*)::integer as total_questions,
      min(item.position) as first_position
    from pg_catalog.jsonb_array_elements(v_exam.questions)
      with ordinality as item(question, position)
    group by item.question ->> 'objective_key'
  ) as grouped;

  insert into public.mock_exam_attempts (
    user_id, mock_exam_id, submission_key, attempt_number, answers,
    correct_count, total_questions, score, objective_scores, question_results
  ) values (
    v_user_id, v_exam.id, p_submission_key, v_attempt_number, p_answers,
    v_correct_count, 15, v_score, v_objective_scores, v_question_results
  ) returning * into v_saved;

  return pg_catalog.to_jsonb(v_saved) - 'user_id' - 'id'
    || pg_catalog.jsonb_build_object(
      'attempt_id', v_saved.id,
      'already_processed', false
    );
end;
$$;

revoke all on function public.save_mock_exam(
  uuid, uuid, text, integer, jsonb, text, text, uuid, uuid
) from public, anon, authenticated;
revoke all on function public.get_mock_exams_by_plan(uuid)
  from public, anon, authenticated;
revoke all on function public.get_mock_exam_state(uuid)
  from public, anon, authenticated;
revoke all on function public.submit_mock_exam_attempt(uuid, jsonb, uuid)
  from public, anon, authenticated;

grant execute on function public.save_mock_exam(
  uuid, uuid, text, integer, jsonb, text, text, uuid, uuid
) to authenticated;
grant execute on function public.get_mock_exams_by_plan(uuid)
  to authenticated;
grant execute on function public.get_mock_exam_state(uuid)
  to authenticated;
grant execute on function public.submit_mock_exam_attempt(uuid, jsonb, uuid)
  to authenticated;

comment on table public.mock_exams is
  '학습계획 전체 범위를 반복 연습하는 15문항 시험 대비 모의 평가';
comment on table public.mock_exam_attempts is
  '모의 평가 재응시별 서버 채점 결과이며 EXP와 과제 상태를 변경하지 않음';

commit;
