begin;

create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;

insert into auth.users (id, email) values
  ('11111111-1111-4111-8111-111111111111', 'portfolio-one@example.test'),
  ('22222222-2222-4222-8222-222222222222', 'portfolio-two@example.test'),
  ('33333333-3333-4333-8333-333333333333', 'portfolio-legacy@example.test'),
  ('44444444-4444-4444-8444-444444444444', 'portfolio-oversold@example.test');

insert into public.portfolio_cash_entries (
  id, user_id, entry_type, amount_vnd, note, occurred_at, created_at, updated_at
) values
  (
    '11111111-aaaa-4111-8111-111111111111',
    '11111111-1111-4111-8111-111111111111',
    'deposit', 1000000, 'Fixture user one',
    '2026-07-16T08:00:00+07:00', '2026-07-16T08:00:00+07:00', '2026-07-16T08:00:00+07:00'
  ),
  (
    '22222222-aaaa-4222-8222-222222222222',
    '22222222-2222-4222-8222-222222222222',
    'deposit', 2000000, 'Fixture user two',
    '2026-07-16T08:00:00+07:00', '2026-07-16T08:00:00+07:00', '2026-07-16T08:00:00+07:00'
  );

insert into public.portfolio_transactions (
  id, user_id, transaction_type, symbol, quantity, unit_price_vnd,
  fee_vnd, tax_vnd, occurred_at, created_at, updated_at
) values
  (
    '11111111-bbbb-4111-8111-111111111111',
    '11111111-1111-4111-8111-111111111111',
    'buy', 'VNM.VN', 1, 100000, 0, 0,
    '2026-07-16T08:05:00+07:00', '2026-07-16T08:05:00+07:00', '2026-07-16T08:05:00+07:00'
  ),
  (
    '22222222-bbbb-4222-8222-222222222222',
    '22222222-2222-4222-8222-222222222222',
    'buy', 'FPT.VN', 1, 50000, 0, 0,
    '2026-07-16T08:05:00+07:00', '2026-07-16T08:05:00+07:00', '2026-07-16T08:05:00+07:00'
  ),
  (
    '33333333-bbbb-4333-8333-333333333331',
    '33333333-3333-4333-8333-333333333333',
    'buy', 'VNM.VN', 2, 100000, 1000, 0,
    '2026-07-16T09:00:00+07:00', '2026-07-16T09:00:00+07:00', '2026-07-16T09:00:00+07:00'
  ),
  (
    '33333333-bbbb-4333-8333-333333333332',
    '33333333-3333-4333-8333-333333333333',
    'sell', 'VNM.VN', 1, 110000, 2000, 1000,
    '2026-07-16T10:00:00+07:00', '2026-07-16T10:00:00+07:00', '2026-07-16T10:00:00+07:00'
  );

insert into public.portfolio_wallets (user_id, available_cash_vnd) values
  ('11111111-1111-4111-8111-111111111111', 900000),
  ('22222222-2222-4222-8222-222222222222', 1950000);

create temporary table legacy_trade_fingerprint as
select md5(string_agg(
  concat_ws('|', id, user_id, transaction_type, symbol, quantity, unit_price_vnd,
    fee_vnd, tax_vnd, occurred_at, created_at, updated_at),
  E'\n' order by occurred_at, created_at, id
)) as checksum
from public.portfolio_transactions
where user_id = '33333333-3333-4333-8333-333333333333';

-- The convergence migration must be safe to execute repeatedly over preserved rows.
\ir ../migrations/20260716095943_ensure_complete_portfolio_schema.sql
\ir ../migrations/20260716095943_ensure_complete_portfolio_schema.sql

insert into public.portfolio_transactions (
  id, user_id, transaction_type, symbol, quantity, unit_price_vnd,
  fee_vnd, tax_vnd, occurred_at, created_at, updated_at
) values (
  '44444444-bbbb-4444-8444-444444444444',
  '44444444-4444-4444-8444-444444444444',
  'sell', 'VNM.VN', 1, 100000, 0, 0,
  '2026-07-16T09:00:00+07:00', '2026-07-16T09:00:00+07:00', '2026-07-16T09:00:00+07:00'
);

select plan(24);

select is(
  (select md5(string_agg(
    concat_ws('|', id, user_id, transaction_type, symbol, quantity, unit_price_vnd,
      fee_vnd, tax_vnd, occurred_at, created_at, updated_at),
    E'\n' order by occurred_at, created_at, id
  )) from public.portfolio_transactions where user_id = '33333333-3333-4333-8333-333333333333'),
  (select checksum from legacy_trade_fingerprint),
  'valid legacy trade business fields remain unchanged'
);

select is(
  (select count(*) from public.portfolio_cash_entries
   where user_id = '33333333-3333-4333-8333-333333333333' and entry_type = 'opening_balance'),
  1::bigint,
  're-running convergence creates one opening balance'
);
select is(
  (select amount_vnd from public.portfolio_cash_entries
   where user_id = '33333333-3333-4333-8333-333333333333' and entry_type = 'opening_balance'),
  201000::bigint,
  'legacy history receives the minimum valid opening balance'
);
select is(
  (select available_cash_vnd from public.portfolio_wallets
   where user_id = '33333333-3333-4333-8333-333333333333'),
  107000::bigint,
  'legacy wallet equals the replayed ending cash'
);
select is(
  (select count(*) from public.portfolio_wallets
   where user_id = '33333333-3333-4333-8333-333333333333'),
  1::bigint,
  're-running convergence creates one wallet'
);
select is(
  (select count(*) from pg_indexes where schemaname = 'public' and indexname in (
    'portfolio_transactions_owner_occurred_at_idx',
    'portfolio_transactions_owner_replay_idx',
    'watchlist_symbols_owner_created_at_idx',
    'analysis_runs_owner_requested_at_idx',
    'analysis_runs_one_active_run_per_symbol_idx',
    'analysis_runs_owner_symbol_quote_idx',
    'portfolio_cash_entries_owner_occurred_at_idx'
  )),
  7::bigint,
  'convergence leaves one copy of every portfolio index'
);
select is(
  (select count(*) from pg_policies where schemaname = 'public' and tablename in (
    'portfolio_transactions', 'watchlist_symbols', 'analysis_runs', 'portfolio_wallets', 'portfolio_cash_entries'
  )),
  7::bigint,
  'convergence leaves one copy of every portfolio policy'
);
select ok(
  (select bool_and(c.relrowsecurity)
   from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and c.relname in (
     'portfolio_transactions', 'watchlist_symbols', 'analysis_runs', 'portfolio_wallets', 'portfolio_cash_entries'
   )),
  'RLS is enabled on every exposed portfolio table'
);
select ok(
  (select bool_and(
    not has_table_privilege('authenticated', format('public.%I', table_name), privilege)
  ) from unnest(array['portfolio_transactions', 'portfolio_wallets', 'portfolio_cash_entries']) as tables(table_name)
    cross join unnest(array['INSERT', 'UPDATE', 'DELETE']) as privileges(privilege)),
  'authenticated has no direct financial-table mutation privilege'
);
select ok(
  (select bool_and(has_function_privilege('authenticated', p.oid, 'EXECUTE'))
   from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.proname in (
     'record_cash_entry', 'update_cash_entry', 'delete_cash_entry',
     'record_portfolio_trade', 'update_portfolio_trade', 'delete_portfolio_trade'
   )),
  'authenticated can execute only the financial mutation RPC boundary'
);
select ok(
  (select bool_and(not has_function_privilege('anon', p.oid, 'EXECUTE'))
   from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.proname in (
     'record_cash_entry', 'update_cash_entry', 'delete_cash_entry',
     'record_portfolio_trade', 'update_portfolio_trade', 'delete_portfolio_trade'
   )),
  'anonymous users cannot execute financial mutation RPCs'
);
select is(
  private.minimum_opening_balance('33333333-3333-4333-8333-333333333333'),
  201000::bigint,
  'minimum opening balance is deterministic for a valid buy/sell history'
);
select throws_ok(
  $$select private.minimum_opening_balance('44444444-4444-4444-8444-444444444444')$$,
  'P0001',
  'MIGRATION_INSUFFICIENT_SHARES user=44444444-4444-4444-8444-444444444444 trade=44444444-bbbb-4444-8444-444444444444',
  'an impossible historical share balance fails with a clear diagnostic'
);

set local role authenticated;
set local "request.jwt.claim.sub" = '11111111-1111-4111-8111-111111111111';

select is((select count(*) from public.portfolio_transactions), 1::bigint, 'user one sees only their trade');
select is((select count(*) from public.portfolio_cash_entries), 1::bigint, 'user one sees only their cash entry');
select is((select available_cash_vnd from public.portfolio_wallets), 900000::bigint, 'user one sees only their wallet');

select lives_ok(
  $$select public.record_cash_entry('deposit', 500000, '2026-07-16T11:00:00+07:00', 'Nạp thêm')$$,
  'owner can record a deposit through the RPC'
);
select is((select available_cash_vnd from public.portfolio_wallets), 1400000::bigint, 'deposit refreshes wallet cash');
select lives_ok(
  $$select public.record_portfolio_trade('buy', 'VNM.VN', 2, 100000, 1000, 0, '2026-07-16T11:05:00+07:00')$$,
  'owner can record a funded buy through the RPC'
);
select is((select available_cash_vnd from public.portfolio_wallets), 1199000::bigint, 'buy refreshes wallet cash');
select throws_ok(
  $$select public.record_portfolio_trade('sell', 'VNM.VN', 10, 100000, 0, 0, '2026-07-16T11:10:00+07:00')$$,
  'P0001', 'INSUFFICIENT_SHARES',
  'overselling is rejected atomically'
);
select is((select count(*) from public.portfolio_transactions), 2::bigint, 'a rejected sell leaves the ledger unchanged');

set local "request.jwt.claim.sub" = '22222222-2222-4222-8222-222222222222';
select is((select count(*) from public.portfolio_transactions), 1::bigint, 'user two sees only their trade');
select is((select available_cash_vnd from public.portfolio_wallets), 1950000::bigint, 'user two sees only their wallet');

select * from finish();
rollback;
