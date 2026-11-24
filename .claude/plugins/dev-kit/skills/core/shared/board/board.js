/* dev-kit board - live view of .dev/state.json: milestone window, what needs the user, the stages of the milestone with what runs in each, the milestone kanban, insights; with actions on, requests to Claude Code (run a command, answer a question, new issue, a plan draft made by dragging cards) queued through the server and run by /dev-kit:worker. No dependencies. All untrusted text goes through textContent. */
(() => {
  "use strict";

  const TOKEN = document.querySelector('meta[name="board-token"]').content;

  // ------------------------------------------------------------------ text catalogs (i18n/<lang>.json): every visible text goes through tr()
  // Keys are the English text (en.json is the base); {name} takes a value; plurals live under "plurals" with Intl plural
  // forms. The project's own content (task titles, questions, notes) is never translated.
  const CATS = (() => { try { return JSON.parse(document.getElementById("i18n-catalogs").textContent); } catch (e) { return {}; } })();
  const LANGS = Object.keys(CATS).length ? Object.keys(CATS) : ["en"];
  const LANG_NAME = { en: "English", "pt-BR": "Português (Brasil)" };
  let LANG = "en";
  const pickLang = (want) => {
    if (!want) return null;
    const w = String(want).toLowerCase();
    return LANGS.find((l) => l.toLowerCase() === w) || LANGS.find((l) => l.toLowerCase().split("-")[0] === w.split("-")[0]) || null;
  };
  const cat = () => CATS[LANG] || {};
  const base = () => CATS.en || {};
  const fmtNum = (n) => { try { return new Intl.NumberFormat(LANG).format(n); } catch (e) { return String(n); } };
  const fill_ = (str, vars) => String(str).replace(/\{(\w+)\}/g, (m, k) => (vars && vars[k] != null ? (typeof vars[k] === "number" ? fmtNum(vars[k]) : String(vars[k])) : m));
  /** The text of a key in the language shown, with its values. */
  function tr(key, vars) {
    const c = cat().strings || {}, b = base().strings || {};
    return fill_(c[key] != null ? c[key] : b[key] != null ? b[key] : key, vars);
  }
  /** A key marked for the catalog where it is defined; tr() translates it where it is shown. */
  const N_ = (key) => key;
  /** A map (or record) whose text values are catalog keys: read through it, they come out in the language shown. */
  const tmap = (obj, fields) => new Proxy(obj, { get: (o, k) => (typeof o[k] === "string" && (!fields || fields.includes(k)) ? tr(o[k]) : o[k]) });
  /** "3 tasks": the noun's plural forms from the catalog (Intl plural rules of the language shown). */
  function plural(n, one, many) {
    const forms = (cat().plurals || {})[one] || (base().plurals || {})[one];
    let rule = "other";
    try { rule = new Intl.PluralRules(LANG).select(n); } catch (e) { /* other */ }
    const s = forms ? forms[rule] || forms.other : `{n} ${n === 1 ? one : many || one + "s"}`;
    return fill_(s, { n });
  }
  const SVGNS = "http://www.w3.org/2000/svg";
  const STATUS = [
    tmap({ key: "todo", label: N_("To do"), icon: "○" }, ["label"]),
    tmap({ key: "in_progress", label: N_("In progress"), icon: "◐" }, ["label"]),
    tmap({ key: "blocked", label: N_("Blocked"), icon: "⛔" }, ["label"]),
    tmap({ key: "done", label: N_("Done"), icon: "✓" }, ["label"]),
  ];
  // project lifecycle (conventions.md §19): conception -> planning -> construction -> stable, as a cycle
  const PHASE_NAME = tmap({ conception: N_("Conception"), planning: N_("Planning"), construction: N_("Construction"), stable: N_("Stable"), releases: N_("Releases") });
  const PHASE_WORD = tmap({ done: N_("done"), current: N_("current phase"), active: N_("still running"), upcoming: N_("not started") });
  const STEP_NAME = tmap({ interview: N_("interview"), prd: N_("PRD"), architecture: N_("architecture"), ux: N_("UX"), ui: N_("UI"), plan: N_("plan"),
    milestones: N_("milestones"), release: N_("release") });
  const GATE_WORD = tmap({ passed: N_("passed"), skipped: N_("skipped"), pending: N_("pending") });
  const STEP_WORD = tmap({ todo: N_("to do"), doing: N_("in progress"), stale: N_("out of date"), review: N_("waiting for its review"), checkpoint: N_("waiting for your confirmation"), done: N_("done"), skipped: N_("skipped") });
  const STEP_MARK = { todo: "○", doing: "◐", stale: "↻", review: "◐", checkpoint: "◐", done: "✓", skipped: "–" };
  const STEP_TITLE = tmap({ interview: N_("Interview"), prd: N_("PRD"), architecture: N_("Architecture"), ux: N_("UX"), ui: N_("UI"), plan: N_("Plan") });
  const STEP_ABOUT = tmap({ interview: N_("Requirements interview, written to brief.md"), prd: N_("Product requirements with numbered acceptance criteria"),
    architecture: N_("Stack, data model, contracts and ADRs"), ux: N_("Journeys, screens and every screen state"), ui: N_("Design tokens, components and screen specs"),
    plan: N_("Milestones of small tasks, with dependencies") });
  const STEP_CMD = { interview: "/dev-kit:interview", prd: "/dev-kit:prd", architecture: "/dev-kit:architecture", ux: "/dev-kit:ux", ui: "/dev-kit:ui", plan: "/dev-kit:plan" };
  const STEP_REVIEW_CMD = { prd: "/dev-kit:review prd", ux: "/dev-kit:review design", ui: "/dev-kit:review design", plan: "/dev-kit:review plan" };
  const REVIEW_NAME = tmap({ prd: N_("PRD"), design: N_("Design"), plan: N_("Plan"), ux: N_("Usability"), docs: N_("Docs") });

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
  const fmtDate = (v) => new Date(v).toLocaleDateString(LANG, { month: "short", day: "numeric" });
  const fmtDT = (v) => new Date(v).toLocaleString(LANG, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  const compact = (n) => { try { return new Intl.NumberFormat(LANG, { notation: n >= 1e4 ? "compact" : "standard", maximumFractionDigits: 1 }).format(n); } catch (e) { return String(n); } };
  function ago(t) {
    const s = Math.max(0, Math.round((Date.now() - t) / 1000));
    if (s < 5) return tr("just now");
    if (s < 60) return tr("{s} s ago", { s });
    if (s < 3600) return tr("{v} min ago", { v: Math.floor(s / 60) });
    return tr("{v} h ago", { v: Math.floor(s / 3600) });
  }
  function tasksOf(m) { return (m ? m.tasks : []).map((id) => ({ id, ...data.tasks[id] })); }


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
  let query = "";            // text filter of the kanban
  let typeFilter = "";       // task type filter of the kanban
  let mobileCol = null;      // column shown on narrow screens (null = pick the most useful one)
  // construction: the task board or the QA of the milestone; the metrics open in a modal
  const VIEWS = ["tasks", "qa"];
  const VIEW_KEY = "board-view-v3";
  // the lanes of docs/dev-kit-flow.svg are the tabs, in its order and numbers; "map" shows all five at once
  const LANES = ["conception", "planning", "construction", "releases", "stable"];
  const LANE_NUM = { conception: "1", planning: "2", construction: "3", releases: "3", stable: "4" };
  const LANE_NAME = tmap({ conception: N_("Conception"), planning: N_("Planning"), construction: N_("Milestones"), releases: N_("Releases"), stable: N_("Stable") });
  // the lane shown: null follows the project's phase. Not kept across reloads: the board always opens where the project is.
  let phasePick = null;
  const shownPhase = () => (phasePick && (phasePick === "map" || phasePick === "arch" || LANES.includes(phasePick)) ? phasePick : (data && data.phase) || "conception");
  let needsBy = {};          // items of "Needs you" per lane, shown as badges on the tabs and on the steps of the flow
  let view = VIEWS.includes(store.get(VIEW_KEY, "")) ? store.get(VIEW_KEY, "") : "tasks";
  let firstRender = true;

  const stLabel = (x) => String(x || "").replace("_", " ");
  function dur(sec) {
    sec = Math.max(0, Math.round(sec));
    return sec < 60 ? `${sec}s` : sec < 3600 ? `${Math.floor(sec / 60)}m` : sec < 86400 ? `${Math.floor(sec / 3600)}h${String(Math.floor((sec % 3600) / 60)).padStart(2, "0")}m`
      : `${Math.floor(sec / 86400)}d${String(Math.floor((sec % 86400) / 3600)).padStart(2, "0")}h`;
  }
  /** Seconds from a to b (two timestamps), or null when one is missing. */
  function secsBetween(a, b) {
    const x = parseT(a), y = parseT(b);
    return Number.isFinite(x) && Number.isFinite(y) ? Math.max(0, (y - x) / 1000) : null;
  }
  /** How long a finished task ran: started -> done (null while it is not done). */
  const taskTook = (t) => (t && t.status === "done" ? secsBetween(t.started_at, t.done_at) : null);
  function agoShort(t) {
    const sec = Math.max(0, Math.round((Date.now() - t) / 1000));
    return sec < 60 ? tr("now") : sec < 3600 ? tr("{v}m ago", { v: Math.floor(sec / 60) }) : sec < 86400 ? tr("{v}h ago", { v: Math.floor(sec / 3600) }) : sec < 7 * 86400 ? tr("{v}d ago", { v: Math.floor(sec / 86400) }) : fmtDate(t);
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
    const label = tr("Copy {text}", { text });
    const btn = h("button", { type: "button", class: "copy-btn", title: label, "aria-label": label }, copySvg());
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const ok = await copyText(text);
      btn.classList.toggle("copied", ok);
      btn.classList.toggle("copy-failed", !ok);
      fill(btn, ok ? "✓" : "✕");
      $("copy-status").textContent = ok ? tr("Copied {text}. Paste it in Claude Code.", { text }) : tr("Could not copy. Select {text} and copy it by hand.", { text });
      clearTimeout(btn._t);
      btn._t = setTimeout(() => { btn.classList.remove("copied", "copy-failed"); fill(btn, copySvg()); }, 1600);
    });
    return btn;
  }
  /** A command shown as code with its copy button and, when the board takes requests, a button that queues it. */
  const cmd = (text) => (runnable(text) ? h("span", { class: "cmd act" }, runBtn(text, true), copyBtn(text))
    : h("span", { class: "cmd" }, h("code", { text }), copyBtn(text)));
  /** What a command does, in words, for its button ("Run QA of M2"); the literal command is in the title and the copy button. */
  const ACTION_LABEL = tmap({ qa: N_("Run QA of {s}"), implement: N_("Build {s}"), autopilot: N_("Continue construction"), docs: N_("Generate docs"), release: N_("Prepare release {s}"),
    plan: N_("Plan"), review: N_("Review {s}"), interview: N_("Answer open questions"), prd: N_("Write the PRD"), architecture: N_("Design the architecture"), ux: N_("Design the UX"),
    ui: N_("Design the UI"), usability: N_("Test usability"), deploy: N_("Deploy"), issue: N_("Triage issues"), backlog: N_("Review the backlog"), feedback: N_("Review the kit's feedback"),
    start: N_("Start"), worker: N_("Take board requests"), board: N_("Open the board"), settings: N_("Settings"), onboarding: N_("Onboard the project") });
  function actionLabel(text) {
    const m = /^\/dev-kit:([a-z-]+)\s*(.*)$/.exec(text || "");
    if (!m) return text;
    const scope = m[2].trim();
    const base = ACTION_LABEL[m[1]];
    if (!base) return text;
    return base.includes("{s}") ? (scope ? base.replace("{s}", scope.split(/\s+/)[0]) : base.replace(/ (of )?\{s\}/, "")) : base;
  }
  /** The run of this command going on now (same skill and scope), if any. */
  const runningRun = (text) => skillRuns().find((r) => runCmd(r) === String(text || "").trim());
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
  popover($("ap-btn"), $("ap-pop"));
  popover($("live"), $("live-pop"));
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
    const label = next === "light" ? tr("Switch to light theme") : tr("Switch to dark theme");
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

  // ------------------------------------------------------------------ language: the user's choice (kept in this browser),
  // else the project's language (state.json), else the browser's, else English
  const LANG_KEY = "board-lang";
  let langPicked = pickLang(store.get(LANG_KEY, ""));
  LANG = langPicked || pickLang(navigator.language) || "en";
  /** The static texts of the page (data-i18n*); "once" ones are rewritten by the render that follows. */
  function applyStatic(all) {
    document.documentElement.lang = LANG;
    document.querySelectorAll(all ? "[data-i18n], [data-i18n-once]" : "[data-i18n]").forEach((el) => { el.textContent = tr(el.dataset.i18n || el.dataset.i18nOnce); });
    for (const at of ["title", "aria-label", "placeholder"]) {
      const key = `i18n${at === "aria-label" ? "AriaLabel" : at[0].toUpperCase() + at.slice(1)}`;
      document.querySelectorAll(`[data-i18n-${at}]`).forEach((el) => el.setAttribute(at, tr(el.dataset[key])));
    }
    fill($("lang-switch"), LANGS.map((l) => h("button", { type: "button", class: "seg-btn", "data-lang": l, "aria-pressed": String(l === LANG), lang: l, text: LANG_NAME[l] || l })));
  }
  function setLang(l, remember) {
    const want = pickLang(l) || "en";
    if (remember) { langPicked = want; store.set(LANG_KEY, want); }
    if (want === LANG && !remember) return;
    LANG = want;
    applyStatic(false);
    applyTheme();
    if (data && data.ok) render();  // the same data, in the other language
    tickUpdated();
  }
  $("lang-switch").addEventListener("click", (e) => { const b = e.target.closest("[data-lang]"); if (b) setLang(b.dataset.lang, true); });
  applyStatic(true);
  applyTheme();

  // ------------------------------------------------------------------ header
  // ------------------------------------------------------------------ what Claude Code runs now: skills (outermost first) and agents
  const skillRuns = () => ((data && data.agents && data.agents.runs) || []).filter((r) => r.skill !== "board");  // the board is not work
  const runCmd = (r) => `/dev-kit:${r.skill}${r.scope ? ` ${r.scope}` : ""}`;
  const since = (t) => h("span", { class: "agent-time", "data-start": t, text: dur((Date.now() - parseT(t)) / 1000) });
  // Every skill that runs has a place on the board, so work that is not a task card is visible where it happens.
  // Orchestrators (autopilot, worker, start…) only show in the top bar; the work they start shows in its place.
  const RUN_PLACE = {
    interview: ["conception", "step:interview"], prd: ["conception", "step:prd"], architecture: ["conception", "step:architecture"],
    ux: ["conception", "step:ux"], ui: ["conception", "step:ui"], plan: ["planning", "step:plan"], issue: ["planning", "backlog"],
    qa: ["construction", "qa"], implement: ["construction", "tasks"], test: ["construction", "tasks"],
    usability: ["stable", "checks"], docs: ["stable", "checks"], release: ["stable", "releases"], deploy: ["stable", "prod"],
  };
  const REVIEW_PLACE = { prd: ["conception", "step:prd"], design: ["conception", "step:ui"], plan: ["planning", "step:plan"], docs: ["stable", "checks"], ux: ["stable", "checks"] };
  function runPlace(r) {
    if (r.skill === "review") return REVIEW_PLACE[r.scope] || null;
    return RUN_PLACE[r.skill] || null;
  }
  /** Runs shown at a place (e.g. "step:prd", "checks"); the design review also lights the UX step. */
  const runsAt = (where) => skillRuns().filter((r) => { const p = runPlace(r); return p && (p[1] === where || (where === "step:ux" && p[1] === "step:ui" && r.skill === "review")); });
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
      h("span", { class: "rn-dot", "aria-hidden": "true" }), h("strong", { text: tr("Running now") }),
      runs.map((r) => h("span", { class: "rb-cmd" }, h("code", { text: runCmd(r) }), " ", since(r.started_at))),
      ags.length ? h("span", { class: "rb-agents" }, ags.map((a) => h("span", { class: "agent-chip" }, agentBits(a, true)))) : null);
  }

  // ------------------------------------------------------------------ Live: the connection, and on hover or click what runs now
  /** Headless runs the board's server started (the autopilot, the worker), then the skills of the session log (the
   * board itself is not work) and the agents. */
  function liveRuns() {
    const out = [];
    const ap = inbox().autopilot || {};
    if (ap.state === "running" || ap.state === "stopping") out.push({ cmd: ap.command || "/dev-kit:autopilot", since: ap.since,
      by: ap.where !== "session" ? tr("started by the Autopilot switch") : ap.handoff === "pending" ? tr("handed to your Claude Code session, waiting for it to start") : tr("running in your Claude Code session") });
    const rd = ap.round;
    if (rd) out.push({ cmd: `/dev-kit:${rd.skill} ${rd.scope || ""}`.trim(), since: rd.since, by: roundWhat(rd) });
    const au = inbox().executor.auto || {};
    if (au.state === "running") out.push({ cmd: "/dev-kit:worker", since: au.since, by: au.request ? tr("started by the board for {id}", { id: au.request }) : tr("started by the board") });
    return out;
  }
  function renderRunning() {
    const runs = skillRuns(), ags = activeAgents(), heads = liveRuns();
    const nx = data.next && data.next.command;
    const n = heads.length + runs.length + ags.length;
    const badge = $("live-n");
    badge.hidden = !n;
    badge.textContent = String(n);
    $("live").setAttribute("aria-label", n ? tr("Live: {v} running. Show what runs", { v: String(n) }) : tr("Live: nothing running. Show details"));
    fill($("live-pop"), h("p", { class: "pop-title", text: n ? tr("Running now") : tr("Nothing is running now") }),
      heads.length ? h("ul", { class: "rn-list" }, heads.map((r) => h("li", {}, h("code", { text: r.cmd }), r.since ? h("span", { class: "card-sub" }, tr(" for "), since(r.since)) : null,
        h("span", { class: "card-sub", text: `· ${r.by}` })))) : null,
      runs.length ? h("ol", { class: "rn-list" }, runs.map((r, i) => h("li", { class: i ? "nested" : null },
        h("code", { text: runCmd(r) }), h("span", { class: "card-sub" }, tr(" for "), since(r.started_at))))) : null,
      ags.length ? [h("p", { class: "pop-title", text: plural(ags.length, "agent") }), h("ul", { class: "rn-list" }, ags.map((a) => h("li", {},
        h("span", { class: "agent-chip" }, agentBits(a, true)),
        a.node ? (TASK_RE.test(a.node) ? h("button", { type: "button", class: "tid-btn", text: a.node, onclick: () => openTask(a.node) })
          : h("span", { class: "chip", text: a.node.replace("GATE:", "QA ") })) : h("span", { class: "card-sub", text: tr("not linked") }))))] : null,
      !n && nx && !runningRun(nx) ? h("p", { class: "pop-note top" }, tr("Next step: "), cmd(nx)) : null,
      h("p", { class: "pop-note", text: tr("Skills and agents show here while Claude Code runs them (from the session log); Live means this page is connected to the board's server.") }));
  }
  // hover opens it too (a click keeps it open; touch screens use the click)
  (() => {
    const wrap = $("live-wrap"), btn = $("live"), pop = $("live-pop");
    let byHover = false, t = 0;
    wrap.addEventListener("mouseenter", () => { clearTimeout(t); if (pop.hidden) { pops.forEach((p) => p.close()); pop.hidden = false; btn.setAttribute("aria-expanded", "true"); byHover = true; } });
    wrap.addEventListener("mouseleave", () => { if (byHover) t = setTimeout(() => { pop.hidden = true; btn.setAttribute("aria-expanded", "false"); byHover = false; }, 250); });
    btn.addEventListener("click", () => { if (byHover) { byHover = false; pop.hidden = false; btn.setAttribute("aria-expanded", "true"); } }, true);
  })();

  // ------------------------------------------------------------------ the Autopilot switch: /dev-kit:autopilot run by the board (dev_worker AutoExecutor)
  const AP_WORD = tmap({ off: N_("off"), idle: N_("starting"), running: N_("running"), stopping: N_("finishing the step"), waiting_user: N_("waiting for you"),
    release: N_("waiting for your approval"), stable: N_("project stable"), waiting_session: N_("waiting for another session"), backoff: N_("retrying soon"), stopped: N_("stopped") });
  const AP_CLASS = { off: "off", idle: "on", running: "on", stopping: "wait", waiting_user: "wait", release: "wait", stable: "off", waiting_session: "wait", backoff: "bad", stopped: "bad" };
  const AP_REASON = tmap({ milestone_done: N_("the last run closed a milestone"), waiting_for_user: N_("only work that needs you is left: answer in Needs you and it starts again"),
    release_approval: N_("a release waits for your approval in Needs you"), stable: N_("nothing is open"), until_reached: N_("the last run reached its target"),
    switched_off: N_("switched off"), force_stopped: N_("force-stopped"), no_change: N_("the last run changed nothing: look at its log"), failed: N_("a run failed"),
    request_running: N_("a Claude Code session runs a board request"), other_session: N_("/dev-kit:autopilot runs in another session"),
    no_claude: N_("the claude command was not found") });
  /** What a headless round works on: its tasks, or a warning when an implement round has none started. */
  function roundWhat(rd) {
    if (rd.tasks && rd.tasks.length) return tr("round on {v}", { v: rd.tasks.map((t) => t.id).join(", ") });
    return rd.unregistered ? tr("round with no task started in the state") : tr("headless round");
  }
  /** The round running now, in the Autopilot card: tasks (each opens its card) and its last action. */
  function roundBlock(rd) {
    if (!rd) return null;
    const last = rd.last;
    return h("div", { class: "ap-round" },
      h("p", { class: "ap-line" }, h("strong", { text: tr("Now: ") }), h("code", { text: `/dev-kit:${rd.skill} ${rd.scope || ""}`.trim() }),
        rd.since ? [tr(" for "), since(rd.since)] : null),
      rd.tasks && rd.tasks.length ? h("p", { class: "card-sub" }, tr("Tasks: "), rd.tasks.map((t) => h("button", { type: "button", class: "tid-btn",
        text: t.id, title: t.title || t.id, onclick: () => openTask(t.id) })))
        : rd.unregistered ? h("p", { class: "card-sub warn-text", text: tr("No task is started in the state while this round works: the board cannot say which one runs. The round's reconcile fixes it when it ends.") }) : null,
      last ? h("p", { class: "card-sub" }, tr("Last action: "), h("code", { text: `${last.tool || ""}${last.what ? ` · ${last.what}` : ""}` }),
        last.agent ? ` (${last.agent})` : null, last.at ? [" · ", ago(parseT(last.at))] : null) : null);
  }
  function renderAutopilot() {
    const wrap = $("ap-wrap");
    wrap.hidden = !actionsOn();
    if (wrap.hidden) return;
    const ap = inbox().autopilot || { on: false, state: "off" };
    const sw = $("ap-switch");
    sw.setAttribute("aria-checked", String(Boolean(ap.on)));
    sw.classList.toggle("on", Boolean(ap.on));
    const st = $("ap-btn");
    st.className = `ap-state ${AP_CLASS[ap.state] || "off"}`;
    const waitN = ap.state === "waiting_user" ? needsN : 0;
    const rd = ap.round;
    const word = ap.state === "stopping" && rd ? tr("finishing {v}", { v: `${rd.skill} ${rd.scope || ""}`.trim() }) : AP_WORD[ap.state] || ap.state;
    fill($("ap-word"), word, ap.state === "running" && ap.since ? [" · ", since(ap.since)] : null, waitN ? ` · ${waitN}` : null);
    st.setAttribute("aria-label", tr("Autopilot: {v}. Show details", { v: AP_WORD[ap.state] || ap.state }));
    const reason = ap.reason ? (AP_REASON[ap.reason] || ap.reason) : null;
    fill($("ap-pop"), h("p", { class: "pop-title", text: tr("Autopilot") }),
      h("p", { class: "ap-line" }, h("strong", { text: word }), reason ? ` · ${reason}` : null,
        ap.state === "backoff" && ap.until ? ` · ${tr("next try at {v}", { v: new Date(ap.until * 1000).toLocaleTimeString(LANG, { hour: "2-digit", minute: "2-digit" }) })}` : null),
      ap.note ? h("p", { class: "card-sub", text: ap.note }) : null,
      roundBlock(rd),
      ap.where === "session"
        ? h("p", { class: "pop-note top" }, tr("Runs "), h("code", { text: ap.command || "/dev-kit:autopilot --milestones 1 --board --rounds session" }),
          tr(" in the Claude Code session that listens to the board, one milestone per run, until a release waits for your approval: its implementers and auditors show in that session's task list. Questions and permissions go to Needs you."))
        : h("p", { class: "pop-note top" }, tr("Runs "), h("code", { text: ap.command || "/dev-kit:autopilot --milestones 1 --board" }),
          tr(" headless, one milestone per run, until a release waits for your approval. Questions and permissions go to Needs you. Output: "), h("code", { text: ".dev/run/autopilot.log" })),
      ap.runs ? h("p", { class: "card-sub", text: plural(ap.runs, "run") }) : null,
      parallelRow(ap),
      h("div", { class: "ap-actions" },
        ap.state === "waiting_user" || ap.state === "release" ? h("button", { type: "button", class: "btn btn-sm", text: tr("Open Needs you"), onclick: goNeeds }) : null,
        h("button", { type: "button", class: "btn btn-sm", text: ap.on ? (ap.state === "stopped" ? tr("Start again") : tr("Turn off")) : tr("Turn on"),
          onclick: () => setAutopilot(ap.state === "stopped" ? true : !ap.on) }),
        ap.state === "running" || ap.state === "stopping" ? h("button", { type: "button", class: "btn btn-sm btn-danger", text: tr("Force stop"), onclick: forceStop }) : null));
  }
  /** Implementers at once (1-6, default 3): `implement` reads it before every batch, so a change applies from the next one. */
  function parallelRow(ap) {
    const n = ap.parallel || 3, [lo, hi] = ap.parallel_range || [1, 6];
    const busy = activeAgents().filter((a) => a.agent === "implementer").length;
    const step = (d, label) => h("button", { type: "button", class: "btn btn-sm ap-step", text: d < 0 ? "−" : "+", "aria-label": label,
      disabled: (d < 0 ? n <= lo : n >= hi) ? "" : null, onclick: () => setParallel(n + d) });
    return h("div", { class: "ap-par" },
      h("div", { class: "ap-par-row" }, h("span", { class: "ap-par-label", id: "ap-par-label", text: tr("Implementers at once") }),
        h("span", { class: "ap-stepper", role: "group", "aria-labelledby": "ap-par-label" }, step(-1, tr("Fewer implementers")),
          h("output", { class: "ap-par-n", "aria-live": "polite", text: String(n) }), step(1, tr("More implementers"))),
        h("span", { class: "card-sub", text: tr("{v} running now", { v: String(busy) }) })),
      h("p", { class: "pop-note", text: n === 1 ? tr("1 = one task at a time.")
        : tr("Applies from the next batch. Only tasks with no file in common run together. More at once costs no more tokens, but uses more CPU and disk and reaches the account's usage limits sooner.") }));
  }
  async function setParallel(n) {
    try { await api("/api/autopilot", { parallel: n }); toast(tr("{v} implementers at once, from the next batch.", { v: String(n) })); load(); } catch (e) { toast(e.message, true); }
  }
  async function setAutopilot(on) {
    try {
      const d = await api("/api/autopilot", { on });
      toast(on ? tr("Autopilot on: the board starts /dev-kit:autopilot in a few seconds.")
        : d.autopilot && d.autopilot.state === "stopping" ? tr("Autopilot off: the run finishes its step, then stops.") : tr("Autopilot off."));
      load();
    } catch (e) { toast(e.message, true); }
  }
  async function forceStop() {
    try { await api("/api/autopilot", { force_stop: true }); toast(tr("Autopilot stopped now.")); load(); } catch (e) { toast(e.message, true); }
  }
  $("ap-switch").addEventListener("click", () => { const ap = inbox().autopilot || {}; setAutopilot(ap.state === "stopped" ? true : !ap.on); });

  function renderHeader() {
    $("project").textContent = data.project;
    renderRunning();
    renderAutopilot();
    $("kit-ver").textContent = data.kit && data.kit !== "unknown" ? `v${data.kit}` : "";
    $("bf-mode").textContent = data.brownfield ? tr("existing project · {v} · since {v2}", { v: data.brownfield.mode || "feature", v2: data.brownfield.baseline_ref || "baseline" }) : "";
    renderPhaseTabs();
  }

  // ------------------------------------------------------------------ the phase tabs: the five lanes of docs/dev-kit-flow.svg, in its order and colours
  // Conception (1), Planning (2), Milestones and Releases (both 3, construction) and Stable (4). The Map shows all five at once.
  /** The state of a lane: done, current (the project is there) or upcoming; Releases is current while a release is past its milestones. */
  function laneState(k) {
    if (k === "releases") {
      const rp = relPlan();
      if (!rp.length) return "upcoming";
      if (rp.every((r) => r.status === "released")) return "done";
      return rp.some((r) => ["ready_for_review", "awaiting_approval", "deploying_prod"].includes(r.status)) ? "current" : rp.some((r) => r.status === "released") ? "active" : "upcoming";
    }
    const p = data.cycle.phases.find((x) => x.key === k);
    return p ? (p.state === "active" ? "active" : p.state) : "upcoming";
  }
  /** One short line under the name of a lane: how far it got. */
  function laneStatus(k) {
    const st = laneState(k);
    const word = st === "done" ? tr("✓ done") : "";
    if (k === "conception") {
      const live = (phaseOf("conception").steps || []).filter((x) => x.state !== "skipped");
      const n = live.filter((x) => x.state === "done").length;
      return [word, live.length ? `${n}/${live.length}` : ""].filter(Boolean).join(" · ");
    }
    if (k === "planning") { const s = (phaseOf("planning").steps || [])[0]; return st === "done" ? tr("✓ plan confirmed") : s ? STEP_WORD[s.state] : ""; }
    if (k === "construction") {
      const m = data.milestones.find((x) => x.id === data.current_milestone);
      const closed = data.milestones.filter(isClosed).length;
      return m ? `${m.id} · ${milestoneInfo(m).done}/${milestoneInfo(m).total}` : data.milestones.length ? tr("{closed}/{n} closed", { closed, n: data.milestones.length }) : tr("no milestones yet");
    }
    if (k === "releases") {
      const rp = relPlan();
      if (!rp.length) return tr("no planned releases");
      const wait = rp.find((r) => r.status === "awaiting_approval");
      if (wait) return tr("{id} awaits you", { id: wait.id });
      return tr("{out}/{rp_n} released", { out: rp.filter((r) => r.status === "released").length, rp_n: rp.length });
    }
    const hc = data.prod_health;
    if (hc && hc.last) return hc.last.ok ? tr("production healthy") : tr("production failing");
    return data.phase === "stable" ? tr("nothing open") : plural((data.releases || []).length, "release");
  }
  const LANE_TIP = tmap({ conception: N_("Interview, PRD, architecture and design, with your confirmation of the PRD"),
    planning: N_("Releases, milestones and tasks, with your confirmation of the plan"), construction: N_("Construction, one milestone at a time: build, QA and its gate"),
    releases: N_("Construction, per release: usability, audit, review, your approval and production"), stable: N_("Nothing open: production health and the next issue") });
  /** The runs of a lane: release checks and releases count for the Releases lane. */
  const laneRuns = (k) => skillRuns().filter((r) => { const p = runPlace(r); return p && (p[0] === "stable" && ["checks", "releases"].includes(p[1]) ? "releases" : p[0]) === k; });
  function renderPhaseTabs() {
    const shown = shownPhase();
    const here = data.phase;
    $("phase-step").textContent = tr("Now: {v}{v2}", { v: PHASE_NAME[data.phase], v2: data.step ? ` · ${STEP_NAME[data.step] || data.step}` : "" })
      + (data.reopened ? tr(" · reopened by a change, construction goes on") : "");
    $("phase-back").hidden = shown === here;
    $("ph-map").setAttribute("aria-pressed", String(shown === "map"));
    $("ph-arch").setAttribute("aria-pressed", String(shown === "arch"));
    fill($("phases"), LANES.map((k) => {
      const sel = k === shown;
      const st = laneState(k);
      const now = k === here || (k === "releases" && st === "current");
      const need = needsBy[k] || 0;
      const running = laneRuns(k);
      const reopened = ((data.cycle.phases.find((p) => p.key === k) || {}).reopened) || false;
      return h("button", { type: "button", role: "tab", id: `ph-${k}`, "aria-controls": `phase-${k}`, "aria-selected": String(sel), tabindex: sel ? "0" : "-1",
        class: `ptab lane-${k} st-${st}${now ? " now" : ""}${sel ? " sel" : ""}`, title: LANE_TIP[k], onclick: () => setPhase(k) },
      h("span", { class: "ptab-num", "aria-hidden": "true", text: st === "done" ? "✓" : LANE_NUM[k] }),
      h("span", { class: "ptab-body" },
        h("span", { class: "ptab-kicker", text: k === "construction" || k === "releases" ? tr("{n} · Construction", { n: LANE_NUM[k] }) : tr("Phase {n}", { n: LANE_NUM[k] }) }),
        h("span", { class: "ptab-name" }, LANE_NAME[k], reopened ? h("span", { class: "ptab-tag", text: tr("reopened") }) : null),
        h("span", { class: "ptab-status", text: laneStatus(k) })),
      now ? h("span", { class: "ptab-now", text: tr("now") }) : null,
      running.length ? h("span", { class: "ptab-run", title: tr("Running now in {v}: {v2}", { v: LANE_NAME[k], v2: running.map(runCmd).join(", ") }) },
        h("span", { class: "rn-dot", "aria-hidden": "true" }), h("span", { class: "visually-hidden", text: tr("running") })) : null,
      need ? h("span", { class: "ptab-needs", title: tr("{v} in Needs you", { v: plural(need, "item") }), text: String(need) }) : null,
      h("span", { class: "visually-hidden", text: `: ${PHASE_WORD[st === "active" ? "current" : st] || ""}${now ? tr(", the project is here") : ""}${need ? tr(", {v} need you", { v: plural(need, "item") }) : ""}.` }));
    }));
    tabInSight();
  }
  // on a narrow screen the tabs scroll sideways: keep the one shown in sight
  const tabInSight = () => { const el = $(`ph-${shownPhase()}`); const bar = document.querySelector(".phasebar");
    if (el && bar && bar.scrollWidth > bar.clientWidth) bar.scrollLeft = Math.max(0, el.offsetLeft - 80); };
  function setPhase(p, focus) {
    closeDrawers(); closeList();
    phasePick = data && p === data.phase ? null : p;   // picking the current phase goes back to following it
    if (p !== "planning") replanOpen = false;
    render();
    const el = $(p === "map" ? "ph-map" : p === "arch" ? "ph-arch" : `ph-${shownPhase()}`);
    if (focus && el) el.focus();
  }
  $("phase-back").addEventListener("click", () => setPhase(data.phase, true));
  $("ph-map").addEventListener("click", () => setPhase(shownPhase() === "map" ? data.phase : "map"));
  $("ph-arch").addEventListener("click", () => setPhase(shownPhase() === "arch" ? data.phase : "arch"));
  $("phases").addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key) || !data || !data.ok) return;
    const keys = LANES;
    let i = Math.max(0, keys.indexOf(shownPhase()));
    i = e.key === "Home" ? 0 : e.key === "End" ? keys.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + keys.length) % keys.length;
    setPhase(keys[i], true); e.preventDefault();
  });

  // ------------------------------------------------------------------ the flow of a lane: the steps of the diagram, coloured by who does them
  // kind: "" (a skill), "human" (yours, yellow), "work" (agents, orange), "ship" (delivery, green), "gate" (a check that can fail, red)
  // state: done, current, todo, failed, skipped. A node opens its details; the strip's detail line says what happens at the current one.
  const NODE_WORD = tmap({ done: N_("done"), current: N_("in progress"), todo: N_("not started"), failed: N_("needs a decision"), skipped: N_("does not apply"), waiting: N_("waiting for you") });
  const NODE_MARK = { done: "✓", current: "●", todo: "", failed: "!", skipped: "–", waiting: "!" };
  function flowNode(n, compact) {
    const st = n.state === "current" && n.kind === "human" ? "waiting" : n.state;
    const label = `${n.label}: ${NODE_WORD[st] || st}${n.need ? tr(", {v} need you", { v: plural(n.need, "item") }) : ""}${n.running ? tr(", running now") : ""}`;
    return h("li", { class: `fnode k-${n.kind || "skill"} s-${st}${n.here ? " here" : ""}${n.running ? " running" : ""}` },
      h("button", { type: "button", class: "fnode-btn", "aria-label": label, title: n.title || null, "aria-current": n.here ? "step" : null,
        onclick: () => openNode(n) },
      n.here && !compact ? h("span", { class: "fnode-now", "aria-hidden": "true", text: st === "waiting" ? tr("you") : tr("now") }) : null,
      n.need ? h("span", { class: "fnode-need", "aria-hidden": "true", text: compact ? String(n.need) : (n.needText || plural(n.need, "item")) }) : null,
      h("span", { class: "fnode-top", "aria-hidden": "true" },
        NODE_MARK[st] ? h("span", { class: "fnode-mark", text: NODE_MARK[st] }) : null,
        h("span", { class: "fnode-label", text: n.label })),
      !compact && n.sub ? h("span", { class: "fnode-sub", "aria-hidden": "true", text: n.sub }) : null,
      n.agents && n.agents.length ? h("span", { class: "fnode-agents", "aria-hidden": "true" }, n.agents.slice(0, 6).map((a) => h("span", { class: agentDot(a.agent), title: a.agent }))) : null));
  }
  const flowList = (nodes, compact, label) => h("ol", { class: `flow${compact ? " compact" : ""}`, "aria-label": label || null }, nodes.map((n) => flowNode(n, compact)));
  /** The details of one step of the flow, in a modal. */
  function openNode(n) {
    const st = n.state === "current" && n.kind === "human" ? "waiting" : n.state;
    openList(n.label, [
      h("div", { class: "node-state" }, h("span", { class: `chip node-chip s-${st} k-${n.kind || "skill"}`, text: NODE_WORD[st] || st }), n.who ? h("span", { class: "card-sub", text: n.who }) : null),
      n.about ? h("p", { class: "node-about", text: n.about }) : null,
      n.sub ? h("p", { class: "card-sub", text: n.sub }) : null,
      n.detail ? n.detail() : null,
      n.need ? h("p", {}, h("button", { type: "button", class: "btn btn-sm btn-danger", text: tr("Open Needs you"), onclick: () => { closeList(); goNeeds(); } })) : null]);
  }
  /** The head of a lane's strip: "1 · Conception", a line on where it is, and a slot on the right (a selector or an action). */
  function stripHead(k, sub, right) {
    return h("div", { class: "strip-head" }, h("h2", { class: "strip-title", id: `${k}-strip-h` }, h("span", { class: "strip-num", text: LANE_NUM[k] }), " ", LANE_NAME[k]),
      sub ? h("span", { class: "strip-sub" }, sub) : null, right || null);
  }
  const flowDetail = (...kids) => { const k = kids.flat().filter(Boolean); return k.length ? h("div", { class: "flow-detail" }, k) : null; };

  // ------------------------------------------------------------------ planned releases
  const relPlan = () => (data && data.cycle && data.cycle.releases) || [];
  /** The milestones the selector shows: all of them, grouped by release when there are planned releases. */
  function msInView() { return data.milestones; }
  function currentId() {
    const ms = msInView();
    const ids = ms.map((m) => m.id);
    if (selected && ids.includes(selected)) return selected;
    if (data.current_milestone && ids.includes(data.current_milestone)) return data.current_milestone;
    const open = ms.find((m) => m.gate === "pending" && tasksOf(m).length);
    return (open && open.id) || ids[ids.length - 1] || null;
  }
  const REL_WORD = tmap({ in_progress: N_("in progress"), ready_for_review: N_("ready for review"), awaiting_approval: N_("waiting for your approval"),
    deploying_prod: N_("approved · going to production"), released: N_("released") });
  /** Approve, or reject with what must change: queued for Claude Code, which records it (release-decide --request). */
  const rejectDrafts = {};
  function releaseDecision(r) {
    if (!actionsOn()) return h("span", { class: "sub" }, tr("Decide in Claude Code with "), cmd("/dev-kit:release"));
    const sent = inbox().open.find((x) => x.action === "release_decision" && x.args && x.args.release === r.id);
    if (sent) return h("div", { class: "sub answer-sent", text: tr("Decision sent ({id}): {decision}. Claude Code applies it.", { id: sent.id, decision: sent.args.decision }) });
    const box = h("div", { class: "sub answer rel-decide", role: "group", "aria-label": tr("Decision on {id}", { id: r.id }) });
    const ta = h("textarea", { id: `rej-${r.id}`, maxlength: "4000", rows: "3", class: "answer-input", "aria-label": tr("What must change in {id}, one item per line", { id: r.id }),
      placeholder: tr("What must change, one item per line (each becomes a fix task)") });
    ta.value = rejectDrafts[r.id] || "";
    ta.addEventListener("input", () => { rejectDrafts[r.id] = ta.value; });
    const send = async (args, el) => { el.disabled = true; try { await queue("release_decision", { release: r.id, ...args }); delete rejectDrafts[r.id]; } catch (e) { el.disabled = false; } };
    box.append(
      h("button", { type: "button", class: "btn btn-sm btn-primary", text: tr("Approve {id}", { id: r.id }), onclick: (e) => send({ decision: "approve" }, e.currentTarget) }),
      h("span", { class: "answer-free" }, ta, h("button", { type: "button", class: "btn btn-sm btn-danger", id: `rej-send-${r.id}`, text: tr("Reject"),
        onclick: (e) => { const v = ta.value.trim(); if (v) send({ decision: "reject", feedback: v }, e.currentTarget); else { ta.focus(); toast(tr("Write what must change before rejecting."), true); } } })));
    return box;
  }

  // ------------------------------------------------------------------ Releases: the release picked (the next to ship by default), its flow and four tiles
  let relView = null;
  const relPick = () => { const rp = relPlan(); return rp.find((r) => r.id === relView) || rp.find((r) => r.status !== "released") || rp[rp.length - 1] || null; };
  function openRelease(id) {
    relView = id;
    setPhase("releases");
    try { history.replaceState(null, "", `#release:${id}`); } catch (e) { /* the link is a convenience */ }
  }
  const relMs = (r) => r.milestones.map((id) => data.milestones.find((m) => m.id === id)).filter(Boolean);
  const isClosed = (m) => m.gate === "passed" || m.gate === "skipped";
  /** What a release adds up to, from the milestones it holds: progress, cost, time and pace. */
  function relTotals(r) {
    const ms = relMs(r);
    const live = ms.filter((m) => tasksOf(m).length);
    const ts = ms.flatMap(tasksOf).filter((t) => t.status !== "dropped");
    const done = ts.filter((t) => t.status === "done").length;
    const span = workSpan(ts);
    let elapsed = null, work = null;
    if (span) {
      const allClosed = live.length > 0 && live.every(isClosed);
      const ends = live.map((m) => parseT(m.passed_at)).concat(ts.map((t) => parseT(t.done_at))).filter(Number.isFinite);
      const end = allClosed && ends.length ? Math.max(...ends) : span.now;
      elapsed = Math.max(0, end - span.start) / 36e5;
      work = span.work / 36e5;
    }
    // cost: dollars when every milestone has them, tokens otherwise; "+" says some part is missing
    let usd = 0, tok = 0, any = false, complete = true;
    r.milestones.forEach((id) => {
      const c = (data.milestone_costs || {})[id];
      if (!c) { if (tasksOf(data.milestones.find((m) => m.id === id)).length) complete = false; return; }
      any = true;
      usd += Number(c.usd) || 0;
      tok += Number(c.tokens) || 0;
      if (c.usd_complete === false || (!(Number(c.usd) > 0) && Number(c.tokens) > 0)) complete = false;
    });
    const spend = !any ? null : usd > 0 ? { text: tr("US$ {v}{v2}", { v: usd.toFixed(2), v2: complete ? "" : "+" }), title: complete ? tr("Estimated cost, API-equivalent") : tr("At least this much: some work has no price yet") }
      : tok > 0 ? { text: tr("{v} tok", { v: compact(tok) }), title: tr("Tokens used (no price measured)") } : null;
    const gates = live.filter(isClosed).length;
    return { ms, live, ts, done, elapsed, work, spend, gates, pace: work && done ? done / work : null };
  }
  const bar = (done, total, label) => {
    const mm = h("div", { class: "meter", role: "img", "aria-label": label });
    const sp = h("span"); sp.style.width = `${total ? Math.round((100 * done) / total) : 0}%`;
    mm.append(sp);
    return mm;
  };
  /** The six steps of a release (diagram lane "3 · Releases"), from its status and the release checks of the one being built. */
  function relNodes(r) {
    const lc = data.lifecycle || {};
    const prodOn = lc.deploy_when && lc.deploy_when !== "none";
    const order = ["in_progress", "ready_for_review", "awaiting_approval", "deploying_prod", "released"];
    const at = order.indexOf(r.status);
    const cr = data.cycle.release && data.cycle.release.release === r.id ? data.cycle.release : null;
    const okv = (v) => v === "done" || v === "n/a";
    const checksDone = at >= 2 || (cr && okv(cr.usability) && okv(cr.docs));
    const releasing = r.status !== "released" && runsAt("releases").length > 0;
    const notes = (data.releases || []).filter((x) => x.release === r.id).map((x) => x.tag || x.version).join(", ");
    const sub = (v) => (v === "done" ? tr("done") : v === "n/a" ? tr("not needed") : v === "review" ? tr("in review") : null);
    const nodes = [
      { key: "checks", label: tr("Usability, docs"), kind: "", sub: cr ? [cr.usability ? `${tr("usability")} ${sub(cr.usability) || "○"}` : null, cr.docs ? `${tr("docs")} ${sub(cr.docs) || "○"}` : null].filter(Boolean).join(" · ") : tr("a11y · ux · copy · docs"),
        state: checksDone ? "done" : at === 1 ? "current" : "todo", about: tr("Usability (a11y, UX, copy) and the docs, with their reviews"), run: at === 1 && !checksDone ? "/dev-kit:usability" : null },
      { key: "audit", label: tr("Release audit"), kind: "work", sub: tr("security · ops · deps"), state: at >= 2 ? "done" : at === 1 && checksDone ? "current" : "todo", running: releasing && at === 1,
        about: tr("Security, operations, dependencies, spec and performance, over the whole release") },
      { key: "review", label: tr("Release review"), kind: "", sub: r.review_doc ? "review.md" : tr("releases/{id}/review.md", { id: r.id }), state: at >= 2 ? "done" : at === 1 && checksDone ? "current" : "todo",
        about: tr("The review that goes to you: what is in the release and how it went"), run: at === 1 ? "/dev-kit:release" : null,
        detail: () => (r.review_doc ? h("p", {}, docLink(r.review_doc, tr("Open the release review"))) : null) },
      { key: "approval", label: tr("Your approval"), kind: "human", sub: tr("approve or reject"), state: at > 2 ? "done" : at === 2 ? "current" : "todo", need: at === 2 ? 1 : 0, needText: tr("waiting"),
        about: tr("Approve it, or reject it with what must change: a fixes milestone in the same release follows"), detail: () => (at === 2 ? releaseDecision(r) : null) },
      { key: "prod", label: tr("Production"), kind: "ship", sub: prodOn ? tr("deploy · smoke · flag on") : tr("no production"), state: !prodOn ? "skipped" : at > 3 ? "done" : at === 3 ? "current" : "todo",
        running: releasing && at === 3, run: at === 3 ? "/dev-kit:release" : null },
      { key: "released", label: tr("Released"), kind: "ship", sub: notes || tr("tag and notes"), state: at === 4 ? "done" : "todo" },
    ];
    const here = nodes.find((n) => n.state === "current");
    if (here) here.here = true;
    return nodes;
  }
  function renderReleasesPanel() {
    const rp = relPlan();
    const r = relPick();
    const strip = $("rel-strip");
    if (!r) {
      fill(strip, stripHead("releases", tr("No planned releases. Group the milestones with /dev-kit:plan.")), flowList(relNodes({ id: "R1", status: "in_progress", milestones: [], closed: [], history: [] }), false, tr("Stages of a release")));
      fill($("rel-tiles"), h("div", { class: "empty wide" }, tr("No planned releases. Group the milestones with "), cmd("/dev-kit:plan"), "."));
      return;
    }
    const t = relTotals(r);
    const selector = h("div", { class: "selector" }, h("span", { class: "sel-label", text: tr("Release") }),
      h("div", { class: "sel-groups", role: "tablist", id: "rel-tabs", "aria-label": tr("Releases") }, h("div", { class: "sel-group" }, rp.map((x) => {
        const done = x.status === "released", sel = x.id === r.id;
        const ver = (data.releases || []).filter((v) => v.release === x.id).map((v) => v.tag || v.version).pop();
        return h("button", { type: "button", role: "tab", id: `rel-${x.id}`, "aria-selected": String(sel), tabindex: sel ? "0" : "-1", class: `sel-btn${done ? " ok" : ""}${sel ? " sel" : ""}${x.status === "awaiting_approval" ? " wait" : ""}`,
          title: `${x.id} · ${x.title}: ${REL_WORD[x.status]}${relTook(x) ? ` · ${tr("took {v}", { v: relTook(x).text })}` : ""}`, onclick: () => { relView = x.id; render(); $(`rel-${x.id}`) && $(`rel-${x.id}`).focus(); } },
        h("strong", { text: x.id }), done ? h("span", { class: "sel-meta", text: `✓ ${ver || ""}`.trim() }) : h("span", { class: "sel-meta", text: `${x.closed.length}/${x.milestones.length}` }));
      }))));
    const rej = (r.history || []).filter((x) => x.event === "rejected");
    const waiting = r.status === "in_progress" ? r.milestones.filter((id) => { const m = data.milestones.find((x) => x.id === id); return m && !isClosed(m); }) : [];
    const rt = relTook(r);
    const sub = [h("strong", { text: `${r.id} · ${r.title || r.id}` }), ` · ${REL_WORD[r.status] || r.status}`,
      rt ? h("span", { class: "took", title: rt.title, text: tr(" in {v}", { v: rt.text }) }) : "",
      waiting.length ? tr(" · starts when {v} pass their gate", { v: waiting.join(", ") }) : ""];
    const nodes = relNodes(r);
    const here = nodes.find((n) => n.here);
    const fc = fcFor("releases", "release", r.id);
    fill(strip, stripHead("releases", sub, selector), flowList(nodes, false, tr("Stages of {id}", { id: r.id })),
      h("div", { class: `rel-reject${rej.length ? " hit" : ""}` }, h("span", { class: "rel-reject-ico", "aria-hidden": "true", text: "↺" }),
        rej.length ? tr("Rejected {v}: fixes in {m}, then back to the loop", { v: plural(rej.length, "time"), m: rej.map((x) => x.milestone).filter(Boolean).join(", ") || "M?" })
          : tr("If you reject it: a fixes milestone in the same release, back to the loop")),
      flowDetail(
        here && here.key === "approval" ? [r.review_doc ? h("span", { class: "sub" }, docLink(r.review_doc, tr("Open the release review"))) : null, releaseDecision(r)] : null,
        here && here.run && !(here.key === "approval") ? [h("span", { class: "fd-word", text: here.label }), cmd(here.run)] : null,
        !here && r.status === "in_progress" ? [h("span", { class: "fd-word", text: tr("Building the milestones") }), h("span", { class: "sub", text: tr("{closed}/{n} closed", { closed: r.closed.length, n: r.milestones.length }) }), forecastChip(fcFor("releases", "release", r.id))] : null,
        here && runsAt("releases").length ? runBanner(runsAt("releases")) : null));
    // tiles: the release in numbers, its milestones, what holds it back, quality and documents
    const ids = new Set(r.milestones);
    const fact = (label, value, title) => h("div", { class: "fact", title: title || null }, h("span", { class: "fact-label", text: label }), h("strong", { class: "fact-value", text: value }));
    const overview = [bar(t.done, t.ts.length, tr("{done} of {ts_n} tasks done", { done: t.done, ts_n: t.ts.length })),
      h("div", { class: "facts-grid" },
        fact(tr("Tasks"), `${t.done}/${t.ts.length}`),
        fact(tr("Milestones"), tr("{closed_n}/{live_n} closed", { closed_n: r.closed.length, live_n: t.live.length })),
        fact(tr("QA gates"), tr("{gates}/{live_n} passed", { gates: t.gates, live_n: t.live.length })),
        fact(tr("Cost"), t.spend ? t.spend.text : "—", t.spend && t.spend.title),
        fact(tr("Time"), fmtH(t.work), rt ? rt.title : t.elapsed != null ? tr("{v} from the first task to {v2}", { v: fmtH(t.elapsed), v2: r.status === "released" || r.status === "ready_for_review" ? tr("the last gate") : "now" }) : tr("No task started")),
        fact(tr("Pace"), t.pace != null ? tr("{v} tasks/h", { v: t.pace.toFixed(1) }) : "—", tr("Tasks done per working hour, parallel work counted once")))];
    const msRows = () => t.ms.map((m) => {
      const x = milestoneInfo(m), tm = msTiming(m), sp = msSpend(m.id), q = qaState(m);
      return h("li", { class: "has-btn" }, h("button", { type: "button", class: "row-btn", title: tr("Show {id} in construction", { id: m.id }), onclick: () => { closeList(); openMilestone(m.id); } },
        h("span", { class: "id", text: m.id }), h("span", { text: m.title || "" }),
        h("span", { class: `chip${isClosed(m) ? " good" : ""}`, text: isClosed(m) ? tr("gate {gate}{v}", { gate: GATE_WORD[m.gate] || m.gate, v: m.score != null ? ` · ${m.score}` : "" }) : q.running ? tr("QA running") : tr("{done}/{total} tasks", { done: x.done, total: x.total }) }),
        q.qa.runs > 1 ? h("span", { class: "chip", text: plural(q.qa.runs - 1, "fix round") }) : null,
        h("span", { class: "sub", title: msTook(m) ? msTook(m).title : null, text: [msTook(m) ? tr("took {v}", { v: msTook(m).text }) : tm ? fmtH(tm.work) : null, sp ? sp.text : null].filter(Boolean).join(" · ") })));
    });
    const fixes = t.ts.filter((x) => x.type === "fix");
    const issues = Object.entries(((data.backlog || {}).issues) || {}).filter(([, i]) => ids.has(i.scheduled_in)).map(([id, i]) => ({ id, ...i }));
    const blocked = t.ts.filter((x) => x.status === "blocked");
    const stuck = t.ms.filter((m) => qaState(m).exhausted);
    const hot = ((data.backlog || {}).hotfix_open || []);
    const holdRows = () => blocked.map((x) => h("li", { class: "has-btn" }, h("button", { type: "button", class: "row-btn", "data-tid": x.id, onclick: () => openTask(x.id) },
      h("span", { class: "id", text: x.id }), h("span", { text: x.title || "" }), h("span", { class: "chip", text: tr("blocked") }), h("span", { class: "sub", text: x.blocked_reason || "" }))))
      .concat(stuck.map((m) => h("li", {}, h("span", { class: "id", text: m.id }), h("span", { text: tr("QA rounds used up. Keep fixing, accept with an ADR, or replan.") }), h("span", { class: "sub" }, cmd(`/dev-kit:qa ${m.id}`)))))
      .concat(hot.map((id) => h("li", {}, issueId(id), h("span", { text: (data.tasks[id] || ((data.backlog || {}).issues || {})[id] || {}).title || "" }), h("span", { class: "chip lane-hotfix", text: tr("hotfix") }))));
    const fixRows = () => fixes.map((x) => h("li", { class: "has-btn" }, h("button", { type: "button", class: "row-btn", "data-tid": x.id, onclick: () => openTask(x.id) },
      h("span", { class: "id", text: x.id }), h("span", { text: x.title || "" }), h("span", { class: `chip st-chip s-${x.status}`, text: stLabel(x.status) }),
      h("span", { class: "sub", text: [x.milestone, String(x.source || "").startsWith("release:") ? tr("from a rejection") : tr("from QA")].join(" · ") }))));
    const holdBody = () => [listBlock(tr("Holding the release back"), holdRows(), tr("Nothing blocks this release."), true),
      listBlock(tr("Fixes"), fixRows(), tr("No fix tasks."), true), listBlock(tr("Issues scheduled in it"), issues.map(issueLi), tr("No issue is scheduled in this release."), true)];
    const cut = (data.quality || {}).min_overall;
    const scores = () => t.ms.filter((m) => m.qa && m.qa.last).map((m) => dodRow(tr("{id} QA", { id: m.id }), m.qa.last.overall, m.qa.last.cutoff != null ? m.qa.last.cutoff : cut != null ? cut : 80, m.qa.last.verdict,
      hasDoc(`qa/${m.id}/report.md`) ? [docLink(`qa/${m.id}/report.md`, tr("Report"))] : []));
    const hist = ((data.release_history || {})[r.id] || []).slice().reverse();
    const histRows = () => hist.map((x) => h("li", {}, h("span", { class: `chip${x.event === "rejected" ? " bad" : x.event === "approved" || x.event === "released" ? " good" : ""}`, text: x.event }),
      h("span", { text: x.at ? fmtDT(parseT(x.at)) : "" }),
      x.event === "rejected" && x.milestone ? h("span", { class: "sub", text: tr("fixes in {milestone}{v}", { milestone: x.milestone, v: (x.tasks || []).length ? `: ${x.tasks.join(", ")}` : "" }) }) : null,
      x.event === "submitted" && x.review_doc ? h("span", { class: "sub" }, docLink(x.review_doc, tr("Release review"))) : null,
      x.event === "released" && x.version ? h("span", { class: "sub", text: x.version }) : null));
    const docs = () => {
      const out = [];
      if (r.review_doc) out.push(h("li", {}, docLink(r.review_doc, tr("Release review"))));
      (data.releases || []).filter((x) => x.release === r.id).forEach((x) => {
        const notes = `releases/release-notes-${x.version}.md`;
        const alt = (data.docs || []).find((p) => p.endsWith(`release-notes-${x.version}.md`));
        if (alt || hasDoc(notes)) out.push(h("li", {}, docLink(alt || notes, tr("Release notes {version}", { version: x.version }))));
      });
      r.milestones.forEach((id) => { if (hasDoc(`qa/${id}/report.md`)) out.push(h("li", {}, docLink(`qa/${id}/report.md`, tr("{id} QA report", { id })))); });
      return out;
    };
    const qualBody = () => [scores().length ? h("div", { class: "list" }, scores()) : null, listBlock(tr("Gate history"), histRows(), tr("Not submitted yet."), true), listBlock(tr("Documents"), docs(), tr("No document yet."), true)];
    fill($("rel-tiles"),
      tile({ title: tr("{id} in numbers", { id: r.id }), sub: fc ? forecastText(fc) : REL_WORD[r.status], body: overview }),
      tile({ title: tr("Milestones"), count: t.ms.length, sub: tr("{closed}/{n} closed", { closed: r.closed.length, n: r.milestones.length }), body: h("ul", { class: "list" }, msRows()), all: () => h("ul", { class: "list" }, msRows()) }),
      tile({ title: tr("Holding back, fixes and issues"), count: blocked.length + stuck.length + hot.length + fixes.length + issues.length || null, body: holdBody(), all: holdBody }),
      tile({ title: tr("Quality and documents"), sub: tr("QA scores, gate history, documents"), body: qualBody(), all: qualBody }));
  }
  const currentMilestone = () => (data && data.milestones.find((x) => x.id === currentId())) || null;
  function selectMilestone(id, focusTab) {
    selected = id; mobileCol = null;
    render();
    if (focusTab && $(`tab-${currentId()}`)) $(`tab-${currentId()}`).focus();
  }

  // ------------------------------------------------------------------ milestone: the selector (grouped by release), goal, progress
  function milestoneInfo(m) {
    const ts = tasksOf(m);
    return { active: ts.some((t) => t.status === "in_progress"), done: ts.filter((t) => t.status === "done").length, total: ts.length };
  }
  function renderTabs() {
    const cur = currentId();
    const ms = msInView();
    const rp = relPlan();
    const btn = (m) => {
      const x = milestoneInfo(m);
      const closed = isClosed(m);
      const inQa = !closed && x.total > 0 && x.done === x.total;
      const now = m.id === data.current_milestone;
      return h("button", {
        role: "tab", type: "button", id: `tab-${m.id}`, class: `sel-btn${closed ? " ok" : ""}${now ? " now" : ""}${m.id === cur ? " sel" : ""}${x.active || inQa ? " active" : ""}`,
        "aria-selected": String(m.id === cur), "aria-controls": "main", tabindex: m.id === cur ? "0" : "-1", title: tr("{v} · gate {gate}", { v: m.title || m.id, gate: m.gate }) + (msTook(m) ? ` · ${tr("took {v}", { v: msTook(m).text })}` : ""),
        onclick: () => selectMilestone(m.id, true),
      }, h("strong", { text: m.id }),
      closed ? h("span", { class: "sel-meta", "aria-hidden": "true", text: "✓" }) : x.total ? h("span", { class: "sel-meta", text: `${x.done}/${x.total}` }) : null,
      inQa ? h("span", { class: "tab-stage", title: tr("In QA & fixes"), "aria-label": tr("in QA & fixes"), text: "◐" }) : null,
      now ? h("span", { class: "visually-hidden", text: tr(", current") }) : null);
    };
    let groups;
    if (rp.length) {
      const inRel = new Set(rp.flatMap((r) => r.milestones));
      const loose = ms.filter((m) => !inRel.has(m.id));
      groups = rp.map((r) => [r.id, ms.filter((m) => r.milestones.includes(m.id))]).filter(([, l]) => l.length);
      if (loose.length) groups.push(["", loose]);
    } else groups = [["", ms]];
    fill($("tabs"), ms.length ? groups.map(([rid, list]) => h("div", { class: "sel-group", role: "presentation" },
      rid ? h("button", { type: "button", class: "sel-rel", title: tr("Open {id} in Releases", { id: rid }), tabindex: "-1", text: rid, onclick: () => openRelease(rid) }) : null,
      list.map(btn))) : h("span", { class: "card-sub" }, tr("No milestones yet. They appear after "), cmd("/dev-kit:plan"), "."));
    $("tabs-back").hidden = !data.current_milestone || cur === data.current_milestone;
    // keep the selected milestone in sight when the selector scrolls sideways
    const selBtn = $(`tab-${cur}`);
    if (selBtn && selBtn.scrollIntoView) selBtn.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
  $("tabs-back").addEventListener("click", () => { selected = null; selectMilestone(null, true); });

  function renderMilestone(m) {
    const ts = tasksOf(m);
    const counts = Object.fromEntries(STATUS.map((st) => [st.key, ts.filter((t) => t.status === st.key).length]));
    const pct = ts.length ? Math.round((counts.done / ts.length) * 100) : 0;
    $("ms-title").textContent = m ? `${m.id} · ${m.title || tr("Milestone")}` : tr("No milestone planned yet");
    const goal = $("ms-goal");
    if (m) goal.textContent = m.goal || tr("No goal paragraph in plan.md for this milestone.");
    else fill(goal, tr("Run "), cmd("/dev-kit:plan"), tr(" to create milestones and tasks."));
    goal.disabled = !m;
    $("ms-done").textContent = String(counts.done);
    $("ms-total").textContent = `/${plural(ts.length, "task")}`;
    // weighted progress: tasks 70%, QA 30% (0 before the first round, the blocking findings fixed so far, 100% when the gate passes)
    const st = m ? stagesOf(m) : [];
    const closedNow = st.length && st.at(-1).state === "done";
    const prog = m ? weightedProgress(m) : null;
    const took = closedNow ? msTook(m) : null;
    $("ms-pct").textContent = !m ? "" : closedNow ? (took ? tr(" · closed in {v}", { v: took.text }) : tr(" · closed")) : prog.runs ? tr(" · QA round {runs}", { runs: prog.runs }) : "";
    $("ms-pct").title = took ? took.title : m ? tr("{v}% of the milestone: tasks {pct}% (70% of the bar), QA {v2}% (30%)", { v: Math.round(prog.total * 100), pct, v2: Math.round(prog.qa * 100) }) : "";
    const order = ["done", "in_progress", "blocked", "todo"];
    const label = (k) => STATUS.find((x) => x.key === k).label;
    const tot = Math.max(1, ts.length);
    fill($("segbar"), order.filter((k) => counts[k]).map((k) => {
      const sp = h("span", { class: `st-${k}`, title: `${label(k)}: ${counts[k]}` });
      sp.style.flexGrow = String((0.7 * counts[k]) / tot);
      return sp;
    }), m && ts.length ? [["qa-done", prog.qa], ["qa-left", 1 - prog.qa]].filter(([, v]) => v > 0).map(([k, v]) => {
      const sp = h("span", { class: `st-${k}`, title: k === "qa-done" ? tr("QA: {v}%", { v: Math.round(prog.qa * 100) }) : tr("QA still to do") });
      sp.style.flexGrow = String(0.3 * v);
      return sp;
    }) : null);
    $("segbar").setAttribute("aria-label", order.map((k) => `${label(k)} ${counts[k]}`).join(", "));
    // only what belongs to this milestone: its issues and its forecast
    const b = data.backlog || {};
    const buf = b.buffer && m && b.buffer.milestone === m.id ? b.buffer : null;
    const sched = m ? Object.entries(b.issues || {}).filter(([, v]) => v.scheduled_in === m.id && ["scheduled", "in_progress"].includes(v.status)) : [];
    fill($("ms-facts"),
      buf || sched.length ? h("span", { title: [buf ? tr("{pct}% of the milestone reserved for issues", { pct: buf.pct }) : null, sched.length ? tr("Scheduled here: {v}", { v: sched.map(([id, v]) => `${id} ${v.title || ""}`).join("; ") }) : null].filter(Boolean).join("\n"),
        text: [buf ? (buf.capacity ? bufferText(buf) : `${plural(buf.used, "issue task")}`) : null, sched.length ? plural(sched.length, "issue") : null].filter(Boolean).join(" · ") }) : null,
      forecastChip(m && fcFor("milestones", "milestone", m.id)));
  }
  $("ms-goal").addEventListener("click", () => { const m = currentMilestone(); if (m) openList(`${m.id} · ${m.title || ""}`, [h("p", { class: "node-about", text: m.goal || tr("No goal paragraph in plan.md for this milestone.") }), hasDoc("plan.md") ? h("p", {}, docLink("plan.md", tr("Open plan.md"), m.id)) : null]); });
  // ------------------------------------------------------------------ forecast: probable finish (P50), late finish (P85), cost to finish
  const fcFor = (kind, key, id) => { const fc = data.forecast; return fc && fc.available ? (fc[kind] || []).find((x) => x[key] === id) || null : null; };
  const fcCost = (x) => (x && x.cost_p50_usd != null ? tr("~US$ {v}–{v2}", { v: Math.round(x.cost_p50_usd), v2: Math.round(x.cost_p85_usd) }) : "");
  function forecastText(x) {
    return x ? tr("probable {v}, by {v2}{v3}", { v: fmtDate(x.finish_p50), v2: fmtDate(x.finish_p85), v3: fcCost(x) ? tr(" · {v} to finish", { v: fcCost(x) }) : "" }) : "";
  }
  function forecastChip(x) {
    if (!x) return null;
    const fc = data.forecast;
    return h("span", { class: "fc", title: tr("Forecast from the pace of {v} ({v2} left): 50% chance by {v3}, 85% by {v4}", { v: fc.basis.join(", "), v2: plural(x.tasks_left, "task"), v3: fmtDT(x.finish_p50), v4: fmtDT(x.finish_p85) }),
      text: forecastText(x) });
  }
  /** The issue buffer of a milestone: the share reserved for issues, and what went past it with the user's confirmation. */
  function bufferText(b) {
    const over = b.capacity && b.used > b.capacity ? b.used - b.capacity : 0;
    return tr("Issue buffer {used}/{capacity}{v}", { used: b.used, capacity: b.capacity, v: over ? tr(" · {over} above the limit, confirmed by you", { over }) : "" });
  }
  /** Tasks 70%, QA 30%: 0 before the first round, then the blocking findings fixed (fix tasks done; at most 90% until
   * the gate), 100% when it passes. */
  function weightedProgress(m) {
    const x = qaState(m);
    const build = x.ts.filter((t) => !isFix(t));
    const tasks = build.length ? build.filter((t) => t.status === "done").length / build.length : 0;
    const qa = x.passed ? 1 : !x.qa.runs ? 0 : x.fixes.length ? 0.9 * (x.fixes.length - x.fixOpen.length) / x.fixes.length : 0;
    return { tasks, qa, total: 0.7 * tasks + 0.3 * qa, runs: x.qa.runs };
  }

  // ------------------------------------------------------------------ kanban
  function waitingOn(t) {
    return (t.deps || []).filter((d) => d && data.tasks[d] && data.tasks[d].status !== "done");
  }
  function taskCard(t) {
    const isNext = data.next && data.next.task === t.id;
    const wait = t.status === "done" ? [] : waitingOn(t);
    const here = agentsOn(t.id);
    return h("article", { class: `tcard s-${t.status}${isNext ? " next" : ""}`, "aria-label": tr("{id} {title}, {v}{v2}. Open details", { id: t.id, title: t.title, v: stLabel(t.status), v2: wait.length ? tr(", waiting on {v}", { v: wait.join(", ") }) : "" }),
      tabindex: "0", role: "button", "aria-haspopup": "dialog", "data-tid": t.id,
      onclick: () => openTask(t.id), onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openTask(t.id); } } },
      h("div", { class: "tcard-top" }, h("span", { class: "tid", text: t.id }), h("span", { class: "chip", text: t.type }),
        t.lane ? h("span", { class: `chip lane-${t.lane}`, text: t.lane }) : null,
        isNext ? h("span", { class: "chip next-chip", text: tr("next up") }) : null),
      h("div", { class: "tcard-title", text: t.title }),
      here.length ? h("div", { class: "tcard-agents" }, here.map((x) => h("span", { class: "agent-chip" }, agentBits(x)))) : null,
      t.status === "blocked" && t.blocked_reason ? h("div", { class: "reason", text: t.blocked_reason }) : null,
      h("div", { class: "tcard-meta" },
        wait.length ? h("span", { class: "chip wait", text: tr("Waiting on {v}", { v: wait.join(", ") }) }) : null,
        t.status === "todo" && !wait.length && !isNext ? h("span", { class: "chip ready", text: tr("Ready") }) : null,
        t.acceptance ? h("span", { title: tr("Acceptance criteria"), text: tr("{acceptance} AC", { acceptance: t.acceptance }) }) : null,
        t.status === "in_progress" && t.started_at ? h("span", { text: tr("started {v}", { v: ago(parseT(t.started_at)) }) }) : null,
        t.status === "done" && t.done_at ? h("span", { text: tr("done {v}", { v: fmtDT(parseT(t.done_at)) }) }) : null,
        taskTook(t) != null ? h("span", { class: "took", title: tr("Execution time: from start to done"), text: tr("took {v}", { v: dur(taskTook(t)) }) }) : null,
        t.commit ? h("span", { class: "tid", title: tr("Commit"), text: t.commit.slice(0, 7) }) : null));
  }

  function renderKanban(m) {
    if (view !== "tasks") return;
    const ts = tasksOf(m);
    const types = [...new Set(ts.map((t) => t.type).filter(Boolean))].sort();
    const sel = $("type-filter");
    if (typeFilter && !types.includes(typeFilter)) typeFilter = "";
    if (sel.dataset.types !== types.join(",")) {
      sel.dataset.types = types.join(",");
      fill(sel, h("option", { value: "", text: tr("All types") }), types.map((t) => h("option", { value: t, text: t })));
    }
    sel.value = typeFilter;
    sel.disabled = types.length < 2;
    const q = query.trim().toLowerCase();
    const filtering = Boolean(q || typeFilter);
    const match = (t) => (!typeFilter || t.type === typeFilter) && (!q || `${t.id} ${t.title}`.toLowerCase().includes(q));
    const shown = ts.filter(match);
    const note = $("filter-note");
    note.hidden = !filtering;
    if (filtering) fill(note, tr("{shown_n} of {v} shown. ", { shown_n: shown.length, v: plural(ts.length, "task") }),
      h("button", { type: "button", class: "link-btn", text: tr("Clear filter"), onclick: () => { query = ""; typeFilter = ""; $("task-search").value = ""; renderKanban(currentMilestone()); $("task-search").focus(); } }));
    const box = $("kanban");
    if (!m) {
      fill($("col-tabs"));
      fill(box, h("div", { class: "board-empty" }, tr("No milestone planned yet. Run "), cmd("/dev-kit:plan"), tr(" to create milestones and tasks.")));
      return;
    }
    const by = Object.fromEntries(STATUS.map((st) => [st.key, shown.filter((t) => t.status === st.key)]));
    by.done.sort((a, b) => (parseT(b.done_at) || 0) - (parseT(a.done_at) || 0));
    // To do: next up first, then ready, then waiting, so the cards that fit are the useful ones
    const nextId = data.next && data.next.task;
    const todoRank = (t) => (t.id === nextId ? 0 : waitingOn(t).length ? 2 : 1);
    by.todo.sort((a, b) => todoRank(a) - todoRank(b) || Number(a.id.slice(2)) - Number(b.id.slice(2)));
    const col = mobileCol || ["in_progress", "blocked", "todo", "done"].find((k) => by[k].length) || "todo";
    box.dataset.col = col;
    fill($("col-tabs"), STATUS.map((st) => h("button", { type: "button", class: "seg-btn", "aria-pressed": String(col === st.key),
      text: `${st.label} ${by[st.key].length}`, onclick: () => { mobileCol = st.key; renderKanban(currentMilestone()); } })));
    // every column has the same height; the cards that do not fit become "+N more", which opens the whole column
    fill(box, STATUS.map((st) => {
      const list = by[st.key];
      const all = () => openList(`${m.id} · ${st.label} (${list.length})`, h("div", { class: "modal-cards" }, list.map(taskCard)));
      return h("section", { class: "col", "data-st": st.key, "aria-label": `${st.label}, ${plural(list.length, "task")}` },
        h("div", { class: "col-head" }, h("span", { class: `swatch st-${st.key}`, "aria-hidden": "true" }), st.label,
          h("span", { class: "count", text: String(list.length) })),
        h("div", { class: `col-cards${filtering ? " scroll" : ""}`, "data-clamp": filtering ? null : "cards" },
          list.length ? list.map(taskCard) : h("div", { class: "col-empty", text: filtering ? tr("No match") : st.key === "blocked" ? tr("Nothing blocked") : tr("Empty") })),
        h("button", { type: "button", class: "col-more", id: `more-${st.key}`, hidden: true, onclick: all }));
    }));
    clampSoon();
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
      fill(box, h("div", { class: "chart-empty", text: tr("The burndown starts when the first task of this milestone starts.") }));
      fill($("burndown-table"));
      return;
    }
    const W = Math.max(300, Math.round(box.clientWidth || 640)), H = 240, L = 36, R = 16, T = 14, B = 28;
    const x = (t) => L + ((t - ser.t0) / (ser.t1 - ser.t0)) * (W - L - R);
    const y = (v) => T + (1 - v / Math.max(1, ser.total)) * (H - T - B);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": tr("Burndown for {id}: {v} of {total} tasks remaining", { id: m.id, v: ser.pts.at(-1)[1], total: ser.total }) });
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
    svg.append(s("text", { class: "label-strong", x: x(last[0]) - 8, y: y(last[1]) - 10, "text-anchor": "end", text: tr("{v} left", { v: last[1] }) }));
    const cross = s("line", { class: "crosshair", y1: T, y2: y(0), visibility: "hidden" });
    const dot = s("circle", { class: "marker", r: 4, visibility: "hidden" });
    svg.append(cross, dot);
    const hit = s("rect", { x: L, y: T, width: W - L - R, height: H - T - B, fill: "transparent", tabindex: "0",
      "aria-label": tr("Burndown chart; use the table view for every value") });
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
    const rows = [[ser.t0, ser.total, tr("milestone start")]];
    let rem = ser.total;
    for (const d of ser.dones) { rem -= 1; rows.push([d, rem, tr("task done")]); }
    fill($("burndown-table"), h("table", {}, h("thead", {}, h("tr", {}, h("th", { text: tr("When") }), h("th", { text: tr("Remaining") }), h("th", { text: tr("Event") }))),
      h("tbody", {}, rows.map(([t, v, e]) => h("tr", {}, h("td", { text: fmtDT(t) }), h("td", { text: String(v) }), h("td", { text: e }))))));
  }

  // ------------------------------------------------------------------ velocity: tasks done per milestone, then its hours and cost
  /** Hours a milestone took: elapsed (first task start -> gate, or now while open) and working (the union of the time
   * its tasks were in progress, so parallel tasks do not count twice). null before any task started. */
  function workSpan(ts) {
    const now = Date.now();
    const iv = ts.filter((t) => Number.isFinite(parseT(t.started_at))).map((t) => {
      const s0 = parseT(t.started_at), e0 = parseT(t.done_at);
      return [s0, Number.isFinite(e0) ? Math.max(s0, e0) : t.status === "in_progress" ? now : s0];
    }).sort((a, b) => a[0] - b[0]);
    if (!iv.length) return null;
    let work = 0, [cs, ce] = iv[0];
    for (const [s0, e0] of iv.slice(1)) { if (s0 <= ce) ce = Math.max(ce, e0); else { work += ce - cs; cs = s0; ce = e0; } }
    work += ce - cs;
    return { start: iv[0][0], work, now };
  }
  function msTiming(m) {
    const span = workSpan(tasksOf(m));
    if (!span) return null;
    const { now, work } = span;
    const closed = m.gate === "passed" || m.gate === "skipped";
    const dones = tasksOf(m).map((t) => parseT(t.done_at)).filter(Number.isFinite);
    const end = closed && Number.isFinite(parseT(m.passed_at)) ? parseT(m.passed_at) : closed && dones.length ? Math.max(...dones) : now;
    return { elapsed: Math.max(0, end - span.start) / 36e5, work: work / 36e5, open: !closed };
  }
  /** Execution time of a closed milestone: from its first task's start to its gate (null while open or never started). */
  function msTook(m) {
    const tm = m && isClosed(m) ? msTiming(m) : null;
    return tm ? { text: fmtTook(tm.elapsed), title: tr("Execution time: {v} from the first task to the gate, {v2} working", { v: fmtTook(tm.elapsed), v2: fmtH(tm.work) }) } : null;
  }
  /** Execution time of a released release: from the first task of its milestones to the release (null before). */
  function relTook(r) {
    if (!r || r.status !== "released") return null;
    const span = workSpan(relMs(r).flatMap(tasksOf).filter((t) => t.status !== "dropped"));
    if (!span) return null;
    const ev = ((data.release_history || {})[r.id] || []).filter((x) => x.event === "released").map((x) => x.at)
      .concat((data.releases || []).filter((v) => v.release === r.id).map((v) => v.at)).map(parseT).filter(Number.isFinite);
    const gates = relMs(r).map((m) => parseT(m.passed_at)).filter(Number.isFinite);
    const end = ev.length ? Math.max(...ev) : gates.length ? Math.max(...gates) : null;
    if (end == null) return null;
    const h0 = Math.max(0, end - span.start) / 36e5;
    return { text: fmtTook(h0), title: tr("Execution time: {v} from the first task to the release, {v2} working", { v: fmtTook(h0), v2: fmtH(span.work / 36e5) }) };
  }
  const fmtTook = (x) => (x != null && x >= 48 ? tr("{v} d", { v: (x / 24).toFixed(1) }) : fmtH(x));  // long spans read better in days
  const fmtH = (x) => (x == null ? "—" : x < 1 ? `${Math.max(1, Math.round(x * 60))} min` : x < 100 ? `${x.toFixed(1)} h` : `${Math.round(x)} h`);
  /** Cost when it was measured, otherwise tokens when they were, otherwise null (dev_cost.py writes milestones.json). */
  function msSpend(id) {
    const c = (data.milestone_costs || {})[id];
    if (!c) return null;
    if (Number(c.usd) > 0) return { text: tr("US$ {v}{v2}", { v: Number(c.usd).toFixed(2), v2: c.usd_complete === false ? "+" : "" }), title: c.usd_complete === false ? tr("Some requests had no price: at least this much") : tr("Estimated cost, API-equivalent") };
    if (Number(c.tokens) > 0) return { text: tr("{v} tok", { v: compact(Number(c.tokens)) }), title: c.partial ? tr("Tokens reported by the skills (no transcripts): partial") : tr("Tokens used (no price for the model)") };
    return null;
  }
  function renderVelocity(cur) {
    const box = $("velocity");
    const rows = data.milestones.map((m) => {
      const ts = tasksOf(m);
      return { id: m.id, title: m.title, done: ts.filter((t) => t.status === "done").length, total: ts.length, time: msTiming(m), spend: msSpend(m.id) };
    }).filter((r) => r.total);
    if (!rows.length) {
      fill(box, h("div", { class: "chart-empty", text: tr("Velocity appears once milestones have tasks.") }));
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
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": tr("Tasks done per milestone: ") + rows.map((r) => `${r.id} ${r.done}`).join(", ") });
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
        "aria-label": tr("{id}: {done} of {total} tasks done", { id: r.id, done: r.done, total: r.total }) });
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
    fill($("velocity-table"), h("table", {}, h("thead", {}, h("tr", {}, [tr("Milestone"), tr("Done"), tr("Total"), tr("Elapsed"), tr("Working"), tr("Cost or tokens")].map((x) => h("th", { text: x })))),
      h("tbody", {}, rows.slice().reverse().map((r) => h("tr", {}, h("td", { text: `${r.id} ${r.title || ""}` }), h("td", { text: String(r.done) }), h("td", { text: String(r.total) }),
        h("td", { text: r.time ? fmtH(r.time.elapsed) + (r.time.open ? tr(" so far") : "") : "—" }), h("td", { text: r.time ? fmtH(r.time.work) : "—" }),
        h("td", { text: r.spend ? r.spend.text : tr("not measured") }))))));
  }
  function velTip(r) {
    const out = [[`${r.done}`, tr("done of {total}", { total: r.total }), "s1"]];
    if (r.time) out.push([fmtH(r.time.elapsed), r.time.open ? tr("elapsed so far") : "elapsed", "s1"], [fmtH(r.time.work), "working", "s2"]);
    if (r.spend) out.push([r.spend.text, r.spend.text.endsWith("tok") ? "tokens" : "cost"]);
    return out;
  }
  /** Hours per milestone, same milestones and order as the bars above: one axis (hours), two lines - elapsed (solid)
   * and working (dashed) - with markers, direct labels on the last point, and the cost or tokens under each label. */
  function renderHours(rows, W) {
    const box = $("velocity-hours");
    const pts = rows.filter((r) => r.time);
    if (!pts.length) { fill(box, h("div", { class: "chart-empty", text: tr("Hours appear once a task of a milestone has started.") })); return; }
    const H = 220, L = 44, R = 64, T = 16, B = 44;
    const max = Math.max(0.5, ...pts.map((r) => Math.max(r.time.elapsed, r.time.work)));
    const nice = (v) => { const p = 10 ** Math.floor(Math.log10(v)); return [1, 2, 2.5, 5, 10].map((k) => k * p).find((k) => k >= v); };
    const step = nice(max / 4), top = step * Math.ceil(max / step);
    const y = (v) => T + (1 - v / top) * (H - T - B);
    const band = (W - L - R) / rows.length;
    const cx = (i) => L + band * i + band / 2;
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": tr("Hours per milestone: ") + pts.map((r) => tr("{id} elapsed {v}, working {v2}", { id: r.id, v: fmtH(r.time.elapsed), v2: fmtH(r.time.work) })).join("; ") });
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
    svg.append(s("text", { class: "label-strong", x: cx(lastI) + 9, y: ye + 4 + gap[0], text: tr("elapsed") }),
      s("text", { class: "label-strong", x: cx(lastI) + 9, y: yw + 4 + gap[1], text: tr("working") }));
    rows.forEach((r, i) => {
      svg.append(s("text", { x: cx(i), y: H - 24, "text-anchor": "middle", text: r.id }));
      if (r.spend) svg.append(s("text", { class: "spend", x: cx(i), y: H - 8, "text-anchor": "middle", text: r.spend.text }));
      const hit = s("rect", { class: "hit", x: cx(i) - band / 2 + 2, y: T, width: band - 4, height: H - T - B, tabindex: "0",
        "aria-label": `${r.id}: ${r.time ? tr("elapsed {v}, working {v2}", { v: fmtH(r.time.elapsed), v2: fmtH(r.time.work) }) : tr("not started")}${r.spend ? `, ${r.spend.text}` : ""}` });
      const tipFn = (evt) => showTip(evt, `${r.id} · ${r.title || ""}`, velTip(r));
      hit.addEventListener("pointermove", tipFn); hit.addEventListener("focus", tipFn);
      hit.addEventListener("pointerleave", hideTip); hit.addEventListener("blur", hideTip);
      svg.append(hit);
    });
    fill(box, svg);
  }

  // ------------------------------------------------------------------ needs you, activity
  /** A small button naming a phase: it opens that phase. */
  const phaseTag = (p) => h("button", { type: "button", class: "phase-tag", title: tr("Open {v}", { v: PHASE_NAME[p] }), text: PHASE_NAME[p], onclick: () => setPhase(p) });
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
    const b = data.backlog || {};
    const hot = (b.hotfix_open || []).filter((id) => !data.tasks[id] || !["done", "dropped"].includes(data.tasks[id].status));
    const warns = b.warnings || [];
    // milestones past the QA limit with no blocked card to show it (the round failed on scores alone)
    const stuck = data.milestones.filter((m) => qaState(m).exhausted);
    const heldByQa = (t) => isFix(t) && /rounds_exhausted/.test(t.blocked_reason || "");
    const blocked = Object.entries(data.tasks).filter(([, t]) => t.status === "blocked" && !heldByQa(t) && t.lane !== "hotfix");
    const approvals = actionsOn() ? inbox().approvals : [];
    const waitingRel = relPlan().filter((r) => r.status === "awaiting_approval");
    const allNeeds = b.needs || [];
    const cneeds = allNeeds.filter((x) => x.kind === "checkpoint");
    const dneeds = allNeeds.filter((x) => x.kind === "debt_over_cap");
    const lneeds = allNeeds.filter((x) => x.kind === "lesson");
    const hneeds = allNeeds.filter((x) => x.kind === "prod_health");
    const qneeds = allNeeds.filter((x) => !["checkpoint", "debt_over_cap", "lesson", "prod_health"].includes(x.kind));
    const n = blocked.length + data.questions.length + hot.length + stuck.length + approvals.length + waitingRel.length + allNeeds.length;
    // which phase each item belongs to: the tabs show the count, the rows a tag that opens the phase
    const cpPrd = cneeds.filter((x) => x.target === "prd").length;
    needsBy = { conception: cpPrd, planning: qneeds.length + cneeds.length - cpPrd, construction: blocked.length + hot.length + stuck.length + dneeds.length, stable: hneeds.length, releases: waitingRel.length };
    if (approvals.length) needsBy[data.phase] = (needsBy[data.phase] || 0) + approvals.length;
    data.questions.forEach((q) => { needsBy[questionPhase(q)] += 1; });
    // the strip exists only while something needs the user; warnings alone ride along but do not open it
    const nb = $("needs-btn");
    const before = needsN;
    needsN = n;
    $("needs-n").textContent = String(n);
    nb.classList.toggle("calm", !n);
    nb.classList.toggle("alert", n > 0);
    $("needs-sr").textContent = n ? `: ${plural(n, "item")}` : tr(": nothing now");
    $("needs-count").textContent = n ? plural(n, "item") : "";
    // a new item makes the button ring once (the favicon and the title of the tab change too)
    if (n > before && !firstRender) { nb.classList.remove("ping"); void nb.offsetWidth; nb.classList.add("ping"); }
    if (!n) { fill($("impediments"), h("div", { class: "empty good needs-empty" }, h("strong", { text: tr("Nothing needs you now.") }), h("span", { text: tr("Questions, confirmations, approvals and blocked work show up here.") }))); return; }
    fill($("impediments"),
      approvals.length ? listBlock(tr("Claude Code asks permission"), approvals.map(approvalRow), "") : null,
      hneeds.length ? listBlock(tr("Production is failing its health check"), hneeds.map(healthRow), "", false, "stable") : null,
      waitingRel.length ? listBlock(tr("Releases waiting for your approval"), waitingRel.map((r) => h("li", {}, h("span", { class: "id", text: r.id }),
        h("span", { text: tr("{title} · {v} closed", { title: r.title, v: plural(r.closed.length, "milestone") }) }),
        h("button", { type: "button", class: "link-btn", text: tr("Open"), onclick: () => openRelease(r.id) }),
        r.review_doc ? h("span", { class: "sub" }, docLink(r.review_doc, tr("Open the release review"))) : null,
        releaseDecision(r))), "", false, "releases") : null,
      stuck.length ? listBlock(tr("QA rounds used up"), stuck.map(qaDecisionRow), "", false, "construction") : null,
      cneeds.length ? listBlock(tr("Confirm before building"), cneeds.map(checkpointRow), "", false, cpPrd ? "conception" : "planning") : null,
      dneeds.length ? listBlock(tr("Deferred debt above the cap"), dneeds.map(debtRow), "", false, "construction") : null,
      lneeds.length ? listBlock(tr("Proposed lessons"), lneeds.map(lessonRow), "", false, "construction") : null,
      qneeds.length ? listBlock(tr("Issue queue"), qneeds.map(queueNeedRow), "", false, "planning") : null,
      hot.length ? listBlock(tr("Open hotfixes"), hot.map((id) => hotfixRow(id, b)), "", false, "construction") : null,
      blocked.length ? listBlock(tr("Blocked tasks"), blocked.map(([id, t]) => blockedRow(id, t)), "", false, "construction") : null,
      data.questions.length ? listBlock(tr("Open questions"), data.questions.map((q) => h("li", {}, hasDoc("open-questions.md") ? docLink("open-questions.md", q.id, q.id, "id") : h("span", { class: "id", text: q.id }), h("span", {}, linkify(q.question)),
        h("span", { class: "q-tags" }, h("span", { class: "chip", text: q.by || "?" }), phaseTag(questionPhase(q))), q.assumption ? h("span", { class: "sub", text: tr("Assumed meanwhile: {assumption}", { assumption: q.assumption }) }) : null,
        actionsOn() ? answerBox(q) : null)), "") : null,
      warns.length ? listBlock(tr("Warnings"), warns.map((w) => h("li", {}, h("span", { class: "id", text: "!" }), h("span", { text: w }))), "") : null,
      actionsOn() && data.questions.length ? h("p", { class: "needs-hint" }, tr("Answer here: Claude Code records the answer and continues what was waiting on it.")) : null,
      data.questions.length || blocked.length ? h("p", { class: "needs-hint" }, actionsOn() ? tr("Or go through all of them with ") : tr("Answer in Claude Code with "), cmd("/dev-kit:interview --gaps")) : null);
  }
  /** A row of decision buttons that queue one request; the recommended one first and highlighted, a note field when asked. */
  const decisionDrafts = {};
  function decisionBox(key, label, action, base, options, sentText) {
    const sent = inbox().open.find((r) => r.action === action && Object.entries(base).every(([k, v]) => r.args && r.args[k] === v));
    if (sent) return h("div", { class: "sub answer-sent", text: tr("Sent ({id}): {v}. Claude Code applies it.", { id: sent.id, v: sentText(sent.args) }) });
    const ta = h("textarea", { maxlength: "2000", rows: "2", class: "answer-input", "aria-label": tr("{label}: note", { label }), placeholder: tr("Note or reason (needed where marked *)") });
    ta.value = decisionDrafts[key] || "";
    ta.addEventListener("input", () => { decisionDrafts[key] = ta.value; });
    const send = async (o, el) => {
      const note = ta.value.trim();
      if (o.needsNote && !note) { ta.focus(); toast(tr("Write the reason first."), true); return; }
      el.disabled = true;
      try { await queue(action, { ...base, ...o.args, ...(note ? { note } : {}) }); delete decisionDrafts[key]; } catch (e) { el.disabled = false; }
    };
    const opts = options.slice().sort((a, b) => Boolean(b.recommended) - Boolean(a.recommended));
    return h("div", { class: "sub answer", role: "group", "aria-label": label },
      opts.map((o) => h("button", { type: "button", class: `btn btn-sm${o.recommended ? " btn-primary" : o.danger ? " btn-danger" : ""}`, title: o.title || null,
        onclick: (e) => send(o, e.currentTarget) }, o.text + (o.needsNote ? " *" : ""), o.recommended ? h("span", { class: "rec", text: tr("recommended") }) : null)),
      options.some((o) => o.note !== false) ? h("span", { class: "answer-free" }, ta) : null);
  }
  /** Needs you › QA rounds used up (conventions §7): keep fixing (+1 round), accept with an ADR (a justification), or replan. */
  function qaDecisionRow(m) {
    const q = qaState(m);
    const head = [h("span", { class: "id", text: m.id }),
      h("span", { text: tr("{v} fix rounds used of {max} ({v2}).", { v: Math.max(0, q.qa.runs - 1), max: q.max, v2: qaReason(q.qa, m) || tr("see the QA report") }) })];
    if (!actionsOn()) return h("li", {}, ...head, h("span", { class: "sub" }, tr("Decide in Claude Code with "), cmd(`/dev-kit:qa ${m.id}`)));
    // a fix that did not hold twice points to the plan, not to one more round
    const replan = q.fixBlocked.some((t) => (t.blocked_count || 0) >= 2);
    return h("li", {}, ...head, decisionBox(`qa:${m.id}`, tr("QA of {id}", { id: m.id }), "qa_decision", { milestone: m.id }, [
      { text: tr("Continue fixing (+1 round)"), args: { decision: "continue", rounds: 1 }, recommended: !replan, title: tr("One more fix round, then QA again") },
      { text: tr("Accept with an ADR"), args: { decision: "accept" }, needsNote: true, title: tr("The milestone closes as it is; an ADR records why") },
      { text: tr("Replan"), args: { decision: "replan" }, recommended: replan, title: tr("Change the plan of this milestone") }],
    (a) => ({ continue: tr("continue fixing"), accept: tr("accept with an ADR"), replan: "replan" })[a.decision]));
  }
  /** Needs you › a blocked task: the question it waits on, answered right here, or unblock / skip / drop. */
  function blockedRow(id, t) {
    const q = data.questions.find((x) => x.task === id);
    const head = h("button", { type: "button", class: "row-btn", "data-tid": id, "aria-haspopup": "dialog", onclick: () => openTask(id) },
      h("span", { class: "id", text: id }), h("span", { text: t.title }), h("span", { class: "chip", text: t.milestone }),
      h("span", { class: "sub bad", text: t.blocked_reason || tr("No reason recorded") }));
    if (!actionsOn()) return h("li", { class: "has-btn" }, head);
    if (q) return h("li", { class: "has-btn" }, head, h("span", { class: "sub" }, tr("Waiting on {id}: ", { id: q.id }), linkify(q.question)), answerBox(q));
    return h("li", { class: "has-btn" }, head, decisionBox(`task:${id}`, tr("Blocked {id}", { id }), "task_decision", { task: id }, [
      { text: tr("Unblock"), args: { decision: "unblock" }, recommended: true, title: tr("Back to To do, with your note for the implementer") },
      { text: tr("Skip to the next milestone"), args: { decision: "skip" }, title: tr("Move it to the next open milestone") },
      { text: tr("Drop"), args: { decision: "drop" }, needsNote: true, danger: true, title: tr("Remove it from the plan, with the reason") }],
    (a) => ({ unblock: "unblock", skip: tr("skip to the next milestone"), drop: "drop" })[a.decision]));
  }
  /** Needs you › an open hotfix: where it is, and run it now or drop it. */
  function hotfixRow(id, b) {
    const t = data.tasks[id] || {};
    const head = [issueId(id), h("span", { text: t.title || ((b.issues || {})[id] || {}).title || "" }), h("span", { class: "chip lane-hotfix", text: tr("hotfix") }),
      t.status ? h("span", { class: "chip", text: stLabel(t.status) }) : null];
    if (!actionsOn() || !data.tasks[id]) return h("li", {}, ...head);
    return h("li", {}, ...head, decisionBox(`hot:${id}`, tr("Hotfix {id}", { id }), "task_decision", { task: id }, [
      { text: tr("Run"), args: { decision: "run" }, recommended: true, title: tr("Build {id} now", { id }), note: false },
      { text: tr("Drop"), args: { decision: "drop" }, needsNote: true, danger: true, title: tr("Drop the hotfix, with the reason") }],
    (a) => (a.decision === "run" ? "run" : "drop")));
  }
  /** Needs you › Confirm PRD / Confirm plan (conventions §19): the document opens formatted in the side drawer; Confirm,
   * or ask for changes with what must change (the skill revises, a new review and a new checkpoint follow). */
  const adjustDrafts = {};
  function checkpointRow(x) {
    const doc = hasDoc(x.doc) ? docLink(x.doc, tr("Open {doc}", { doc: x.doc })) : h("span", { class: "sub", text: x.doc });
    const head = [h("span", { class: "id", text: x.target === "prd" ? tr("PRD") : tr("Plan") }),
      h("span", { text: tr("{title}{v}: the review passed; nothing {v2} until you confirm.", { title: x.title, v: x.round > 1 ? tr(" · round {round}", { round: x.round }) : "", v2: x.target === "prd" ? tr("after the PRD") : tr("new is built") }) }),
      h("span", { class: "sub" }, doc)];
    const summary = x.summary ? h("div", { class: "sub cp-summary" }, linkify(x.summary)) : null;
    if (!actionsOn()) return h("li", {}, ...head, summary, h("span", { class: "sub" }, tr("Confirm in Claude Code with "), cmd(`/dev-kit:review ${x.target}`)));
    const sent = inbox().open.find((r) => r.action === "checkpoint" && r.args && r.args.target === x.target);
    if (sent) return h("li", {}, ...head, summary, h("div", { class: "sub answer-sent", text: tr("Sent ({id}): {decision}. Claude Code records it.", { id: sent.id, decision: sent.args.decision }) }));
    const ta = h("textarea", { maxlength: "4000", rows: "3", class: "answer-input", "aria-label": tr("What must change in the {target}", { target: x.target }), placeholder: tr("What must change (Claude revises it and asks again)") });
    ta.value = adjustDrafts[x.target] || "";
    ta.addEventListener("input", () => { adjustDrafts[x.target] = ta.value; });
    const send = async (args, el) => { el.disabled = true; try { await queue("checkpoint", { target: x.target, ...args }); delete adjustDrafts[x.target]; } catch (e) { el.disabled = false; } };
    return h("li", {}, ...head, summary, h("div", { class: "sub answer", role: "group", "aria-label": x.title },
      h("button", { type: "button", class: "btn btn-sm btn-primary", text: tr("Confirm"), onclick: (e) => send({ decision: "confirm" }, e.currentTarget) }),
      h("span", { class: "answer-free" }, ta, h("button", { type: "button", class: "btn btn-sm", text: tr("Ask for changes"),
        onclick: (e) => { const v = ta.value.trim(); if (v) send({ decision: "adjust", feedback: v }, e.currentTarget); else { ta.focus(); toast(tr("Write what must change first."), true); } } }))));
  }
  /** Needs you › deferred debt above the cap (conventions §7): promote to issues, accept with an ADR, or the next cool-down. */
  function debtRow(x) {
    const head = [h("span", { class: "id", text: "!" }), h("span", { text: tr("{total} deferred findings open (cap {cap_total}) · {medium} medium (cap {cap_medium}).", { total: x.total, cap_total: x.cap_total, medium: x.medium, cap_medium: x.cap_medium }) })];
    if (!actionsOn()) return h("li", {}, ...head, h("span", { class: "sub" }, tr("Decide in Claude Code with "), cmd("/dev-kit:backlog")));
    const sent = inbox().open.find((r) => r.action === "debt_decision");
    if (sent) return h("li", {}, ...head, h("div", { class: "sub answer-sent", text: tr("Sent ({id}): {decision}.", { id: sent.id, decision: sent.args.decision }) }));
    const send = (decision, what) => queue("debt_decision", { decision }).then(() => toast(what)).catch(() => {});
    return h("li", {}, ...head, h("span", { class: "q-tags" },
      h("button", { type: "button", class: "btn btn-sm", text: tr("Promote to issues"), title: tr("Choose which findings become standard issues"), onclick: () => send("promote", tr("Claude Code lists the findings to promote.")) }),
      h("button", { type: "button", class: "btn btn-sm", text: tr("Accept formally"), title: tr("An ADR lists the accepted findings"), onclick: () => send("accept", tr("Claude Code records the ADR.")) }),
      h("button", { type: "button", class: "btn btn-sm", text: tr("Use the next cool-down"), title: tr("Cool-down is turned on for the next milestone with these items"), onclick: () => send("cooldown", tr("Cool-down turned on for the next milestone.")) })));
  }
  /** Needs you › a proposed lesson of method for one agent (conventions §13), with the evidence that raised it: approve
   * (the text can be edited first) or dismiss. An approved lesson goes into every prompt of that agent. */
  const lessonDrafts = {};
  function lessonRow(x) {
    const key = `${x.agent}:${x.signal}`;
    const head = [h("span", { class: "id", text: x.agent }), h("span", { text: x.text }), h("span", { class: "sub", text: tr("Why: {evidence}", { evidence: x.evidence }) })];
    if (!actionsOn()) return h("li", {}, ...head, h("span", { class: "sub" }, tr("Decide in Claude Code with "), cmd("/dev-kit:feedback")));
    const sent = inbox().open.find((r) => r.action === "lesson_decision" && r.args && `${r.args.agent}:${r.args.signal}` === key);
    if (sent) return h("li", {}, ...head, h("div", { class: "sub answer-sent", text: tr("Sent ({id}): {decision}.", { id: sent.id, decision: sent.args.decision }) }));
    const ta = h("textarea", { maxlength: "300", rows: "2", class: "answer-input", "aria-label": tr("Lesson for {agent}", { agent: x.agent }) });
    ta.value = lessonDrafts[key] !== undefined ? lessonDrafts[key] : x.text;
    ta.addEventListener("input", () => { lessonDrafts[key] = ta.value; });
    const send = (args, what) => queue("lesson_decision", { agent: x.agent, signal: x.signal, ...args }).then(() => { delete lessonDrafts[key]; toast(what); }).catch(() => {});
    return h("li", {}, ...head, h("div", { class: "sub answer", role: "group", "aria-label": tr("Lesson for {agent}", { agent: x.agent }) },
      h("span", { class: "answer-free" }, ta,
        h("button", { type: "button", class: "btn btn-sm btn-primary", text: tr("Approve"), onclick: () => { const v = ta.value.trim(); if (v) send({ decision: "approve", text: v }, tr("Claude Code adds the lesson.")); else ta.focus(); } }),
        h("button", { type: "button", class: "btn btn-sm", text: tr("Dismiss"), onclick: () => send({ decision: "dismiss" }, tr("Suggestion dismissed.")) }))));
  }
  /** Needs you › the issue queue (conventions §15): above the limit, or an issue waiting too long. Every action is a
   * plan draft the user sends; nothing changes the plan by itself. */
  /** A failing production health check: its expedite issue, how many checks failed, and the way to a hotfix. */
  function healthRow(x) {
    const fix = x.tasks && x.tasks.length ? `/dev-kit:implement ${x.tasks[x.tasks.length - 1]}` : `/dev-kit:issue ${x.issue}`;
    return h("li", {}, h("span", { class: "id", text: x.issue }),
      h("span", { text: tr("{v} · last: {detail}", { v: plural(x.failures, "failed check"), detail: x.detail || "?" }) }),
      h("span", { class: "chip lane-hotfix", text: tr("expedite") }),
      h("span", { class: "sub", text: x.target || "" }),
      actionsOn() ? runBtn(fix, true) : cmd(fix));
  }
  function queueNeedRow(x) {
    const acts = actionsOn();
    if (x.kind === "queue_over_limit") {
      const load = () => {
        draft = { ops: x.draft.ops.slice(), base: data.updated_at, serverErrors: [], buffer: false, frozen: false };
        planMode = "tasks";
        setPhase("planning");
        toast(tr("Draft of {milestone} — Issues with {v}: review it, then send it.", { milestone: x.milestone, v: plural(x.issues.length, "issue") }));
      };
      return h("li", {}, h("span", { class: "id", text: "!" }),
        h("span", { text: tr("Queue above the limit: {v} waiting (limit {limit}).", { v: plural(x.count, "issue"), limit: x.limit }) }),
        acts && x.issues.length ? h("button", { type: "button", class: "btn btn-sm", text: tr("Plan the queue milestone"), title: tr("Draft {milestone} — Issues with the oldest and most severe issues; nothing changes until you send it", { milestone: x.milestone }), onclick: load }) : null);
    }
    const nextOpen = (data.milestones || []).find((m) => m.gate === "pending" && !m.frozen_at);
    const send = (ops, what) => queue("plan_draft", { ops, base: data.updated_at }).then(() => toast(what)).catch(() => {});
    return h("li", {}, issueId(x.issue),
      h("span", { text: tr("{v} · waiting for {v2}", { v: (issueOf(x.issue) || {}).title || "", v2: plural(x.milestones, "closed milestone") }) }),
      acts ? h("span", { class: "q-tags" },
        nextOpen ? h("button", { type: "button", class: "btn btn-sm", text: tr("Schedule in {id}", { id: nextOpen.id }), onclick: () => send([{ op: "schedule_issue", issue: x.issue, milestone: nextOpen.id, force: true }], tr("{issue} → {id} queued.", { issue: x.issue, id: nextOpen.id })) }) : null,
        h("button", { type: "button", class: "btn btn-sm", text: tr("Park"), title: tr("Parked issues are never pulled into a milestone until you schedule them"), onclick: () => send([{ op: "set_issue_status", issue: x.issue, status: "parked" }], tr("{issue} parked.", { issue: x.issue })) }),
        h("button", { type: "button", class: "btn btn-sm", text: tr("Won't fix"), onclick: () => send([{ op: "set_issue_status", issue: x.issue, status: "wontfix" }], tr("{issue} closed as won't fix.", { issue: x.issue })) })) : null);
  }
  /** Opens "Needs you" (the drawer of the red button in the top bar). */
  function goNeeds() { openDrawer(ndlg); }

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
    const max = m.max_fix_rounds || (data.lifecycle || {}).max_fix_rounds || 3;
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
      parts.push(mins.size === 1 ? tr("{v} below {min}", { v: below.map((d) => `${d.dimension} ${d.score}`).join(", "), min: below[0].min })
        : below.map((d) => `${d.dimension} ${d.score} < ${d.min}`).join(", "));
    }
    if (last.blockers) parts.push(plural(last.blockers, "blocking finding"));
    if (last.overall != null && last.cutoff != null && last.overall < last.cutoff) parts.push(tr("overall {overall} below {cutoff}", { overall: last.overall, cutoff: last.cutoff }));
    return parts.join("; ");
  }
  /** The QA loop as a trail: one pill per round, the fixes in between, and the round running or due now. */
  function qaTrail(m, x) {
    const hist = x.qa.history && x.qa.history.length ? x.qa.history
      : Array.from({ length: x.qa.runs }, (_, i) => ({ n: i + 1, value: i === x.qa.runs - 1 ? m.gate : "pending", score: i === x.qa.runs - 1 ? m.score : null }));
    const pills = [];
    hist.forEach((r, i) => {
      const ok = r.value === "passed" || r.value === "skipped";
      // a failed round says why: its reason, or the blockers of the last round; the score only when it is the reason
      const last = i === hist.length - 1 && x.qa.last;
      const why = ok ? null : r.reason || (last && last.blockers ? plural(last.blockers, "blocker") : null)
        || (r.score != null ? `${r.score}${last && last.cutoff != null ? ` < ${last.cutoff}` : ""}` : null);
      pills.push({ cls: ok ? "ok" : "bad", text: tr("Round {n}{v}", { n: r.n, v: ok ? ` ✓${r.score != null ? ` ${r.score}` : ""}` : ` ✕${why ? ` · ${why}` : ""}` }),
        title: tr("Round {n}: {v}{v2}{v3}", { n: r.n, v: ok ? tr("passed") : tr("failed"), v2: r.score != null ? tr(" with {score}", { score: r.score }) : "", v3: i === hist.length - 1 && !ok ? ` · ${qaReason(x.qa, m)}` : "" }) });
    });
    if (x.fixes.length) {
      const done = x.fixes.length - x.fixOpen.length;
      pills.push({ cls: x.fixBlocked.length ? "bad" : x.fixOpen.length ? "run" : "ok",
        text: `${done}/${plural(x.fixes.length, "fix", "fixes")}${x.fixBlocked.length ? tr(" · {fixBlocked_n} blocked", { fixBlocked_n: x.fixBlocked.length }) : x.fixOpen.length ? "" : " ✓"}`,
        title: x.fixBlocked.length ? tr("{fixBlocked_n} fix task(s) blocked: the agreed limit was reached", { fixBlocked_n: x.fixBlocked.length }) : x.fixOpen.length ? tr("{fixOpen_n} fix task(s) still open", { fixOpen_n: x.fixOpen.length }) : tr("All fix tasks done") });
    }
    if (!x.passed && x.ts.length && !x.buildOpen.length) {
      if (x.running) pills.push({ cls: "run", text: tr("Round {round} ●", { round: x.round }), title: tr("Round {round} is running now", { round: x.round }) });
      else if (x.exhausted) pills.push({ cls: "bad", text: tr("decide"), title: tr("The agreed limit was reached: keep fixing, accept with an ADR, or replan") });
      else if (!x.fixOpen.length) pills.push({ cls: "next", text: tr("Round {round} next", { round: x.round }), title: tr("Round {round} has not started yet", { round: x.round }) });
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
    const deployOn = ["per_milestone", "per_milestone_flagged"].includes(lc.deploy_when);
    const dep = m.deploy;
    const st = [];
    st.push({ key: "plan", name: tr("Plan"), state: ts.length ? "done" : "current",
      note: ts.length ? plural(ts.length, "task") : tr("Run"), cmd: ts.length ? null : "/dev-kit:plan", tasks: [] });
    st.push({ key: "build", name: tr("Build"), tasks: build,
      state: !ts.length ? "upcoming" : buildOpen.length ? "current" : "done",
      note: build.length ? tr("{v}/{build_n} done", { v: build.length - buildOpen.length, build_n: build.length }) : tr("No tasks") });
    // QA and its fixes are one loop: audit → fix → audit again, until the gate passes
    const qaCmd = `/dev-kit:qa ${m.id}`;
    let qaNote, qaCmdShown = null, qaStateName;
    if (passed) { qaStateName = "done"; qaNote = m.gate === "skipped" ? tr("Skipped") : tr("Passed{v}{v2}", { v: m.score != null ? ` · ${m.score}` : "", v2: x.qa.runs > 1 ? tr(" in round {runs}", { runs: x.qa.runs }) : "" }); }
    else if (!ts.length || buildOpen.length) { qaStateName = "upcoming"; qaNote = tr("After the build"); }
    else if (x.running) {
      qaStateName = "current";
      const r = x.qa.round;
      qaNote = tr("Round {round} running", { round: x.round }) + (r && r.spawned ? tr(" · {done_n} of {spawned} auditors done", { done_n: r.done.length, spawned: r.spawned }) : "");
      if (runningRun(qaCmd)) qaCmdShown = qaCmd;  // shown disabled, with how long it has run
    } else if (x.exhausted) {
      qaStateName = "failed";
      qaNote = x.qa.runs > x.max ? tr("{v} fix rounds used of {max}: needs your decision", { v: x.qa.runs - 1, max: x.max })
        : tr("{v} did not hold twice: needs your decision", { v: plural(x.fixBlocked.length, "fix", "fixes") });
    } else if (x.fixActive.length) { qaStateName = "current"; qaNote = tr("Fixing round {runs}: {v}/{fixes_n} done · {v2}", { runs: x.qa.runs, v: x.fixes.length - x.fixOpen.length, fixes_n: x.fixes.length, v2: qaReason(x.qa, m) }); }
    else if (runningRun(qaCmd)) { qaStateName = "current"; qaNote = tr("Round {round}:", { round: x.round }); qaCmdShown = qaCmd; }  // the ▶ shows it running, disabled
    else if (skillRuns().some((r) => r.skill === "autopilot")) { qaStateName = "current"; qaNote = tr("{v} done; autopilot runs QA round {round} next", { v: x.qa.runs ? tr("Fixes") : tr("Tasks"), round: x.round }); }
    else if (x.qa.runs) { qaStateName = "current"; qaNote = tr("Fixes done; round {round} not started. Run", { round: x.round }); qaCmdShown = qaCmd; }
    else { qaStateName = "current"; qaNote = tr("Tasks done; round 1 not started. Run"); qaCmdShown = qaCmd; }
    st.push({ key: "qa", name: "QA & fixes", tasks: x.fixes, agents: x.agents, state: qaStateName, note: qaNote, cmd: qaCmdShown,
      trail: qaTrail(m, x), decide: x.exhausted && !x.fixBlocked.length });
    st.push({ key: "smoke", name: tr("Smoke test"), tasks: [],
      state: !smokeOn ? "na" : m.preview ? "done" : "upcoming",
      note: !smokeOn ? tr("Local preview off") : m.preview ? (m.preview.pid != null ? tr("Preview running") : tr("Passed")) : passed ? tr("Not recorded") : tr("Runs inside QA") });
    const deploying = passed && runsAt("prod").length > 0;  // a deploy runs now (this milestone is past its gate)
    st.push({ key: "deploy", name: tr("Deploy"), tasks: [], running: deploying,
      state: deploying ? "current" : !deployOn ? "na" : dep && dep.status === "ok" ? "done" : dep ? "failed" : passed ? "current" : "upcoming",
      note: deploying ? tr("Running now") : !deployOn ? (lc.deploy_when === "on_release" ? tr("At release") : tr("Not per milestone"))
        : dep && dep.status === "ok" ? `${(dep.sha || "").slice(0, 7)}${dep.at && Number.isFinite(parseT(dep.at)) ? ` · ${fmtDate(parseT(dep.at))}` : ""}`
        : dep ? stLabel(dep.status) : passed ? tr("Waiting for") : tr("After the gate"),
      cmd: !deploying && deployOn && passed && !(dep && dep.status === "ok") ? "/dev-kit:deploy" : null });
    const closed = passed && (!deployOn || (dep && dep.status === "ok"));
    st.push({ key: "close", name: tr("Closed"), tasks: [], state: closed ? "done" : "upcoming",
      note: closed ? [m.passed_at && Number.isFinite(parseT(m.passed_at)) ? fmtDate(parseT(m.passed_at)) : tr("Milestone closed"),
        msTook(m) ? tr("took {v}", { v: msTook(m).text }) : null].filter(Boolean).join(" · ") : "" });
    // stages that do not apply are not drawn: no smoke without a local preview, no deploy unless it is per milestone;
    // the smoke test runs inside QA, so it is a line of the QA stage
    const smoke = st.find((y) => y.key === "smoke"), qa = st.find((y) => y.key === "qa");
    if (smoke.state !== "na") qa.sub = { name: tr("Smoke test"), state: smoke.state, note: smoke.note };
    const out = st.filter((y) => y.key !== "smoke" && y.state !== "na");
    // one stage is "where we are": the first current or failed one
    const here = out.find((y) => y.state === "current" || y.state === "failed");
    if (here) here.here = true;
    return out;
  }
  const STAGE_ICON = { done: "✓", current: "●", upcoming: "○", failed: "✕", na: "–" };
  function runChip(t) {
    return h("button", { type: "button", class: "run-chip", "data-tid": t.id, title: tr("{id} {title}. Open details", { id: t.id, title: t.title }), onclick: () => openTask(t.id) },
      h("span", { class: "tid", text: t.id }), h("span", { class: "run-title", text: t.title }), agentsOn(t.id).slice(0, 2).flatMap((a) => agentBits(a)));
  }
  /** The milestone as lane "3 · Milestones" of the diagram: pull issues → implement → QA → gate → smoke/deploy (or closed). */
  function msNodes(m) {
    const st = stagesOf(m);
    const by = Object.fromEntries(st.map((x) => [x.key, x]));
    const x = qaState(m);
    const b = (data.backlog || {}).buffer;
    const buf = b && b.milestone === m.id && b.capacity ? tr("buffer {used}/{capacity}", { used: b.used, capacity: b.capacity }) : null;
    const node = (s, extra) => (s ? { state: s.state === "upcoming" ? "todo" : s.state, here: Boolean(s.here), ...extra } : null);
    const building = (by.build ? by.build.tasks : []).filter((t) => t.status === "in_progress");
    const blocked = (by.build ? by.build.tasks : []).filter((t) => t.status === "blocked").length;
    const qaNode = by.qa;
    const gateFailed = qaNode && qaNode.state === "failed";
    const nodes = [
      node(by.plan, { key: "plan", label: tr("Pull issues"), sub: buf || (by.plan && by.plan.note) || "", about: tr("Queued issues fill the milestone's buffer before it is built"), stage: by.plan }),
      node(by.build, { key: "build", label: tr("Implement"), kind: "work", sub: by.build ? by.build.note : "", running: building.length > 0,
        agents: building.flatMap((t) => agentsOn(t.id)), need: blocked, needText: tr("{n} blocked", { n: blocked }), about: tr("Tests first, the full suite, one commit per task"), stage: by.build }),
      qaNode ? { key: "qa", label: tr("QA"), kind: "work", stage: qaNode, about: tr("Auditors in parallel score the milestone from 0 to 100 per dimension"),
        state: gateFailed ? "done" : qaNode.state === "upcoming" ? "todo" : qaNode.state, here: Boolean(qaNode.here) && !gateFailed, running: x.running, agents: x.agents,
        sub: x.passed ? tr("passed{v}", { v: m.score != null ? ` · ${m.score}` : "" }) : x.running ? tr("auditing · round {n}", { n: x.round }) : x.fixActive.length ? tr("fixes {v}/{n}", { v: x.fixes.length - x.fixOpen.length, n: x.fixes.length }) : x.qa.runs ? plural(x.qa.runs, "round") : tr("auditors") } : null,
      qaNode ? { key: "gate", label: tr("Gate"), kind: "gate", stage: qaNode, about: tr("Hard floor, exit check and cut-offs: a failed gate creates fix tasks and a new round"),
        state: x.passed ? "done" : gateFailed ? "failed" : "todo", here: gateFailed, need: gateFailed ? 1 : 0, needText: tr("decide"),
        sub: x.passed ? (m.gate === "skipped" ? tr("skipped") : tr("passed")) : gateFailed ? tr("rounds used up") : tr("floor · exit · cut-off") } : null,
    ];
    if (by.deploy) nodes.push(node(by.deploy, { key: "deploy", label: qaNode && qaNode.sub ? tr("Smoke, deploy") : tr("Deploy"), kind: "ship", sub: by.deploy.note, running: Boolean(by.deploy.running), stage: by.deploy,
      about: tr("Deploy after the gate, behind the release flag when the release is flagged") }));
    else nodes.push(node(by.close, { key: "close", label: tr("Closed"), kind: "ship", sub: by.close ? by.close.note : "", stage: by.close }));
    const out = nodes.filter(Boolean);
    out.forEach((n) => {
      const s = n.stage;
      if (!s) return;
      n.detail = () => [s.note ? h("p", { class: "fd-note" }, s.note, s.cmd ? [" ", cmd(s.cmd)] : null) : null,
        s.trail && s.trail.length && n.key === "qa" ? qaTrailEl(s.trail) : null,
        (s.tasks || []).length ? h("ul", { class: "list" }, s.tasks.map((t) => h("li", { class: "has-btn" }, h("button", { type: "button", class: "row-btn", "data-tid": t.id, onclick: () => { closeList(); openTask(t.id); } },
          h("span", { class: "id", text: t.id }), h("span", { text: t.title || "" }), h("span", { class: `chip st-chip s-${t.status}`, text: stLabel(t.status) }))))) : null,
        n.key === "qa" && hasDoc(`qa/${m.id}/report.md`) ? h("p", {}, docLink(`qa/${m.id}/report.md`, tr("Open the QA report"))) : null];
    });
    return out;
  }
  const qaTrailEl = (trail) => h("ol", { class: "qa-trail", "aria-label": tr("QA rounds") },
    trail.map((p, i) => h("li", { class: `qa-pill ${p.cls}`, title: p.title }, i ? h("span", { class: "qa-arrow", "aria-hidden": "true", text: "→" }) : null,
      h("span", { class: "qa-tag", text: p.text }), h("span", { class: "visually-hidden", text: `: ${p.title}.` }))));
  function renderStages(m) {
    const box = $("stages");
    $("ms-strip-sub").textContent = m ? tr("construction: the next milestone starts only after this gate passes") : "";
    if (!m) {
      fill(box, flowList([{ key: "plan", label: tr("Pull issues"), state: "todo" }, { key: "build", label: tr("Implement"), kind: "work", state: "todo" }, { key: "qa", label: tr("QA"), kind: "work", state: "todo" },
        { key: "gate", label: tr("Gate"), kind: "gate", state: "todo" }, { key: "close", label: tr("Closed"), kind: "ship", state: "todo" }], false, tr("Milestone stages")),
      flowDetail(h("span", { class: "sub" }, tr("Stages appear once the plan has milestones."))));
      return;
    }
    const st = stagesOf(m);
    const here = st.find((x) => x.here);
    const shown = new Set();
    // the detail line: what happens at the current stage, its command, the QA rounds, who works on it now
    let detail = null;
    if (here) {
      const running = here.tasks.filter((t) => t.status === "in_progress");
      const blocked = here.tasks.filter((t) => t.status === "blocked");
      running.forEach((t) => shown.add(t.id));
      const chips = [...running.map(runChip), ...(here.agents || []).map((a) => h("span", { class: "run-chip auditor", title: roleOf(a.agent).about || a.agent }, agentBits(a, true)))];
      let nextBtn = null;
      if (!chips.length) {
        const nt = data.next && data.next.task && data.tasks[data.next.task];
        if (nt && nt.milestone === m.id && here.tasks.some((t) => t.id === data.next.task)) {
          nextBtn = h("button", { type: "button", class: "next-btn", "data-tid": data.next.task, onclick: () => openTask(data.next.task) },
            h("span", { class: "chip next-chip", text: tr("next up") }), h("span", { class: "tid", text: data.next.task }), h("span", { class: "run-title", text: nt.title }));
        }
      }
      const isRun = here.running || (here.key === "qa" && qaState(m).running);
      detail = [h("span", { class: `fd-word st-${here.state}` }, isRun ? h("span", { class: "rn-dot", "aria-hidden": "true" }) : null, here.name),
        here.note ? h("span", { class: "fd-note" }, here.note, here.cmd ? [" ", cmd(here.cmd)] : null,
          here.key === "qa" && hasDoc(`qa/${m.id}/report.md`) ? [" ", docLink(`qa/${m.id}/report.md`, "report")] : null) : null,
        here.sub ? h("span", { class: `stage-sub st-${here.sub.state}` }, h("span", { "aria-hidden": "true", text: `${STAGE_ICON[here.sub.state]} ` }), `${here.sub.name}: ${here.sub.note}`) : null,
        here.trail && here.trail.length ? qaTrailEl(here.trail) : null,
        here.decide ? h("button", { type: "button", class: "stage-blocked", text: tr("Needs your decision"), onclick: goNeeds }) : null,
        blocked.length ? h("button", { type: "button", class: "stage-blocked", text: tr("⛔ {blocked_n} blocked", { blocked_n: blocked.length }), onclick: goNeeds }) : null,
        chips.length ? h("span", { class: "stage-run" }, chips) : null, nextBtn];
    } else if (st.at(-1).state === "done") {
      detail = [h("span", { class: "fd-word st-done", text: tr("Closed") }), h("span", { class: "sub", text: st.at(-1).note || "" })];
    }
    // anything running outside this milestone's stages stays visible
    const elsewhere = Object.entries(data.tasks).filter(([id, t]) => t.status === "in_progress" && !shown.has(id) && t.milestone !== m.id).map(([id, t]) => runChip({ id, ...t }));
    const taskIds = new Set(Object.keys(data.tasks));
    activeAgents().filter((a) => !(a.node && (taskIds.has(a.node) || a.node === `GATE:${m.id}`))).forEach((a) =>
      elsewhere.push(h("span", { class: "run-chip", title: `${roleOf(a.agent).about || a.agent}${a.node ? "" : tr(". Not linked to a task or a QA gate")}` },
        a.node ? h("span", { class: "tid", text: a.node.replace("GATE:", "QA ") }) : h("span", { class: "unlinked", text: tr("not linked") }), agentBits(a, true))));
    fill(box, flowList(msNodes(m), false, tr("Stages of {id}", { id: m.id })),
      flowDetail(detail, elsewhere.length ? h("span", { class: "also-running", id: "also-running" }, h("span", { class: "also-label", text: tr("Running outside this milestone") }), elsewhere) : null));
  }

  /** The words of one feed row: what happened, for the user (the full log keeps every technical line). */
  const FEED_TEXT = tmap({
    task_done: N_("{task} done: {title}"), task_started: N_("{task} started: {title}"), task_blocked: N_("{task} blocked: {reason}"), task_dropped: N_("{task} dropped: {reason}"),
    gate_passed: N_("{milestone} passed the QA gate{score_part}"), qa_round_done: N_("QA round of {milestone} finished{score_part}: fixes follow{reason_part}"),
    gate_failed: N_("{milestone} failed the QA gate{score_part}"), qa_round_started: N_("QA round of {milestone} started"),
    question_open: N_("Question {id}: {text}"), question_answered: N_("{id} answered: {text}"), issue_new: N_("New {type} {id}: {title}"), issue_classified: N_("{id} classified as {cls}"),
    release_submitted: N_("{release} submitted for your approval"), release_approved: N_("{release} approved"), release_rejected: N_("{release} rejected: fixes planned"),
    released: N_("Released {version} ({tag})"), deploy: N_("Deploy to {env}: {status} ({sha})"), review: N_("Review of the {name}: {value}{score_part}"),
    checkpoint: N_("{target_word} {decision_word}"), failure: N_("/dev-kit:{skill} {scope} failed") });
  function feedText(r) {
    const v = { ...(r.vars || {}) };
    v.score_part = v.score ? ` (${v.score})` : "";
    v.reason_part = v.reason ? ` · ${v.reason}` : "";
    v.target_word = v.target === "prd" ? tr("PRD") : tr("Plan");
    v.decision_word = v.decision === "confirm" ? "confirmed" : tr("sent back for changes");
    return (FEED_TEXT[r.kind] || r.kind).replace(/\{(\w+)\}/g, (_, k) => (v[k] != null ? String(v[k]) : "")).replace(/\s+$/, "");
  }
  let fullLog = false;
  function renderFeed() {
    fill($("log-link"), h("button", { type: "button", class: "link-btn", "aria-pressed": String(fullLog), text: fullLog ? tr("Activity") : tr("Full log"),
      title: fullLog ? tr("Back to what happened") : tr("Every line of .dev/log.md and the session log"), onclick: () => { fullLog = !fullLog; renderFeed(); } }),
      fullLog && hasDoc("log.md") ? [" · ", docLink("log.md", "log.md")] : null);
    const rows = fullLog ? data.log : (data.feed || []);
    fill($("feed"), rows.length ? rows.map((r) => {
      const t = parseT(r.at);
      return h("li", { class: r.kind === "live" ? "feed-live" : r.kind ? `feed-${r.kind}` : null }, h("time", { datetime: r.at, title: Number.isFinite(t) ? fmtDT(t) : r.at, text: Number.isFinite(t) ? agoShort(t) : r.at }),
        h("span", { class: "txt" }, linkify(fullLog ? r.text : feedText(r))));
    }) : h("li", {}, h("span", { class: "txt", text: tr("No activity logged yet.") })));
    fill($("foot"), tr("{v} of {project}/.dev{v2} · autonomy {v3}", { v: actionsOn() ? tr("View") : tr("Read-only view"), project: data.project, v2: actionsOn() ? tr(" · requests run by Claude Code") : "", v3: data.autonomy || "?" }));
    const b = data.board;
    fill($("server-about"), b ? tr("Server pid {pid} on port {port}", { pid: b.pid, port: b.port }) : tr("Server details unknown"), tr(". Stop it here or with "), cmd("/dev-kit:board stop"), ".");
  }

  // ------------------------------------------------------------------ insights: quality (definition of done) and backlog
  function dodRow(name, score, cut, verdict, links) {
    const mm = h("div", { class: "meter" });
    const sp = h("span"); sp.style.width = `${score != null ? Math.min(100, score) : 0}%`;
    const c = h("span", { class: "cut", title: tr("cut-off {cut}", { cut }) }); c.style.left = `calc(${cut}% - 1px)`;
    mm.append(sp, c);
    const ok = verdict === "pass" || verdict === "passed" || verdict === "skipped" || verdict === "n/a";
    const bad = verdict === "fail" || (score != null && score < cut && !ok);
    return h("div", { class: "dod-row" }, h("span", { class: "name" }, name, " ",
      h("span", { class: `badge ${ok ? "good" : bad ? "bad" : "neutral"}`, text: ok ? `✓ ${verdict}` : bad ? tr("✕ below cut-off") : verdict || "pending" }),
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
      pend.length ? h("p", { class: "pending-line", text: tr("Not run yet: {v}", { v: pend.join(", ") }) }) : null,
      !rows.length && !pend.length ? h("div", { class: "empty", text: emptyText }) : null);
  }
  const OWN_REVIEWS = ["prd", "design", "plan", "ux", "docs"];

  /** Construction › Gates: the QA gate of every milestone that ran one. */
  const debtLine = (d) => tr("Deferred debt: {total} open (cap {v}) · {medium} medium (cap {v2}){v3}", { total: d.total, v: d.cap_total ?? "off", medium: d.medium, v2: d.cap_medium ?? "off", v3: d.over ? tr(" · above the cap") : "" });
  function renderGates() {
    const q = data.quality;
    $("dod-sub").textContent = tr("Cut-off {min_overall} overall · {min_dimension} per dimension. Rows show the score against its cut-off mark.", { min_overall: q.min_overall, min_dimension: q.min_dimension });
    const gStarted = (m) => m.score != null || m.gate !== "pending";
    const rows = data.milestones.filter(gStarted).map((m) => dodRow(`${m.id} ${m.title || ""}`, m.score ?? null, q.min_overall, m.gate === "pending" ? "fail" : m.gate,
      [`qa/${m.id}/report.md`, `qa/${m.id}/risk-report.md`].filter(hasDoc).map((p) => docLink(p, p.endsWith("risk-report.md") ? tr("risk report") : tr("report"))))).reverse();
    const pending = data.milestones.filter((m) => !gStarted(m)).map((m) => m.id);
    const debt = (data.backlog || {}).debt;
    fill($("dod"), rows.length ? h("div", { class: "list" }, rows) : !pending.length ? h("div", { class: "empty", text: tr("No milestones yet.") }) : null,
      pending.length ? h("p", { class: "pending-line", text: tr("Not run yet: {v}", { v: pending.join(", ") }) }) : null,
      debt && debt.total ? h("p", { class: `pending-line${debt.over ? " bad" : ""}`, text: debtLine(debt) }) : null);
  }

  const issueId = (id) => (hasDoc("issues.md") ? docLink("issues.md", String(id), String(id), "id") : h("span", { class: "id", text: String(id) }));
  const issueLi = (i) => h("li", {}, issueId(i.id), h("span", { text: i.title || "" }),
    h("span", { class: `chip${i.c === "expedite" ? " lane-hotfix" : ""}`, text: i.c || i.status }),
    h("span", { class: "sub", text: [i.type, i.severity, i.origin === "baseline" ? "pre-existing" : null, i.scheduled_in ? `→ ${i.scheduled_in}` : null, i.c && i.status && i.c !== i.status ? i.status : null].filter(Boolean).join(" · ") }));
  /** Shows a milestone in Construction, from anywhere on the board. */
  function openMilestone(id) {
    selected = id; mobileCol = null;
    setPhase("construction");
  }

  // ------------------------------------------------------------------ QA panel: what the QA & fixes stage is doing now
  let qaAutoFor = null;  // the milestone the panel opened by itself for (once; the user's choice of tab is kept after that)
  function autoQaView(m) {
    const here = m && stagesOf(m).find((x) => x.here);
    if (here && here.key === "qa" && qaAutoFor !== m.id) { qaAutoFor = m.id; if (view === "tasks") { view = "qa"; applyView(); } }
  }
  function renderQaPanel(m) {
    const box = $("qa-panel");
    if (!m) { fill(box); return; }
    const x = qaState(m);
    const sect = (title, ...kids) => h("section", { class: "qa-sect" }, h("h3", { class: "list-title", text: title }), ...kids);
    const r = x.qa.round;
    const auditors = r && r.auditors && r.auditors.length ? h("ul", { class: "list" }, r.auditors.map((a) => h("li", {},
      h("span", { class: "id", text: a.agent }), h("span", { class: `chip ${a.state === "running" ? "wait" : a.state === "done" ? "ready" : "bad"}`, text: a.state }),
      a.model ? h("span", { class: "chip", text: a.model }) : null,
      h("span", { class: "sub", text: a.duration_s != null ? dur(a.duration_s) : a.started_at ? tr("for {v}", { v: dur((Date.now() - parseT(a.started_at)) / 1000) }) : "" }),
      a.findings ? h("span", { class: "sub", text: Object.entries(a.findings).filter(([, n]) => n).map(([k, n]) => `${n} ${k}`).join(", ") }) : null)))
      : h("div", { class: "empty", text: x.running ? tr("Auditors starting") : x.passed ? tr("The gate passed") : tr("No round running now") });
    const last = x.qa.last;
    const report = hasDoc(`qa/${m.id}/report.md`) ? `qa/${m.id}/report.md` : null;
    const blocking = !x.passed && last && last.blocking && last.blocking.length ? h("ul", { class: "list" }, last.blocking.map((f) => h("li", {},
      report && f.id ? docLink(report, f.id, f.id, "id") : h("span", { class: "id", text: f.id || "!" }),
      h("span", { text: f.title || "" }), h("span", { class: `chip sev-${f.severity}`, text: f.severity || "" }),
      f.file ? h("span", { class: "sub mono-wrap", text: `${f.file}${f.line ? `:${f.line}` : ""}` }) : null)))
      : h("div", { class: "empty good", text: x.passed ? tr("None: the gate passed") : tr("No blocking finding open") });
    const cols = ["todo", "in_progress", "blocked", "done"].map((k) => [k, x.fixes.filter((t) => t.status === k)]).filter(([, v]) => v.length);
    const fixes = cols.length ? h("div", { class: "qa-fixes" }, cols.map(([k, v]) => h("div", { class: `qa-fix-col s-${k}` },
      h("div", { class: "list-title", text: `${stLabel(k)} ${v.length}` }), v.map((t) => h("button", { type: "button", class: "run-chip", "data-tid": t.id, onclick: () => openTask(t.id) },
        h("span", { class: "tid", text: t.id }), h("span", { class: "run-title", text: t.title })))))) : h("div", { class: "empty", text: tr("No fix tasks") });
    const hf = m.hard_floor && m.hard_floor.checks ? h("ul", { class: "list" }, Object.entries(m.hard_floor.checks).map(([n, c]) => h("li", {},
      h("span", { class: "id", text: c.status === "fail" ? "✕" : c.status === "pass" ? "✓" : "–" }), h("span", { text: n }),
      c.severity ? h("span", { class: "chip", text: c.severity }) : null, c.task ? h("span", { class: "sub", text: c.task }) : null)))
      : h("div", { class: "empty", text: tr("No deterministic checks recorded yet") });
    const ex = m.exit_check ? h("div", { class: "sub" }, [m.exit_check.cmd ? `cmd: ${m.exit_check.cmd}` : null, m.exit_check.e2e ? `e2e: ${m.exit_check.e2e}` : null,
      (m.exit_check.acs || []).length ? tr("acs: {v}", { v: (m.exit_check.acs || []).join(", ") }) : null].filter(Boolean).join(" · "))
      : h("div", { class: "empty", text: tr("No exit_check in the plan for this milestone") });
    const problems = (m.gate_checks || []).length ? h("ul", { class: "list" }, m.gate_checks.map((g) => h("li", {}, h("span", { class: "id", text: g.hard ? "⛔" : "!" }), h("span", { text: g.text })))) : null;
    fill(box, sect(tr("Auditors{v}", { v: r ? tr(" · round {n}", { n: r.n }) : "" }), auditors), sect(tr("Blocking findings open"), blocking, report ? h("p", { class: "sub" }, docLink(report, tr("Open the QA report"))) : null),
      sect(tr("Fixes"), fixes), sect(tr("Hard floor"), hf), sect(tr("Exit check"), ex), problems ? sect(tr("What still stops the gate"), problems) : null);
  }

  // ------------------------------------------------------------------ tiles: blocks of the same size; what does not fit opens in a modal
  /** A tile: title, a count, a line, its body, and "See all" when the body is cut (or always, with all()). */
  function tile(o) {
    // "See all" opens the whole list (all()), or a copy of the body when the tile has no longer version
    const whole = () => (o.all ? o.all() : [].concat(o.body).flat(9).filter((n) => n && n.cloneNode).map((n) => n.cloneNode(true)));
    const more = h("button", { type: "button", class: "tile-more", hidden: true, onclick: () => openList(o.title, whole()) });
    return h("section", { class: `tile${o.cls ? ` ${o.cls}` : ""}`, "aria-label": o.title, id: o.id || null },
      h("div", { class: "tile-head" }, h("h3", { text: o.title }), o.count != null ? h("span", { class: "tile-count", text: String(o.count) }) : null,
        o.sub ? h("span", { class: "tile-sub", title: typeof o.sub === "string" ? o.sub : null }, o.sub) : null),
      h("div", { class: "tile-body", id: o.bodyId || null, "data-clamp": "rows" }, o.body),
      h("div", { class: "tile-foot" }, h("span", { class: "tile-foot-text" }, o.foot || null), more));
  }
  // rows a cut tile hides (list items, score rows, list titles, empty notes, facts) and the ones it counts in "See all"
  const CLAMP_ROWS = ":scope > *, :scope .list > li, :scope .list > .dod-row, :scope .list-title, :scope .empty, :scope .pending-line, :scope .kpi, :scope .fact, :scope .hc > *, :scope .facts-grid";  // i18n-ok: selectors
  const COUNTED = "li, .dod-row, .kpi, .fact";  // i18n-ok: selectors
  /** Hides what does not fit in one box; returns how many rows went and whether anything did. */
  function clampBox(box) {
    box.querySelectorAll(".clamped").forEach((el) => el.classList.remove("clamped"));
    const limit = box.getBoundingClientRect().bottom + 1;
    let cut = 0, any = false;
    if (box.dataset.clamp === "cards") {
      // a column keeps its first cards: once one does not fit, the ones below it go too
      let over = false;
      [...box.children].forEach((el) => { if (over || el.getBoundingClientRect().bottom > limit) { over = true; el.classList.add("clamped"); cut += 1; } });
      return { cut, any: cut > 0 };
    }
    // last rows first, so a list keeps its first rows and a block goes as a whole only when none of it fits
    const rows = [...box.querySelectorAll(CLAMP_ROWS)].reverse();
    const live = (el) => [...el.querySelectorAll(COUNTED)].filter((c) => !c.closest(".clamped")).length;
    rows.forEach((el) => {
      if (el.closest(".clamped") || el.getBoundingClientRect().bottom <= limit) return;
      cut += el.matches(COUNTED) ? 1 : live(el);
      el.classList.add("clamped"); any = true;
    });
    // a block left with nothing visible goes too (its title alone says nothing)
    rows.forEach((el) => { if (!el.classList.contains("clamped") && el.children.length && [...el.children].every((c) => c.classList.contains("clamped") || c.classList.contains("list-title"))) el.classList.add("clamped"); });
    return { cut, any };
  }
  /** Every tile and kanban column keeps the size of the grid: what does not fit goes behind "See all" / "+N more". */
  function clampAll() {
    clampRaf = 0;
    document.querySelectorAll("[data-clamp]").forEach((box) => {
      if (!box.offsetParent) return;
      const cards = box.dataset.clamp === "cards";
      const more = box.parentElement.querySelector(cards ? ".col-more" : ".tile-more");
      if (more) more.hidden = true;
      const label = (n) => (cards ? tr("+{n} more", { n }) : n ? tr("See all ({n} more)", { n }) : tr("See all"));
      let r = clampBox(box);
      if (r.any && more) {
        // the button takes room (with its text): measure again with it shown
        more.hidden = false; more.textContent = label(r.cut);
        r = clampBox(box);
      }
      if (!more) return;
      more.hidden = !r.any;
      more.textContent = label(r.cut);
    });
  }
  let clampRaf = 0;
  const clampSoon = () => { if (!clampRaf) clampRaf = requestAnimationFrame(clampAll); };

  // the modal that shows a whole list, or the details of a step
  const ldlg = $("list-dialog");
  let listOrigin = null;
  function openList(title, kids) {
    if (!ldlg.open) listOrigin = document.activeElement;
    $("list-title").textContent = title;
    fill($("list-body"), [].concat(kids).flat(9));
    if (!ldlg.open) (ldlg.showModal ? ldlg.showModal() : ldlg.setAttribute("open", ""));
    $("list-body").scrollTop = 0;
  }
  const closeList = () => { if (ldlg.open) ldlg.close(); };
  $("list-close").addEventListener("click", closeList);
  ldlg.addEventListener("click", (e) => { if (e.target === ldlg) closeList(); });
  ldlg.addEventListener("close", () => { if (listOrigin && listOrigin.isConnected) listOrigin.focus(); listOrigin = null; });

  // ------------------------------------------------------------------ phases: conception, planning, stable (construction is the milestone view above)
  /** One conception or planning step: state, why it is out of date, its files in .dev/, and the command that moves it on. */
  function stepCard(x) {
    const files = (data.artifacts || {})[x.key] || [];
    const running = runsAt(`step:${x.key}`);
    const c = x.state === "review" ? STEP_REVIEW_CMD[x.key] : ["todo", "doing", "stale"].includes(x.state) ? STEP_CMD[x.key] : null;
    return h("div", { class: `step-card s-${x.state}${running.length ? " running" : ""}` },
      runBanner(running),
      h("div", { class: "step-top" }, h("span", { class: "step-mark", "aria-hidden": "true", text: STEP_MARK[x.state] }),
        h("strong", { text: STEP_TITLE[x.key] || x.key }), h("span", { class: `chip step-st s-${x.state}`, text: STEP_WORD[x.state] })),
      h("p", { class: "card-sub", text: STEP_ABOUT[x.key] || "" }),
      x.note ? h("p", { class: "step-note", text: x.note }) : null,
      files.length ? h("p", { class: "step-files" }, files.map((f) => docLink(f, relDev(f)))) : null,
      c ? h("div", { class: "step-act" }, cmd(c)) : null);
  }
  const phaseOf = (key) => data.cycle.phases.find((p) => p.key === key) || { steps: [] };
  const stepOf = (phase, key) => (phaseOf(phase).steps || []).find((x) => x.key === key) || { key, state: "todo", note: null };
  /** A skill's step of conception or planning as a node: its state, its run, and its card in the details. */
  function stepNode(phase, key, label, sub, extra) {
    const x = stepOf(phase, key);
    const s = x.state;
    const state = s === "skipped" ? "skipped" : ["done", "review", "checkpoint"].includes(s) ? "done" : ["doing", "stale"].includes(s) ? "current" : "todo";
    return { key, label, sub, state, running: runsAt(`step:${key}`).length > 0, about: STEP_ABOUT[key] || null, run: ["todo", "doing", "stale"].includes(s) ? STEP_CMD[key] : null,
      detail: () => stepCard(x), ...extra };
  }
  /** The review after a step: current while the step waits for it, with its score against the cut-off. */
  function reviewNode(key, label, steps, rkey, who) {
    const sts = steps.map((k) => stepOf(key === "plan" ? "planning" : "conception", k).state);
    const live = sts.filter((s) => s !== "skipped");
    const v = data.reviews[rkey] || {};
    const cut = data.quality.review_min_overall;
    const state = !live.length ? "skipped" : live.some((s) => s === "review") ? "current" : live.every((s) => ["done", "checkpoint"].includes(s)) ? (v.verdict === "fail" ? "failed" : "done") : "todo";
    return { key: `review-${rkey}`, label, kind: "", sub: v.score != null ? `${v.score} / ${cut}` : who, state, who, running: runsAt(`step:${steps[steps.length - 1]}`).some((r) => r.skill === "review"),
      about: tr("A reviewer scores it against the cut-off; a fail sends it back for revision"), run: state === "current" ? STEP_REVIEW_CMD[steps[0]] : null,
      detail: () => reviewList([rkey], tr("Not run yet.")) };
  }
  /** Your confirmation (a checkpoint): current while the review passed and nothing goes on until you confirm. */
  function confirmNode(phase, key, label) {
    const s = stepOf(phase, key).state;
    const cp = ((data.backlog || {}).needs || []).find((x) => x.kind === "checkpoint" && x.target === key);
    return { key: `confirm-${key}`, label, kind: "human", sub: tr("checkpoint on the board"), state: s === "done" ? "done" : s === "checkpoint" || cp ? "current" : "todo", need: cp ? 1 : 0,
      needText: tr("waiting"), about: tr("Nothing after this step starts until you confirm it, or ask for changes"),
      detail: () => (cp ? h("ul", { class: "list" }, checkpointRow(cp)) : null) };
  }
  /** The badge of a lane goes on its steps: what is not tied to one step sits on the current one (or the first not done). */
  function placeNeeds(k, nodes) {
    const placed = nodes.reduce((n, x) => n + (x.need || 0), 0);
    const left = Math.max(0, (needsBy[k] || 0) - placed);
    if (!left) return nodes;
    const at = nodes.find((x) => x.here) || nodes.find((x) => x.kind === "human" && x.state !== "done") || nodes.find((x) => x.state !== "done" && x.state !== "skipped") || nodes[nodes.length - 1];
    if (at) { at.need = (at.need || 0) + left; at.needText = plural(at.need, "item"); }
    return nodes;
  }
  const markHere = (nodes) => { if (!nodes.some((n) => n.here)) { const c = nodes.find((n) => n.state === "current" || n.state === "failed"); if (c) c.here = true; } return nodes; };
  function concNodes() {
    const uxs = ["ux", "ui"].map((k) => stepOf("conception", k).state);
    const uxLive = uxs.filter((s) => s !== "skipped");
    const ux = { key: "uxui", label: tr("UX → UI"), sub: uxLive.length ? tr("flows and screens") : tr("only with an interface"),
      state: !uxLive.length ? "skipped" : uxLive.some((s) => ["doing", "stale"].includes(s)) ? "current" : uxLive.every((s) => ["done", "review", "checkpoint"].includes(s)) ? "done" : "todo",
      running: runsAt("step:ux").length + runsAt("step:ui").length > 0, about: STEP_ABOUT.ux, run: uxLive.some((s) => ["todo", "doing", "stale"].includes(s)) ? STEP_CMD[uxs[0] !== "done" && uxs[0] !== "skipped" ? "ux" : "ui"] : null,
      detail: () => h("div", { class: "step-pair" }, stepCard(stepOf("conception", "ux")), stepCard(stepOf("conception", "ui"))) };
    return placeNeeds("conception", markHere([
      stepNode("conception", "interview", tr("Interview"), "brief.md"),
      stepNode("conception", "prd", tr("PRD"), tr("prd.md · criteria AC-n")),
      reviewNode("prd", tr("Review PRD"), ["prd"], "prd", "requirements-reviewer"),
      confirmNode("conception", "prd", tr("Confirm PRD")),
      stepNode("conception", "architecture", tr("Architecture"), tr("architecture.md · ADRs")),
      ux,
      reviewNode("design", tr("Review design"), ["ux", "ui"], "design", "design-reviewer")]));
  }
  function planNodes() {
    const s = stepOf("planning", "plan").state;
    return placeNeeds("planning", markHere([
      stepNode("planning", "plan", tr("Plan"), tr("releases → milestones → tasks")),
      reviewNode("plan", tr("Review plan"), ["plan"], "plan", "requirements-reviewer"),
      confirmNode("planning", "plan", tr("Confirm plan")),
      { key: "sync", label: tr("Sync plan"), sub: tr("state.json, IDs, release flags"), state: s === "done" && data.milestones.length ? "done" : "todo",
        about: tr("The plan becomes milestones and tasks with IDs; release flags are created") }]));
  }
  /** Where the next step of conception or planning happens, in one line: the step, its note, its command, what runs. */
  function stepDetail(nodes) {
    const here = nodes.find((n) => n.here);
    if (!here) return null;
    const runs = here.key.startsWith("review-") ? [] : runsAt(`step:${here.key === "uxui" ? "ux" : here.key}`);
    const st = here.state === "current" && here.kind === "human" ? "waiting" : here.state;
    return flowDetail(h("span", { class: `fd-word st-${st}` }, here.running ? h("span", { class: "rn-dot", "aria-hidden": "true" }) : null, here.label),
      h("span", { class: "sub", text: NODE_WORD[st] }),
      here.kind === "human" && here.need ? h("button", { type: "button", class: "btn btn-sm btn-danger", text: tr("Open Needs you"), onclick: goNeeds }) : null,
      here.run ? cmd(here.run) : null, runs.length ? runBanner(runs) : null);
  }

  function renderConception() {
    const nodes = concNodes();
    const p = phaseOf("conception");
    fill($("conc-strip"), stripHead("conception", tr("What the product is and how it is built, before any plan"),
      h("span", { class: `chip lane-chip st-${laneState("conception")}`, text: PHASE_WORD[p.state === "active" ? "current" : p.state] || "" })),
      flowList(nodes, false, tr("Steps of conception")), stepDetail(nodes));
    // documents of the steps, the reviews, decisions and facts, scope changes
    const docs = ["interview", "prd", "architecture", "ux", "ui"].flatMap((k) => ((data.artifacts || {})[k] || []).map((f) => ({ k, f })));
    const docRows = () => docs.map(({ k, f }) => h("li", { class: "has-btn" }, docLink(f, `${STEP_TITLE[k] || k} · ${relDev(f)}`, null, "row-doc")));
    const adrs = data.decisions || [];
    const facts = data.facts || [];
    const adrLi = (d) => h("li", { class: /supersed/i.test(d.status || "") ? "muted" : null }, docLink("decisions.md", d.id, d.id, "id"), h("span", { text: d.title }),
      h("span", { class: "chip", text: d.status || "?" }), d.date ? h("span", { class: "sub", text: d.date }) : null);
    const factLi = (f) => h("li", { class: f.stale ? "muted" : null }, hasDoc("facts.md") ? docLink("facts.md", f.id, f.id, "id") : h("span", { class: "id", text: f.id }),
      f.stale ? h("s", { text: f.text }) : h("span", { text: f.text }), h("span", { class: "sub", text: tr("Evidence: {evidence}", { evidence: f.evidence }) }));
    const decBody = () => [listBlock(tr("Decisions"), adrs.map(adrLi), tr("No decision recorded yet. The interview and architecture write them."), false),
      listBlock(tr("Facts"), facts.filter((f) => !f.stale).map(factLi), tr("No fact recorded yet. Agents record what they verify with evidence."), false)];
    const issues = Object.entries((data.backlog || {}).issues || {}).map(([id, v]) => ({ id, c: v.class, ...v })).filter((i) => i.type === "change" || i.class === "change");
    const open = issues.filter((i) => !["closed", "done", "dropped"].includes(i.status));
    fill($("conc-tiles"),
      tile({ title: tr("Documents"), count: docs.length, sub: tr("open in the reader"), body: docs.length ? h("ul", { class: "list" }, docRows()) : h("div", { class: "empty", text: tr("No document yet. The interview writes the first one.") }), all: () => h("ul", { class: "list" }, docRows()) }),
      tile({ title: tr("Reviews"), sub: tr("Cut-off {review_min_overall}", { review_min_overall: data.quality.review_min_overall }), body: reviewList(["prd", "design"], tr("No reviews.")), all: () => reviewList(["prd", "design"], tr("No reviews.")) }),
      tile({ title: tr("Decisions and facts"), count: adrs.length + facts.filter((f) => !f.stale).length || null, sub: ".dev/decisions.md · facts.md", body: decBody(), all: () => [decBody()[0], renderFacts()] }),
      tile({ title: tr("Scope changes"), count: open.length || null, sub: tr("Change issues go back through the PRD"),
        body: [listBlock(tr("Open"), open.map(issueLi), tr("No scope change waiting."), true), issues.length > open.length ? h("p", { class: "pending-line", text: tr("{v} closed", { v: issues.length - open.length }) }) : null],
        foot: actionsOn() ? h("button", { type: "button", class: "link-btn", text: tr("＋ New issue"), onclick: newIssue }) : null }));
  }
  /** Facts (conventions §2), searchable by text, file or AC: verified facts with their evidence, newest first; a contradicted one stays, struck through. */
  let factQuery = "";
  function renderFacts() {
    const all = data.facts || [];
    const q = () => factQuery.trim().toLowerCase();
    const hit = (f) => !q() || [f.id, f.text, f.evidence, ...(f.files || []), ...(f.acs || [])].some((v) => String(v || "").toLowerCase().includes(q()));
    const li = (f) => h("li", { class: f.stale ? "muted" : null }, hasDoc("facts.md") ? docLink("facts.md", f.id, f.id, "id") : h("span", { class: "id", text: f.id }),
      f.stale ? h("s", { text: f.text }) : h("span", { text: f.text }),
      h("span", { class: "sub", text: tr("Evidence: {evidence}{v} · {v2} · {v3}", { evidence: f.evidence, v: f.sha ? ` @${f.sha}` : "", v2: f.date || "", v3: f.origin || "" }) }),
      (f.files || []).length || (f.acs || []).length ? h("span", { class: "q-tags" }, ...(f.files || []).map((x) => h("span", { class: "chip", text: x })), ...(f.acs || []).map((x) => h("span", { class: "chip", text: x }))) : null,
      f.stale ? h("span", { class: "sub bad", text: tr("Contradicted by {by}: {evidence}", { by: f.stale.by, evidence: f.stale.evidence }) }) : null);
    if (!all.length) return listBlock(tr("Facts"), [], tr("No fact recorded yet. Agents record what they verify with evidence."), false);
    const input = h("input", { type: "search", class: "answer-input", placeholder: tr("Search facts, files, ACs"), "aria-label": tr("Search facts") });
    input.value = factQuery;
    const list = h("ul", { class: "list" });
    const paint = () => fill(list, all.filter(hit).map(li));
    input.addEventListener("input", () => { factQuery = input.value; paint(); });
    paint();
    return h("div", {}, h("div", { class: "list-title", text: tr("Facts") }), input, list);
  }

  // the CSP forbids style attributes: the width goes through the CSSOM
  const roadMeter = (x) => { const bar = h("span"); bar.style.width = `${x.total ? Math.round((x.done / x.total) * 100) : 0}%`; return h("span", { class: "road-meter", "aria-hidden": "true" }, bar); };
  let replanOpen = false;
  function renderPlanning() {
    const nodes = planNodes();
    const p = phaseOf("planning");
    fill($("pl-strip"), stripHead("planning", tr("The plan and every replan; no milestone starts before the plan is confirmed"),
      actionsOn() ? h("button", { type: "button", class: "btn btn-sm btn-primary", id: "replan-btn", onclick: () => { replanOpen = true; render(); } }, tr("Replan the milestones →"))
        : h("span", { class: `chip lane-chip st-${laneState("planning")}`, text: PHASE_WORD[p.state === "active" ? "current" : p.state] || "" })),
      flowList(nodes, false, tr("Steps of planning")), stepDetail(nodes));
    // roadmap: releases and their milestones, in plan order
    const ms = data.milestones;
    const closed = ms.filter(isClosed).length;
    const row = (m) => {
      const x = milestoneInfo(m);
      const done = isClosed(m);
      return h("li", { class: "has-btn" }, h("button", { type: "button", class: `road-row${done ? " done" : ""}${m.id === data.current_milestone ? " cur" : ""}`, title: m.goal || null, onclick: () => { closeList(); openMilestone(m.id); } },
        h("span", { class: done ? "tab-ok" : `tab-dot ${x.active ? "active" : m.gate}`, "aria-hidden": "true", text: done ? "✓" : null }),
        h("strong", { class: "id", text: m.id }),
        h("span", { class: "road-title", text: m.title || m.id }),
        m.id === data.current_milestone ? h("span", { class: "tab-current", text: tr("current") }) : null,
        h("span", { class: "road-count", text: `${x.done}/${x.total}` }),
        roadMeter(x)));
    };
    const rp = relPlan();
    const roadRows = () => (rp.length ? ms.filter((m) => !rp.some((r) => r.milestones.includes(m.id))).map(row)
      .concat(rp.flatMap((r) => [h("li", { class: `road-rel s-${r.status}` }, h("strong", { text: r.id }), h("span", { class: "road-rel-title", text: r.title }),
        h("span", { class: `chip rel-st-${r.status}`, text: REL_WORD[r.status] })), ...ms.filter((m) => r.milestones.includes(m.id)).map(row)]))
      : ms.map(row));
    // backlog: the issue queue by class of service, the issues already scheduled, and what later milestones hold
    const b = data.backlog || {};
    const issues = b.issues || {};
    const order = ["expedite", "current", "standard", "intangible", "change"];
    const queued = order.flatMap((c) => ((b.queue || {})[c] || []).map((id) => ({ id, c, ...issues[id] })));
    const scheduled = Object.entries(issues).filter(([, v]) => ["scheduled", "in_progress"].includes(v.status));
    const curIdx = ms.findIndex((m) => m.id === data.current_milestone);
    const later = ms.slice(curIdx + 1).map((m) => ({ m, left: tasksOf(m).filter((t) => t.status !== "done").length })).filter((x) => x.left);
    const laterTasks = later.reduce((n, x) => n + x.left, 0);
    const backBody = () => [listBlock(tr("Issue queue"), queued.map(issueLi), tr("No issues waiting."), true),
      scheduled.length ? listBlock(tr("Scheduled issues"), scheduled.map(([id, v]) => issueLi({ id, c: v.class, ...v })), "") : null,
      listBlock(tr("Later milestones"), later.map(({ m, left }) => h("li", { class: "has-btn" },
        h("button", { type: "button", class: "row-btn", title: tr("Show {id} in construction", { id: m.id }), onclick: () => { closeList(); openMilestone(m.id); } },
          h("span", { class: "id", text: m.id }), h("span", { text: m.title || "" }), h("span", { class: "chip", text: plural(left, "task") })))),
      tr("Nothing planned after the current milestone."))];
    const tasks = Object.values(data.tasks).filter((t) => t.status !== "dropped").length;
    const kpi = (label, value) => h("div", { class: "kpi" }, h("span", { class: "fact-label", text: label }), h("strong", { text: String(value) }));
    fill($("pl-tiles"),
      tile({ title: tr("Roadmap"), count: ms.length || null, sub: ms.length ? tr("{closed} of {v} closed", { closed, v: plural(ms.length, "milestone") }) : "",
        body: ms.length ? h("ol", { class: "list road" }, roadRows()) : h("div", { class: "empty" }, tr("No milestones yet. They appear after "), cmd("/dev-kit:plan"), "."), all: () => h("ol", { class: "list road" }, roadRows()) }),
      tile({ title: tr("Backlog"), count: queued.length + laterTasks || null, sub: tr("{v} · {v2} in later milestones", { v: plural(queued.length, "queued issue"), v2: plural(laterTasks, "task") }),
        body: [runBanner(runsAt("backlog")), ...backBody()], all: backBody,
        foot: actionsOn() ? h("button", { type: "button", class: "link-btn", text: tr("＋ New issue"), onclick: newIssue }) : null }),
      tile({ title: tr("Plan review"), sub: tr("Cut-off {review_min_overall}", { review_min_overall: data.quality.review_min_overall }),
        body: [reviewList(["plan"], tr("Not run yet.")), h("div", { class: "kpis" }, kpi(tr("Releases"), rp.length), kpi(tr("Milestones"), ms.length), kpi(tr("Tasks"), tasks), kpi(tr("Flags"), (data.flags || []).length))],
        foot: hasDoc("plan.md") ? docLink("plan.md", "plan.md") : null }));
  }

  function stableNodes() {
    const hc = data.prod_health;
    const b = data.backlog || {};
    const q = b.queue || {};
    const n = (c) => (q[c] || []).length;
    const open = data.milestones.filter((m) => !isClosed(m)).length;
    const qneeds = (b.needs || []).filter((x) => !["checkpoint", "debt_over_cap", "lesson", "prod_health"].includes(x.kind)).length;
    const hneeds = (b.needs || []).filter((x) => x.kind === "prod_health").length;
    return placeNeeds("stable", markHere([
      { key: "stable", label: tr("Stable"), kind: "ship", sub: data.phase === "stable" ? tr("nothing open") : tr("Open milestones: {n}", { n: open }), state: data.phase === "stable" ? "done" : "todo",
        about: tr("Nothing open and every milestone released; the next issue starts the cycle again") },
      { key: "health", label: tr("Production health"), sub: hc && hc.last ? [hc.last.ok ? tr("healthy") : tr("failing"), hc.streak > 1 ? tr("{n} in a row", { n: hc.streak }) : null].filter(Boolean).join(" · ") : tr("prod-check every interval"),
        state: !hc ? "skipped" : !hc.last ? "todo" : hc.last.ok ? "done" : "failed", need: hneeds, needText: tr("failing"), running: runsAt("prod").length > 0,
        about: tr("A failure opens an expedite issue"), detail: () => healthBlock() },
      { key: "issue", label: "/dev-kit:issue", kind: "human", sub: tr("classifies what happened"), state: n("expedite") + n("standard") + n("change") + n("current") + n("intangible") ? "current" : "todo",
        need: qneeds, needText: tr("queue"), about: tr("A bug, an improvement or a change: Claude Code classifies it (also from the board)"),
        detail: () => [actionsOn() ? h("p", {}, h("button", { type: "button", class: "btn btn-sm btn-primary", text: tr("＋ New issue"), onclick: () => { closeList(); newIssue(); } })) : h("p", {}, cmd("/dev-kit:issue"))] },
      { key: "branch", label: tr("Expedite · standard · change"), kind: "gate", sub: tr("hotfix · next milestone · PRD"), state: "todo", branch: [
        ["expedite", tr("Expedite"), tr("hotfix lane, patch release"), n("expedite")], ["standard", tr("Standard"), tr("the next milestone"), n("standard") + n("current") + n("intangible")],
        ["change", tr("Change"), tr("the PRD, then a replan"), n("change")]] }]));
  }
  /** The last node of Stable branches out like the diagram: three classes of service, each with its queue. */
  function branchNode(n) {
    return h("li", { class: "fnode k-branch" }, h("div", { class: "branch", role: "group", "aria-label": n.label },
      n.branch.map(([k, name, what, count]) => h("button", { type: "button", class: `branch-row b-${k}`, title: what, onclick: () => setPhase(k === "change" ? "conception" : "planning") },
        h("strong", { text: name }), h("span", { class: "branch-what", text: what }), h("span", { class: `branch-n${count ? " on" : ""}`, text: String(count) })))));
  }
  function renderStable() {
    const nodes = stableNodes();
    const p = data.progress, c = data.costs, ms = data.milestones, rel = data.releases || [];
    const closed = ms.filter(isClosed).length;
    const list = flowList(nodes.filter((n) => !n.branch), false, tr("Stable and maintenance"));
    nodes.filter((n) => n.branch).forEach((n) => list.append(branchNode(n)));
    fill($("st-strip"), stripHead("stable", data.phase === "stable" ? tr("Stable: nothing open, everything released") : tr("Not stable yet: the project is in {v}", { v: PHASE_NAME[data.phase] }),
      h("span", { class: `chip lane-chip st-${laneState("stable")}`, text: PHASE_WORD[laneState("stable") === "active" ? "current" : laneState("stable")] || "" })), list,
      flowDetail(runsAt("prod").length || runsAt("checks").length ? runBanner(runsAt("prod").concat(runsAt("checks"))) : null));
    const fact = (label, value, extra) => h("div", { class: "fact" }, h("span", { class: "fact-label", text: label }), h("strong", { class: "fact-value", text: value }), extra || null);
    const summary = h("div", { class: "facts-grid", id: "st-summary" },
      fact(tr("Tasks done"), `${p.done}/${p.total}`),
      fact(tr("Milestones closed"), `${closed}/${ms.length}`),
      fact(tr("Releases"), String(rel.length), rel.length ? h("span", { class: "card-sub", text: tr("last {v}", { v: rel.at(-1).tag || rel.at(-1).version || "" }) }) : null),
      (data.backlog || {}).debt ? fact(tr("Deferred debt"), String(data.backlog.debt.total), h("span", { class: "card-sub", text: debtLine(data.backlog.debt) })) : fact(tr("Deferred debt"), "0"),
      c && (Number(c.usd) > 0 || Number(c.tokens) > 0) ? fact(tr("Cost (estimate)"), tr("US$ {v}", { v: Number(c.usd || 0).toFixed(2) }), h("span", { class: "card-sub", text: tr("{v} tokens", { v: compact(c.tokens || 0) }) }))
        : fact(tr("Cost"), tr("not computed"), h("span", { class: "fact-cmd" }, copyBtn("/dev-kit:costs"))));
    // production
    const pr = data.production, lc = data.lifecycle || {};
    const when = { per_milestone: tr("after each milestone"), per_milestone_flagged: tr("after each milestone, behind the release flag"), on_release: tr("at each release"), manual: tr("by hand"), none: tr("no production environment") };
    let prod;
    if (!pr) prod = [h("div", { class: "empty", text: lc.deploy_when === "none" ? tr("This project has no production deploy.") : tr("No production deploy recorded yet.") }),
      lc.deploy_when && lc.deploy_when !== "none" ? h("p", { class: "pending-line" }, tr("Deploy with "), cmd("/dev-kit:deploy")) : null];
    else {
      const cur = pr.current, last = pr.last;
      prod = [h("ul", { class: "list" },
        cur ? h("li", {}, h("span", { class: "id", text: (cur.sha || "").slice(0, 7) }), h("span", { text: cur.milestone ? tr("Running {milestone}", { milestone: cur.milestone }) : tr("Running") }),
          h("span", { class: "badge good", text: tr("✓ ok") }), h("span", { class: "sub", text: [cur.at && Number.isFinite(parseT(cur.at)) ? fmtDT(parseT(cur.at)) : null, cur.migration ? tr("migration {v}", { v: cur.migration }) : null].filter(Boolean).join(" · ") })) : null,
        last && last.status !== "ok" ? h("li", {}, h("span", { class: "id", text: (last.sha || "").slice(0, 7) }), h("span", { text: tr("Last attempt") }),
          h("span", { class: "badge bad", text: stLabel(last.status) }), h("span", { class: "sub", text: last.at && Number.isFinite(parseT(last.at)) ? fmtDT(parseT(last.at)) : "" })) : null),
      pr.drift ? h("p", { class: "pending-line", text: pr.drift }) : null];
    }
    const others = Object.keys(data.reviews).filter((k) => !OWN_REVIEWS.includes(k));
    const relRows = () => rel.slice().reverse().map((r) => h("li", {},
      hasDoc(`release-notes-${r.version}.md`) ? docLink(`release-notes-${r.version}.md`, r.tag || r.version, null, "id") : h("span", { class: "id", text: r.tag || r.version || "release" }),
      h("span", { text: (r.release ? `${r.release} · ` : "") + (r.hotfix ? tr("Hotfix {hotfix}", { hotfix: r.hotfix }) : (r.milestones || []).join(", ") || "—") }),
      h("span", { class: "chip", text: r.version || "" }), r.at && Number.isFinite(parseT(r.at)) ? h("span", { class: "sub", text: fmtDate(parseT(r.at)) }) : null));
    const fl = data.flags || [];
    fill($("st-tiles"),
      tile({ title: tr("Project"), sub: data.phase === "stable" ? tr("stable") : PHASE_NAME[data.phase], body: summary }),
      tile({ title: tr("Production"), sub: h("span", { id: "st-prod-sub", text: tr("Deploys {v}", { v: when[lc.deploy_when] || lc.deploy_when || "?" }) }), bodyId: "st-prod", body: [runBanner(runsAt("prod")), ...prod], all: () => prod.map((n) => n && n.cloneNode(true)) }),
      tile({ title: tr("Health check"), sub: data.prod_health ? tr("every {n} min · {target}", { n: data.prod_health.interval_min, target: data.prod_health.target }) : "", bodyId: "st-health",
        body: healthBlock() || h("div", { class: "empty", text: tr("No health check: set autonomy.production.health to watch production.") }) }),
      tile({ title: tr("Release flags"), count: fl.length || null, bodyId: "st-flags", body: flagsBlock() || h("div", { class: "empty", text: tr("No release flags.") }), all: () => flagsBlock() }),
      tile({ title: tr("Release checks"), sub: tr("Cut-off: reviews {review_min_overall} · usability {min_overall}", { review_min_overall: data.quality.review_min_overall, min_overall: data.quality.min_overall }),
        body: [runBanner(runsAt("checks")), reviewList(["ux", "docs", ...others], tr("No checks."))], all: () => reviewList(["ux", "docs", ...others], tr("No checks.")) }),
      tile({ title: tr("Releases"), count: rel.length || null, sub: tr("Newest first"),
        body: [runBanner(runsAt("releases")), rel.length ? h("ul", { class: "list" }, relRows()) : h("div", { class: "empty", text: tr("No release yet. Closed milestones wait for the next release.") })], all: () => h("ul", { class: "list" }, relRows()) }));
  }

  /** The production health check (autonomy.production.health): the last result and the short history as dots. */
  function healthBlock() {
    const hc = data.prod_health;
    if (!hc) return null;
    const last = hc.last;
    const dots = h("span", { class: "hc-dots", "aria-hidden": "true" }, (hc.history || []).map((c) =>
      h("span", { class: `hc-dot ${c.ok ? "ok" : "bad"}`, title: `${c.at && Number.isFinite(parseT(c.at)) ? fmtDT(parseT(c.at)) : ""} · ${c.detail || ""}` })));
    return h("div", { class: "hc" },
      h("p", { class: "hc-sr visually-hidden", text: tr("every {n} min · {target}", { n: hc.interval_min, target: hc.target }) }),
      last ? h("p", { class: "hc-last" }, h("span", { class: `badge ${last.ok ? "good" : "bad"}`, text: last.ok ? tr("✓ healthy") : tr("✕ failing") }), " ",
        h("span", { class: "sub", text: [last.at && Number.isFinite(parseT(last.at)) ? fmtDT(parseT(last.at)) : null, last.detail,
          hc.streak > 1 ? tr("{n} in a row", { n: hc.streak }) : null, last.issue ? last.issue : null].filter(Boolean).join(" · ") })) : null,
      last ? h("p", { class: "hc-hist" }, dots) : h("p", { class: "pending-line" }, tr("Not run yet: the board runs it while it is open, or run "), cmd("/dev-kit:deploy --health")));
  }
  /** Release flags (autonomy.release_flags): which release is switched on in production. */
  function flagsBlock() {
    const fl = data.flags || [];
    if (!fl.length) return null;
    const word = tmap({ on: N_("on"), off: N_("off"), removed: N_("removed") });
    return h("ul", { class: "list" }, fl.map((f) => h("li", {}, h("span", { class: "id", text: f.release }), h("span", {}, h("code", { text: f.name })),
      h("span", { class: `badge ${f.state === "on" ? "good" : ""}`, text: word[f.state] || f.state }),
      f.cleanup_task && f.cleanup_task !== "pending" ? h("span", { class: "sub", text: tr("removal: {id}", { id: f.cleanup_task }) }) : null)));
  }

  // ------------------------------------------------------------------ the map: the five lanes of the flow at once, with where the project is
  // ------------------------------------------------------------------ architecture: the diagram of the system being built
  // docs/diagrams/architecture.svg (served by /api/diagram) drawn by /dev-kit:diagram; none yet → the board asks for it once
  const DIAGRAM_NEW = "/dev-kit:diagram", DIAGRAM_UPDATE = "/dev-kit:diagram update";
  let archAsked = false;     // a missing diagram is queued once per page, never again by itself after a failure
  let archZoom = false;
  const diagramBusy = () => [DIAGRAM_NEW, DIAGRAM_UPDATE].map((c) => runningRun(c) || openRun(c)).find(Boolean) || null;
  function renderArch() {
    const d = data.diagram || { exists: false };
    const busy = diagramBusy();
    const busyText = busy ? (busy.started_at && !busy.id ? tr("Claude Code is drawing it now") : tr("Queued ({id})", { id: busy.id || "" })) : "";
    const sub = $("arch-sub");
    if (d.exists) {
      fill(sub, d.at ? tr("High-level view of the system being built, drawn on {v}", { v: fmtDT(d.at) }) : tr("High-level view of the system being built"),
        d.stale || !d.current ? h("span", { class: "stale", text: ` · ${tr("out of date: the architecture changed since")}` }) : null,
        busy ? ` · ${busyText}` : null);
    } else fill(sub, tr("High-level view of the system being built"));
    const upd = h("button", { type: "button", class: `btn btn-sm${d.exists ? "" : " btn-primary"}`, disabled: busy || !actionsOn() ? true : null,
      title: actionsOn() ? tr("Run {text} in Claude Code", { text: d.exists ? DIAGRAM_UPDATE : DIAGRAM_NEW }) : tr("Requests are off on this board: run {text} in Claude Code", { text: d.exists ? DIAGRAM_UPDATE : DIAGRAM_NEW }),
      text: d.exists ? tr("Update diagram") : tr("Create diagram") });
    upd.addEventListener("click", async () => {
      upd.disabled = true;
      try { await queue("run", { command: d.exists ? DIAGRAM_UPDATE : DIAGRAM_NEW }); } catch (e) { upd.disabled = false; }
    });
    const v = encodeURIComponent(d.at || "");
    fill($("arch-actions"), upd,
      d.exists ? h("a", { class: "btn btn-sm", href: `/api/diagram?v=${v}`, target: "_blank", rel: "noopener", text: tr("Open full size") }) : null);
    const view = $("arch-view");
    view.classList.toggle("zoom", archZoom && d.exists);
    view.classList.toggle("has-img", Boolean(d.exists));
    if (d.exists) {
      const img = h("img", { src: `/api/diagram?v=${v}`, alt: tr("Architecture diagram of the system being built"), title: tr("Click to zoom") });
      img.addEventListener("click", () => { archZoom = !archZoom; view.classList.toggle("zoom", archZoom); });
      fill(view, img);
      return;
    }
    if (!busy && !archAsked && actionsOn()) {
      archAsked = true;
      queue("run", { command: DIAGRAM_NEW }).catch(() => {});
    }
    fill(view, h("div", { class: "empty" },
      busy || archAsked && actionsOn() ? tr("No diagram yet: Claude Code is drawing it with /dev-kit:diagram. It shows here when it is done.")
        : actionsOn() ? tr("No diagram yet. Create it to see the architecture here.")
          : tr("No diagram yet. Run /dev-kit:diagram in Claude Code to draw it.")));
  }

  function renderMap() {
    const m = data.milestones.find((x) => x.id === data.current_milestone) || currentMilestone();
    const r = relPick();
    const lane = (k, nodes, right) => {
      const st = laneState(k);
      const here = k === data.phase || (k === "releases" && st === "current");
      const list = flowList(nodes.filter((n) => !n.branch), true, LANE_NAME[k]);
      nodes.filter((n) => n.branch).forEach((n) => list.append(branchNode(n)));
      return h("section", { class: `map-lane lane-${k} st-${st}${here ? " here" : ""}`, "aria-label": LANE_NAME[k] },
        h("button", { type: "button", class: "map-lane-head", onclick: () => setPhase(k) },
          h("span", { class: "strip-num", text: LANE_NUM[k] }), h("span", { class: "map-lane-name", text: LANE_NAME[k] }), h("span", { class: "map-lane-tip", text: LANE_TIP[k] })),
        list,
        h("div", { class: "map-lane-side" }, here ? h("span", { class: "map-here", text: tr("you are here") }) : null, h("strong", { text: laneStatus(k) }), right ? h("span", { class: "sub", text: right }) : null,
          h("button", { type: "button", class: "link-btn map-open", text: tr("Open →"), onclick: () => setPhase(k) })));
    };
    const fc = m && fcFor("milestones", "milestone", m.id);
    fill($("map-lanes"),
      lane("conception", concNodes(), tr("{v} documents", { v: ["interview", "prd", "architecture", "ux", "ui"].reduce((n, k) => n + ((data.artifacts || {})[k] || []).length, 0) })),
      lane("planning", planNodes(), tr("{r} releases · {m} milestones", { r: relPlan().length, m: data.milestones.length })),
      lane("construction", m ? msNodes(m) : [], m ? `${m.title || ""}${fc ? ` · ${forecastText(fc)}` : ""}` : ""),
      lane("releases", r ? relNodes(r) : [], r ? `${r.id} · ${REL_WORD[r.status]}` : ""),
      lane("stable", stableNodes(), ""));
    const ib = inbox();
    const [, word] = execLabel(ib.executor);
    const c = data.costs;
    fill($("map-any"), h("strong", { class: "any-title", text: tr("Anytime") }),
      h("button", { type: "button", class: "link-btn", onclick: goNeeds }, tr("Needs you: {n}", { n: needsN })),
      h("button", { type: "button", class: "link-btn", onclick: () => openDrawer(rdlg) }, tr("Requests: {n}", { n: ib.open.length })),
      h("span", { class: "sub", text: word }),
      c && Number(c.usd) > 0 ? h("span", { class: "sub", text: tr("Cost so far: US$ {v}", { v: Number(c.usd).toFixed(2) }) }) : null,
      h("span", { class: "any-sp" }),
      actionsOn() ? h("button", { type: "button", class: "btn btn-sm", text: tr("＋ New issue"), onclick: newIssue }) : null,
      h("button", { type: "button", class: "btn btn-sm", text: tr("Activity"), onclick: () => openDrawer(adlg) }));
  }

  function tickAgents() {
    document.querySelectorAll(".agent-time[data-start]").forEach((el) => { el.textContent = dur((Date.now() - parseT(el.dataset.start)) / 1000); });
  }
  setInterval(tickAgents, 1000);

  // ------------------------------------------------------------------ requests to Claude Code (dev_worker.py on the server, /dev-kit:worker runs them)
  // the commands the server accepts (dev_worker.RUN_COMMANDS); anything else keeps only its copy button
  const RUN_RES = [/^\/dev-kit:implement(?: (?:T-\d{3,5}|--milestone M\d{1,3}(?:\.\d{1,2})?))?$/, /^\/dev-kit:qa M\d{1,3}(?:\.\d{1,2})?$/, /^\/dev-kit:review (?:prd|design|plan|docs)$/,
    /^\/dev-kit:(?:interview|prd|architecture|ux|ui|plan|docs|usability|costs|backlog|status|release)$/, /^\/dev-kit:interview --gaps$/, /^\/dev-kit:deploy(?: M\d{1,3}(?:\.\d{1,2})?)?$/,
    /^\/dev-kit:diagram(?: update)?$/];
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
      const err = new Error((d.errors && d.errors.join("; ")) || d.hint || d.error || tr("HTTP {status}", { status: r.status }));
      err.errors = d.errors || [err.message];
      throw err;
    }
    return d;
  }
  // the board starts Claude Code by itself when a request waits (unless it is off, or no claude command is installed)
  const autoOn = (ex) => Boolean(ex.auto && !["off", "no_claude"].includes(ex.auto.state));
  const takesIt = (ex) => Boolean(ex.listening || (ex.online && ex.state === "running") || autoOn(ex));
  const workerHint = () => (takesIt(inbox().executor) ? tr("Claude Code takes it.")
    : (inbox().executor.auto || {}).state === "no_claude" ? tr("The claude command was not found: install Claude Code, or run /dev-kit:worker in a session.")
    : tr("Run /dev-kit:worker in Claude Code to start it."));
  async function queue(action, args, quietErrors) {
    try {
      const d = await api("/api/inbox", { action, args });
      toast(tr("Queued {id}. {v}", { id: d.item.id, v: workerHint() }));
      load();
      return d.item;
    } catch (e) {
      if (!quietErrors) toast(tr("Not queued: {message}", { message: e.message }), true);
      throw e;
    }
  }
  function runBtn(text, labelled) {
    const q = openRun(text), live = runningRun(text);
    const busy = live ? tr("Running for {v}", { v: dur((Date.now() - parseT(live.started_at)) / 1000) }) : q ? tr("Queued ({id})", { id: q.id }) : null;
    const label = busy ? `${text}: ${busy}` : tr("Run {text} in Claude Code", { text });
    const btn = h("button", { type: "button", class: `run-btn${busy ? " queued" : ""}${labelled ? " labelled" : ""}`, title: label, "aria-label": labelled ? `${actionLabel(text)}: ${label}` : label,
      disabled: busy ? true : null, "data-cmd": text }, busy ? "◷" : "▶", labelled ? h("span", { class: "run-label", text: busy ? `${actionLabel(text)} · ${busy}` : actionLabel(text) }) : null);
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
    if (x.action === "issue_new") return tr("New {v}: {v2}", { v: a.type === "improvement" ? "improvement" : a.type === "change" ? "change" : "bug", v2: a.title || "" });
    if (x.action === "answer_question") return tr("Answer to {question}: {v}", { question: a.question, v: a.option || a.answer || "" });
    if (x.action === "plan_draft") return tr("Plan draft · {v}", { v: plural((a.ops || []).length, "change") });
    if (x.action === "release_decision") return `${a.decision === "approve" ? tr("Approve") : tr("Reject")} ${a.release}`;
    if (x.action === "checkpoint") return `${a.decision === "confirm" ? tr("Confirm") : tr("Ask for changes in")} ${a.target === "prd" ? tr("the PRD") : tr("the plan")}`;
    if (x.action === "debt_decision") return tr("Deferred debt: {decision}", { decision: a.decision });
    if (x.action === "lesson_decision") return tr("Lesson for {agent}: {decision}", { agent: a.agent, decision: a.decision });
    if (x.action === "qa_decision") return tr("QA of {milestone}: {decision}{v}", { milestone: a.milestone, decision: a.decision, v: a.rounds ? ` (+${a.rounds})` : "" });
    if (x.action === "task_decision") return `${a.task}: ${a.decision}`;
    return x.action;
  }
  const REQ_WORD = tmap({ pending: N_("waiting"), running: N_("running"), needs_input: N_("needs your answer"), done: N_("done"), failed: N_("failed"), cancelled: N_("cancelled"), stale: N_("stopped") });
  function execLabel(ex) {
    const runs = skillRuns();
    const au = ex.auto || {};
    if (au.state === "running") return ["on", tr("Claude Code: started by the board{v}", { v: au.request ? ` (${au.request})` : "" })];
    if (au.state === "waiting") return ["paused", tr("Claude Code: the last run failed ({reason}); it tries again soon", { reason: au.reason || "?" })];
    if (!ex.online && !runs.length) return ["off", tr("Claude Code: not running")];
    if (ex.paused) return ["paused", tr("Claude Code: paused")];
    if (ex.state === "running") return ["on", tr("Claude Code: working{v}", { v: ex.item ? ` on ${ex.item}` : "" })];
    if (ex.listening) return ["on", tr("Claude Code: listening")];

    if (runs.length) return ["on", tr("Claude Code: running {v}; requests wait for it", { v: runCmd(runs[runs.length - 1]) })];
    return ["idle", tr("Claude Code: open, not listening")];
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
    pb.textContent = ib.executor.paused ? tr("Resume queue") : tr("Pause queue");
    const waiting = ib.open.filter((x) => x.status === "pending").length;
    const line = (...kids) => h("span", { class: "hint-line" }, kids);
    fill($("req-hint"),
      !ib.actions ? line(tr("This board only shows the project: requests are off (start it with --actions on).")) : null,
      ib.actions && !takesIt(ib.executor) && waiting && (ib.executor.auto || {}).state === "no_claude" ? h("span", { class: "hint-line bad" }, workerHint()) : null,
      ib.actions && !takesIt(ib.executor) && waiting && (ib.executor.auto || {}).state !== "no_claude" ? line(tr("{v} waiting. In Claude Code, run ", { v: plural(waiting, "request") }), h("span", { class: "cmd" }, h("code", { text: "/dev-kit:worker" }), copyBtn("/dev-kit:worker"))) : null,
      ib.actions && !ib.executor.online && !waiting && !autoOn(ib.executor) ? line(tr("No Claude Code session is listening. Run "), h("span", { class: "cmd" }, h("code", { text: "/dev-kit:board" }), copyBtn("/dev-kit:board")), tr(" in one: requests then start by themselves.")) : null,
      ib.actions && ib.executor.paused ? line(tr("Paused: Claude Code finishes what it is doing and takes nothing new.")) : null,
      ib.actions && !ib.open.length && !ib.recent.length ? line(tr("Nothing queued. Use ▶ next to a command, answer a question, add an issue, or plan by dragging cards.")) : null);
    const row = (x, open) => h("li", { class: `req s-${x.status}` },
      h("span", { class: "id", text: x.id }),
      h("span", { class: "req-what" }, describeReq(x)),
      h("span", { class: `chip req-st s-${x.status}`, text: x.cancel_requested ? "cancelling" : REQ_WORD[x.status] || x.status }),
      x.note ? h("span", { class: "sub", text: x.note }) : null,
      x.status === "needs_input" ? h("button", { type: "button", class: "link-btn sub", text: tr("Answer {v} in Needs you", { v: x.question || tr("the question") }), onclick: goNeeds }) : null,
      open && ib.actions && !x.cancel_requested ? h("button", { type: "button", class: "link-btn req-cancel", "aria-label": tr("Cancel {id}", { id: x.id }), text: tr("Cancel"),
        onclick: async (e) => { e.currentTarget.disabled = true; try { await api(`/api/inbox/${x.id}/cancel`, {}); toast(`${x.id}: ${x.status === "running" ? tr("Claude Code stops at the next safe point") : "cancelled"}.`); load(); } catch (err) { toast(err.message, true); } } }) : null);
    fill($("req-list"), ib.open.map((x) => row(x, true)), ib.recent.slice(0, 6).map((x) => row(x, false)));
    const rc = $("req-count");
    rc.hidden = !ib.open.length;
    rc.textContent = String(ib.open.length);
  }
  $("pause-btn").addEventListener("click", async () => {
    const paused = !inbox().executor.paused;
    try { await api("/api/worker/mode", { paused }); toast(paused ? tr("Queue paused.") : tr("Queue resumed.")); load(); } catch (e) { toast(e.message, true); }
  });

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
    document.title = n ? tr("({n}) Needs you · {project}", { n, project: data.project }) : tr("{project} · dev-kit board", { project: data.project });
    const icon = document.querySelector('link[rel="icon"]');
    const want = n ? "/assets/favicon-alert.svg" : "/assets/favicon.svg";
    if (icon && icon.getAttribute("href") !== want) icon.setAttribute("href", want);
  }
  document.addEventListener("visibilitychange", updateAttention);
  window.addEventListener("focus", updateAttention);

  // new issue: a short form; Claude Code classifies it and asks here when it needs to
  const idlg = $("issue-dialog");
  const newIssue = () => { $("issue-form").reset(); idlg.showModal(); };
  $("new-issue-btn").addEventListener("click", newIssue);
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
    if (sent) return h("div", { class: "sub answer-sent", text: tr("Answer sent ({id}): {v}. Claude Code applies it.", { id: sent.id, v: sent.args.option || sent.args.answer }) });
    const opts = (q.options || []).slice().sort((a, b) => (b === q.recommended) - (a === q.recommended));
    const box = h("div", { class: "sub answer", role: "group", "aria-label": tr("Answer {id}", { id: q.id }) });
    const send = async (args, el) => { el.disabled = true; try { await queue("answer_question", { question: q.id, ...args }); delete answerDrafts[q.id]; } catch (e) { el.disabled = false; } };
    opts.forEach((o) => box.append(h("button", { type: "button", class: `btn btn-sm${o === q.recommended ? " btn-primary" : ""}`, onclick: (e) => send({ option: o }, e.currentTarget) },
      o, o === q.recommended ? h("span", { class: "rec", text: tr("recommended") }) : null)));
    if (!opts.length && q.assumption) box.append(h("button", { type: "button", class: "btn btn-sm btn-primary", onclick: (e) => send({ answer: q.assumption }, e.currentTarget) }, tr("Keep the assumption")));
    const inp = h("input", { type: "text", id: `ans-${q.id}`, maxlength: "2000", class: "answer-input", "aria-label": tr("Your answer to {id}", { id: q.id }),
      placeholder: opts.length || q.assumption ? tr("Or write another answer") : tr("Your answer") });
    inp.value = answerDrafts[q.id] || "";
    inp.addEventListener("input", () => { answerDrafts[q.id] = inp.value; });
    const go = h("button", { type: "button", class: "btn btn-sm", id: `ans-send-${q.id}`, text: tr("Send"),
      onclick: (e) => { const v = inp.value.trim(); if (v) send({ answer: v }, e.currentTarget); else inp.focus(); } });
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); go.click(); } });
    box.append(h("span", { class: "answer-free" }, inp, go));
    return box;
  }
  const DECIDED = tmap({ allow: N_("Allowed"), allow_session: N_("Allowed for this session"), deny: N_("Denied") });
  const leftText = (ms) => (ms <= 0 ? tr("No answer in time: denied.") : ms < 60000 ? tr("Denied in {v} s without an answer.", { v: Math.ceil(ms / 1000) }) : tr("Denied in {v} min without an answer.", { v: Math.ceil(ms / 60000) }));
  function approvalRow(a) {
    const deadline = lastUpdate + (a.seconds_left || 0) * 1000;
    const decide = async (decision, el) => {
      el.disabled = true;
      try { await api(`/api/approvals/${a.id}`, { decision }); toast(`${DECIDED[decision]}: ${a.tool}.`); load(); } catch (e) { el.disabled = false; toast(e.message, true); load(); }
    };
    return h("li", {}, h("span", { class: "id", text: a.tool || "tool" }), h("span", { class: "mono-wrap", text: a.target || "" }),
      h("span", { class: "chip", text: a.request || "" }),
      h("div", { class: "sub answer", role: "group", "aria-label": tr("Permission for {tool}", { tool: a.tool }) },
        h("button", { type: "button", class: "btn btn-sm btn-primary", text: tr("Allow"), onclick: (e) => decide("allow", e.currentTarget) }),
        a.rule ? h("button", { type: "button", class: "btn btn-sm", title: tr("Until the Claude Code session ends, without asking again: {rule}", { rule: a.rule }),
          onclick: (e) => decide("allow_session", e.currentTarget) }, tr("Allow for this session")) : null,
        h("button", { type: "button", class: "btn btn-sm btn-danger", text: tr("Deny"), onclick: (e) => decide("deny", e.currentTarget) })),
      a.rule ? h("span", { class: "sub" }, tr("For this session it would allow: "), h("code", { text: a.rule })) : null,
      h("span", { class: "sub approval-left", "data-deadline": String(deadline), text: leftText(deadline - Date.now()) }));
  }
  setInterval(() => document.querySelectorAll(".approval-left[data-deadline]").forEach((el) => { el.textContent = leftText(Number(el.dataset.deadline) - Date.now()); }), 1000);

  // ------------------------------------------------------------------ plan: drag tasks and issues between open milestones, add the next milestone, send the draft
  let draft = { ops: [], base: null, serverErrors: [], buffer: false, frozen: false };
  /** A milestone whose QA began: its scope is frozen; adding to it needs a confirmation (conventions §15). */
  const isFrozen = (mid) => Boolean(((data.milestones || []).find((m) => m.id === mid) || {}).frozen_at);
  const FROZEN_COST = (mid) => tr("This item enters the next QA round of {mid} and invalidates the audit of the files it touches.", { mid });
  const MS_NUM = (id) => { const m = /^M(\d+)(?:\.(\d+))?$/.exec(String(id)); return m ? Number(m[1]) + Number(m[2] || 0) / 100 : 1e6; };
  const REL_OPS = ["move_milestone", "new_release", "drop_release"];
  const RELEASE_SIZE = [2, 5];  // milestones per release (conventions.md §4); dev_state.py checks it again
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
      const at = tr("Change {v}", { v: n + 1 });
      if (REL_OPS.includes(op.op)) return;  // release changes are replayed by relModel
      if (op.op === "new_milestone") { ms.push({ id: op.milestone, title: op.title, isNew: true }); cols[op.milestone] = []; return; }
      if (!cols[op.milestone]) { problems.push(tr("{at}: {milestone} is no longer open", { at, milestone: op.milestone })); return; }
      const id = op.op === "move_task" ? op.task : op.issue;
      if (op.op === "move_task" && !movableTask(data.tasks[id])) { problems.push(tr("{at}: {id} is {v} now; undo this change", { at, id, v: stLabel((data.tasks[id] || {}).status || "gone") })); return; }
      if (op.op === "schedule_issue" && !movableIssue(issueOf(id))) { problems.push(tr("{at}: {id} is not open any more; undo this change", { at, id })); return; }
      const card = take(id);
      if (card) put(card, op.milestone, op.before);
    });
    // a task never sits in an earlier milestone than a task it depends on (done ones do not count)
    Object.entries(cols).forEach(([m, l]) => l.forEach((c) => {
      if (c.kind !== "task") return;
      (data.tasks[c.id].deps || []).forEach((d) => {
        const dt = data.tasks[d];
        if (dt && dt.status !== "done" && where[d] && where[d] !== "queue" && MS_NUM(where[d]) > MS_NUM(m)) problems.push(tr("{id} depends on {d}, which would be in a later milestone ({v})", { id: c.id, d, v: where[d] }));
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
    toast(tr("{id} → {m}{v}. Send the draft when it is ready.", { id: card.id, m, v: before ? tr(" (before {before})", { before }) : "" }));
  }
  function describeOp(op) {
    if (op.op === "new_milestone") return tr("New milestone {milestone} · {title}", { milestone: op.milestone, title: op.title });
    if (op.op === "move_milestone") return `${op.milestone} → ${op.release}`;
    if (op.op === "new_release") return tr("New release {release}{v}", { release: op.release, v: op.title ? ` · ${op.title}` : "" });
    if (op.op === "drop_release") return tr("Remove release {release}", { release: op.release });
    if (op.op === "move_task") return `${op.task} → ${op.milestone}${op.before ? tr(" (before {before})", { before: op.before }) : ""}`;
    if (op.op === "schedule_issue") return `${op.issue} → ${op.milestone}${op.before ? tr(" (before {before})", { before: op.before }) : ""}${op.force ? tr(" · over the buffer") : ""}${op.confirm_frozen ? tr(" · confirmed after the freeze") : ""}`;
    if (op.op === "set_issue_status") return `${op.issue} → ${op.status}`;
    return op.op;
  }
  let dragging = null;
  function planCard(c, model, m) {
    const isTask = c.kind === "task";
    const x = isTask ? data.tasks[c.id] : issueOf(c.id);
    if (!x) return null;
    const movable = isTask ? movableTask(x) : movableIssue(x);
    const targets = model.ms.map((t) => t.id);
    const sel = movable ? h("select", { class: "move-sel", "aria-label": tr("Move {id}", { id: c.id }), id: `mv-${c.id}` },
      h("option", { value: "", text: tr("Move…") }),
      isTask && m ? [h("option", { value: "up", text: tr("↑ Up") }), h("option", { value: "down", text: tr("↓ Down") })] : null,
      targets.filter((t) => t !== m).map((t) => h("option", { value: `to:${t}`, text: tr("To {t}", { t }) }))) : null;
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
      title: movable ? tr("Drag to another place, or use Move…") : isTask ? tr("{v}: only tasks not started move", { v: stLabel(x.status) }) : tr("{class}: goes through /dev-kit:issue", { class: x.class }) },
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
        if (i >= 0) { draft.ops.splice(i, 1); renderPlan(); toast(tr("{id} back in the queue.", { id: card.id })); }
        return;
      }
      moveCard(card, m, t ? t.dataset.id : null, model);
    });
  }
  // ---- plan, releases mode: drag whole milestones between the planned releases (R1, R2, ...) of plan.md
  let planMode = "tasks";
  let newRelTitle = "";
  const msTasks = (id) => Object.values(data.tasks).filter((t) => t.milestone === id && t.status !== "dropped");
  /** The planned releases as the draft leaves them: each with its milestones in number order, and the problems found. */
  function relModel() {
    const rels = relPlan().map((r) => ({ id: r.id, title: r.title, status: r.status, ms: r.milestones.slice().sort((a, b) => MS_NUM(a) - MS_NUM(b)), isNew: false }));
    const touched = new Set();
    const problems = [];
    draft.ops.filter((o) => REL_OPS.includes(o.op)).forEach((op, n) => {
      if (op.op === "new_release") { rels.push({ id: op.release, title: op.title || "", status: "in_progress", ms: [], isNew: true }); touched.add(op.release); return; }
      if (op.op === "drop_release") { const i = rels.findIndex((r) => r.id === op.release); if (i >= 0) rels.splice(i, 1); touched.delete(op.release); return; }
      const from = rels.find((r) => r.ms.includes(op.milestone)), to = rels.find((r) => r.id === op.release);
      const m = data.milestones.find((x) => x.id === op.milestone);
      if (!from || !to || !m || m.gate !== "pending" || from.status !== "in_progress" || to.status !== "in_progress") {
        problems.push(tr("{milestone} → {release} no longer fits the plan; undo this change", { milestone: op.milestone, release: op.release }));
        return;
      }
      from.ms.splice(from.ms.indexOf(op.milestone), 1);
      to.ms.push(op.milestone);
      to.ms.sort((a, b) => MS_NUM(a) - MS_NUM(b));
      touched.add(from.id); touched.add(to.id);
    });
    rels.filter((r) => touched.has(r.id) && (r.ms.length < RELEASE_SIZE[0] || r.ms.length > RELEASE_SIZE[1]))
      .forEach((r) => problems.push(tr("{id} would hold {v}; a release holds {v2} to {v3}", { id: r.id, v: plural(r.ms.length, "milestone"), v2: RELEASE_SIZE[0], v3: RELEASE_SIZE[1] })));
    return { rels, problems };
  }
  const relLocked = (r) => r.status !== "in_progress";
  function msCard(mid, rel, model) {
    const m = data.milestones.find((x) => x.id === mid);
    if (!m) return null;
    const ts = msTasks(mid);
    const running = ts.some((t) => t.status === "in_progress");
    const movable = m.gate === "pending" && !relLocked(rel) && !running;
    const why = m.gate !== "pending" ? tr("its gate is {gate}", { gate: m.gate }) : relLocked(rel) ? `${rel.id} is ${REL_WORD[rel.status] || rel.status}` : running ? tr("a task is running") : "";
    const targets = model.rels.filter((r) => r.id !== rel.id && !relLocked(r));
    const sel = movable && targets.length ? h("select", { class: "move-sel", "aria-label": tr("Move {mid} to another release", { mid }), id: `mv-${mid}` },
      h("option", { value: "", text: tr("Move…") }), targets.map((r) => h("option", { value: r.id, text: tr("To {id}", { id: r.id }) }))) : null;
    if (sel) sel.addEventListener("change", () => {
      const v = sel.value;
      sel.value = "";
      if (v) { addOp({ op: "move_milestone", milestone: mid, release: v }); toast(tr("{mid} → {v}. Send the draft when it is ready.", { mid, v })); }
      requestAnimationFrame(() => { const el = $(`mv-${mid}`); if (el) el.focus(); });
    });
    const el = h("li", { class: `pcard${movable ? " movable" : " locked"}${m.gate === "pending" ? "" : " s-done"}`, "data-id": mid, draggable: movable ? "true" : null,
      title: movable ? tr("Drag to another release, or use Move…") : tr("Stays here: {why}", { why }) },
      h("div", { class: "tcard-top" }, h("span", { class: "tid", text: mid }),
        h("span", { class: "chip", text: m.gate === "pending" ? plural(ts.length, "task") : tr("gate {v}", { v: m.gate }) }),
        msTook(m) ? h("span", { class: "took", title: msTook(m).title, text: tr("took {v}", { v: msTook(m).text }) }) : null),
      h("div", { class: "tcard-title", text: m.title || mid, title: m.title || null }), sel);
    if (movable) {
      el.addEventListener("dragstart", (e) => { dragging = { kind: "ms", id: mid, from: rel.id }; e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", mid); el.classList.add("dragging"); });
      el.addEventListener("dragend", () => { dragging = null; el.classList.remove("dragging"); });
    }
    return el;
  }
  function relDropZone(list, rel) {
    if (relLocked(rel)) return;
    const ok = () => dragging && dragging.kind === "ms" && dragging.from !== rel.id;
    list.addEventListener("dragover", (e) => { if (!ok()) return; e.preventDefault(); list.classList.add("drop-on"); });
    list.addEventListener("dragleave", (e) => { if (!list.contains(e.relatedTarget)) list.classList.remove("drop-on"); });
    list.addEventListener("drop", (e) => {
      e.preventDefault();
      list.classList.remove("drop-on");
      if (!ok()) return;
      const card = dragging;
      dragging = null;
      addOp({ op: "move_milestone", milestone: card.id, release: rel.id });
      toast(tr("{id} → {id2}. Send the draft when it is ready.", { id: card.id, id2: rel.id }));
    });
  }
  /** The lanes of releases mode, and the one to create the next release. */
  function relColumns() {
    const model = relModel();
    const lanes = model.rels.map((r) => {
      const list = h("ol", { class: "pcol-list", "data-key": `rel-${r.id}`, "aria-label": `${r.id} ${r.title}, ${plural(r.ms.length, "milestone")}` }, r.ms.map((m) => msCard(m, r, model)).filter(Boolean));
      if (!r.ms.length) list.append(h("li", { class: "col-empty", text: relLocked(r) ? "—" : tr("Drop milestones here") }));
      relDropZone(list, r);
      const canDrop = !relLocked(r) && !r.ms.length;
      return h("section", { class: `pcol rel${r.isNew ? " new" : ""}${relLocked(r) ? " locked" : ""}`, "aria-label": `${r.id} ${r.title}` },
        h("div", { class: "col-head" }, h("strong", { text: r.id }), r.title && r.title !== r.id ? h("span", { class: "pcol-title", text: r.title, title: r.title }) : null,
          h("span", { class: "count", text: String(r.ms.length) })),
        h("p", { class: "card-sub", text: r.isNew ? tr("New in this draft") : REL_WORD[r.status] || r.status }), list,
        canDrop ? h("button", { type: "button", class: "link-btn", text: tr("Remove {id}", { id: r.id }), onclick: () => addOp({ op: "drop_release", release: r.id }) }) : null);
    });
    const next = `R${Math.max(0, ...model.rels.map((r) => Number(r.id.slice(1)))) + 1}`;
    const inp = h("input", { type: "text", id: "new-rel-title", maxlength: "80", placeholder: tr("Title of {next} (optional)", { next }), "aria-label": tr("Title of the new release {next}", { next }) });
    inp.value = newRelTitle;
    inp.addEventListener("input", () => { newRelTitle = inp.value; });
    const add = () => { const v = inp.value.trim(); newRelTitle = ""; addOp({ op: "new_release", release: next, ...(v ? { title: v } : {}) }); toast(tr("{next} added to the draft: drag its milestones in.", { next })); };
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } });
    lanes.push(h("section", { class: "pcol add" }, h("div", { class: "col-head" }, h("strong", { text: `＋ ${next}` })),
      h("p", { class: "card-sub", text: tr("The next release, after the others. Create it, then drag milestones into it. A release holds 2 to 5 milestones.") }),
      h("div", { class: "answer-free" }, inp, h("button", { type: "button", class: "btn btn-sm", text: tr("Add"), onclick: add }))));
    return { cols: lanes, problems: model.problems };
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
      if (!open.length) list.append(h("li", { class: "col-empty", text: key === "queue" ? tr("No open issue") : tr("Drop tasks or issues here") }));
      dropZone(list, key, model);
      let folded = null;
      if (done.length) {
        folded = h("details", { class: "pcol-done" }, h("summary", { text: tr("{v} done", { v: plural(done.length, "task") }) }),
          h("ol", { class: "pcol-list done-list", "aria-label": tr("{title}, done tasks", { title }) }, done.map((c) => planCard(c, model, key)).filter(Boolean)));
        folded.open = doneOpen.has(key);
        folded.addEventListener("toggle", () => { if (folded.open) doneOpen.add(key); else doneOpen.delete(key); });
      }
      return h("section", { class: `pcol${key === "queue" ? " queue" : ""}${isNew ? " new" : ""}`, "aria-label": key === "queue" ? tr("Issue queue") : `${key} ${title}` },
        h("div", { class: "col-head" }, h("strong", { text: key === "queue" ? tr("Issue queue") : key }), key === "queue" || title === key ? null : h("span", { class: "pcol-title", text: title, title }),
          h("span", { class: "count", title: done.length ? tr("{open_n} open, {done_n} done", { open_n: open.length, done_n: done.length }) : null, text: !done.length ? String(open.length) : open.length ? `${open.length} · ${done.length} ✓` : `${done.length} ✓` })),
        sub ? h("p", { class: "card-sub", text: sub }) : null, list, folded, extra);
    };
    const newNum = `M${Math.floor(Math.max(0, ...data.milestones.map((m) => MS_NUM(m.id)), ...draft.ops.filter((o) => o.op === "new_milestone").map((o) => MS_NUM(o.milestone)))) + 1}`;
    const hasNew = draft.ops.some((o) => o.op === "new_milestone");
    const b = (data.backlog || {}).buffer;
    const hasRels = relPlan().length > 0;
    if (!hasRels) planMode = "tasks";
    const rm = planMode === "releases" ? relColumns() : null;
    const cols = rm ? rm.cols : [column("queue", tr("Issue queue"), tr("Expedite and change issues go through /dev-kit:issue."), model.queued)]
      .concat(model.ms.slice().map((m) => column(m.id, m.title || m.id, m.isNew ? tr("New in this draft") : isFrozen(m.id) ? tr("🔒 Frozen for QA — adding needs your confirmation") : b && b.milestone === m.id ? bufferText(b) : null, model.cols[m.id] || [], null, m.isNew)));
    if (!hasNew && !rm) {
      const inp = h("input", { type: "text", id: "new-ms-title", maxlength: "80", placeholder: tr("Title of {newNum}", { newNum }), "aria-label": tr("Title of the new milestone {newNum}", { newNum }) });
      inp.value = newMsTitle;
      inp.addEventListener("input", () => { newMsTitle = inp.value; });
      const add = () => { const v = inp.value.trim(); if (!v) { inp.focus(); return; } newMsTitle = ""; addOp({ op: "new_milestone", milestone: newNum, title: v }); toast(tr("{newNum} added to the draft.", { newNum })); };
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } });
      cols.push(h("section", { class: "pcol add" }, h("div", { class: "col-head" }, h("strong", { text: `＋ ${newNum}` })),
        h("p", { class: "card-sub", text: tr("The next milestone, after the others. Name it, then drag cards into it.") }),
        h("div", { class: "answer-free" }, inp, h("button", { type: "button", class: "btn btn-sm", text: tr("Add"), onclick: add }))));
    }
    const errors = model.problems.concat(relModel().problems, draft.serverErrors);
    const modeBar = hasRels ? h("div", { class: "plan-mode", role: "group", "aria-label": tr("What to plan") },
      [["tasks", tr("Tasks and issues")], ["releases", tr("Releases")]].map(([k, label]) => h("button", { type: "button", class: "btn btn-sm", "aria-pressed": String(planMode === k), text: label,
        onclick: () => { planMode = k; renderPlan(); } }))) : null;
    const sendBtn = h("button", { type: "button", class: "btn btn-primary", id: "plan-send", disabled: !draft.ops.length || errors.some((x) => !draft.serverErrors.includes(x)) ? true : null, text: tr("Send to Claude Code"),
      onclick: async (e) => {
        e.currentTarget.disabled = true;
        const ops = draft.ops.map((o) => (o.op === "schedule_issue" && draft.buffer ? { ...o, force: true } : o))
          .map((o) => (draft.frozen && (o.op === "schedule_issue" || o.op === "move_task") && isFrozen(o.milestone) ? { ...o, confirm_frozen: true } : o));
        try {
          await queue("plan_draft", { ops, base: draft.base || data.updated_at }, true);
          draft = { ops: [], base: null, serverErrors: [], buffer: false, frozen: false };
          renderPlan();
        } catch (err) {
          draft.serverErrors = err.errors || [err.message];
          renderPlan();
        }
      } });
    const overBuffer = draft.serverErrors.some((x) => /issue buffer/.test(x));
    const frozenHit = draft.serverErrors.find((x) => /is frozen since its QA began/.test(x));
    const frozenM = frozenHit ? (/(M\d+(?:\.\d+)?) is frozen/.exec(frozenHit) || [])[1] : null;
    fill(box, modeBar,
      h("div", { class: "plan-cols" }, cols),
      h("aside", { class: "plan-draft", "aria-label": tr("Draft of the plan") },
        h("div", { class: "list-title" }, tr("Draft"), draft.ops.length ? h("span", { class: "chip", text: String(draft.ops.length) }) : null),
        draft.ops.length ? h("ol", { class: "td-list" }, draft.ops.map((o) => h("li", { text: describeOp(o) })))
          : h("p", { class: "card-sub", text: tr("Drag tasks not started and open issues between open milestones, or milestones between releases, or use Move… on a card. Nothing changes until you send the draft; Claude Code applies it with /dev-kit:worker.") }),
        errors.length ? h("ul", { class: "td-list plan-errors", role: "alert" }, errors.map((x) => h("li", { text: x }))) : null,
        overBuffer ? h("button", { type: "button", class: "link-btn", text: tr("Go over the issue buffer and send again"), onclick: () => { draft.buffer = true; draft.serverErrors = []; renderPlan(); $("plan-send").click(); } }) : null,
        frozenM ? h("p", { class: "card-sub bad", text: FROZEN_COST(frozenM) }) : null,
        frozenM ? h("button", { type: "button", class: "link-btn", text: tr("Confirm adding to {frozenM} and send again", { frozenM }), onclick: () => { draft.frozen = true; draft.serverErrors = []; renderPlan(); $("plan-send").click(); } }) : null,
        h("div", { class: "plan-actions" },
          h("button", { type: "button", class: "btn", disabled: !draft.ops.length ? true : null, text: tr("Undo"), onclick: () => { draft.ops.pop(); draft.serverErrors = []; renderPlan(); } }),
          h("button", { type: "button", class: "btn", disabled: !draft.ops.length ? true : null, text: tr("Discard"), onclick: () => { draft = { ops: [], base: null, serverErrors: [], buffer: false, frozen: false }; renderPlan(); } }),
          sendBtn)));
    box.querySelector(".plan-cols").scrollLeft = scrollX;
    box.querySelectorAll(".pcol-list[data-key]").forEach((l) => { if (scrollY[l.dataset.key]) l.scrollTop = scrollY[l.dataset.key]; });
  }
  /** The plan view (drag, draft, send) has a screen of its own, opened from Planning while the board takes requests. */
  const planShown = () => actionsOn() && replanOpen && shownPhase() === "planning";
  /** Tabs and panels of the construction view: the task board or the QA of the milestone. */
  function applyView() {
    if (!VIEWS.includes(view)) view = "tasks";
    document.querySelectorAll("#view-switch [role=tab]").forEach((b) => {
      const on = b.dataset.view === view;
      b.setAttribute("aria-selected", String(on));
      b.tabIndex = on ? 0 : -1;
    });
    $("view-tasks").hidden = view !== "tasks";
    $("view-qa").hidden = view !== "qa";
    $("board-card").dataset.view = view;
    $("board-h").textContent = view === "qa" ? tr("QA & fixes") : tr("Task board");
  }
  function setView(v, focus) {
    view = v; store.set(VIEW_KEY, v);
    applyView();
    if (data && data.ok && shownPhase() === "construction") {
      const m = currentMilestone();
      if (view === "qa") renderQaPanel(m); else renderKanban(m);
    }
    if (focus) document.querySelector(`#view-switch [data-view="${view}"]`).focus();
  }
  /** Arrow keys, Home and End move between the tabs of a tab list. */
  function tabKeys(box, keys, cur, go) {
    box.addEventListener("keydown", (e) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
      let i = keys.indexOf(cur());
      i = e.key === "Home" ? 0 : e.key === "End" ? keys.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + keys.length) % keys.length;
      go(keys[i]); e.preventDefault();
    });
  }
  $("view-switch").addEventListener("click", (e) => { const b = e.target.closest("[data-view]"); if (b) setView(b.dataset.view, false); });
  tabKeys($("view-switch"), VIEWS, () => view, (v) => setView(v, true));

  // ------------------------------------------------------------------ drawers (Needs you, Requests, Activity) and the metrics modal
  const ndlg = $("needs-dialog"), rdlg = $("req-dialog"), adlg = $("act-dialog"), mdlg = $("metrics-dialog");
  const DRAWERS = [ndlg, rdlg, adlg, mdlg];
  const drawerFrom = new Map();
  /** One drawer at a time; closing it gives the focus back to what opened it. */
  function openDrawer(d) {
    DRAWERS.forEach((x) => { if (x !== d && x.open) { drawerFrom.delete(x); x.close(); } });
    if (d.open) return;
    drawerFrom.set(d, document.activeElement);
    if (d.showModal) d.showModal(); else d.setAttribute("open", "");
  }
  const closeDrawers = () => DRAWERS.forEach((x) => { if (x.open) { drawerFrom.delete(x); x.close(); } });
  [[ndlg, "needs-close"], [rdlg, "req-close"], [adlg, "act-close"], [mdlg, "metrics-close"]].forEach(([d, c]) => {
    $(c).addEventListener("click", () => d.close());
    d.addEventListener("click", (e) => { if (e.target === d) d.close(); });  // a click on the backdrop
    d.addEventListener("close", () => { const o = drawerFrom.get(d); drawerFrom.delete(d); if (o && o.isConnected) o.focus({ preventScroll: true }); });
  });
  $("needs-btn").addEventListener("click", () => openDrawer(ndlg));
  $("req-btn").addEventListener("click", () => openDrawer(rdlg));
  $("act-btn").addEventListener("click", () => openDrawer(adlg));
  $("replan-back").addEventListener("click", () => { replanOpen = false; render(); const b = $("replan-btn"); if (b) b.focus(); });

  // metrics: burndown, velocity and gates, drawn when the modal opens (the charts measure their box)
  const INS_KEY = "board-metrics-v1";
  let insView = INS.includes(store.get(INS_KEY, "")) ? store.get(INS_KEY, "") : "burndown";
  function renderMetrics() {
    if (!mdlg.open || !data || !data.ok) return;
    INS.forEach((k) => {
      $(`ins-${k}`).hidden = k !== insView;
      const b = $(`ins-tab-${k}`);
      b.setAttribute("aria-selected", String(k === insView));
      b.tabIndex = k === insView ? 0 : -1;
    });
    const m = currentMilestone();
    $("metrics-sub").textContent = m ? `${m.id} · ${m.title || ""}` : "";
    if (insView === "burndown") renderBurndown(m);
    else if (insView === "velocity") renderVelocity(currentId());
    else renderGates();
  }
  const setIns = (k, focus) => { insView = k; store.set(INS_KEY, k); renderMetrics(); if (focus) $(`ins-tab-${k}`).focus(); };
  $("ins-switch").addEventListener("click", (e) => { const b = e.target.closest("[data-view]"); if (b) setIns(b.dataset.view, false); });
  tabKeys($("ins-switch"), INS, () => insView, (k) => setIns(k, true));
  $("metrics-btn").addEventListener("click", () => { openDrawer(mdlg); renderMetrics(); });

  // ------------------------------------------------------------------ main render + data flow
  function render() {
    if (!data) return;
    const banner = $("banner");
    if (!data.ok) {
      banner.hidden = false; banner.textContent = data.message || tr("Could not read the project state.");
      return;
    }
    banner.hidden = true;
    const m = currentMilestone();
    const ph = shownPhase();
    const panel = planShown() ? "replan" : ph;
    keepFocus(() => {
      // global: the lane tabs, Needs you, requests and activity; below, only the screen of the lane shown
      ["map", "arch", ...LANES, "replan"].forEach((k) => { $(`phase-${k}`).hidden = k !== panel; });
      document.body.dataset.screen = panel;
      renderImpediments(); renderHeader(); renderRequests(); renderFeed();
      applyView();
      if (panel === "map") renderMap();
      else if (panel === "arch") renderArch();
      else if (panel === "conception") renderConception();
      else if (panel === "planning") renderPlanning();
      else if (panel === "replan") renderPlan();
      else if (panel === "construction") {
        renderTabs(); renderMilestone(m); renderStages(m); autoQaView(m);
        if (view === "qa") renderQaPanel(m); else renderKanban(m);
      } else if (panel === "releases") renderReleasesPanel();
      else renderStable();
      if (panel !== "replan") $("planner").hidden = true;
      renderMetrics();
    });
    updateAttention();
    clampSoon();
    $("main").setAttribute("aria-busy", "false");
    if (firstRender) {
      firstRender = false;
      const tid = decodeURIComponent(location.hash.slice(1));
      if (TASK_RE.test(tid)) openTask(tid);
      const dm = tid.match(DOC_HASH);
      if (dm) openDoc(dm[1], dm[2]);
      const rm = tid.match(REL_HASH);
      if (rm && relPlan().some((r) => r.id === rm[1])) openRelease(rm[1]);
    }
  }

  async function load() {
    if (stopped) return;
    if (loading) { pending = true; return; }
    loading = true;
    try {
      const r = await fetch("/api/state", { cache: "no-store" });
      const next = await r.json();
      if (next.ok && !data && !langPicked && pickLang(next.language) && pickLang(next.language) !== LANG) { data = next; setLang(next.language, false); }
      if (next.ok || !data) data = next;
      else if (!next.ok && next.error === "corrupt_state") { /* mid-write: keep the previous frame */ }
      else data = next;
      lastUpdate = Date.now();
      render();
      tickUpdated();
      if (tdlg.open && tdCur) fetchTask(tdCur, true);
      if (ddlg.open && docCur) fetchDoc(docCur, true);
    } catch (e) {
      setLive("off", tr("Offline"));
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
  /** The time header: how long the orchestrator and the current skill have run, and when the last event came
   * ("Live" says the connection is up; "last event" says something is happening). */
  function tickUpdated() {
    if (!data || !data.ok) { $("updated").textContent = ""; return; }
    const runs = skillRuns(), parts = [];
    const orch = runs.find((r) => ["autopilot", "worker"].includes(r.skill));
    const work = [...runs].reverse().find((r) => !["autopilot", "worker", "board"].includes(r.skill));
    if (orch) parts.push(tr("{v} for {d}", { v: orch.skill, d: dur((Date.now() - parseT(orch.started_at)) / 1000) }));
    if (work) parts.push(tr("{v} for {d}", { v: actionLabel(runCmd(work)).replace(/^Run /, ""), d: dur((Date.now() - parseT(work.started_at)) / 1000) }));
    const last = Math.max(0, ...[...(data.log || []), ...(data.feed || [])].map((r) => parseT(r.at)).filter(Number.isFinite));
    if (last) parts.push(tr("last event {v}", { v: ago(last) }));
    $("updated").textContent = parts.join(" · ");
    $("updated").title = lastUpdate ? tr("Board data refreshed {v}", { v: ago(lastUpdate) }) : "";
  }

  function connect() {
    if (stopped) return;
    es = new EventSource("/api/events");
    es.addEventListener("hello", () => { setLive("on", tr("Live")); $("banner").hidden = !(data && !data.ok); load(); });
    es.addEventListener("change", () => load());
    es.addEventListener("bye", () => { es.close(); showStopped(); });
    es.onerror = () => {
      if (stopped) return;
      setLive("off", tr("Reconnecting…"));
      const b = $("banner"); b.hidden = false; fill(b, tr("The board server is not answering. Reconnecting… Start it again with "), cmd("/dev-kit:board"));
    };
  }

  function showStopped() {
    stopped = true;
    if (es) es.close();
    setLive("off", tr("Stopped"));
    if (tdlg.open) tdlg.close();
    $("stopped").hidden = false;
    document.title = tr("Board stopped · dev-kit");
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
    h("button", { type: "button", class: "tid-btn", text: x.id, "aria-label": tr("Open {id}", { id: x.id }), onclick: () => openTask(x.id) }), ` ${x.title || ""} `,
    h("span", { class: `chip st-chip s-${x.status}`, text: stLabel(x.status) }),
    x.reason ? h("span", { class: "muted", text: tr(" · needed because {reason}", { reason: x.reason }) }) : null))) : null);
  /** A task's source as a link: a .dev markdown report (qa/M1/report.md#F-3), or the release review of a rejected release. */
  function sourceLink(src) {
    const rel = String(src).match(/^release:(R\d{1,3})$/);
    if (rel) {
      const r = relPlan().find((x) => x.id === rel[1]);
      return docLink((r && r.review_doc) || `releases/${rel[1]}/review.md`, tr("{v} rejected · release review", { v: rel[1] }));
    }
    const m = String(src).match(/^(?:\.dev\/)?([\w./-]+\.md)(?:#([\w-]+))?/);
    return m && hasDoc(m[1]) ? docLink(m[1], src, m[2] || null) : String(src);
  }
  function renderTask(d) {
    const body = $("task-body");
    if (!d.ok) { fill(body, h("p", { class: "card-sub", text: d.error === "unknown task" /* i18n-ok: server code */ ? tr("This task no longer exists (a replan may have removed it).") : tr("Could not load the task.") })); return; }
    $("task-title").textContent = `${d.id} ${d.title || ""}`;
    const c = d.commit;
    fill(body, [
      h("div", { class: "tcard-top" }, h("span", { class: `chip st-chip s-${d.status}`, text: stLabel(d.status) }), h("span", { class: "chip", text: d.type }),
        d.lane ? h("span", { class: `chip lane-${d.lane}`, text: d.lane }) : null, h("span", { class: "chip", text: d.milestone }),
        d.started_at ? h("span", { text: tr("started {v}", { v: fmtDT(parseT(d.started_at)) }) }) : null,
        d.done_at ? h("span", { text: tr("done {v}", { v: fmtDT(parseT(d.done_at)) }) }) : null,
        taskTook(d) != null ? h("span", { class: "took", title: tr("Execution time: from start to done"), text: tr("took {v}", { v: dur(taskTook(d)) }) }) : null),
      agentsOn(d.id).length ? h("div", { class: "tcard-agents td-sec" }, agentsOn(d.id).map((x) => h("span", { class: "agent-chip" }, agentBits(x)))) : null,
      d.blocked_reason ? h("div", { class: "reason td-sec", text: d.blocked_reason }) : null,
      section(tr("Origin"), d.issue ? h("p", {}, h("span", { class: "tid", text: d.issue.id }), ` ${d.issue.title || ""}`,
        h("span", { class: "card-sub", text: ` · ${[d.issue.type, d.issue.class, d.issue.severity, d.issue.status].filter(Boolean).join(" · ")}` }),
        d.issue.note ? h("span", { class: "td-note", text: d.issue.note }) : null) : (d.source ? h("p", {}, sourceLink(d.source)) : null)),
      section(tr("Acceptance criteria ({acceptance_n})", { acceptance_n: d.acceptance.length }), d.acceptance.length ? h("ul", { class: "td-list" }, d.acceptance.map((a) =>
        h("li", {}, a.text, a.prd ? h("span", { class: "td-note", text: tr("PRD: {prd}", { prd: a.prd }) }) : null))) : null),
      section(tr("How to test"), d.test_notes ? h("p", { text: d.test_notes }) : null),
      section(tr("Depends on"), taskRefs(d.deps)),
      section(tr("Unblocks"), taskRefs(d.blocks)),
      section(tr("Planned files"), d.files.length ? h("ul", { class: "td-list mono" }, d.files.map((f) => h("li", { text: f }))) : null),
      section(tr("Commit"), c ? [h("p", {}, h("span", { class: "tid", text: c.sha.slice(0, 7) }), ` ${c.subject}`, h("span", { class: "card-sub", text: ` · ${c.author} · ${fmtDT(parseT(c.date))}` })),
        c.files.length ? h("ul", { class: "td-list mono" }, c.files.map((f) => h("li", { text: f }))) : null, c.summary ? h("p", { class: "card-sub", text: c.summary }) : null]
        : (d.commit_sha ? h("p", {}, h("span", { class: "tid", text: d.commit_sha.slice(0, 7) }), h("span", { class: "card-sub", text: tr(" · not available in this checkout") })) : null)),
      section(tr("History"), d.log.length ? h("ul", { class: "td-list plain" }, d.log.map((r) => h("li", {}, h("span", { class: "card-sub", text: `${r.at} ` }), r.text))) : null),
      h("p", { class: "card-sub td-foot", text: tr("No free-text description is stored for tasks yet; this is everything recorded in .dev/.") })]);
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
    fill($("task-body"), h("p", { class: "card-sub", text: tr("Loading…") }));
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
    const rm = tid.match(REL_HASH);
    if (rm && relPlan().some((r) => r.id === rm[1])) { openRelease(rm[1]); return; }
    if (TASK_RE.test(tid) && tid !== tdCur) openTask(tid);
    else if (!tid && tdlg.open) tdlg.close();
    else if (!tid && ddlg.open) ddlg.close();
  });

  // ------------------------------------------------------------------ markdown documents of .dev/: a side drawer, linkable as #doc:<path>
  // A small renderer that builds the DOM with h() (text through textContent, never innerHTML): headings with anchors,
  // paragraphs, nested lists and checkboxes, tables, fenced code, quotes, rules, and inline code, bold, italic, links.
  const ID_TOKEN = /^(ADR-\d{1,5}|Q-\d{1,5}|I-\d{1,5}|T-\d{1,5}|F-\d{1,5}|AC-\d{1,4}|M\d{1,3}(?:\.\d{1,2})?|R\d{1,3})\b/;
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
        cb ? h("span", { class: "visually-hidden", text: cb[1] === " " ? tr("to do: ") : tr("done: ") }) : null,
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
  const DOC_NAME = tmap({ "brief.md": N_("Brief"), "prd.md": N_("PRD"), "architecture.md": N_("Architecture"), "design/ux-flows.md": N_("UX flows"), "design/ui-spec.md": N_("UI spec"),
    "plan.md": N_("Plan"), "decisions.md": N_("Decisions"), "facts.md": N_("Facts"), "open-questions.md": N_("Open questions"), "issues.md": N_("Issues"), "log.md": N_("Log") });
  let docStack = [];          // documents opened from inside the drawer: "Back" walks them
  let docOrigin = null;       // element the drawer was opened from: focus returns there
  const hasDoc = (p) => (data.docs || []).includes(p);
  const relDev = (p) => String(p || "").replace(/^\.dev\//, "");
  /** A button that opens a .dev markdown file in the drawer, or plain text when the file does not exist. */
  function docLink(path, label, anchor, cls) {
    const p = relDev(path);
    if (!hasDoc(p)) return h("span", { class: `doc-off${cls ? ` ${cls}` : ""}`, title: tr(".dev/{p} does not exist yet", { p }), text: label || p });
    return h("button", { type: "button", class: `doc-link${cls ? ` ${cls}` : ""}`, "data-doc": p, title: tr("Open .dev/{p}{v}", { p, v: anchor ? ` at ${anchor}` : "" }),
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
    if (!d.ok) { fill(body, h("p", { class: "card-sub", text: d.error === "not found" /* i18n-ok: server code */ ? tr("This document does not exist (any more).") : tr("Could not open it: {v}.", { v: d.error || "error" }) })); return; }
    fill(body, renderMarkdown(d.text, d.path), h("p", { class: "card-sub td-foot", text: tr(".dev/{p} · changed {v}", { p: d.path, v: Number.isFinite(parseT(d.mtime)) ? fmtDT(parseT(d.mtime)) : d.mtime }) }));
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
    fill($("doc-body"), h("p", { class: "card-sub", text: tr("Loading…") }));
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
  const REL_HASH = /^release:(R\d{1,3})$/;
  const DOC_HASH = /^doc:([\w./-]+\.md)(?::([\w-]+))?$/i;

  // ------------------------------------------------------------------ stop server
  const dlg = $("stop-dialog");
  $("stop-btn").addEventListener("click", () => {
    pops.forEach((p) => p.close());
    if (dlg.showModal) dlg.showModal(); else if (confirm(tr("Stop the board server?"))) stopServer();
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
      const b = $("banner"); b.hidden = false; fill(b, tr("Could not stop the server ({message}). Use ", { message: e.message }), cmd("/dev-kit:board stop"));
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
  let lastW = window.innerWidth, lastH = window.innerHeight;
  window.addEventListener("resize", () => {
    if (window.innerWidth === lastW && window.innerHeight === lastH) return;
    const wide = window.innerWidth !== lastW;
    lastW = window.innerWidth; lastH = window.innerHeight;
    clearTimeout(resizeT);
    // the tiles and columns have the height of the window: what fits changes with it
    resizeT = setTimeout(wide ? render : clampAll, 150);
  });

  setInterval(tickUpdated, 1000);
  load();
  connect();
})();
