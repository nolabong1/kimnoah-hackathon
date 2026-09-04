begin;

do $$
begin
  if pg_catalog.to_regclass('public.learning_materials') is null then
    raise exception 'public.learning_materials 테이블이 없습니다.';
  end if;

  if exists (
    select 1
    from public.learning_materials
    where material_type not in ('text', 'pdf')
  ) then
    raise exception '알 수 없는 learning_materials.material_type 값이 있습니다.';
  end if;
end
$$;

alter table public.learning_materials
drop constraint learning_materials_material_type_check;

alter table public.learning_materials
add constraint learning_materials_material_type_check
check (material_type in ('text', 'pdf', 'image')) not valid;

alter table public.learning_materials
validate constraint learning_materials_material_type_check;

alter table public.learning_materials
add constraint learning_materials_image_content_check
check (
  material_type <> 'image'
  or (content_text is not null and pg_catalog.btrim(content_text) <> '')
) not valid;

alter table public.learning_materials
validate constraint learning_materials_image_content_check;

alter table public.learning_materials
add constraint learning_materials_image_storage_check
check (material_type <> 'image' or storage_path is null) not valid;

alter table public.learning_materials
validate constraint learning_materials_image_storage_check;

comment on column public.learning_materials.material_type is
  '사용자 원본 유형: text, pdf, image. 원본 파일은 저장하지 않고 content_text만 보존한다.';

commit;
