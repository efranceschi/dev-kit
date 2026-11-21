/* dev-kit board - live view of .dev/state.json: milestone window, what needs the user, the stages of the milestone with what runs in each, the milestone kanban, insights; with actions on, requests to Claude Code (run a command, answer a question, new issue, a plan draft made by dragging cards) queued through the server and run by /dev-kit:worker. No dependencies. All untrusted text goes through textContent. */
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
  // project lifecycle (conventions.md §19): conception -> planning -> construction -> stable, as a cycle
  const PHASE_NAME = { conception: "Conception", planning: "Planning", construction: "Construction", stable: "Stable" };
  const PHASE_WORD = { done: "done", current: "current phase", active: "still running", upcoming: "not started" };
  const STEP_NAME = { interview: "interview", prd: "PRD", architecture: "architecture", ux: "UX", ui: "UI", plan: "plan",
    milestones: "milestones", release: "release" };
  const STEP_WORD = { todo: "to do", doing: "in progress", stale: "out of date", review: "waiting for its review", done: "done", skipped: "skipped" };
  const STEP_MARK = { todo: "○", doing: "◐", stale: "↻", review: "◐", done: "✓", skipped: "–" };
  const PHASES = ["conception", "planning", "construction", "stable"];
  const STEP_TITLE = { interview: "Interview", prd: "PRD", architecture: "Architecture", ux: "UX", ui: "UI", plan: "Plan" };
  const STEP_ABOUT = { interview: "Requirements interview, written to brief.md", prd: "Product requirements with numbered acceptance criteria",
    architecture: "Stack, data model, contracts and ADRs", ux: "Journeys, screens and every screen state", ui: "Design tokens, components and screen specs",
    plan: "Milestones of small tasks, with dependencies" };
  const STEP_CMD = { interview: "/dev-kit:interview", prd: "/dev-kit:prd", architecture: "/dev-kit:architecture", ux: "/dev-kit:ux", ui: "/dev-kit:ui", plan: "/dev-kit:plan" };
  const STEP_REVIEW_CMD = { prd: "/dev-kit:review prd", ux: "/dev-kit:review design", ui: "/dev-kit:review design", plan: "/dev-kit:review plan" };
  const REVIEW_NAME = { prd: "PRD", design: "Design", plan: "Plan", ux: "Usability", docs: "Docs" };

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
  function gateBadge(m) {
    if (!m) return null;
    const x = qaState(m);
    const why = qaReason(x.qa, m);
    const last = x.qa.last;
    const title = last ? `Last QA run: overall ${last.overall} (cut-off ${last.cutoff}); ${why || "no dimension below its minimum"}`
      : `Cut-off ${data.quality.min_overall} overall · ${data.quality.min_dimension} per dimension`;
    let b;
    if (m.gate === "passed") b = h("span", { class: "badge good" }, "✓ Gate passed" + (m.score != null ? ` · ${m.score}` : "") + (x.qa.runs > 1 ? ` in round ${x.qa.runs}` : ""));
    else if (m.gate === "skipped") b = h("span", { class: "badge neutral" }, "Gate skipped");
    else if (x.running) b = h("span", { class: "badge warn" }, `◌ QA round ${x.round} running`);
    else if (x.exhausted) b = h("span", { class: "badge bad" }, `✕ ${x.qa.runs} QA rounds failed · needs your decision`);
    else if (x.qa.runs) b = h("span", { class: "badge bad" }, `✕ Round ${x.qa.runs} failed` + (why ? ` · ${why.length > 44 ? why.slice(0, 43) + "…" : why}` : ""));
    else if (x.ts.length && !x.buildOpen.length) {
      // every task is done and no QA round ran yet: say what the gate waits for, not just "pending"
      b = h("span", { class: "badge warn" }, "◌ Waiting for QA");
      b.title = `All tasks of ${m.id} are done; the QA gate has not run yet. It runs with /dev-kit:qa ${m.id} (▶ on the board queues it; autopilot or /dev-kit:worker runs it). ${title}`;
      return b;
    } else {
      b = h("span", { class: "badge neutral" }, "Gate after the build");
      b.title = `The QA gate runs once every task of ${m.id} is done. ${title}`;
      return b;
    }
    b.title = title;
    return b;
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

  const store = { get(k, d) { try { return localStorage.getItem(k) || d; } catch (e) { return d; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } } };
  const TASK_RE = /^T-\d{1,5}$/;
  const INS = ["burndown", "velocity", "gates"];
  const COL_LIMIT = 3;       // cards shown per kanban column before "Show all"
  let query = "";            // text filter of the kanban
  let typeFilter = "";       // task type filter of the kanban
  let expanded = new Set();  // kanban columns showing every card
  let mobileCol = null;      // column shown on narrow screens (null = pick the most useful one)
  let goalOpen = false;      // milestone goal expanded
  // construction: one card, one row of tabs - the task board and the insights (the plan view lives in Planning)
  const VIEWS = ["tasks", ...INS];
  const VIEW_KEY = "board-view-v2";
  // the phase shown: null follows the project's phase; a phase picked by the user stays until "Back to the current phase"
  const PHASE_KEY = "board-phase-v1";
  let phasePick = PHASES.includes(store.get(PHASE_KEY, "")) ? store.get(PHASE_KEY, "") : null;
  const shownPhase = () => (phasePick && PHASES.includes(phasePick) ? phasePick : (data && data.phase) || "conception");
  let needsBy = {};          // items of "Needs you" per phase, shown on the phase tabs
  let view = VIEWS.includes(store.get(VIEW_KEY, "")) ? store.get(VIEW_KEY, "") : "tasks";
  let firstRender = true;

  const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;
  const stLabel = (x) => String(x || "").replace("_", " ");
  function dur(sec) {
    sec = Math.max(0, Math.round(sec));
    return sec < 60 ? `${sec}s` : sec < 3600 ? `${Math.floor(sec / 60)}m` : `${Math.floor(sec / 3600)}h${String(Math.floor((sec % 3600) / 60)).padStart(2, "0")}m`;
  }
  function agoShort(t) {
    const sec = Math.max(0, Math.round((Date.now() - t) / 1000));
    return sec < 60 ? "now" : sec < 3600 ? `${Math.floor(sec / 60)}m ago` : sec < 86400 ? `${Math.floor(sec / 3600)}h ago` : sec < 7 * 86400 ? `${Math.floor(sec / 86400)}d ago` : fmtDate(t);
  }
  const activeAgents = () => ((data && data.agents && data.agents.active) || []);
  const agentsOn = (key) => activeAgents().filter((x) => x.node === key);
  const roleOf = (name) => ((data && data.agent_roles) || {})[name] || {};
  const AGENT_COLORS = ["red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"];  // same names as Claude Code
  const agentDot = (name) => { const c = roleOf(name).color; return "agent-dot" + (AGENT_COLORS.includes(c) ? ` ag-${c}` : ""); };
  const agentBits = (x, withRole) => [h("span", { class: agentDot(x.agent), "aria-hidden": "true" }),
    h("span", { class: "agent-name", text: x.agent, title: roleOf(x.agent).about || null }),
    withRole && roleOf(x.agent).role ? h("span", { class: "agent-role", text: roleOf(x.agent).role }) : null,
    h("span", { class: "agent-time", "data-start": x.started_at, text: dur((Date.now() - parseT(x.started_at)) / 1000) })].filter(Boolean);
  /** Task ids inside free text become buttons that open the task; everything else stays text. */
  function linkify(text) {
    return String(text || "").split(/\b(T-\d{1,5})\b/).map((part) => (TASK_RE.test(part) && data.tasks[part]
      ? h("button", { type: "button", class: "tid-btn", text: part, title: data.tasks[part].title, onclick: () => openTask(part) }) : part));
  }
  // ------------------------------------------------------------------ commands the user pastes into Claude Code: always with a copy button
  const COPY_ICON = "M9 9h10v12H9zM5 15V3h10";
  const copySvg = () => s("svg", { viewBox: "0 0 24 24", width: "14", height: "14", "aria-hidden": "true" },
    s("path", { d: COPY_ICON, fill: "none", stroke: "currentColor", "stroke-width": "2", "stroke-linejoin": "round" }));
  async function copyText(text) {
    try {
      if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return true; }
    } catch (e) { /* fall back below */ }
    // plain HTTP on the network (shared board) has no Clipboard API: use a temporary selection
    const ta = h("textarea", { class: "copy-buffer", readonly: true, "aria-hidden": "true", tabindex: "-1" });
    ta.value = text;
    document.body.append(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    ta.remove();
    return ok;
  }
  function copyBtn(text) {
    const label = `Copy ${text}`;
    const btn = h("button", { type: "button", class: "copy-btn", title: label, "aria-label": label }, copySvg());
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const ok = await copyText(text);
      btn.classList.toggle("copied", ok);
      btn.classList.toggle("copy-failed", !ok);
      fill(btn, ok ? "✓" : "✕");
      $("copy-status").textContent = ok ? `Copied ${text}. Paste it in Claude Code.` : `Could not copy. Select ${text} and copy it by hand.`;
      clearTimeout(btn._t);
      btn._t = setTimeout(() => { btn.classList.remove("copied", "copy-failed"); fill(btn, copySvg()); }, 1600);
    });
    return btn;
  }
  /** A command shown as code with its copy button and, when the board takes requests, a button that queues it. */
  const cmd = (text) => h("span", { class: "cmd" }, h("code", { text }), runnable(text) ? runBtn(text) : null, copyBtn(text));
  // static commands in index.html: <code data-copy>
  document.querySelectorAll("code[data-copy]").forEach((c) => {
    const wrap = h("span", { class: "cmd" });
    c.replaceWith(wrap);
    wrap.append(c, copyBtn(c.textContent));
  });

  function keepFocus(fn) {
    const a = document.activeElement;
    const tid = a && a.getAttribute && a.getAttribute("data-tid");
    const id = a && a.id;
    fn();
    if (!a || a.isConnected) return;
    const el = tid ? document.querySelector(`[data-tid="${tid}"]`) : id ? $(id) : null;
    if (el) el.focus({ preventScroll: true });
  }

  // ------------------------------------------------------------------ popovers (options, milestone lists) and theme
  const pops = [];
  function popover(btn, pop) {
    const close = () => { pop.hidden = true; btn.setAttribute("aria-expanded", "false"); };
    btn.addEventListener("click", () => {
      const open = pop.hidden;
      pops.forEach((p) => p.close());
      if (open) { pop.hidden = false; btn.setAttribute("aria-expanded", "true"); }
    });
    pops.push({ btn, pop, close });
  }
  popover($("menu-btn"), $("menu-pop"));
  popover($("run-btn"), $("run-pop"));
  popover($("tabs-earlier"), $("tabs-earlier-pop"));
  popover($("tabs-later"), $("tabs-later-pop"));
  document.addEventListener("click", (e) => pops.forEach((p) => { if (!p.pop.hidden && !p.pop.contains(e.target) && !p.btn.contains(e.target)) p.close(); }));
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    pops.forEach((p) => { if (!p.pop.hidden) { p.close(); p.btn.focus(); } });
  });

  // theme: "auto" follows the system; the top-bar button flips between light and dark, the menu can go back to auto
  const sysDark = matchMedia("(prefers-color-scheme: dark)");
  let themePref = store.get("board-theme", "auto");
  const effectiveTheme = () => (themePref === "light" || themePref === "dark" ? themePref : sysDark.matches ? "dark" : "light");
  function applyTheme() {
    const v = themePref === "light" || themePref === "dark" ? themePref : "auto";
    if (v === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", v);
    document.documentElement.dataset.effective = effectiveTheme();
    document.querySelectorAll("[data-theme-opt]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeOpt === v)));
    const next = effectiveTheme() === "dark" ? "light" : "dark";
    const label = `Switch to ${next} theme`;
    $("theme-btn").setAttribute("aria-label", label);
    $("theme-btn").title = label;
  }
  function setTheme(v) {
    themePref = v; store.set("board-theme", v); applyTheme();
    if (data && data.ok) render();  // charts read colours from CSS at draw time
  }
  applyTheme();
  sysDark.addEventListener("change", () => { if (themePref === "auto") { applyTheme(); if (data && data.ok) render(); } });
  $("theme-btn").addEventListener("click", () => setTheme(effectiveTheme() === "dark" ? "light" : "dark"));
  $("theme-switch").addEventListener("click", (e) => {
    const b = e.target.closest("[data-theme-opt]");
    if (b) setTheme(b.dataset.themeOpt);
  });

  // ------------------------------------------------------------------ header
  // ------------------------------------------------------------------ what Claude Code runs now: skills (outermost first) and agents
  const skillRuns = () => ((data && data.agents && data.agents.runs) || []);
  const runCmd = (r) => `/dev-kit:${r.skill}${r.scope ? ` ${r.scope}` : ""}`;
  const since = (t) => h("span", { class: "agent-time", "data-start": t, text: dur((Date.now() - parseT(t)) / 1000) });
  // Every skill that runs has a place on the board, so work that is not a task card is visible where it happens.
  // Orchestrators (autopilot, worker, start…) only show in the top bar; the work they start shows in its place.
  const RUN_PLACE = {
    interview: ["conception", "step:interview"], prd: ["conception", "step:prd"], architecture: ["conception", "step:architecture"],
    ux: ["conception", "step:ux"], ui: ["conception", "step:ui"], plan: ["planning", "step:plan"], issue: ["planning", "backlog"],
    qa: ["construction", "qa"], implement: ["construction", "tasks"], test: ["construction", "tasks"],
    usability: ["stable", "checks"], docs: ["stable", "checks"], release: ["construction", "release"], deploy: ["stable", "prod"],
  };
  const REVIEW_PLACE = { prd: ["conception", "step:prd"], design: ["conception", "step:ui"], plan: ["planning", "step:plan"], docs: ["stable", "checks"], ux: ["stable", "checks"] };
  function runPlace(r) {
    if (r.skill === "review") return REVIEW_PLACE[r.scope] || null;
    return RUN_PLACE[r.skill] || null;
  }
  /** Runs shown at a place (e.g. "step:prd", "checks"); the design review also lights the UX step. */
  const runsAt = (where) => skillRuns().filter((r) => { const p = runPlace(r); return p && (p[1] === where || (where === "step:ux" && p[1] === "step:ui" && r.skill === "review")); });
  const phaseRunning = (ph) => skillRuns().some((r) => { const p = runPlace(r); return p && p[0] === ph; });
  // which skills spawn each agent (agents/*.md and the skills that call them): an agent with no task or gate belongs to
  // the latest of those runs that started before it, or else to the latest run of any kind
  const AGENT_SKILLS = {
    "requirements-reviewer": ["review"], "design-reviewer": ["review"], "docs-reviewer": ["review", "docs", "release"],
    architect: ["architecture"], "usability-auditor": ["usability"], "a11y-auditor": ["usability", "qa"], "visual-reviewer": ["usability", "qa"],
    "copy-reviewer": ["usability", "qa"], "spec-tracer": ["qa", "release"], "security-auditor": ["qa", "release"], "ops-reviewer": ["qa", "release"],
    "deps-auditor": ["qa", "release"], "performance-auditor": ["qa", "release"], "data-reviewer": ["qa", "release"], "code-reviewer": ["qa"],
    "test-auditor": ["qa"], implementer: ["implement"],
  };
  function ownerRun(a) {
    const before = skillRuns().filter((r) => runPlace(r) && parseT(r.started_at) <= parseT(a.started_at) + 5000);
    const want = AGENT_SKILLS[a.agent] || [];
    const fit = before.filter((r) => want.includes(r.skill));
    const pick = (fit.length ? fit : before).sort((x, y) => parseT(x.started_at) - parseT(y.started_at));
    return pick[pick.length - 1] || null;
  }
  /** Agents not tied to a task card or a QA gate, working for one of these runs. */
  const looseAgents = (runs) => activeAgents().filter((a) => !a.node && runs.includes(ownerRun(a)));
  /** "● Running now" banner for a card: the command(s), for how long, and the agents working for it. */
  function runBanner(runs) {
    if (!runs.length) return null;
    const ags = looseAgents(runs);
    return h("div", { class: "run-banner", role: "status" },
      h("span", { class: "rn-dot", "aria-hidden": "true" }), h("strong", { text: "Running now" }),
      runs.map((r) => h("span", { class: "rb-cmd" }, h("code", { text: runCmd(r) }), " ", since(r.started_at))),
      ags.length ? h("span", { class: "rb-agents" }, ags.map((a) => h("span", { class: "agent-chip" }, agentBits(a, true)))) : null);
  }
  function fillRunSlot(id, where) { const el = $(id); if (el) fill(el, runBanner([].concat(...[].concat(where).map(runsAt)))); }

  function renderRunning() {
    const runs = skillRuns(), ags = activeAgents();
    const btn = $("run-btn");
    const nx = data.next && data.next.command;
    if (!runs.length && !ags.length) {
      btn.className = "run-now idle";
      fill(btn, h("span", { class: "rn-dot", "aria-hidden": "true" }), "Idle");
      btn.setAttribute("aria-label", "Nothing is running now");
      fill($("run-pop"), h("p", { class: "pop-title", text: "Nothing is running now" }),
        nx ? h("p", { class: "pop-note top" }, "Next step: ", cmd(nx)) : null,
        h("p", { class: "pop-note", text: "Skills and agents show here while Claude Code runs them (from the session log)." }));
      return;
    }
    const chain = runs.slice(-2).map(runCmd);
    btn.className = "run-now on";
    fill(btn, h("span", { class: "rn-dot", "aria-hidden": "true" }), h("span", { class: "rn-label", text: chain.length ? chain.join(" › ") : "agents" }),
      ags.length ? h("span", { class: "rn-count", text: plural(ags.length, "agent") }) : null,
      runs.length ? since(runs[0].started_at) : null);
    btn.setAttribute("aria-label", `Running now: ${runs.map(runCmd).join(", ") || "agents"}${ags.length ? `, ${plural(ags.length, "agent")}` : ""}. Show details`);
    fill($("run-pop"), h("p", { class: "pop-title", text: "Running now" }),
      runs.length ? h("ol", { class: "rn-list" }, runs.map((r, i) => h("li", { class: i ? "nested" : null },
        h("code", { text: runCmd(r) }), h("span", { class: "card-sub" }, " for ", since(r.started_at))))) : null,
      ags.length ? [h("p", { class: "pop-title", text: plural(ags.length, "agent") }), h("ul", { class: "rn-list" }, ags.map((a) => h("li", {},
        h("span", { class: "agent-chip" }, agentBits(a, true)),
        a.node ? (TASK_RE.test(a.node) ? h("button", { type: "button", class: "tid-btn", text: a.node, onclick: () => openTask(a.node) })
          : h("span", { class: "chip", text: a.node.replace("GATE:", "QA ") })) : h("span", { class: "card-sub", text: "not linked" }))))] : null,
      h("p", { class: "pop-note", text: "From the session log: a skill shows from its start until it ends." }));
  }

  function renderHeader() {
    $("project").textContent = data.project;
    renderRunning();
    $("kit-ver").textContent = data.kit && data.kit !== "unknown" ? `v${data.kit}` : "";
    $("bf-mode").textContent = data.brownfield ? `existing project · ${data.brownfield.mode || "feature"} · since ${data.brownfield.baseline_ref || "baseline"}` : "";
    renderLifecycle();
  }

  /** One short badge per phase (the details live inside the phase): steps done, the plan's state, milestones closed, releases. */
  function phaseBadge(p) {
    const st = p.steps || [];
    if (p.key === "conception") { const live = st.filter((x) => x.state !== "skipped"); return live.length ? `${live.filter((x) => x.state === "done").length}/${live.length}` : ""; }
    if (p.key === "planning") return st[0] ? STEP_WORD[st[0].state] : "";
    if (p.key === "construction") {
      const ms = st.find((x) => x.key === "milestones"), rel = st.find((x) => x.key === "release");
      const relWord = rel && rel.count ? (rel.state === "review" ? `${rel.count} awaits you` : /^R\d/.test(rel.count) ? null : `${rel.count} to release`) : null;
      return [ms && ms.count ? `${ms.count} closed` : null, relWord].filter(Boolean).join(" · ");
    }
    const n = (data.releases || []).length;
    return n ? plural(n, "release") : "";
  }
  const phaseTip = (p) => [`${PHASE_NAME[p.key]}: ${PHASE_WORD[p.state]}${p.reopened ? ", reopened" : ""}`,
    ...(p.steps || []).map((x) => `${STEP_NAME[x.key]}: ${STEP_WORD[x.state]}${x.note ? ` (${x.note})` : ""}`)].join("\n");

  /** The lifecycle bar is the page's top navigation: one tab per phase; the panel below shows only that phase. */
  function renderLifecycle() {
    const lc = data.cycle;
    const idx = lc.phases.findIndex((p) => p.key === data.phase);
    const cur = lc.phases[idx];
    const shown = shownPhase();
    // the sub-stage in progress, never a milestone id: the bar names only finite stages and sub-stages
    const sub = cur && cur.steps ? (cur.steps.find((x) => !["done", "skipped"].includes(x.state)) || null) : null;
    const step = sub ? STEP_NAME[sub.key] : "";
    $("phase-step").textContent = `Now: ${PHASE_NAME[data.phase]}${step ? ` · ${step}` : ""}`
      + (data.reopened ? " · reopened by a change, construction goes on" : "");
    $("phase-back").hidden = shown === data.phase;
    fill($("phases"), lc.phases.map((p, i) => {
      const sel = p.key === shown;
      const st = p.state === "active" ? "current" : p.state;
      const badge = phaseBadge(p);
      const need = needsBy[p.key] || 0;
      return h("button", { type: "button", role: "tab", id: `ph-${p.key}`, "aria-controls": `phase-${p.key}`, "aria-selected": String(sel), tabindex: sel ? "0" : "-1",
        class: `chev lc st-${st}${sel ? " here" : ""}${i === idx ? " now" : ""}${p.reopened ? " reopened" : ""}`, title: phaseTip(p),
        onclick: () => setPhase(p.key) },
      h("span", { class: "chev-ico", "aria-hidden": "true", text: p.state === "done" ? "✓" : p.key === "stable" ? "↻" : String(i + 1) }),
      h("span", { class: "lc-body" },
        h("span", { class: "chev-name" }, PHASE_NAME[p.key], p.reopened ? h("span", { class: "lc-tag", text: "reopened" }) : null,
          i === idx && !sel ? h("span", { class: "lc-tag now-tag", text: "now" }) : null),
        badge ? h("span", { class: "lc-badge", text: badge }) : null),
      phaseRunning(p.key) ? h("span", { class: "lc-run", title: `Running now in ${PHASE_NAME[p.key]}: ${skillRuns().filter((r) => (runPlace(r) || [])[0] === p.key).map(runCmd).join(", ")}` },
        h("span", { class: "rn-dot", "aria-hidden": "true" }), "running") : null,
      need ? h("span", { class: "lc-needs", title: `${plural(need, "item")} in Needs you`, text: String(need) }) : null,
      h("span", { class: "visually-hidden", text: `: ${PHASE_WORD[p.state]}${i === idx ? ", the project is here" : ""}${badge ? `, ${badge}` : ""}${need ? `, ${plural(need, "item")} need you` : ""}.` }));
    }));
  }
  function setPhase(p, focus) {
    phasePick = data && p === data.phase ? null : p;   // picking the current phase goes back to following it
    store.set(PHASE_KEY, phasePick || "");
    render();
    if (focus && $(`ph-${shownPhase()}`)) $(`ph-${shownPhase()}`).focus();
  }
  $("phase-back").addEventListener("click", () => setPhase(data.phase, true));
  $("phases").addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key) || !data || !data.ok) return;
    let i = PHASES.indexOf(shownPhase());
    i = e.key === "Home" ? 0 : e.key === "End" ? PHASES.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + PHASES.length) % PHASES.length;
    setPhase(PHASES[i], true); e.preventDefault();
  });

  // ------------------------------------------------------------------ planned releases: construction shows one release and its milestones
  let relSel = null;         // release chosen by the user (null = the next release to ship)
  const relPlan = () => (data && data.cycle && data.cycle.releases) || [];
  const relShown = () => {
    const rp = relPlan();
    if (!rp.length) return null;
    if (relSel && rp.some((r) => r.id === relSel)) return rp.find((r) => r.id === relSel);
    return rp.find((r) => r.status !== "released") || rp[rp.length - 1];
  };
  /** The milestones the construction tabs show: those of the release shown, or every milestone without planned releases. */
  function msInView() {
    const r = relShown();
    return r ? data.milestones.filter((m) => r.milestones.includes(m.id)) : data.milestones;
  }
  function currentId() {
    const ms = msInView();
    const ids = ms.map((m) => m.id);
    if (selected && ids.includes(selected)) return selected;
    if (data.current_milestone && ids.includes(data.current_milestone)) return data.current_milestone;
    const open = ms.find((m) => m.gate === "pending" && tasksOf(m).length);
    return (open && open.id) || ids[ids.length - 1] || null;
  }
  function selectRelease(rid, focus) {
    relSel = rid === (relPlan().find((r) => r.status !== "released") || {}).id ? null : rid;
    selected = null; expanded = new Set(); goalOpen = false; mobileCol = null;
    render();
    if (focus && $(`rel-${rid}`)) $(`rel-${rid}`).focus();
  }
  const REL_WORD = { in_progress: "in progress", ready_for_review: "ready for review", awaiting_approval: "waiting for your approval",
    deploying_prod: "approved · going to production", released: "released" };
  /** The release strip (R1 ✓ › R2 ● › R3 ○) and the stages of the release shown: milestones, dossier, approval, production, released. */
  function renderReleases() {
    const rp = relPlan();
    $("rel-row").hidden = !rp.length;
    if (!rp.length) return;
    const shown = relShown();
    fill($("rel-tabs"), rp.map((r, i) => {
      const done = r.status === "released", sel = r.id === shown.id;
      const live = r.milestones.filter((mid) => { const m = data.milestones.find((x) => x.id === mid); return m && tasksOf(m).length; }).length;
      const state = sel ? "here" : done ? "st-done" : r.status === "in_progress" && !r.closed.length ? "st-upcoming" : "st-current";
      return h("button", { type: "button", role: "tab", id: `rel-${r.id}`, "aria-selected": String(sel), tabindex: sel ? "0" : "-1",
        class: `schev ${state}${i === 0 ? " chev-first" : ""}${i === rp.length - 1 ? " chev-last" : ""}`, title: `${r.id} · ${r.title}: ${REL_WORD[r.status]}`,
        onclick: () => selectRelease(r.id, true) },
      done ? h("span", { class: "tab-ok", "aria-hidden": "true", text: "✓" }) : h("span", { class: `tab-dot${r.status === "awaiting_approval" ? " wait" : r.closed.length ? " active" : ""}`, "aria-hidden": "true" }),
      h("strong", { text: r.id }), h("span", { class: "tab-count", text: `${r.closed.length}/${live}` }),
      r.status === "awaiting_approval" ? h("span", { class: "tab-qa", text: "approve" }) : null,
      h("span", { class: "visually-hidden", text: `: ${REL_WORD[r.status]}` }));
    }));
    const lc = data.lifecycle || {};
    const prodOn = lc.deploy_when && lc.deploy_when !== "none";
    const order = ["in_progress", "ready_for_review", "awaiting_approval", "deploying_prod", "released"];
    const at = order.indexOf(shown.status);
    const live = shown.milestones.filter((mid) => { const m = data.milestones.find((x) => x.id === mid); return m && tasksOf(m).length; }).length;
    const stage = (i, name, note, cmdText, na) => {
      const state = na ? "na" : at > i ? "done" : at === i ? "current" : "upcoming";
      return h("li", { class: `chev stage st-${state}${at === i && !na ? " here" : ""}`, "aria-current": at === i ? "step" : null },
        h("div", { class: "stage-top" }, h("span", { class: "stage-ico", "aria-hidden": "true", text: STAGE_ICON[state] }), h("span", { class: "stage-name", text: name }),
          h("span", { class: "visually-hidden", text: `: ${STAGE_WORD[state]}.` })),
        note ? h("span", { class: "stage-note" }, note, cmdText ? [" ", cmd(cmdText)] : null) : null);
    };
    const rej = (shown.history || []).filter((x) => x.event === "rejected").length;
    fill($("rel-stages"),
      stage(0, "Milestones", `${shown.closed.length}/${live} closed${rej ? ` · ${plural(rej, "rejection")}` : ""}`),
      stage(1, "Dossier", at === 1 ? "Audit and submit:" : shown.dossier ? "Submitted" : "", at === 1 ? "/dev-kit:release" : null),
      stage(2, "Your approval", at === 2 ? "Waiting for you" : at > 2 ? "Approved" : ""),
      stage(3, "Production", !prodOn ? "No production" : at === 3 ? "Deploy and smoke:" : "", at === 3 ? "/dev-kit:release" : null, !prodOn && at !== 3),
      stage(4, "Released", at === 4 ? ((data.releases || []).filter((x) => x.release === shown.id).map((x) => x.tag || x.version).join(", ") || "Recorded") : ""));
  }
  $("rel-tabs").addEventListener("keydown", (e) => {
    const rp = relPlan();
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key) || !rp.length) return;
    let i = rp.findIndex((r) => r.id === relShown().id);
    i = e.key === "Home" ? 0 : e.key === "End" ? rp.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + rp.length) % rp.length;
    selectRelease(rp[i].id, true); e.preventDefault();
  });
  /** Approve, or reject with what must change: queued for Claude Code, which records it (release-decide --request). */
  const rejectDrafts = {};
  function releaseDecision(r) {
    if (!actionsOn()) return h("span", { class: "sub" }, "Decide in Claude Code with ", cmd("/dev-kit:release"));
    const sent = inbox().open.find((x) => x.action === "release_decision" && x.args && x.args.release === r.id);
    if (sent) return h("div", { class: "sub answer-sent", text: `Decision sent (${sent.id}): ${sent.args.decision}. Claude Code applies it.` });
    const box = h("div", { class: "sub answer rel-decide", role: "group", "aria-label": `Decision on ${r.id}` });
    const ta = h("textarea", { id: `rej-${r.id}`, maxlength: "4000", rows: "3", class: "answer-input", "aria-label": `What must change in ${r.id}, one item per line`,
      placeholder: "What must change, one item per line (each becomes a fix task)" });
    ta.value = rejectDrafts[r.id] || "";
    ta.addEventListener("input", () => { rejectDrafts[r.id] = ta.value; });
    const send = async (args, el) => { el.disabled = true; try { await queue("release_decision", { release: r.id, ...args }); delete rejectDrafts[r.id]; } catch (e) { el.disabled = false; } };
    box.append(
      h("button", { type: "button", class: "btn btn-sm btn-primary", text: `Approve ${r.id}`, onclick: (e) => send({ decision: "approve" }, e.currentTarget) }),
      h("span", { class: "answer-free" }, ta, h("button", { type: "button", class: "btn btn-sm btn-danger", id: `rej-send-${r.id}`, text: "Reject",
        onclick: (e) => { const v = ta.value.trim(); if (v) send({ decision: "reject", feedback: v }, e.currentTarget); else { ta.focus(); toast("Write what must change before rejecting.", true); } } })));
    return box;
  }
  const currentMilestone = () => (data && data.milestones.find((x) => x.id === currentId())) || null;
  function selectMilestone(id, focusTab) {
    selected = id; expanded = new Set(); goalOpen = false; mobileCol = null;
    render();
    if (focusTab && $(`tab-${currentId()}`)) $(`tab-${currentId()}`).focus();
  }

  // ------------------------------------------------------------------ milestone: tabs, goal, progress
  const TAB_WINDOW = 3;       // milestones shown as tabs: the selected one and its neighbours; the rest sit in the earlier/later lists
  function tabWindow(ids, cur) {
    const i = Math.max(0, ids.indexOf(cur));
    const start = Math.max(0, Math.min(i - Math.floor(TAB_WINDOW / 2), ids.length - TAB_WINDOW));
    return [start, Math.min(ids.length, start + TAB_WINDOW)];
  }
  function milestoneInfo(m) {
    const ts = tasksOf(m);
    return { active: ts.some((t) => t.status === "in_progress"), done: ts.filter((t) => t.status === "done").length, total: ts.length };
  }
  function renderTabs() {
    const cur = currentId();
    const ms = msInView();
    const [a, b] = tabWindow(ms.map((m) => m.id), cur);
    // milestones as one chevron strip: [+N earlier] M-1 › M › M+1 [+N later], coloured by the milestone's state
    const hasEarlier = a > 0, hasLater = b < ms.length;
    const shown = ms.slice(a, b);
    const tabs = shown.map((m, i) => {
      const x = milestoneInfo(m);
      const closed = m.gate === "passed" || m.gate === "skipped";
      const inQa = !closed && x.total > 0 && x.done === x.total;
      const state = m.id === cur ? "here" : closed ? "st-done" : x.active || inQa || m.id === data.current_milestone ? "st-current" : "st-upcoming";
      const edge = `${i === 0 && !hasEarlier ? " chev-first" : ""}${i === shown.length - 1 && !hasLater ? " chev-last" : ""}`;
      return h("button", {
        role: "tab", type: "button", id: `tab-${m.id}`, class: `schev ${state}${edge}`, "aria-selected": String(m.id === cur), "aria-controls": "main",
        tabindex: m.id === cur ? "0" : "-1", title: `${m.title || m.id} · gate ${m.gate}`,
        onclick: () => selectMilestone(m.id, true),
      }, closed ? h("span", { class: "tab-ok", "aria-hidden": "true", text: "✓" }) : h("span", { class: `tab-dot ${x.active ? "active" : m.gate}`, "aria-hidden": "true" }),
      h("strong", { text: m.id }), h("span", { class: "tab-count", text: `${x.done}/${x.total}` }),
      !closed && x.total > 0 && x.done === x.total ? h("span", { class: "tab-qa", title: "All tasks done; waiting for the QA gate", text: "QA" }) : null,
      m.id === data.current_milestone ? h("span", { class: "tab-current", text: "current" }) : null);
    });
    if (!tabs.length) tabs.push(h("span", { class: "card-sub" }, "No milestones yet. They appear after ", cmd("/dev-kit:plan"), "."));
    fill($("tabs"), tabs);
    const side = (key, list, word) => {
      $(`tabs-${key}-wrap`).hidden = !list.length;
      fill($(`tabs-${key}`), `+${list.length}`, h("span", { class: "mt-word", text: ` ${word}` }));
      $(`tabs-${key}`).setAttribute("aria-label", `${plural(list.length, `${word} milestone`)}: choose one`);
      fill($(`tabs-${key}-list`), list.map((m) => {
        const x = milestoneInfo(m);
        return h("li", {}, h("button", { type: "button", class: "ms-item", onclick: () => { pops.forEach((p) => p.close()); selectMilestone(m.id, true); } },
          h("span", { class: `tab-dot ${x.active ? "active" : m.gate}`, "aria-hidden": "true" }), h("strong", { text: m.id }),
          h("span", { class: "si-title", text: m.title || "" }), h("span", { class: "si-count", text: `${x.done}/${x.total}` }),
          m.id === data.current_milestone ? h("span", { class: "tab-current", text: "current" }) : null));
      }));
    };
    side("earlier", ms.slice(0, a).reverse(), "earlier");  // the lists read newest first, like every milestone list
    side("later", ms.slice(b).reverse(), "later");
    $("tabs-back").hidden = !data.current_milestone || cur === data.current_milestone;
  }
  $("tabs-back").addEventListener("click", () => { selected = null; selectMilestone(null, true); });

  function renderMilestone(m) {
    const ts = tasksOf(m);
    const counts = Object.fromEntries(STATUS.map((st) => [st.key, ts.filter((t) => t.status === st.key).length]));
    const pct = ts.length ? Math.round((counts.done / ts.length) * 100) : 0;
    $("ms-title").textContent = m ? `${m.id} · ${m.title || "Milestone"}` : "No milestone planned yet";
    const goal = $("ms-goal");
    if (m) goal.textContent = m.goal || "No goal paragraph in plan.md for this milestone.";
    else fill(goal, "Run ", cmd("/dev-kit:plan"), " to create milestones and tasks.");
    goal.classList.remove("open");
    const clipped = goal.scrollHeight > goal.clientHeight + 1;
    goal.classList.toggle("open", goalOpen);
    $("goal-more").hidden = !clipped;
    $("goal-more").textContent = goalOpen ? "Show less" : "Show more";
    $("goal-more").setAttribute("aria-expanded", String(goalOpen));
    $("ms-done").textContent = String(counts.done);
    $("ms-total").textContent = ` of ${plural(ts.length, "task")} done`;
    // the percentage counts tasks, not the milestone: show where the milestone is instead
    const st = m ? stagesOf(m) : [];
    const live = st.filter((x) => x.state !== "na");
    const hereIdx = live.findIndex((x) => x.here);
    const closedNow = st.length && st.at(-1).state === "done";
    $("ms-pct").textContent = !m ? "" : closedNow ? "Closed" : hereIdx >= 0 ? `Stage ${hereIdx + 1} of ${live.length} · ${live[hereIdx].name}` : `${pct}%`;
    $("ms-pct").title = m ? `${pct}% of the tasks are done` : "";
    const next = st.slice(hereIdx + 1).find((x) => x.state !== "na");
    $("ms-caption").textContent = m && ts.length && counts.done === ts.length && !closedNow
      ? `All tasks done; the milestone closes after ${hereIdx >= 0 ? (live[hereIdx].key === "qa" ? "the QA gate" : live[hereIdx].name.toLowerCase()) : "its gate"}${next && next.key !== "close" ? ` and ${next.name.toLowerCase()}` : ""}.` : "";
    const order = ["done", "in_progress", "blocked", "todo"];
    const label = (k) => STATUS.find((x) => x.key === k).label;
    fill($("segbar"), order.filter((k) => counts[k]).map((k) => {
      const sp = h("span", { class: `st-${k}`, title: `${label(k)}: ${counts[k]}` });
      sp.style.flexGrow = String(counts[k]);
      return sp;
    }));
    $("segbar").setAttribute("aria-label", order.map((k) => `${label(k)} ${counts[k]}`).join(", "));
    fill($("seg-legend"), order.map((k) => h("li", {}, h("span", { class: `swatch st-${k}`, "aria-hidden": "true" }), `${label(k)} ${counts[k]}`)));
    // project totals and cost live in Stable; here only what belongs to this milestone: its issues and its gate
    const b = data.backlog || {};
    const buf = b.buffer && m && b.buffer.milestone === m.id ? b.buffer : null;
    const sched = m ? Object.entries(b.issues || {}).filter(([, v]) => v.scheduled_in === m.id && ["scheduled", "in_progress"].includes(v.status)) : [];
    fill($("ms-facts"),
      buf || sched.length ? h("span", { title: [buf ? `${buf.pct}% of the milestone reserved for issues` : null, sched.length ? `Scheduled here: ${sched.map(([id, v]) => `${id} ${v.title || ""}`).join("; ")}` : null].filter(Boolean).join("\n"),
        text: [buf ? (buf.capacity ? `Issue buffer ${buf.used}/${buf.capacity}` : `${plural(buf.used, "issue task")}`) : null, sched.length ? plural(sched.length, "issue") : null].filter(Boolean).join(" · ") }) : null,
      gateBadge(m));
  }
  $("goal-more").addEventListener("click", () => { goalOpen = !goalOpen; renderMilestone(currentMilestone()); });

  // ------------------------------------------------------------------ kanban
  function waitingOn(t) {
    return (t.deps || []).filter((d) => d && data.tasks[d] && data.tasks[d].status !== "done");
  }
  function taskCard(t) {
    const isNext = data.next && data.next.task === t.id;
    const wait = t.status === "done" ? [] : waitingOn(t);
    const here = agentsOn(t.id);
    return h("article", { class: `tcard s-${t.status}${isNext ? " next" : ""}`, "aria-label": `${t.id} ${t.title}, ${stLabel(t.status)}${wait.length ? `, waiting on ${wait.join(", ")}` : ""}. Open details`,
      tabindex: "0", role: "button", "aria-haspopup": "dialog", "data-tid": t.id,
      onclick: () => openTask(t.id), onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openTask(t.id); } } },
      h("div", { class: "tcard-top" }, h("span", { class: "tid", text: t.id }), h("span", { class: "chip", text: t.type }),
        t.lane ? h("span", { class: `chip lane-${t.lane}`, text: t.lane }) : null,
        isNext ? h("span", { class: "chip next-chip", text: "next up" }) : null),
      h("div", { class: "tcard-title", text: t.title }),
      here.length ? h("div", { class: "tcard-agents" }, here.map((x) => h("span", { class: "agent-chip" }, agentBits(x)))) : null,
      t.status === "blocked" && t.blocked_reason ? h("div", { class: "reason", text: t.blocked_reason }) : null,
      h("div", { class: "tcard-meta" },
        wait.length ? h("span", { class: "chip wait", text: `Waiting on ${wait.join(", ")}` }) : null,
        t.status === "todo" && !wait.length && !isNext ? h("span", { class: "chip ready", text: "Ready" }) : null,
        t.acceptance ? h("span", { title: "Acceptance criteria", text: `${t.acceptance} AC` }) : null,
        t.status === "in_progress" && t.started_at ? h("span", { text: `started ${ago(parseT(t.started_at))}` }) : null,
        t.status === "done" && t.done_at ? h("span", { text: `done ${fmtDT(parseT(t.done_at))}` }) : null,
        t.commit ? h("span", { class: "tid", title: "Commit", text: t.commit.slice(0, 7) }) : null));
  }

  function renderKanban(m) {
    if (view !== "tasks") return;
    const ts = tasksOf(m);
    const types = [...new Set(ts.map((t) => t.type).filter(Boolean))].sort();
    const sel = $("type-filter");
    if (typeFilter && !types.includes(typeFilter)) typeFilter = "";
    if (sel.dataset.types !== types.join(",")) {
      sel.dataset.types = types.join(",");
      fill(sel, h("option", { value: "", text: "All types" }), types.map((t) => h("option", { value: t, text: t })));
    }
    sel.value = typeFilter;
    sel.disabled = types.length < 2;
    const q = query.trim().toLowerCase();
    const filtering = Boolean(q || typeFilter);
    const match = (t) => (!typeFilter || t.type === typeFilter) && (!q || `${t.id} ${t.title}`.toLowerCase().includes(q));
    const shown = ts.filter(match);
    const note = $("filter-note");
    note.hidden = !filtering;
    if (filtering) fill(note, `${shown.length} of ${plural(ts.length, "task")} shown. `,
      h("button", { type: "button", class: "link-btn", text: "Clear filter", onclick: () => { query = ""; typeFilter = ""; $("task-search").value = ""; renderKanban(currentMilestone()); $("task-search").focus(); } }));
    const box = $("kanban");
    if (!m) {
      fill($("col-tabs"));
      fill(box, h("div", { class: "board-empty" }, "No milestone planned yet. Run ", cmd("/dev-kit:plan"), " to create milestones and tasks."));
      return;
    }
    const by = Object.fromEntries(STATUS.map((st) => [st.key, shown.filter((t) => t.status === st.key)]));
    by.done.sort((a, b) => (parseT(b.done_at) || 0) - (parseT(a.done_at) || 0));
    // To do: next up first, then ready, then waiting, so the few visible cards are the useful ones
    const nextId = data.next && data.next.task;
    const todoRank = (t) => (t.id === nextId ? 0 : waitingOn(t).length ? 2 : 1);
    by.todo.sort((a, b) => todoRank(a) - todoRank(b) || Number(a.id.slice(2)) - Number(b.id.slice(2)));
    const col = mobileCol || ["in_progress", "blocked", "todo", "done"].find((k) => by[k].length) || "todo";
    box.dataset.col = col;
    fill($("col-tabs"), STATUS.map((st) => h("button", { type: "button", class: "seg-btn", "aria-pressed": String(col === st.key),
      text: `${st.label} ${by[st.key].length}`, onclick: () => { mobileCol = st.key; renderKanban(currentMilestone()); } })));
    fill(box, STATUS.map((st) => {
      let list = by[st.key];
      let more = null;
      if (list.length > COL_LIMIT && !filtering) {
        const open = expanded.has(st.key);
        more = h("button", { type: "button", class: "col-more", id: `more-${st.key}`, "aria-expanded": String(open),
          text: open ? "Show less" : `Show all ${list.length}`,
          onclick: () => { if (open) expanded.delete(st.key); else expanded.add(st.key); keepFocus(() => renderKanban(currentMilestone())); } });
        if (!open) list = list.slice(0, COL_LIMIT);
      }
      const slim = st.key === "blocked" && !ts.some((t) => t.status === "blocked");
      return h("section", { class: `col${slim ? " slim" : ""}`, "data-st": st.key, "aria-label": `${st.label}, ${plural(by[st.key].length, "task")}` },
        h("div", { class: "col-head" }, h("span", { class: `swatch st-${st.key}`, "aria-hidden": "true" }), st.label,
          h("span", { class: "count", text: String(by[st.key].length) })),
        list.length ? list.map(taskCard) : h("div", { class: "col-empty", text: filtering ? "No match" : st.key === "blocked" ? "Nothing blocked" : "Empty" }),
        more);
    }));
  }
  $("task-search").addEventListener("input", (e) => { query = e.target.value; renderKanban(currentMilestone()); });
  $("type-filter").addEventListener("change", (e) => { typeFilter = e.target.value; renderKanban(currentMilestone()); });

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
      fill(box, h("div", { class: "chart-empty", text: "The burndown starts when the first task of this milestone starts." }));
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
    const rows = [[ser.t0, ser.total, "milestone start"]];
    let rem = ser.total;
    for (const d of ser.dones) { rem -= 1; rows.push([d, rem, "task done"]); }
    fill($("burndown-table"), h("table", {}, h("thead", {}, h("tr", {}, h("th", { text: "When" }), h("th", { text: "Remaining" }), h("th", { text: "Event" }))),
      h("tbody", {}, rows.map(([t, v, e]) => h("tr", {}, h("td", { text: fmtDT(t) }), h("td", { text: String(v) }), h("td", { text: e }))))));
  }

  // ------------------------------------------------------------------ velocity: tasks done per milestone, then its hours and cost
  /** Hours a milestone took: elapsed (first task start -> gate, or now while open) and working (the union of the time
   * its tasks were in progress, so parallel tasks do not count twice). null before any task started. */
  function msTiming(m) {
    const now = Date.now();
    const iv = tasksOf(m).filter((t) => Number.isFinite(parseT(t.started_at))).map((t) => {
      const s0 = parseT(t.started_at), e0 = parseT(t.done_at);
      return [s0, Number.isFinite(e0) ? Math.max(s0, e0) : t.status === "in_progress" ? now : s0];
    }).sort((a, b) => a[0] - b[0]);
    if (!iv.length) return null;
    let work = 0, [cs, ce] = iv[0];
    for (const [s0, e0] of iv.slice(1)) { if (s0 <= ce) ce = Math.max(ce, e0); else { work += ce - cs; cs = s0; ce = e0; } }
    work += ce - cs;
    const closed = m.gate === "passed" || m.gate === "skipped";
    const dones = tasksOf(m).map((t) => parseT(t.done_at)).filter(Number.isFinite);
    const end = closed && Number.isFinite(parseT(m.passed_at)) ? parseT(m.passed_at) : closed && dones.length ? Math.max(...dones) : now;
    return { elapsed: Math.max(0, end - iv[0][0]) / 36e5, work: work / 36e5, open: !closed };
  }
  const fmtH = (x) => (x == null ? "—" : x < 1 ? `${Math.max(1, Math.round(x * 60))} min` : x < 100 ? `${x.toFixed(1)} h` : `${Math.round(x)} h`);
  /** Cost when it was measured, otherwise tokens when they were, otherwise null (dev_cost.py writes milestones.json). */
  function msSpend(id) {
    const c = (data.milestone_costs || {})[id];
    if (!c) return null;
    if (Number(c.usd) > 0) return { text: `US$ ${Number(c.usd).toFixed(2)}${c.usd_complete === false ? "+" : ""}`, title: c.usd_complete === false ? "Some requests had no price: at least this much" : "Estimated cost, API-equivalent" };
    if (Number(c.tokens) > 0) return { text: `${compact(Number(c.tokens))} tok`, title: c.partial ? "Tokens reported by the skills (no transcripts): partial" : "Tokens used (no price for the model)" };
    return null;
  }
  function renderVelocity(cur) {
    const box = $("velocity");
    const rows = data.milestones.map((m) => {
      const ts = tasksOf(m);
      return { id: m.id, title: m.title, done: ts.filter((t) => t.status === "done").length, total: ts.length, time: msTiming(m), spend: msSpend(m.id) };
    }).filter((r) => r.total);
    if (!rows.length) {
      fill(box, h("div", { class: "chart-empty", text: "Velocity appears once milestones have tasks." }));
      fill($("velocity-hours"));
      fill($("velocity-table"));
      return;
    }
    // same margins as the hours chart below, so each milestone's bar sits right above its points
    const W = Math.max(300, Math.round(box.clientWidth || 420)), H = 240, L = 44, R = 64, T = 22, B = 28;
    const max = Math.max(1, ...rows.map((r) => r.total));
    const y = (v) => T + (1 - v / max) * (H - T - B);
    const band = (W - L - R) / rows.length;
    const bw = Math.min(24, band * 0.6);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Tasks done per milestone: " + rows.map((r) => `${r.id} ${r.done}`).join(", ") });
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
      const tipFn = (evt) => showTip(evt, `${r.id} · ${r.title || ""}`, velTip(r));
      hit.addEventListener("pointermove", tipFn); hit.addEventListener("focus", tipFn);
      hit.addEventListener("pointerleave", hideTip); hit.addEventListener("blur", hideTip);
      svg.append(hit, s("path", { class: `bar${r.id === cur ? " current" : ""}`, d }));
      svg.append(s("text", { class: "label-strong", x: cx, y: top - 6, "text-anchor": "middle", text: String(r.done) }));
      svg.append(s("text", { x: cx, y: H - 8, "text-anchor": "middle", text: r.id }));
    });
    fill(box, svg);
    renderHours(rows, W);
    // the table is a list: newest first (the charts keep time order)
    fill($("velocity-table"), h("table", {}, h("thead", {}, h("tr", {}, ["Milestone", "Done", "Total", "Elapsed", "Working", "Cost or tokens"].map((x) => h("th", { text: x })))),
      h("tbody", {}, rows.slice().reverse().map((r) => h("tr", {}, h("td", { text: `${r.id} ${r.title || ""}` }), h("td", { text: String(r.done) }), h("td", { text: String(r.total) }),
        h("td", { text: r.time ? fmtH(r.time.elapsed) + (r.time.open ? " so far" : "") : "—" }), h("td", { text: r.time ? fmtH(r.time.work) : "—" }),
        h("td", { text: r.spend ? r.spend.text : "not measured" }))))));
  }
  function velTip(r) {
    const out = [[`${r.done}`, `done of ${r.total}`, "s1"]];
    if (r.time) out.push([fmtH(r.time.elapsed), r.time.open ? "elapsed so far" : "elapsed", "s1"], [fmtH(r.time.work), "working", "s2"]);
    if (r.spend) out.push([r.spend.text, r.spend.text.endsWith("tok") ? "tokens" : "cost"]);
    return out;
  }
  /** Hours per milestone, same milestones and order as the bars above: one axis (hours), two lines - elapsed (solid)
   * and working (dashed) - with markers, direct labels on the last point, and the cost or tokens under each label. */
  function renderHours(rows, W) {
    const box = $("velocity-hours");
    const pts = rows.filter((r) => r.time);
    if (!pts.length) { fill(box, h("div", { class: "chart-empty", text: "Hours appear once a task of a milestone has started." })); return; }
    const H = 220, L = 44, R = 64, T = 16, B = 44;
    const max = Math.max(0.5, ...pts.map((r) => Math.max(r.time.elapsed, r.time.work)));
    const nice = (v) => { const p = 10 ** Math.floor(Math.log10(v)); return [1, 2, 2.5, 5, 10].map((k) => k * p).find((k) => k >= v); };
    const step = nice(max / 4), top = step * Math.ceil(max / step);
    const y = (v) => T + (1 - v / top) * (H - T - B);
    const band = (W - L - R) / rows.length;
    const cx = (i) => L + band * i + band / 2;
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Hours per milestone: " + pts.map((r) => `${r.id} elapsed ${fmtH(r.time.elapsed)}, working ${fmtH(r.time.work)}`).join("; ") });
    const grid = s("g", { class: "grid" });
    for (let v = 0; v <= top + 1e-9; v += step) grid.append(s("line", { x1: L, x2: W - R, y1: y(v), y2: y(v) }), s("text", { x: L - 8, y: y(v) + 4, "text-anchor": "end", text: v ? fmtH(v).replace(" ", " ") : "0" }));
    svg.append(grid, s("line", { class: "axis-line", x1: L, x2: W - R, y1: y(0), y2: y(0) }));
    const series = [["elapsed", "line-actual", "marker"], ["work", "line-work", "marker s2"]];
    series.forEach(([key, cls, mk]) => {
      // a milestone without a started task breaks the line instead of dropping to zero
      let d = "", pen = false;
      rows.forEach((r, i) => { if (!r.time) { pen = false; return; } d += `${pen ? "L" : "M"}${cx(i).toFixed(1)},${y(r.time[key]).toFixed(1)}`; pen = true; });
      svg.append(s("path", { class: cls, d }));
      rows.forEach((r, i) => { if (r.time) svg.append(s("circle", { class: mk, cx: cx(i), cy: y(r.time[key]), r: 4 })); });
    });
    const lastI = rows.reduce((k, r, i) => (r.time ? i : k), -1);
    const last = rows[lastI];
    const ye = y(last.time.elapsed), yw = y(last.time.work);
    const gap = Math.abs(ye - yw) < 14 ? (ye <= yw ? [-7, 7] : [7, -7]) : [0, 0];  // keep the two direct labels apart
    svg.append(s("text", { class: "label-strong", x: cx(lastI) + 9, y: ye + 4 + gap[0], text: "elapsed" }),
      s("text", { class: "label-strong", x: cx(lastI) + 9, y: yw + 4 + gap[1], text: "working" }));
    rows.forEach((r, i) => {
      svg.append(s("text", { x: cx(i), y: H - 24, "text-anchor": "middle", text: r.id }));
      if (r.spend) svg.append(s("text", { class: "spend", x: cx(i), y: H - 8, "text-anchor": "middle", text: r.spend.text }));
      const hit = s("rect", { class: "hit", x: cx(i) - band / 2 + 2, y: T, width: band - 4, height: H - T - B, tabindex: "0",
        "aria-label": `${r.id}: ${r.time ? `elapsed ${fmtH(r.time.elapsed)}, working ${fmtH(r.time.work)}` : "not started"}${r.spend ? `, ${r.spend.text}` : ""}` });
      const tipFn = (evt) => showTip(evt, `${r.id} · ${r.title || ""}`, velTip(r));
      hit.addEventListener("pointermove", tipFn); hit.addEventListener("focus", tipFn);
      hit.addEventListener("pointerleave", hideTip); hit.addEventListener("blur", hideTip);
      svg.append(hit);
    });
    fill(box, svg);
  }

  // ------------------------------------------------------------------ needs you, activity
  /** A small button naming a phase: it opens that phase. */
  const phaseTag = (p) => h("button", { type: "button", class: "phase-tag", title: `Open ${PHASE_NAME[p]}`, text: PHASE_NAME[p], onclick: () => setPhase(p) });
  function listBlock(title, items, emptyText, good, phase) {
    return h("div", {}, h("div", { class: "list-title" }, title, items.length ? h("span", { class: "chip", text: String(items.length) }) : null, phase ? phaseTag(phase) : null),
      items.length ? h("ul", { class: "list" }, items) : h("div", { class: `empty${good ? " good" : ""}`, text: emptyText }));
  }

  /** The phase an open question belongs to, from the skill that raised it. */
  function questionPhase(q) {
    const by = String(q.by || "").toLowerCase();
    if (/interview|prd|architect|\bux\b|\bui\b|design|brief/.test(by)) return "conception";
    if (/\bplan\b|requirements/.test(by)) return "planning";
    if (/release|deploy|docs|usability/.test(by)) return "stable";
    return "construction";
  }
  function renderImpediments() {
    const blocked = Object.entries(data.tasks).filter(([, t]) => t.status === "blocked");
    const b = data.backlog || {};
    const hot = b.hotfix_open || [];
    const warns = b.warnings || [];
    // milestones past the QA limit with no blocked card to show it (the round failed on scores alone)
    const stuck = data.milestones.filter((m) => qaState(m).exhausted && !qaState(m).fixBlocked.length);
    const approvals = actionsOn() ? inbox().approvals : [];
    const waitingRel = relPlan().filter((r) => r.status === "awaiting_approval");
    const n = blocked.length + data.questions.length + hot.length + stuck.length + approvals.length + waitingRel.length;
    // which phase each item belongs to: the tabs show the count, the rows a tag that opens the phase
    needsBy = { conception: 0, planning: 0, construction: blocked.length + hot.length + stuck.length + waitingRel.length, stable: 0 };
    if (approvals.length) needsBy[data.phase] = (needsBy[data.phase] || 0) + approvals.length;
    data.questions.forEach((q) => { needsBy[questionPhase(q)] += 1; });
    // the strip exists only while something needs the user; warnings alone ride along but do not open it
    const strip = $("needs");
    strip.hidden = !n;
    $("needs-count").textContent = n ? plural(n, "item") : "";
    needsN = n;
    if (!n) { fill($("impediments")); return; }
    fill($("impediments"),
      approvals.length ? listBlock("Claude Code asks permission", approvals.map(approvalRow), "") : null,
      waitingRel.length ? listBlock("Releases waiting for your approval", waitingRel.map((r) => h("li", {}, h("span", { class: "id", text: r.id }),
        h("span", { text: `${r.title} · ${plural(r.closed.length, "milestone")} closed` }),
        h("button", { type: "button", class: "link-btn", text: "Open", onclick: () => { selectRelease(r.id); setPhase("construction"); } }),
        r.dossier ? h("span", { class: "sub" }, docLink(r.dossier, "Open the dossier")) : null,
        releaseDecision(r))), "", false, "construction") : null,
      stuck.length ? listBlock("QA rounds used up", stuck.map((m) => h("li", {}, h("span", { class: "id", text: m.id }),
        h("span", { text: `${qaState(m).qa.runs - 1} fix rounds used of ${qaState(m).max} (${qaReason(qaState(m).qa, m) || "see the QA report"}). Keep fixing, accept with an ADR, or replan.` }),
        h("span", { class: "sub" }, cmd(`/dev-kit:qa ${m.id}`)))), "", false, "construction") : null,
      hot.length ? listBlock("Open hotfixes", hot.map((id) => h("li", {}, issueId(id),
        h("span", { text: (data.tasks[id] || (b.issues || {})[id] || {}).title || "" }), h("span", { class: "chip lane-hotfix", text: "hotfix" }))), "", false, "construction") : null,
      blocked.length ? listBlock("Blocked tasks", blocked.map(([id, t]) => h("li", { class: "has-btn" },
        h("button", { type: "button", class: "row-btn", "data-tid": id, "aria-haspopup": "dialog", onclick: () => openTask(id) },
          h("span", { class: "id", text: id }), h("span", { text: t.title }), h("span", { class: "chip", text: t.milestone }),
          h("span", { class: "sub bad", text: t.blocked_reason || "No reason recorded" })))), "", false, "construction") : null,
      data.questions.length ? listBlock("Open questions", data.questions.map((q) => h("li", {}, hasDoc("open-questions.md") ? docLink("open-questions.md", q.id, q.id, "id") : h("span", { class: "id", text: q.id }), h("span", {}, linkify(q.question)),
        h("span", { class: "q-tags" }, h("span", { class: "chip", text: q.by || "?" }), phaseTag(questionPhase(q))), q.assumption ? h("span", { class: "sub", text: `Assumed meanwhile: ${q.assumption}` }) : null,
        actionsOn() ? answerBox(q) : null)), "") : null,
      warns.length ? listBlock("Warnings", warns.map((w) => h("li", {}, h("span", { class: "id", text: "!" }), h("span", { text: w }))), "") : null,
      actionsOn() && data.questions.length ? h("p", { class: "needs-hint" }, "Answer here: Claude Code records the answer and continues what was waiting on it.") : null,
      data.questions.length || blocked.length ? h("p", { class: "needs-hint" }, actionsOn() ? "Or go through all of them with " : "Answer in Claude Code with ", cmd("/dev-kit:interview --gaps")) : null);
  }
  function goNeeds() {
    const el = $("needs");
    if (el.hidden) return;
    el.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    el.focus({ preventScroll: true });
  }

  // ------------------------------------------------------------------ stages of the milestone, in the order the kit runs them
  // Plan → Build → QA gate ⇄ Fixes → Smoke (local preview, inside qa) → Deploy (per-milestone production) → Closed
  // fixes of a QA round sit in the QA & fixes stage; a rejected release's fixes are the build of its fixes milestone
  const isFix = (t) => t.type === "fix" && Boolean(t.source) && !String(t.source).startsWith("release:");
  /** Where the QA loop of a milestone stands: rounds run, fixes, whether a round is running now. */
  function qaState(m) {
    const qa = m.qa || { runs: m.qa_runs || 0, history: [] };
    const ts = tasksOf(m);
    const fixes = ts.filter(isFix), fixOpen = fixes.filter((t) => t.status !== "done");
    const buildOpen = ts.filter((t) => !isFix(t) && t.status !== "done");
    const passed = m.gate === "passed" || m.gate === "skipped";
    const agents = agentsOn(`GATE:${m.id}`);
    const running = !passed && (Boolean(qa.round) || agents.length > 0);
    const max = (data.lifecycle || {}).max_fix_rounds || 3;
    const fixActive = fixes.filter((t) => t.status === "todo" || t.status === "in_progress");
    const fixBlocked = fixes.filter((t) => t.status === "blocked");
    // past the agreed fix rounds (or a fix that did not hold twice) the next step is a decision: dev_state blocks those cards
    const exhausted = !passed && !running && !fixActive.length && (qa.runs > max || fixBlocked.length > 0);
    return { qa, ts, fixes, fixOpen, fixActive, fixBlocked, buildOpen, passed, agents, running, max, exhausted, round: qa.runs + 1 };
  }
  /** Why the last QA round failed, in words: dimensions under their minimum first, then blockers, then the overall. */
  function qaReason(qa, m) {
    const last = qa && qa.last;
    if (!last) return (m && m.gate_note) || (qa && qa.note) || "";
    const below = last.below || [];
    const parts = [];
    if (below.length) {
      const mins = new Set(below.map((d) => d.min));
      parts.push(mins.size === 1 ? `${below.map((d) => `${d.dimension} ${d.score}`).join(", ")} below ${below[0].min}`
        : below.map((d) => `${d.dimension} ${d.score} < ${d.min}`).join(", "));
    }
    if (last.blockers) parts.push(plural(last.blockers, "blocking finding"));
    if (last.overall != null && last.cutoff != null && last.overall < last.cutoff) parts.push(`overall ${last.overall} below ${last.cutoff}`);
    return parts.join("; ");
  }
  /** The QA loop as a trail: one pill per round, the fixes in between, and the round running or due now. */
  function qaTrail(m, x) {
    const hist = x.qa.history && x.qa.history.length ? x.qa.history
      : Array.from({ length: x.qa.runs }, (_, i) => ({ n: i + 1, value: i === x.qa.runs - 1 ? m.gate : "pending", score: i === x.qa.runs - 1 ? m.score : null }));
    const pills = [];
    hist.forEach((r, i) => {
      const ok = r.value === "passed" || r.value === "skipped";
      pills.push({ cls: ok ? "ok" : "bad", text: `R${r.n} ${ok ? "✓" : "✕"}${r.score != null ? ` ${r.score}` : ""}`,
        title: `Round ${r.n}: ${ok ? "passed" : "failed"}${r.score != null ? ` with ${r.score}` : ""}${i === hist.length - 1 && !ok ? ` · ${qaReason(x.qa, m)}` : ""}` });
    });
    if (x.fixes.length) {
      const done = x.fixes.length - x.fixOpen.length;
      pills.push({ cls: x.fixBlocked.length ? "bad" : x.fixOpen.length ? "run" : "ok",
        text: `${done}/${plural(x.fixes.length, "fix", "fixes")}${x.fixBlocked.length ? ` · ${x.fixBlocked.length} blocked` : x.fixOpen.length ? "" : " ✓"}`,
        title: x.fixBlocked.length ? `${x.fixBlocked.length} fix task(s) blocked: the agreed limit was reached` : x.fixOpen.length ? `${x.fixOpen.length} fix task(s) still open` : "All fix tasks done" });
    }
    if (!x.passed && x.ts.length && !x.buildOpen.length) {
      if (x.running) pills.push({ cls: "run", text: `R${x.round} ●`, title: `Round ${x.round} is running now` });
      else if (x.exhausted) pills.push({ cls: "bad", text: "decide", title: "The agreed limit was reached: keep fixing, accept with an ADR, or replan" });
      else if (!x.fixOpen.length) pills.push({ cls: "next", text: `R${x.round} next`, title: `Round ${x.round} has not started yet` });
    }
    return pills;
  }
  function stagesOf(m) {
    const ts = tasksOf(m);
    const lc = data.lifecycle || {};
    const build = ts.filter((t) => !isFix(t));
    const buildOpen = build.filter((t) => t.status !== "done");
    const x = qaState(m);
    const passed = x.passed;
    const smokeOn = lc.local_deploy && lc.local_deploy !== "off";
    const deployOn = lc.deploy_when === "per_milestone";
    const dep = m.deploy;
    const st = [];
    st.push({ key: "plan", name: "Plan", state: ts.length ? "done" : "current",
      note: ts.length ? plural(ts.length, "task") : "Run", cmd: ts.length ? null : "/dev-kit:plan", tasks: [] });
    st.push({ key: "build", name: "Build", tasks: build,
      state: !ts.length ? "upcoming" : buildOpen.length ? "current" : "done",
      note: build.length ? `${build.length - buildOpen.length}/${build.length} done` : "No tasks" });
    // QA and its fixes are one loop: audit → fix → audit again, until the gate passes
    const qaCmd = `/dev-kit:qa ${m.id}`;
    let qaNote, qaCmdShown = null, qaStateName;
    if (passed) { qaStateName = "done"; qaNote = m.gate === "skipped" ? "Skipped" : `Passed${m.score != null ? ` · ${m.score}` : ""}${x.qa.runs > 1 ? ` in round ${x.qa.runs}` : ""}`; }
    else if (!ts.length || buildOpen.length) { qaStateName = "upcoming"; qaNote = "After the build"; }
    else if (x.running) {
      qaStateName = "current";
      const r = x.qa.round;
      qaNote = `Round ${x.round} running` + (r && r.spawned ? ` · ${r.done.length} of ${r.spawned} auditors done` : "");
    } else if (x.exhausted) {
      qaStateName = "failed";
      qaNote = x.qa.runs > x.max ? `${x.qa.runs - 1} fix rounds used of ${x.max}: needs your decision`
        : `${plural(x.fixBlocked.length, "fix", "fixes")} did not hold twice: needs your decision`;
    } else if (x.fixActive.length) { qaStateName = "current"; qaNote = `Fixing round ${x.qa.runs}: ${x.fixes.length - x.fixOpen.length}/${x.fixes.length} done · ${qaReason(x.qa, m)}`; }
    else if (skillRuns().some((r) => r.skill === "autopilot")) { qaStateName = "current"; qaNote = `${x.qa.runs ? "Fixes" : "Tasks"} done; autopilot runs QA round ${x.round} next`; }
    else if (x.qa.runs) { qaStateName = "current"; qaNote = `Fixes done; round ${x.round} not started. Run`; qaCmdShown = qaCmd; }
    else { qaStateName = "current"; qaNote = "Tasks done; round 1 not started. Run"; qaCmdShown = qaCmd; }
    st.push({ key: "qa", name: "QA & fixes", tasks: x.fixes, agents: x.agents, state: qaStateName, note: qaNote, cmd: qaCmdShown,
      trail: qaTrail(m, x), decide: x.exhausted && !x.fixBlocked.length });
    st.push({ key: "smoke", name: "Smoke test", tasks: [],
      state: !smokeOn ? "na" : m.preview ? "done" : "upcoming",
      note: !smokeOn ? "Local preview off" : m.preview ? (m.preview.pid != null ? "Preview running" : "Passed") : passed ? "Not recorded" : "Runs inside QA" });
    const deploying = passed && runsAt("prod").length > 0;  // a deploy runs now (this milestone is past its gate)
    st.push({ key: "deploy", name: "Deploy", tasks: [], running: deploying,
      state: deploying ? "current" : !deployOn ? "na" : dep && dep.status === "ok" ? "done" : dep ? "failed" : passed ? "current" : "upcoming",
      note: deploying ? "Running now" : !deployOn ? (lc.deploy_when === "on_release" ? "At release" : "Not per milestone")
        : dep && dep.status === "ok" ? `${(dep.sha || "").slice(0, 7)}${dep.at && Number.isFinite(parseT(dep.at)) ? ` · ${fmtDate(parseT(dep.at))}` : ""}`
        : dep ? stLabel(dep.status) : passed ? "Waiting for" : "After the gate",
      cmd: !deploying && deployOn && passed && !(dep && dep.status === "ok") ? "/dev-kit:deploy" : null });
    const closed = passed && (!deployOn || (dep && dep.status === "ok"));
    st.push({ key: "close", name: "Closed", tasks: [], state: closed ? "done" : "upcoming",
      note: closed ? (m.passed_at && Number.isFinite(parseT(m.passed_at)) ? fmtDate(parseT(m.passed_at)) : "Milestone closed") : "" });
    // one stage is "where we are": the first current or failed one
    const here = st.find((y) => y.state === "current" || y.state === "failed");
    if (here) here.here = true;
    return st;
  }
  const STAGE_ICON = { done: "✓", current: "●", upcoming: "○", failed: "✕", na: "–" };
  const STAGE_WORD = { done: "done", current: "in progress", upcoming: "not started", failed: "failed", na: "does not apply" };
  function runChip(t) {
    return h("button", { type: "button", class: "run-chip", "data-tid": t.id, title: `${t.id} ${t.title}. Open details`, onclick: () => openTask(t.id) },
      h("span", { class: "tid", text: t.id }), h("span", { class: "run-title", text: t.title }), agentsOn(t.id).slice(0, 2).flatMap((a) => agentBits(a)));
  }
  function renderStages(m) {
    const box = $("stages");
    if (!m) {
      fill(box, h("li", { class: "stage-empty card-sub", text: "Stages appear once the plan has milestones." }));
      $("stages-sub").textContent = ""; $("also-running").hidden = true;
      return;
    }
    const st = stagesOf(m);
    const here = st.find((x) => x.here);
    const closed = st.at(-1).state === "done";
    $("stages-sub").textContent = closed ? `${m.id} is closed` : here ? `${m.id} is in ${here.name}${here.key === "qa" && qaState(m).running ? ` · round ${qaState(m).round} running` : ""}` : "";
    const shown = new Set();
    fill(box, st.map((x) => {
      const running = x.tasks.filter((t) => t.status === "in_progress");
      const blocked = x.tasks.filter((t) => t.status === "blocked");
      running.forEach((t) => shown.add(t.id));
      const chips = [...running.map(runChip), ...(x.agents || []).map((a) => h("span", { class: "run-chip auditor", title: roleOf(a.agent).about || a.agent }, agentBits(a, true)))];
      let nextBtn = null;
      if (x.here && !chips.length) {
        const nt = data.next && data.next.task && data.tasks[data.next.task];
        if (nt && nt.milestone === m.id && x.tasks.some((t) => t.id === data.next.task)) {
          nextBtn = h("button", { type: "button", class: "next-btn", "data-tid": data.next.task, onclick: () => openTask(data.next.task) },
            h("span", { class: "chip next-chip", text: "next up" }), h("span", { class: "tid", text: data.next.task }), h("span", { class: "run-title", text: nt.title }));
        }
      }
      const isRun = x.running || (x.key === "qa" && qaState(m).running);
      return h("li", { class: `chev stage st-${x.state}${x.here ? " here" : ""}${isRun ? " running" : ""}`, "aria-current": x.here ? "step" : null },
        h("div", { class: "stage-top" }, h("span", { class: "stage-ico", "aria-hidden": "true", text: STAGE_ICON[x.state] }),
          h("span", { class: "stage-name", text: x.name }), isRun ? h("span", { class: "lc-run" }, h("span", { class: "rn-dot", "aria-hidden": "true" }), "running") : null,
          h("span", { class: "visually-hidden", text: `: ${STAGE_WORD[x.state]}${isRun ? ", running now" : ""}.` })),
        x.note ? h("span", { class: "stage-note" }, x.note, x.cmd ? [" ", cmd(x.cmd)] : null,
          x.key === "qa" && hasDoc(`qa/${m.id}/report.md`) ? [" ", docLink(`qa/${m.id}/report.md`, "report")] : null) : null,
        x.trail && x.trail.length ? h("ol", { class: "qa-trail", "aria-label": "QA rounds" },
          x.trail.map((p, i) => h("li", { class: `qa-pill ${p.cls}`, title: p.title }, i ? h("span", { class: "qa-arrow", "aria-hidden": "true", text: "→" }) : null,
            h("span", { class: "qa-tag", text: p.text }), h("span", { class: "visually-hidden", text: `: ${p.title}.` })))) : null,
        x.decide ? h("button", { type: "button", class: "stage-blocked", text: "Needs your decision", onclick: goNeeds }) : null,
        blocked.length ? h("button", { type: "button", class: "stage-blocked", text: `⛔ ${blocked.length} blocked`, onclick: goNeeds }) : null,
        chips.length ? h("div", { class: "stage-run" }, chips) : null, nextBtn);
    }));
    // anything running outside this milestone's stages stays visible
    const elsewhere = Object.entries(data.tasks).filter(([id, t]) => t.status === "in_progress" && !shown.has(id)).map(([id, t]) => runChip({ id, ...t }));
    const taskIds = new Set(Object.keys(data.tasks));
    activeAgents().filter((a) => !(a.node && (taskIds.has(a.node) || a.node === `GATE:${m.id}`))).forEach((a) =>
      elsewhere.push(h("span", { class: "run-chip", title: `${roleOf(a.agent).about || a.agent}${a.node ? "" : ". Not linked to a task or a QA gate"}` },
        a.node ? h("span", { class: "tid", text: a.node.replace("GATE:", "QA ") }) : h("span", { class: "unlinked", text: "not linked" }), agentBits(a, true))));
    const also = $("also-running");
    also.hidden = !elsewhere.length;
    fill(also, elsewhere.length ? [h("span", { class: "also-label", text: "Running outside this milestone" }), ...elsewhere] : []);
  }

  function renderFeed() {
    fill($("log-link"), hasDoc("log.md") ? docLink("log.md", "Full log") : null);
    fill($("feed"), data.log.length ? data.log.map((r) => {
      const t = parseT(r.at);
      return h("li", { class: r.kind === "live" ? "feed-live" : null }, h("time", { datetime: r.at, title: Number.isFinite(t) ? fmtDT(t) : r.at, text: Number.isFinite(t) ? agoShort(t) : r.at }),
        h("span", { class: "txt" }, linkify(r.text)));
    }) : h("li", {}, h("span", { class: "txt", text: "No activity logged yet." })));
    const b = data.board;
    fill($("foot"), `${actionsOn() ? "View" : "Read-only view"} of ${data.project}/.dev${actionsOn() ? " · requests run by Claude Code" : ""} · autonomy ${data.autonomy || "?"}`,
      b ? ` · server pid ${b.pid} on port ${b.port}` : "", " · stop it from the ⋯ menu or with ", cmd("/dev-kit:board stop"));
  }

  // ------------------------------------------------------------------ insights: quality (definition of done) and backlog
  function dodRow(name, score, cut, verdict, links) {
    const mm = h("div", { class: "meter" });
    const sp = h("span"); sp.style.width = `${score != null ? Math.min(100, score) : 0}%`;
    const c = h("span", { class: "cut", title: `cut-off ${cut}` }); c.style.left = `calc(${cut}% - 1px)`;
    mm.append(sp, c);
    const ok = verdict === "pass" || verdict === "passed" || verdict === "skipped" || verdict === "n/a";
    const bad = verdict === "fail" || (score != null && score < cut && !ok);
    return h("div", { class: "dod-row" }, h("span", { class: "name" }, name, " ",
      h("span", { class: `badge ${ok ? "good" : bad ? "bad" : "neutral"}`, text: ok ? `✓ ${verdict}` : bad ? "✕ below cut-off" : verdict || "pending" }),
      links && links.length ? h("span", { class: "dod-links" }, links) : null),
      h("span", { class: "score", text: score != null ? `${score} / ${cut}` : `— / ${cut}` }), mm);
  }

  // the document a review judged, and the review's own report when there is one
  const REVIEW_DOCS = { prd: ["prd.md"], design: ["design/ux-flows.md", "design/ui-spec.md"], plan: ["plan.md"], ux: [], docs: [] };
  function reviewDocs(k) {
    const links = (REVIEW_DOCS[k] || []).filter(hasDoc).map((p) => docLink(p, DOC_NAME[p] || p));
    const report = k === "ux" ? "qa/ux/report.md" : `reviews/${k}/report.md`;
    if (hasDoc(report)) links.push(docLink(report, "report"));
    return links;
  }
  /** Review rows (score against its cut-off) for the given review keys, then the ones not run yet. */
  function reviewList(keys, emptyText) {
    const q = data.quality;
    const rname = (k) => REVIEW_NAME[k] || (k.length <= 3 ? k.toUpperCase() : k[0].toUpperCase() + k.slice(1));
    const started = (v) => v.score != null || (v.verdict && v.verdict !== "pending");
    const rows = [], pend = [];
    keys.forEach((k) => {
      const v = data.reviews[k] || {};
      if (started(v)) rows.push(dodRow(rname(k), v.score ?? null, k === "ux" ? q.min_overall : q.review_min_overall, v.verdict, reviewDocs(k)));
      else pend.push(rname(k));
    });
    return h("div", {}, rows.length ? h("div", { class: "list" }, rows) : null,
      pend.length ? h("p", { class: "pending-line", text: `Not run yet: ${pend.join(", ")}` }) : null,
      !rows.length && !pend.length ? h("div", { class: "empty", text: emptyText }) : null);
  }
  const OWN_REVIEWS = ["prd", "design", "plan", "ux", "docs"];
  const cutoffNote = () => `Cut-off: reviews ${data.quality.review_min_overall} · usability ${data.quality.min_overall}. Rows show the score against its cut-off mark.`;

  /** Construction › Gates: the QA gate of every milestone that ran one. */
  function renderGates() {
    const q = data.quality;
    $("dod-sub").textContent = `Cut-off ${q.min_overall} overall · ${q.min_dimension} per dimension. Rows show the score against its cut-off mark.`;
    const gStarted = (m) => m.score != null || m.gate !== "pending";
    const rows = data.milestones.filter(gStarted).map((m) => dodRow(`${m.id} ${m.title || ""}`, m.score ?? null, q.min_overall, m.gate === "pending" ? "fail" : m.gate,
      [`qa/${m.id}/report.md`, `qa/${m.id}/risk-report.md`].filter(hasDoc).map((p) => docLink(p, p.endsWith("risk-report.md") ? "risk report" : "report")))).reverse();
    const pending = data.milestones.filter((m) => !gStarted(m)).map((m) => m.id);
    fill($("dod"), rows.length ? h("div", { class: "list" }, rows) : !pending.length ? h("div", { class: "empty", text: "No milestones yet." }) : null,
      pending.length ? h("p", { class: "pending-line", text: `Not run yet: ${pending.join(", ")}` }) : null);
  }

  const issueId = (id) => (hasDoc("issues.md") ? docLink("issues.md", String(id), String(id), "id") : h("span", { class: "id", text: String(id) }));
  const issueLi = (i) => h("li", {}, issueId(i.id), h("span", { text: i.title || "" }),
    h("span", { class: `chip${i.c === "expedite" ? " lane-hotfix" : ""}`, text: i.c || i.status }),
    h("span", { class: "sub", text: [i.type, i.severity, i.origin === "baseline" ? "pre-existing" : null, i.scheduled_in ? `→ ${i.scheduled_in}` : null, i.c && i.status && i.c !== i.status ? i.status : null].filter(Boolean).join(" · ") }));
  /** Planning › Backlog: the issue queue by class of service, the issues already scheduled, and what later milestones hold. */
  function renderBacklog(cur) {
    const b = data.backlog || {};
    const issues = b.issues || {};
    const order = ["expedite", "current", "standard", "intangible", "change"];
    const queued = order.flatMap((c) => ((b.queue || {})[c] || []).map((id) => ({ id, c, ...issues[id] })));
    const scheduled = Object.entries(issues).filter(([, v]) => ["scheduled", "in_progress"].includes(v.status));
    const curIdx = data.milestones.findIndex((m) => m.id === cur);
    const later = data.milestones.slice(curIdx + 1).map((m) => ({ m, left: tasksOf(m).filter((t) => t.status !== "done").length })).filter((x) => x.left);
    const laterTasks = later.reduce((n, x) => n + x.left, 0);
    $("pb-sub").textContent = `${plural(queued.length, "queued issue")} · ${plural(laterTasks, "task")} in later milestones`;
    fill($("product-backlog"),
      listBlock("Issue queue", queued.map(issueLi), "No issues waiting.", true),
      scheduled.length ? listBlock("Scheduled issues", scheduled.map(([id, v]) => issueLi({ id, c: v.class, ...v })), "") : null,
      listBlock("Later milestones", later.slice().reverse().map(({ m, left }) => h("li", { class: "has-btn" },
        h("button", { type: "button", class: "row-btn", title: `Show ${m.id} in construction`, onclick: () => openMilestone(m.id) },
          h("span", { class: "id", text: m.id }), h("span", { text: m.title || "" }), h("span", { class: "chip", text: plural(left, "task") })))),
        "Nothing planned after the current milestone."));
  }
  /** Shows a milestone in Construction, from anywhere on the board. */
  function openMilestone(id) {
    const m = data.milestones.find((x) => x.id === id);
    const first = (relPlan().find((r) => r.status !== "released") || {}).id;
    relSel = m && m.release && m.release !== first ? m.release : null;
    selected = id; expanded = new Set(); goalOpen = false; mobileCol = null;
    setPhase("construction");
    $("main").scrollIntoView({ block: "start" });
  }

  function renderInsights(m, curId) {
    if (view === "burndown") renderBurndown(m);
    else if (view === "velocity") renderVelocity(curId);
    else if (view === "gates") renderGates();
  }

  // ------------------------------------------------------------------ phases: conception, planning, stable (construction is the milestone view above)
  /** One conception or planning step: state, why it is out of date, its files in .dev/, and the command that moves it on. */
  function stepCard(x) {
    const files = (data.artifacts || {})[x.key] || [];
    const running = runsAt(`step:${x.key}`);
    const c = x.state === "review" ? STEP_REVIEW_CMD[x.key] : ["todo", "doing", "stale"].includes(x.state) ? STEP_CMD[x.key] : null;
    return h("li", { class: `step-card s-${x.state}${running.length ? " running" : ""}` },
      runBanner(running),
      h("div", { class: "step-top" }, h("span", { class: "step-mark", "aria-hidden": "true", text: STEP_MARK[x.state] }),
        h("strong", { text: STEP_TITLE[x.key] || x.key }), h("span", { class: `chip step-st s-${x.state}`, text: STEP_WORD[x.state] })),
      h("p", { class: "card-sub", text: STEP_ABOUT[x.key] || "" }),
      x.note ? h("p", { class: "step-note", text: x.note }) : null,
      files.length ? h("p", { class: "step-files" }, files.map((f) => docLink(f, relDev(f)))) : null,
      c ? h("div", { class: "step-act" }, cmd(c)) : null);
  }
  const phaseOf = (key) => data.cycle.phases.find((p) => p.key === key) || { steps: [] };

  function renderConception() {
    fill($("conc-steps"), (phaseOf("conception").steps || []).map(stepCard));
    $("conc-rev-sub").textContent = `Cut-off ${data.quality.review_min_overall}`;
    fill($("conc-reviews"), reviewList(["prd", "design"], "No reviews."));
    const issues = Object.entries((data.backlog || {}).issues || {}).map(([id, v]) => ({ id, c: v.class, ...v }))
      .filter((i) => i.type === "change" || i.class === "change");
    const open = issues.filter((i) => !["closed", "done", "dropped"].includes(i.status));
    fill($("conc-changes"), listBlock("Open", open.map(issueLi), "No scope change waiting.", true),
      issues.length > open.length ? h("p", { class: "pending-line", text: `${issues.length - open.length} closed` }) : null);
    const adrs = data.decisions || [];
    $("conc-adr-sub").textContent = adrs.length ? `${plural(adrs.length, "decision")} from .dev/decisions.md, newest first` : "From .dev/decisions.md";
    const adrLi = (d) => h("li", { class: /supersed/i.test(d.status || "") ? "muted" : null }, docLink("decisions.md", d.id, d.id, "id"), h("span", { text: d.title }),
      h("span", { class: "chip", text: d.status || "?" }), d.date ? h("span", { class: "sub", text: d.date }) : null);
    const SHOWN = 6;
    fill($("conc-adrs"), adrs.length ? [h("ul", { class: "list" }, adrs.slice(0, SHOWN).map(adrLi)),
      adrs.length > SHOWN ? h("details", { class: "more-list" }, h("summary", { text: `Show ${adrs.length - SHOWN} older` }), h("ul", { class: "list" }, adrs.slice(SHOWN).map(adrLi))) : null]
      : h("div", { class: "empty", text: "No decision recorded yet. The interview and architecture write them." }));
  }

  // the CSP forbids style attributes: the width goes through the CSSOM
  const roadMeter = (x) => { const bar = h("span"); bar.style.width = `${x.total ? Math.round((x.done / x.total) * 100) : 0}%`; return h("span", { class: "road-meter", "aria-hidden": "true" }, bar); };
  function renderPlanning() {
    fill($("pl-step"), (phaseOf("planning").steps || []).map(stepCard));
    fill($("pl-review"), reviewList(["plan"], ""));
    renderBacklog(data.current_milestone);
    fillRunSlot("run-backlog", "backlog");
    const ms = data.milestones;
    const closed = ms.filter((m) => m.gate === "passed" || m.gate === "skipped").length;
    $("road-sub").textContent = ms.length ? `${closed} of ${plural(ms.length, "milestone")} closed. Open one to see it in construction.` : "";
    const row = (m) => {
      const x = milestoneInfo(m);
      const done = m.gate === "passed" || m.gate === "skipped";
      return h("li", {}, h("button", { type: "button", class: `road-row${done ? " done" : ""}${m.id === data.current_milestone ? " cur" : ""}`, onclick: () => openMilestone(m.id) },
        h("span", { class: done ? "tab-ok" : `tab-dot ${x.active ? "active" : m.gate}`, "aria-hidden": "true", text: done ? "✓" : null }),
        h("strong", { class: "id", text: m.id }),
        h("span", { class: "road-text" }, h("span", { class: "road-title", text: m.title || m.id }), m.goal ? h("span", { class: "road-goal", text: m.goal }) : null),
        m.id === data.current_milestone ? h("span", { class: "tab-current", text: "current" }) : null,
        h("span", { class: "road-count", text: `${x.done}/${x.total}` }),
        roadMeter(x)));
    };
    // lists show milestones newest first (the chevron strips and the charts keep time order)
    const rp = relPlan();
    const newest = ms.slice().reverse();
    const byRel = rp.length ? newest.filter((m) => !rp.some((r) => r.milestones.includes(m.id))).map(row)
      .concat(rp.slice().reverse().flatMap((r) => [h("li", { class: `road-rel s-${r.status}` }, h("strong", { text: r.id }), h("span", { text: r.title }),
        h("span", { class: "chip", text: REL_WORD[r.status] })), ...newest.filter((m) => r.milestones.includes(m.id)).map(row)]))
      : newest.map(row);
    $("road-sub").textContent += rp.length ? ` ${plural(rp.length, "planned release")}: each waits for your approval before production.` : "";
    fill($("roadmap"), ms.length ? byRel : h("li", { class: "empty" }, "No milestones yet. They appear after ", cmd("/dev-kit:plan"), "."));
  }

  /** Construction › Next release: the closed milestones waiting for a release and what the release still needs. */
  function renderTrain() {
    fillRunSlot("run-train", ["release", "checks"]);
    const tr = data.cycle.release || {};
    const word = { done: "✓ done", todo: "○ to do", review: "◐ waiting for its review", "n/a": "– not needed" };
    const r = relShown();
    if (runsAt("release").length || runsAt("checks").length) $("train-card").hidden = false;
    if (r) {
      // planned releases: the release shown, what it still needs, and the decision when it waits for the user
      $("train-card").hidden = false;
      $("train-h").textContent = `${r.id} · ${r.title}`;
      $("train-sub").textContent = REL_WORD[r.status] + (r.rounds ? ` · ${plural(r.rounds, "rejection")} so far` : "");
      const isNext = tr.release === r.id;
      const last = (r.history || []).filter((x) => x.event === "rejected").at(-1);
      fill($("train"),
        h("span", { class: "train-ms" }, r.milestones.map((id) => { const m = data.milestones.find((x) => x.id === id);
          const ok = m && (m.gate === "passed" || m.gate === "skipped");
          return h("button", { type: "button", class: `chip train-chip${ok ? " ok" : ""}`, text: `${ok ? "✓ " : ""}${id}`, title: `Show ${id}${m && m.title ? ` · ${m.title}` : ""}`, onclick: () => openMilestone(id) }); })),
        isNext && tr.usability && r.status === "ready_for_review" ? h("span", { class: `train-check s-${tr.usability}` }, `Usability ${word[tr.usability] || tr.usability}`) : null,
        isNext && tr.docs && r.status === "ready_for_review" ? h("span", { class: `train-check s-${tr.docs}` }, `Docs ${word[tr.docs] || tr.docs}`) : null,
        r.dossier ? h("span", { class: "train-check" }, docLink(r.dossier, "Dossier")) : null,
        last ? h("span", { class: "train-check" }, `Last rejection → ${last.milestone}`) : null,
        r.status === "ready_for_review" ? cmd("/dev-kit:release") : null,
        r.status === "awaiting_approval" ? releaseDecision(r) : null);
      return;
    }
    $("train-h").textContent = "Next release";
    const waiting = tr.milestones || [];
    const busy = runsAt("release").length || runsAt("checks").length;
    $("train-card").hidden = !waiting.length && !busy;
    if (!waiting.length) { $("train-sub").textContent = ""; fill($("train")); return; }
    $("train-sub").textContent = tr.ready ? "Ready to cut" : `After ${(tr.waiting_for || []).join(", ") || "the open work"}`;
    fill($("train"),
      h("span", { class: "train-ms" }, waiting.map((id) => h("button", { type: "button", class: "chip train-chip", text: id, title: `Show ${id}`, onclick: () => openMilestone(id) }))),
      tr.usability ? h("span", { class: `train-check s-${tr.usability}` }, `Usability ${word[tr.usability] || tr.usability}`) : null,
      tr.docs ? h("span", { class: `train-check s-${tr.docs}` }, `Docs ${word[tr.docs] || tr.docs}`) : null,
      tr.ready ? cmd("/dev-kit:release") : null);
  }

  function renderStable() {
    const p = data.progress, c = data.costs, ms = data.milestones, rel = data.releases || [];
    const closed = ms.filter((m) => m.gate === "passed" || m.gate === "skipped").length;
    $("st-sum-sub").textContent = data.phase === "stable" ? "Stable: nothing open, everything released" : `Not stable yet: the project is in ${PHASE_NAME[data.phase]}`;
    const fact = (label, value, extra) => h("div", { class: "fact" }, h("span", { class: "fact-label", text: label }), h("strong", { class: "fact-value", text: value }), extra || null);
    fill($("st-summary"),
      fact("Tasks done", `${p.done}/${p.total}`),
      fact("Milestones closed", `${closed}/${ms.length}`),
      fact("Releases", String(rel.length), rel.length ? h("span", { class: "card-sub", text: `last ${rel.at(-1).tag || rel.at(-1).version || ""}` }) : null),
      c && (Number(c.usd) > 0 || Number(c.tokens) > 0) ? fact("Cost (estimate)", `US$ ${Number(c.usd || 0).toFixed(2)}`, h("span", { class: "card-sub", text: `${compact(c.tokens || 0)} tokens` }))
        : fact("Cost", "not computed", h("span", { class: "fact-cmd" }, copyBtn("/dev-kit:costs"))));
    fillRunSlot("run-prod", "prod");
    fillRunSlot("run-checks", "checks");
    fillRunSlot("run-releases", "release");
    // production
    const pr = data.production, lc = data.lifecycle || {};
    const when = { per_milestone: "after each milestone", on_release: "at each release", manual: "by hand", none: "no production environment" };
    $("st-prod-sub").textContent = `Deploys ${when[lc.deploy_when] || lc.deploy_when || "?"}`;
    if (!pr) fill($("st-prod"), h("div", { class: "empty", text: lc.deploy_when === "none" ? "This project has no production deploy." : "No production deploy recorded yet." }),
      lc.deploy_when && lc.deploy_when !== "none" ? h("p", { class: "pending-line" }, "Deploy with ", cmd("/dev-kit:deploy")) : null);
    else {
      const cur = pr.current, last = pr.last;
      fill($("st-prod"), h("ul", { class: "list" },
        cur ? h("li", {}, h("span", { class: "id", text: (cur.sha || "").slice(0, 7) }), h("span", { text: cur.milestone ? `Running ${cur.milestone}` : "Running" }),
          h("span", { class: "badge good", text: "✓ ok" }), h("span", { class: "sub", text: [cur.at && Number.isFinite(parseT(cur.at)) ? fmtDT(parseT(cur.at)) : null, cur.migration ? `migration ${cur.migration}` : null].filter(Boolean).join(" · ") })) : null,
        last && last.status !== "ok" ? h("li", {}, h("span", { class: "id", text: (last.sha || "").slice(0, 7) }), h("span", { text: "Last attempt" }),
          h("span", { class: "badge bad", text: stLabel(last.status) }), h("span", { class: "sub", text: last.at && Number.isFinite(parseT(last.at)) ? fmtDT(parseT(last.at)) : "" })) : null),
      pr.drift ? h("p", { class: "pending-line", text: pr.drift }) : null);
    }
    // release checks: usability and docs reviews, and any other review the project recorded
    const others = Object.keys(data.reviews).filter((k) => !OWN_REVIEWS.includes(k));
    $("st-rev-sub").textContent = cutoffNote();
    fill($("st-reviews"), reviewList(["ux", "docs", ...others], "No checks."));
    fill($("st-releases"), rel.length ? h("ul", { class: "list" }, rel.slice().reverse().map((r) => h("li", {},
      hasDoc(`release-notes-${r.version}.md`) ? docLink(`release-notes-${r.version}.md`, r.tag || r.version, null, "id") : h("span", { class: "id", text: r.tag || r.version || "release" }),
      h("span", { text: (r.release ? `${r.release} · ` : "") + (r.hotfix ? `Hotfix ${r.hotfix}` : (r.milestones || []).join(", ") || "—") }),
      h("span", { class: "chip", text: r.version || "" }), r.at && Number.isFinite(parseT(r.at)) ? h("span", { class: "sub", text: fmtDate(parseT(r.at)) }) : null)))
      : h("div", { class: "empty", text: "No release yet. Closed milestones wait in Construction › Next release." }));
  }

  function tickAgents() {
    document.querySelectorAll(".agent-time[data-start]").forEach((el) => { el.textContent = dur((Date.now() - parseT(el.dataset.start)) / 1000); });
  }
  setInterval(tickAgents, 1000);

  // ------------------------------------------------------------------ requests to Claude Code (dev_worker.py on the server, /dev-kit:worker runs them)
  // the commands the server accepts (dev_worker.RUN_COMMANDS); anything else keeps only its copy button
  const RUN_RES = [/^\/dev-kit:implement(?: (?:T-\d{3,5}|--milestone M\d{1,3}))?$/, /^\/dev-kit:qa M\d{1,3}$/, /^\/dev-kit:review (?:prd|design|plan|docs)$/,
    /^\/dev-kit:(?:interview|prd|architecture|ux|ui|plan|docs|usability|costs|backlog|status|release)$/, /^\/dev-kit:interview --gaps$/, /^\/dev-kit:deploy(?: M\d{1,3})?$/];
  const EMPTY_INBOX = { open: [], recent: [], executor: { state: "offline", online: false, paused: false }, approvals: [], actions: false };
  const inbox = () => (data && data.inbox) || EMPTY_INBOX;
  const actionsOn = () => Boolean(inbox().actions);
  function runnable(c) { return actionsOn() && RUN_RES.some((r) => r.test(c)); }
  const openRun = (c) => inbox().open.find((x) => x.action === "run" && x.args && x.args.command === c);
  let toastT = null;
  function toast(text, bad) {
    const el = $("toast");
    el.textContent = text;
    el.classList.toggle("bad", Boolean(bad));
    el.hidden = false;
    clearTimeout(toastT);
    toastT = setTimeout(() => { el.hidden = true; }, bad ? 9000 : 5000);
  }
  async function api(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Board-Token": TOKEN }, body: JSON.stringify(body || {}) });
    let d = {};
    try { d = await r.json(); } catch (e) { /* no body */ }
    if (!r.ok) {
      const err = new Error((d.errors && d.errors.join("; ")) || d.hint || d.error || `HTTP ${r.status}`);
      err.errors = d.errors || [err.message];
      throw err;
    }
    return d;
  }
  const takesIt = (ex) => Boolean(ex.listening || (ex.online && ex.state === "running"));
  const workerHint = () => (takesIt(inbox().executor) ? "Claude Code takes it." : "Run /dev-kit:worker in Claude Code to start it.");
  async function queue(action, args, quietErrors) {
    try {
      const d = await api("/api/inbox", { action, args });
      toast(`Queued ${d.item.id}. ${workerHint()}`);
      load();
      return d.item;
    } catch (e) {
      if (!quietErrors) toast(`Not queued: ${e.message}`, true);
      throw e;
    }
  }
  function runBtn(text) {
    const q = openRun(text);
    const label = q ? `${text} is queued (${q.id}, ${stLabel(q.status)})` : `Run ${text} in Claude Code`;
    const btn = h("button", { type: "button", class: `run-btn${q ? " queued" : ""}`, title: label, "aria-label": label, disabled: q ? true : null }, q ? "◷" : "▶");
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      btn.disabled = true;
      try { await queue("run", { command: text }); } catch (err) { btn.disabled = false; }
    });
    return btn;
  }
  function describeReq(x) {
    const a = x.args || {};
    if (x.action === "run") return h("code", { text: a.command || "" });
    if (x.action === "issue_new") return `New ${a.type === "improvement" ? "improvement" : a.type === "change" ? "change" : "bug"}: ${a.title || ""}`;
    if (x.action === "answer_question") return `Answer to ${a.question}: ${a.option || a.answer || ""}`;
    if (x.action === "plan_draft") return `Plan draft · ${plural((a.ops || []).length, "change")}`;
    if (x.action === "release_decision") return `${a.decision === "approve" ? "Approve" : "Reject"} ${a.release}`;
    return x.action;
  }
  const REQ_WORD = { pending: "waiting", running: "running", needs_input: "needs your answer", done: "done", failed: "failed", cancelled: "cancelled", stale: "stopped" };
  function execLabel(ex) {
    const runs = skillRuns();
    if (!ex.online && !runs.length) return ["off", "Claude Code: not running"];
    if (ex.paused) return ["paused", "Claude Code: paused"];
    if (ex.state === "running") return ["on", `Claude Code: working${ex.item ? ` on ${ex.item}` : ""}`];
    if (ex.listening) return ["on", "Claude Code: listening"];
    if (runs.length) return ["on", `Claude Code: running ${runCmd(runs[runs.length - 1])}; requests wait for it`];
    return ["idle", "Claude Code: open, not listening"];
  }
  function renderRequests() {
    const ib = inbox();
    const card = $("req-card");
    card.hidden = !ib.actions && !ib.open.length && !ib.recent.length;
    if (card.hidden) return;
    const [cls, word] = execLabel(ib.executor);
    const ex = $("exec");
    ex.className = `exec ${cls}`;
    ex.textContent = word;
    $("new-issue-btn").hidden = !ib.actions;
    const pb = $("pause-btn");
    pb.hidden = !ib.actions;
    pb.setAttribute("aria-pressed", String(Boolean(ib.executor.paused)));
    pb.textContent = ib.executor.paused ? "Resume queue" : "Pause queue";
    const cb = $("cont-btn");
    cb.hidden = !ib.actions;
    cb.setAttribute("aria-pressed", String(Boolean(ib.executor.continuous)));
    const waiting = ib.open.filter((x) => x.status === "pending").length;
    const stopped = ib.executor.continuous && ib.executor.continuous_stopped;
    const line = (...kids) => h("span", { class: "hint-line" }, kids);
    fill($("req-hint"),
      !ib.actions ? line("This board only shows the project: requests are off (start it with --actions on).") : null,
      ib.actions && !takesIt(ib.executor) && waiting ? line(`${plural(waiting, "request")} waiting. In Claude Code, run `, h("span", { class: "cmd" }, h("code", { text: "/dev-kit:worker" }), copyBtn("/dev-kit:worker"))) : null,
      ib.actions && !ib.executor.online && !waiting ? line("No Claude Code session is listening. Run ", h("span", { class: "cmd" }, h("code", { text: "/dev-kit:board" }), copyBtn("/dev-kit:board")), " in one: requests then start by themselves.") : null,
      ib.actions && ib.executor.paused ? line("Paused: Claude Code finishes what it is doing and takes nothing new.") : null,
      ib.actions && ib.executor.continuous && !stopped ? line("Going on by itself: after each step Claude Code starts the next one, until something needs you or the milestone closes.") : null,
      stopped ? h("span", { class: "hint-line bad" }, `It stopped going on by itself: ${stopped}. `,
        h("button", { type: "button", class: "link-btn", text: "Go on", onclick: () => setContinuous(true) })) : null,
      ib.actions && !ib.open.length && !ib.recent.length ? line("Nothing queued. Use ▶ next to a command, answer a question, add an issue, or plan by dragging cards.") : null);
    const row = (x, open) => h("li", { class: `req s-${x.status}` },
      h("span", { class: "id", text: x.id }),
      h("span", { class: "req-what" }, describeReq(x)),
      h("span", { class: `chip req-st s-${x.status}`, text: x.cancel_requested ? "cancelling" : REQ_WORD[x.status] || x.status }),
      x.note ? h("span", { class: "sub", text: x.note }) : null,
      x.status === "needs_input" ? h("button", { type: "button", class: "link-btn sub", text: `Answer ${x.question || "the question"} in Needs you`, onclick: goNeeds }) : null,
      open && ib.actions && !x.cancel_requested ? h("button", { type: "button", class: "link-btn req-cancel", "aria-label": `Cancel ${x.id}`, text: "Cancel",
        onclick: async (e) => { e.currentTarget.disabled = true; try { await api(`/api/inbox/${x.id}/cancel`, {}); toast(`${x.id}: ${x.status === "running" ? "Claude Code stops at the next safe point" : "cancelled"}.`); load(); } catch (err) { toast(err.message, true); } } }) : null);
    fill($("req-list"), ib.open.map((x) => row(x, true)), ib.recent.slice(0, 6).map((x) => row(x, false)));
    const nx = data.next && data.next.command;
    fill($("ms-next"), nx ? ["Next step: ", cmd(nx)] : null);
  }
  $("pause-btn").addEventListener("click", async () => {
    const paused = !inbox().executor.paused;
    try { await api("/api/worker/mode", { paused }); toast(paused ? "Queue paused." : "Queue resumed."); load(); } catch (e) { toast(e.message, true); }
  });
  async function setContinuous(on) {
    try {
      await api("/api/worker/mode", { continuous: on });
      toast(on ? `Going on by itself. ${takesIt(inbox().executor) ? "Claude Code starts the next step." : "It starts when a Claude Code session listens (/dev-kit:board)."}`
        : "It now waits for you after each request.");
      load();
    } catch (e) { toast(e.message, true); }
  }
  $("cont-btn").addEventListener("click", () => setContinuous(!inbox().executor.continuous));

  // the tab says when something waits on the user: "(2) Needs you" in the title and a dot on the icon
  let needsN = 0;
  let seenFail = Number(store.get("board-seen-fail", "0")) || 0;
  function updateAttention() {
    if (!data || !data.ok) return;
    const fails = inbox().recent.filter((x) => (x.status === "failed" || x.status === "stale") && Number(x.id.slice(2)) > seenFail);
    if (fails.length && document.visibilityState === "visible" && document.hasFocus()) {
      seenFail = Math.max(...fails.map((x) => Number(x.id.slice(2))));  // looking at the board: they have been seen
      store.set("board-seen-fail", String(seenFail));
      fails.length = 0;
    }
    const n = needsN + fails.length;
    document.title = n ? `(${n}) Needs you · ${data.project}` : `${data.project} · dev-kit board`;
    const icon = document.querySelector('link[rel="icon"]');
    const want = n ? "/assets/favicon-alert.svg" : "/assets/favicon.svg";
    if (icon && icon.getAttribute("href") !== want) icon.setAttribute("href", want);
  }
  document.addEventListener("visibilitychange", updateAttention);
  window.addEventListener("focus", updateAttention);

  // new issue: a short form; Claude Code classifies it and asks here when it needs to
  const idlg = $("issue-dialog");
  $("new-issue-btn").addEventListener("click", () => { $("issue-form").reset(); idlg.showModal(); });
  idlg.addEventListener("close", async () => {
    if (idlg.returnValue !== "send") { $("new-issue-btn").focus(); return; }
    const title = $("issue-title").value.trim();
    if (!title) return;
    try { await queue("issue_new", { title, type: $("issue-type").value, note: $("issue-note").value.trim() }); } catch (e) { /* toast shown */ }
    $("new-issue-btn").focus();
  });

  // answers to the open questions, right where they are listed
  const answerDrafts = {};
  function answerBox(q) {
    const sent = inbox().open.find((x) => x.action === "answer_question" && x.args && x.args.question === q.id);
    if (sent) return h("div", { class: "sub answer-sent", text: `Answer sent (${sent.id}): ${sent.args.option || sent.args.answer}. Claude Code applies it.` });
    const opts = (q.options || []).slice().sort((a, b) => (b === q.recommended) - (a === q.recommended));
    const box = h("div", { class: "sub answer", role: "group", "aria-label": `Answer ${q.id}` });
    const send = async (args, el) => { el.disabled = true; try { await queue("answer_question", { question: q.id, ...args }); delete answerDrafts[q.id]; } catch (e) { el.disabled = false; } };
    opts.forEach((o) => box.append(h("button", { type: "button", class: `btn btn-sm${o === q.recommended ? " btn-primary" : ""}`, onclick: (e) => send({ option: o }, e.currentTarget) },
      o, o === q.recommended ? h("span", { class: "rec", text: "recommended" }) : null)));
    if (!opts.length && q.assumption) box.append(h("button", { type: "button", class: "btn btn-sm btn-primary", onclick: (e) => send({ answer: q.assumption }, e.currentTarget) }, "Keep the assumption"));
    const inp = h("input", { type: "text", id: `ans-${q.id}`, maxlength: "2000", class: "answer-input", "aria-label": `Your answer to ${q.id}`,
      placeholder: opts.length || q.assumption ? "Or write another answer" : "Your answer" });
    inp.value = answerDrafts[q.id] || "";
    inp.addEventListener("input", () => { answerDrafts[q.id] = inp.value; });
    const go = h("button", { type: "button", class: "btn btn-sm", id: `ans-send-${q.id}`, text: "Send",
      onclick: (e) => { const v = inp.value.trim(); if (v) send({ answer: v }, e.currentTarget); else inp.focus(); } });
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); go.click(); } });
    box.append(h("span", { class: "answer-free" }, inp, go));
    return box;
  }
  const DECIDED = { allow: "Allowed", allow_session: "Allowed for this session", deny: "Denied" };
  const leftText = (ms) => (ms <= 0 ? "No answer in time: denied." : ms < 60000 ? `Denied in ${Math.ceil(ms / 1000)} s without an answer.` : `Denied in ${Math.ceil(ms / 60000)} min without an answer.`);
  function approvalRow(a) {
    const deadline = lastUpdate + (a.seconds_left || 0) * 1000;
    const decide = async (decision, el) => {
      el.disabled = true;
      try { await api(`/api/approvals/${a.id}`, { decision }); toast(`${DECIDED[decision]}: ${a.tool}.`); load(); } catch (e) { el.disabled = false; toast(e.message, true); load(); }
    };
    return h("li", {}, h("span", { class: "id", text: a.tool || "tool" }), h("span", { class: "mono-wrap", text: a.target || "" }),
      h("span", { class: "chip", text: a.request || "" }),
      h("div", { class: "sub answer", role: "group", "aria-label": `Permission for ${a.tool}` },
        h("button", { type: "button", class: "btn btn-sm btn-primary", text: "Allow", onclick: (e) => decide("allow", e.currentTarget) }),
        a.rule ? h("button", { type: "button", class: "btn btn-sm", title: `Until the Claude Code session ends, without asking again: ${a.rule}`,
          onclick: (e) => decide("allow_session", e.currentTarget) }, "Allow for this session") : null,
        h("button", { type: "button", class: "btn btn-sm btn-danger", text: "Deny", onclick: (e) => decide("deny", e.currentTarget) })),
      a.rule ? h("span", { class: "sub" }, "For this session it would allow: ", h("code", { text: a.rule })) : null,
      h("span", { class: "sub approval-left", "data-deadline": String(deadline), text: leftText(deadline - Date.now()) }));
  }
  setInterval(() => document.querySelectorAll(".approval-left[data-deadline]").forEach((el) => { el.textContent = leftText(Number(el.dataset.deadline) - Date.now()); }), 1000);

  // ------------------------------------------------------------------ plan: drag tasks and issues between open milestones, add the next milestone, send the draft
  let draft = { ops: [], base: null, serverErrors: [], buffer: false };
  const MS_NUM = (id) => Number(String(id).slice(1));
  const cmpSeq = (a, b) => ((data.tasks[a].seq ?? 1e6) - (data.tasks[b].seq ?? 1e6)) || (Number(a.slice(2)) - Number(b.slice(2)));
  const movableTask = (t) => t && t.status === "todo" && t.lane !== "hotfix";
  const issueOf = (id) => ((data.backlog || {}).issues || {})[id];
  const movableIssue = (i) => i && i.status === "open" && !["expedite", "change"].includes(i.class) && i.type !== "change";
  /** The plan as the draft leaves it: open milestones (and the new one) with their cards, the issue queue, and the problems found. */
  function planModel() {
    const ms = data.milestones.filter((m) => m.gate === "pending").map((m) => ({ id: m.id, title: m.title, isNew: false }));
    const cols = Object.fromEntries(ms.map((m) => [m.id, []]));
    Object.keys(data.tasks).filter((id) => cols[data.tasks[id].milestone] && data.tasks[id].status !== "dropped").sort(cmpSeq)
      .forEach((id) => cols[data.tasks[id].milestone].push({ kind: "task", id }));
    const queued = Object.entries((data.backlog || {}).issues || {}).filter(([, i]) => i.status === "open")
      .sort((a, b) => String(a[1].created_at || "").localeCompare(String(b[1].created_at || ""))).map(([id]) => ({ kind: "issue", id }));
    const where = {};
    Object.entries(cols).forEach(([m, l]) => l.forEach((c) => { where[c.id] = m; }));
    const problems = [];
    const take = (id) => {
      if (where[id] === "queue") { const i = queued.findIndex((c) => c.id === id); return queued.splice(i, 1)[0]; }
      const l = cols[where[id]] || [];
      const i = l.findIndex((c) => c.id === id);
      return i >= 0 ? l.splice(i, 1)[0] : null;
    };
    const put = (card, m, before) => {
      const l = cols[m];
      const i = before ? l.findIndex((c) => c.id === before) : -1;
      if (i >= 0) l.splice(i, 0, card); else l.push(card);
      where[card.id] = m;
    };
    queued.forEach((c) => { where[c.id] = "queue"; });
    draft.ops.forEach((op, n) => {
      const at = `Change ${n + 1}`;
      if (op.op === "new_milestone") { ms.push({ id: op.milestone, title: op.title, isNew: true }); cols[op.milestone] = []; return; }
      if (!cols[op.milestone]) { problems.push(`${at}: ${op.milestone} is no longer open`); return; }
      const id = op.op === "move_task" ? op.task : op.issue;
      if (op.op === "move_task" && !movableTask(data.tasks[id])) { problems.push(`${at}: ${id} is ${stLabel((data.tasks[id] || {}).status || "gone")} now; undo this change`); return; }
      if (op.op === "schedule_issue" && !movableIssue(issueOf(id))) { problems.push(`${at}: ${id} is not open any more; undo this change`); return; }
      const card = take(id);
      if (card) put(card, op.milestone, op.before);
    });
    // a task never sits in an earlier milestone than a task it depends on (done ones do not count)
    Object.entries(cols).forEach(([m, l]) => l.forEach((c) => {
      if (c.kind !== "task") return;
      (data.tasks[c.id].deps || []).forEach((d) => {
        const dt = data.tasks[d];
        if (dt && dt.status !== "done" && where[d] && where[d] !== "queue" && MS_NUM(where[d]) > MS_NUM(m)) problems.push(`${c.id} depends on ${d}, which would be in a later milestone (${where[d]})`);
      });
    }));
    return { ms, cols, queued, where, problems };
  }
  function addOp(op) {
    if (!draft.ops.length) draft.base = data.updated_at;
    draft.ops.push(op);
    draft.serverErrors = [];
    draft.buffer = false;
    renderPlan();
  }
  function moveCard(card, m, beforeId, model) {
    const l = model.cols[m] || [];
    // a draft anchors on tasks only: an issue scheduled in the draft has no task id yet
    let before = null;
    if (beforeId) {
      const i = l.findIndex((c) => c.id === beforeId);
      before = (l.slice(i).find((c) => c.kind === "task" && c.id !== card.id) || {}).id || null;
    }
    if (card.kind === "task") {
      if (model.where[card.id] === m && !beforeId && l[l.length - 1] && l[l.length - 1].id === card.id) return;
      addOp({ op: "move_task", task: card.id, milestone: m, ...(before ? { before } : {}) });
    } else {
      addOp({ op: "schedule_issue", issue: card.id, milestone: m, ...(before ? { before } : {}) });
    }
    toast(`${card.id} → ${m}${before ? ` (before ${before})` : ""}. Send the draft when it is ready.`);
  }
  function describeOp(op) {
    if (op.op === "new_milestone") return `New milestone ${op.milestone} · ${op.title}`;
    if (op.op === "move_task") return `${op.task} → ${op.milestone}${op.before ? ` (before ${op.before})` : ""}`;
    if (op.op === "schedule_issue") return `${op.issue} → ${op.milestone}${op.before ? ` (before ${op.before})` : ""}${op.force ? " · over the buffer" : ""}`;
    return op.op;
  }
  let dragging = null;
  function planCard(c, model, m) {
    const isTask = c.kind === "task";
    const x = isTask ? data.tasks[c.id] : issueOf(c.id);
    if (!x) return null;
    const movable = isTask ? movableTask(x) : movableIssue(x);
    const targets = model.ms.map((t) => t.id);
    const sel = movable ? h("select", { class: "move-sel", "aria-label": `Move ${c.id}`, id: `mv-${c.id}` },
      h("option", { value: "", text: "Move…" }),
      isTask && m ? [h("option", { value: "up", text: "↑ Up" }), h("option", { value: "down", text: "↓ Down" })] : null,
      targets.filter((t) => t !== m).map((t) => h("option", { value: `to:${t}`, text: `To ${t}` }))) : null;
    if (sel) sel.addEventListener("change", () => {
      const v = sel.value;
      sel.value = "";
      if (!v) return;
      const l = model.cols[m] || [];
      const i = l.findIndex((k) => k.id === c.id);
      if (v === "up" && i > 0) moveCard(c, m, l[i - 1].id, model);
      else if (v === "down" && i >= 0 && i < l.length - 1) moveCard(c, m, l[i + 2] ? l[i + 2].id : null, model);
      else if (v.startsWith("to:")) moveCard(c, v.slice(3), null, model);
      requestAnimationFrame(() => { const el = $(`mv-${c.id}`); if (el) el.focus(); });
    });
    const el = h("li", { class: `pcard ${isTask ? `s-${x.status}` : "issue"}${movable ? " movable" : " locked"}`, "data-id": c.id, draggable: movable ? "true" : null,
      title: movable ? "Drag to another place, or use Move…" : isTask ? `${stLabel(x.status)}: only tasks not started move` : `${x.class}: goes through /dev-kit:issue` },
      h("div", { class: "tcard-top" }, h("span", { class: "tid", text: c.id }),
        isTask ? h("span", { class: "chip", text: x.type }) : h("span", { class: `chip${x.class === "expedite" ? " lane-hotfix" : ""}`, text: x.class || "issue" }),
        isTask && x.status !== "todo" ? h("span", { class: `chip st-chip s-${x.status}`, text: stLabel(x.status) }) : null,
        isTask && x.lane ? h("span", { class: `chip lane-${x.lane}`, text: x.lane }) : null,
        !isTask && x.severity ? h("span", { class: "chip", text: x.severity }) : null),
      h("div", { class: "tcard-title", text: x.title || "", title: x.title || null }),
      sel);
    if (movable) {
      el.addEventListener("dragstart", (e) => { dragging = c; e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", c.id); el.classList.add("dragging"); });
      el.addEventListener("dragend", () => { dragging = null; el.classList.remove("dragging"); document.querySelectorAll(".drop-before").forEach((n) => n.classList.remove("drop-before")); });
    }
    return el;
  }
  function dropZone(list, m, model) {
    const target = (e) => [...list.querySelectorAll(".pcard:not(.dragging)")].find((n) => { const r = n.getBoundingClientRect(); return e.clientY < r.top + r.height / 2; });
    list.addEventListener("dragover", (e) => {
      if (!dragging || (m === "queue" && dragging.kind === "task")) return;
      e.preventDefault();
      list.querySelectorAll(".drop-before").forEach((n) => n.classList.remove("drop-before"));
      const t = target(e);
      if (t) t.classList.add("drop-before");
      list.classList.add("drop-on");
    });
    list.addEventListener("dragleave", (e) => { if (!list.contains(e.relatedTarget)) { list.classList.remove("drop-on"); list.querySelectorAll(".drop-before").forEach((n) => n.classList.remove("drop-before")); } });
    list.addEventListener("drop", (e) => {
      e.preventDefault();
      list.classList.remove("drop-on");
      const card = dragging;
      if (!card) return;
      dragging = null;  // the drop re-renders the plan; renderPlan waits while a drag is in progress
      const t = target(e);
      if (m === "queue") {
        // back to the queue: undo the scheduling of this issue (the latest one)
        const i = draft.ops.map((o) => o.issue).lastIndexOf(card.id);
        if (i >= 0) { draft.ops.splice(i, 1); renderPlan(); toast(`${card.id} back in the queue.`); }
        return;
      }
      moveCard(card, m, t ? t.dataset.id : null, model);
    });
  }
  let newMsTitle = "";
  const doneOpen = new Set();  // plan columns whose done tasks are expanded, kept across live updates
  function renderPlan() {
    const box = $("planner");
    if (!planShown() || !data || !data.ok) { box.hidden = true; return; }
    if (dragging) return;  // a live update in the middle of a drag would pull the card from under the pointer
    box.hidden = false;
    // the plan is rebuilt on every update: keep where the user had scrolled to
    const lanes = box.querySelector(".plan-cols");
    const scrollX = lanes ? lanes.scrollLeft : 0;
    const scrollY = {};
    box.querySelectorAll(".pcol-list[data-key]").forEach((l) => { scrollY[l.dataset.key] = l.scrollTop; });
    const model = planModel();
    const column = (key, title, sub, cards, extra, isNew) => {
      // done tasks never move: they fold away under the open ones
      const done = cards.filter((c) => c.kind === "task" && data.tasks[c.id].status === "done");
      const open = cards.filter((c) => !done.includes(c));
      const list = h("ol", { class: "pcol-list", "data-key": key, "aria-label": `${title}, ${plural(open.length, "open card")}` }, open.map((c) => planCard(c, model, key === "queue" ? null : key)).filter(Boolean));
      if (!open.length) list.append(h("li", { class: "col-empty", text: key === "queue" ? "No open issue" : "Drop tasks or issues here" }));
      dropZone(list, key, model);
      let folded = null;
      if (done.length) {
        folded = h("details", { class: "pcol-done" }, h("summary", { text: `${plural(done.length, "task")} done` }),
          h("ol", { class: "pcol-list done-list", "aria-label": `${title}, done tasks` }, done.map((c) => planCard(c, model, key)).filter(Boolean)));
        folded.open = doneOpen.has(key);
        folded.addEventListener("toggle", () => { if (folded.open) doneOpen.add(key); else doneOpen.delete(key); });
      }
      return h("section", { class: `pcol${key === "queue" ? " queue" : ""}${isNew ? " new" : ""}`, "aria-label": key === "queue" ? "Issue queue" : `${key} ${title}` },
        h("div", { class: "col-head" }, h("strong", { text: key === "queue" ? "Issue queue" : key }), key === "queue" || title === key ? null : h("span", { class: "pcol-title", text: title, title }),
          h("span", { class: "count", title: done.length ? `${open.length} open, ${done.length} done` : null, text: !done.length ? String(open.length) : open.length ? `${open.length} · ${done.length} ✓` : `${done.length} ✓` })),
        sub ? h("p", { class: "card-sub", text: sub }) : null, list, folded, extra);
    };
    const newNum = `M${Math.max(0, ...data.milestones.map((m) => MS_NUM(m.id)), ...draft.ops.filter((o) => o.op === "new_milestone").map((o) => MS_NUM(o.milestone))) + 1}`;
    const hasNew = draft.ops.some((o) => o.op === "new_milestone");
    const b = (data.backlog || {}).buffer;
    const cols = [column("queue", "Issue queue", "Expedite and change issues go through /dev-kit:issue.", model.queued)]
      .concat(model.ms.slice().reverse().map((m) => column(m.id, m.title || m.id, m.isNew ? "New in this draft" : b && b.milestone === m.id ? `Issue buffer ${b.used}/${b.capacity}` : null, model.cols[m.id] || [], null, m.isNew)));
    if (!hasNew) {
      const inp = h("input", { type: "text", id: "new-ms-title", maxlength: "80", placeholder: `Title of ${newNum}`, "aria-label": `Title of the new milestone ${newNum}` });
      inp.value = newMsTitle;
      inp.addEventListener("input", () => { newMsTitle = inp.value; });
      const add = () => { const v = inp.value.trim(); if (!v) { inp.focus(); return; } newMsTitle = ""; addOp({ op: "new_milestone", milestone: newNum, title: v }); toast(`${newNum} added to the draft.`); };
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } });
      cols.push(h("section", { class: "pcol add" }, h("div", { class: "col-head" }, h("strong", { text: `＋ ${newNum}` })),
        h("p", { class: "card-sub", text: "The next milestone, after the others. Name it, then drag cards into it." }),
        h("div", { class: "answer-free" }, inp, h("button", { type: "button", class: "btn btn-sm", text: "Add", onclick: add }))));
    }
    const errors = model.problems.concat(draft.serverErrors);
    const sendBtn = h("button", { type: "button", class: "btn btn-primary", id: "plan-send", disabled: !draft.ops.length || model.problems.length ? true : null, text: "Send to Claude Code",
      onclick: async (e) => {
        e.currentTarget.disabled = true;
        const ops = draft.ops.map((o) => (o.op === "schedule_issue" && draft.buffer ? { ...o, force: true } : o));
        try {
          await queue("plan_draft", { ops, base: draft.base || data.updated_at }, true);
          draft = { ops: [], base: null, serverErrors: [], buffer: false };
          renderPlan();
        } catch (err) {
          draft.serverErrors = err.errors || [err.message];
          renderPlan();
        }
      } });
    const overBuffer = draft.serverErrors.some((x) => /issue buffer/.test(x));
    fill(box,
      h("div", { class: "plan-cols" }, cols),
      h("aside", { class: "plan-draft", "aria-label": "Draft of the plan" },
        h("div", { class: "list-title" }, "Draft", draft.ops.length ? h("span", { class: "chip", text: String(draft.ops.length) }) : null),
        draft.ops.length ? h("ol", { class: "td-list" }, draft.ops.map((o) => h("li", { text: describeOp(o) })))
          : h("p", { class: "card-sub", text: "Drag tasks not started and open issues between open milestones, or use Move… on a card. Nothing changes until you send the draft; Claude Code applies it with /dev-kit:worker." }),
        errors.length ? h("ul", { class: "td-list plan-errors", role: "alert" }, errors.map((x) => h("li", { text: x }))) : null,
        overBuffer ? h("button", { type: "button", class: "link-btn", text: "Go over the issue buffer and send again", onclick: () => { draft.buffer = true; draft.serverErrors = []; renderPlan(); $("plan-send").click(); } }) : null,
        h("div", { class: "plan-actions" },
          h("button", { type: "button", class: "btn", disabled: !draft.ops.length ? true : null, text: "Undo", onclick: () => { draft.ops.pop(); draft.serverErrors = []; renderPlan(); } }),
          h("button", { type: "button", class: "btn", disabled: !draft.ops.length ? true : null, text: "Discard", onclick: () => { draft = { ops: [], base: null, serverErrors: [], buffer: false }; renderPlan(); } }),
          sendBtn)));
    box.querySelector(".plan-cols").scrollLeft = scrollX;
    box.querySelectorAll(".pcol-list[data-key]").forEach((l) => { if (scrollY[l.dataset.key]) l.scrollTop = scrollY[l.dataset.key]; });
  }
  const VIEW_TITLE = { tasks: "Task board", burndown: "Burndown", velocity: "Velocity", gates: "Milestone gates" };
  const viewsShown = () => VIEWS;
  /** The plan view (drag, draft, send) lives only in Planning, while the board takes requests. */
  const planShown = () => actionsOn() && shownPhase() === "planning";
  function placePlanner() { $("plan-host-card").hidden = !planShown(); }
  /** Tabs, panels, heading and layout for the current view (Plan only while the board takes requests). */
  function applyView() {
    if (!viewsShown().includes(view)) view = "tasks";
    document.querySelectorAll("#view-switch [role=tab]").forEach((b) => {
      const on = b.dataset.view === view;
      b.setAttribute("aria-selected", String(on));
      b.tabIndex = on ? 0 : -1;
    });
    $("view-tasks").hidden = view !== "tasks";
    INS.forEach((k) => { $(`ins-${k}`).hidden = k !== view; });
    $("board-card").dataset.view = view;
    $("workspace").classList.toggle("planning", planShown());
    $("board-h").textContent = VIEW_TITLE[view];
  }
  function setView(v, focus) {
    view = v; store.set(VIEW_KEY, v);
    applyView();
    if (data && data.ok && shownPhase() === "construction") {
      renderKanban(currentMilestone());
      renderInsights(currentMilestone(), currentId());
    }
    if (focus) document.querySelector(`#view-switch [data-view="${view}"]`).focus();
  }
  $("view-switch").addEventListener("click", (e) => { const b = e.target.closest("[data-view]"); if (b) setView(b.dataset.view, false); });
  $("view-switch").addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    const vs = viewsShown();
    let i = vs.indexOf(view);
    i = e.key === "Home" ? 0 : e.key === "End" ? vs.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + vs.length) % vs.length;
    setView(vs[i], true); e.preventDefault();
  });

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
    const ph = shownPhase();
    keepFocus(() => {
      // global: the phase tabs, Needs you, requests and activity; below, only the panel of the phase shown
      PHASES.forEach((k) => { $(`phase-${k}`).hidden = k !== ph; });
      renderImpediments(); renderHeader(); renderRequests(); renderFeed();
      placePlanner(); applyView();
      if (ph === "conception") renderConception();
      else if (ph === "planning") { renderPlanning(); renderPlan(); }
      else if (ph === "construction") { renderReleases(); renderTrain(); renderTabs(); renderMilestone(m); renderStages(m); renderKanban(m); renderInsights(m, curId); }
      else renderStable();
    });
    updateAttention();
    pinOffsets();
    stickyLayout();
    $("main").setAttribute("aria-busy", "false");
    if (firstRender) {
      firstRender = false;
      const tid = decodeURIComponent(location.hash.slice(1));
      if (TASK_RE.test(tid)) openTask(tid);
      const dm = tid.match(DOC_HASH);
      if (dm) openDoc(dm[1], dm[2]);
    }
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
      if (tdlg.open && tdCur) fetchTask(tdCur, true);
      if (ddlg.open && docCur) fetchDoc(docCur, true);
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
      const b = $("banner"); b.hidden = false; fill(b, "The board server is not answering. Reconnecting… Start it again with ", cmd("/dev-kit:board"));
    };
  }

  function showStopped() {
    stopped = true;
    if (es) es.close();
    setLive("off", "Stopped");
    if (tdlg.open) tdlg.close();
    $("stopped").hidden = false;
    document.title = "Board stopped · dev-kit";
  }

  // ------------------------------------------------------------------ task details: a side drawer, linkable as #T-nnn
  const tdlg = $("task-dialog");
  let tdOrigin = null;   // card the drawer was opened from: focus returns there
  let tdCur = null;      // task shown now (the user can walk through dependencies inside the drawer)
  function section(title, ...kids) {
    const body = kids.flat().filter(Boolean);
    return body.length ? h("section", { class: "td-sec" }, h("h3", { text: title }), body) : null;
  }
  const taskRefs = (list) => (list.length ? h("ul", { class: "td-list plain" }, list.map((x) => h("li", {},
    h("button", { type: "button", class: "tid-btn", text: x.id, "aria-label": `Open ${x.id}`, onclick: () => openTask(x.id) }), ` ${x.title || ""} `,
    h("span", { class: `chip st-chip s-${x.status}`, text: stLabel(x.status) })))) : null);
  /** A task's source as a link: a .dev markdown report (qa/M1/report.md#F-3), or the dossier of a rejected release. */
  function sourceLink(src) {
    const rel = String(src).match(/^release:(R\d{1,3})$/);
    if (rel) return docLink(`releases/${rel[1]}/dossier.md`, `${rel[1]} rejected · dossier`);
    const m = String(src).match(/^(?:\.dev\/)?([\w./-]+\.md)(?:#([\w-]+))?/);
    return m && hasDoc(m[1]) ? docLink(m[1], src, m[2] || null) : String(src);
  }
  function renderTask(d) {
    const body = $("task-body");
    if (!d.ok) { fill(body, h("p", { class: "card-sub", text: d.error === "unknown task" ? "This task no longer exists (a replan may have removed it)." : "Could not load the task." })); return; }
    $("task-title").textContent = `${d.id} ${d.title || ""}`;
    const c = d.commit;
    fill(body, [
      h("div", { class: "tcard-top" }, h("span", { class: `chip st-chip s-${d.status}`, text: stLabel(d.status) }), h("span", { class: "chip", text: d.type }),
        d.lane ? h("span", { class: `chip lane-${d.lane}`, text: d.lane }) : null, h("span", { class: "chip", text: d.milestone }),
        d.started_at ? h("span", { text: `started ${fmtDT(parseT(d.started_at))}` }) : null,
        d.done_at ? h("span", { text: `done ${fmtDT(parseT(d.done_at))}` }) : null),
      agentsOn(d.id).length ? h("div", { class: "tcard-agents td-sec" }, agentsOn(d.id).map((x) => h("span", { class: "agent-chip" }, agentBits(x)))) : null,
      d.blocked_reason ? h("div", { class: "reason td-sec", text: d.blocked_reason }) : null,
      section("Origin", d.issue ? h("p", {}, h("span", { class: "tid", text: d.issue.id }), ` ${d.issue.title || ""}`,
        h("span", { class: "card-sub", text: ` · ${[d.issue.type, d.issue.class, d.issue.severity, d.issue.status].filter(Boolean).join(" · ")}` }),
        d.issue.note ? h("span", { class: "td-note", text: d.issue.note }) : null) : (d.source ? h("p", {}, sourceLink(d.source)) : null)),
      section(`Acceptance criteria (${d.acceptance.length})`, d.acceptance.length ? h("ul", { class: "td-list" }, d.acceptance.map((a) =>
        h("li", {}, a.text, a.prd ? h("span", { class: "td-note", text: `PRD: ${a.prd}` }) : null))) : null),
      section("How to test", d.test_notes ? h("p", { text: d.test_notes }) : null),
      section("Depends on", taskRefs(d.deps)),
      section("Unblocks", taskRefs(d.blocks)),
      section("Planned files", d.files.length ? h("ul", { class: "td-list mono" }, d.files.map((f) => h("li", { text: f }))) : null),
      section("Commit", c ? [h("p", {}, h("span", { class: "tid", text: c.sha.slice(0, 7) }), ` ${c.subject}`, h("span", { class: "card-sub", text: ` · ${c.author} · ${fmtDT(parseT(c.date))}` })),
        c.files.length ? h("ul", { class: "td-list mono" }, c.files.map((f) => h("li", { text: f }))) : null, c.summary ? h("p", { class: "card-sub", text: c.summary }) : null]
        : (d.commit_sha ? h("p", {}, h("span", { class: "tid", text: d.commit_sha.slice(0, 7) }), h("span", { class: "card-sub", text: " · not available in this checkout" })) : null)),
      section("History", d.log.length ? h("ul", { class: "td-list plain" }, d.log.map((r) => h("li", {}, h("span", { class: "card-sub", text: `${r.at} ` }), r.text))) : null),
      h("p", { class: "card-sub td-foot", text: "No free-text description is stored for tasks yet; this is everything recorded in .dev/." })]);
  }
  async function fetchTask(id, quiet) {
    try {
      const r = await fetch(`/api/task?id=${encodeURIComponent(id)}`, { cache: "no-store" });
      const d = await r.json();
      if (tdCur === id) renderTask(d);
    } catch (e) { if (tdCur === id && !quiet) renderTask({ ok: false, error: "network" }); }
  }
  function openTask(id) {
    if (!tdlg.open) tdOrigin = id;
    tdCur = id;
    $("task-title").textContent = data && data.tasks && data.tasks[id] ? `${id} ${data.tasks[id].title}` : id;
    fill($("task-body"), h("p", { class: "card-sub", text: "Loading…" }));
    if (!tdlg.open) (tdlg.showModal ? tdlg.showModal() : tdlg.setAttribute("open", ""));
    tdlg.scrollTop = 0;
    if (location.hash !== `#${id}`) history.replaceState(null, "", `#${id}`);
    fetchTask(id, false);
  }
  $("task-close").addEventListener("click", () => tdlg.close());
  tdlg.addEventListener("click", (e) => { if (e.target === tdlg) tdlg.close(); });
  tdlg.addEventListener("close", () => {
    const back = tdOrigin && document.querySelector(`[data-tid="${tdOrigin}"]`);
    tdOrigin = tdCur = null;
    if (TASK_RE.test(decodeURIComponent(location.hash.slice(1)))) history.replaceState(null, "", location.pathname + location.search);
    if (back) back.focus();
  });
  window.addEventListener("hashchange", () => {
    const tid = decodeURIComponent(location.hash.slice(1));
    const dm = tid.match(DOC_HASH);
    if (dm && (!docCur || docCur.path !== dm[1])) { openDoc(dm[1], dm[2]); return; }
    if (TASK_RE.test(tid) && tid !== tdCur) openTask(tid);
    else if (!tid && tdlg.open) tdlg.close();
    else if (!tid && ddlg.open) ddlg.close();
  });

  // ------------------------------------------------------------------ markdown documents of .dev/: a side drawer, linkable as #doc:<path>
  // A small renderer that builds the DOM with h() (text through textContent, never innerHTML): headings with anchors,
  // paragraphs, nested lists and checkboxes, tables, fenced code, quotes, rules, and inline code, bold, italic, links.
  const ID_TOKEN = /^(ADR-\d{1,5}|Q-\d{1,5}|I-\d{1,5}|T-\d{1,5}|F-\d{1,5}|AC-\d{1,4}|M\d{1,3}|R\d{1,3})\b/;
  const INLINE = /(`+)([\s\S]*?[^`])\1(?!`)|\*\*([^*]+?)\*\*|__([^_]+?)__|~~([^~]+?)~~|\*([^*\s](?:[^*]*?[^*\s])?)\*|(?<![\w])_([^_\s](?:[^_]*?[^_\s])?)_(?![\w])|\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)|<(https?:\/\/[^>\s]+)>/g;
  let docCur = null;          // {path, anchor} of the document shown
  /** A .dev-relative path for a link written inside a document (relative to that document), or null outside .dev. */
  function devPath(href, base) {
    const clean = href.split("#")[0];
    if (!clean || /^[a-z][a-z0-9+.-]*:/i.test(clean) || clean.startsWith("/")) return null;
    const parts = (base ? base.split("/").slice(0, -1) : []).concat(clean.replace(/^\.dev\//, "").split("/"));
    const out = [];
    for (const p of parts) { if (p === "..") { if (!out.length) return null; out.pop(); } else if (p && p !== ".") out.push(p); }
    return out.join("/");
  }
  function mdLink(label, href, base) {
    if (/^https?:\/\//i.test(href)) return h("a", { href, target: "_blank", rel: "noopener noreferrer" }, label);
    if (href.startsWith("#")) return h("button", { type: "button", class: "link-btn md-a", onclick: () => scrollDoc(decodeURIComponent(href.slice(1))) }, label);
    const p = devPath(href, base);
    if (p && /\.md$/i.test(p) && (data.docs || []).includes(p)) {
      const anchor = href.includes("#") ? decodeURIComponent(href.split("#")[1]) : null;
      return h("button", { type: "button", class: "link-btn md-a", title: `.dev/${p}`, onclick: () => openDoc(p, anchor, "inner") }, label);
    }
    return h("span", { class: "md-a-off", title: href }, label);
  }
  function mdInline(text, base) {
    const out = [];
    let last = 0;
    for (const m of String(text).matchAll(INLINE)) {
      if (m.index > last) out.push(...linkify(text.slice(last, m.index)));
      if (m[1]) out.push(h("code", { text: m[2] }));
      else if (m[3] || m[4]) out.push(h("strong", {}, mdInline(m[3] || m[4], base)));
      else if (m[5]) out.push(h("del", {}, mdInline(m[5], base)));
      else if (m[6] || m[7]) out.push(h("em", {}, mdInline(m[6] || m[7], base)));
      else if (m[8]) out.push(mdLink(mdInline(m[8], base), m[9], base));
      else if (m[10]) out.push(mdLink(m[10], m[10], base));
      last = m.index + m[0].length;
    }
    if (last < text.length) out.push(...linkify(text.slice(last)));
    return out;
  }
  const slug = (s) => "md-" + String(s).toLowerCase().replace(/[`*_~[\]()]/g, "").replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, "").slice(0, 60);
  const LIST_RE = /^(\s*)([-*+]|\d{1,3}[.)])\s+(.*)$/;
  const indentOf = (l) => l.match(/^\s*/)[0].replace(/\t/g, "    ").length;
  const splitRow = (l) => l.trim().replace(/^\||\|$/g, "").split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));
  function mdList(lines, i, indent, base) {
    const ordered = /^\s*\d/.test(lines[i]);
    const list = h(ordered ? "ol" : "ul", { class: "md-list" });
    let cur = null;
    while (i < lines.length) {
      const l = lines[i];
      const m = l.match(LIST_RE);
      if (!m) {
        if (l.trim() && cur && indentOf(l) > indent) { cur.append(" ", ...mdInline(l.trim(), base)); i++; continue; }
        break;
      }
      const ind = indentOf(m[1]);
      if (ind < indent) break;
      if (ind > indent) {
        const [sub, j] = mdList(lines, i, ind, base);
        (cur || list).append(sub);
        i = j;
        continue;
      }
      let body = m[3];
      const cb = body.match(/^\[( |x|X)\]\s+(.*)$/);
      if (cb) body = cb[2];
      cur = h("li", { class: cb ? "md-task" : null },
        cb ? h("span", { class: "md-box", "aria-hidden": "true", text: cb[1] === " " ? "☐" : "☑" }) : null,
        cb ? h("span", { class: "visually-hidden", text: cb[1] === " " ? "to do: " : "done: " }) : null,
        mdInline(body, base));
      const id = body.match(ID_TOKEN);
      if (id) cur.setAttribute("data-anchor", id[1]);
      list.append(cur);
      i++;
    }
    return [list, i];
  }
  function renderMarkdown(text, base) {
    const lines = String(text).replace(/\r\n?/g, "\n").split("\n");
    const out = [];
    let i = 0;
    const isBlock = (l) => /^\s*(#{1,6}\s|```|~~~|>|(\*{3,}|-{3,}|_{3,})\s*$)/.test(l) || LIST_RE.test(l);
    if (lines[0] === "---") { const end = lines.indexOf("---", 1); if (end > 0) i = end + 1; }  // front matter
    while (i < lines.length) {
      const l = lines[i];
      if (!l.trim()) { i++; continue; }
      const fence = l.match(/^\s*(```+|~~~+)\s*([\w+-]*)/);
      if (fence) {
        const body = [];
        i++;
        while (i < lines.length && !lines[i].trim().startsWith(fence[1])) body.push(lines[i++]);
        i++;
        out.push(h("pre", { class: "md-pre" }, h("code", { text: body.join("\n"), "data-lang": fence[2] || null })));
        continue;
      }
      const hd = l.match(/^(#{1,6})\s+(.*?)\s*#*\s*$/);
      if (hd) {
        const id = hd[2].match(ID_TOKEN);
        out.push(h(`h${Math.min(6, hd[1].length + 1)}`, { class: "md-h", id: slug(hd[2]), "data-anchor": id ? id[1] : null }, mdInline(hd[2], base)));
        i++;
        continue;
      }
      if (/^\s*(\*{3,}|-{3,}|_{3,})\s*$/.test(l)) { out.push(h("hr")); i++; continue; }
      if (l.includes("|") && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(lines[i + 1])) {
        const head = splitRow(l);
        const align = splitRow(lines[i + 1]).map((c) => (c.startsWith(":") && c.endsWith(":") ? "center" : c.endsWith(":") ? "right" : null));
        i += 2;
        const rows = [];
        while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(splitRow(lines[i++]));
        const cell = (tag, c, k) => { const el = h(tag, {}, mdInline(c, base)); if (align[k]) el.classList.add(`md-${align[k]}`); return el; };
        out.push(h("div", { class: "md-table" }, h("table", {},
          h("thead", {}, h("tr", {}, head.map((c, k) => cell("th", c, k)))),
          h("tbody", {}, rows.map((r) => { const id = (r[0] || "").match(ID_TOKEN); return h("tr", { "data-anchor": id ? id[1] : null }, head.map((_, k) => cell("td", r[k] || "", k))); })))));
        continue;
      }
      if (/^\s*>/.test(l)) {
        const q = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) q.push(lines[i++].replace(/^\s*>\s?/, ""));
        out.push(h("blockquote", { class: "md-quote" }, renderMarkdown(q.join("\n"), base)));
        continue;
      }
      if (LIST_RE.test(l)) {
        const [list, j] = mdList(lines, i, indentOf(l), base);
        out.push(list);
        i = j;
        continue;
      }
      const para = [l.trim()];
      i++;
      while (i < lines.length && lines[i].trim() && !isBlock(lines[i]) && !(lines[i].includes("|") && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1] || ""))) para.push(lines[i++].trim());
      out.push(h("p", {}, mdInline(para.join(" "), base)));
    }
    return out;
  }

  const ddlg = $("doc-dialog");
  const DOC_NAME = { "brief.md": "Brief", "prd.md": "PRD", "architecture.md": "Architecture", "design/ux-flows.md": "UX flows", "design/ui-spec.md": "UI spec",
    "plan.md": "Plan", "decisions.md": "Decisions", "open-questions.md": "Open questions", "issues.md": "Issues", "log.md": "Log" };
  let docStack = [];          // documents opened from inside the drawer: "Back" walks them
  let docOrigin = null;       // element the drawer was opened from: focus returns there
  const hasDoc = (p) => (data.docs || []).includes(p);
  const relDev = (p) => String(p || "").replace(/^\.dev\//, "");
  /** A button that opens a .dev markdown file in the drawer, or plain text when the file does not exist. */
  function docLink(path, label, anchor, cls) {
    const p = relDev(path);
    if (!hasDoc(p)) return h("span", { class: `doc-off${cls ? ` ${cls}` : ""}`, title: `.dev/${p} does not exist yet`, text: label || p });
    return h("button", { type: "button", class: `doc-link${cls ? ` ${cls}` : ""}`, "data-doc": p, title: `Open .dev/${p}${anchor ? ` at ${anchor}` : ""}`,
      onclick: (e) => { e.stopPropagation(); openDoc(p, anchor); } }, h("span", { class: "doc-ico", "aria-hidden": "true", text: "▤" }), label || p);
  }
  function scrollDoc(anchor) {
    if (!anchor) return;
    const body = $("doc-body");
    const el = body.querySelector(`[data-anchor="${CSS.escape(anchor)}"]`) || body.querySelector(`#${CSS.escape(slug(anchor))}`)
      || body.querySelector(`#${CSS.escape(anchor)}`);
    if (!el) return;
    el.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    el.classList.add("md-hit");
    setTimeout(() => el.classList.remove("md-hit"), 2200);
  }
  function renderDoc(d) {
    const body = $("doc-body");
    if (!d.ok) { fill(body, h("p", { class: "card-sub", text: d.error === "not found" ? "This document does not exist (any more)." : `Could not open it: ${d.error || "error"}.` })); return; }
    fill(body, renderMarkdown(d.text, d.path), h("p", { class: "card-sub td-foot", text: `.dev/${d.path} · changed ${Number.isFinite(parseT(d.mtime)) ? fmtDT(parseT(d.mtime)) : d.mtime}` }));
    if (!DOC_NAME[d.path]) { const h1 = body.querySelector(".md-h"); if (h1) $("doc-title").textContent = h1.textContent; }
  }
  async function fetchDoc(cur, quiet) {
    try {
      const r = await fetch(`/api/doc?path=${encodeURIComponent(cur.path)}`, { cache: "no-store" });
      const d = await r.json();
      if (docCur !== cur) return;
      const keep = quiet ? ddlg.scrollTop : 0;
      renderDoc(d);
      if (quiet) ddlg.scrollTop = keep; else scrollDoc(cur.anchor);
    } catch (e) { if (docCur === cur && !quiet) renderDoc({ ok: false, error: "network" }); }
  }
  /** mode: undefined opens from the page (a fresh history), "inner" from a link inside a document, "back" from Back. */
  function openDoc(path, anchor, mode) {
    if (tdlg.open) { tdOrigin = null; tdlg.close(); }
    if (!ddlg.open) { docOrigin = document.activeElement; docStack = []; }
    else if (mode === "inner" && docCur) docStack.push(docCur);
    else if (!mode) docStack = [];
    docCur = { path, anchor: anchor || null };
    $("doc-title").textContent = DOC_NAME[path] || path.split("/").pop().replace(/\.md$/i, "");
    fill($("doc-path"), h("code", { text: `.dev/${path}` }), copyBtn(`.dev/${path}`));
    $("doc-back").hidden = !docStack.length;
    fill($("doc-body"), h("p", { class: "card-sub", text: "Loading…" }));
    if (!ddlg.open) (ddlg.showModal ? ddlg.showModal() : ddlg.setAttribute("open", ""));
    ddlg.scrollTop = 0;
    const hash = `#doc:${path}${anchor ? `:${anchor}` : ""}`;
    if (location.hash !== hash) history.replaceState(null, "", hash);
    fetchDoc(docCur, false);
  }
  $("doc-close").addEventListener("click", () => ddlg.close());
  $("doc-back").addEventListener("click", () => { const prev = docStack.pop(); if (prev) openDoc(prev.path, prev.anchor, "back"); });
  ddlg.addEventListener("click", (e) => { if (e.target === ddlg) ddlg.close(); });
  ddlg.addEventListener("close", () => {
    docCur = null; docStack = [];
    if (location.hash.startsWith("#doc:")) history.replaceState(null, "", location.pathname + location.search);
    if (docOrigin && docOrigin.isConnected) docOrigin.focus();
    docOrigin = null;
  });
  const DOC_HASH = /^doc:([\w./-]+\.md)(?::([\w-]+))?$/i;

  // ------------------------------------------------------------------ stop server
  const dlg = $("stop-dialog");
  $("stop-btn").addEventListener("click", () => {
    pops.forEach((p) => p.close());
    if (dlg.showModal) dlg.showModal(); else if (confirm("Stop the board server?")) stopServer();
  });
  dlg.addEventListener("close", () => { if (dlg.returnValue === "stop") stopServer(); else $("menu-btn").focus(); });
  async function stopServer() {
    const btn = $("stop-btn");
    btn.disabled = true;
    try {
      const r = await fetch("/api/shutdown", { method: "POST", headers: { "X-Board-Token": TOKEN } });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      showStopped();
    } catch (e) {
      btn.disabled = false;
      const b = $("banner"); b.hidden = false; fill(b, `Could not stop the server (${e.message}). Use `, cmd("/dev-kit:board stop"));
    }
  }

  // milestone tabs: arrow keys move between milestones
  $("tabs").addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key) || !data || !msInView().length) return;
    const ids = msInView().map((m) => m.id);
    let i = ids.indexOf(currentId());
    i = e.key === "Home" ? 0 : e.key === "End" ? ids.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + ids.length) % ids.length;
    selectMilestone(ids[i], true); e.preventDefault();
  });

  let resizeT = null;
  let lastW = window.innerWidth;
  window.addEventListener("resize", () => {
    if (window.innerWidth === lastW) return;
    lastW = window.innerWidth;
    clearTimeout(resizeT);
    resizeT = setTimeout(render, 150);
  });

  // chevrons stay on screen while scrolling, shrinking to a compact strip once the page has moved.
  // Shrinking the pinned strips makes the page shorter above the content, and the browser keeps the content still by
  // lowering scrollY by that much. With a fixed threshold that drop crossed it back and the strips flickered between
  // the two sizes. So the strip compacts only past the height it will lose (measured, plus a margin) and expands only
  // at the very top: after either switch scrollY lands on the same side of the threshold.
  let stickyRaf = 0;
  const pinned = () => [document.querySelector(".topbar"), document.querySelector(".phasebar"), $("cons-nav")].filter(Boolean);
  const pinnedHeight = () => pinned().reduce((n, el) => n + el.offsetHeight, 0);  // a hidden strip measures 0
  const shrink = {};   // per phase shown: pinned height when full and when compact, as last measured
  const lostHeight = () => {
    const m = shrink[shownPhase()];
    return m && m.full && m.compact ? Math.max(0, m.full - m.compact) : 260;  // not measured yet: a safe margin
  };
  function stickyLayout() {
    stickyRaf = 0;
    const y = window.scrollY || 0;
    const body = document.body;
    const on = body.classList.contains("compact");
    if (!on && y > lostHeight() + 40) body.classList.add("compact");
    else if (on && y <= 4) body.classList.remove("compact");
  }
  // offsets of the stacked strips (top bar, then lifecycle tabs, then construction's chevrons) follow their height
  // on every frame of the transition, so the lower strips slide with the upper ones instead of jumping at the end
  function pinOffsets() {
    const top = document.querySelector(".topbar"), bar = document.querySelector(".phasebar");
    const set = (k, v) => { if (document.documentElement.style.getPropertyValue(k) !== v) document.documentElement.style.setProperty(k, v); };
    if (top) set("--topbar-h", `${top.offsetHeight}px`);
    if (bar) set("--phasebar-h", `${bar.offsetHeight}px`);
    const m = (shrink[shownPhase()] = shrink[shownPhase()] || {});
    m[document.body.classList.contains("compact") ? "compact" : "full"] = pinnedHeight();
  }
  if (window.ResizeObserver) {
    const ro = new ResizeObserver(() => pinOffsets());
    pinned().forEach((el) => ro.observe(el));
  }
  window.addEventListener("scroll", () => { if (!stickyRaf) stickyRaf = requestAnimationFrame(stickyLayout); }, { passive: true });

  setInterval(tickUpdated, 1000);
  load();
  connect();
})();
