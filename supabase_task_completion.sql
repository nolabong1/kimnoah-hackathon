begin;

create or replace function
public.enforce_quiz_completion_requirement()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
begin
  if new.status = 'completed'
     and old.status is distinct from new.status
     and new.task_type = 'quiz'
  then
    if v_user_id is null then
      raise exception '로그인이 필요합니다.';
    end if;

    if new.user_id <> v_user_id then
      raise exception '본인의 과제만 완료할 수 있습니다.';
    end if;

    perform 1
    from public.quizzes as quiz
    where quiz.task_id = new.id
      and quiz.user_id = v_user_id
    for share;

    if not found then
      raise exception
        '퀴즈를 생성하고 모든 문항을 맞힌 후 완료해주세요.';
    end if;

    if not exists (
      select 1
      from public.quizzes as quiz
      join public.quiz_attempts as attempt
        on attempt.quiz_id = quiz.id
       and attempt.user_id = quiz.user_id
       and attempt.quiz_updated_at = quiz.updated_at
      where quiz.task_id = new.id
        and quiz.user_id = v_user_id
        and attempt.correct_count = quiz.question_count
        and attempt.total_questions = quiz.question_count
    ) then
      raise exception
        '현재 퀴즈의 모든 문항을 맞힌 후 완료해주세요.';
    end if;
  end if;

  return new;
end;
$$;

drop trigger if exists
study_tasks_enforce_quiz_completion
on public.study_tasks;

create trigger study_tasks_enforce_quiz_completion
before update of status
on public.study_tasks
for each row
execute function
public.enforce_quiz_completion_requirement();

revoke all
on function public.enforce_quiz_completion_requirement()
from public, anon, authenticated;


create or replace function public.complete_study_task(
  p_task_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_today date := (now() at time zone 'Asia/Seoul')::date;

  v_task record;
  v_profile record;

  v_task_exp integer := 0;
  v_daily_bonus_exp integer := 0;
  v_new_total_exp integer;
  v_new_streak integer;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  select *
  into v_task
  from public.study_tasks
  where id = p_task_id
    and user_id = v_user_id
  for update;

  if not found then
    raise exception '과제를 찾을 수 없습니다.';
  end if;

  if v_task.status = 'completed' then
    select *
    into v_profile
    from public.profiles
    where id = v_user_id;

    return jsonb_build_object(
      'task_id', v_task.id,
      'task_status', v_task.status,
      'task_exp', 0,
      'daily_bonus_exp', 0,
      'total_exp', v_profile.total_exp,
      'level', v_profile.level,
      'current_streak', v_profile.current_streak,
      'already_completed', true
    );
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      v_user_id::text || ':' || v_today::text,
      0
    )
  );

  update public.study_tasks
  set
    status = 'completed',
    completed_at = now()
  where id = v_task.id
    and user_id = v_user_id;

  insert into public.exp_events (
    user_id,
    event_type,
    source_key,
    amount
  )
  values (
    v_user_id,
    'task_completion',
    'task:' || v_task.id::text,
    10
  )
  on conflict (user_id, source_key) do nothing
  returning amount into v_task_exp;

  v_task_exp := coalesce(v_task_exp, 0);

  insert into public.learning_activity (
    user_id,
    activity_date,
    completed_task_count,
    quiz_submission_count,
    earned_exp,
    all_tasks_completed
  )
  values (
    v_user_id,
    v_today,
    1,
    0,
    v_task_exp,
    false
  )
  on conflict (user_id, activity_date)
  do update set
    completed_task_count =
      public.learning_activity.completed_task_count + 1,
    earned_exp =
      public.learning_activity.earned_exp + excluded.earned_exp,
    updated_at = now();

  if v_task.scheduled_date = v_today
     and not exists (
       select 1
       from public.study_tasks as task
       join public.study_plans as plan
         on plan.id = task.plan_id
        and plan.user_id = task.user_id
       where task.user_id = v_user_id
         and task.scheduled_date = v_today
         and task.status <> 'completed'
         and plan.status = 'active'
     )
  then
    insert into public.exp_events (
      user_id,
      event_type,
      source_key,
      amount
    )
    values (
      v_user_id,
      'daily_completion',
      'daily:' || v_today::text,
      20
    )
    on conflict (user_id, source_key) do nothing
    returning amount into v_daily_bonus_exp;

    v_daily_bonus_exp := coalesce(v_daily_bonus_exp, 0);

    update public.learning_activity
    set
      earned_exp = earned_exp + v_daily_bonus_exp,
      all_tasks_completed = true,
      updated_at = now()
    where user_id = v_user_id
      and activity_date = v_today;
  end if;

  select *
  into v_profile
  from public.profiles
  where id = v_user_id
  for update;

  if v_profile.last_activity_date = v_today then
    v_new_streak := v_profile.current_streak;
  elsif v_profile.last_activity_date = v_today - 1 then
    v_new_streak := v_profile.current_streak + 1;
  else
    v_new_streak := 1;
  end if;

  v_new_total_exp :=
    v_profile.total_exp
    + v_task_exp
    + v_daily_bonus_exp;

  update public.profiles
  set
    total_exp = v_new_total_exp,
    level = (v_new_total_exp / 100) + 1,
    current_streak = v_new_streak,
    longest_streak = greatest(
      longest_streak,
      v_new_streak
    ),
    last_activity_date = v_today
  where id = v_user_id
  returning * into v_profile;

  return jsonb_build_object(
    'task_id', v_task.id,
    'task_status', 'completed',
    'task_exp', v_task_exp,
    'daily_bonus_exp', v_daily_bonus_exp,
    'total_exp', v_profile.total_exp,
    'level', v_profile.level,
    'current_streak', v_profile.current_streak,
    'already_completed', false
  );
end;
$$;

revoke all
on function public.complete_study_task(uuid)
from public, anon;

grant execute
on function public.complete_study_task(uuid)
to authenticated;

commit;
