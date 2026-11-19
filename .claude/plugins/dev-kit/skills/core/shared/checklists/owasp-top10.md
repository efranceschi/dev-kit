# OWASP Top 10 (2021) — code audit checklist

For each item, grep/inspect the code in scope and record concrete findings (`category: security`). Default severities: exploitable on main path → critical; exploitable with preconditions → high; hardening gaps → medium.

- **A01 Broken access control** — every endpoint/page checks authn *and* authz server-side; object-level checks (IDOR: user can only reach own records); no privilege decisions from client input; CORS not `*` with credentials; directory listing off.
- **A02 Cryptographic failures** — passwords hashed with bcrypt/argon2/scrypt; TLS everywhere; no custom crypto; secrets not in code or logs; sensitive fields encrypted at rest when the brief demands.
- **A03 Injection** — parameterised queries/ORM only; no string-built SQL/NoSQL/shell/LDAP; output encoding in templates; no `dangerouslySetInnerHTML`/`innerHTML` with user data; input validated with schemas.
- **A04 Insecure design** — rate limiting on auth and expensive endpoints; business-logic abuse cases (negative quantities, replay, enumeration) considered; threat model notes in architecture.
- **A05 Security misconfiguration** — debug off in prod; default credentials absent; security headers (CSP, HSTS, X-Content-Type-Options, frame-ancestors); verbose errors not exposed; permissive file permissions.
- **A06 Vulnerable and outdated components** — run `npm audit` / `pip-audit` / `cargo audit` / `govulncheck` when available; lockfile present; pinned versions; no abandoned libs for critical paths.
- **A07 Identification and authentication failures** — session fixation/rotation, secure+httpOnly+SameSite cookies, token expiry and refresh, brute-force protection, password policy, MFA if brief requires, logout invalidates.
- **A08 Software and data integrity failures** — CI pulls pinned actions/images; no `eval` of remote code; signed webhooks verified; deserialisation of untrusted data avoided.
- **A09 Security logging and monitoring failures** — auth events and authz denials logged without secrets/PII; errors tracked; logs not injectable.
- **A10 Server-side request forgery** — user-supplied URLs validated against allowlist; no fetching internal metadata endpoints; DNS rebinding considered.

Also check: file upload validation (type, size, storage outside web root, no execution), mass assignment (whitelist fields), open redirects, GraphQL depth/complexity limits, multi-tenancy isolation in every query.
