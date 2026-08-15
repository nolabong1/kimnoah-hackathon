begin;

-- 복습 자료가 연결된 과제와 동일한 계획·사용자에
-- 속하는지 복합 외래 키로 검증하기 위한 제약조건입니다.
alter table public.study_tasks
add constraint study_tasks_id_plan_user_unique
unique (id, plan_id, user_id);

alter table public.learning_materials
add constraint learning_materials_id_plan_user_unique
unique (id, plan_id, user_id);


-- 각 AI 학습자료를 특정 과제와 연결합니다.
alter table public.review_materials
add column task_id uuid not null;

-- 자료 재생성 시 갱신 시각을 기록합니다.
alter table public.review_materials
add column updated_at timestamptz
not null default now();


-- 기존 source_material_id 단독 외래 키를 제거합니다.
alter table public.review_materials
drop constraint if exists
review_materials_source_material_id_fkey;


-- 과제, 계획, 사용자가 서로 일치하는지 검증합니다.
alter table public.review_materials
add constraint review_materials_task_owner_fk
foreign key (task_id, plan_id, user_id)
references public.study_tasks(id, plan_id, user_id)
on delete cascade;


-- 원본 자료도 같은 계획과 사용자에 속하는지 검증합니다.
-- 원본 자료 삭제 시 연결만 해제하고 AI 자료는 유지합니다.
alter table public.review_materials
add constraint review_materials_source_owner_fk
foreign key (
  source_material_id,
  plan_id,
  user_id
)
references public.learning_materials(
  id,
  plan_id,
  user_id
)
on delete set null (source_material_id);


-- 현재 정책은 과제당 AI 자료 하나입니다.
-- 추후 버전 보관 기능을 추가할 때 이 제약조건을 변경합니다.
alter table public.review_materials
add constraint review_materials_task_unique
unique (task_id);


-- 사용자별 계획 자료 조회를 위한 인덱스입니다.
create index review_materials_user_plan_idx
on public.review_materials(user_id, plan_id);


-- 원본 자료를 기준으로 연결된 AI 자료를 찾기 위한 인덱스입니다.
create index review_materials_source_idx
on public.review_materials(source_material_id)
where source_material_id is not null;


-- 자료가 갱신될 때 updated_at을 자동 변경합니다.
create or replace function
public.set_review_material_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create trigger review_materials_set_updated_at
before update
on public.review_materials
for each row
execute function
public.set_review_material_updated_at();

commit;