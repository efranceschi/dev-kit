#!/usr/bin/env python3
"""dev_detect_stack.py - detect the technology stack of a project from its manifests.

Standard library only. Usage: python3 -I dev_detect_stack.py [ROOT] [--pretty] [--tools]
Prints JSON: {"lang", "framework", "pkg", "test", "lint", "db", "detected_from": [...], "greenfield": bool, "notes": [...]}
Values are null when unknown. Exit 0 always (detection is best effort).

--tools prints instead what the QA agents can use without installing anything: browser automation (Playwright,
a Chromium), accessibility and performance scanners (axe, Lighthouse), installed dependencies (node_modules, a
virtualenv) and the QA harness scripts (shared/templates/qa-harness.md):
{"playwright": {"available": bool, "via": ...}, "chromium": ..., "axe": ..., "lighthouse": ..., "node_modules": bool,
 "venv": bool, "harness": {"qa:shots": bool, "qa:a11y": bool}, "visual_ready": bool,
 "audit": {"<ecosystem>": {"available": [...], "suggest": "<tool to install>" | null}}}
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys
from pathlib import Path

JS_FRAMEWORKS = [
    ("next", "next.js"), ("nuxt", "nuxt"), ("@remix-run/react", "remix"), ("@sveltejs/kit", "sveltekit"),
    ("astro", "astro"), ("@angular/core", "angular"), ("vue", "vue"), ("svelte", "svelte"),
    ("react-native", "react-native"), ("expo", "expo"), ("electron", "electron"),
    ("@nestjs/core", "nestjs"), ("fastify", "fastify"), ("express", "express"), ("hono", "hono"),
    ("koa", "koa"), ("react", "react"),
]
JS_TESTS = [("vitest", "vitest"), ("jest", "jest"), ("@playwright/test", "playwright"), ("cypress", "cypress"), ("mocha", "mocha")]
JS_LINT = [("biome", "biome"), ("@biomejs/biome", "biome"), ("eslint", "eslint"), ("prettier", "prettier")]
JS_DB = [("prisma", "prisma"), ("@prisma/client", "prisma"), ("drizzle-orm", "drizzle"), ("typeorm", "typeorm"),
         ("mongoose", "mongoose"), ("sequelize", "sequelize"), ("knex", "knex"), ("pg", "postgres"), ("mysql2", "mysql"), ("better-sqlite3", "sqlite")]
PY_FRAMEWORKS = [("django", "django"), ("fastapi", "fastapi"), ("flask", "flask"), ("litestar", "litestar"), ("streamlit", "streamlit"), ("typer", "typer"), ("click", "click")]
PY_TESTS = [("pytest", "pytest")]
PY_LINT = [("ruff", "ruff"), ("black", "black"), ("flake8", "flake8"), ("mypy", "mypy"), ("pyright", "pyright")]
PY_DB = [("sqlalchemy", "sqlalchemy"), ("sqlmodel", "sqlmodel"), ("psycopg", "postgres"), ("asyncpg", "postgres"), ("pymongo", "mongodb"), ("tortoise-orm", "tortoise")]


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def first_match(names: list[str], table: list[tuple[str, str]]) -> str | None:
    s = set(names)
    for key, label in table:
        if key in s:
            return label
    return None


def detect(root: Path) -> dict:
    out: dict = {"lang": None, "framework": None, "pkg": None, "test": None, "lint": None, "db": None,
                 "detected_from": [], "greenfield": False, "notes": []}
    found = out["detected_from"]

    pkg_json = root / "package.json"
    if pkg_json.exists():
        found.append("package.json")
        try:
            data = json.loads(read(pkg_json))
        except json.JSONDecodeError:
            data = {}
            out["notes"].append("package.json is not valid JSON")
        deps = list({**data.get("dependencies", {}), **data.get("devDependencies", {})}.keys())
        out["lang"] = "typescript" if "typescript" in deps or (root / "tsconfig.json").exists() else "javascript"
        out["framework"] = first_match(deps, JS_FRAMEWORKS)
        out["test"] = first_match(deps, JS_TESTS)
        out["lint"] = first_match(deps, JS_LINT)
        out["db"] = first_match(deps, JS_DB)
        for lock, mgr in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"), ("bun.lock", "bun"), ("package-lock.json", "npm")):
            if (root / lock).exists():
                out["pkg"] = mgr
                found.append(lock)
                break
        if out["pkg"] is None:
            pm = str(data.get("packageManager", ""))
            out["pkg"] = pm.split("@")[0] if pm else "npm"
        if (root / "deno.json").exists() or (root / "deno.jsonc").exists():
            out["pkg"] = "deno"
        scripts = data.get("scripts", {})
        if scripts:
            out["scripts"] = {k: scripts[k] for k in ("dev", "build", "test", "lint", "start") if k in scripts}

    pyproject = root / "pyproject.toml"
    reqs = root / "requirements.txt"
    if pyproject.exists() or reqs.exists():
        text = read(pyproject) + "\n" + read(reqs)
        names = [n.lower() for n in re.findall(r'^\s*"?([A-Za-z0-9_.\-]+)\s*(?:[>=<~!\[]|"|$)', text, flags=re.M)]
        names += [n.lower() for n in re.findall(r"\b([A-Za-z0-9_\-]+)\s*(?:>=|==|~=|\[)", text)]
        if pyproject.exists():
            found.append("pyproject.toml")
        if reqs.exists():
            found.append("requirements.txt")
        out["lang"] = out["lang"] or "python"
        if out["lang"] != "python":
            out["notes"].append("polyglot: python manifests present alongside " + out["lang"])
        out["framework"] = out["framework"] or first_match(names, PY_FRAMEWORKS)
        out["test"] = out["test"] or first_match(names, PY_TESTS) or ("pytest" if "[tool.pytest" in text else None)
        out["lint"] = out["lint"] or first_match(names, PY_LINT) or ("ruff" if "[tool.ruff" in text else None)
        out["db"] = out["db"] or first_match(names, PY_DB)
        if (root / "uv.lock").exists():
            out["pkg"] = out["pkg"] or "uv"; found.append("uv.lock")
        elif (root / "poetry.lock").exists() or "[tool.poetry]" in text:
            out["pkg"] = out["pkg"] or "poetry"
        elif (root / "Pipfile").exists():
            out["pkg"] = out["pkg"] or "pipenv"
        else:
            out["pkg"] = out["pkg"] or "pip"

    simple = [
        ("go.mod", "go", "go", "go test"), ("Cargo.toml", "rust", "cargo", "cargo test"),
        ("pom.xml", "java", "maven", "junit"), ("build.gradle", "java/kotlin", "gradle", "junit"),
        ("build.gradle.kts", "kotlin", "gradle", "junit"), ("Gemfile", "ruby", "bundler", None),
        ("composer.json", "php", "composer", "phpunit"), ("pubspec.yaml", "dart/flutter", "pub", "flutter test"),
        ("mix.exs", "elixir", "mix", "exunit"), ("Package.swift", "swift", "spm", "xctest"),
    ]
    for fname, lang, pkg, test in simple:
        if (root / fname).exists():
            found.append(fname)
            if out["lang"] is None:
                out["lang"], out["pkg"], out["test"] = lang, pkg, test
            else:
                out["notes"].append(f"polyglot: {fname} present alongside {out['lang']}")
    csproj = list(root.glob("*.csproj")) + list(root.glob("*.sln"))
    if csproj:
        found.append(csproj[0].name)
        if out["lang"] is None:
            out["lang"], out["pkg"], out["test"] = "csharp", "dotnet", "xunit/nunit"
    if (root / "go.mod").exists():
        gomod = read(root / "go.mod")
        for key, label in (("gin-gonic/gin", "gin"), ("labstack/echo", "echo"), ("gofiber/fiber", "fiber"), ("go-chi/chi", "chi")):
            if key in gomod:
                out["framework"] = out["framework"] or label
    if (root / "Cargo.toml").exists():
        cargo = read(root / "Cargo.toml")
        for key in ("axum", "actix-web", "rocket", "tauri", "bevy"):
            if re.search(rf"^\s*{re.escape(key)}\s*=", cargo, flags=re.M):
                out["framework"] = out["framework"] or key

    for fname in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yaml", "fly.toml", "vercel.json", "netlify.toml", "render.yaml"):
        if (root / fname).exists():
            out.setdefault("infra", []).append(fname)
    for d in (".github/workflows", ".gitlab-ci.yml", ".circleci"):
        if (root / d).exists():
            out.setdefault("ci", []).append(d)
    if (root / ".git").exists():
        out["git"] = True

    if not found:
        found += other_markers(root, out)
    if not found:
        out["greenfield"] = True
        files = [p.name for p in root.iterdir() if not p.name.startswith(".")] if root.exists() else []
        out["notes"].append("no manifests found" + (f"; files present: {', '.join(files[:10])}" if files else "; directory is empty"))
    return out


SOURCE_EXT = {".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs", ".c", ".cc",
              ".cpp", ".h", ".hpp", ".swift", ".dart", ".ex", ".exs", ".scala", ".lua", ".sh", ".html", ".vue", ".svelte", ".sql"}
OTHER_MANIFESTS = [("setup.py", "python"), ("setup.cfg", "python"), ("Pipfile", "python"), ("requirements.txt", "python"),
                   ("Makefile", None), ("CMakeLists.txt", "c/c++"), ("meson.build", "c/c++"), ("deno.json", "typescript")]
SKIP_DIRS = {"node_modules", "vendor", "dist", "build", "target", "venv", ".venv", "__pycache__"}


def other_markers(root: Path, out: dict) -> list[str]:
    """No main manifest at the root: look for secondary manifests, manifests in subfolders (monorepos, up to
    two levels) and source files, so an existing codebase is never mistaken for a new project."""
    hits: list[str] = []
    for fname, lang in OTHER_MANIFESTS:
        if (root / fname).exists():
            hits.append(fname)
            out["lang"] = out["lang"] or lang
    if not root.exists():
        return hits
    main_names = ("package.json", "pyproject.toml", "go.mod", "Cargo.toml", "pom.xml", "build.gradle", "Gemfile", "composer.json")
    sources = 0
    for depth_glob in ("*", "*/*", "*/*/*"):
        for p in root.glob(depth_glob):
            if any(part.startswith(".") or part in SKIP_DIRS for part in p.relative_to(root).parts):
                continue
            if p.is_file():
                if p.name in main_names and p.parent != root:
                    hits.append(str(p.relative_to(root)))
                elif p.suffix.lower() in SOURCE_EXT:
                    sources += 1
        if len(hits) > 20:
            break
    if any("/" in h for h in hits):
        out["notes"].append("manifests in subfolders (monorepo?): " + ", ".join(h for h in hits if "/" in h)[:200])
    if sources:
        hits.append(f"{sources} source file(s)")
        out["notes"].append(f"no main manifest, but {sources} source file(s) found: existing code")
    return hits


def _first(*cands: tuple[bool, str]) -> dict:
    for ok, via in cands:
        if ok:
            return {"available": True, "via": via}
    return {"available": False, "via": None}


def _py_has(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def detect_tools(root: Path) -> dict:
    nm = root / "node_modules"
    caches = [Path(x) for x in [os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or ""] if x and x != "0"]
    caches += [Path.home() / ".cache" / "ms-playwright", Path.home() / "Library" / "Caches" / "ms-playwright"]
    scripts: dict = {}
    try:
        scripts = (json.loads(read(root / "package.json") or "{}").get("scripts") or {})
    except json.JSONDecodeError:
        pass
    harness = {k: k in scripts for k in ("qa:shots", "qa:a11y")}
    if not any(harness.values()):
        mk = read(root / "Makefile")
        harness = {k: bool(re.search(rf"^{re.escape(k.replace(':', '-'))}:", mk, re.M)) for k in harness}
    out = {
        "playwright": _first(((nm / "@playwright" / "test").exists(), "node_modules/@playwright/test"),
                             ((nm / "playwright").exists(), "node_modules/playwright"),
                             (_py_has("playwright"), "python playwright"),
                             (bool(shutil.which("playwright")), "playwright on PATH")),
        "chromium": _first((any(c.is_dir() and any(c.glob("chromium*")) for c in caches), "playwright browser cache"),
                           *[(bool(shutil.which(b)), b) for b in ("chromium", "chromium-browser", "google-chrome", "chrome")]),
        "axe": _first(((nm / "@axe-core" / "playwright").exists(), "node_modules/@axe-core/playwright"),
                      ((nm / "axe-core").exists(), "node_modules/axe-core"),
                      (_py_has("axe_playwright_python"), "python axe-playwright"),
                      (bool(shutil.which("axe")), "axe on PATH")),
        "lighthouse": _first(((nm / "lighthouse").exists(), "node_modules/lighthouse"),
                             (bool(shutil.which("lighthouse")), "lighthouse on PATH")),
        "node_modules": nm.exists(),
        "venv": any((root / d / "bin").exists() or (root / d / "Scripts").exists() for d in (".venv", "venv")),
        "harness": harness,
    }
    out["visual_ready"] = out["playwright"]["available"] and out["chromium"]["available"]
    # dependency auditors per ecosystem present in the project: what deps-auditor and security-auditor can run,
    # and what to suggest installing when missing (a dev_tooling decision)
    eco = {
        "node": ((root / "package.json").exists(), [("npm audit", bool(shutil.which("npm"))), ("pnpm audit", bool(shutil.which("pnpm"))),
                                                     ("yarn npm audit", bool(shutil.which("yarn")))]),
        "python": (any((root / f).exists() for f in ("pyproject.toml", "requirements.txt", "Pipfile", "setup.py")),
                   [("pip-audit", bool(shutil.which("pip-audit")) or _py_has("pip_audit")), ("safety", bool(shutil.which("safety")))]),
        "rust": ((root / "Cargo.toml").exists(), [("cargo audit", bool(shutil.which("cargo-audit")))]),
        "go": ((root / "go.mod").exists(), [("govulncheck", bool(shutil.which("govulncheck")))]),
        "ruby": ((root / "Gemfile").exists(), [("bundle audit", bool(shutil.which("bundle-audit")))]),
        "php": ((root / "composer.json").exists(), [("composer audit", bool(shutil.which("composer")))]),
    }
    out["audit"] = {k: {"available": [n for n, ok in tools if ok], "suggest": None if any(ok for _, ok in tools) else tools[0][0]}
                    for k, (present, tools) in eco.items() if present}
    return out


def main(argv: list[str]) -> None:
    pretty = "--pretty" in argv
    args = [a for a in argv if not a.startswith("--")]
    root = Path(args[0]).resolve() if args else Path.cwd()
    result = detect_tools(root) if "--tools" in argv else detect(root)
    print(json.dumps(result, indent=2 if pretty else None, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
