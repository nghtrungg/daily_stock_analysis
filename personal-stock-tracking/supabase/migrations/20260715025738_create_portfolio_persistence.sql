create schema if not exists private;
revoke all on schema private from public;

create table public.portfolio_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  transaction_type text not null check (transaction_type in ('buy', 'sell')),
  symbol text not null check (symbol = upper(symbol) and symbol ~ '^[A-Z0-9]{1,10}[.]VN$'),
  quantity numeric(18, 4) not null check (quantity > 0),
  unit_price_vnd bigint not null check (unit_price_vnd > 0),
  fee_vnd bigint not null default 0 check (fee_vnd >= 0),
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table public.watchlist_symbols (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  symbol text not null check (symbol = upper(symbol) and symbol ~ '^[A-Z0-9]{1,10}[.]VN$'),
  created_at timestamptz not null default now(),
  unique (user_id, symbol)
);

create table public.analysis_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  symbol text not null check (symbol = upper(symbol) and symbol ~ '^[A-Z0-9]{1,10}[.]VN$'),
  status text not null check (status in ('queued', 'dispatched', 'running', 'succeeded', 'failed')),
  requested_at timestamptz not null default now(),
  completed_at timestamptz,
  summary text check (summary is null or char_length(summary) between 1 and 4000),
  error_code text check (error_code is null or error_code in ('SOURCE_UNAVAILABLE', 'PROCESSING_FAILED', 'DISPATCH_FAILED', 'WORKER_NOT_CONFIGURED')),
  updated_at timestamptz not null default now()
);

create index portfolio_transactions_owner_occurred_at_idx
  on public.portfolio_transactions (user_id, occurred_at desc);

create index analysis_runs_owner_requested_at_idx
  on public.analysis_runs (user_id, requested_at desc);

create unique index analysis_runs_one_active_run_per_symbol_idx
  on public.analysis_runs (user_id, symbol)
  where status in ('queued', 'dispatched', 'running');

create or replace function private.enforce_analysis_cooldown()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
  if exists (
    select 1
    from public.analysis_runs
    where user_id = new.user_id
      and symbol = new.symbol
      and requested_at > now() - interval '60 seconds'
  ) then
    raise exception 'ANALYSIS_COOLDOWN_ACTIVE' using errcode = 'P0001';
  end if;

  return new;
end;
$$;

revoke all on function private.enforce_analysis_cooldown() from public;

create trigger analysis_runs_enforce_cooldown
before insert on public.analysis_runs
for each row execute function private.enforce_analysis_cooldown();

alter table public.portfolio_transactions enable row level security;
alter table public.watchlist_symbols enable row level security;
alter table public.analysis_runs enable row level security;

revoke all on public.portfolio_transactions, public.watchlist_symbols, public.analysis_runs from anon, authenticated;
grant select, insert, update, delete on public.portfolio_transactions to authenticated;
grant select, insert, delete on public.watchlist_symbols to authenticated;
grant select on public.analysis_runs to authenticated;

create policy "portfolio transactions are visible to their owner"
on public.portfolio_transactions for select to authenticated
using ((select auth.uid()) = user_id);

create policy "portfolio transactions are created by their owner"
on public.portfolio_transactions for insert to authenticated
with check ((select auth.uid()) = user_id);

create policy "portfolio transactions are updated by their owner"
on public.portfolio_transactions for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy "portfolio transactions are deleted by their owner"
on public.portfolio_transactions for delete to authenticated
using ((select auth.uid()) = user_id);

create policy "watchlist symbols are visible to their owner"
on public.watchlist_symbols for select to authenticated
using ((select auth.uid()) = user_id);

create policy "watchlist symbols are created by their owner"
on public.watchlist_symbols for insert to authenticated
with check ((select auth.uid()) = user_id);

create policy "watchlist symbols are deleted by their owner"
on public.watchlist_symbols for delete to authenticated
using ((select auth.uid()) = user_id);

create policy "analysis runs are visible to their owner"
on public.analysis_runs for select to authenticated
using ((select auth.uid()) = user_id);
