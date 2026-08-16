do $$
begin
  if not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'review_materials'
      and column_name = 'task_id'
      and is_nullable = 'YES'
  ) then
    raise exception 'review_materials.task_id must be nullable';
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'review_materials_source_owner_fk'
      and conrelid = 'public.review_materials'::regclass
  ) then
    raise exception 'review_materials_source_owner_fk is missing';
  end if;

  if not exists (
    select 1
    from pg_class
    where oid = 'public.learning_materials'::regclass
      and relrowsecurity
  ) then
    raise exception 'learning_materials RLS must be enabled';
  end if;

  if not exists (
    select 1
    from pg_class
    where oid = 'public.review_materials'::regclass
      and relrowsecurity
  ) then
    raise exception 'review_materials RLS must be enabled';
  end if;
end;
$$;

select 'source material review validation: success'
as validation_result;
