-- supabase_quiz_diagnosis_personalization.sql 적용 후 실행합니다.
do $$
begin
  if not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'concept_mastery_events'
      and column_name = 'diagnosis_type'
      and data_type = 'text'
  ) then
    raise exception 'concept_mastery_events.diagnosis_type 열이 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_constraint as constraint_info
    join pg_catalog.pg_class as table_info
      on table_info.oid = constraint_info.conrelid
    join pg_catalog.pg_namespace as namespace_info
      on namespace_info.oid = table_info.relnamespace
    where namespace_info.nspname = 'public'
      and table_info.relname = 'concept_mastery_events'
      and constraint_info.conname = (
        'concept_mastery_events_diagnosis_type_check'
      )
  ) then
    raise exception '오답 유형 CHECK 제약이 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_trigger as trigger_info
    join pg_catalog.pg_class as table_info
      on table_info.oid = trigger_info.tgrelid
    join pg_catalog.pg_namespace as namespace_info
      on namespace_info.oid = table_info.relnamespace
    where namespace_info.nspname = 'public'
      and table_info.relname = 'concept_mastery_events'
      and trigger_info.tgname = 'set_concept_mastery_event_diagnosis'
      and not trigger_info.tgisinternal
      and trigger_info.tgenabled <> 'D'
  ) then
    raise exception '오답 유형 기록 트리거가 활성화되지 않았습니다.';
  end if;

  if pg_catalog.has_function_privilege(
    'authenticated',
    'public.set_concept_mastery_event_diagnosis()',
    'EXECUTE'
  ) then
    raise exception '내부 트리거 함수를 authenticated가 직접 실행할 수 있습니다.';
  end if;

  if exists (
    select 1
    from public.concept_mastery_events as event
    where event.diagnosis_type is not null
      and (
        event.is_correct
        or event.diagnosis_type not in (
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
  ) then
    raise exception '허용되지 않은 오답 유형 데이터가 있습니다.';
  end if;

  if exists (
    select 1
    from public.concept_mastery_events as event
    where event.diagnosis_type is not null
      and not exists (
        select 1
        from public.quiz_attempts as attempt
        where attempt.id = event.quiz_attempt_id
          and attempt.quiz_id = event.quiz_id
          and attempt.user_id = event.user_id
          and pg_catalog.jsonb_typeof(attempt.questions_snapshot) = 'array'
          and pg_catalog.jsonb_typeof(attempt.answers) = 'array'
          and event.question_index >= 0
          and event.question_index < pg_catalog.jsonb_array_length(
            attempt.questions_snapshot
          )
          and event.question_index < pg_catalog.jsonb_array_length(
            attempt.answers
          )
          and (
            attempt.questions_snapshot -> event.question_index::integer
          ) #>> array[
            'choice_feedback',
            (attempt.answers ->> event.question_index::integer),
            'diagnosis_type'
          ] = event.diagnosis_type
      )
  ) then
    raise exception '저장된 응시와 일치하지 않는 오답 유형이 있습니다.';
  end if;
end;
$$;

select
  count(*) filter (where not is_correct) as incorrect_event_count,
  count(*) filter (where diagnosis_type is not null) as diagnosed_event_count,
  count(*) filter (
    where not is_correct and diagnosis_type is null
  ) as legacy_undiagnosed_event_count
from public.concept_mastery_events;

select 'quiz diagnosis personalization validation: success'
as validation_result;
