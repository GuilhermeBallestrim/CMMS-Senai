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
    role            varchar(24) not null check (role in ('professor', 'tecnico', 'administrator')),
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
create index if not exists ix_equipment_sector_id on equipment (sector_id);
create index if not exists ix_equipment_responsible_id on equipment (responsible_id);
create index if not exists ix_equipment_state on equipment (state);

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
create index if not exists ix_maintenance_calls_requester_id on maintenance_calls (requester_id);
create index if not exists ix_maintenance_calls_equipment_id on maintenance_calls (equipment_id);
create index if not exists ix_maintenance_calls_status on maintenance_calls (status);
create index if not exists ix_maintenance_calls_created_at on maintenance_calls (created_at);

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
create index if not exists ix_work_orders_call_id on work_orders (call_id);
create index if not exists ix_work_orders_responsible_id on work_orders (responsible_id);
create index if not exists ix_work_orders_status on work_orders (status);

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
create index if not exists ix_purchase_requests_requester_id on purchase_requests (requester_id);
create index if not exists ix_purchase_requests_status on purchase_requests (status);

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

create table if not exists audit_logs (
    id              serial primary key,
    actor_id        integer references users (id) on delete set null,
    action          varchar(80) not null,
    entity_type     varchar(80) not null,
    entity_id       integer,
    details         varchar(500) not null,
    created_at      timestamp with time zone not null default now()
);

create index if not exists ix_audit_logs_actor_id on audit_logs (actor_id);
create index if not exists ix_audit_logs_created_at on audit_logs (created_at);

-- ============================================================
-- Funções RPC para operações atômicas (§5.1 / §7.3)
-- ============================================================

-- Aprova um chamado e cria a OS correspondente em uma única transação.
create or replace function approve_call_atomic(p_call_id int, p_admin_id int, p_number text)
returns json
language plpgsql
as $$
declare
    v_call maintenance_calls%rowtype;
    v_order work_orders%rowtype;
begin
    select * into v_call from maintenance_calls where id = p_call_id for update;
    if not found then
        raise exception 'Chamado não encontrado' using errcode = 'P0002';
    end if;
    if v_call.status = 'Cancelado' then
        raise exception 'Chamados cancelados não podem gerar ordem de serviço' using errcode = 'P0001';
    end if;
    select * into v_order from work_orders where call_id = p_call_id;
    if found then
        return json_build_object('id', v_order.id, 'number', v_order.number, 'status', v_order.status);
    end if;
    insert into work_orders (number, call_id, responsible_id, status)
    values (p_number, p_call_id, p_admin_id, 'Aguardando início')
    returning * into v_order;
    update maintenance_calls set status = 'Em análise', updated_at = now() where id = p_call_id;
    return json_build_object('id', v_order.id, 'number', v_order.number, 'status', v_order.status);
end;
$$;

-- Conclui uma OS atualizando chamado e equipamento na mesma transação.
create or replace function conclude_order_atomic(p_order_id int, p_solution text)
returns void
language plpgsql
as $$
declare
    v_order work_orders%rowtype;
    v_call maintenance_calls%rowtype;
begin
    select * into v_order from work_orders where id = p_order_id for update;
    if not found then
        raise exception 'Ordem de serviço não encontrada' using errcode = 'P0002';
    end if;
    if v_order.status = 'Concluída' then
        raise exception 'Ordem concluída não pode ser alterada' using errcode = 'P0001';
    end if;
    if coalesce(trim(p_solution), '') = '' then
        raise exception 'Solução obrigatória para conclusão' using errcode = 'P0001';
    end if;
    update work_orders
       set status = 'Concluída',
           solution = p_solution,
           finished_at = now()
     where id = p_order_id;
    select * into v_call from maintenance_calls where id = v_order.call_id;
    if found then
        update maintenance_calls set status = 'Concluído', updated_at = now() where id = v_call.id;
        update equipment set state = 'Disponível' where id = (select equipment_id from maintenance_calls where id = v_call.id);
    end if;
end;
$$;

-- Dados iniciais obrigatórios
insert into unit_settings (id, unit_name, timezone_name, notify_admin_new_call)
values (1, 'SENAI — São Paulo', 'America/Sao_Paulo', true)
on conflict (id) do nothing;

insert into sectors (name) values ('Usinagem'), ('Plástico'), ('Utilidades'), ('Marcenaria')
on conflict (name) do nothing;
