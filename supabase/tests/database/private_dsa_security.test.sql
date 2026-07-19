begin;

create extension if not exists pgtap with schema extensions;
select plan(28);

select has_schema('dsa', 'private compute schema exists');

select tables_are(
  'dsa',
  array[
    'agent_provider_turns',
    'alert_cooldowns',
    'alert_notifications',
    'alert_rules',
    'alert_triggers',
    'analysis_history',
    'backtest_results',
    'backtest_summaries',
    'conversation_messages',
    'conversation_summaries',
    'decision_signal_feedback',
    'decision_signal_outcomes',
    'decision_signal_trade_links',
    'decision_signals',
    'fundamental_snapshot',
    'intelligence_items',
    'intelligence_sources',
    'llm_usage',
    'news_intel',
    'portfolio_accounts',
    'portfolio_cash_ledger',
    'portfolio_corporate_actions',
    'portfolio_daily_snapshots',
    'portfolio_fx_rates',
    'portfolio_position_lots',
    'portfolio_positions',
    'portfolio_trade_settlements',
    'portfolio_trades',
    'settlement_alert_states',
    'settlement_outcomes',
    'stock_daily'
  ],
  'dsa contains exactly the PR1 private compute tables'
);

select has_role('dsa_worker', 'worker role exists');
select is(
  (select rolcanlogin from pg_roles where rolname = 'dsa_worker'),
  true,
  'worker can log in'
);
select is(
  (select rolinherit from pg_roles where rolname = 'dsa_worker'),
  false,
  'worker does not inherit privileges'
);
select is(
  (select rolbypassrls from pg_roles where rolname = 'dsa_worker'),
  false,
  'worker cannot bypass RLS'
);
select is(
  (select rolsuper from pg_roles where rolname = 'dsa_worker'),
  false,
  'worker is not a superuser'
);

select is(
  has_schema_privilege('anon', 'dsa', 'usage'),
  false,
  'anonymous requests cannot use dsa'
);
select is(
  has_schema_privilege('authenticated', 'dsa', 'usage'),
  false,
  'authenticated requests cannot use dsa'
);
select is(
  has_table_privilege('anon', 'dsa.stock_daily', 'select'),
  false,
  'anonymous requests cannot select private prices'
);
select is(
  has_table_privilege('authenticated', 'dsa.stock_daily', 'select'),
  false,
  'authenticated requests cannot select private prices'
);
select is(
  has_schema_privilege('service_role', 'dsa', 'usage'),
  false,
  'service-role Data API requests cannot use dsa'
);
select is(
  has_table_privilege('service_role', 'dsa.stock_daily', 'select'),
  false,
  'service-role Data API requests cannot select private prices'
);

select is(
  (
    select count(*)::integer
    from pg_class
    join pg_namespace on pg_namespace.oid = pg_class.relnamespace
    where pg_namespace.nspname = 'dsa'
      and pg_class.relkind = 'r'
      and pg_class.relrowsecurity
  ),
  31,
  'RLS is enabled on every private table'
);
select is(
  (
    select count(*)::integer
    from pg_policies
    where schemaname = 'dsa'
      and policyname like '%_worker_all'
      and roles = array['dsa_worker']::name[]
      and cmd = 'ALL'
  ),
  31,
  'every private table has one worker-only policy'
);

set local role authenticated;
set local request.jwt.claim.sub = '123e4567-e89b-12d3-a456-426614174000';
select throws_ok(
  'select * from dsa.stock_daily',
  '42501',
  'permission denied for schema dsa',
  'first authenticated user cannot access private compute data'
);
reset role;

set local role authenticated;
set local request.jwt.claim.sub = '987fcdeb-51a2-43d7-9012-345678901234';
select throws_ok(
  'select * from dsa.stock_daily',
  '42501',
  'permission denied for schema dsa',
  'second authenticated user cannot access private compute data'
);
reset role;

set local role anon;
select throws_ok(
  'select * from dsa.stock_daily',
  '42501',
  'permission denied for schema dsa',
  'anonymous requests cannot access private compute data'
);
reset role;

set local role dsa_worker;
select lives_ok(
  $$insert into dsa.stock_daily (code, date) values ('VNM.VN', date '2026-07-20')$$,
  'worker can insert through its RLS policy'
);
select results_eq(
  $$select code from dsa.stock_daily where date = date '2026-07-20'$$,
  array['VNM.VN'::varchar],
  'worker can read through its RLS policy'
);
select throws_ok(
  $$insert into dsa.stock_daily (code, date) values ('vnm.vn', date '2026-07-20')$$,
  '23514',
  'new row for relation "stock_daily" violates check constraint "ck_stock_daily_code_vn"',
  'symbols must use canonical uppercase .VN form'
);
select throws_ok(
  $$insert into dsa.portfolio_accounts (name, base_currency) values ('invalid', 'USD')$$,
  '23514',
  'new row for relation "portfolio_accounts" violates check constraint "ck_portfolio_accounts_base_currency_vnd"',
  'portfolio currency must be VND'
);
select throws_ok(
  $$insert into dsa.alert_notifications (channel, attempt) values ('test', -1)$$,
  '23514',
  'new row for relation "alert_notifications" violates check constraint "ck_alert_notifications_attempt_nonnegative"',
  'counts cannot be negative'
);
reset role;

select hasnt_table(
  'public',
  'analysis_runs',
  'dashboard-owned analysis_runs DDL is not duplicated'
);
select hasnt_table(
  'public',
  'portfolio_cash_entries',
  'dashboard-owned cash-entry DDL is not duplicated'
);
select hasnt_table(
  'public',
  'portfolio_transactions',
  'dashboard-owned transaction DDL is not duplicated'
);
select hasnt_table(
  'public',
  'portfolio_wallets',
  'dashboard-owned wallet DDL is not duplicated'
);
select hasnt_table(
  'public',
  'watchlist_symbols',
  'dashboard-owned watchlist DDL is not duplicated'
);

select * from finish();
rollback;
