# Data model and migrations review checklist (data-reviewer)

Review schema, migrations, queries and data-handling code against `.dev/architecture.md` §4, `.dev/brief.md` block 4 (volume, retention, LGPD/GDPR) and the PRD. Findings use `category: data`.

## Model
- **Fit**: every entity and relationship in the architecture exists; names consistent with the domain terms of the PRD; no leftover or unused tables/columns.
- **Constraints**: primary keys, foreign keys with explicit `ON DELETE` behaviour, `NOT NULL`, `UNIQUE` (emails, slugs, natural keys), `CHECK` for enums and ranges. Business invariants enforced only in application code → `medium`; uniqueness enforced only in code → `high`.
- **Types**: money as integer minor units or decimal (never float); timestamps with time zone and UTC storage; IDs type consistent; enums/values defined once.
- **Indexes**: for every filter, sort and join used by queries in scope; no redundant indexes; composite index order matches usage.
- **Multi-tenancy**: tenant key present on every tenant-owned table, included in unique constraints and every query; isolation tested. Missing scoping → `critical`.
- **Soft delete / audit**: consistent policy; audit columns (created/updated, actor) where the brief demands.

## Migrations
- **Reproducible**: a clean database can be built from migrations alone; migration order has no gaps; schema snapshot (if kept) matches.
- **Safe**: no destructive change (drop column/table, type narrowing) without an ADR (`delete_data` is an always-ask category) → `critical` if present without one; large-table operations use safe patterns (add nullable then backfill, concurrent index) when volume warrants.
- **Reversible** (down/rollback present) unless the framework forbids it; data migrations idempotent.
- Run the migrate-up (and down if available) against a scratch database when tooling allows; report results.

## Access patterns
- Parameterised queries only; no string-built SQL. N+1 and unbounded queries (coordinate with performance auditor, flag only if data-structural).
- Transactions around multi-step writes; isolation/locking considered for counters, inventory, balances; idempotency keys for retried writes.
- Pagination stable (keyset or deterministic order).

## Privacy and retention
- Personal data identified and minimised; sensitive fields encrypted or hashed as the brief requires; passwords hashed with a strong KDF.
- Retention/deletion/export implemented as the brief states; backups noted in architecture; logs and analytics free of personal data.
- Seed/fixture data contains no real personal data.

## Severity
Data loss or cross-tenant leakage → `critical`; missing uniqueness/FK/constraint on a main entity → `high`; missing index on a main query → `medium` (high when volume is large); naming/style → `low`.
