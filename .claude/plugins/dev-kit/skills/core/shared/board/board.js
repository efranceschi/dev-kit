/* dev-kit board - read-only view of .dev/state.json. No dependencies. All untrusted text goes through textContent. */
(() => {
  "use strict";

  const TOKEN = document.querySelector('meta[name="board-token"]').content;
  const SVGNS = "http://www.w3.org/2000/svg";
  const STATUS = [
    { key: "todo", label: "To do", icon: "○" },
    { key: "in_progress", label: "In progress", icon: "◐" },
    { key: "blocked", label: "Blocked", icon: "⛔" },
    { key: "done", label: "Done", icon: "✓" },
  ];
  const PHASE_LABEL = { init: "init", interview: "interview", prd: "PRD", architecture: "architecture", ux: "UX", ui: "UI",
    plan: "plan", implement: "implement", qa: "QA", usability: "usability", docs: "docs", done: "done" };

  let data = null;
  let selected = null;       // milestone id chosen by the user (null = follow the current one)
  let lastUpdate = 0;
  let es = null;
  let stopped = false;
  let loading = false;
  let pending = false;

  // ------------------------------------------------------------------ helpers
  const $ = (id) => document.getElementById(id);
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }
  function s(tag, attrs, ...kids) {
    const el = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined) continue;
      if (k === "text") el.textContent = v; else el.setAttribute(k, v);
    }
    for (const kid of kids.flat()) if (kid) el.append(kid);
    return el;
  }
  const fill = (el, ...kids) => { el.replaceChildren(...kids.flat().filter(Boolean)); return el; };
  const parseT = (v) => (v ? new Date(v).getTime() : NaN);
  const fmtDate = (t) => new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const fmtDT = (t) => new Date(t).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  const compact = (n) => (n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e4 ? Math.round(n / 1e3) + "K" : n.toLocaleString());
  function ago(t) {
    const s = Math.max(0, Math.round((Date.now() - t) / 1000));
    if (s < 5) return "just now";
    if (s < 60) return `${s} s ago`;
    if (s < 3600) return `${Math.floor(s / 60)} min ago`;
    return `${Math.floor(s / 3600)} h ago`;
  }
  function tasksOf(m) { return (m ? m.tasks : []).map((id) => ({ id, ...data.tasks[id] })); }
  function gateBadge(m, q) {
    if (!m) return null;
    if (m.gate === "passed") return h("span", { class: "badge good" }, "✓ Gate passed" + (m.score != null ? ` · ${m.score}` : ""));
    if (m.gate === "skipped") return h("span", { class: "badge neutral" }, "Gate skipped");
    if (m.score != null) return h("span", { class: "badge bad" }, `✕ Gate failed · ${m.score} / ${q.min_overall}`);
    return h("span", { class: "badge warn" }, "◌ Gate pending" + (m.qa_runs ? ` · ${m.qa_runs} QA runs` : ""));
  }

  // ------------------------------------------------------------------ tooltip
  const tip = $("tooltip");
  function showTip(evt, title, rows) {
    fill(tip, h("div", { class: "tt-title", text: title }),
      rows.map(([value, label, cls]) => h("div", { class: "tt-row" },
        cls ? h("span", { class: `key-line ${cls}`, "aria-hidden": "true" }) : null, h("strong", { text: value }), h("span", { text: label }))));
    tip.hidden = false;
    let x, y;
    if (evt.clientX !== undefined && evt.type !== "focus") { x = evt.clientX; y = evt.clientY; }
    else { const r = evt.target.getBoundingClientRect(); x = r.left + r.width / 2; y = r.top; }
    const w = tip.offsetWidth, hh = tip.offsetHeight;
    tip.style.left = Math.min(window.innerWidth - w - 8, Math.max(8, x + 14)) + "px";
    tip.style.top = Math.max(8, y - hh - 12) + "px";
  }
  const hideTip = () => { tip.hidden = true; };

  // ------------------------------------------------------------------ render pieces
  function renderHeader() {
    $("project").textContent = data.project;
    document.title = `${data.project} · dev-kit board`;
    $("kit-ver").textContent = data.kit && data.kit !== "unknown" ? `v${data.kit}` : "";
    const phases = data.phases.filter((p) => p !== "init");
    const idx = phases.indexOf(data.phase);
    fill($("phases"), phases.map((p, i) => h("li", {
      class: i < idx || data.phase === "done" ? "past" : i === idx ? "current" : "",
      "aria-current": i === idx ? "step" : null, text: PHASE_LABEL[p] || p,
      "data-step": i === idx ? ` · step ${i + 1} of ${phases.length}` : null,
    })));
  }

  function currentId() {
    const ids = data.milestones.map((m) => m.id);
    if (selected && ids.includes(selected)) return selected;
    return data.current_milestone || ids[0] || null;
  }

  function renderTabs() {
    const cur = currentId();
    const tabs = data.milestones.map((m) => {
      const ts = tasksOf(m);
      const active = ts.some((t) => t.status === "in_progress");
      const done = ts.filter((t) => t.status === "done").length;
      return h("button", {
        role: "tab", type: "button", id: `tab-${m.id}`, "aria-selected": String(m.id === cur), "aria-controls": "main",
        tabindex: m.id === cur ? "0" : "-1", title: m.title || m.id,
        onclick: () => { selected = m.id; render(); $(`tab-${m.id}`).focus(); },
      }, h("span", { class: `tab-dot ${active ? "active" : m.gate}`, "aria-hidden": "true" }), h("strong", { text: m.id }),
      h("span", { text: `${done}/${ts.length}` }),
      m.id === data.current_milestone ? h("span", { class: "tab-current", text: "current" }) : null);
    });
    if (!tabs.length) tabs.push(h("span", { class: "card-sub", text: "No milestones yet. They appear after /dev-kit:plan." }));
    fill($("tabs"), tabs);
  }

  function renderHero(m) {
    const ts = tasksOf(m);
    const counts = Object.fromEntries(STATUS.map((st) => [st.key, ts.filter((t) => t.status === st.key).length]));
    const pct = ts.length ? Math.round((counts.done / ts.length) * 100) : 0;
    $("sprint-eyebrow").textContent = m ? `Sprint ${m.id}${m.id === data.current_milestone ? " · current" : ""}` : "Sprint";
    $("sprint-title").textContent = m ? m.title || m.id : "No sprint planned yet";
    $("sprint-goal").textContent = m ? m.goal || "No goal paragraph in plan.md for this milestone." : "Run /dev-kit:plan to create milestones and tasks.";
    $("hero-pct").textContent = String(pct);
    const order = ["done", "in_progress", "blocked", "todo"];
    fill($("segbar"), order.filter((k) => counts[k]).map((k) => {
      const sp = h("span", { class: `st-${k}`, title: `${STATUS.find((x) => x.key === k).label}: ${counts[k]}` });
      sp.style.flexGrow = String(counts[k]);
      return sp;
    }));
    $("segbar").setAttribute("aria-label", order.map((k) => `${STATUS.find((x) => x.key === k).label} ${counts[k]}`).join(", "));
    fill($("seg-legend"), order.map((k) => h("li", {}, h("span", { class: `swatch st-${k}`, "aria-hidden": "true" }),
      `${STATUS.find((x) => x.key === k).label} ${counts[k]}`)));
    fill($("gate-badge"), gateBadge(m, data.quality));
  }

  function tile(label, value, note, extra) {
    return h("div", { class: `tile ${extra || ""}` }, h("div", { class: "tile-label", text: label }),
      h("div", { class: "tile-value" }, value), note ? h("div", { class: "tile-note", text: note }) : null);
  }

  function renderTiles(m) {
    const ts = tasksOf(m);
    const done = ts.filter((t) => t.status === "done").length;
    const inprog = ts.filter((t) => t.status === "in_progress");
    const blockedAll = Object.values(data.tasks).filter((t) => t.status === "blocked").length;
    const imp = blockedAll + data.questions.length;
    const p = data.progress;
    const scoreVal = m && m.score != null ? h("span", {}, String(m.score), h("small", { text: `/ ${data.quality.min_overall}` })) : "—";
    const c = data.costs;
    fill($("tiles"),
        tile("Sprint backlog", h("span", {}, String(done), h("small", { text: `/ ${ts.length} done` })), `Project: ${p.done}/${p.total} tasks done`),
        tile("In progress", String(inprog.length), inprog.length ? `${inprog[0].id} ${inprog[0].title}` : "Nobody is working right now"),
        tile("Impediments", String(imp), `${blockedAll} blocked · ${data.questions.length} open questions`, imp ? "alert" : ""),
        tile("Gate score", scoreVal, m ? `Cut-off ${data.quality.min_overall} overall · ${data.quality.min_dimension} per dimension` : ""),
      tile("Estimated cost", c ? `US$ ${Number(c.usd || 0).toFixed(2)}` : "—", c ? `${compact(c.tokens || 0)} tokens (API-equivalent)` : "Run /dev-kit:costs to compute"));
  }

  function taskCard(t) {
    const isNext = data.next && data.next.task === t.id;
    const deps = (t.deps || []).filter(Boolean);
    return h("article", { class: `tcard s-${t.status}${isNext ? " next" : ""}`, "aria-label": `${t.id} ${t.title}, ${t.status.replace("_", " ")}` },
      h("div", { class: "tcard-top" }, h("span", { class: "tid", text: t.id }), h("span", { class: "chip", text: t.type }),
        t.lane ? h("span", { class: `chip lane-${t.lane}`, text: t.lane }) : null,
        isNext ? h("span", { class: "chip next-chip", text: "next up" }) : null),
      h("div", { class: "tcard-title", text: t.title }),
      agentsOn(t.id).length ? h("div", { class: "tcard-agents" }, agentsOn(t.id).map((x) => h("span", { class: "agent-chip small" },
        h("span", { class: "agent-dot", "aria-hidden": "true" }), h("span", { class: "agent-name", text: x.agent }),
        h("span", { class: "agent-time", "data-start": x.started_at, text: fmtDur((Date.now() - parseT(x.started_at)) / 1000) })))) : null,
      t.status === "blocked" && t.blocked_reason ? h("div", { class: "reason", text: t.blocked_reason }) : null,
      h("div", { class: "tcard-meta" },
        t.acceptance ? h("span", { text: `${t.acceptance} AC` }) : null,
        deps.length ? h("span", { text: `deps ${deps.join(", ")}` }) : null,
        t.status === "in_progress" && t.started_at ? h("span", { text: `started ${ago(parseT(t.started_at))}` }) : null,
        t.status === "done" && t.done_at ? h("span", { text: `done ${fmtDT(parseT(t.done_at))}` }) : null,
        t.commit ? h("span", { class: "tid", text: t.commit.slice(0, 7) }) : null));
  }

  function renderKanban(m) {
    const ts = tasksOf(m);
    fill($("kanban"), STATUS.map((st) => {
      const list = ts.filter((t) => t.status === st.key);
      if (st.key === "done") list.sort((a, b) => parseT(b.done_at) - parseT(a.done_at));
      return h("section", { class: "col", "aria-label": `${st.label}, ${list.length} tasks` },
        h("div", { class: "col-head" }, h("span", { class: `swatch st-${st.key}`, "aria-hidden": "true" }), st.label,
          h("span", { class: "count", text: String(list.length) })),
        list.length ? list.map(taskCard) : h("div", { class: "col-empty", text: st.key === "blocked" ? "No impediments" : "Empty" }));
    }));
    const nx = data.next || {};
    $("next-up").textContent = nx.task ? `Next up: ${nx.task} ${data.tasks[nx.task].title}` : nx.reason ? `Next: ${nx.reason}` : "";
  }

  // ------------------------------------------------------------------ burndown (step line over time + ideal line)
  function burndownSeries(m) {
    const ts = tasksOf(m);
    const total = ts.length;
    const starts = ts.map((t) => parseT(t.started_at)).filter(Number.isFinite);
    const dones = ts.map((t) => parseT(t.done_at)).filter(Number.isFinite).sort((a, b) => a - b);
    if (!total || !starts.length && !dones.length) return null;
    const t0 = Math.min(...starts, ...dones);
    const end = m.gate === "passed" && m.passed_at ? Math.max(parseT(m.passed_at), dones.at(-1) || t0)
      : dones.length === total ? dones.at(-1) : Date.now();
    const t1 = Math.max(end, t0 + 60e3);
    const pts = [[t0, total]];
    let rem = total;
    for (const d of dones) { pts.push([d, rem]); rem -= 1; pts.push([d, rem]); }
    pts.push([t1, rem]);
    return { total, t0, t1, pts, dones };
  }

  function renderBurndown(m) {
    const box = $("burndown");
    const ser = m && burndownSeries(m);
    if (!ser) {
      fill(box, h("div", { class: "chart-empty", text: "The burndown starts when the first task of this sprint starts." }));
      fill($("burndown-table"));
      return;
    }
    const W = Math.max(300, Math.round(box.clientWidth || 640)), H = 240, L = 36, R = 16, T = 14, B = 28;
    const x = (t) => L + ((t - ser.t0) / (ser.t1 - ser.t0)) * (W - L - R);
    const y = (v) => T + (1 - v / Math.max(1, ser.total)) * (H - T - B);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Burndown for ${m.id}: ${ser.pts.at(-1)[1]} of ${ser.total} tasks remaining` });
    const step = ser.total <= 6 ? 1 : Math.ceil(ser.total / 5);
    const grid = s("g", { class: "grid" });
    for (let v = 0; v <= ser.total; v += step) {
      grid.append(s("line", { x1: L, x2: W - R, y1: y(v), y2: y(v) }), s("text", { x: L - 8, y: y(v) + 4, "text-anchor": "end", text: String(v) }));
    }
    svg.append(grid);
    const span = ser.t1 - ser.t0;
    const nTicks = Math.max(2, Math.min(4, Math.floor((W - L - R) / 130)));
    let prevLabel = null;
    for (let i = 0; i <= nTicks; i++) {
      const t = ser.t0 + (span * i) / nTicks;
      const label = span < 2 * 86400e3 ? new Date(t).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : fmtDate(t);
      if (label === prevLabel) continue;
      prevLabel = label;
      svg.append(s("text", { x: x(t), y: H - 8, "text-anchor": i === 0 ? "start" : i === nTicks ? "end" : "middle", text: label }));
    }
    svg.append(s("line", { class: "axis-line", x1: L, x2: W - R, y1: y(0), y2: y(0) }));
    const pathD = ser.pts.map(([t, v], i) => `${i ? "L" : "M"}${x(t).toFixed(1)},${y(v).toFixed(1)}`).join("");
    svg.append(s("path", { class: "area-actual", d: `${pathD}L${x(ser.t1)},${y(0)}L${x(ser.t0)},${y(0)}Z` }));
    svg.append(s("path", { class: "line-ideal", d: `M${x(ser.t0)},${y(ser.total)}L${x(ser.t1)},${y(0)}` }));
    svg.append(s("path", { class: "line-actual", d: pathD }));
    const last = ser.pts.at(-1);
    svg.append(s("circle", { class: "marker", cx: x(last[0]), cy: y(last[1]), r: 5 }));
    svg.append(s("text", { class: "label-strong", x: x(last[0]) - 8, y: y(last[1]) - 10, "text-anchor": "end", text: `${last[1]} left` }));
    const cross = s("line", { class: "crosshair", y1: T, y2: y(0), visibility: "hidden" });
    const dot = s("circle", { class: "marker", r: 4, visibility: "hidden" });
    svg.append(cross, dot);
    const hit = s("rect", { x: L, y: T, width: W - L - R, height: H - T - B, fill: "transparent", tabindex: "0",
      "aria-label": "Burndown chart; use the table view for every value" });
    const remAt = (t) => { let v = ser.total; for (const [pt, pv] of ser.pts) if (pt <= t) v = pv; return v; };
    const idealAt = (t) => Math.max(0, ser.total * (1 - (t - ser.t0) / (ser.t1 - ser.t0)));
    function move(evt) {
      const r = svg.getBoundingClientRect();
      const px = evt.type === "focus" ? x(last[0]) : ((evt.clientX - r.left) / r.width) * W;
      const t = ser.t0 + ((Math.min(W - R, Math.max(L, px)) - L) / (W - L - R)) * (ser.t1 - ser.t0);
      cross.setAttribute("x1", x(t)); cross.setAttribute("x2", x(t)); cross.setAttribute("visibility", "visible");
      dot.setAttribute("cx", x(t)); dot.setAttribute("cy", y(remAt(t))); dot.setAttribute("visibility", "visible");
      showTip(evt, fmtDT(t), [[String(remAt(t)), "remaining", "s1"], [idealAt(t).toFixed(1), "ideal", "ideal"]]);
    }
    hit.addEventListener("pointermove", move); hit.addEventListener("focus", move);
    const out = () => { cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); hideTip(); };
    hit.addEventListener("pointerleave", out); hit.addEventListener("blur", out);
    svg.append(hit);
    fill(box, svg);
    const rows = [[ser.t0, ser.total, "sprint start"]];
    let rem = ser.total;
    for (const d of ser.dones) { rem -= 1; rows.push([d, rem, "task done"]); }
    fill($("burndown-table"), h("table", {}, h("thead", {}, h("tr", {}, h("th", { text: "When" }), h("th", { text: "Remaining" }), h("th", { text: "Event" }))),
      h("tbody", {}, rows.map(([t, v, e]) => h("tr", {}, h("td", { text: fmtDT(t) }), h("td", { text: String(v) }), h("td", { text: e }))))));
  }

  // ------------------------------------------------------------------ velocity (one series: done per milestone)
  function renderVelocity(cur) {
    const box = $("velocity");
    const rows = data.milestones.map((m) => {
      const ts = tasksOf(m);
      return { id: m.id, title: m.title, done: ts.filter((t) => t.status === "done").length, total: ts.length };
    }).filter((r) => r.total);
    if (!rows.length) {
      fill(box, h("div", { class: "chart-empty", text: "Velocity appears once sprints have tasks." }));
      fill($("velocity-table"));
      return;
    }
    const W = Math.max(260, Math.round(box.clientWidth || 420)), H = 240, L = 30, R = 8, T = 22, B = 28;
    const max = Math.max(1, ...rows.map((r) => r.total));
    const y = (v) => T + (1 - v / max) * (H - T - B);
    const band = (W - L - R) / rows.length;
    const bw = Math.min(24, band * 0.6);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Tasks done per sprint: " + rows.map((r) => `${r.id} ${r.done}`).join(", ") });
    svg.append(s("defs", {}, s("linearGradient", { id: "accent-grad", x1: "0", y1: "1", x2: "0", y2: "0" },
      s("stop", { offset: "0", "stop-color": "#8b5cf6" }), s("stop", { offset: "1", "stop-color": "#22d3ee" }))));
    const step = max <= 6 ? 1 : Math.ceil(max / 5);
    const grid = s("g", { class: "grid" });
    for (let v = 0; v <= max; v += step) grid.append(s("line", { x1: L, x2: W - R, y1: y(v), y2: y(v) }), s("text", { x: L - 8, y: y(v) + 4, "text-anchor": "end", text: String(v) }));
    svg.append(grid);
    rows.forEach((r, i) => {
      const cx = L + band * i + band / 2;
      const top = y(r.done), base = y(0);
      const hgt = Math.max(0, base - top);
      const rad = Math.min(4, hgt);
      const d = hgt > 0 ? `M${cx - bw / 2},${base}V${top + rad}Q${cx - bw / 2},${top} ${cx - bw / 2 + rad},${top}H${cx + bw / 2 - rad}Q${cx + bw / 2},${top} ${cx + bw / 2},${top + rad}V${base}Z` : "";
      const hit = s("rect", { class: "hit", x: cx - band / 2 + 2, y: T, width: band - 4, height: H - T - B, tabindex: "0",
        "aria-label": `${r.id}: ${r.done} of ${r.total} tasks done` });
      const tipFn = (evt) => showTip(evt, `${r.id} · ${r.title || ""}`, [[`${r.done}`, `done of ${r.total}`, "s1"]]);
      hit.addEventListener("pointermove", tipFn); hit.addEventListener("focus", tipFn);
      hit.addEventListener("pointerleave", hideTip); hit.addEventListener("blur", hideTip);
      svg.append(hit, s("path", { class: `bar${r.id === cur ? " current" : ""}`, d }));
      svg.append(s("text", { class: "label-strong", x: cx, y: top - 6, "text-anchor": "middle", text: String(r.done) }));
      svg.append(s("text", { x: cx, y: H - 8, "text-anchor": "middle", text: r.id }));
    });
    fill(box, svg);
    fill($("velocity-table"), h("table", {}, h("thead", {}, h("tr", {}, h("th", { text: "Sprint" }), h("th", { text: "Done" }), h("th", { text: "Total" }))),
      h("tbody", {}, rows.map((r) => h("tr", {}, h("td", { text: `${r.id} ${r.title || ""}` }), h("td", { text: String(r.done) }), h("td", { text: String(r.total) }))))));
  }

  // ------------------------------------------------------------------ backlog, impediments, definition of done, activity
  function listBlock(title, items, emptyText, good) {
    return h("div", {}, h("div", { class: "list-title" }, title, items.length ? h("span", { class: "chip", text: String(items.length) }) : null),
      items.length ? h("ul", { class: "list" }, items) : h("div", { class: `empty${good ? " good" : ""}`, text: emptyText }));
  }

  function renderBacklog(cur) {
    const b = data.backlog || {};
    const issues = b.issues || {};
    const order = ["expedite", "current", "standard", "intangible", "change"];
    const queued = order.flatMap((c) => ((b.queue || {})[c] || []).map((id) => ({ id, c, ...issues[id] })));
    const scheduled = Object.entries(issues).filter(([, v]) => ["scheduled", "in_progress"].includes(v.status));
    const curIdx = data.milestones.findIndex((m) => m.id === cur);
    const future = data.milestones.slice(curIdx + 1).flatMap((m) => tasksOf(m).filter((t) => t.status !== "done"));
    $("pb-sub").textContent = `${queued.length} queued issues · ${future.length} tasks in later sprints`;
    const issueLi = (i) => h("li", {}, h("span", { class: "id", text: i.id }), h("span", { text: i.title || "" }),
      h("span", { class: `chip${i.c === "expedite" ? " lane-hotfix" : ""}`, text: i.c || i.status }),
      h("span", { class: "sub", text: [i.type, i.severity, i.scheduled_in ? `→ ${i.scheduled_in}` : null].filter(Boolean).join(" · ") }));
    const buf = b.buffer;
    fill($("product-backlog"),
      listBlock("Issue queue", queued.map(issueLi), "No issues waiting.", true),
      scheduled.length ? listBlock("Scheduled", scheduled.map(([id, v]) => issueLi({ id, c: v.class, ...v })), "") : null,
      buf ? h("div", {}, h("div", { class: "list-title", text: `Buffer of ${buf.milestone}` }),
        h("div", { class: "score", text: `${buf.used}/${buf.capacity} slots used (${buf.pct}%)` }),
        (() => { const mm = h("div", { class: "meter" }); const sp = h("span"); sp.style.width = `${Math.min(100, buf.capacity ? (buf.used / buf.capacity) * 100 : 0)}%`; mm.append(sp); return mm; })()) : null,
      listBlock("Later sprints", future.slice(0, 8).map((t) => h("li", {}, h("span", { class: "id", text: t.id }), h("span", { text: t.title }),
        h("span", { class: "chip", text: t.milestone }))), "Nothing planned after this sprint."),
      future.length > 8 ? h("div", { class: "card-sub", text: `+ ${future.length - 8} more` }) : null);
  }

  function renderImpediments() {
    const blocked = Object.entries(data.tasks).filter(([, t]) => t.status === "blocked");
    fill($("impediments"),
      listBlock("Blocked tasks", blocked.map(([id, t]) => h("li", {}, h("span", { class: "id", text: id }), h("span", { text: t.title }),
        h("span", { class: "chip", text: t.milestone }), h("span", { class: "sub", text: t.blocked_reason || "no reason recorded" }))), "Nothing is blocked.", true),
      listBlock("Open questions", data.questions.map((q) => h("li", {}, h("span", { class: "id", text: q.id }), h("span", { text: q.question }),
        h("span", { class: "chip", text: q.by || "?" }), q.assumption ? h("span", { class: "sub", text: `Assumed: ${q.assumption}` }) : null)),
        "No open questions.", true),
      ((data.backlog || {}).warnings || []).length ? listBlock("Warnings", data.backlog.warnings.map((w) => h("li", {}, h("span", { class: "id", text: "!" }), h("span", { text: w }))), "") : null,
      data.questions.length || blocked.length ? h("p", { class: "card-sub" }, "Resolve with ", h("code", { text: "/dev-kit:interview --gaps" })) : null);
  }

  function dodRow(name, score, cut, verdict) {
    const mm = h("div", { class: "meter" });
    const sp = h("span"); sp.style.width = `${score != null ? Math.min(100, score) : 0}%`;
    const c = h("span", { class: "cut", title: `cut-off ${cut}` }); c.style.left = `calc(${cut}% - 1px)`;
    mm.append(sp, c);
    const ok = verdict === "pass" || verdict === "passed" || verdict === "skipped" || verdict === "n/a";
    const bad = verdict === "fail" || (score != null && score < cut && !ok);
    return h("div", { class: "dod-row" }, h("span", { class: "name" }, name, " ",
      h("span", { class: `badge ${ok ? "good" : bad ? "bad" : "neutral"}`, text: ok ? `✓ ${verdict}` : bad ? "✕ below cut-off" : verdict || "pending" })),
      h("span", { class: "score", text: score != null ? `${score} / ${cut}` : `— / ${cut}` }), mm);
  }

  function renderDoD() {
    const q = data.quality;
    $("dod-sub").textContent = `Gate cut-off ${q.min_overall} · reviews ${q.review_min_overall}`;
    const revs = ["prd", "design", "plan", "ux", "docs"].map((k) => [k, data.reviews[k] || {}]);
    const extra = Object.entries(data.reviews).filter(([k]) => !["prd", "design", "plan", "ux", "docs"].includes(k));
    fill($("dod"),
      h("div", {}, h("div", { class: "list-title", text: "Reviews" }), h("div", { class: "list" },
        [...revs, ...extra].map(([k, v]) => dodRow(k.toUpperCase().length <= 3 ? k.toUpperCase() : k[0].toUpperCase() + k.slice(1), v.score ?? null, k === "ux" ? q.min_overall : q.review_min_overall, v.verdict)))),
      h("div", {}, h("div", { class: "list-title", text: "Milestone gates" }), h("div", { class: "list" },
        data.milestones.length ? data.milestones.map((m) => dodRow(`${m.id} ${m.title || ""}`, m.score ?? null, q.min_overall, m.gate === "pending" ? (m.score != null ? "fail" : "pending") : m.gate))
          : h("div", { class: "empty", text: "No milestones yet." }))));
  }

  function renderFeed() {
    fill($("feed"), data.log.length ? data.log.map((r) => h("li", {}, h("time", { datetime: r.at, text: Number.isFinite(parseT(r.at)) ? fmtDT(parseT(r.at)) : r.at }),
      h("span", { class: "txt", text: r.text }))) : h("li", {}, h("span", { class: "txt", text: "No activity logged yet." })));
    const b = data.board;
    fill($("foot"), `Read-only view of ${data.project}/.dev · phase ${data.phase} · autonomy ${data.autonomy || "?"}`,
      b ? ` · server pid ${b.pid} on port ${b.port}` : "", " · stop it here or with ", h("code", { text: "/dev-kit:board stop" }));
  }

  // ------------------------------------------------------------------ execution graph (DAG of the milestone)
  const GW = 176, GH = 46, GX = 72, GY = 52, GPAD = 34;
  const store = { get(k, d) { try { return localStorage.getItem(k) || d; } catch (e) { return d; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } } };
  let view = store.get("board-view", "graph") === "kanban" ? "kanban" : "graph", gmode = "actual", gdata = null, gseq = 0;
  const STCOL = { done: "var(--good)", in_progress: "var(--warning)", blocked: "var(--critical)", todo: "var(--todo)", pending: "var(--todo)", passed: "var(--good)", skipped: "var(--todo)" };

  function segSwitch(label, opts, cur, onPick) {
    return h("div", { class: "seg-switch", role: "group", "aria-label": label },
      opts.map(([k, text]) => h("button", { type: "button", class: `seg-btn${cur === k ? " on" : ""}`, "aria-pressed": String(cur === k), text, onclick: () => onPick(k) })));
  }
  function renderBoardView(m) {
    const tools = [segSwitch("View", [["graph", "Graph"], ["kanban", "Kanban"]], view, (k) => { view = k; store.set("board-view", k); renderBoardView(currentMilestone()); renderAgents(); })];
    if (view === "graph") tools.push(segSwitch("Graph mode", [["actual", "Actual"], ["planned", "Planned"]], gmode, (k) => { gmode = k; drawGraph(); renderBoardView(currentMilestone()); }));
    fill($("board-tools"), tools);
    $("kanban").hidden = view !== "kanban";
    $("graph").hidden = view !== "graph";
    if (view === "graph" && m) loadGraph(m.id);
  }
  const currentMilestone = () => (data && data.milestones.find((x) => x.id === currentId())) || null;

  async function loadGraph(mid) {
    const my = ++gseq;
    try {
      const r = await fetch(`/api/graph?m=${encodeURIComponent(mid)}`, { cache: "no-store" });
      const g = await r.json();
      if (my !== gseq) return;
      gdata = g.ok ? g : null;
    } catch (e) { if (my !== gseq) return; gdata = null; }
    drawGraph();
  }

  function layoutGraph(g) {
    const planned = gmode === "planned";
    const nodes = g.nodes.filter((n) => (planned ? n.planned && n.id !== "GATE" || n.id === "GATE" : true));
    const ids = new Set(nodes.map((n) => n.id));
    const edges = g.edges.filter((e) => ids.has(e.from) && ids.has(e.to) && (planned ? e.kind === "planned" || e.kind === "removed" : e.kind !== "removed"));
    const dep = edges.filter((e) => e.kind !== "fix" && e.to !== "GATE" && e.from !== "GATE");
    const layer = {};
    const preds = (id) => dep.filter((e) => e.to === id).map((e) => e.from);
    const lay = (id, seen = new Set()) => {
      if (layer[id] !== undefined) return layer[id];
      if (seen.has(id)) return 0; seen.add(id);
      layer[id] = preds(id).reduce((mx, p) => Math.max(mx, lay(p, seen) + 1), 0);
      return layer[id];
    };
    const fixes = new Set(g.edges.filter((e) => e.kind === "fix" && e.from === "GATE" && ids.has(e.to)).map((e) => e.to));
    nodes.forEach((n) => { if (n.id !== "GATE" && !fixes.has(n.id)) lay(n.id); });
    const maxL = Math.max(0, ...Object.values(layer));
    fixes.forEach((f) => { layer[f] = maxL; });
    layer.GATE = maxL + 1;
    const cols = {};
    nodes.forEach((n) => { (cols[layer[n.id]] = cols[layer[n.id]] || []).push(n); });
    const pos = {}, rowOf = {};
    let rowsMax = 1;
    Object.keys(cols).map(Number).sort((a, b) => a - b).forEach((l) => {
      const list = cols[l];
      if (+l === layer.GATE) return;
      const bary = (n) => { const ys = preds(n.id).map((p) => rowOf[p]).filter((v) => v !== undefined); return ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : Infinity; };
      list.sort((a, b) => (fixes.has(a.id) - fixes.has(b.id)) || (bary(a) - bary(b)) || (parseInt(a.id.slice(2)) - parseInt(b.id.slice(2))));
      list.forEach((n, i) => { rowOf[n.id] = i; pos[n.id] = { x: GPAD + l * (GW + GX), y: GPAD + 24 + i * (GH + GY) }; });
      rowsMax = Math.max(rowsMax, list.length);
    });
    const midY = GPAD + 24 + ((rowsMax - 1) * (GH + GY)) / 2;
    pos.GATE = { x: GPAD + layer.GATE * (GW + GX), y: midY };
    return { nodes, edges, pos, fixes, layer, width: GPAD * 2 + (layer.GATE + 1) * (GW + GX) - GX, height: GPAD * 2 + 24 + rowsMax * (GH + GY) + 40, planned };
  }

  function groupLoops(g, id) {
    const by = {};
    g.loops.filter((l) => l.task === id).forEach((l) => { (by[l.kind] = by[l.kind] || []).push(l); });
    return Object.entries(by).map(([kind, list]) => ({ kind, list }));
  }
  const LOOPTXT = { block: "blocked", restart: "retry", gate: "gate failed" };

  function drawGraph() {
    const box = $("graph");
    if (!gdata) { fill(box, h("div", { class: "empty", text: "No graph available for this milestone." })); return; }
    const g = gdata, L = layoutGraph(g);
    const parGroups = g.parallel.map((grp, i) => ({ grp, tag: String.fromCharCode(65 + i) }));
    const parOf = {}; parGroups.forEach((p) => p.grp.forEach((id) => { parOf[id] = p; }));
    const svg = s("svg", { class: "gsvg", width: L.width, height: L.height, viewBox: `0 0 ${L.width} ${L.height}`, role: "img",
      "aria-label": `Execution graph of ${g.milestone}: ${L.nodes.length} nodes` });
    // arrowheads are drawn explicitly (a small triangle at the end of each edge), so direction shows in any renderer
    const head = (tx, ty, fx, fy, cls) => {
      const a = Math.atan2(ty - fy, tx - fx), L1 = 9, W = 4.5;
      const bx = tx - Math.cos(a) * L1, by = ty - Math.sin(a) * L1, px = -Math.sin(a) * W, py = Math.cos(a) * W;
      svg.append(s("path", { d: `M${tx} ${ty} L${bx + px} ${by + py} L${bx - px} ${by - py} Z`, class: `ghead ${cls}` }));
    };
    const P = (id) => L.pos[id];
    let bottom = L.height;
    // dependency edges
    L.edges.forEach((e) => {
      const a = P(e.from), b = P(e.to);
      if (!a || !b) return;
      if (e.kind === "fix") {
        if (e.from === "GATE") {  // back edge below the nodes: the gate sends work to the fix task
          const y = Math.max(a.y, b.y) + GH + 30;
          svg.append(s("path", { d: `M${a.x + GW / 2} ${a.y + GH} C${a.x + GW / 2} ${y} ${b.x + GW / 2} ${y} ${b.x + GW / 2} ${b.y + GH}`, class: "gedge fix" }));
          head(b.x + GW / 2, b.y + GH, b.x + GW / 2, y, "fix");
        } else {
          const x1 = a.x + GW, y1 = a.y + GH / 2, x2 = b.x, y2 = b.y + GH / 2, dx = (x2 - x1) / 2;
          svg.append(s("path", { d: `M${x1} ${y1} C${x1 + dx} ${y1} ${x2 - dx} ${y2} ${x2} ${y2}`, class: "gedge fix" }));
          head(x2, y2, x2 - dx, y2, "fix");
        }
        return;
      }
      const x1 = a.x + GW, y1 = a.y + GH / 2, x2 = b.x, y2 = b.y + GH / 2, dx = Math.max(24, (x2 - x1) / 2);
      // an edge that skips columns arches over the nodes in between instead of running behind them
      const arch = L.layer[e.to] - L.layer[e.from] > 1 ? Math.min(y1, y2) - GH * 1.4 : null;
      const cy1 = arch === null ? y1 : arch, cy2 = arch === null ? y2 : arch;
      svg.append(s("path", { d: `M${x1} ${y1} C${x1 + dx} ${cy1} ${x2 - dx} ${cy2} ${x2} ${y2}`, class: `gedge ${e.kind}` }));
      head(x2, y2, x2 - dx, cy2, e.kind);
    });
    // nodes
    L.nodes.forEach((n) => {
      const p = P(n.id); if (!p) return;
      const st = L.planned ? "todo" : n.status;
      const dur = n.intervals.reduce((sum, [a, b]) => sum + ((b ? parseT(b) : Date.now()) - parseT(a)), 0) / 1000;
      const label = n.id === "GATE" ? `QA gate${!L.planned && n.score != null ? ` · ${n.score}` : ""}` : n.id;
      const title = (n.title || "").length > 24 ? n.title.slice(0, 23) + "…" : n.title || "";
      const par = L.planned ? null : parOf[n.id];
      const here = L.planned ? [] : agentsOn(n.id === "GATE" ? `GATE:${g.milestone}` : n.id);
      const gEl = s("g", { class: `gnode${n.external ? " ext" : ""}${n.added && !L.planned ? " added" : ""}${n.id === "GATE" ? " gate" : ""}`, transform: `translate(${p.x} ${p.y})`, tabindex: "0",
        role: "img", "aria-label": `${n.id} ${n.title || ""}, ${String(n.status).replace("_", " ")}${n.attempts > 1 ? `, ${n.attempts} attempts` : ""}${par ? `, parallel group ${par.tag}` : ""}${here.length ? `, agents running: ${here.map((x) => x.agent).join(", ")}` : ""}` },
        s("rect", { class: "gbox", width: GW, height: GH, rx: 9 }),
        s("rect", { class: "gbar", width: 5, height: GH - 12, x: 0, y: 6, rx: 2.5, style: `fill:${STCOL[st] || STCOL.todo}` }),
        s("text", { class: "gid", x: 14, y: 19, text: label + (n.external ? ` · ${n.milestone}` : "") }),
        s("text", { class: "gtitle", x: 14, y: 36, text: title }));
      if (!L.planned && n.attempts > 1) gEl.append(s("text", { class: "gbadge", x: GW - 8, y: 17, "text-anchor": "end", text: `×${n.attempts}` }));
      if (par) gEl.append(s("text", { class: "gpar", x: GW - 8, y: 36, "text-anchor": "end", text: `∥${par.tag}` }));
      const tip = (evt) => {
        const rows = [[String(n.status).replace("_", " "), "status"]];
        if (n.id !== "GATE") rows.push([String(n.attempts), n.attempts === 1 ? "attempt" : "attempts"], [String(n.blocks), "blocks"]);
        if (dur > 0) rows.push([fmtDur(dur), "executing"]);
        if (n.id === "GATE") rows.push([String(n.qa_runs || 0), "QA runs"]);
        if (par) rows.push([`∥${par.tag}`, `with ${par.grp.filter((x) => x !== n.id).join(", ")}`]);
        here.forEach((x) => rows.push([x.agent, `running ${fmtDur((Date.now() - parseT(x.started_at)) / 1000)}`]));
        (n.agents_done || []).slice(-5).forEach((x) => rows.push([x.agent, [x.status || "done", x.duration_s != null ? fmtDur(x.duration_s) : null,
          x.findings != null ? `${x.findings} findings` : null].filter(Boolean).join(" · ")]));
        n.history.slice(-8).forEach(([at, tr]) => rows.push([tr, Number.isFinite(parseT(at)) ? fmtDT(parseT(at)) : at]));
        showTip(evt, `${n.id}${n.title ? ` · ${n.title}` : ""}`, rows);
      };
      ["pointermove", "focus"].forEach((ev) => gEl.addEventListener(ev, tip));
      ["pointerleave", "blur"].forEach((ev) => gEl.addEventListener(ev, hideTip));
      svg.append(gEl);
      // running agents on this node: pills under the box (max 3, then +N)
      // stacked under the node: the gate is alone in its column, so it shows more rows (parallel auditors)
      const rows = n.id === "GATE" ? 6 : 2, BH = 17, BG = 3;
      const list = here.length > rows ? here.slice(0, rows - 1) : here;
      list.forEach((x, k) => {
        const dur = shortDur((Date.now() - parseT(x.started_at)) / 1000);
        const w = Math.min(GW, 30 + x.agent.length * 6.3 + 34);
        svg.append(s("g", { class: "gagent", transform: `translate(${p.x} ${p.y + GH + 5 + k * (BH + BG)})` },
          s("rect", { width: w, height: BH, rx: BH / 2 }),
          s("circle", { class: "agent-dot", cx: 9, cy: BH / 2, r: 3.5 }),
          s("text", { class: "gagent-name", x: 17, y: 12.5, text: x.agent }),
          s("text", { class: "agent-time gagent-time", x: w - 8, y: 12.5, "text-anchor": "end", "data-start": x.started_at, "data-short": "1", text: dur })));
      });
      bottom = Math.max(bottom, p.y + GH + 5 + (list.length + (here.length > list.length ? 1 : 0)) * (BH + BG) + 16);
      if (here.length > list.length) svg.append(s("text", { class: "gagent-more", x: p.x + 6, y: p.y + GH + 5 + list.length * (BH + BG) + 12.5,
        text: `+${here.length - list.length} more` }));
      // failure loops: leave the top of the node and re-enter it
      if (!L.planned) groupLoops(g, n.id).forEach(({ kind, list }, i) => {
        const x1 = p.x + GW * 0.2 + i * 7, x2 = p.x + GW * 0.5 + i * 7, y = p.y, hgt = 16 + i * 9;
        svg.append(s("path", { d: `M${x1} ${y} C${x1 - 4} ${y - hgt} ${x2 + 4} ${y - hgt} ${x2} ${y - 1}`, class: "gedge loop" }));
        head(x2, y - 1, x2 + 4, y - hgt, "loop");
        const last = list[list.length - 1];
        svg.append(s("text", { class: "gloop", x: p.x + GW * 0.5 + 18, y: y - 5 - i * 12, "text-anchor": "start",
          text: `${LOOPTXT[kind] || kind}${list.length > 1 ? ` ×${list.length}` : ""}${kind === "gate" && last.score != null ? ` · ${last.score}` : ""}` }));
      });
    });
    const note = [];
    if (!g.baseline) note.push(h("p", { class: "gnote", text: "No baseline recorded for this project yet: the initial plan is taken from the next sync-plan, so Planned shows the current plan." }));
    const legend = h("ul", { class: "glegend", "aria-label": "Legend" },
      [["done", "Done"], ["in_progress", "In progress"], ["blocked", "Blocked"], ["todo", "To do"]].map(([k, t]) => h("li", {}, h("span", { class: `swatch st-${k}`, "aria-hidden": "true" }), t)),
      h("li", {}, h("span", { class: "lg-line loop", "aria-hidden": "true" }), "Failure loop (block, retry, failed gate)"),
      h("li", {}, h("span", { class: "lg-line added", "aria-hidden": "true" }), "Added after the plan"),
      h("li", {}, h("span", { class: "agent-dot", "aria-hidden": "true" }), (data.agents && data.agents.hooks) ? "Agent running" : "Agent running (agents outside dev-kit skills need plugin hooks)"),
      parGroups.length ? h("li", {}, "∥ " + parGroups.map((p) => `${p.tag}: ${p.grp.join(", ")}`).join(" · ")) : h("li", { text: "No parallel execution yet" }));
    const rows = g.nodes.filter((n) => n.id !== "GATE").map((n) => {
      const deps = g.edges.filter((e) => e.to === n.id && e.kind !== "removed").map((e) => e.from).join(", ");
      return h("tr", {}, h("td", { text: n.id }), h("td", { text: n.title || "" }), h("td", { text: String(n.status).replace("_", " ") }), h("td", { text: deps || "—" }),
        h("td", { text: String(n.attempts) }), h("td", { text: String(n.blocks) }));
    });
    if (bottom > L.height) { svg.setAttribute("height", bottom); svg.setAttribute("viewBox", `0 0 ${L.width} ${bottom}`); }
    renderAgents();
    fill(box, note, legend, h("div", { class: "graph-scroll", tabindex: "0", role: "region", "aria-label": "Execution graph (scrollable)" }, svg),
      h("details", { class: "table-view" }, h("summary", { text: "Show as table" }),
        h("table", { class: "gtable" }, h("thead", {}, h("tr", {}, ["Task", "Title", "Status", "Depends on", "Attempts", "Blocks"].map((c) => h("th", { text: c })))), h("tbody", {}, rows))));
  }

  // ------------------------------------------------------------------ agents (fed by plugin hooks)
  function fmtDur(sec) {
    sec = Math.max(0, Math.round(sec));
    return sec < 60 ? `${sec} s` : sec < 3600 ? `${Math.floor(sec / 60)} min ${sec % 60} s` : `${Math.floor(sec / 3600)} h ${Math.floor((sec % 3600) / 60)} min`;
  }
  const activeAgents = () => ((data && data.agents && data.agents.active) || []);
  const agentsOn = (key) => activeAgents().filter((x) => x.node === key);
  function renderAgents() {
    // agents placed on a visible graph node are shown there; the strip keeps the rest
    const onGraph = new Set();
    if (view === "graph" && gdata) gdata.nodes.forEach((n) => onGraph.add(n.id === "GATE" ? `GATE:${gdata.milestone}` : n.id));
    const loose = activeAgents().filter((x) => !x.node || !onGraph.has(x.node));
    $("agents-card").hidden = loose.length === 0;
    fill($("agents"), loose.map((x) => h("span", { class: "agent-chip" },
      h("span", { class: "agent-dot", "aria-hidden": "true" }),
      h("span", { class: "agent-name", text: x.agent }),
      x.node ? h("span", { class: "agent-node", text: x.node.replace("GATE:", "QA ") }) : null,
      h("span", { class: "agent-time", "data-start": x.started_at, text: fmtDur((Date.now() - parseT(x.started_at)) / 1000) }))));
  }
  function shortDur(sec) {
    sec = Math.max(0, Math.round(sec));
    return sec < 60 ? `${sec}s` : sec < 3600 ? `${Math.floor(sec / 60)}m` : `${Math.floor(sec / 3600)}h${Math.floor((sec % 3600) / 60)}m`;
  }
  function tickAgents() {
    document.querySelectorAll(".agent-time[data-start]").forEach((el) => {
      const sec = (Date.now() - parseT(el.dataset.start)) / 1000;
      el.textContent = el.dataset.short ? shortDur(sec) : fmtDur(sec);
    });
  }
  setInterval(tickAgents, 1000);

  // ------------------------------------------------------------------ main render + data flow
  function render() {
    if (!data) return;
    const banner = $("banner");
    if (!data.ok) {
      banner.hidden = false; banner.textContent = data.message || "Could not read the project state.";
      return;
    }
    banner.hidden = true;
    const curId = currentId();
    const m = data.milestones.find((x) => x.id === curId) || null;
    renderHeader(); renderTabs(); renderHero(m); renderTiles(m); renderAgents(); renderKanban(m); renderBoardView(m);
    renderBurndown(m); renderVelocity(curId); renderBacklog(curId); renderImpediments(); renderDoD(); renderFeed();
    $("main").setAttribute("aria-busy", "false");
  }

  async function load() {
    if (stopped) return;
    if (loading) { pending = true; return; }
    loading = true;
    try {
      const r = await fetch("/api/state", { cache: "no-store" });
      const next = await r.json();
      if (next.ok || !data) data = next;
      else if (!next.ok && next.error === "corrupt_state") { /* mid-write: keep the previous frame */ }
      else data = next;
      lastUpdate = Date.now();
      render();
      tickUpdated();
    } catch (e) {
      setLive("off", "Offline");
    } finally {
      loading = false;
      if (pending) { pending = false; setTimeout(load, 150); }
    }
  }

  function setLive(state, text) {
    const el = $("live");
    el.className = `live ${state}`;
    $("live-text").textContent = text;
  }
  function tickUpdated() { $("updated").textContent = lastUpdate ? `updated ${ago(lastUpdate)}` : ""; }

  function connect() {
    if (stopped) return;
    es = new EventSource("/api/events");
    es.addEventListener("hello", () => { setLive("on", "Live"); $("banner").hidden = !(data && !data.ok); load(); });
    es.addEventListener("change", () => load());
    es.addEventListener("bye", () => { es.close(); showStopped(); });
    es.onerror = () => {
      if (stopped) return;
      setLive("off", "Reconnecting…");
      const b = $("banner"); b.hidden = false; b.textContent = "The board server is not answering. Reconnecting… (start it again with /dev-kit:board)";
    };
  }

  function showStopped() {
    stopped = true;
    if (es) es.close();
    setLive("off", "Stopped");
    $("stopped").hidden = false;
    document.title = "Board stopped · dev-kit";
  }

  // ------------------------------------------------------------------ stop server
  const dlg = $("stop-dialog");
  $("stop-btn").addEventListener("click", () => (dlg.showModal ? dlg.showModal() : confirm("Stop the board server?") && stopServer()));
  dlg.addEventListener("close", () => { if (dlg.returnValue === "stop") stopServer(); });
  async function stopServer() {
    const btn = $("stop-btn");
    btn.disabled = true;
    try {
      const r = await fetch("/api/shutdown", { method: "POST", headers: { "X-Board-Token": TOKEN } });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      showStopped();
    } catch (e) {
      btn.disabled = false;
      const b = $("banner"); b.hidden = false; b.textContent = `Could not stop the server (${e.message}). Use /dev-kit:board stop.`;
    }
  }

  // tabs: arrow keys move between sprints
  $("tabs").addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key) || !data) return;
    const ids = data.milestones.map((m) => m.id);
    let i = ids.indexOf(currentId());
    i = e.key === "Home" ? 0 : e.key === "End" ? ids.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + ids.length) % ids.length;
    selected = ids[i]; render(); $(`tab-${ids[i]}`).focus(); e.preventDefault();
  });

  let resizeT = null;
  let lastW = window.innerWidth;
  window.addEventListener("resize", () => {
    if (window.innerWidth === lastW) return;
    lastW = window.innerWidth;
    clearTimeout(resizeT);
    resizeT = setTimeout(render, 150);
  });

  setInterval(tickUpdated, 1000);
  load();
  connect();
})();
