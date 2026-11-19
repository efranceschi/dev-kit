# Dependencies and licences audit checklist (deps-auditor)

Run only tools already installed; never install anything. Findings use `category: dependencies`.

## Inventory
- List direct runtime and dev dependencies from the manifest(s) (`package.json`, `pyproject.toml`/`requirements*.txt`, `go.mod`, `Cargo.toml`, `Gemfile`, `composer.json`…) and compare with `.dev/architecture.md` §1 and `.dev/decisions.md`: any dependency without a stack-table line or an ADR → `medium` (`high` if it has network, crypto, auth or native-code responsibilities).
- Lockfile present, committed, and consistent with the manifest; reproducible install command in the docs.
- Unused dependencies (declared but never imported: `depcheck`, `knip`, `deptry`, or grep) → `low`; dependencies imported but undeclared → `high`.
- Duplicates (two libraries for the same job: moment+dayjs, axios+fetch wrapper, two test runners) → `medium`.

## Vulnerabilities
- Run the matching audit: `npm audit --omit=dev --json` / `pnpm audit --prod --json` / `yarn npm audit`, `pip-audit`, `cargo audit`, `govulncheck ./...`, `bundle audit`, `composer audit`.
- Critical or high advisory on a runtime dependency reachable from the app → `high` (`critical` if exploitable on a main path); development-only dependency → `medium`; report fixed-in versions.

## Health of each critical dependency
For auth, database, payments, crypto, framework core: last release date, maintenance status, open security advisories, major-version lag. Abandoned (> 2 years without release and archived/deprecated) → `high`; one major version behind → `low`; check official docs/registry with WebFetch when unsure and cite the source.

## Licences
- List licences of direct dependencies (`license-checker`, `pip-licenses`, `cargo license`, `go-licenses` if present; otherwise read manifests/package metadata).
- Compare with the project licence and the brief (commercial closed-source vs open source). GPL/AGPL in a proprietary distributed product, or licence missing/unknown → `high`; weak copyleft (LGPL/MPL) needing attention → `medium`.
- A `LICENSE` file exists for the project when the brief says it is open source.

## Supply-chain hygiene
- Versions pinned or ranges bounded for critical packages; CI actions/images pinned by tag or digest; no `curl | sh` installers in scripts; no postinstall scripts from unknown packages doing network calls; no dependencies pulled from git URLs or unusual registries without an ADR.
- Package names verified for typosquatting on newly added dependencies.

## Output extras
Add `"counts": {"direct": n, "vulnerable": n, "outdated_major": n}` and `"licenses": {"MIT": n, ...}` inside the JSON.
- Existing projects (`conventions.md` §16): diff the manifests against `git show <brownfield.baseline_ref>:<manifest>`; only added or upgraded dependencies need an ADR; issues in pre-existing ones are `"legacy": true` unless the scope upgraded them.
