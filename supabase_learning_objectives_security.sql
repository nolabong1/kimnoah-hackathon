-- 학습목표와 과제·자료·퀴즈 연결의 사용자/계획 소유권을 DB에서 보장합니다.
-- 이번 단계는 읽기 권한과 관계 무결성만 추가하며 기존 행의 의미를 바꾸지 않습니다.
begin;

set local lock_timeout = '10s';
set local statement_timeout = '60s';

do $$
begin
  if pg_catalog.to_regclass('public.learning_objectives') is null then
    raise exception '033_learning_objectives_schema migration이 먼저 필요합니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    left join public.learning_objectives as objective
      on objective.id = task.learning_objective_id
     and objective.plan_id = task.plan_id
     and objective.user_id = task.user_id
    where task.learning_objective_id is not null
      and objective.id is null
  ) then
    raise exception '다른 사용자 또는 계획의 학습목표를 가리키는 과제가 있습니다.';
  end if;

  if exists (
    select 1
    from public.learning_materials as material
    left join public.learning_objectives as objective
      on objective.id = material.learning_objective_id
     and objective.plan_id = material.plan_id
     and objective.user_id = material.user_id
    where material.learning_objective_id is not null
      and objective.id is null
  ) then
    raise exception '다른 사용자 또는 계획의 학습목표를 가리키는 원본 자료가 있습니다.';
  end if;

  if exists (
    select 1
    from public.review_materials as material
    left join public.learning_objectives as objective
      on objective.id = material.learning_objective_id
     and objective.plan_id = material.plan_id
     and objective.user_id = material.user_id
    where material.learning_objective_id is not null
      and objective.id is null
  ) then
    raise exception '다른 사용자 또는 계획의 학습목표를 가리키는 복습자료가 있습니다.';
  end if;

  if exists (
    select 1
    from public.quizzes as quiz
    left join public.learning_objectives as objective
      on objective.id = quiz.learning_objective_id
     and objective.plan_id = quiz.plan_id
     and objective.user_id = quiz.user_id
    where quiz.learning_objective_id is not null
      and objective.id is null
  ) then
    raise exception '다른 사용자 또는 계획의 학습목표를 가리키는 퀴즈가 있습니다.';
  end if;

  if exists (
    select 1
    from public.quizzes as quiz
    left join public.learning_materials as material
      on material.id = quiz.reference_learning_material_id
     and material.plan_id = quiz.plan_id
     and material.user_id = quiz.user_id
    where quiz.reference_learning_material_id is not null
      and material.id is null
  ) then
    raise exception '다른 사용자 또는 계획의 원본 자료를 가리키는 퀴즈가 있습니다.';
  end if;

  if exists (
    select 1
    from public.quizzes as quiz
    left join public.review_materials as material
      on material.id = quiz.reference_review_material_id
     and material.plan_id = quiz.plan_id
     and material.user_id = quiz.user_id
    where quiz.reference_review_material_id is not null
      and material.id is null
  ) then
    raise exception '다른 사용자 또는 계획의 복습자료를 가리키는 퀴즈가 있습니다.';
  end if;
end;
$$;

-- 퀴즈 참고자료 FK가 자료의 사용자와 계획까지 함께 검증할 수 있게 합니다.
alter table public.review_materials
add constraint review_materials_id_plan_user_unique
unique (id, plan_id, user_id);

alter table public.study_tasks
add constraint study_tasks_objective_owner_fk
foreign key (learning_objective_id, plan_id, user_id)
references public.learning_objectives(id, plan_id, user_id)
on delete set null (learning_objective_id)
not valid;

alter table public.learning_materials
add constraint learning_materials_objective_owner_fk
foreign key (learning_objective_id, plan_id, user_id)
references public.learning_objectives(id, plan_id, user_id)
on delete set null (learning_objective_id)
not valid;

alter table public.review_materials
add constraint review_materials_objective_owner_fk
foreign key (learning_objective_id, plan_id, user_id)
references public.learning_objectives(id, plan_id, user_id)
on delete set null (learning_objective_id)
not valid;

alter table public.quizzes
add constraint quizzes_objective_owner_fk
foreign key (learning_objective_id, plan_id, user_id)
references public.learning_objectives(id, plan_id, user_id)
on delete set null (learning_objective_id)
not valid;

alter table public.quizzes
add constraint quizzes_reference_learning_material_owner_fk
foreign key (reference_learning_material_id, plan_id, user_id)
references public.learning_materials(id, plan_id, user_id)
on delete set null (reference_learning_material_id)
not valid;

alter table public.quizzes
add constraint quizzes_reference_review_material_owner_fk
foreign key (reference_review_material_id, plan_id, user_id)
references public.review_materials(id, plan_id, user_id)
on delete set null (reference_review_material_id)
not valid;

alter table public.study_tasks
validate constraint study_tasks_objective_owner_fk;

alter table public.learning_materials
validate constraint learning_materials_objective_owner_fk;

alter table public.review_materials
validate constraint review_materials_objective_owner_fk;

alter table public.quizzes
validate constraint quizzes_objective_owner_fk;

alter table public.quizzes
validate constraint quizzes_reference_learning_material_owner_fk;

alter table public.quizzes
validate constraint quizzes_reference_review_material_owner_fk;

-- 클라이언트는 본인의 목표만 읽고, 쓰기는 후속 서버 RPC를 통해서만 수행합니다.
drop policy if exists learning_objectives_select_own
on public.learning_objectives;

create policy learning_objectives_select_own
on public.learning_objectives
for select
to authenticated
using ((select auth.uid()) = user_id);

revoke all on public.learning_objectives from public, anon, authenticated;
grant select on public.learning_objectives to authenticated;

-- 목표별 조회와 퀴즈 참고자료 역조회에 필요한 최소 인덱스입니다.
create index learning_objectives_user_plan_order_idx
on public.learning_objectives(user_id, plan_id, sort_order);

create index study_tasks_plan_objective_date_idx
on public.study_tasks(plan_id, learning_objective_id, scheduled_date)
where learning_objective_id is not null;

create index learning_materials_plan_objective_created_idx
on public.learning_materials(plan_id, learning_objective_id, created_at desc)
where learning_objective_id is not null;

create index review_materials_plan_objective_updated_idx
on public.review_materials(plan_id, learning_objective_id, updated_at desc)
where learning_objective_id is not null;

create index quizzes_plan_objective_updated_idx
on public.quizzes(plan_id, learning_objective_id, updated_at desc)
where learning_objective_id is not null;

create index quizzes_reference_learning_material_idx
on public.quizzes(reference_learning_material_id)
where reference_learning_material_id is not null;

create index quizzes_reference_review_material_idx
on public.quizzes(reference_review_material_id)
where reference_review_material_id is not null;

commit;
