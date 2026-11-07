begin;

create extension if not exists pgcrypto;

-- Identidad y auditoría mínimas: esta migración no depende de un frontend previo.
create table if not exists public.plan_members (
  user_id uuid primary key references auth.users(id) on delete cascade,
  functional_role text check (functional_role in ('rrhh','professional','management','dmn')),
  professional_id text,
  institute_codes text[] not null default '{}'
);

create table if not exists public.plan_audit_logs (
  id bigserial primary key,
  actor_id uuid,
  actor_text text,
  actor_role text,
  operation text not null,
  revision_id text,
  entity_type text,
  entity_id text,
  old_value jsonb,
  new_value jsonb,
  justification text,
  origin text,
  correlation_id text,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.institutes (
  code text primary key,
  name text not null,
  zone text
);

create table if not exists public.professionals (
  id text primary key,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.rpa_imports (
  id text primary key default gen_random_uuid()::text,
  source text not null check (source in ('BUK','SIC')),
  filename text not null,
  file_hash text not null,
  idempotency_key text not null unique,
  status text not null default 'created' check (status in ('created','receiving','completed','failed')),
  rows_received integer not null default 0 check (rows_received >= 0),
  rows_accepted integer not null default 0 check (rows_accepted >= 0),
  rows_rejected integer not null default 0 check (rows_rejected >= 0),
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create table if not exists public.rpa_import_records (
  id text primary key default gen_random_uuid()::text,
  import_id text not null references public.rpa_imports(id) on delete cascade,
  source_record_id text not null,
  record_type text not null check (record_type in ('buk','sic','delta')),
  payload jsonb not null,
  applied boolean not null default false,
  unique(import_id, source_record_id)
);

create table if not exists public.rpa_import_errors (
  id text primary key default gen_random_uuid()::text,
  import_id text not null references public.rpa_imports(id) on delete cascade,
  row_number integer,
  field text,
  code text not null,
  message text not null
);

create table if not exists public.contract_versions (
  id text primary key default gen_random_uuid()::text,
  professional_id text not null references public.professionals(id),
  institute_code text not null references public.institutes(code),
  role text not null,
  area text,
  weekly_hours numeric(8,2) not null check (weekly_hours between 0 and 60),
  effective_from date not null,
  effective_to date,
  source_record_id text not null,
  source_import_id text references public.rpa_imports(id),
  check (effective_to is null or effective_to >= effective_from),
  unique(professional_id, institute_code, effective_from, source_record_id)
);
create index if not exists contract_versions_professional_idx on public.contract_versions(professional_id, effective_from);

create table if not exists public.unavailability_periods (
  id text primary key default gen_random_uuid()::text,
  professional_id text not null references public.professionals(id),
  institute_code text not null references public.institutes(code),
  year integer not null,
  month integer not null check (month between 1 and 12),
  kind text not null check (kind in ('sick_leave','vacation','permission','extended_leave')),
  days numeric(8,2) not null check (days >= 0),
  source_import_id text references public.rpa_imports(id)
);

create table if not exists public.distribution_parameters (
  id text primary key default gen_random_uuid()::text,
  role text not null,
  workload_band text not null check (workload_band in ('T1_>=40','T2_22-39','T3_<22')),
  direct_pct numeric(8,6) not null check (direct_pct between 0 and 1),
  indirect_pct numeric(8,6) not null check (indirect_pct between 0 and 1),
  nas_pct numeric(8,6) not null check (nas_pct between 0 and 1),
  direct_minutes integer not null check (direct_minutes in (30,40,45,60)),
  indirect_minutes integer not null default 30 check (indirect_minutes > 0),
  group_pct numeric(8,6) not null default 0 check (group_pct between 0 and 1),
  group_size numeric(8,2) not null default 1 check (group_size >= 1),
  valid_from date not null,
  valid_to date,
  check (direct_pct + indirect_pct + nas_pct <= 1.000001),
  check (valid_to is null or valid_to >= valid_from),
  unique(role, workload_band, valid_from)
);

create table if not exists public.system_parameters (
  id text primary key default gen_random_uuid()::text,
  code text not null,
  value jsonb not null,
  description text not null,
  valid_from date not null,
  valid_to date,
  check (valid_to is null or valid_to >= valid_from),
  unique(code, valid_from)
);

create table if not exists public.legal_workweek_references (
  id text primary key default gen_random_uuid()::text,
  weekly_hours numeric(8,2) not null check (weekly_hours > 0 and weekly_hours <= 60),
  valid_from date not null unique,
  valid_to date,
  description text not null,
  check (valid_to is null or valid_to >= valid_from)
);

create table if not exists public.institutional_calendars (
  id text primary key default gen_random_uuid()::text,
  institute_code text not null references public.institutes(code),
  year integer not null,
  month integer not null check (month between 1 and 12),
  working_days numeric(8,2) not null check (working_days between 0 and 31),
  national_holidays integer not null default 0 check (national_holidays >= 0),
  regional_holidays integer not null default 0 check (regional_holidays >= 0),
  special_regime_days numeric(8,2) not null default 0 check (special_regime_days >= 0),
  zone text,
  unique(institute_code, year, month)
);

create table if not exists public.assignment_catalog (
  id text primary key default gen_random_uuid()::text,
  name text not null unique,
  weekly_hours numeric(8,2) check (weekly_hours > 0),
  active boolean not null default true,
  requires_dmn boolean not null default false,
  valid_from date not null
);

create table if not exists public.assignment_requests (
  id text primary key default gen_random_uuid()::text,
  professional_id text not null references public.professionals(id),
  institute_code text not null references public.institutes(code),
  catalog_id text not null references public.assignment_catalog(id),
  valid_from date not null,
  valid_to date,
  status text not null default 'pending' check (status in ('pending','approved','rejected','cancelled')),
  requested_by text not null,
  decided_by text,
  requested_reason text not null,
  decision_reason text,
  decided_at timestamptz,
  check (valid_to is null or valid_to >= valid_from)
);

create table if not exists public.replacements (
  id text primary key default gen_random_uuid()::text,
  holder_id text not null references public.professionals(id),
  replacement_id text not null references public.professionals(id),
  institute_code text not null references public.institutes(code),
  valid_from date not null,
  valid_to date not null,
  status text not null default 'active',
  check (valid_to >= valid_from),
  check (holder_id <> replacement_id)
);

create table if not exists public.vacancies (
  id text primary key default gen_random_uuid()::text,
  institute_code text not null references public.institutes(code),
  role text not null,
  weekly_hours numeric(8,2) not null check (weekly_hours between 0 and 60),
  valid_from date not null,
  valid_to date,
  status text not null default 'open',
  include_in_planning boolean not null default true,
  check (valid_to is null or valid_to >= valid_from)
);

create table if not exists public.monthly_planning (
  id text primary key default gen_random_uuid()::text,
  professional_id text not null references public.professionals(id),
  institute_code text not null references public.institutes(code),
  role text not null,
  area text,
  year integer not null,
  month integer not null check (month between 1 and 12),
  workload_band text not null,
  contracted_hours numeric(12,4) not null check (contracted_hours >= 0),
  direct_hours numeric(12,4) not null check (direct_hours >= 0),
  indirect_hours numeric(12,4) not null check (indirect_hours >= 0),
  nas_hours numeric(12,4) not null check (nas_hours >= 0),
  absence_hours numeric(12,4) not null check (absence_hours >= 0),
  planned_direct integer not null check (planned_direct >= 0),
  planned_indirect integer not null check (planned_indirect >= 0),
  planned_total integer not null check (planned_total >= 0),
  target_total integer not null check (target_total >= 0),
  foja numeric(12,6),
  parameters_version text not null,
  calculated_at timestamptz not null default now(),
  unique(professional_id, institute_code, year, month),
  check (planned_total = planned_direct + planned_indirect),
  check (target_total <= planned_total)
);

create table if not exists public.sic_actuals (
  id text primary key default gen_random_uuid()::text,
  professional_id text not null references public.professionals(id),
  institute_code text not null references public.institutes(code),
  year integer not null,
  month integer not null check (month between 1 and 12),
  executed_direct integer not null check (executed_direct >= 0),
  executed_indirect integer not null default 0 check (executed_indirect >= 0),
  validated_report boolean not null default true,
  source_import_id text references public.rpa_imports(id),
  unique(professional_id, institute_code, year, month)
);

alter table public.plan_audit_logs
  add column if not exists actor_text text,
  add column if not exists actor_role text,
  add column if not exists entity_type text,
  add column if not exists entity_id text,
  add column if not exists old_value jsonb,
  add column if not exists new_value jsonb,
  add column if not exists justification text,
  add column if not exists origin text,
  add column if not exists correlation_id text;
create index if not exists plan_audit_logs_correlation_idx on public.plan_audit_logs(correlation_id);

insert into public.system_parameters(code,value,description,valid_from)
values ('META_GESTION','{"value":"0.90"}'::jsonb,'Porcentaje mínimo de meta de gestión asistencial','2026-01-01')
on conflict (code,valid_from) do nothing;

insert into public.legal_workweek_references(weekly_hours,valid_from,valid_to,description)
values
  (44,'2026-01-01','2026-04-30','Referencia legal enero-abril 2026'),
  (42,'2026-05-01',null,'Referencia legal desde mayo 2026')
on conflict (valid_from) do nothing;

create or replace function public.current_app_role() returns text
language sql stable security definer set search_path=public,pg_temp as $$
  select functional_role from public.plan_members where user_id=auth.uid()
$$;

create or replace function public.current_professional_id() returns text
language sql stable security definer set search_path=public,pg_temp as $$
  select professional_id from public.plan_members where user_id=auth.uid()
$$;

create or replace function public.prevent_audit_mutation() returns trigger
language plpgsql set search_path=public,pg_temp as $$
begin
  raise exception 'El historial de auditoría es inmutable' using errcode='42501';
end;
$$;

drop trigger if exists audit_events_append_only on public.plan_audit_logs;
create trigger audit_events_append_only before update or delete on public.plan_audit_logs
for each row execute function public.prevent_audit_mutation();

alter table public.institutes enable row level security;
alter table public.professionals enable row level security;
alter table public.rpa_imports enable row level security;
alter table public.rpa_import_records enable row level security;
alter table public.rpa_import_errors enable row level security;
alter table public.contract_versions enable row level security;
alter table public.unavailability_periods enable row level security;
alter table public.distribution_parameters enable row level security;
alter table public.system_parameters enable row level security;
alter table public.legal_workweek_references enable row level security;
alter table public.institutional_calendars enable row level security;
alter table public.assignment_catalog enable row level security;
alter table public.assignment_requests enable row level security;
alter table public.replacements enable row level security;
alter table public.vacancies enable row level security;
alter table public.monthly_planning enable row level security;
alter table public.sic_actuals enable row level security;

create policy institutes_read on public.institutes for select to authenticated using (true);
create policy parameters_read on public.distribution_parameters for select to authenticated using (true);
create policy system_parameters_read on public.system_parameters for select to authenticated using (true);
create policy legal_reference_read on public.legal_workweek_references for select to authenticated using (true);
create policy calendars_read on public.institutional_calendars for select to authenticated using (true);
create policy assignment_catalog_read on public.assignment_catalog for select to authenticated using (true);

create policy professionals_scoped_read on public.professionals for select to authenticated using (
  public.current_app_role() in ('rrhh','management','dmn')
  or id=public.current_professional_id()
);
create policy contracts_scoped_read on public.contract_versions for select to authenticated using (
  public.current_app_role() in ('rrhh','management','dmn')
  or professional_id=public.current_professional_id()
);
create policy planning_scoped_read on public.monthly_planning for select to authenticated using (
  public.current_app_role() in ('rrhh','management','dmn')
  or professional_id=public.current_professional_id()
);
create policy assignment_requests_scoped_read on public.assignment_requests for select to authenticated using (
  public.current_app_role() in ('rrhh','management','dmn')
  or professional_id=public.current_professional_id()
);
drop policy if exists audit_read on public.plan_audit_logs;
create policy audit_authorized_read on public.plan_audit_logs for select to authenticated using (
  public.current_app_role() in ('rrhh','management','dmn')
);
revoke all on public.institutes, public.professionals, public.rpa_imports,
  public.rpa_import_records, public.rpa_import_errors, public.contract_versions,
  public.unavailability_periods, public.distribution_parameters, public.system_parameters,
  public.legal_workweek_references, public.institutional_calendars, public.assignment_catalog,
  public.assignment_requests, public.replacements, public.vacancies, public.monthly_planning,
  public.sic_actuals from anon;
grant select on public.institutes, public.professionals, public.contract_versions,
  public.distribution_parameters, public.system_parameters, public.legal_workweek_references,
  public.institutional_calendars, public.assignment_catalog, public.assignment_requests,
  public.monthly_planning, public.sic_actuals to authenticated;

commit;
