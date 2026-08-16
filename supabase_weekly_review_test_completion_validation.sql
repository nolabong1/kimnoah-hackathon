-- supabase_weekly_review_test_completion.sql 실행 후 사용하는 읽기 전용 검증입니다.
begin;

do $$
declare
  completion_function regprocedure := pg_catalog.to_regprocedure(
    'public.complete_study_plan_for_weekly_review_test(uuid)'
  );
  quiz_trigger_function regprocedure := pg_catalog.to_regprocedure(
    'public.enforce_quiz_completion_requirement()'
  );
  reset_function regprocedure := pg_catalog.to_regprocedure(
    'public.reset_today_test_progress()'
  );
begin
  if completion_function is null then
    raise exception '주간 회고 테스트 완료 RPC가 없습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    where procedure.oid = completion_function
      and procedure.prosecdef
      and coalesce(procedure.proconfig::text, '')
        like '%search_path=%'
  ) then
    raise exception '테스트 완료 RPC의 보안 설정이 올바르지 않습니다.';
  end if;

  if not has_function_privilege(
    'authenticated',
    completion_function,
    'EXECUTE'
  ) then
    raise exception 'authenticated 역할에 테스트 완료 실행 권한이 없습니다.';
  end if;

  if has_function_privilege(
    'anon',
    completion_function,
    'EXECUTE'
  ) then
    raise exception 'anon 역할에 테스트 완료 실행 권한이 남아 있습니다.';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_trigger as trigger
    where trigger.tgrelid = 'public.study_tasks'::regclass
      and trigger.tgname = 'study_tasks_enforce_quiz_completion'
      and trigger.tgfoid = quiz_trigger_function
      and not trigger.tgisinternal
      and trigger.tgenabled <> 'D'
      and pg_catalog.pg_get_triggerdef(trigger.oid)
        ilike '%BEFORE UPDATE OF status ON public.study_tasks%'
  ) then
    raise exception '퀴즈 완료 조건 트리거가 올바르게 연결되지 않았습니다.';
  end if;

  if position(
    'app.weekly_review_test_completion'
    in pg_catalog.pg_get_functiondef(quiz_trigger_function)
  ) = 0 then
    raise exception '퀴즈 완료 트리거에 테스트 전용 플래그 검사가 없습니다.';
  end if;

  if position(
    'auth.uid()'
    in pg_catalog.pg_get_functiondef(completion_function)
  ) = 0 then
    raise exception '테스트 완료 RPC에 사용자 인증 검사가 없습니다.';
  end if;

  if position(
    'on conflict (user_id, source_key) do nothing'
    in lower(pg_catalog.pg_get_functiondef(completion_function))
  ) = 0 then
    raise exception '테스트 완료 RPC에 EXP 중복 방지가 없습니다.';
  end if;

  if reset_function is null then
    raise exception '오늘 테스트 기록 초기화 RPC가 없습니다.';
  end if;
end;
$$;

select 'weekly review test completion validation: success'
as validation_result;

rollback;
