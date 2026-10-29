-- SENAI CMMS — schema no Supabase (Postgres)
-- Execute no SQL Editor do Supabase (Settings -> SQL Editor -> New query).
-- A ordem importa: setores, users, equipment -> demais.

create table if not exists sectors (
    id              serial primary key,
    name            varchar(100) not null unique
);

create table if not exists users (
    id              serial primary key,
    name            varchar(120) not null,
    email           varchar(254) not null unique,
    password_hash   varchar(255) not null,
    role            varchar(24) not null check (role in ('professor', 'administrator')),
    is_active       boolean not null default true,
    created_at      timestamp with time zone not null default now()
);

create index if not exists ix_users_email on users (email);

create table if not exists unit_settings (
    id                  integer primary key default 1,
    unit_name           varchar(160) not null default 'SENAI — São Paulo',
    timezone_name       varchar(80) not null default 'America/Sao_Paulo',
    notify_admin_new_call boolean not null default true
);

create table if not exists equipment (
    id              serial primary key,
    name            varchar(120) not null,
    sector_id       integer not null references sectors (id) on delete restrict,
    model           varchar(120),
    asset_tag       varchar(80) not null unique,
    serial_number   varchar(100),
    acquired_at     date,
    responsible_id  integer references users (id) on delete set null,
    state           varchar(30) not null default 'Disponível',
    photo_name      varchar(255),
    manual_name     varchar(255),
    photo_mime      varchar(40),
    manual_mime     varchar(40),
    created_at      timestamp with time zone not null default now()
);

create index if not exists ix_equipment_name on equipment (name);

create table if not exists maintenance_calls (
    id              serial primary key,
    number          varchar(24) not null unique,
    equipment_id    integer not null references equipment (id) on delete restrict,
    requester_id    integer not null references users (id) on delete restrict,
    description     text not null,
    priority        varchar(16) not null,
    status          varchar(32) not null default 'Aberto',
    created_at      timestamp with time zone not null default now(),
    updated_at      timestamp with time zone not null default now(),
    photo_name      varchar(255),
    photo_mime      varchar(40)
);

create index if not exists ix_maintenance_calls_number on maintenance_calls (number);

create table if not exists work_orders (
    id              serial primary key,
    number          varchar(24) not null unique,
    call_id         integer not null unique references maintenance_calls (id) on delete restrict,
    responsible_id  integer not null references users (id) on delete restrict,
    status          varchar(32) not null default 'Aguardando início',
    started_at      timestamp with time zone,
    finished_at     timestamp with time zone,
    defect          text,
    cause           text,
    solution        text,
    parts           text,
    notes           text
);

create index if not exists ix_work_orders_number on work_orders (number);

create table if not exists purchase_requests (
    id              serial primary key,
    number          varchar(24) not null unique,
    item_type       varchar(40) not null,
    item            varchar(180) not null,
    quantity        integer not null,
    justification   text not null,
    requester_id    integer not null references users (id) on delete restrict,
    status          varchar(24) not null default 'Em análise',
    reviewed_by_id  integer references users (id) on delete set null,
    created_at      timestamp with time zone not null default now()
);

create index if not exists ix_purchase_requests_number on purchase_requests (number);

create table if not exists notifications (
    id              serial primary key,
    user_id         integer not null references users (id) on delete cascade,
    title           varchar(160) not null,
    message         varchar(500) not null,
    href            varchar(255) not null,
    kind            varchar(24) not null default 'info',
    is_read         boolean not null default false,
    created_at      timestamp with time zone not null default now()
);

create index if not exists ix_notifications_user_id on notifications (user_id);

-- Dados iniciais obrigatórios
insert into unit_settings (id, unit_name, timezone_name, notify_admin_new_call)
values (1, 'SENAI — São Paulo', 'America/Sao_Paulo', true)
on conflict (id) do nothing;

insert into sectors (name) values ('Usinagem'), ('Plástico'), ('Utilidades'), ('Marcenaria')
on conflict (name) do nothing;
