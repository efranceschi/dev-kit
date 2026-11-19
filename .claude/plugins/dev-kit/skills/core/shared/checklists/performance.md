# Performance audit checklist (performance-auditor)

Targets come from `.dev/brief.md` block 8 and the PRD NFRs. If none were given, use the defaults below and say so. Measure when tooling exists; otherwise reason from code and mark `confidence: low`. Never install tools.

## Defaults when the brief is silent
| Area | Default target |
|---|---|
| Web page, mid-range device, 4G | LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1 |
| JS shipped for a typical route | ≤ 200 KB gzip |
| API read endpoint (local DB, typical data) | p95 ≤ 300 ms |
| API write endpoint | p95 ≤ 500 ms |
| List endpoints | paginated, page size ≤ 100 |

## Backend
- **Query patterns**: N+1 (loop with query inside, lazy relations in serializers), missing indexes for filters/sorts/joins used by new queries (compare `EXPLAIN` when a DB is available), `SELECT *` on wide tables, unbounded result sets, counting by loading rows.
- **Work on the request path**: heavy computation, file processing, email sending, third-party calls without timeout that belong in a job; sequential awaits that could be parallel.
- **Caching and limits**: cache for expensive idempotent reads when volume demands it; timeouts and retries with backoff on outbound calls; connection pooling configured.
- **Memory and streams**: large files streamed, not buffered; no unbounded in-memory collections.
- **Load smoke test** (only if the project already has a tool such as k6/autocannon/locust): run a short test on the main endpoints and report p95.

## Frontend
- **Bundle**: build the app and read the report (`next build` output, `vite build`, `webpack-bundle-analyzer` if present); large dependencies for small features (moment, lodash full import, icon packs), no code splitting for heavy routes.
- **Rendering**: needless re-renders, large lists without virtualisation, blocking scripts, layout shift from images without dimensions or late fonts.
- **Assets**: images sized and in modern formats, lazy loading below the fold, font loading strategy (`font-display`), HTTP caching headers for static assets.
- **Network**: waterfall of dependent requests that could be parallel or prefetched; duplicate requests; missing pagination or debounce on search inputs.
- **Lighthouse** (only if Lighthouse/Chrome is available): run on 2–3 key pages, report the scores and the main opportunities.

## Data and scale
- Behaviour with the volume stated in brief block 4 (10× rows): pagination, indexes, batch operations, background processing.

## Severity
Target missed on a main path (measured) → `high`; N+1 or unbounded query on a main path → `high`; likely issue without measurement → `medium` with low confidence; optimisation opportunity → `low`.
