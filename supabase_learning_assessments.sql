begin;

create table public.learning_assessments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  plan_id uuid not null,
  pair_key uuid not null,
  phase text not null check (phase in ('pre', 'post')),
  title text not null check (char_length(btrim(title)) between 1 and 200),
  objective_snapshot jsonb not null
    check (jsonb_typeof(objective_snapshot) = 'array'),
  questions jsonb not null check (jsonb_typeof(questions) = 'array'),
  question_count smallint not null
    constraint learning_assessments_question_count_range_check
    check (question_count between 6 and 15),
  prompt_version text not null
    check (char_length(btrim(prompt_version)) between 1 and 100),
  model_name text not null
    check (char_length(btrim(model_name)) between 1 and 100),
  created_at timestamptz not null default now(),
  constraint learning_assessments_plan_owner_fk
    foreign key (plan_id, user_id)
    references public.study_plans(id, user_id)
    on delete cascade,
  constraint learning_assessments_id_user_unique unique (id, user_id),
  constraint learning_assessments_plan_phase_unique
    unique (user_id, plan_id, phase),
  constraint learning_assessments_pair_phase_unique
    unique (pair_key, phase),
  constraint learning_assessments_questions_length_check
    check (jsonb_array_length(questions) = question_count),
  constraint learning_assessments_objective_count_check
    check (jsonb_array_length(objective_snapshot) between 2 and 5)
);

create table public.learning_assessment_attempts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  assessment_id uuid not null,
  submission_key uuid not null,
  answers jsonb not null check (jsonb_typeof(answers) = 'array'),
  correct_count smallint not null check (correct_count between 0 and 15),
  total_questions smallint not null check (total_questions between 6 and 15),
  score smallint not null check (score between 0 and 100),
  objective_scores jsonb not null
    check (jsonb_typeof(objective_scores) = 'array'),
  question_results jsonb not null
    check (jsonb_typeof(question_results) = 'array'),
  submitted_at timestamptz not null default now(),
  constraint learning_assessment_attempts_assessment_owner_fk
    foreign key (assessment_id, user_id)
    references public.learning_assessments(id, user_id)
    on delete cascade,
  constraint learning_assessment_attempts_official_unique
    unique (user_id, assessment_id),
  constraint learning_assessment_attempts_submission_unique
    unique (user_id, submission_key),
  constraint learning_assessment_attempts_count_check
    check (
      correct_count <= total_questions
      and jsonb_array_length(answers) = total_questions
      and jsonb_array_length(question_results) = total_questions
      and jsonb_array_length(objective_scores) between 2 and 5
    )
);

create index learning_assessments_user_plan_idx
  on public.learning_assessments(user_id, plan_id, phase);

create index learning_assessment_attempts_user_submitted_idx
  on public.learning_assessment_attempts(user_id, submitted_at desc);

alter table public.learning_assessments enable row level security;
alter table public.learning_assessment_attempts enable row level security;

create policy "learning_assessments_select_own"
on public.learning_assessments
for select to authenticated
using ((select auth.uid()) = user_id);

create policy "learning_assessments_insert_own"
on public.learning_assessments
for insert to authenticated
with check ((select auth.uid()) = user_id);

create policy "learning_assessments_update_own"
on public.learning_assessments
for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy "learning_assessments_delete_own"
on public.learning_assessments
for delete to authenticated
using ((select auth.uid()) = user_id);

create policy "learning_assessment_attempts_select_own"
on public.learning_assessment_attempts
for select to authenticated
using ((select auth.uid()) = user_id);

create policy "learning_assessment_attempts_insert_own"
on public.learning_assessment_attempts
for insert to authenticated
with check ((select auth.uid()) = user_id);

create policy "learning_assessment_attempts_update_own"
on public.learning_assessment_attempts
for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy "learning_assessment_attempts_delete_own"
on public.learning_assessment_attempts
for delete to authenticated
using ((select auth.uid()) = user_id);

revoke all on public.learning_assessments from public, anon, authenticated;
revoke all on public.learning_assessment_attempts from public, anon, authenticated;

create function public.save_learning_assessment_pair(
  p_plan_id uuid,
  p_pair_key uuid,
  p_pre_title text,
  p_pre_questions jsonb,
  p_post_title text,
  p_post_questions jsonb,
  p_prompt_version text,
  p_model_name text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_plan public.study_plans%rowtype;
  v_objective_snapshot jsonb;
  v_objective_count integer;
  v_existing_pre public.learning_assessments%rowtype;
  v_existing_post public.learning_assessments%rowtype;
  v_pre public.learning_assessments%rowtype;
  v_post public.learning_assessments%rowtype;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;
  if p_plan_id is null or p_pair_key is null then
    raise exception '학습계획과 평가 쌍 식별자가 필요합니다.';
  end if;
  if p_pre_title is null
     or char_length(btrim(p_pre_title)) not between 1 and 200
     or p_post_title is null
     or char_length(btrim(p_post_title)) not between 1 and 200 then
    raise exception '평가 제목은 1자 이상 200자 이하여야 합니다.';
  end if;
  if p_prompt_version is null
     or char_length(btrim(p_prompt_version)) not between 1 and 100
     or p_model_name is null
     or char_length(btrim(p_model_name)) not between 1 and 100 then
    raise exception '평가 생성 버전 정보가 올바르지 않습니다.';
  end if;

  select plan.*
  into v_plan
  from public.study_plans as plan
  where plan.id = p_plan_id
    and plan.user_id = v_user_id
  for update;

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
        )
        order by objective.sort_order
      ),
      '[]'::jsonb
    )
  into v_objective_count, v_objective_snapshot
  from public.learning_objectives as objective
  where objective.plan_id = p_plan_id
    and objective.user_id = v_user_id;

  if v_objective_count not between 2 and 5 then
    raise exception '평가에는 2개 이상 5개 이하의 학습목표가 필요합니다.';
  end if;

  select assessment.*
  into v_existing_pre
  from public.learning_assessments as assessment
  where assessment.user_id = v_user_id
    and assessment.plan_id = p_plan_id
    and assessment.phase = 'pre';

  select assessment.*
  into v_existing_post
  from public.learning_assessments as assessment
  where assessment.user_id = v_user_id
    and assessment.plan_id = p_plan_id
    and assessment.phase = 'post';

  if v_existing_pre.id is not null or v_existing_post.id is not null then
    if v_existing_pre.id is null
       or v_existing_post.id is null
       or v_existing_pre.pair_key is distinct from p_pair_key
       or v_existing_post.pair_key is distinct from p_pair_key
       or v_existing_pre.title is distinct from btrim(p_pre_title)
       or v_existing_post.title is distinct from btrim(p_post_title)
       or v_existing_pre.questions is distinct from p_pre_questions
       or v_existing_post.questions is distinct from p_post_questions
       or v_existing_pre.prompt_version is distinct from btrim(p_prompt_version)
       or v_existing_post.prompt_version is distinct from btrim(p_prompt_version)
       or v_existing_pre.model_name is distinct from btrim(p_model_name)
       or v_existing_post.model_name is distinct from btrim(p_model_name)
    then
      raise exception '이미 다른 사전·사후 평가가 저장된 계획입니다.';
    end if;

    return pg_catalog.jsonb_build_object(
      'user_id', v_user_id,
      'plan_id', p_plan_id,
      'pair_key', p_pair_key,
      'pre_assessment_id', v_existing_pre.id,
      'post_assessment_id', v_existing_post.id,
      'already_processed', true
    );
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    where task.plan_id = p_plan_id
      and task.user_id = v_user_id
      and task.status = 'completed'
  ) or exists (
    select 1
    from public.quiz_attempts as attempt
    join public.quizzes as quiz
      on quiz.id = attempt.quiz_id
     and quiz.user_id = attempt.user_id
    where quiz.plan_id = p_plan_id
      and quiz.user_id = v_user_id
  ) then
    raise exception '학습을 시작한 계획에는 사전 평가를 새로 만들 수 없습니다.';
  end if;

  if p_pre_questions is null
     or pg_catalog.jsonb_typeof(p_pre_questions) <> 'array'
     or pg_catalog.jsonb_array_length(p_pre_questions) not between 6 and 15
     or p_post_questions is null
     or pg_catalog.jsonb_typeof(p_post_questions) <> 'array'
     or pg_catalog.jsonb_array_length(p_post_questions)
          <> pg_catalog.jsonb_array_length(p_pre_questions) then
    raise exception '사전·사후 평가 문항 수가 올바르지 않습니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_pre_questions || p_post_questions)
      as item(question)
    where pg_catalog.jsonb_typeof(item.question) <> 'object'
       or pg_catalog.jsonb_typeof(item.question -> 'question') <> 'string'
       or char_length(btrim(item.question ->> 'question')) not between 1 and 500
       or pg_catalog.jsonb_typeof(item.question -> 'choices') <> 'array'
       or pg_catalog.jsonb_array_length(item.question -> 'choices') <> 4
       or pg_catalog.jsonb_typeof(item.question -> 'correct_answer_index')
            <> 'number'
       or (item.question -> 'correct_answer_index')::text !~ '^[0-3]$'
       or pg_catalog.jsonb_typeof(item.question -> 'explanation') <> 'string'
       or char_length(btrim(item.question ->> 'explanation'))
            not between 1 and 1000
       or pg_catalog.jsonb_typeof(item.question -> 'objective_key') <> 'string'
       or (item.question ->> 'objective_key')
            !~ '^[a-z0-9]+(?:_[a-z0-9]+)*$'
       or item.question ->> 'evidence_key'
            not in ('explain', 'apply', 'differentiate')
       or item.question ->> 'target_depth'
            not in ('foundation', 'developing', 'advanced')
       or exists (
         select 1
         from pg_catalog.jsonb_array_elements(item.question -> 'choices')
           as choice(value)
         where pg_catalog.jsonb_typeof(choice.value) <> 'string'
            or char_length(btrim(choice.value #>> '{}')) not between 1 and 300
       )
       or (
         select count(distinct pg_catalog.lower(btrim(choice.value #>> '{}')))
         from pg_catalog.jsonb_array_elements(item.question -> 'choices')
           as choice(value)
       ) <> 4
  ) then
    raise exception '평가 문항 또는 선택지 형식이 올바르지 않습니다.';
  end if;

  if exists (
    select 1
    from (
      select
        item.question ->> 'objective_key' as objective_key,
        item.question ->> 'target_depth' as target_depth,
        count(*) as question_count,
        count(distinct item.question ->> 'evidence_key') as evidence_count
      from pg_catalog.jsonb_array_elements(p_pre_questions)
        as item(question)
      group by 1, 2
    ) as measured
    left join public.learning_objectives as objective
      on objective.user_id = v_user_id
     and objective.plan_id = p_plan_id
     and objective.objective_key = measured.objective_key
     and objective.target_depth = measured.target_depth
    where objective.id is null
       or measured.question_count <> 3
       or measured.evidence_count <> 3
  ) or (
    select count(distinct item.question ->> 'objective_key')
    from pg_catalog.jsonb_array_elements(p_pre_questions) as item(question)
  ) <> v_objective_count then
    raise exception '사전 평가가 계획의 학습목표 계약과 일치하지 않습니다.';
  end if;

  if (
    select pg_catalog.jsonb_agg(
      pg_catalog.jsonb_build_array(
        item.question ->> 'objective_key',
        item.question ->> 'evidence_key',
        item.question ->> 'target_depth'
      )
      order by item.position
    )
    from pg_catalog.jsonb_array_elements(p_pre_questions)
      with ordinality as item(question, position)
  ) is distinct from (
    select pg_catalog.jsonb_agg(
      pg_catalog.jsonb_build_array(
        item.question ->> 'objective_key',
        item.question ->> 'evidence_key',
        item.question ->> 'target_depth'
      )
      order by item.position
    )
    from pg_catalog.jsonb_array_elements(p_post_questions)
      with ordinality as item(question, position)
  ) then
    raise exception '사전·사후 평가의 측정 계약이 일치하지 않습니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_pre_questions)
      with ordinality as item(question, position)
    join public.learning_objectives as objective
      on objective.user_id = v_user_id
     and objective.plan_id = p_plan_id
     and objective.objective_key = item.question ->> 'objective_key'
    where ((item.position - 1) / 3 + 1) <> objective.sort_order
       or item.question ->> 'evidence_key' <> case (item.position - 1) % 3
         when 0 then 'explain'
         when 1 then 'apply'
         else 'differentiate'
       end
  ) then
    raise exception '평가 문항 순서가 학습목표와 성공 기준 순서에 맞지 않습니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_post_questions)
      with ordinality as post_item(question, position)
    join pg_catalog.jsonb_array_elements(p_pre_questions)
      with ordinality as pre_item(question, position)
      on pg_catalog.lower(btrim(pre_item.question ->> 'question'))
       = pg_catalog.lower(btrim(post_item.question ->> 'question'))
  ) then
    raise exception '사전·사후 평가는 서로 다른 문항이어야 합니다.';
  end if;

  insert into public.learning_assessments (
    user_id,
    plan_id,
    pair_key,
    phase,
    title,
    objective_snapshot,
    questions,
    question_count,
    prompt_version,
    model_name
  )
  values (
    v_user_id,
    p_plan_id,
    p_pair_key,
    'pre',
    btrim(p_pre_title),
    v_objective_snapshot,
    p_pre_questions,
    pg_catalog.jsonb_array_length(p_pre_questions),
    btrim(p_prompt_version),
    btrim(p_model_name)
  )
  returning * into v_pre;

  insert into public.learning_assessments (
    user_id,
    plan_id,
    pair_key,
    phase,
    title,
    objective_snapshot,
    questions,
    question_count,
    prompt_version,
    model_name
  )
  values (
    v_user_id,
    p_plan_id,
    p_pair_key,
    'post',
    btrim(p_post_title),
    v_objective_snapshot,
    p_post_questions,
    pg_catalog.jsonb_array_length(p_post_questions),
    btrim(p_prompt_version),
    btrim(p_model_name)
  )
  returning * into v_post;

  return pg_catalog.jsonb_build_object(
    'user_id', v_user_id,
    'plan_id', p_plan_id,
    'pair_key', p_pair_key,
    'pre_assessment_id', v_pre.id,
    'post_assessment_id', v_post.id,
    'already_processed', false
  );
end;
$$;

create function public.get_learning_assessment_state(p_plan_id uuid)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_plan public.study_plans%rowtype;
  v_pre public.learning_assessments%rowtype;
  v_post public.learning_assessments%rowtype;
  v_pre_attempt public.learning_assessment_attempts%rowtype;
  v_post_attempt public.learning_assessment_attempts%rowtype;
  v_task_count integer;
  v_completed_count integer;
  v_has_learning_activity boolean;
  v_period_finished boolean;
  v_can_generate boolean;
  v_pre_eligible boolean;
  v_post_eligible boolean;
  v_today date := (pg_catalog.timezone(
    'Asia/Seoul',
    pg_catalog.statement_timestamp()
  ))::date;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;
  if p_plan_id is null then
    raise exception '학습계획 ID가 필요합니다.';
  end if;

  select plan.*
  into v_plan
  from public.study_plans as plan
  where plan.id = p_plan_id
    and plan.user_id = v_user_id;
  if not found then
    raise exception '학습계획을 찾을 수 없습니다.';
  end if;

  select
    count(*)::integer,
    count(*) filter (where task.status = 'completed')::integer
  into v_task_count, v_completed_count
  from public.study_tasks as task
  where task.plan_id = p_plan_id
    and task.user_id = v_user_id;

  v_has_learning_activity := v_completed_count > 0 or exists (
    select 1
    from public.quiz_attempts as attempt
    join public.quizzes as quiz
      on quiz.id = attempt.quiz_id
     and quiz.user_id = attempt.user_id
    where quiz.plan_id = p_plan_id
      and quiz.user_id = v_user_id
  );
  v_period_finished := v_today >= v_plan.target_date
    or (v_task_count > 0 and v_completed_count = v_task_count);

  select assessment.* into v_pre
  from public.learning_assessments as assessment
  where assessment.user_id = v_user_id
    and assessment.plan_id = p_plan_id
    and assessment.phase = 'pre';

  select assessment.* into v_post
  from public.learning_assessments as assessment
  where assessment.user_id = v_user_id
    and assessment.plan_id = p_plan_id
    and assessment.phase = 'post';

  if v_pre.id is not null then
    select attempt.* into v_pre_attempt
    from public.learning_assessment_attempts as attempt
    where attempt.user_id = v_user_id
      and attempt.assessment_id = v_pre.id;
  end if;
  if v_post.id is not null then
    select attempt.* into v_post_attempt
    from public.learning_assessment_attempts as attempt
    where attempt.user_id = v_user_id
      and attempt.assessment_id = v_post.id;
  end if;

  v_can_generate := v_pre.id is null and not v_has_learning_activity;
  v_pre_eligible := v_pre.id is not null
    and v_pre_attempt.id is null
    and not v_has_learning_activity;
  v_post_eligible := v_post.id is not null
    and v_pre_attempt.id is not null
    and v_post_attempt.id is null
    and v_period_finished;

  return pg_catalog.jsonb_build_object(
    'user_id', v_user_id,
    'plan_id', p_plan_id,
    'today', v_today,
    'task_count', v_task_count,
    'completed_task_count', v_completed_count,
    'has_learning_activity', v_has_learning_activity,
    'period_finished', v_period_finished,
    'can_generate', v_can_generate,
    'pre_eligible', v_pre_eligible,
    'post_eligible', v_post_eligible,
    'pre_reason', case
      when v_pre_attempt.id is not null then '사전 진단을 완료했습니다.'
      when v_has_learning_activity then '학습을 시작한 계획은 사전 진단을 새로 응시할 수 없습니다.'
      when v_pre.id is null then '사전·사후 평가를 먼저 생성해주세요.'
      else null
    end,
    'post_reason', case
      when v_post_attempt.id is not null then '사후 평가를 완료했습니다.'
      when v_pre_attempt.id is null then '사전 진단을 먼저 완료해주세요.'
      when not v_period_finished then '계획 종료일 또는 모든 과제 완료 후 응시할 수 있습니다.'
      else null
    end,
    'pre_assessment', case when v_pre.id is null then null else
      pg_catalog.jsonb_build_object(
        'id', v_pre.id,
        'phase', v_pre.phase,
        'title', v_pre.title,
        'question_count', v_pre.question_count,
        'objective_snapshot', v_pre.objective_snapshot,
        'questions', case
          when v_pre_attempt.id is not null then v_pre.questions
          when v_pre_eligible then (
            select pg_catalog.jsonb_agg(
              item.question - 'correct_answer_index' - 'explanation'
              order by item.position
            )
            from pg_catalog.jsonb_array_elements(v_pre.questions)
              with ordinality as item(question, position)
          )
          else null
        end,
        'created_at', v_pre.created_at
      )
    end,
    'post_assessment', case when v_post.id is null then null else
      pg_catalog.jsonb_build_object(
        'id', v_post.id,
        'phase', v_post.phase,
        'title', v_post.title,
        'question_count', v_post.question_count,
        'objective_snapshot', v_post.objective_snapshot,
        'questions', case
          when v_post_attempt.id is not null then v_post.questions
          when v_post_eligible then (
            select pg_catalog.jsonb_agg(
              item.question - 'correct_answer_index' - 'explanation'
              order by item.position
            )
            from pg_catalog.jsonb_array_elements(v_post.questions)
              with ordinality as item(question, position)
          )
          else null
        end,
        'created_at', v_post.created_at
      )
    end,
    'pre_attempt', case when v_pre_attempt.id is null then null else
      pg_catalog.to_jsonb(v_pre_attempt) - 'user_id' - 'id'
      || pg_catalog.jsonb_build_object(
        'attempt_id', v_pre_attempt.id,
        'phase', 'pre',
        'already_processed', true
      )
    end,
    'post_attempt', case when v_post_attempt.id is null then null else
      pg_catalog.to_jsonb(v_post_attempt) - 'user_id' - 'id'
      || pg_catalog.jsonb_build_object(
        'attempt_id', v_post_attempt.id,
        'phase', 'post',
        'already_processed', true
      )
    end
  );
end;
$$;

create function public.submit_learning_assessment_attempt(
  p_assessment_id uuid,
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
  v_assessment public.learning_assessments%rowtype;
  v_plan public.study_plans%rowtype;
  v_existing public.learning_assessment_attempts%rowtype;
  v_attempt public.learning_assessment_attempts%rowtype;
  v_task_count integer;
  v_completed_count integer;
  v_has_learning_activity boolean;
  v_pre_completed boolean;
  v_period_finished boolean;
  v_correct_count integer;
  v_score smallint;
  v_question_results jsonb;
  v_objective_scores jsonb;
  v_today date := (pg_catalog.timezone(
    'Asia/Seoul',
    pg_catalog.statement_timestamp()
  ))::date;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;
  if p_assessment_id is null or p_submission_key is null then
    raise exception '평가와 제출 식별자가 필요합니다.';
  end if;
  if p_answers is null or pg_catalog.jsonb_typeof(p_answers) <> 'array' then
    raise exception '평가 답안은 JSON 배열이어야 합니다.';
  end if;

  perform 1
  from public.profiles as profile
  where profile.id = v_user_id
  for update;
  if not found then
    raise exception '사용자 프로필을 찾을 수 없습니다.';
  end if;

  select assessment.* into v_assessment
  from public.learning_assessments as assessment
  where assessment.id = p_assessment_id
    and assessment.user_id = v_user_id
  for update;
  if not found then
    raise exception '응시할 평가를 찾을 수 없습니다.';
  end if;

  select attempt.* into v_existing
  from public.learning_assessment_attempts as attempt
  where attempt.user_id = v_user_id
    and attempt.submission_key = p_submission_key;
  if found then
    if v_existing.assessment_id is distinct from p_assessment_id
       or v_existing.answers is distinct from p_answers then
      raise exception '같은 제출 식별 키를 다른 답안에 사용할 수 없습니다.';
    end if;
    return pg_catalog.to_jsonb(v_existing)
      - 'user_id'
      - 'id'
      || pg_catalog.jsonb_build_object(
        'attempt_id', v_existing.id,
        'phase', v_assessment.phase,
        'already_processed', true
      );
  end if;

  if exists (
    select 1
    from public.learning_assessment_attempts as attempt
    where attempt.user_id = v_user_id
      and attempt.assessment_id = p_assessment_id
  ) then
    raise exception '공식 평가는 한 번만 제출할 수 있습니다.';
  end if;

  select plan.* into v_plan
  from public.study_plans as plan
  where plan.id = v_assessment.plan_id
    and plan.user_id = v_user_id
  for key share;
  if not found then
    raise exception '평가와 연결된 학습계획을 찾을 수 없습니다.';
  end if;

  select
    count(*)::integer,
    count(*) filter (where task.status = 'completed')::integer
  into v_task_count, v_completed_count
  from public.study_tasks as task
  where task.plan_id = v_assessment.plan_id
    and task.user_id = v_user_id;

  v_has_learning_activity := v_completed_count > 0 or exists (
    select 1
    from public.quiz_attempts as attempt
    join public.quizzes as quiz
      on quiz.id = attempt.quiz_id
     and quiz.user_id = attempt.user_id
    where quiz.plan_id = v_assessment.plan_id
      and quiz.user_id = v_user_id
  );
  v_pre_completed := exists (
    select 1
    from public.learning_assessment_attempts as attempt
    join public.learning_assessments as assessment
      on assessment.id = attempt.assessment_id
     and assessment.user_id = attempt.user_id
    where assessment.plan_id = v_assessment.plan_id
      and assessment.user_id = v_user_id
      and assessment.phase = 'pre'
  );
  v_period_finished := v_today >= v_plan.target_date
    or (v_task_count > 0 and v_completed_count = v_task_count);

  if v_assessment.phase = 'pre' and v_has_learning_activity then
    raise exception '학습을 시작한 계획의 사전 진단은 제출할 수 없습니다.';
  end if;
  if v_assessment.phase = 'post'
     and (not v_pre_completed or not v_period_finished) then
    raise exception '사전 진단과 학습 기간을 마친 뒤 사후 평가를 제출할 수 있습니다.';
  end if;

  if pg_catalog.jsonb_array_length(p_answers) <> v_assessment.question_count
     or exists (
       select 1
       from pg_catalog.jsonb_array_elements(p_answers) as answer(value)
       where pg_catalog.jsonb_typeof(answer.value) <> 'number'
          or answer.value::text !~ '^[0-3]$'
     ) then
    raise exception '모든 문항에 0부터 3 사이의 답을 선택해주세요.';
  end if;

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
        'selected_answer_index',
          (p_answers ->> ((item.position - 1)::integer))::integer,
        'correct_answer_index',
          (item.question ->> 'correct_answer_index')::integer,
        'is_correct', p_answers -> ((item.position - 1)::integer)
          = item.question -> 'correct_answer_index',
        'explanation', item.question ->> 'explanation'
      )
      order by item.position
    )
  into v_correct_count, v_question_results
  from pg_catalog.jsonb_array_elements(v_assessment.questions)
    with ordinality as item(question, position);

  v_score := pg_catalog.round(
    v_correct_count * 100.0 / v_assessment.question_count
  )::smallint;

  select pg_catalog.jsonb_agg(
    pg_catalog.jsonb_build_object(
      'objective_key', grouped.objective_key,
      'correct_count', grouped.correct_count,
      'total_questions', grouped.total_questions,
      'score', pg_catalog.round(
        grouped.correct_count * 100.0 / grouped.total_questions
      )::smallint
    )
    order by grouped.first_position
  )
  into v_objective_scores
  from (
    select
      item.question ->> 'objective_key' as objective_key,
      count(*) filter (
        where p_answers -> ((item.position - 1)::integer)
          = item.question -> 'correct_answer_index'
      )::integer as correct_count,
      count(*)::integer as total_questions,
      min(item.position) as first_position
    from pg_catalog.jsonb_array_elements(v_assessment.questions)
      with ordinality as item(question, position)
    group by item.question ->> 'objective_key'
  ) as grouped;

  insert into public.learning_assessment_attempts (
    user_id,
    assessment_id,
    submission_key,
    answers,
    correct_count,
    total_questions,
    score,
    objective_scores,
    question_results
  )
  values (
    v_user_id,
    v_assessment.id,
    p_submission_key,
    p_answers,
    v_correct_count,
    v_assessment.question_count,
    v_score,
    v_objective_scores,
    v_question_results
  )
  returning * into v_attempt;

  return pg_catalog.to_jsonb(v_attempt)
    - 'user_id'
    - 'id'
    || pg_catalog.jsonb_build_object(
      'attempt_id', v_attempt.id,
      'phase', v_assessment.phase,
      'already_processed', false
    );
end;
$$;

revoke all on function public.save_learning_assessment_pair(
  uuid, uuid, text, jsonb, text, jsonb, text, text
) from public, anon;
revoke all on function public.get_learning_assessment_state(uuid)
from public, anon;
revoke all on function public.submit_learning_assessment_attempt(
  uuid, jsonb, uuid
) from public, anon;

grant execute on function public.save_learning_assessment_pair(
  uuid, uuid, text, jsonb, text, jsonb, text, text
) to authenticated;
grant execute on function public.get_learning_assessment_state(uuid)
to authenticated;
grant execute on function public.submit_learning_assessment_attempt(
  uuid, jsonb, uuid
) to authenticated;

commit;
