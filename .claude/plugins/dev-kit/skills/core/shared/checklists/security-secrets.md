# Secrets and configuration hygiene — checklist

Run during `security-auditor` and before every `release`.

## Detect
```bash
# high-signal patterns; adapt paths to the repo
rg -n -i --hidden -g '!node_modules' -g '!.git' \
  -e 'AKIA[0-9A-Z]{16}' \
  -e '-----BEGIN (RSA|EC|OPENSSH|PGP) PRIVATE KEY-----' \
  -e 'sk_live_[0-9a-zA-Z]{10,}' -e 'sk-[A-Za-z0-9]{20,}' \
  -e 'ghp_[A-Za-z0-9]{36}' -e 'xox[baprs]-[A-Za-z0-9-]{10,}' \
  -e '(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*["'"'"'][^"'"'"']{8,}' .
git log -p --all -S 'PRIVATE KEY' --oneline | head   # history leaks
```
Also check: `.env*` committed? (`git ls-files | rg '^\.env'`), `.gitignore` covers `.env`, `*.pem`, `*.key`, credentials JSON; Docker images copying `.env`; CI logs echoing secrets.

## Require
- `.env.example` with every variable name and a comment, no values.
- Config loaded from env with validation at boot (fail fast on missing vars).
- Secrets never logged; redaction in error trackers.
- Separate credentials per environment; least-privilege DB users and API scopes.
- Rotation note in docs for any key the project uses.

## Severity
- Live credential in repo or history → critical (also tell the user to rotate it immediately). In an existing project a credential that predates the baseline is reported with `"legacy": true` (it does not block the gate) but keeps `critical` and the rotation warning; it becomes a `standard` issue (`conventions.md` §16).
- `.env` committed with placeholder values → high.
- Missing `.env.example` / no boot validation → medium.
