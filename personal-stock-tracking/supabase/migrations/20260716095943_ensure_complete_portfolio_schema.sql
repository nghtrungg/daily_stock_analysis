-- Additive, data-preserving portfolio schema convergence.
--
-- This migration never drops or truncates a table and never deletes user rows.
-- Existing rows are retained. If saved data violates a required invariant, the
-- migration raises a descriptive exception and rolls back instead of repairing
-- the data destructively.

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table if not exists public.portfolio_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid(),
  transaction_type text not null,
  symbol text not null,
  quantity numeric(18, 4) not null,
  unit_price_vnd bigint not null,
  fee_vnd bigint not null default 0,
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  tax_vnd bigint not null default 0,
  updated_at timestamptz not null default now()
);

create table if not exists public.watchlist_symbols (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid(),
  symbol text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.analysis_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  symbol text not null,
  status text not null,
  requested_at timestamptz not null default now(),
  completed_at timestamptz,
  summary text,
  error_code text,
  updated_at timestamptz not null default now(),
  current_price_vnd bigint,
  quote_as_of timestamptz,
  quote_source text,
  external_run_id text,
  external_run_url text
);

create table if not exists public.portfolio_wallets (
  user_id uuid primary key,
  currency text not null default 'VND',
  available_cash_vnd bigint not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.portfolio_cash_entries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid(),
  entry_type text not null,
  amount_vnd bigint not null,
  note text,
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Converge additive columns for databases created from an older schema.
alter table public.portfolio_transactions
  add column if not exists tax_vnd bigint not null default 0,
  add column if not exists updated_at timestamptz not null default now();

alter table public.analysis_runs
  add column if not exists current_price_vnd bigint,
  add column if not exists quote_as_of timestamptz,
  add column if not exists quote_source text,
  add column if not exists external_run_id text,
  add column if not exists external_run_url text;

-- Refuse to round or truncate existing quantities when adding the intended
-- numeric(18,4) boundary.
do $$
begin
  if exists (
    select 1
    from public.portfolio_transactions
    where quantity <> round(quantity, 4)
       or abs(quantity) > 99999999999999.9999
  ) then
    raise exception 'SCHEMA_MIGRATION_INVALID_QUANTITY: existing quantities do not fit numeric(18,4)';
  end if;
end;
$$;

alter table public.portfolio_transactions
  alter column quantity type numeric(18, 4) using quantity::numeric(18, 4),
  alter column fee_vnd set default 0,
  alter column tax_vnd set default 0,
  alter column updated_at set default now();

alter table public.portfolio_wallets
  alter column currency set default 'VND',
  alter column available_cash_vnd set default 0,
  alter column created_at set default now(),
  alter column updated_at set default now();

alter table public.portfolio_cash_entries
  alter column user_id set default auth.uid(),
  alter column created_at set default now(),
  alter column updated_at set default now();

-- Recreate known constraints with explicit names. These operations preserve
-- rows; an incompatible row causes the transaction to roll back.
alter table public.portfolio_transactions
  drop constraint if exists portfolio_transactions_transaction_type_check,
  drop constraint if exists portfolio_transactions_symbol_check,
  drop constraint if exists portfolio_transactions_quantity_check,
  drop constraint if exists portfolio_transactions_unit_price_vnd_check,
  drop constraint if exists portfolio_transactions_fee_vnd_check,
  drop constraint if exists portfolio_transactions_tax_vnd_check,
  drop constraint if exists portfolio_transactions_user_id_fkey,
  add constraint portfolio_transactions_transaction_type_check check (transaction_type in ('buy', 'sell')),
  add constraint portfolio_transactions_symbol_check check (symbol = upper(symbol) and symbol ~ '^[A-Z0-9]{1,10}[.]VN$'),
  add constraint portfolio_transactions_quantity_check check (quantity > 0),
  add constraint portfolio_transactions_unit_price_vnd_check check (unit_price_vnd > 0),
  add constraint portfolio_transactions_fee_vnd_check check (fee_vnd >= 0),
  add constraint portfolio_transactions_tax_vnd_check check (tax_vnd >= 0),
  add constraint portfolio_transactions_user_id_fkey foreign key (user_id) references auth.users (id) on delete cascade;

alter table public.watchlist_symbols
  drop constraint if exists watchlist_symbols_symbol_check,
  drop constraint if exists watchlist_symbols_user_id_symbol_key,
  drop constraint if exists watchlist_symbols_user_id_fkey,
  add constraint watchlist_symbols_symbol_check check (symbol = upper(symbol) and symbol ~ '^[A-Z0-9]{1,10}[.]VN$'),
  add constraint watchlist_symbols_user_id_symbol_key unique (user_id, symbol),
  add constraint watchlist_symbols_user_id_fkey foreign key (user_id) references auth.users (id) on delete cascade;

alter table public.analysis_runs
  drop constraint if exists analysis_runs_symbol_check,
  drop constraint if exists analysis_runs_status_check,
  drop constraint if exists analysis_runs_summary_check,
  drop constraint if exists analysis_runs_error_code_check,
  drop constraint if exists analysis_runs_current_price_vnd_check,
  drop constraint if exists analysis_runs_quote_source_check,
  drop constraint if exists analysis_runs_external_run_id_check,
  drop constraint if exists analysis_runs_external_run_url_check,
  drop constraint if exists analysis_runs_quote_fields_complete_check,
  drop constraint if exists analysis_runs_user_id_fkey,
  add constraint analysis_runs_symbol_check check (symbol = upper(symbol) and symbol ~ '^[A-Z0-9]{1,10}[.]VN$'),
  add constraint analysis_runs_status_check check (status in ('queued', 'dispatched', 'running', 'succeeded', 'failed')),
  add constraint analysis_runs_summary_check check (summary is null or char_length(summary) between 1 and 4000),
  add constraint analysis_runs_error_code_check check (
    error_code is null or error_code in (
      'SOURCE_UNAVAILABLE', 'PROCESSING_FAILED', 'DISPATCH_FAILED', 'WORKER_NOT_CONFIGURED',
      'QUOTE_UNAVAILABLE', 'CALLBACK_TIMEOUT'
    )
  ),
  add constraint analysis_runs_current_price_vnd_check check (current_price_vnd > 0),
  add constraint analysis_runs_quote_source_check check (quote_source is null or char_length(quote_source) between 1 and 120),
  add constraint analysis_runs_external_run_id_check check (external_run_id is null or char_length(external_run_id) between 1 and 120),
  add constraint analysis_runs_external_run_url_check check (external_run_url is null or char_length(external_run_url) between 1 and 2048),
  add constraint analysis_runs_quote_fields_complete_check check (
    num_nonnulls(current_price_vnd, quote_as_of, quote_source) in (0, 3)
  ),
  add constraint analysis_runs_user_id_fkey foreign key (user_id) references auth.users (id) on delete cascade;

alter table public.portfolio_wallets
  drop constraint if exists portfolio_wallets_currency_check,
  drop constraint if exists portfolio_wallets_available_cash_vnd_check,
  drop constraint if exists portfolio_wallets_user_id_fkey,
  add constraint portfolio_wallets_currency_check check (currency = 'VND'),
  add constraint portfolio_wallets_available_cash_vnd_check check (available_cash_vnd >= 0),
  add constraint portfolio_wallets_user_id_fkey foreign key (user_id) references auth.users (id) on delete cascade;

alter table public.portfolio_cash_entries
  drop constraint if exists portfolio_cash_entries_entry_type_check,
  drop constraint if exists portfolio_cash_entries_amount_vnd_check,
  drop constraint if exists portfolio_cash_entries_note_check,
  drop constraint if exists portfolio_cash_entries_user_id_fkey,
  add constraint portfolio_cash_entries_entry_type_check check (entry_type in ('deposit', 'withdrawal', 'opening_balance')),
  add constraint portfolio_cash_entries_amount_vnd_check check (amount_vnd > 0),
  add constraint portfolio_cash_entries_note_check check (note is null or char_length(note) between 1 and 500),
  add constraint portfolio_cash_entries_user_id_fkey foreign key (user_id) references auth.users (id) on delete cascade;

create index if not exists portfolio_transactions_owner_occurred_at_idx
  on public.portfolio_transactions (user_id, occurred_at desc);
create index if not exists portfolio_transactions_owner_replay_idx
  on public.portfolio_transactions (user_id, occurred_at, created_at, id);
create index if not exists watchlist_symbols_owner_created_at_idx
  on public.watchlist_symbols (user_id, created_at desc);
create index if not exists analysis_runs_owner_requested_at_idx
  on public.analysis_runs (user_id, requested_at desc);
create unique index if not exists analysis_runs_one_active_run_per_symbol_idx
  on public.analysis_runs (user_id, symbol)
  where status in ('queued', 'dispatched', 'running');
create index if not exists analysis_runs_owner_symbol_quote_idx
  on public.analysis_runs (user_id, symbol, quote_as_of desc)
  where status = 'succeeded' and current_price_vnd is not null;
create index if not exists portfolio_cash_entries_owner_occurred_at_idx
  on public.portfolio_cash_entries (user_id, occurred_at, created_at, id);

create or replace function private.enforce_analysis_cooldown()
returns trigger
language plpgsql
security definer
set search_path = ''
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

revoke all on function private.enforce_analysis_cooldown() from public, anon, authenticated;
drop trigger if exists analysis_runs_enforce_cooldown on public.analysis_runs;
create trigger analysis_runs_enforce_cooldown
before insert on public.analysis_runs
for each row execute function private.enforce_analysis_cooldown();

create or replace function private.replay_portfolio_ledger(p_user_id uuid)
returns bigint
language plpgsql
set search_path = ''
as $$
declare
  v_event record;
  v_cash bigint := 0;
  v_effect bigint;
  v_held numeric(18, 4);
  v_shares jsonb := '{}'::jsonb;
begin
  for v_event in
    select * from (
      select 'cash'::text as kind, id, entry_type as event_type, null::text as symbol,
        null::numeric as quantity, null::bigint as unit_price_vnd, null::bigint as fee_vnd,
        null::bigint as tax_vnd, amount_vnd, occurred_at, created_at
      from public.portfolio_cash_entries where user_id = p_user_id
      union all
      select 'trade', id, transaction_type, symbol, quantity, unit_price_vnd, fee_vnd,
        tax_vnd, null::bigint, occurred_at, created_at
      from public.portfolio_transactions where user_id = p_user_id
    ) events
    order by occurred_at, created_at, id
  loop
    if v_event.kind = 'cash' then
      v_effect := case when v_event.event_type = 'withdrawal' then -v_event.amount_vnd else v_event.amount_vnd end;
    elsif v_event.event_type = 'buy' then
      v_effect := -(round(v_event.quantity * v_event.unit_price_vnd)::bigint + v_event.fee_vnd);
      v_held := coalesce((v_shares ->> v_event.symbol)::numeric, 0) + v_event.quantity;
      v_shares := jsonb_set(v_shares, array[v_event.symbol], to_jsonb(v_held), true);
    else
      v_held := coalesce((v_shares ->> v_event.symbol)::numeric, 0);
      if v_held < v_event.quantity then
        raise exception 'INSUFFICIENT_SHARES' using errcode = 'P0001';
      end if;
      v_shares := jsonb_set(v_shares, array[v_event.symbol], to_jsonb(v_held - v_event.quantity), true);
      v_effect := round(v_event.quantity * v_event.unit_price_vnd)::bigint - v_event.fee_vnd - v_event.tax_vnd;
    end if;

    v_cash := v_cash + v_effect;
    if v_cash < 0 then
      raise exception 'INSUFFICIENT_CASH' using errcode = 'P0001';
    end if;
  end loop;
  return v_cash;
end;
$$;

create or replace function private.minimum_opening_balance(p_user_id uuid)
returns bigint
language plpgsql
set search_path = ''
as $$
declare
  v_trade record;
  v_cash bigint := 0;
  v_min_cash bigint := 0;
  v_held numeric(18, 4);
  v_shares jsonb := '{}'::jsonb;
begin
  for v_trade in
    select * from public.portfolio_transactions
    where user_id = p_user_id order by occurred_at, created_at, id
  loop
    v_held := coalesce((v_shares ->> v_trade.symbol)::numeric, 0);
    if v_trade.transaction_type = 'buy' then
      v_shares := jsonb_set(v_shares, array[v_trade.symbol], to_jsonb(v_held + v_trade.quantity), true);
      v_cash := v_cash - round(v_trade.quantity * v_trade.unit_price_vnd)::bigint - v_trade.fee_vnd;
    else
      if v_held < v_trade.quantity then
        raise exception 'MIGRATION_INSUFFICIENT_SHARES user=% trade=%', p_user_id, v_trade.id using errcode = 'P0001';
      end if;
      v_shares := jsonb_set(v_shares, array[v_trade.symbol], to_jsonb(v_held - v_trade.quantity), true);
      v_cash := v_cash + round(v_trade.quantity * v_trade.unit_price_vnd)::bigint - v_trade.fee_vnd - v_trade.tax_vnd;
    end if;
    v_min_cash := least(v_min_cash, v_cash);
  end loop;
  return -v_min_cash;
end;
$$;

create or replace function private.portfolio_trade_cash_effect(p_user_id uuid)
returns bigint
language sql
stable
set search_path = ''
as $$
  select coalesce(sum(
    case transaction_type
      when 'buy' then -(round(quantity * unit_price_vnd)::bigint + fee_vnd)
      else round(quantity * unit_price_vnd)::bigint - fee_vnd - tax_vnd
    end
  ), 0)::bigint
  from public.portfolio_transactions
  where user_id = p_user_id;
$$;

create or replace function private.portfolio_ledger_snapshot(p_user_id uuid)
returns jsonb
language sql
stable
set search_path = ''
as $$
  select jsonb_build_object(
    'wallet', coalesce(
      (select to_jsonb(w) from public.portfolio_wallets w where w.user_id = p_user_id),
      jsonb_build_object('user_id', p_user_id, 'currency', 'VND', 'available_cash_vnd', 0)
    ),
    'cash_entries', coalesce(
      (select jsonb_agg(to_jsonb(c) order by c.occurred_at, c.created_at, c.id)
       from public.portfolio_cash_entries c where c.user_id = p_user_id),
      '[]'::jsonb
    ),
    'transactions', coalesce(
      (select jsonb_agg(to_jsonb(t) order by t.occurred_at, t.created_at, t.id)
       from public.portfolio_transactions t where t.user_id = p_user_id),
      '[]'::jsonb
    )
  );
$$;

revoke all on function private.replay_portfolio_ledger(uuid) from public, anon, authenticated;
revoke all on function private.minimum_opening_balance(uuid) from public, anon, authenticated;
revoke all on function private.portfolio_trade_cash_effect(uuid) from public, anon, authenticated;
revoke all on function private.portfolio_ledger_snapshot(uuid) from public, anon, authenticated;

-- Preserve existing ledgers and wallet balances. Transaction-only users receive
-- the minimum opening balance needed for a valid history. An existing wallet is
-- never silently overwritten when it disagrees with its ledger.
do $$
declare
  v_user record;
  v_has_cash boolean;
  v_has_wallet boolean;
  v_existing_wallet bigint;
  v_minimum_opening bigint;
  v_trade_effect bigint;
  v_target_opening numeric;
  v_first timestamptz;
  v_ending bigint;
begin
  for v_user in
    select user_id from public.portfolio_transactions
    union
    select user_id from public.portfolio_cash_entries
    union
    select user_id from public.portfolio_wallets
  loop
    select exists (
      select 1 from public.portfolio_cash_entries where user_id = v_user.user_id
    ) into v_has_cash;

    select exists (
      select 1 from public.portfolio_wallets where user_id = v_user.user_id
    ) into v_has_wallet;

    if v_has_wallet then
      select available_cash_vnd into v_existing_wallet
      from public.portfolio_wallets where user_id = v_user.user_id;
    else
      v_existing_wallet := null;
    end if;

    if not v_has_cash then
      v_minimum_opening := private.minimum_opening_balance(v_user.user_id);
      v_trade_effect := private.portfolio_trade_cash_effect(v_user.user_id);

      if v_has_wallet then
        v_target_opening := v_existing_wallet::numeric - v_trade_effect::numeric;
        if v_target_opening < v_minimum_opening
           or v_target_opening > 9223372036854775807 then
          raise exception 'SCHEMA_MIGRATION_WALLET_HISTORY_MISMATCH user=%', v_user.user_id;
        end if;
      else
        v_target_opening := v_minimum_opening;
      end if;

      if v_target_opening > 0 then
        select min(occurred_at) into v_first
        from public.portfolio_transactions where user_id = v_user.user_id;

        insert into public.portfolio_cash_entries (
          user_id, entry_type, amount_vnd, note, occurred_at, created_at, updated_at
        ) values (
          v_user.user_id,
          'opening_balance',
          v_target_opening::bigint,
          'Số dư đầu kỳ được tạo khi chuyển đổi dữ liệu',
          coalesce(v_first - interval '1 microsecond', now()),
          coalesce(v_first - interval '1 microsecond', now()),
          now()
        );
      end if;
    end if;

    v_ending := private.replay_portfolio_ledger(v_user.user_id);
    if v_has_wallet and v_existing_wallet <> v_ending then
      raise exception 'SCHEMA_MIGRATION_WALLET_LEDGER_MISMATCH user=% wallet=% ledger=%',
        v_user.user_id, v_existing_wallet, v_ending;
    end if;

    insert into public.portfolio_wallets (user_id, available_cash_vnd)
    values (v_user.user_id, v_ending)
    on conflict (user_id) do nothing;
  end loop;
end;
$$;

alter table public.portfolio_transactions enable row level security;
alter table public.watchlist_symbols enable row level security;
alter table public.analysis_runs enable row level security;
alter table public.portfolio_wallets enable row level security;
alter table public.portfolio_cash_entries enable row level security;

revoke all on public.portfolio_transactions, public.watchlist_symbols,
  public.analysis_runs, public.portfolio_wallets, public.portfolio_cash_entries
from anon, authenticated;

grant select on public.portfolio_transactions to authenticated;
grant select, insert, delete on public.watchlist_symbols to authenticated;
grant select on public.analysis_runs to authenticated;
grant select on public.portfolio_wallets, public.portfolio_cash_entries to authenticated;
grant select, insert, update, delete on public.analysis_runs to service_role;

drop policy if exists "portfolio transactions are visible to their owner" on public.portfolio_transactions;
drop policy if exists "portfolio transactions are created by their owner" on public.portfolio_transactions;
drop policy if exists "portfolio transactions are updated by their owner" on public.portfolio_transactions;
drop policy if exists "portfolio transactions are deleted by their owner" on public.portfolio_transactions;
create policy "portfolio transactions are visible to their owner"
on public.portfolio_transactions for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "watchlist symbols are visible to their owner" on public.watchlist_symbols;
drop policy if exists "watchlist symbols are created by their owner" on public.watchlist_symbols;
drop policy if exists "watchlist symbols are deleted by their owner" on public.watchlist_symbols;
create policy "watchlist symbols are visible to their owner"
on public.watchlist_symbols for select to authenticated
using ((select auth.uid()) = user_id);
create policy "watchlist symbols are created by their owner"
on public.watchlist_symbols for insert to authenticated
with check ((select auth.uid()) = user_id);
create policy "watchlist symbols are deleted by their owner"
on public.watchlist_symbols for delete to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "analysis runs are visible to their owner" on public.analysis_runs;
create policy "analysis runs are visible to their owner"
on public.analysis_runs for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "portfolio wallets are visible to their owner" on public.portfolio_wallets;
create policy "portfolio wallets are visible to their owner"
on public.portfolio_wallets for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "portfolio cash entries are visible to their owner" on public.portfolio_cash_entries;
create policy "portfolio cash entries are visible to their owner"
on public.portfolio_cash_entries for select to authenticated
using ((select auth.uid()) = user_id);

create or replace function private.lock_portfolio_wallet(p_user_id uuid)
returns void
language plpgsql
set search_path = ''
as $$
begin
  insert into public.portfolio_wallets (user_id)
  values (p_user_id)
  on conflict (user_id) do nothing;

  perform 1
  from public.portfolio_wallets
  where user_id = p_user_id
  for update;
end;
$$;

drop function if exists private.lock_and_refresh_wallet(uuid);

create or replace function private.refresh_portfolio_wallet(p_user_id uuid)
returns void
language plpgsql
set search_path = ''
as $$
declare
  v_cash bigint;
begin
  v_cash := private.replay_portfolio_ledger(p_user_id);
  update public.portfolio_wallets
  set available_cash_vnd = v_cash,
      updated_at = now()
  where user_id = p_user_id;
end;
$$;

revoke all on function private.lock_portfolio_wallet(uuid) from public, anon, authenticated;
revoke all on function private.refresh_portfolio_wallet(uuid) from public, anon, authenticated;

create or replace function public.record_cash_entry(
  p_entry_type text,
  p_amount_vnd bigint,
  p_occurred_at timestamptz,
  p_note text default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user uuid := auth.uid();
begin
  if v_user is null then
    raise exception 'AUTH_REQUIRED' using errcode = 'P0001';
  end if;

  perform private.lock_portfolio_wallet(v_user);

  if p_entry_type not in ('deposit', 'withdrawal')
     or p_amount_vnd <= 0
     or p_occurred_at is null
     or (p_note is not null and (char_length(btrim(p_note)) = 0 or char_length(p_note) > 500)) then
    raise exception 'INVALID_CASH_ENTRY' using errcode = 'P0001';
  end if;

  insert into public.portfolio_cash_entries (
    user_id, entry_type, amount_vnd, note, occurred_at
  ) values (
    v_user, p_entry_type, p_amount_vnd, nullif(btrim(p_note), ''), p_occurred_at
  );

  perform private.refresh_portfolio_wallet(v_user);
  return private.portfolio_ledger_snapshot(v_user);
end;
$$;

create or replace function public.update_cash_entry(
  p_id uuid,
  p_expected_updated_at timestamptz,
  p_entry_type text,
  p_amount_vnd bigint,
  p_occurred_at timestamptz,
  p_note text default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user uuid := auth.uid();
begin
  if v_user is null then
    raise exception 'AUTH_REQUIRED' using errcode = 'P0001';
  end if;

  perform private.lock_portfolio_wallet(v_user);

  if p_entry_type not in ('deposit', 'withdrawal')
     or p_amount_vnd <= 0
     or p_occurred_at is null
     or (p_note is not null and (char_length(btrim(p_note)) = 0 or char_length(p_note) > 500)) then
    raise exception 'INVALID_CASH_ENTRY' using errcode = 'P0001';
  end if;

  update public.portfolio_cash_entries
  set entry_type = p_entry_type,
      amount_vnd = p_amount_vnd,
      note = nullif(btrim(p_note), ''),
      occurred_at = p_occurred_at,
      updated_at = now()
  where id = p_id
    and user_id = v_user
    and updated_at = p_expected_updated_at
    and entry_type <> 'opening_balance';

  if not found then
    raise exception 'STALE_ENTRY' using errcode = 'P0001';
  end if;

  perform private.refresh_portfolio_wallet(v_user);
  return private.portfolio_ledger_snapshot(v_user);
end;
$$;

create or replace function public.delete_cash_entry(
  p_id uuid,
  p_expected_updated_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user uuid := auth.uid();
begin
  if v_user is null then
    raise exception 'AUTH_REQUIRED' using errcode = 'P0001';
  end if;

  perform private.lock_portfolio_wallet(v_user);

  delete from public.portfolio_cash_entries
  where id = p_id
    and user_id = v_user
    and updated_at = p_expected_updated_at
    and entry_type <> 'opening_balance';

  if not found then
    raise exception 'STALE_ENTRY' using errcode = 'P0001';
  end if;

  perform private.refresh_portfolio_wallet(v_user);
  return private.portfolio_ledger_snapshot(v_user);
end;
$$;

create or replace function public.record_portfolio_trade(
  p_transaction_type text,
  p_symbol text,
  p_quantity numeric,
  p_unit_price_vnd bigint,
  p_fee_vnd bigint,
  p_tax_vnd bigint,
  p_occurred_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user uuid := auth.uid();
begin
  if v_user is null then
    raise exception 'AUTH_REQUIRED' using errcode = 'P0001';
  end if;

  perform private.lock_portfolio_wallet(v_user);

  if p_transaction_type not in ('buy', 'sell')
     or p_symbol !~ '^[A-Z0-9]{1,10}[.]VN$'
     or p_quantity <= 0
     or scale(p_quantity) > 4
     or p_quantity > 99999999999999.9999
     or p_unit_price_vnd <= 0
     or p_fee_vnd < 0
     or p_tax_vnd < 0
     or p_occurred_at is null then
    raise exception 'INVALID_TRADE' using errcode = 'P0001';
  end if;

  insert into public.portfolio_transactions (
    user_id, transaction_type, symbol, quantity, unit_price_vnd,
    fee_vnd, tax_vnd, occurred_at
  ) values (
    v_user, p_transaction_type, p_symbol, p_quantity, p_unit_price_vnd,
    p_fee_vnd, p_tax_vnd, p_occurred_at
  );

  perform private.refresh_portfolio_wallet(v_user);
  return private.portfolio_ledger_snapshot(v_user);
end;
$$;

create or replace function public.update_portfolio_trade(
  p_id uuid,
  p_expected_updated_at timestamptz,
  p_transaction_type text,
  p_symbol text,
  p_quantity numeric,
  p_unit_price_vnd bigint,
  p_fee_vnd bigint,
  p_tax_vnd bigint,
  p_occurred_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user uuid := auth.uid();
begin
  if v_user is null then
    raise exception 'AUTH_REQUIRED' using errcode = 'P0001';
  end if;

  perform private.lock_portfolio_wallet(v_user);

  if p_transaction_type not in ('buy', 'sell')
     or p_symbol !~ '^[A-Z0-9]{1,10}[.]VN$'
     or p_quantity <= 0
     or scale(p_quantity) > 4
     or p_quantity > 99999999999999.9999
     or p_unit_price_vnd <= 0
     or p_fee_vnd < 0
     or p_tax_vnd < 0
     or p_occurred_at is null then
    raise exception 'INVALID_TRADE' using errcode = 'P0001';
  end if;

  update public.portfolio_transactions
  set transaction_type = p_transaction_type,
      symbol = p_symbol,
      quantity = p_quantity,
      unit_price_vnd = p_unit_price_vnd,
      fee_vnd = p_fee_vnd,
      tax_vnd = p_tax_vnd,
      occurred_at = p_occurred_at,
      updated_at = now()
  where id = p_id
    and user_id = v_user
    and updated_at = p_expected_updated_at;

  if not found then
    raise exception 'STALE_ENTRY' using errcode = 'P0001';
  end if;

  perform private.refresh_portfolio_wallet(v_user);
  return private.portfolio_ledger_snapshot(v_user);
end;
$$;

create or replace function public.delete_portfolio_trade(
  p_id uuid,
  p_expected_updated_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user uuid := auth.uid();
begin
  if v_user is null then
    raise exception 'AUTH_REQUIRED' using errcode = 'P0001';
  end if;

  perform private.lock_portfolio_wallet(v_user);

  delete from public.portfolio_transactions
  where id = p_id
    and user_id = v_user
    and updated_at = p_expected_updated_at;

  if not found then
    raise exception 'STALE_ENTRY' using errcode = 'P0001';
  end if;

  perform private.refresh_portfolio_wallet(v_user);
  return private.portfolio_ledger_snapshot(v_user);
end;
$$;

revoke all on function public.record_cash_entry(text, bigint, timestamptz, text)
  from public, anon, authenticated;
revoke all on function public.update_cash_entry(uuid, timestamptz, text, bigint, timestamptz, text)
  from public, anon, authenticated;
revoke all on function public.delete_cash_entry(uuid, timestamptz)
  from public, anon, authenticated;
revoke all on function public.record_portfolio_trade(text, text, numeric, bigint, bigint, bigint, timestamptz)
  from public, anon, authenticated;
revoke all on function public.update_portfolio_trade(uuid, timestamptz, text, text, numeric, bigint, bigint, bigint, timestamptz)
  from public, anon, authenticated;
revoke all on function public.delete_portfolio_trade(uuid, timestamptz)
  from public, anon, authenticated;

grant execute on function public.record_cash_entry(text, bigint, timestamptz, text)
  to authenticated;
grant execute on function public.update_cash_entry(uuid, timestamptz, text, bigint, timestamptz, text)
  to authenticated;
grant execute on function public.delete_cash_entry(uuid, timestamptz)
  to authenticated;
grant execute on function public.record_portfolio_trade(text, text, numeric, bigint, bigint, bigint, timestamptz)
  to authenticated;
grant execute on function public.update_portfolio_trade(uuid, timestamptz, text, text, numeric, bigint, bigint, bigint, timestamptz)
  to authenticated;
grant execute on function public.delete_portfolio_trade(uuid, timestamptz)
  to authenticated;

-- Final migration-time assertions. These test metadata without changing rows.
do $$
declare
  v_table text;
begin
  foreach v_table in array array[
    'portfolio_transactions',
    'watchlist_symbols',
    'analysis_runs',
    'portfolio_wallets',
    'portfolio_cash_entries'
  ]
  loop
    if not exists (
      select 1
      from pg_catalog.pg_class c
      join pg_catalog.pg_namespace n on n.oid = c.relnamespace
      where n.nspname = 'public'
        and c.relname = v_table
        and c.relrowsecurity
    ) then
      raise exception 'SCHEMA_MIGRATION_RLS_MISSING table=%', v_table;
    end if;
  end loop;
end;
$$;
