begin;

create or replace function public.reset_today_test_progress()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_today date := (
    now() at time zone 'Asia/Seoul'
  )::date;

  v_task_ids uuid[] := array[]::uuid[];
  v_reset_task_count integer := 0;

  v_removed_task_exp integer := 0;
  v_removed_daily_bonus_exp integer := 0;
  v_new_total_exp integer := 0;

  v_last_activity_date date;
  v_check_date date;
  v_new_streak integer := 0;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      v_user_id::text || ':' || v_today::text,
      0
    )
  );

  select
    coalesce(
      pg_catalog.array_agg(task.id),
      array[]::uuid[]
    ),
    count(*)::integer
  into
    v_task_ids,
    v_reset_task_count
  from public.study_tasks as task
  where task.user_id = v_user_id
    and task.status = 'completed'
    and task.completed_at is not null
    and (
      task.completed_at
      at time zone 'Asia/Seoul'
    )::date = v_today;

  if v_reset_task_count > 0 then
    select
      coalesce(sum(event.amount), 0)::integer
    into v_removed_task_exp
    from public.exp_events as event
    where event.user_id = v_user_id
      and event.source_key in (
        select
          'task:' || reset_task.task_id::text
        from pg_catalog.unnest(
          v_task_ids
        ) as reset_task(task_id)
      );

    delete from public.exp_events as event
    where event.user_id = v_user_id
      and event.source_key in (
        select
          'task:' || reset_task.task_id::text
        from pg_catalog.unnest(
          v_task_ids
        ) as reset_task(task_id)
      );

    update public.study_tasks
    set
      status = 'pending',
      completed_at = null
    where user_id = v_user_id
      and id = any(v_task_ids);
  end if;

  select
    coalesce(sum(event.amount), 0)::integer
  into v_removed_daily_bonus_exp
  from public.exp_events as event
  where event.user_id = v_user_id
    and event.source_key = (
      'daily:' || v_today::text
    );

  delete from public.exp_events
  where user_id = v_user_id
    and source_key = (
      'daily:' || v_today::text
    );

  update public.learning_activity
  set
    completed_task_count = greatest(
      completed_task_count - v_reset_task_count,
      0
    ),
    earned_exp = greatest(
      earned_exp
      - v_removed_task_exp
      - v_removed_daily_bonus_exp,
      0
    ),
    all_tasks_completed = false,
    updated_at = now()
  where user_id = v_user_id
    and activity_date = v_today;

  delete from public.learning_activity
  where user_id = v_user_id
    and activity_date = v_today
    and completed_task_count = 0
    and quiz_submission_count = 0
    and earned_exp = 0;

  select
    coalesce(sum(event.amount), 0)::integer
  into v_new_total_exp
  from public.exp_events as event
  where event.user_id = v_user_id;

  select max(activity.activity_date)
  into v_last_activity_date
  from public.learning_activity as activity
  where activity.user_id = v_user_id
    and (
      activity.completed_task_count > 0
      or activity.quiz_submission_count > 0
      or activity.earned_exp > 0
    );

  v_check_date := v_last_activity_date;

  while v_check_date is not null
    and exists (
      select 1
      from public.learning_activity as activity
      where activity.user_id = v_user_id
        and activity.activity_date = v_check_date
        and (
          activity.completed_task_count > 0
          or activity.quiz_submission_count > 0
          or activity.earned_exp > 0
        )
    )
  loop
    v_new_streak := v_new_streak + 1;
    v_check_date := v_check_date - 1;
  end loop;

  update public.profiles
  set
    total_exp = v_new_total_exp,
    level = (v_new_total_exp / 100) + 1,
    current_streak = v_new_streak,
    last_activity_date = v_last_activity_date
  where id = v_user_id;

  return jsonb_build_object(
    'reset_task_count', v_reset_task_count,
    'removed_task_exp', v_removed_task_exp,
    'removed_daily_bonus_exp',
      v_removed_daily_bonus_exp,
    'removed_total_exp',
      v_removed_task_exp
      + v_removed_daily_bonus_exp,
    'total_exp', v_new_total_exp,
    'level', (v_new_total_exp / 100) + 1,
    'current_streak', v_new_streak,
    'reset_date', v_today
  );
end;
$$;

revoke all
on function public.reset_today_test_progress()
from public, anon;

grant execute
on function public.reset_today_test_progress()
to authenticated;

commit;