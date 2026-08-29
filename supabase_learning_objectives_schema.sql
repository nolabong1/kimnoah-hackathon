-- 학습목표를 계획·과제·자료·퀴즈 사이의 공통 계약으로 보존할 기본 구조입니다.
-- 이번 단계에서는 기존 런타임과의 호환을 위해 새 연결 열을 nullable로 유지합니다.
begin;

set local lock_timeout = '10s';
set local statement_timeout = '60s';

do $$
begin
  if pg_catalog.to_regclass('public.learning_objectives') is not null then
    raise exception 'public.learning_objectives 테이블이 이미 존재합니다.';
  end if;

  if pg_catalog.to_regclass('public.study_plans') is null
     or pg_catalog.to_regclass('public.study_tasks') is null
     or pg_catalog.to_regclass('public.learning_materials') is null
     or pg_catalog.to_regclass('public.review_materials') is null
     or pg_catalog.to_regclass('public.quizzes') is null
  then
    raise exception '학습목표 스키마에 필요한 기존 테이블이 없습니다.';
  end if;

  if exists (
    select 1
    from public.study_tasks as task
    left join public.study_plans as plan
      on plan.id = task.plan_id
     and plan.user_id = task.user_id
    where plan.id is null
  ) then
    raise exception '소유 계획과 연결되지 않은 기존 과제가 있습니다.';
  end if;
end;
$$;

create table public.learning_objectives (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  plan_id uuid not null,
  objective_key text not null
    check (
      char_length(objective_key) between 1 and 100
      and objective_key ~ '^[a-z0-9]+(_[a-z0-9]+)*$'
    ),
  title text not null
    check (char_length(btrim(title)) between 1 and 200),
  description text not null
    check (char_length(btrim(description)) between 1 and 1000),
  target_depth text not null
    check (target_depth in ('foundation', 'developing', 'advanced')),
  evidence_requirements jsonb not null,
  contract_hash text,
  sort_order smallint not null
    check (sort_order between 1 and 5),
  origin text not null default 'generated'
    check (origin in ('generated', 'legacy_backfill')),
  created_at timestamptz not null default now(),
  constraint learning_objectives_plan_owner_fk
    foreign key (plan_id, user_id)
    references public.study_plans(id, user_id)
    on delete cascade,
  constraint learning_objectives_id_plan_user_unique
    unique (id, plan_id, user_id),
  constraint learning_objectives_plan_key_unique
    unique (plan_id, objective_key),
  constraint learning_objectives_plan_order_unique
    unique (plan_id, sort_order),
  constraint learning_objectives_evidence_contract_check
    check (
      jsonb_typeof(evidence_requirements) = 'array'
      and jsonb_array_length(evidence_requirements) = 3
      and evidence_requirements -> 0 ->> 'key'
            is not distinct from 'explain'
      and evidence_requirements -> 1 ->> 'key'
            is not distinct from 'apply'
      and evidence_requirements -> 2 ->> 'key'
            is not distinct from 'differentiate'
      and jsonb_typeof(evidence_requirements -> 0 -> 'description')
            is not distinct from 'string'
      and jsonb_typeof(evidence_requirements -> 1 -> 'description')
            is not distinct from 'string'
      and jsonb_typeof(evidence_requirements -> 2 -> 'description')
            is not distinct from 'string'
      and char_length(btrim(evidence_requirements -> 0 ->> 'description'))
            between 1 and 300
      and char_length(btrim(evidence_requirements -> 1 ->> 'description'))
            between 1 and 300
      and char_length(btrim(evidence_requirements -> 2 ->> 'description'))
            between 1 and 300
    ),
  constraint learning_objectives_hash_origin_check
    check (
      (
        origin = 'legacy_backfill'
        and contract_hash is null
      )
      or (
        origin = 'generated'
        and contract_hash is not null
        and contract_hash ~ '^[0-9a-f]{64}$'
      )
    )
);

alter table public.learning_objectives enable row level security;

-- 3단계에서 본인 조회 정책과 서버 쓰기 경계를 추가하기 전까지 닫힌 상태입니다.
revoke all on public.learning_objectives from public, anon, authenticated;

alter table public.study_tasks
add column learning_objective_id uuid;

alter table public.learning_materials
add column learning_objective_id uuid;

alter table public.review_materials
add column learning_objective_id uuid,
add column objective_snapshot jsonb,
add column objective_contract_hash text,
add constraint review_materials_objective_snapshot_check
check (
  (objective_snapshot is null and objective_contract_hash is null)
  or (
    objective_snapshot is not null
    and objective_contract_hash is not null
    and jsonb_typeof(objective_snapshot) = 'object'
    and objective_contract_hash ~ '^[0-9a-f]{64}$'
  )
);

alter table public.quizzes
add column learning_objective_id uuid,
add column objective_snapshot jsonb,
add column objective_contract_hash text,
add column reference_learning_material_id uuid,
add column reference_review_material_id uuid,
add constraint quizzes_objective_snapshot_check
check (
  (objective_snapshot is null and objective_contract_hash is null)
  or (
    objective_snapshot is not null
    and objective_contract_hash is not null
    and jsonb_typeof(objective_snapshot) = 'object'
    and objective_contract_hash ~ '^[0-9a-f]{64}$'
  )
),
add constraint quizzes_single_reference_material_check
check (
  num_nonnulls(
    reference_learning_material_id,
    reference_review_material_id
  ) <= 1
);

-- 기존 계획은 과거 생성 당시 세부 목표가 없었으므로 계획 전체 목표 하나로
-- 정직하게 표시하고 계약 해시는 만들지 않습니다.
insert into public.learning_objectives (
  user_id,
  plan_id,
  objective_key,
  title,
  description,
  target_depth,
  evidence_requirements,
  contract_hash,
  sort_order,
  origin
)
select
  plan.user_id,
  plan.id,
  'legacy_primary',
  '기존 계획 전체 목표',
  btrim(plan.goal),
  case
    when plan.current_level <= 3 then 'foundation'
    when plan.current_level <= 7 then 'developing'
    else 'advanced'
  end,
  pg_catalog.jsonb_build_array(
    pg_catalog.jsonb_build_object(
      'key', 'explain',
      'description', '핵심 개념과 적용 조건을 자신의 말로 설명할 수 있다.'
    ),
    pg_catalog.jsonb_build_object(
      'key', 'apply',
      'description', '핵심 개념을 구체적인 예시나 문제 상황에 적용할 수 있다.'
    ),
    pg_catalog.jsonb_build_object(
      'key', 'differentiate',
      'description', '올바른 적용과 흔한 오해 또는 잘못된 적용을 구분할 수 있다.'
    )
  ),
  null,
  1,
  'legacy_backfill'
from public.study_plans as plan;

update public.study_tasks as task
set learning_objective_id = objective.id
from public.learning_objectives as objective
where objective.plan_id = task.plan_id
  and objective.user_id = task.user_id
  and objective.objective_key = 'legacy_primary'
  and task.learning_objective_id is null;

comment on table public.learning_objectives is
  '계획 안에서 여러 학습 과제와 자료·퀴즈가 공유하는 학습목표 계약';
comment on column public.learning_objectives.origin is
  'generated는 새 목표, legacy_backfill은 기존 계획 호환 목표';
comment on column public.study_tasks.learning_objective_id is
  '과제가 수행하는 대표 학습목표. 런타임 전환 전까지 nullable';
comment on column public.learning_materials.learning_objective_id is
  '사용자 원본 자료가 지원하는 선택적 학습목표';
comment on column public.review_materials.objective_snapshot is
  'AI 학습자료 생성 당시 사용한 학습목표 계약 스냅샷';
comment on column public.quizzes.objective_snapshot is
  '퀴즈 생성 당시 사용한 학습목표 계약 스냅샷';

commit;
