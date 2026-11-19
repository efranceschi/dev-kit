#!/usr/bin/env python3
"""dev_detect_stack.py - detect the technology stack of a project from its manifests.

Standard library only. Usage: python3 -I dev_detect_stack.py [ROOT] [--pretty]
Prints JSON: {"lang", "framework", "pkg", "test", "lint", "db", "detected_from": [...], "greenfield": bool, "notes": [...]}
Values are null when unknown. Exit 0 always (detection is best effort).
"""
from __future__ import annotations

import json
import re
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
        out["greenfield"] = True
        files = [p.name for p in root.iterdir() if not p.name.startswith(".")] if root.exists() else []
        out["notes"].append("no manifests found" + (f"; files present: {', '.join(files[:10])}" if files else "; directory is empty"))
    return out


def main(argv: list[str]) -> None:
    pretty = "--pretty" in argv
    args = [a for a in argv if not a.startswith("--")]
    root = Path(args[0]).resolve() if args else Path.cwd()
    result = detect(root)
    print(json.dumps(result, indent=2 if pretty else None, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
