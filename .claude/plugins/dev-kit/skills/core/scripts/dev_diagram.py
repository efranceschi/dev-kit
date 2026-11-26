#!/usr/bin/env python3
"""dev_diagram.py - the diagrams of the system being built, drawn in the style of draw.io, with no draw.io.

Standard library only. The model (what the system is made of) is written by /dev-kit:diagram; this script only
checks it and draws it, always the same way for the same model:

Three kinds (`--kind`, default architecture), each its own model, picture and draw.io file:
  architecture  the high-level view: users, clients, services, jobs, stores and outside services, and how they talk
  data          the data model: entities with their key fields, and their relationships (.dev/architecture.md §4)
  deploy        where it runs: environments, hosts, managed services, network edges (.dev/architecture.md §7)

  render [--kind K] [--model PATH] [--svg PATH] [--drawio PATH] [--json]
          check the model and write the SVG (shown by the board and the README) and a .drawio file (the same
          diagram, for whoever wants to open or edit it in draw.io; nobody needs draw.io for anything)
  check [--kind K|all] [--json] [--info]
          is there a diagram, was it drawn from the current model, and did its part of .dev/architecture.md change
          since (exit 0 current, 3 missing, 4 out of date; --info: always 0). `all`: the architecture diagram, plus
          the data and deploy diagrams once they have a model (a missing architecture diagram is 3, any out of date 4)
  example [--kind K]
          print a model to start from

Default paths, in the project (part of its documentation, committed like the rest of docs/):
  docs/diagrams/architecture.json    the model
  docs/diagrams/architecture.svg     the picture
  docs/diagrams/architecture.drawio  the same picture as a draw.io file
  docs/diagrams/data-model.{json,svg,drawio}   the data diagram
  docs/diagrams/deployment.{json,svg,drawio}   the deploy diagram

The model:
  {"title": "...", "subtitle": "...",
   "layers": [{"id": "clients", "label": "Clients", "nodes": [
       {"id": "web", "label": "Web app", "kind": "client", "tech": "React 18"}]}, ...],
   "edges": [{"from": "web", "to": "api", "label": "HTTPS / JSON", "style": "sync|async|data", "both": false}],
   "legend": {"client": "Client", ...}}
Layers are drawn top to bottom in their order (users and clients first, data and external services last), nodes
left to right in their order. Kinds: actor, client, service, worker, database, storage, queue, cache, external,
network, component, and entity (a data-model table: `"fields": ["PK id uuid", "FK customer_id", "total numeric"]`,
at most 12; a leading PK or FK is drawn as a key mark). Edge style `relation` (no arrow) joins entities, its label
is the cardinality (`1 — N`). Edges are routed at right angles between the layers; one that skips layers runs down the right side.

The SVG starts with a comment holding the hash of the model and of the part of .dev/architecture.md it was drawn
from (the whole file for architecture, §4 data model for data, §7 environments for deploy; the whole file when the
section is not found), which is what `check` compares.

Exit codes: 0 ok · 1 usage or invalid model (the errors are printed) · 3 no diagram · 4 diagram out of date
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

MODEL = "docs/diagrams/architecture.json"
SVG = "docs/diagrams/architecture.svg"
DRAWIO = "docs/diagrams/architecture.drawio"
SOURCES = (".dev/architecture.md",)   # a change here makes the diagram out of date
# the kinds of diagram: file stem, and the section of architecture.md each is drawn from (None: the whole file)
DIAGRAMS = {
    "architecture": {"stem": "architecture", "section": None},
    "data": {"stem": "data-model", "section": re.compile(r"^##\s+(4\.|.*data model)", re.I)},
    "deploy": {"stem": "deployment", "section": re.compile(r"^##\s+(7\.|.*(environment|deploy))", re.I)},
}
MAX_FIELDS = 12
FIELD_H, ENTITY_HEAD = 18, 30
MAX_LAYERS, MAX_PER_LAYER, MAX_NODES, MAX_EDGES = 8, 8, 40, 80
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")
STAMP_RE = re.compile(r"<!-- dev-kit diagram model=([0-9a-f]{64}) sources=([0-9a-f]{64}|none) at=(\S+) -->")

# fill, stroke and the draw.io shape of each kind (the colours are draw.io's own palette)
KINDS = {
    "actor": ("#ffffff", "#36393d", "umlActor"),
    "client": ("#dae8fc", "#6c8ebf", "rounded"),
    "service": ("#d5e8d4", "#82b366", "rounded"),
    "worker": ("#ffe6cc", "#d79b00", "rounded"),
    "database": ("#fff2cc", "#d6b656", "cylinder"),
    "storage": ("#fff2cc", "#d6b656", "cylinder"),
    "queue": ("#e1d5e7", "#9673a6", "process"),
    "cache": ("#f8cecc", "#b85450", "rounded"),
    "external": ("#f5f5f5", "#666666", "external"),
    "network": ("#b1ddf0", "#10739e", "rounded"),
    "component": ("#ffffff", "#36393d", "rounded"),
    "entity": ("#dae8fc", "#6c8ebf", "entity"),
}
LEGEND = {"actor": "User", "client": "Client", "service": "Service", "worker": "Worker / job", "database": "Database",
          "storage": "Storage", "queue": "Queue / events", "cache": "Cache", "external": "External service",
          "network": "Network / edge", "component": "Component", "entity": "Entity"}
EDGE_STYLES = ("sync", "async", "data", "relation")
EDGE_LEGEND = {"sync": "Call", "async": "Message / event", "data": "Reads / writes", "relation": "Relationship"}

FONT = "Helvetica, Arial, sans-serif"
NODE_W, NODE_H, NODE_GAP = 180, 72, 48
LANE_HEAD, LANE_PAD, LANE_PAD_X = 30, 22, 28
GAP_MIN, TRACK = 56, 14
MARGIN, TITLE_H = 32, 58
CHAR_W = 7.0          # average width of a 13px Helvetica character
SMALL_W = 6.0         # the same at 11px


# --------------------------------------------------------------------------- model

def paths(root: Path, kind: str = "architecture") -> tuple[Path, Path, Path]:
    """The model, the SVG and the .drawio file of a kind of diagram, in the project."""
    stem = DIAGRAMS[kind]["stem"]
    return root / f"docs/diagrams/{stem}.json", root / f"docs/diagrams/{stem}.svg", root / f"docs/diagrams/{stem}.drawio"


def example(kind: str = "architecture") -> dict:
    if kind == "data":
        return {
            "title": "Example — data model",
            "subtitle": "Entities and relationships",
            "layers": [
                {"id": "people", "label": "Customers", "nodes": [
                    {"id": "customer", "label": "Customer", "kind": "entity", "fields": ["PK id uuid", "email text", "created_at timestamptz"]}]},
                {"id": "sales", "label": "Sales", "nodes": [
                    {"id": "order", "label": "Order", "kind": "entity", "fields": ["PK id uuid", "FK customer_id", "total numeric", "status text"]},
                    {"id": "item", "label": "Order item", "kind": "entity", "fields": ["PK id uuid", "FK order_id", "FK product_id", "qty int"]},
                    {"id": "product", "label": "Product", "kind": "entity", "fields": ["PK id uuid", "name text", "price numeric"]}]},
            ],
            "edges": [
                {"from": "customer", "to": "order", "label": "1 — N", "style": "relation"},
                {"from": "order", "to": "item", "label": "1 — N", "style": "relation"},
                {"from": "item", "to": "product", "label": "N — 1", "style": "relation"},
            ],
        }
    if kind == "deploy":
        return {
            "title": "Example — deployment",
            "subtitle": "Production",
            "layers": [
                {"id": "internet", "label": "Internet", "nodes": [{"id": "user", "label": "Customer", "kind": "actor"}]},
                {"id": "edge", "label": "Edge", "nodes": [{"id": "cdn", "label": "CDN and TLS", "kind": "network", "tech": "Cloudflare"}]},
                {"id": "vm", "label": "Production VM", "nodes": [
                    {"id": "api", "label": "API container", "kind": "service", "tech": "Docker"},
                    {"id": "jobs", "label": "Worker container", "kind": "worker", "tech": "Docker"}]},
                {"id": "managed", "label": "Managed services", "nodes": [
                    {"id": "db", "label": "Database", "kind": "database", "tech": "PostgreSQL 16"},
                    {"id": "backup", "label": "Backups", "kind": "storage", "tech": "S3"}]},
            ],
            "edges": [
                {"from": "user", "to": "cdn", "label": "HTTPS"},
                {"from": "cdn", "to": "api", "label": "HTTPS"},
                {"from": "api", "to": "db", "label": "SQL / TLS", "style": "data"},
                {"from": "jobs", "to": "db", "style": "data"},
                {"from": "db", "to": "backup", "label": "nightly", "style": "async"},
            ],
        }
    return {
        "title": "Example — architecture",
        "subtitle": "High-level view",
        "layers": [
            {"id": "users", "label": "Users", "nodes": [{"id": "user", "label": "Customer", "kind": "actor"}]},
            {"id": "clients", "label": "Clients", "nodes": [{"id": "web", "label": "Web app", "kind": "client", "tech": "React"}]},
            {"id": "backend", "label": "Backend", "nodes": [
                {"id": "api", "label": "API", "kind": "service", "tech": "FastAPI"},
                {"id": "jobs", "label": "Background jobs", "kind": "worker", "tech": "Celery"}]},
            {"id": "data", "label": "Data", "nodes": [
                {"id": "db", "label": "Main database", "kind": "database", "tech": "PostgreSQL 16"},
                {"id": "broker", "label": "Job queue", "kind": "queue", "tech": "Redis"},
                {"id": "mail", "label": "E-mail provider", "kind": "external"}]},
        ],
        "edges": [
            {"from": "user", "to": "web", "label": "uses"},
            {"from": "web", "to": "api", "label": "HTTPS / JSON"},
            {"from": "api", "to": "db", "label": "SQL", "style": "data"},
            {"from": "api", "to": "broker", "label": "enqueue", "style": "async"},
            {"from": "broker", "to": "jobs", "style": "async"},
            {"from": "jobs", "to": "mail", "label": "SMTP"},
        ],
    }


def _text(v: object, field: str, limit: int, errors: list[str], required: bool = True) -> str:
    if v is None and not required:
        return ""
    if not isinstance(v, str) or (required and not v.strip()):
        errors.append(f"{field}: a non-empty text is required")
        return ""
    v = " ".join(v.split())
    if len(v) > limit:
        errors.append(f"{field}: at most {limit} characters ({len(v)})")
    return v[:limit]


def validate(m: object) -> tuple[dict, list[str]]:
    """The model cleaned up (spaces folded, defaults filled), and what is wrong with it."""
    errors: list[str] = []
    if not isinstance(m, dict):
        return {}, ["the model must be a JSON object"]
    out: dict = {"title": _text(m.get("title"), "title", 80, errors),
                 "subtitle": _text(m.get("subtitle"), "subtitle", 120, errors, required=False), "layers": [], "edges": []}
    layers = m.get("layers")
    if not isinstance(layers, list) or not layers:
        errors.append("layers: at least one layer is required")
        layers = []
    if len(layers) > MAX_LAYERS:
        errors.append(f"layers: at most {MAX_LAYERS} ({len(layers)}); merge the smaller ones")
    seen: set[str] = set()
    for i, lay in enumerate(layers[:MAX_LAYERS]):
        where = f"layers[{i}]"
        if not isinstance(lay, dict):
            errors.append(f"{where}: must be an object")
            continue
        lid = lay.get("id")
        if not isinstance(lid, str) or not ID_RE.match(lid):
            errors.append(f"{where}.id: lower-case letters, digits, - and _ ({lid!r})")
        elif lid in seen:
            errors.append(f"{where}.id: {lid!r} is used twice")
        seen.add(str(lid))
        nodes = lay.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            errors.append(f"{where}.nodes: at least one node is required")
            nodes = []
        if len(nodes) > MAX_PER_LAYER:
            errors.append(f"{where}.nodes: at most {MAX_PER_LAYER} per layer ({len(nodes)}); split the layer or group nodes")
        clean = []
        for j, n in enumerate(nodes[:MAX_PER_LAYER]):
            w = f"{where}.nodes[{j}]"
            if not isinstance(n, dict):
                errors.append(f"{w}: must be an object")
                continue
            nid = n.get("id")
            if not isinstance(nid, str) or not ID_RE.match(nid):
                errors.append(f"{w}.id: lower-case letters, digits, - and _ ({nid!r})")
            elif nid in seen:
                errors.append(f"{w}.id: {nid!r} is used twice")
            seen.add(str(nid))
            kind = n.get("kind", "component")
            if kind not in KINDS:
                errors.append(f"{w}.kind: one of {', '.join(KINDS)} ({kind!r})")
                kind = "component"
            node = {"id": str(nid), "label": _text(n.get("label"), f"{w}.label", 48, errors), "kind": kind,
                    "tech": _text(n.get("tech"), f"{w}.tech", 40, errors, required=False)}
            fields = n.get("fields")
            if fields is not None:
                if kind != "entity":
                    errors.append(f"{w}.fields: only an entity has fields")
                elif not isinstance(fields, list):
                    errors.append(f"{w}.fields: must be a list of texts")
                else:
                    if len(fields) > MAX_FIELDS:
                        errors.append(f"{w}.fields: at most {MAX_FIELDS} ({len(fields)}); keep the keys and the fields that matter")
                    node["fields"] = [_text(v, f"{w}.fields[{k}]", 40, errors) for k, v in enumerate(fields[:MAX_FIELDS])]
            clean.append(node)
        out["layers"].append({"id": str(lid), "label": _text(lay.get("label"), f"{where}.label", 40, errors), "nodes": clean})
    ids = {n["id"] for lay in out["layers"] for n in lay["nodes"]}
    if len(ids) > MAX_NODES:
        errors.append(f"at most {MAX_NODES} nodes ({len(ids)}): this is the high-level view, group the details")
    edges = m.get("edges") or []
    if not isinstance(edges, list):
        errors.append("edges: must be a list")
        edges = []
    if len(edges) > MAX_EDGES:
        errors.append(f"edges: at most {MAX_EDGES} ({len(edges)})")
    pairs: set[tuple[str, str]] = set()
    for k, e in enumerate(edges[:MAX_EDGES]):
        w = f"edges[{k}]"
        if not isinstance(e, dict):
            errors.append(f"{w}: must be an object")
            continue
        a, b = e.get("from"), e.get("to")
        bad = False
        for side, v in (("from", a), ("to", b)):
            if v not in ids:
                errors.append(f"{w}.{side}: no node {v!r}")
                bad = True
        if not bad and a == b:
            errors.append(f"{w}: a node cannot point to itself ({a!r})")
            bad = True
        if not bad and (a, b) in pairs:
            errors.append(f"{w}: {a!r} -> {b!r} is drawn twice; put both meanings in one label")
            bad = True
        style = e.get("style", "sync")
        if style not in EDGE_STYLES:
            errors.append(f"{w}.style: one of {', '.join(EDGE_STYLES)} ({style!r})")
            style = "sync"
        label = _text(e.get("label"), f"{w}.label", 32, errors, required=False)
        if not bad:
            pairs.add((str(a), str(b)))
            out["edges"].append({"from": a, "to": b, "label": label, "style": style, "both": e.get("both") is True})
    legend = m.get("legend") or {}
    if not isinstance(legend, dict):
        errors.append("legend: must be an object of kind -> text")
        legend = {}
    out["legend"] = {}
    for k, v in legend.items():
        if k not in KINDS and k not in EDGE_STYLES:
            errors.append(f"legend.{k}: not a kind or an edge style")
        else:
            out["legend"][k] = _text(v, f"legend.{k}", 32, errors)
    return out, errors


# --------------------------------------------------------------------------- layout

def wrap(text: str, width: float, char_w: float, lines: int) -> list[str]:
    """Words into at most `lines` lines that fit `width`; the last one ends with an ellipsis when text is left."""
    per = max(4, int(width / char_w))
    words, out, cur = text.split(), [], ""
    for wd in words:
        if len(wd) > per:
            wd = wd[:per - 1] + "…"
        if not cur:
            cur = wd
        elif len(cur) + 1 + len(wd) <= per:
            cur += " " + wd
        else:
            out.append(cur)
            cur = wd
    if cur:
        out.append(cur)
    if len(out) > lines:
        out = out[:lines]
        last = out[-1]
        out[-1] = (last[:per - 1] if len(last) >= per else last) + "…"
    return out or [""]


def node_h(n: dict) -> float:
    """An entity grows with its fields; every other node has the same height."""
    if n["kind"] == "entity":
        return max(NODE_H, ENTITY_HEAD + FIELD_H * len(n.get("fields") or []) + 8)
    return NODE_H


def layout(m: dict) -> dict:
    """Positions of every lane, node and edge (route points and label place), and the size of the picture."""
    layers = m["layers"]
    where = {n["id"]: (li, ni) for li, lay in enumerate(layers) for ni, n in enumerate(lay["nodes"])}
    widest = max(len(lay["nodes"]) for lay in layers)
    # the gap between neighbours grows so that the label of an edge drawn between them fits in it
    gap = max([NODE_GAP] + [len(e["label"]) * SMALL_W + 28 for e in m["edges"]
                            if where[e["from"]][0] == where[e["to"]][0] and abs(where[e["from"]][1] - where[e["to"]][1]) == 1])
    lane_w = max(widest * NODE_W + (widest - 1) * gap + 2 * LANE_PAD_X,
                 max(len(m["title"]) * 11.0, len(m.get("subtitle") or "") * SMALL_W) - 0.0, 360)
    lane_hs = [LANE_HEAD + 2 * LANE_PAD + max(node_h(n) for n in lay["nodes"]) for lay in layers]

    # 1. what each edge needs: its sides, the gaps it crosses horizontally and whether it takes the right corridor
    plans = []
    for e in m["edges"]:
        (la, na), (lb, nb) = where[e["from"]], where[e["to"]]
        if la == lb and abs(na - nb) == 1:
            kind, a_side, b_side, gaps = "beside", ("r" if nb > na else "l"), ("l" if nb > na else "r"), []
        elif la == lb:
            kind, a_side, b_side, gaps = "under", "b", "b", [la]          # gap below the lane
        elif lb == la + 1:
            kind, a_side, b_side, gaps = "down", "b", "t", [la]
        elif lb == la - 1:
            kind, a_side, b_side, gaps = "up", "t", "b", [lb]
        elif lb > la:
            kind, a_side, b_side, gaps = "far_down", "b", "t", [la, lb - 1]
        else:
            kind, a_side, b_side, gaps = "far_up", "t", "b", [la - 1, lb]
        plans.append({"e": e, "kind": kind, "a": (la, na), "b": (lb, nb), "a_side": a_side, "b_side": b_side, "gaps": gaps})

    # 2. tracks: one height per edge in each gap it crosses, one x per edge in the corridor
    tracks: dict[int, int] = {}
    corridor = 0
    for p in plans:
        p["tracks"] = []
        for g in p["gaps"]:
            p["tracks"].append(tracks.get(g, 0))
            tracks[g] = tracks.get(g, 0) + 1
        if p["kind"].startswith("far_"):
            p["corridor"] = corridor
            corridor += 1
    gap_h = {g: max(GAP_MIN, (n + 1) * TRACK + 16) for g, n in tracks.items()}

    # 3. lanes and nodes
    x0 = MARGIN
    y = MARGIN + TITLE_H
    lanes, nodes = [], {}
    for li, lay in enumerate(layers):
        n = len(lay["nodes"])
        content = n * NODE_W + (n - 1) * gap
        nx = x0 + (lane_w - content) / 2
        lanes.append({"id": lay["id"], "label": lay["label"], "x": x0, "y": y, "w": lane_w, "h": lane_hs[li]})
        for ni, node in enumerate(lay["nodes"]):
            nodes[node["id"]] = {**node, "x": nx + ni * (NODE_W + gap), "y": y + LANE_HEAD + LANE_PAD, "w": NODE_W, "h": node_h(node)}
        y += lane_hs[li] + gap_h.get(li, GAP_MIN if li < len(layers) - 1 else 0)
    gap_top = {li: lanes[li]["y"] + lanes[li]["h"] for li in range(len(layers))}
    corridor_x = x0 + lane_w + 24
    width = corridor_x + (corridor * TRACK + 8 if corridor else -24) + MARGIN
    height = y

    def track_y(g: int, k: int) -> float:
        return gap_top[g] + 8 + (k + 1) * (gap_h.get(g, GAP_MIN) - 16) / (tracks.get(g, 0) + 1)

    # 4. ports: the attachments on each side of a node, spread along it in the order of where the other end is
    sides: dict[tuple[str, str], list] = {}
    for p in plans:
        e = p["e"]
        far_x = corridor_x + p.get("corridor", 0) * TRACK if p["kind"].startswith("far_") else None
        for end, nid, side, other in (("a", e["from"], p["a_side"], e["to"]), ("b", e["to"], p["b_side"], e["from"])):
            o = nodes[other]
            sides.setdefault((nid, side), []).append((far_x if far_x is not None else o["x"] + o["w"] / 2, id(p), end, p))
    for (nid, side), lst in sides.items():
        lst.sort(key=lambda t: (t[0], t[1]))
        nd = nodes[nid]
        for j, (_, _, end, p) in enumerate(lst):
            f = (j + 1) / (len(lst) + 1)
            if side in ("t", "b"):
                pt = (nd["x"] + nd["w"] * f, nd["y"] + (0 if side == "t" else nd["h"]))
            else:
                # along the common height of a lane's nodes (they share their top), so a side-to-side line stays straight
                pt = (nd["x"] + (0 if side == "l" else nd["w"]), nd["y"] + NODE_H * f)
            p[f"{end}_pt"] = pt
            p[f"{end}_frac"] = f

    # 5. routes
    edges = []
    for p in plans:
        (ax, ay), (bx, by) = p["a_pt"], p["b_pt"]
        k = p["kind"]
        if k == "beside":
            pts = [(ax, ay), (bx, ay)] if abs(ay - by) < 1 else [(ax, ay), ((ax + bx) / 2, ay), ((ax + bx) / 2, by), (bx, by)]
        elif k in ("down", "up", "under"):
            ty = track_y(p["gaps"][0], p["tracks"][0])
            pts = [(ax, ay), (ax, ty), (bx, ty), (bx, by)]
        else:
            cx = corridor_x + p["corridor"] * TRACK
            t1, t2 = track_y(p["gaps"][0], p["tracks"][0]), track_y(p["gaps"][1], p["tracks"][1])
            pts = [(ax, ay), (ax, t1), (cx, t1), (cx, t2), (bx, t2), (bx, by)]
        pts = _simplify(pts)
        edges.append({**p["e"], "points": pts, "label_at": _label_at(pts, p["e"]["label"]),
                      "a_side": p["a_side"], "b_side": p["b_side"], "a_frac": p["a_frac"], "b_frac": p["b_frac"]})

    used = []
    for lay_ in layers:
        for n in lay_["nodes"]:
            if n["kind"] not in used:
                used.append(n["kind"])
    styles = [s for s in EDGE_STYLES if any(e["style"] == s for e in m["edges"])]
    full_w = max(width, x0 + lane_w + MARGIN)
    # the legend: one item per kind and edge style used, in rows that fit the picture
    items, lx, ly = [], MARGIN, height + 24
    for key, text, swatch in ([(k, m["legend"].get(k) or LEGEND[k], "kind") for k in used]
                              + [(s, m["legend"].get(s) or EDGE_LEGEND[s], "edge") for s in styles]):
        iw = (24 if swatch == "kind" else 32) + len(text) * SMALL_W
        if lx > MARGIN and lx + iw > full_w - MARGIN:
            lx, ly = MARGIN, ly + 22
        items.append({"key": key, "text": text, "swatch": swatch, "x": lx, "y": ly})
        lx += iw + 18
    return {"lanes": lanes, "nodes": nodes, "edges": edges, "width": full_w,
            "height": (ly + 8 if items else height) + MARGIN, "legend": items, "lane_w": lane_w}


def _simplify(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for pt in pts:
        pt = (round(pt[0], 1), round(pt[1], 1))
        if out and abs(out[-1][0] - pt[0]) < 0.5 and abs(out[-1][1] - pt[1]) < 0.5:
            continue
        out.append(pt)
    # drop middle points on a straight line
    i = 1
    while i < len(out) - 1:
        (x1, y1), (x2, y2), (x3, y3) = out[i - 1], out[i], out[i + 1]
        if (abs(x1 - x2) < 0.5 and abs(x2 - x3) < 0.5) or (abs(y1 - y2) < 0.5 and abs(y2 - y3) < 0.5):
            out.pop(i)
        else:
            i += 1
    return out


def _label_at(pts: list[tuple[float, float]], label: str) -> tuple[float, float, str] | None:
    """Where the label of an edge goes: the middle of its longest horizontal run (always in a gap between lanes),
    else beside its longest vertical run."""
    if not label:
        return None
    best_h, best_v = None, None
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if abs(y1 - y2) < 0.5:
            ln = abs(x2 - x1)
            if best_h is None or ln > best_h[0]:
                best_h = (ln, (x1 + x2) / 2, y1)
        else:
            ln = abs(y2 - y1)
            if best_v is None or ln > best_v[0]:
                best_v = (ln, x1, (y1 + y2) / 2)
    if best_h:
        return (best_h[1], best_h[2], "middle")
    if best_v:
        return (best_v[1] + 6, best_v[2], "start")
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    return ((x1 + x2) / 2, (y1 + y2) / 2 - 8, "middle")


# --------------------------------------------------------------------------- SVG

def _f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _node_svg(n: dict) -> list[str]:
    fill, stroke, shape = KINDS[n["kind"]]
    x, y, w, h = n["x"], n["y"], n["w"], n["h"]
    out = [f'<g class="node" data-id="{escape(n["id"])}">']
    title = wrap(n["label"], w - 16, CHAR_W, 2)
    tech = f'[{n["tech"]}]' if n.get("tech") else ""
    cx = x + w / 2
    if shape == "umlActor":
        # a stick figure with its name under it, as draw.io draws an actor
        hx, top = cx, y + 2
        out.append(f'<g fill="{fill}" stroke="{stroke}" stroke-width="1.5">'
                   f'<circle cx="{_f(hx)}" cy="{_f(top + 7)}" r="7"/>'
                   f'<path d="M{_f(hx)} {_f(top + 14)}V{_f(top + 32)}M{_f(hx - 12)} {_f(top + 20)}H{_f(hx + 12)}'
                   f'M{_f(hx)} {_f(top + 32)}L{_f(hx - 10)} {_f(top + 44)}M{_f(hx)} {_f(top + 32)}L{_f(hx + 10)} {_f(top + 44)}" fill="none"/></g>')
        ty = top + 58
        for ln in title[:1]:
            out.append(f'<text x="{_f(cx)}" y="{_f(ty)}" text-anchor="middle" font-size="13" font-weight="bold">{escape(ln)}</text>')
        if tech:
            out.append(f'<text x="{_f(cx)}" y="{_f(ty + 14)}" text-anchor="middle" font-size="11" fill="#555555">{escape(wrap(tech, w, SMALL_W, 1)[0])}</text>')
        out.append("</g>")
        return out
    if shape == "entity":
        # a table, as draw.io draws one: the name in a coloured header, one row per field, keys marked
        out.append(f'<rect x="{_f(x)}" y="{_f(y)}" width="{_f(w)}" height="{_f(h)}" rx="4" fill="#ffffff" stroke="{stroke}" stroke-width="1.5"/>'
                   f'<path d="M{_f(x + 0.75)} {_f(y + ENTITY_HEAD)}V{_f(y + 4)}Q{_f(x + 0.75)} {_f(y + 0.75)} {_f(x + 4)} {_f(y + 0.75)}'
                   f'H{_f(x + w - 4)}Q{_f(x + w - 0.75)} {_f(y + 0.75)} {_f(x + w - 0.75)} {_f(y + 4)}V{_f(y + ENTITY_HEAD)}Z" fill="{fill}"/>'
                   f'<path d="M{_f(x)} {_f(y + ENTITY_HEAD)}H{_f(x + w)}" stroke="{stroke}" stroke-width="1.5"/>')
        out.append(f'<text x="{_f(cx)}" y="{_f(y + 20)}" text-anchor="middle" font-size="13" font-weight="bold" fill="#1a1a1a">'
                   f'{escape(wrap(n["label"], w - 16, CHAR_W, 1)[0])}</text>')
        fy = y + ENTITY_HEAD + 4
        for fld in n.get("fields") or []:
            key, _, rest = fld.partition(" ")
            is_key = key.upper() in ("PK", "FK") and rest
            if is_key:
                out.append(f'<text x="{_f(x + 8)}" y="{_f(fy + 13)}" font-size="10" font-weight="bold" fill="{stroke}">{escape(key.upper())}</text>')
            txt = wrap(rest if is_key else fld, w - (38 if is_key else 16), SMALL_W, 1)[0]
            out.append(f'<text x="{_f(x + (30 if is_key else 8))}" y="{_f(fy + 13)}" font-size="11" fill="#333333">{escape(txt)}</text>')
            fy += FIELD_H
        out.append("</g>")
        return out
    if shape == "cylinder":
        ry = 9
        out.append(f'<path d="M{_f(x)} {_f(y + ry)}A{_f(w / 2)} {ry} 0 0 1 {_f(x + w)} {_f(y + ry)}V{_f(y + h - ry)}'
                   f'A{_f(w / 2)} {ry} 0 0 1 {_f(x)} {_f(y + h - ry)}Z" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
        out.append(f'<path d="M{_f(x)} {_f(y + ry)}A{_f(w / 2)} {ry} 0 0 0 {_f(x + w)} {_f(y + ry)}" fill="none" stroke="{stroke}" stroke-width="1.5"/>')
        y_text = y + ry + 4
        h_text = h - ry - 6
    else:
        dash = ' stroke-dasharray="6 4"' if shape == "external" else ""
        out.append(f'<rect x="{_f(x)}" y="{_f(y)}" width="{_f(w)}" height="{_f(h)}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{dash}/>')
        if shape == "process":
            out.append(f'<path d="M{_f(x + 12)} {_f(y)}V{_f(y + h)}M{_f(x + w - 12)} {_f(y)}V{_f(y + h)}" stroke="{stroke}" stroke-width="1.5"/>')
        y_text, h_text = y, h
    lines = [(ln, 13, "bold", "#1a1a1a") for ln in title] + ([(wrap(tech, w - 16, SMALL_W, 1)[0], 11, "normal", "#555555")] if tech else [])
    total = sum(16 if s == 13 else 14 for _, s, _, _ in lines)
    ty = y_text + (h_text - total) / 2 + 12
    for ln, size, weight, color in lines:
        out.append(f'<text x="{_f(cx)}" y="{_f(ty)}" text-anchor="middle" font-size="{size}" font-weight="{weight}" fill="{color}">{escape(ln)}</text>')
        ty += 16 if size == 13 else 14
    out.append("</g>")
    return out


def to_svg(m: dict, lay: dict, stamp: str) -> str:
    W, H = lay["width"], lay["height"]
    o = [stamp,
         f'<svg xmlns="http://www.w3.org/2000/svg" width="{_f(W)}" height="{_f(H)}" viewBox="0 0 {_f(W)} {_f(H)}" '
         f'font-family="{FONT}" role="img" aria-labelledby="dk-title">',
         f'<title id="dk-title">{escape(m["title"])}</title>',
         '<defs><marker id="dk-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
         '<path d="M0 0L10 5L0 10z" fill="#333333"/></marker></defs>',
         f'<rect width="{_f(W)}" height="{_f(H)}" fill="#ffffff"/>',
         f'<text x="{MARGIN}" y="{MARGIN + 20}" font-size="20" font-weight="bold" fill="#1a1a1a">{escape(m["title"])}</text>']
    if m.get("subtitle"):
        o.append(f'<text x="{MARGIN}" y="{MARGIN + 40}" font-size="12" fill="#666666">{escape(m["subtitle"])}</text>')
    for ln in lay["lanes"]:
        o.append(f'<g class="lane" data-id="{escape(ln["id"])}">'
                 f'<rect x="{_f(ln["x"])}" y="{_f(ln["y"])}" width="{_f(ln["w"])}" height="{_f(ln["h"])}" rx="4" fill="#fafafa" stroke="#c8c8c8"/>'
                 f'<path d="M{_f(ln["x"])} {_f(ln["y"] + LANE_HEAD)}H{_f(ln["x"] + ln["w"])}" stroke="#c8c8c8"/>'
                 f'<text x="{_f(ln["x"] + 12)}" y="{_f(ln["y"] + 20)}" font-size="13" font-weight="bold" fill="#333333">{escape(ln["label"])}</text></g>')
    for e in lay["edges"]:
        d = "M" + "L".join(f"{_f(x)} {_f(y)}" for x, y in e["points"])
        dash = ' stroke-dasharray="6 4"' if e["style"] == "async" else ' stroke-dasharray="2 3"' if e["style"] == "data" else ""
        start = ' marker-start="url(#dk-arrow)"' if e["both"] and e["style"] != "relation" else ""
        end = "" if e["style"] == "relation" else ' marker-end="url(#dk-arrow)"'
        o.append(f'<path class="edge" data-from="{escape(e["from"])}" data-to="{escape(e["to"])}" d="{d}" fill="none" '
                 f'stroke="#333333" stroke-width="1.5"{dash}{start}{end}/>')
    for n in lay["nodes"].values():
        o.extend(_node_svg(n))
    for e in lay["edges"]:   # labels last, over the lines
        if not e["label_at"]:
            continue
        x, y, anchor = e["label_at"]
        w = len(e["label"]) * SMALL_W + 8
        rx = x - w / 2 if anchor == "middle" else x - 4
        o.append(f'<rect x="{_f(rx)}" y="{_f(y - 9)}" width="{_f(w)}" height="16" rx="3" fill="#ffffff" fill-opacity="0.92"/>'
                 f'<text x="{_f(x)}" y="{_f(y + 3)}" text-anchor="{anchor}" font-size="11" fill="#333333">{escape(e["label"])}</text>')
    for it in lay["legend"]:
        x, y, text = it["x"], it["y"], it["text"]
        if it["swatch"] == "kind":
            fill, stroke, shape = KINDS[it["key"]]
            dash = ' stroke-dasharray="4 3"' if shape == "external" else ""
            o.append(f'<rect x="{_f(x)}" y="{_f(y - 10)}" width="18" height="12" rx="3" fill="{fill}" stroke="{stroke}"{dash}/>'
                     f'<text x="{_f(x + 24)}" y="{_f(y)}" font-size="11" fill="#555555">{escape(text)}</text>')
        else:
            s = it["key"]
            dash = ' stroke-dasharray="6 4"' if s == "async" else ' stroke-dasharray="2 3"' if s == "data" else ""
            arrow = "" if s == "relation" else ' marker-end="url(#dk-arrow)"'
            o.append(f'<path d="M{_f(x)} {_f(y - 4)}H{_f(x + 26)}" stroke="#333333" stroke-width="1.5"{dash}{arrow}/>'
                     f'<text x="{_f(x + 32)}" y="{_f(y)}" font-size="11" fill="#555555">{escape(text)}</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


# --------------------------------------------------------------------------- draw.io

def _attr(v: str) -> str:
    return escape(v, {'"': "&quot;", "\n": "&#10;"})


def to_drawio(m: dict, lay: dict, kind: str = "architecture") -> str:
    """The same picture as an uncompressed draw.io file: lanes are swimlanes, nodes their children, edges keep
    the route points and the ports."""
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    lane_of = {n["id"]: lane["id"] for lane in m["layers"] for n in lane["nodes"]}
    lanes = {ln["id"]: ln for ln in lay["lanes"]}
    for ln in lay["lanes"]:
        cells.append(f'<mxCell id="lane-{ln["id"]}" value="{_attr(ln["label"])}" style="swimlane;startSize={LANE_HEAD};rounded=1;arcSize=2;'
                     f'fillColor=#fafafa;swimlaneFillColor=#fafafa;strokeColor=#c8c8c8;fontStyle=1;align=left;spacingLeft=12;html=1;" vertex="1" parent="1">'
                     f'<mxGeometry x="{_f(ln["x"])}" y="{_f(ln["y"])}" width="{_f(ln["w"])}" height="{_f(ln["h"])}" as="geometry"/></mxCell>')
    for n in lay["nodes"].values():
        fill, stroke, shape = KINDS[n["kind"]]
        base = {"rounded": "rounded=1;arcSize=12;", "cylinder": "shape=cylinder3;boundedLbl=1;size=9;",
                "process": "shape=process;size=0.07;", "external": "rounded=1;arcSize=12;dashed=1;",
                "umlActor": "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;outlineConnect=0;",
                "entity": "rounded=0;verticalAlign=top;align=left;spacingLeft=8;spacingTop=4;"}[shape]
        value = f"<b>{escape(n['label'])}</b>" + (f"<br><font style=\"font-size:11px\" color=\"#555555\">[{escape(n['tech'])}]</font>" if n.get("tech") else "")
        if shape == "entity":
            value = (f"<div style=\"text-align:center\"><b>{escape(n['label'])}</b></div><hr>"
                     + "<br>".join(escape(v) for v in n.get("fields") or []))
            fill = "#ffffff"
        ln = lanes[lane_of[n["id"]]]
        x, y, w, h = n["x"] - ln["x"], n["y"] - ln["y"], n["w"], n["h"]
        if shape == "umlActor":
            x, w, h = x + w / 2 - 15, 30, 46
        cells.append(f'<mxCell id="{n["id"]}" value="{_attr(value)}" style="{base}whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};'
                     f'fontFamily=Helvetica;fontSize=13;" vertex="1" parent="lane-{ln["id"]}">'
                     f'<mxGeometry x="{_f(x)}" y="{_f(y)}" width="{_f(w)}" height="{_f(h)}" as="geometry"/></mxCell>')
    side_xy = {"t": lambda f: (f, 0), "b": lambda f: (f, 1), "l": lambda f: (0, f), "r": lambda f: (1, f)}
    for i, e in enumerate(lay["edges"]):
        ex, ey = side_xy[e["a_side"]](e["a_frac"])
        nx, ny = side_xy[e["b_side"]](e["b_frac"])
        dash = "dashed=1;dashPattern=6 4;" if e["style"] == "async" else "dashed=1;dashPattern=2 3;" if e["style"] == "data" else ""
        both = "startArrow=classic;startFill=1;" if e["both"] and e["style"] != "relation" else ""
        arrow = "endArrow=none;" if e["style"] == "relation" else "endArrow=classic;endFill=1;"
        pts = "".join(f'<mxPoint x="{_f(x)}" y="{_f(y)}"/>' for x, y in e["points"][1:-1])
        cells.append(f'<mxCell id="edge-{i + 1}" value="{_attr(e["label"])}" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;'
                     f'{arrow}{both}{dash}strokeColor=#333333;strokeWidth=1.5;fontSize=11;labelBackgroundColor=#ffffff;'
                     f'exitX={_f(ex)};exitY={_f(ey)};exitDx=0;exitDy=0;entryX={_f(nx)};entryY={_f(ny)};entryDx=0;entryDy=0;" '
                     f'edge="1" parent="1" source="{e["from"]}" target="{e["to"]}">'
                     f'<mxGeometry relative="1" as="geometry">{"<Array as=" + chr(34) + "points" + chr(34) + ">" + pts + "</Array>" if pts else ""}</mxGeometry></mxCell>')
    cells.append(f'<mxCell id="title" value="{_attr("<b>" + escape(m["title"]) + "</b>" + ("<br>" + escape(m["subtitle"]) if m.get("subtitle") else ""))}" '
                 f'style="text;html=1;align=left;verticalAlign=top;fontSize=20;" vertex="1" parent="1">'
                 f'<mxGeometry x="{MARGIN}" y="{MARGIN}" width="{_f(lay["lane_w"])}" height="{TITLE_H - 8}" as="geometry"/></mxCell>')
    W, H = int(lay["width"]) + 1, int(lay["height"]) + 1
    return (f'<mxfile host="dev-kit" type="device">\n<diagram id="{kind}" name="{_attr(m["title"])}">\n'
            f'<mxGraphModel dx="{W}" dy="{H}" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" '
            f'page="1" pageScale="1" pageWidth="{W}" pageHeight="{H}" math="0" shadow="0">\n<root>\n'
            + "\n".join(cells) + "\n</root>\n</mxGraphModel>\n</diagram>\n</mxfile>\n")


# --------------------------------------------------------------------------- files

def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def section(text: str, head: re.Pattern) -> str | None:
    """The `## ` section of a markdown text whose heading matches, up to the next `## ` heading (None: not found)."""
    lines = text.splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if head.match(ln):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("## "):
                j += 1
            return "".join(lines[i:j])
    return None


def sources_sha(root: Path, kind: str = "architecture") -> str:
    """The hash of what a diagram is drawn from: architecture.md, or only its section for data and deploy, so a
    change to the data model leaves the deploy diagram current."""
    head = DIAGRAMS[kind]["section"]
    parts = []
    for rel in SOURCES:
        p = root / rel
        if p.is_file():
            raw = p.read_bytes()
            if head is not None:
                part = section(raw.decode("utf-8", errors="replace"), head)
                if part is not None:
                    raw = part.encode("utf-8")
            parts.append(rel.encode() + b"\0" + raw)
    return _sha(b"\0\0".join(parts)) if parts else "none"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def render(root: Path, model: Path, svg: Path, drawio: Path, kind: str = "architecture") -> tuple[dict, list[str]]:
    try:
        raw = model.read_bytes()
    except OSError:
        return {}, [f"no model at {model} (write it first; `example` prints one)"]
    try:
        m = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return {}, [f"{model}: not valid JSON ({e})"]
    clean, errors = validate(m)
    if errors:
        return {}, errors
    lay = layout(clean)
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = f"<!-- dev-kit diagram model={_sha(raw)} sources={sources_sha(root, kind)} at={at} -->"
    _write(svg, to_svg(clean, lay, stamp))
    _write(drawio, to_drawio(clean, lay, kind))
    return {"ok": True, "kind": kind, "svg": _rel(root, svg), "drawio": _rel(root, drawio), "model": _rel(root, model),
            "nodes": len(lay["nodes"]), "edges": len(lay["edges"]), "layers": len(lay["lanes"]),
            "size": [int(lay["width"]), int(lay["height"])], "at": at}, []


def _rel(root: Path, p: Path) -> str:
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(p)


def status(root: Path, model: Path | None = None, svg: Path | None = None, kind: str = "architecture") -> dict:
    """Whether the project has a diagram of this kind and whether it is current. Read by `check` and by the board."""
    dm, ds, dd = paths(root, kind)
    model = model or dm
    svg = svg or ds
    out = {"kind": kind, "exists": svg.is_file(), "model_exists": model.is_file(), "svg": _rel(root, ds),
           "drawio": _rel(root, dd), "model": _rel(root, dm), "current": False, "stale": False, "at": None, "reasons": []}
    if not out["exists"]:
        out["reasons"].append("no diagram yet")
        return out
    try:
        head = svg.read_text(encoding="utf-8", errors="replace")[:400]
    except OSError:
        head = ""
    st = STAMP_RE.search(head)
    if not st:
        out["reasons"].append("the SVG was not drawn by dev_diagram.py render")
        return out
    out["at"] = st.group(3)
    try:
        out["current"] = model.is_file() and _sha(model.read_bytes()) == st.group(1)
    except OSError:
        out["current"] = False
    if not out["current"]:
        out["reasons"].append("the model changed since the SVG was drawn (run render)" if model.is_file() else "the model is missing")
    if st.group(2) != sources_sha(root, kind):
        out["stale"] = True
        where = {"data": " (its data model)", "deploy": " (its environments)"}.get(kind, "")
        out["reasons"].append(f".dev/architecture.md{where} changed since the diagram was drawn")
    return out


def statuses(root: Path) -> dict:
    """Every kind, for the board: {kind: status}."""
    return {k: status(root, kind=k) for k in DIAGRAMS}


def expected(root: Path) -> list[str]:
    """The kinds `check --kind all` holds the project to: architecture always, data and deploy once started."""
    return [k for k in DIAGRAMS if k == "architecture" or any(p.is_file() for p in paths(root, k)[:2])]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dev_diagram.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render", help="check the model and draw the SVG and the .drawio file")
    r.add_argument("--kind", choices=list(DIAGRAMS), default="architecture")
    r.add_argument("--model")
    r.add_argument("--svg")
    r.add_argument("--drawio")
    r.add_argument("--json", action="store_true")
    c = sub.add_parser("check", help="is the diagram there and current")
    c.add_argument("--kind", choices=[*DIAGRAMS, "all"], default="architecture")
    c.add_argument("--json", action="store_true")
    c.add_argument("--info", action="store_true", help="exit 0 whatever the answer (for a line injected in a skill)")
    e = sub.add_parser("example", help="print a model to start from")
    e.add_argument("--kind", choices=list(DIAGRAMS), default="architecture")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    if a.cmd == "example":
        print(json.dumps(example(a.kind), indent=2, ensure_ascii=False))
        return 0
    if a.cmd == "render":
        dm, ds, dd = paths(root, a.kind)
        p = lambda v, d: (Path(v) if Path(v).is_absolute() else root / v) if v else d  # noqa: E731
        res, errors = render(root, p(a.model, dm), p(a.svg, ds), p(a.drawio, dd), a.kind)
        if errors:
            if a.json:
                print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False))
            else:
                print("invalid model:", file=sys.stderr)
                for e in errors:
                    print(f"  - {e}", file=sys.stderr)
            return 1
        print(json.dumps(res, ensure_ascii=False) if a.json else
              f"drew {res['svg']} and {res['drawio']}: {res['layers']} layers, {res['nodes']} nodes, {res['edges']} edges")
        return 0
    kinds = expected(root) if a.kind == "all" else [a.kind]
    sts = [status(root, kind=k) for k in kinds]
    if a.json:
        print(json.dumps(sts[0] if a.kind != "all" else {"kinds": {s["kind"]: s for s in sts}}, ensure_ascii=False))
    else:
        for st in sts:
            arg = "" if st["kind"] == "architecture" else f" {st['kind']}"
            if not st["exists"]:
                print(f"no {st['kind']} diagram ({st['svg']}): run /dev-kit:diagram{arg}")
            elif st["current"] and not st["stale"]:
                print(f"{st['svg']} is current (drawn {st['at']})")
            else:
                print(f"{st['svg']} is out of date: " + "; ".join(st["reasons"]) + f" — run /dev-kit:diagram update{arg}")
    if a.info:
        return 0
    codes = [0 if st["exists"] and st["current"] and not st["stale"] else 3 if not st["exists"] else 4 for st in sts]
    return 3 if 3 in codes else max(codes)


if __name__ == "__main__":
    sys.exit(main())
