-- Esquema de parámetros para el Motor de Cálculo (Supabase / PostgreSQL)
-- Importar los CSV de ../data/ en el mismo orden en que aparecen aquí.

create table parametros_cargo (
  cargo_homologado   text not null,
  tramo              text not null check (tramo in ('>=40', '22-40', '<22')),
  cod_esp            text,
  unidad             text,
  pct_directo        numeric(5,4) not null,
  pct_indirecto      numeric(5,4) not null,
  pct_nas            numeric(5,4) not null,
  minutos_directa    integer not null,
  minutos_indirecta  integer not null default 30,
  primary key (cargo_homologado, tramo)
);

create table factor_grupal (
  cod_esp                         text primary key,   -- AS, ED, ULAB, UTAC, UEDA
  pct_grupal                      numeric(5,4) not null,
  pacientes_santiago_concepcion   numeric(4,1) not null,
  pacientes_otros_it              numeric(4,1) not null
);

create table asignaciones_especiales (
  id                        serial primary key,
  nombre                    text unique not null,
  horas_semanales           numeric(4,2),            -- null = la define DMN/GP caso a caso
  requiere_aprobacion_dmn   boolean not null default false,
  descripcion               text
);

create table calendario_2026 (
  mes               integer primary key check (mes between 1 and 12),
  dias              integer not null,
  inhabiles         integer not null,
  dias_habiles      integer not null,
  semanas_habiles   numeric(4,2) not null            -- dias_habiles / 5
);

create table feriados_regionales (
  id        serial primary key,
  it        integer not null,                        -- 11 Ari, 12 Iqu, ... 111 Coy
  fecha     date not null,
  motivo    text
);

create table parametros_generales (
  clave   text primary key,
  valor   numeric not null,
  descripcion text
);
insert into parametros_generales values
  ('meta_gestion_pct',        0.90, 'Piso de cumplimiento de la proyección anual'),
  ('max_asignaciones',        2,    'Máximo de asignaciones especiales'),
  ('umbral_horas_asignaciones', 30, 'H/S sobre las que aplica el máximo'),
  ('pausa_saludable_pct',     0.10, 'Fracción de H/S de pausa saludable'),
  ('jornada_legal_ene_abr',   44,   'Horas máximas enero-abril 2026'),
  ('jornada_legal_may_dic',   42,   'Horas máximas mayo-diciembre 2026');

create table log_auditoria (
  id              bigserial primary key,
  usuario         text not null,
  tabla           text not null,
  clave           text not null,
  campo           text,
  valor_anterior  text,
  valor_nuevo     text,
  justificacion   text,
  fecha           timestamptz not null default now()
);
