create table public.portfolio_wallets (
  user_id uuid primary key references auth.users (id) on delete cascade,
  currency text not null default 'VND' check (currency = 'VND'),
  available_cash_vnd bigint not null default 0 check (available_cash_vnd >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.portfolio_cash_entries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  entry_type text not null check (entry_type in ('deposit', 'withdrawal', 'opening_balance')),
  amount_vnd bigint not null check (amount_vnd > 0),
  note text check (note is null or char_length(note) between 1 and 500),
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.portfolio_transactions
  add column tax_vnd bigint not null default 0 check (tax_vnd >= 0),
  add column updated_at timestamptz not null default now();

alter table public.analysis_runs
  add column current_price_vnd bigint check (current_price_vnd > 0),
  add column quote_as_of timestamptz,
  add column quote_source text check (quote_source is null or char_length(quote_source) between 1 and 120),
  add column external_run_id text check (external_run_id is null or char_length(external_run_id) between 1 and 120),
  add column external_run_url text check (external_run_url is null or char_length(external_run_url) between 1 and 2048),
  add constraint analysis_runs_quote_fields_complete_check check (
    num_nonnulls(current_price_vnd, quote_as_of, quote_source) in (0, 3)
  );

alter table public.analysis_runs drop constraint if exists analysis_runs_error_code_check;
alter table public.analysis_runs add constraint analysis_runs_error_code_check check (
  error_code is null or error_code in (
    'SOURCE_UNAVAILABLE', 'PROCESSING_FAILED', 'DISPATCH_FAILED', 'WORKER_NOT_CONFIGURED',
    'QUOTE_UNAVAILABLE', 'CALLBACK_TIMEOUT'
  )
);

create index portfolio_cash_entries_owner_occurred_at_idx
  on public.portfolio_cash_entries (user_id, occurred_at, created_at, id);
create index portfolio_transactions_owner_replay_idx
  on public.portfolio_transactions (user_id, occurred_at, created_at, id);
create index analysis_runs_owner_symbol_quote_idx
  on public.analysis_runs (user_id, symbol, quote_as_of desc)
  where status = 'succeeded' and current_price_vnd is not null;

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

create or replace function private.portfolio_ledger_snapshot(p_user_id uuid)
returns jsonb
language sql
stable
set search_path = ''
as $$
  select jsonb_build_object(
    'wallet', coalesce((select to_jsonb(w) from public.portfolio_wallets w where w.user_id = p_user_id),
      jsonb_build_object('user_id', p_user_id, 'currency', 'VND', 'available_cash_vnd', 0)),
    'cash_entries', coalesce((select jsonb_agg(to_jsonb(c) order by c.occurred_at, c.created_at, c.id)
      from public.portfolio_cash_entries c where c.user_id = p_user_id), '[]'::jsonb),
    'transactions', coalesce((select jsonb_agg(to_jsonb(t) order by t.occurred_at, t.created_at, t.id)
      from public.portfolio_transactions t where t.user_id = p_user_id), '[]'::jsonb)
  );
$$;

revoke all on function private.replay_portfolio_ledger(uuid) from public, anon, authenticated;
revoke all on function private.minimum_opening_balance(uuid) from public, anon, authenticated;
revoke all on function private.portfolio_ledger_snapshot(uuid) from public, anon, authenticated;

do $$
declare
  v_user record;
  v_opening bigint;
  v_first timestamptz;
  v_ending bigint;
begin
  for v_user in
    select distinct t.user_id from public.portfolio_transactions t
    where not exists (select 1 from public.portfolio_cash_entries c where c.user_id = t.user_id)
  loop
    v_opening := private.minimum_opening_balance(v_user.user_id);
    select min(occurred_at) into v_first from public.portfolio_transactions where user_id = v_user.user_id;
    if v_opening > 0 then
      insert into public.portfolio_cash_entries (user_id, entry_type, amount_vnd, note, occurred_at, created_at, updated_at)
      values (v_user.user_id, 'opening_balance', v_opening, 'Số dư đầu kỳ được tạo khi chuyển đổi dữ liệu',
        v_first - interval '1 microsecond', v_first - interval '1 microsecond', now());
    end if;
    v_ending := private.replay_portfolio_ledger(v_user.user_id);
    insert into public.portfolio_wallets (user_id, available_cash_vnd)
    values (v_user.user_id, v_ending)
    on conflict (user_id) do update set available_cash_vnd = excluded.available_cash_vnd, updated_at = now();
  end loop;
end;
$$;

alter table public.portfolio_wallets enable row level security;
alter table public.portfolio_cash_entries enable row level security;

revoke all on public.portfolio_wallets, public.portfolio_cash_entries from anon, authenticated;
revoke insert, update, delete on public.portfolio_transactions from authenticated;
grant select on public.portfolio_wallets, public.portfolio_cash_entries to authenticated;

create policy "portfolio wallets are visible to their owner"
on public.portfolio_wallets for select to authenticated
using ((select auth.uid()) = user_id);
create policy "portfolio cash entries are visible to their owner"
on public.portfolio_cash_entries for select to authenticated
using ((select auth.uid()) = user_id);

create or replace function private.lock_portfolio_wallet(p_user_id uuid)
returns void
language plpgsql
set search_path = ''
as $$
begin
  insert into public.portfolio_wallets (user_id) values (p_user_id) on conflict do nothing;
  perform 1 from public.portfolio_wallets where user_id = p_user_id for update;
end;
$$;
revoke all on function private.lock_portfolio_wallet(uuid) from public, anon, authenticated;

create or replace function private.refresh_portfolio_wallet(p_user_id uuid)
returns void
language plpgsql
set search_path = ''
as $$
declare v_cash bigint;
begin
  v_cash := private.replay_portfolio_ledger(p_user_id);
  update public.portfolio_wallets set available_cash_vnd = v_cash, updated_at = now() where user_id = p_user_id;
end;
$$;
revoke all on function private.refresh_portfolio_wallet(uuid) from public, anon, authenticated;

create or replace function public.record_cash_entry(p_entry_type text, p_amount_vnd bigint, p_occurred_at timestamptz, p_note text default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_user uuid := auth.uid();
begin
  if v_user is null then raise exception 'AUTH_REQUIRED' using errcode = 'P0001'; end if;
  perform private.lock_portfolio_wallet(v_user);
  if p_entry_type not in ('deposit', 'withdrawal') or p_amount_vnd <= 0 or p_occurred_at is null
    or (p_note is not null and (char_length(btrim(p_note)) = 0 or char_length(p_note) > 500))
  then raise exception 'INVALID_CASH_ENTRY' using errcode = 'P0001'; end if;
  insert into public.portfolio_cash_entries (user_id, entry_type, amount_vnd, note, occurred_at)
  values (v_user, p_entry_type, p_amount_vnd, nullif(btrim(p_note), ''), p_occurred_at);
  perform private.refresh_portfolio_wallet(v_user);
  return private.portfolio_ledger_snapshot(v_user);
end; $$;

create or replace function public.update_cash_entry(p_id uuid, p_expected_updated_at timestamptz, p_entry_type text, p_amount_vnd bigint, p_occurred_at timestamptz, p_note text default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_user uuid := auth.uid();
begin
  if v_user is null then raise exception 'AUTH_REQUIRED' using errcode = 'P0001'; end if;
  perform private.lock_portfolio_wallet(v_user);
  if p_entry_type not in ('deposit', 'withdrawal') or p_amount_vnd <= 0 or p_occurred_at is null
  then raise exception 'INVALID_CASH_ENTRY' using errcode = 'P0001'; end if;
  update public.portfolio_cash_entries set entry_type = p_entry_type, amount_vnd = p_amount_vnd,
    note = nullif(btrim(p_note), ''), occurred_at = p_occurred_at, updated_at = now()
  where id = p_id and user_id = v_user and updated_at = p_expected_updated_at and entry_type <> 'opening_balance';
  if not found then raise exception 'STALE_ENTRY' using errcode = 'P0001'; end if;
  perform private.refresh_portfolio_wallet(v_user);
  return private.portfolio_ledger_snapshot(v_user);
end; $$;

create or replace function public.delete_cash_entry(p_id uuid, p_expected_updated_at timestamptz)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_user uuid := auth.uid();
begin
  if v_user is null then raise exception 'AUTH_REQUIRED' using errcode = 'P0001'; end if;
  perform private.lock_portfolio_wallet(v_user);
  delete from public.portfolio_cash_entries
  where id = p_id and user_id = v_user and updated_at = p_expected_updated_at and entry_type <> 'opening_balance';
  if not found then raise exception 'STALE_ENTRY' using errcode = 'P0001'; end if;
  perform private.refresh_portfolio_wallet(v_user);
  return private.portfolio_ledger_snapshot(v_user);
end; $$;

create or replace function public.record_portfolio_trade(p_transaction_type text, p_symbol text, p_quantity numeric, p_unit_price_vnd bigint, p_fee_vnd bigint, p_tax_vnd bigint, p_occurred_at timestamptz)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_user uuid := auth.uid();
begin
  if v_user is null then raise exception 'AUTH_REQUIRED' using errcode = 'P0001'; end if;
  perform private.lock_portfolio_wallet(v_user);
  if p_transaction_type not in ('buy', 'sell') or p_symbol !~ '^[A-Z0-9]{1,10}[.]VN$'
    or p_quantity <= 0 or scale(p_quantity) > 4 or p_unit_price_vnd <= 0 or p_fee_vnd < 0 or p_tax_vnd < 0 or p_occurred_at is null
  then raise exception 'INVALID_TRADE' using errcode = 'P0001'; end if;
  insert into public.portfolio_transactions (user_id, transaction_type, symbol, quantity, unit_price_vnd, fee_vnd, tax_vnd, occurred_at)
  values (v_user, p_transaction_type, p_symbol, p_quantity, p_unit_price_vnd, p_fee_vnd, p_tax_vnd, p_occurred_at);
  perform private.refresh_portfolio_wallet(v_user);
  return private.portfolio_ledger_snapshot(v_user);
end; $$;

create or replace function public.update_portfolio_trade(p_id uuid, p_expected_updated_at timestamptz, p_transaction_type text, p_symbol text, p_quantity numeric, p_unit_price_vnd bigint, p_fee_vnd bigint, p_tax_vnd bigint, p_occurred_at timestamptz)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_user uuid := auth.uid();
begin
  if v_user is null then raise exception 'AUTH_REQUIRED' using errcode = 'P0001'; end if;
  perform private.lock_portfolio_wallet(v_user);
  if p_transaction_type not in ('buy', 'sell') or p_symbol !~ '^[A-Z0-9]{1,10}[.]VN$'
    or p_quantity <= 0 or scale(p_quantity) > 4 or p_unit_price_vnd <= 0 or p_fee_vnd < 0 or p_tax_vnd < 0 or p_occurred_at is null
  then raise exception 'INVALID_TRADE' using errcode = 'P0001'; end if;
  update public.portfolio_transactions set transaction_type = p_transaction_type, symbol = p_symbol,
    quantity = p_quantity, unit_price_vnd = p_unit_price_vnd, fee_vnd = p_fee_vnd, tax_vnd = p_tax_vnd,
    occurred_at = p_occurred_at, updated_at = now()
  where id = p_id and user_id = v_user and updated_at = p_expected_updated_at;
  if not found then raise exception 'STALE_ENTRY' using errcode = 'P0001'; end if;
  perform private.refresh_portfolio_wallet(v_user);
  return private.portfolio_ledger_snapshot(v_user);
end; $$;

create or replace function public.delete_portfolio_trade(p_id uuid, p_expected_updated_at timestamptz)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_user uuid := auth.uid();
begin
  if v_user is null then raise exception 'AUTH_REQUIRED' using errcode = 'P0001'; end if;
  perform private.lock_portfolio_wallet(v_user);
  delete from public.portfolio_transactions where id = p_id and user_id = v_user and updated_at = p_expected_updated_at;
  if not found then raise exception 'STALE_ENTRY' using errcode = 'P0001'; end if;
  perform private.refresh_portfolio_wallet(v_user);
  return private.portfolio_ledger_snapshot(v_user);
end; $$;

revoke all on function public.record_cash_entry(text, bigint, timestamptz, text) from public, anon;
revoke all on function public.update_cash_entry(uuid, timestamptz, text, bigint, timestamptz, text) from public, anon;
revoke all on function public.delete_cash_entry(uuid, timestamptz) from public, anon;
revoke all on function public.record_portfolio_trade(text, text, numeric, bigint, bigint, bigint, timestamptz) from public, anon;
revoke all on function public.update_portfolio_trade(uuid, timestamptz, text, text, numeric, bigint, bigint, bigint, timestamptz) from public, anon;
revoke all on function public.delete_portfolio_trade(uuid, timestamptz) from public, anon;

grant execute on function public.record_cash_entry(text, bigint, timestamptz, text) to authenticated;
grant execute on function public.update_cash_entry(uuid, timestamptz, text, bigint, timestamptz, text) to authenticated;
grant execute on function public.delete_cash_entry(uuid, timestamptz) to authenticated;
grant execute on function public.record_portfolio_trade(text, text, numeric, bigint, bigint, bigint, timestamptz) to authenticated;
grant execute on function public.update_portfolio_trade(uuid, timestamptz, text, text, numeric, bigint, bigint, bigint, timestamptz) to authenticated;
grant execute on function public.delete_portfolio_trade(uuid, timestamptz) to authenticated;
