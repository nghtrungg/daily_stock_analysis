# Vietnam Settlement Calendar, Ledger, And Schema Migrations

## Scope

The backend provides deterministic Vietnam equity settlement calculations and
uses them in the existing portfolio ledger. API contract expansion, report
instructions, alerts, and outcome measurement remain separate follow-up work.

All input timestamps are normalized to `Asia/Ho_Chi_Minh`. Naive timestamps are
interpreted as Vietnam-local time. The current policy is identified as
`vn-equity-t2-2022-08-29`: shares are estimated to become sellable at 13:00 on
the second eligible settlement session after the trade date. The policy time is
based on VSD's T+2 allocation schedule; broker-specific delays are not modeled.

## Calendar data

Committed calendar files live under `config/market_calendars/vn/<year>.json` and
are included in the Docker image. Each file has an explicit version plus
independent `trading_closures` and `settlement_closures` arrays. This separation
allows a date to be:

- a normal trading and settlement day;
- a non-trading closure;
- a settlement-only closure while trading remains open;
- a settlement day while trading is closed;
- a weekend; or
- a weekday with unknown official calendar coverage.

The bundled 2026 closures use the published
[VSDC 2026 settlement calendar](https://www.vsd.vn/vi/lich-giao-dich?date=20%2F03%2F2026&tab=LICH_NGHI_GIAODICH),
its [New Year adjustment](https://vsd.vn/vi/ad/190545), and the
[HOSE New Year trading notice](https://staticfile.hsx.vn/Uploads/UploadDocuments/2426350/20251225_Thong%20bao%20%20ve%20%20viec%20cap%20nhat%20lich%20nghi%20giao%20dich%20Tet%20Duong%20lich%202026%20toan%20thi%20truong.pdf).
Calendar data must be reviewed and versioned when an exchange or VSDC notice
changes.

## Calculation contract

`calculate_vn_settlement()` returns:

```text
trade_date
settlement_date
estimated_sellable_at
calendar_version
policy_version
calculation_status
warnings
```

`confirmed` means every evaluated year used valid bundled data. `degraded`
means a required year file was missing and the date estimate used weekday-only
fallback behavior. `unknown` means a calendar file was malformed or the input
trade date was not a confirmed trading day. Callers may display degraded or
unknown estimates, but must not describe them as official confirmed dates.
Negative settlement-session counts are rejected.

Existing boolean scheduling helpers remain compatible. For Vietnam dates with
valid bundled coverage they now honor public-holiday closures. When a year is
missing, weekday-only behavior remains available, while structured settlement
calculations expose the degraded status and warnings.

## Portfolio ledger behavior

New Vietnam buy trades receive a one-to-one settlement annotation containing
the estimated sellable time and the exact calendar and policy versions used.
An explicitly supplied execution timestamp is normalized to Vietnam time and
stored as UTC without timezone metadata. When a new caller supplies only
`trade_date`, replay uses 14:45 ICT as an internal effective time and records
`execution_time_inferred_from_trade_date` in the annotation warnings; the trade
timestamp itself remains null so inferred timing is not presented as observed.

FIFO and average-cost replay both retain acquisition-lot settlement timing.
Average-cost accounting still calculates cost basis from the aggregate average,
while its acquisition lots independently track which quantity is sellable.
Split adjustments scale both the accounting quantity and each settlement lot.

Vietnam sell validation runs under the same `BEGIN IMMEDIATE` write transaction
as trade insertion. It calculates held, sellable, and unsettled quantities at
the effective sale time, rejects full oversells with the existing exception,
and rejects sales above sellable quantity with
`PortfolioUnsettledSaleError`. Trade UID and deduplication checks remain in the
same transaction, so concurrent requests cannot consume one lot twice.

Derived position state is one of `unsettled`, `partially_sellable`, `sellable`,
or `unknown`. Calendar status is aggregated conservatively: `unknown` takes
precedence over `degraded`, which takes precedence over `confirmed`. Genuine
legacy buys without a settlement sidecar remain sellable for compatibility but
are reported as `unknown`; the service does not invent a historical settlement
timestamp for them. Other markets retain their previous sale validation.

## Ordered database migrations

Startup still calls SQLAlchemy `metadata.create_all()` to create absent tables,
then runs the ordered migration list before services become available. Each
migration:

1. acquires a SQLite writer transaction;
2. checks `schema_migrations` for its version;
3. applies its idempotent upgrade;
4. records the version and description in the same transaction.

Concurrent and repeated initializers therefore do not reapply a completed
migration. A failed required migration stops startup with the failed version
and description; the application never deletes or resets the configured
database automatically.

## Rollback

Reverting this code does not delete rows from `schema_migrations`, remove
calendar files, or drop the additive settlement table and columns. Older code
ignores the migration record and additive fields, while existing trade and
portfolio rows remain intact. To disable enforcement without a code rollback,
route writes through a version that predates the settlement-aware service;
do not delete settlement annotations because they preserve calculation
provenance for later re-enablement.
