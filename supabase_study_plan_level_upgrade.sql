begin;

alter table public.study_plans
drop constraint if exists study_plans_current_level_check;

alter table public.study_plans
add constraint study_plans_current_level_check
check (current_level between 1 and 10);

commit;
