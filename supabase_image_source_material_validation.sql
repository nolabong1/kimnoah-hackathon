begin;

set transaction read only;

do $$
declare
  v_constraint_definition text;
  v_image_content_constraint text;
  v_image_storage_constraint text;
  v_rls_enabled boolean;
begin
  if pg_catalog.to_regclass('public.learning_materials') is null then
    raise exception 'public.learning_materials 테이블이 없습니다.';
  end if;

  select pg_catalog.pg_get_constraintdef(constraint_row.oid)
  into v_constraint_definition
  from pg_catalog.pg_constraint as constraint_row
  where constraint_row.conrelid = 'public.learning_materials'::regclass
    and constraint_row.conname = 'learning_materials_material_type_check'
    and constraint_row.contype = 'c';

  if v_constraint_definition is null
     or pg_catalog.strpos(pg_catalog.lower(v_constraint_definition), 'text') = 0
     or pg_catalog.strpos(pg_catalog.lower(v_constraint_definition), 'pdf') = 0
     or pg_catalog.strpos(pg_catalog.lower(v_constraint_definition), 'image') = 0 then
    raise exception 'learning_materials 원본 유형 제약에 image가 없습니다.';
  end if;

  select pg_catalog.pg_get_constraintdef(constraint_row.oid)
  into v_image_content_constraint
  from pg_catalog.pg_constraint as constraint_row
  where constraint_row.conrelid = 'public.learning_materials'::regclass
    and constraint_row.conname = 'learning_materials_image_content_check'
    and constraint_row.contype = 'c';

  if v_image_content_constraint is null
     or pg_catalog.strpos(pg_catalog.lower(v_image_content_constraint), 'content_text') = 0 then
    raise exception '이미지 원본의 추출 텍스트 필수 제약이 없습니다.';
  end if;

  select pg_catalog.pg_get_constraintdef(constraint_row.oid)
  into v_image_storage_constraint
  from pg_catalog.pg_constraint as constraint_row
  where constraint_row.conrelid = 'public.learning_materials'::regclass
    and constraint_row.conname = 'learning_materials_image_storage_check'
    and constraint_row.contype = 'c';

  if v_image_storage_constraint is null
     or pg_catalog.strpos(pg_catalog.lower(v_image_storage_constraint), 'storage_path') = 0 then
    raise exception '이미지 원본 파일 비저장 제약이 없습니다.';
  end if;

  if exists (
    select 1
    from public.learning_materials
    where material_type not in ('text', 'pdf', 'image')
  ) then
    raise exception '허용되지 않은 learning_materials.material_type 값이 있습니다.';
  end if;

  if exists (
    select 1
    from public.learning_materials
    where material_type = 'image'
      and (content_text is null or pg_catalog.btrim(content_text) = '')
  ) then
    raise exception '이미지 원본에 저장된 추출 텍스트가 없습니다.';
  end if;

  if exists (
    select 1
    from public.learning_materials
    where material_type = 'image'
      and storage_path is not null
  ) then
    raise exception 'MVP 이미지 원본에 storage_path가 저장되어 있습니다.';
  end if;

  select relation.relrowsecurity
  into v_rls_enabled
  from pg_catalog.pg_class as relation
  where relation.oid = 'public.learning_materials'::regclass;

  if v_rls_enabled is not true then
    raise exception 'learning_materials RLS가 비활성화되어 있습니다.';
  end if;
end
$$;

select 'image source material validation: success' as validation_result;

rollback;
