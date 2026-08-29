-- 과제·원본 기반 AI 자료의 학습목표 연결과 생성 시점 계약을 DB에서 강제합니다.
begin;

set local lock_timeout = '10s';
set local statement_timeout = '60s';

do $$
begin
  if pg_catalog.to_regclass('public.learning_objectives') is null
     or pg_catalog.to_regclass('public.study_tasks') is null
     or pg_catalog.to_regclass('public.learning_materials') is null
     or pg_catalog.to_regclass('public.review_materials') is null
  then
    raise exception '035_learning_objective_plan_save migration이 먼저 필요합니다.';
  end if;

  if exists (
    select 1
    from public.review_materials as material
    join public.study_tasks as task
      on task.id = material.task_id
     and task.plan_id = material.plan_id
     and task.user_id = material.user_id
    join public.learning_materials as source
      on source.id = material.source_material_id
     and source.plan_id = material.plan_id
     and source.user_id = material.user_id
    where task.learning_objective_id is not null
      and source.learning_objective_id is not null
      and task.learning_objective_id <> source.learning_objective_id
  ) then
    raise exception '서로 다른 학습목표를 가리키는 과제·원본 복습자료가 있습니다.';
  end if;
end;
$$;

create or replace function public.sync_review_material_learning_objective()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  v_task_objective_id uuid;
  v_source_objective_id uuid;
  v_objective public.learning_objectives%rowtype;
begin
  if new.task_id is not null then
    select task.learning_objective_id
    into v_task_objective_id
    from public.study_tasks as task
    where task.id = new.task_id
      and task.plan_id = new.plan_id
      and task.user_id = new.user_id;

    if not found then
      raise exception '복습자료와 같은 사용자·계획의 과제를 찾을 수 없습니다.';
    end if;
  end if;

  if new.source_material_id is not null then
    select material.learning_objective_id
    into v_source_objective_id
    from public.learning_materials as material
    where material.id = new.source_material_id
      and material.plan_id = new.plan_id
      and material.user_id = new.user_id;

    if not found then
      raise exception '복습자료와 같은 사용자·계획의 원본을 찾을 수 없습니다.';
    end if;
  end if;

  if v_task_objective_id is not null
     and v_source_objective_id is not null
     and v_task_objective_id <> v_source_objective_id
  then
    raise exception '과제와 원본의 학습목표가 서로 다릅니다.';
  end if;

  -- 연결 대상이 있으면 클라이언트 목표 ID를 무시하고 원본 관계에서 계산합니다.
  if new.task_id is not null or new.source_material_id is not null then
    new.learning_objective_id := coalesce(
      v_task_objective_id,
      v_source_objective_id
    );
  end if;

  if new.learning_objective_id is null then
    new.objective_snapshot := null;
    new.objective_contract_hash := null;
    return new;
  end if;

  select objective.*
  into v_objective
  from public.learning_objectives as objective
  where objective.id = new.learning_objective_id
    and objective.plan_id = new.plan_id
    and objective.user_id = new.user_id;

  if not found then
    raise exception '복습자료와 같은 사용자·계획의 학습목표를 찾을 수 없습니다.';
  end if;

  if v_objective.origin = 'generated' then
    new.objective_snapshot := pg_catalog.jsonb_build_object(
      'objective_key', v_objective.objective_key,
      'title', v_objective.title,
      'description', v_objective.description,
      'target_depth', v_objective.target_depth,
      'evidence_requirements', v_objective.evidence_requirements
    );
    new.objective_contract_hash := v_objective.contract_hash;
  else
    -- 기존 계획 호환 목표는 생성 당시 해시가 없으므로 스냅샷을 만들지 않습니다.
    new.objective_snapshot := null;
    new.objective_contract_hash := null;
  end if;

  return new;
end;
$$;

revoke all on function public.sync_review_material_learning_objective()
from public, anon, authenticated;

drop trigger if exists review_materials_sync_learning_objective
on public.review_materials;

create trigger review_materials_sync_learning_objective
before insert or update
on public.review_materials
for each row
execute function public.sync_review_material_learning_objective();

-- 기존 자료도 현재 과제·원본 연결을 기준으로 한 번 정규화합니다.
update public.review_materials
set learning_objective_id = learning_objective_id;

comment on function public.sync_review_material_learning_objective() is
  '과제·원본 관계에서 복습자료 목표를 계산하고 생성 목표 계약 스냅샷을 보존';

commit;
