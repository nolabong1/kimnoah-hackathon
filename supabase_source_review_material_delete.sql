-- 원본 기반 AI 복습자료와 연결 원본 텍스트를 한 트랜잭션에서 삭제합니다.
begin;

create or replace function public.delete_source_review_material(
  p_review_material_id uuid,
  p_source_material_id uuid,
  p_plan_id uuid
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_deleted_review_id uuid;
  v_deleted_source_id uuid;
begin
  if v_user_id is null then
    raise exception using
      errcode = '42501',
      message = '로그인이 필요합니다.';
  end if;

  if p_review_material_id is null
     or p_source_material_id is null
     or p_plan_id is null
  then
    raise exception '삭제할 복습자료 정보가 필요합니다.';
  end if;

  delete from public.review_materials
  where id = p_review_material_id
    and source_material_id = p_source_material_id
    and plan_id = p_plan_id
    and user_id = v_user_id
    and task_id is null
  returning id into v_deleted_review_id;

  if v_deleted_review_id is null then
    raise exception using
      errcode = '42501',
      message = '삭제할 본인 복습자료를 찾을 수 없습니다.';
  end if;

  -- 혹시 같은 원본을 참조하는 다른 복습자료가 있으면 원본은 보존합니다.
  delete from public.learning_materials as source_material
  where source_material.id = p_source_material_id
    and source_material.plan_id = p_plan_id
    and source_material.user_id = v_user_id
    and not exists (
      select 1
      from public.review_materials as remaining_review
      where remaining_review.source_material_id = source_material.id
    )
  returning id into v_deleted_source_id;

  return pg_catalog.jsonb_build_object(
    'review_material_id', v_deleted_review_id,
    'source_material_id', p_source_material_id,
    'source_deleted', v_deleted_source_id is not null
  );
end;
$$;

revoke all on function public.delete_source_review_material(
  uuid,
  uuid,
  uuid
) from public, anon, authenticated;

grant execute on function public.delete_source_review_material(
  uuid,
  uuid,
  uuid
) to authenticated;

commit;
