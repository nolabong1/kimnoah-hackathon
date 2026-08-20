begin;

-- 문항별 숙련도 원장에 서버가 판정한 오답 유형을 함께 보존합니다.
-- 정답과 choice_feedback이 없는 과거 퀴즈는 NULL을 유지합니다.
alter table public.concept_mastery_events
add column if not exists diagnosis_type text;

alter table public.concept_mastery_events
drop constraint if exists concept_mastery_events_diagnosis_type_check;

alter table public.concept_mastery_events
add constraint concept_mastery_events_diagnosis_type_check
check (
  diagnosis_type is null
  or (
    not is_correct
    and diagnosis_type in (
      'concept_confusion',
      'condition_omission',
      'procedure_error',
      'calculation_error',
      'boundary_error',
      'overgeneralization',
      'representation_error',
      'other'
    )
  )
);


-- 클라이언트 값이 아니라 저장된 응시 스냅샷과 답안으로 진단 유형을 계산합니다.
create or replace function public.set_concept_mastery_event_diagnosis()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  v_questions_snapshot jsonb;
  v_answers jsonb;
  v_question jsonb;
  v_selected_index integer;
  v_diagnosis_type text;
begin
  new.diagnosis_type := null;

  if new.is_correct then
    return new;
  end if;

  select
    attempt.questions_snapshot,
    attempt.answers
  into
    v_questions_snapshot,
    v_answers
  from public.quiz_attempts as attempt
  where attempt.id = new.quiz_attempt_id
    and attempt.quiz_id = new.quiz_id
    and attempt.user_id = new.user_id;

  if not found
     or pg_catalog.jsonb_typeof(v_questions_snapshot) <> 'array'
     or pg_catalog.jsonb_typeof(v_answers) <> 'array'
     or new.question_index < 0
     or new.question_index >= pg_catalog.jsonb_array_length(
       v_questions_snapshot
     )
     or new.question_index >= pg_catalog.jsonb_array_length(v_answers)
     or pg_catalog.jsonb_typeof(
       v_answers -> new.question_index::integer
     ) <> 'number'
     or (v_answers ->> new.question_index::integer) !~ '^[0-3]$'
  then
    return new;
  end if;

  v_question := v_questions_snapshot -> new.question_index::integer;
  v_selected_index := (
    v_answers ->> new.question_index::integer
  )::integer;

  if pg_catalog.jsonb_typeof(v_question -> 'choice_feedback') <> 'array'
     or pg_catalog.jsonb_array_length(
       v_question -> 'choice_feedback'
     ) <> 4
  then
    return new;
  end if;

  v_diagnosis_type := v_question #>> array[
    'choice_feedback',
    v_selected_index::text,
    'diagnosis_type'
  ];

  if v_diagnosis_type in (
    'concept_confusion',
    'condition_omission',
    'procedure_error',
    'calculation_error',
    'boundary_error',
    'overgeneralization',
    'representation_error',
    'other'
  ) then
    new.diagnosis_type := v_diagnosis_type;
  end if;

  return new;
end;
$$;

revoke all on function public.set_concept_mastery_event_diagnosis()
from public, anon, authenticated;

drop trigger if exists set_concept_mastery_event_diagnosis
on public.concept_mastery_events;

create trigger set_concept_mastery_event_diagnosis
before insert on public.concept_mastery_events
for each row
execute function public.set_concept_mastery_event_diagnosis();


-- 저장된 스냅샷으로 확인 가능한 과거 오답 이벤트만 보강합니다.
with diagnosis_candidates as (
  select
    event.id,
    (
      attempt.questions_snapshot -> event.question_index::integer
    ) #>> array[
      'choice_feedback',
      (attempt.answers ->> event.question_index::integer),
      'diagnosis_type'
    ] as diagnosis_type
  from public.concept_mastery_events as event
  join public.quiz_attempts as attempt
    on attempt.id = event.quiz_attempt_id
   and attempt.quiz_id = event.quiz_id
   and attempt.user_id = event.user_id
  where not event.is_correct
    and event.diagnosis_type is null
    and pg_catalog.jsonb_typeof(attempt.questions_snapshot) = 'array'
    and pg_catalog.jsonb_typeof(attempt.answers) = 'array'
    and event.question_index >= 0
    and event.question_index < pg_catalog.jsonb_array_length(
      attempt.questions_snapshot
    )
    and event.question_index < pg_catalog.jsonb_array_length(
      attempt.answers
    )
    and pg_catalog.jsonb_typeof(
      attempt.answers -> event.question_index::integer
    ) = 'number'
    and (attempt.answers ->> event.question_index::integer) ~ '^[0-3]$'
    and pg_catalog.jsonb_typeof(
      (
        attempt.questions_snapshot -> event.question_index::integer
      ) -> 'choice_feedback'
    ) = 'array'
    and pg_catalog.jsonb_array_length(
      (
        attempt.questions_snapshot -> event.question_index::integer
      ) -> 'choice_feedback'
    ) = 4
)
update public.concept_mastery_events as event
set diagnosis_type = candidate.diagnosis_type
from diagnosis_candidates as candidate
where event.id = candidate.id
  and candidate.diagnosis_type in (
    'concept_confusion',
    'condition_omission',
    'procedure_error',
    'calculation_error',
    'boundary_error',
    'overgeneralization',
    'representation_error',
    'other'
  );

commit;
