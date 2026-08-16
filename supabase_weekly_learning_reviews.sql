begin;

create table public.weekly_learning_reviews (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  plan_id uuid not null,
  week_start date not null,
  week_end date not null,
  statistics_snapshot jsonb not null
    check (jsonb_typeof(statistics_snapshot) = 'object'),
  reflection_answers jsonb not null
    check (jsonb_typeof(reflection_answers) = 'object'),
  ai_review_data jsonb not null
    check (jsonb_typeof(ai_review_data) = 'object'),
  ai_review_markdown text not null
    check (char_length(btrim(ai_review_markdown)) >= 1),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint weekly_learning_reviews_plan_owner_fk
    foreign key (plan_id, user_id)
    references public.study_plans(id, user_id)
    on delete cascade,
  constraint weekly_learning_reviews_valid_week
    check (week_end >= week_start),
  constraint weekly_learning_reviews_user_plan_unique
    unique (user_id, plan_id)
);

create index weekly_learning_reviews_user_recent_idx
on public.weekly_learning_reviews(user_id, created_at desc);

create index weekly_learning_reviews_plan_idx
on public.weekly_learning_reviews(plan_id);

create trigger weekly_learning_reviews_set_updated_at
before update on public.weekly_learning_reviews
for each row execute function public.set_updated_at();

alter table public.weekly_learning_reviews enable row level security;

create policy "weekly_learning_reviews_select_own"
on public.weekly_learning_reviews
for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "weekly_learning_reviews_insert_own"
on public.weekly_learning_reviews
for insert
to authenticated
with check ((select auth.uid()) = user_id);

create policy "weekly_learning_reviews_update_own"
on public.weekly_learning_reviews
for update
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy "weekly_learning_reviews_delete_own"
on public.weekly_learning_reviews
for delete
to authenticated
using ((select auth.uid()) = user_id);

revoke all on public.weekly_learning_reviews from anon, authenticated;
grant select, insert, update, delete
on public.weekly_learning_reviews
to authenticated;

commit;
