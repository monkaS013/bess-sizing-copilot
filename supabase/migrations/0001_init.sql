-- ============================================================================
-- Migration 0001 - Schema inicial do BESS Sizing Copilot
-- Versao: 0.1.0 (Sprint 3, Fase C)
-- ============================================================================
--
-- Como aplicar no Supabase Cloud:
--   1. Login em https://supabase.com -> seu projeto
--   2. SQL Editor (icone de banco no sidebar)
--   3. Cole TODO este arquivo
--   4. Clique em "Run" (ou Ctrl+Enter)
--
-- Idempotente: pode rodar quantas vezes precisar sem quebrar.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Extensoes
-- ----------------------------------------------------------------------------

create extension if not exists "uuid-ossp";


-- ----------------------------------------------------------------------------
-- Tabela: sessoes_bess
-- ----------------------------------------------------------------------------
-- Uma sessao = uma conversa com o agente, do "ola" ate "obrigado".
-- O usuario pode ter varias sessoes (uma por cliente que esta dimensionando).

create table if not exists public.sessoes_bess (
  id                       uuid primary key default gen_random_uuid(),
  usuario_id               uuid references auth.users(id) on delete cascade,
  status                   text not null default 'ativa'
                             check (status in ('ativa','encerrada','arquivada','erro')),
  agente_atual             text,
  payload                  jsonb not null default '{}'::jsonb,
  tokens_input_total       integer not null default 0,
  tokens_output_total      integer not null default 0,
  custo_usd_total          numeric(10,4) not null default 0,
  criado_em                timestamptz not null default now(),
  atualizado_em            timestamptz not null default now()
);

comment on table public.sessoes_bess is
  'Sessao de conversa com o agente BESS. Uma sessao por cliente em dimensionamento.';

create index if not exists idx_sessoes_usuario
  on public.sessoes_bess(usuario_id);
create index if not exists idx_sessoes_status
  on public.sessoes_bess(status);
create index if not exists idx_sessoes_atualizado
  on public.sessoes_bess(atualizado_em desc);


-- ----------------------------------------------------------------------------
-- Tabela: mensagens
-- ----------------------------------------------------------------------------
-- Histórico user/assistant de cada sessao. Tool calls como JSONB para
-- evitar fan-out de tabelas no MVP.

create table if not exists public.mensagens (
  id            bigserial primary key,
  sessao_id     uuid not null references public.sessoes_bess(id) on delete cascade,
  role          text not null check (role in ('user','assistant','system')),
  content       text not null,
  tool_calls    jsonb not null default '[]'::jsonb,
  tokens_input  integer not null default 0,
  tokens_output integer not null default 0,
  iteracoes     integer not null default 1,
  erro          text,
  criado_em     timestamptz not null default now()
);

comment on table public.mensagens is
  'Mensagens trocadas durante uma sessao. Tool calls dentro de cada msg como JSONB.';

create index if not exists idx_mensagens_sessao
  on public.mensagens(sessao_id, criado_em);


-- ----------------------------------------------------------------------------
-- Tabela: agente_logs
-- ----------------------------------------------------------------------------
-- Auditoria fina: cada tool call, com latencia e custo. Permite analytics
-- sobre quais tools sao mais usadas, quanto custa cada conversa, etc.

create table if not exists public.agente_logs (
  id            bigserial primary key,
  sessao_id     uuid not null references public.sessoes_bess(id) on delete cascade,
  mensagem_id   bigint references public.mensagens(id) on delete set null,
  agente        text not null default 'single',
  tool_chamada  text,
  tool_input    jsonb,
  tool_output   jsonb,
  tokens_input  integer not null default 0,
  tokens_output integer not null default 0,
  custo_usd     numeric(10,4) not null default 0,
  latencia_ms   integer,
  criado_em     timestamptz not null default now()
);

comment on table public.agente_logs is
  'Log de cada tool call e custo. Util para analytics e debugging.';

create index if not exists idx_logs_sessao
  on public.agente_logs(sessao_id);
create index if not exists idx_logs_tool
  on public.agente_logs(tool_chamada);


-- ----------------------------------------------------------------------------
-- Trigger: atualizado_em automatico
-- ----------------------------------------------------------------------------

create or replace function public.trigger_set_atualizado_em()
returns trigger as $$
begin
  new.atualizado_em = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists set_atualizado_em on public.sessoes_bess;
create trigger set_atualizado_em
  before update on public.sessoes_bess
  for each row execute function public.trigger_set_atualizado_em();


-- ----------------------------------------------------------------------------
-- Row-Level Security (RLS)
-- ----------------------------------------------------------------------------
-- Cada usuario so ve suas proprias sessoes. Anonymous auth funciona
-- normalmente: cada anonymous gera um auth.uid() unico que persiste no
-- localStorage do navegador.

alter table public.sessoes_bess enable row level security;
alter table public.mensagens    enable row level security;
alter table public.agente_logs  enable row level security;

-- Policies: sessoes_bess
drop policy if exists "select_propria_sessao" on public.sessoes_bess;
create policy "select_propria_sessao" on public.sessoes_bess
  for select using (auth.uid() = usuario_id);

drop policy if exists "insert_propria_sessao" on public.sessoes_bess;
create policy "insert_propria_sessao" on public.sessoes_bess
  for insert with check (auth.uid() = usuario_id);

drop policy if exists "update_propria_sessao" on public.sessoes_bess;
create policy "update_propria_sessao" on public.sessoes_bess
  for update using (auth.uid() = usuario_id);

drop policy if exists "delete_propria_sessao" on public.sessoes_bess;
create policy "delete_propria_sessao" on public.sessoes_bess
  for delete using (auth.uid() = usuario_id);

-- Policies: mensagens (acesso atraves da sessao)
drop policy if exists "select_propria_mensagem" on public.mensagens;
create policy "select_propria_mensagem" on public.mensagens
  for select using (
    sessao_id in (select id from public.sessoes_bess where usuario_id = auth.uid())
  );

drop policy if exists "insert_propria_mensagem" on public.mensagens;
create policy "insert_propria_mensagem" on public.mensagens
  for insert with check (
    sessao_id in (select id from public.sessoes_bess where usuario_id = auth.uid())
  );

-- Policies: agente_logs
drop policy if exists "select_proprio_log" on public.agente_logs;
create policy "select_proprio_log" on public.agente_logs
  for select using (
    sessao_id in (select id from public.sessoes_bess where usuario_id = auth.uid())
  );

-- Nota: backend Python usa SERVICE_ROLE_KEY para bypass de RLS quando
-- precisa fazer INSERT em mensagens/logs em nome do usuario. O frontend
-- usa ANON_KEY com JWT do auth.signInAnonymously() para SELECT.


-- ----------------------------------------------------------------------------
-- Smoke test (opcional - remova as 2 linhas se for rodar em prod)
-- ----------------------------------------------------------------------------

select 'sessoes_bess' as tabela, count(*) as registros from public.sessoes_bess
union all select 'mensagens',     count(*) from public.mensagens
union all select 'agente_logs',   count(*) from public.agente_logs;
