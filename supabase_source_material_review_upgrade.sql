begin;

-- 과제 기반 AI 학습자료는 기존처럼 task_id를 사용합니다.
-- 사용자가 직접 제공한 원본 기반 복습자료는 source_material_id만 사용하므로
-- task_id를 선택 사항으로 변경합니다.
alter table public.review_materials
alter column task_id drop not null;

commit;
