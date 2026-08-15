begin;

-- 새 퀴즈의 문항별 대표 개념과 퀴즈 본문을 한 트랜잭션으로 저장합니다.
-- 기존 태그 없는 퀴즈는 변경하지 않으며 계속 조회·응시할 수 있습니다.
create or replace function public.save_quiz_with_concepts(
  p_plan_id uuid,
  p_task_id uuid,
  p_course_key text,
  p_course_name text,
  p_title text,
  p_questions jsonb,
  p_concepts jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_plan_course_name text;
  v_task_type text;
  v_concept jsonb;
  v_question jsonb;
  v_concept_id uuid;
  v_saved_alias_concept_id uuid;
  v_existing_concept_key text;
  v_saved_questions jsonb := '[]'::jsonb;
  v_quiz public.quizzes%rowtype;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  if p_plan_id is null or p_task_id is null then
    raise exception '학습계획과 퀴즈 과제 ID가 필요합니다.';
  end if;

  select
    plan.course_name,
    task.task_type
  into
    v_plan_course_name,
    v_task_type
  from public.study_tasks as task
  join public.study_plans as plan
    on plan.id = task.plan_id
   and plan.user_id = task.user_id
  where task.id = p_task_id
    and task.plan_id = p_plan_id
    and task.user_id = v_user_id
  for update of task, plan;

  if not found then
    raise exception '소유한 학습계획의 과제를 찾을 수 없습니다.';
  end if;

  if v_task_type <> 'quiz' then
    raise exception '퀴즈는 quiz 유형 과제에만 저장할 수 있습니다.';
  end if;

  if p_course_name is null
     or btrim(p_course_name) <> btrim(v_plan_course_name)
  then
    raise exception '학습계획의 과목 정보가 일치하지 않습니다.';
  end if;

  if p_course_key is null
     or char_length(btrim(p_course_key)) not between 1 and 120
  then
    raise exception '과목 키는 1자 이상 120자 이하여야 합니다.';
  end if;

  if p_title is null
     or char_length(btrim(p_title)) not between 1 and 200
  then
    raise exception '퀴즈 제목은 1자 이상 200자 이하여야 합니다.';
  end if;

  if p_questions is null
     or pg_catalog.jsonb_typeof(p_questions) <> 'array'
     or pg_catalog.jsonb_array_length(p_questions) not between 1 and 20
  then
    raise exception '퀴즈 문항은 1개 이상 20개 이하의 배열이어야 합니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_questions)
      as question(value)
    where pg_catalog.jsonb_typeof(question.value)
            is distinct from 'object'
       or pg_catalog.jsonb_typeof(question.value -> 'question')
            is distinct from 'string'
       or char_length(btrim(question.value ->> 'question'))
            not between 1 and 500
       or pg_catalog.jsonb_typeof(question.value -> 'choices')
            is distinct from 'array'
       or pg_catalog.jsonb_array_length(question.value -> 'choices') <> 4
       or pg_catalog.jsonb_typeof(
            question.value -> 'correct_answer_index'
          ) is distinct from 'number'
       or (question.value -> 'correct_answer_index')::text
            !~ '^[0-3]$'
       or pg_catalog.jsonb_typeof(question.value -> 'explanation')
            is distinct from 'string'
       or char_length(btrim(question.value ->> 'explanation'))
            not between 1 and 1000
       or pg_catalog.jsonb_typeof(question.value -> 'concept_key')
            is distinct from 'string'
       or (question.value ->> 'concept_key')
            !~ '^[a-z0-9]+(_[a-z0-9]+)*$'
       or char_length(question.value ->> 'concept_key')
            not between 1 and 100
       or pg_catalog.jsonb_typeof(question.value -> 'concept_name')
            is distinct from 'string'
       or char_length(btrim(question.value ->> 'concept_name'))
            not between 1 and 100
  ) then
    raise exception '퀴즈 문항 또는 개념 태그 형식이 올바르지 않습니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_questions)
      as question(value)
    cross join lateral pg_catalog.jsonb_array_elements(
      question.value -> 'choices'
    ) as choice(value)
    where pg_catalog.jsonb_typeof(choice.value) <> 'string'
       or char_length(btrim(choice.value #>> '{}'))
            not between 1 and 300
  ) then
    raise exception '각 선택지는 1자 이상 300자 이하의 문자열이어야 합니다.';
  end if;

  if p_concepts is null
     or pg_catalog.jsonb_typeof(p_concepts) <> 'array'
     or pg_catalog.jsonb_array_length(p_concepts) not between 1 and 20
  then
    raise exception '저장할 개념 목록 형식이 올바르지 않습니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_concepts)
      as concept(value)
    where pg_catalog.jsonb_typeof(concept.value)
            is distinct from 'object'
       or pg_catalog.jsonb_typeof(concept.value -> 'concept_key')
            is distinct from 'string'
       or (concept.value ->> 'concept_key')
            !~ '^[a-z0-9]+(_[a-z0-9]+)*$'
       or char_length(concept.value ->> 'concept_key')
            not between 1 and 100
       or pg_catalog.jsonb_typeof(concept.value -> 'concept_name')
            is distinct from 'string'
       or char_length(btrim(concept.value ->> 'concept_name'))
            not between 1 and 100
       or pg_catalog.jsonb_typeof(
            concept.value -> 'normalized_alias'
          ) is distinct from 'string'
       or char_length(btrim(concept.value ->> 'normalized_alias'))
            not between 1 and 120
  ) then
    raise exception '저장할 개념의 필드 형식이 올바르지 않습니다.';
  end if;

  if exists (
    select concept.value ->> 'concept_key'
    from pg_catalog.jsonb_array_elements(p_concepts)
      as concept(value)
    group by concept.value ->> 'concept_key'
    having count(*) > 1
  ) then
    raise exception '같은 개념 키가 중복되었습니다.';
  end if;

  if exists (
    select concept.value ->> 'normalized_alias'
    from pg_catalog.jsonb_array_elements(p_concepts)
      as concept(value)
    group by concept.value ->> 'normalized_alias'
    having count(distinct concept.value ->> 'concept_key') > 1
  ) then
    raise exception '같은 개념 별칭이 서로 다른 개념 키에 연결되었습니다.';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_questions)
      as question(value)
    where not exists (
      select 1
      from pg_catalog.jsonb_array_elements(p_concepts)
        as concept(value)
      where concept.value ->> 'concept_key'
              = question.value ->> 'concept_key'
        and concept.value ->> 'concept_name'
              = question.value ->> 'concept_name'
    )
  ) then
    raise exception '문항의 개념 태그가 저장할 개념 목록과 일치하지 않습니다.';
  end if;

  for v_concept in
    select concept.value
    from pg_catalog.jsonb_array_elements(p_concepts)
      as concept(value)
  loop
    select learning_concept.concept_key
    into v_existing_concept_key
    from public.concept_aliases as alias
    join public.learning_concepts as learning_concept
      on learning_concept.id = alias.concept_id
     and learning_concept.user_id = alias.user_id
     and learning_concept.course_key = alias.course_key
    where alias.user_id = v_user_id
      and alias.course_key = btrim(p_course_key)
      and alias.normalized_alias
            = v_concept ->> 'normalized_alias';

    if found
       and v_existing_concept_key
            <> v_concept ->> 'concept_key'
    then
      raise exception
        '기존 개념 별칭과 다른 개념 키가 생성되었습니다: %',
        v_concept ->> 'concept_name';
    end if;

    insert into public.learning_concepts (
      user_id,
      course_key,
      course_name,
      concept_key,
      canonical_name
    )
    values (
      v_user_id,
      btrim(p_course_key),
      v_plan_course_name,
      v_concept ->> 'concept_key',
      btrim(v_concept ->> 'concept_name')
    )
    on conflict (user_id, course_key, concept_key)
    do update set
      course_name = excluded.course_name
    returning id into v_concept_id;

    insert into public.concept_aliases (
      user_id,
      concept_id,
      course_key,
      alias_name,
      normalized_alias
    )
    values (
      v_user_id,
      v_concept_id,
      btrim(p_course_key),
      btrim(v_concept ->> 'concept_name'),
      v_concept ->> 'normalized_alias'
    )
    on conflict (user_id, course_key, normalized_alias)
    do update set
      alias_name = excluded.alias_name
    where concept_aliases.concept_id
            = excluded.concept_id
    returning concept_id into v_saved_alias_concept_id;

    if not found then
      raise exception
        '동일한 개념 별칭이 다른 개념 키에 동시에 연결되었습니다: %',
        v_concept ->> 'concept_name';
    end if;
  end loop;

  -- 개념 UUID는 AI나 클라이언트가 정하지 않고 서버가 확인해 추가합니다.
  for v_question in
    select question.value
    from pg_catalog.jsonb_array_elements(p_questions)
      as question(value)
  loop
    select learning_concept.id
    into v_concept_id
    from public.learning_concepts as learning_concept
    where learning_concept.user_id = v_user_id
      and learning_concept.course_key = btrim(p_course_key)
      and learning_concept.concept_key
            = v_question ->> 'concept_key';

    if not found then
      raise exception '문항에 연결할 정규 개념을 찾을 수 없습니다.';
    end if;

    v_saved_questions := v_saved_questions
      || pg_catalog.jsonb_build_array(
        v_question
        || pg_catalog.jsonb_build_object(
          'concept_id',
          v_concept_id
        )
      );
  end loop;

  insert into public.quizzes (
    user_id,
    plan_id,
    task_id,
    title,
    questions,
    question_count
  )
  values (
    v_user_id,
    p_plan_id,
    p_task_id,
    btrim(p_title),
    v_saved_questions,
    pg_catalog.jsonb_array_length(v_saved_questions)
  )
  on conflict (task_id)
  do update set
    user_id = excluded.user_id,
    plan_id = excluded.plan_id,
    title = excluded.title,
    questions = excluded.questions,
    question_count = excluded.question_count
  returning * into v_quiz;

  return pg_catalog.to_jsonb(v_quiz);
end;
$$;

revoke all on function public.save_quiz_with_concepts(
  uuid,
  uuid,
  text,
  text,
  text,
  jsonb,
  jsonb
) from public, anon;

grant execute on function public.save_quiz_with_concepts(
  uuid,
  uuid,
  text,
  text,
  text,
  jsonb,
  jsonb
) to authenticated;

commit;
