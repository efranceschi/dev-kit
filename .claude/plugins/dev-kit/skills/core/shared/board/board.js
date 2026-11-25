/* dev-kit board - live view of .dev/state.json: milestone window, what needs the user, the stages of the milestone with what runs in each, the milestone kanban, insights. Read-only: it only shows the project; every decision and run happens in Claude Code. No dependencies. All untrusted text goes through textContent. */
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
  let lastText = "";         // the last state received (without its timestamp): an identical one is not drawn again

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
  // ------------------------------------------------------------------ commands: shown as text only (the board is read-only; the console runs them)
  const cmd = (text) => h("code", { class: "cmd", text });
  /** What a command does, in words ("Run QA of M2"); the literal command is in the title. */
  const ACTION_LABEL = tmap({ qa: N_("Run QA of {s}"), implement: N_("Build {s}"), autopilot: N_("Continue construction"), docs: N_("Generate docs"), release: N_("Prepare release {s}"),
    plan: N_("Plan"), review: N_("Review {s}"), interview: N_("Answer open questions"), prd: N_("Write the PRD"), architecture: N_("Design the architecture"), ux: N_("Design the UX"),
    ui: N_("Design the UI"), usability: N_("Test usability"), deploy: N_("Deploy"), issue: N_("Triage issues"), backlog: N_("Review the backlog"), feedback: N_("Review the kit's feedback"),
    start: N_("Start"), board: N_("Open the board"), settings: N_("Settings"), onboarding: N_("Onboard the project") });
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

  // ------------------------------------------------------------------ animations: drawings that show the work (agent mascots, the gate traffic light,
  // the Autopilot coffee or the milestone plant, the release train). "full" moves, "still" keeps the drawings without motion, "off" hides them;
  // the system's reduce-motion setting stops every animation (board.css), so it works as "still". Every drawing is aria-hidden or labelled.
  const MOTIONS = ["full", "still", "off"];
  const MOTION_KEY = "board-motion";
  let motion = MOTIONS.includes(store.get(MOTION_KEY, "")) ? store.get(MOTION_KEY, "") : "full";
  function applyMotion() {
    document.documentElement.dataset.motion = motion;
    document.querySelectorAll("[data-motion-opt]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.motionOpt === motion)));
  }
  function setMotion(v) {
    motion = MOTIONS.includes(v) ? v : "full"; store.set(MOTION_KEY, motion); applyMotion();
    if (data && data.ok) render();
  }
  $("motion-switch").addEventListener("click", (e) => { const b = e.target.closest("[data-motion-opt]"); if (b) setMotion(b.dataset.motionOpt); });
  applyMotion();
  const funOn = () => motion !== "off";
  /** Every looping animation lasts a divisor of 24 s and starts at --clk (now, modulo 24 s), so a redraw keeps its phase instead of restarting it. */
  const syncClock = () => document.documentElement.style.setProperty("--clk", `-${Date.now() % 24000}ms`);
  const agColor = (name) => { const c = roleOf(name).color; return AGENT_COLORS.includes(c) ? c : "blue"; };
  /** An implementer walking and pushing a box (its commit) along the card. */
  function walker(name) {
    return s("svg", { class: `mascot walker ag-${agColor(name)}`, viewBox: "0 0 30 40", "aria-hidden": "true" },
      s("g", { class: "m-body" },
        s("circle", { cx: "13", cy: "9", r: "7" }),
        s("circle", { cx: "16", cy: "8", r: "1.6", class: "m-eye" }), s("circle", { cx: "11", cy: "8", r: "1.6", class: "m-eye" }),
        s("circle", { cx: "16.4", cy: "8.2", r: ".8", class: "m-pupil" }), s("circle", { cx: "11.4", cy: "8.2", r: ".8", class: "m-pupil" }),
        s("rect", { x: "8", y: "16", width: "10", height: "12", rx: "4" }),
        s("path", { d: "M16 20 L27 18", class: "m-limb" })),
      s("path", { d: "M11 27 L11 38", class: "m-limb leg-a" }), s("path", { d: "M15 27 L15 38", class: "m-limb leg-b" }));
  }
  function walkTrack(names) {
    return h("span", { class: "walk-track", "aria-hidden": "true" }, names.slice(0, 2).map((n, i) =>
      h("span", { class: `walk${i ? " second" : ""}` }, walker(n), h("span", { class: "walk-box" }))));
  }
  /** The mascot of a task that waits for the user: it naps next to the card and wakes up now and then to wave. */
  function sleeper(name) {
    return h("span", { class: "sleeper", "aria-hidden": "true" },
      s("svg", { class: `mascot ag-${agColor(name)}`, viewBox: "0 0 78 70" },
        s("rect", { x: "22", y: "40", width: "22", height: "20", rx: "8" }),
        s("path", { d: "M24 58 L14 64 M40 58 L50 64 M24 48 L18 56", class: "m-limb thick" }),
        s("path", { d: "M42 46 L54 34", class: "m-limb thick wave" }),
        s("path", { d: "M42 48 L46 56", class: "m-limb thick rest" }),
        s("g", { class: "m-head" },
          s("circle", { cx: "33", cy: "28", r: "12" }),
          s("path", { d: "M26 28 q3 3 6 0 M35 28 q3 3 6 0", class: "m-line closed" }),
          s("g", { class: "open" }, s("circle", { cx: "29", cy: "27", r: "2.6", class: "m-eye" }), s("circle", { cx: "38", cy: "27", r: "2.6", class: "m-eye" }),
            s("circle", { cx: "29.5", cy: "27.4", r: "1.3", class: "m-pupil" }), s("circle", { cx: "38.5", cy: "27.4", r: "1.3", class: "m-pupil" }),
            s("path", { d: "M29 34 q4 3 8 0", class: "m-line" }))),
        s("g", { class: "zz" }, s("path", { d: "M50 15 h5 l-5 6 h5" }), s("path", { d: "M58 5 h6 l-6 7 h6" }), s("path", { d: "M66 -6 h7 l-7 9 h7" }))));
  }
  /** The QA auditor with a magnifier, raising an eyebrow, while QA runs. */
  function inspector(name) {
    return s("svg", { class: `mascot fnode-fun inspector ag-${agColor(name)}`, viewBox: "0 0 56 52", "aria-hidden": "true" },
      s("circle", { cx: "18", cy: "16", r: "10" }),
      s("ellipse", { cx: "14", cy: "15", rx: "2", ry: "2", class: "m-eye" }), s("circle", { cx: "14.5", cy: "15.3", r: "1", class: "m-pupil" }),
      s("ellipse", { cx: "22", cy: "16", rx: "2.2", ry: ".9", class: "m-eye" }),
      s("path", { d: "M19 10.5 L25 9", class: "m-line brow" }), s("path", { d: "M11 11 L16 11.5", class: "m-line" }),
      s("path", { d: "M15 21.5 Q18 20.5 21 21.5", class: "m-line" }),
      s("rect", { x: "11", y: "27", width: "14", height: "16", rx: "5" }),
      s("path", { d: "M14 43 L14 50 M22 43 L22 50", class: "m-limb" }),
      s("g", { class: "lens" }, s("path", { d: "M24 32 L34 26", class: "m-limb" }), s("path", { d: "M35 25 L39 22", class: "m-handle" }),
        s("circle", { cx: "44", cy: "17", r: "7", class: "m-glass" })));
  }
  /** The gate as a traffic light: one lamp per rule (hard floor, exit check, cut-offs). While QA runs the lamps turn green
   * one by one; a passed gate shows three greens and a "go" arrow; a failed gate turns the lamp of the rule that failed red. */
  function trafficLight(state, failed) {
    const lamp = (i, cy) => s("circle", { cx: "17", cy, r: "6.5", class: `tl-lamp l${i}${failed === i ? " bad" : ""}` });
    return s("svg", { class: `fnode-fun tlight g-${state}`, viewBox: "0 0 66 70", "aria-hidden": "true" },
      s("rect", { x: "15", y: "56", width: "4", height: "14", rx: "1", class: "tl-pole" }),
      s("rect", { x: "6", y: "2", width: "22", height: "56", rx: "6", class: "tl-box" }),
      lamp(1, "14"), lamp(2, "30"), lamp(3, "46"),
      s("path", { d: "M36 26 H48 V18 L64 30 L48 42 V34 H36 Z", class: "tl-go" }));
  }
  /** Which rule of the gate failed: 1 the hard floor, 2 the exit check, 3 the cut-offs (the default). */
  function gateFailedRule(m) {
    const hf = m.hard_floor && m.hard_floor.checks ? Object.values(m.hard_floor.checks) : [];
    if (hf.some((c) => c && c.status === "fail")) return 1;
    if ((m.gate_checks || []).some((g) => /exit/i.test(String(g.text || "")))) return 2;
    return 3;
  }
  /** One bug of the QA panel: a blocking finding still open walks; a fixed one lies on its back. */
  function bug(cls) {
    return s("svg", { class: `qa-bug ${cls}`, viewBox: "0 0 22 18", "aria-hidden": "true" },
      s("path", { d: "M6 4 L2 1 M6 9 L1 9 M6 14 L2 17 M16 4 L20 1 M16 9 L21 9 M16 14 L20 17", class: "qb-legs" }),
      s("ellipse", { cx: "11", cy: "9", rx: "6", ry: "7", class: "qb-body" }), s("circle", { cx: "11", cy: "2.5", r: "2.5", class: "qb-head" }));
  }
  /** Open blocking findings crawl across their block (at most three bugs). */
  function bugTrail(n) {
    return h("div", { class: "qa-bugs", "aria-hidden": "true" }, Array.from({ length: Math.min(3, n) }, (_, i) => bug(`qb-run b${i + 1}`)));
  }
  /** Fixed findings: the bugs on their back and a mascot with the swatter. */
  function swatter(done) {
    return h("div", { class: "qa-bugs swatted", "aria-hidden": "true" },
      Array.from({ length: Math.min(3, done) }, () => bug("qb-dead")),
      s("svg", { class: "mascot ag-yellow qa-swatter", viewBox: "0 0 56 50" },
        s("circle", { cx: "12", cy: "20", r: "7" }), s("circle", { cx: "14", cy: "19", r: "1.5", class: "m-eye" }), s("circle", { cx: "14.3", cy: "19.3", r: ".7", class: "m-pupil" }),
        s("rect", { x: "6", y: "28", width: "12", height: "14", rx: "4" }), s("path", { d: "M9 42 V49 M15 42 V49", class: "m-limb" }),
        s("g", { class: "sw-arm" }, s("path", { d: "M17 32 L40 12", class: "sw-stick" }), s("rect", { x: "36", y: "2", width: "16", height: "14", rx: "2", class: "sw-net", transform: "rotate(40 44 9)" }))));
  }
  const plantSeen = {};
  /** The Autopilot coffee (on) or the milestone plant (off): the same place, the progress of the milestone shown. */
  function msFun(m, prog, closed) {
    const box = $("ms-fun");
    if (!box) return;
    const ap = autopilotRun();
    box.hidden = !funOn() || !m;
    if (box.hidden) { fill(box); return; }
    const p = Math.max(0, Math.min(1, closed ? 1 : prog.total));
    const pct = Math.round(p * 100);
    if (ap) {
      const label = tr("Autopilot coffee: {v}% of {id} still to do", { v: 100 - pct, id: m.id });
      box.setAttribute("aria-label", label); box.title = label;
      const liquid = s("rect", { x: "12", y: "28", width: "38", height: "30", class: "c-liquid" });
      liquid.style.setProperty("--drop", `${(p * 26).toFixed(1)}px`);
      fill(box, s("svg", { class: `cup${p < 1 ? " hot" : ""}`, viewBox: "0 0 64 64" },
        s("path", { d: "M24 20 q-3 -4 0 -8 q3 -4 0 -8", class: "c-steam s1" }), s("path", { d: "M31 20 q-3 -4 0 -8 q3 -4 0 -8", class: "c-steam s2" }),
        s("path", { d: "M38 20 q-3 -4 0 -8 q3 -4 0 -8", class: "c-steam s3" }),
        s("defs", {}, s("clipPath", { id: "cup-clip" }, s("path", { d: "M14 26 H46 V44 Q46 54 36 54 H24 Q14 54 14 44 Z" }))),
        s("g", { "clip-path": "url(#cup-clip)" }, liquid),
        s("path", { d: "M14 26 H46 V44 Q46 54 36 54 H24 Q14 54 14 44 Z M46 30 Q55 30 55 37 Q55 44 46 44", class: "c-cup" }),
        s("path", { d: "M10 57 H50", class: "c-dish" })));
      return;
    }
    const label = closed ? tr("{id} flowered: milestone closed", { id: m.id }) : tr("{id} grows with its work: {v}%", { id: m.id, v: pct });
    box.setAttribute("aria-label", label); box.title = label;
    const stem = s("path", { d: "M45 104 C45 90 41 78 45 66 C49 54 43 42 45 26", pathLength: "1", class: "p-stem" });
    stem.style.strokeDashoffset = String(1 - Math.max(0.12, p));
    const leaves = [["l", "M44 94 q-14 -2 -18 -12 q12 -1 18 12 z"], ["r", "M44 84 q14 -2 18 -12 q-12 -1 -18 12 z"], ["l", "M44 72 q-14 -2 -18 -12 q12 -1 18 12 z"],
      ["r", "M46 60 q14 -2 18 -12 q-12 -1 -18 12 z"], ["l", "M44 48 q-12 -2 -15 -10 q10 -1 15 10 z"]];
    const on = Math.round(p * leaves.length);
    const before = plantSeen[m.id] != null ? plantSeen[m.id] : on;  // leaves that opened since the last redraw pop in once
    plantSeen[m.id] = on;
    fill(box, s("svg", { class: "plant", viewBox: "0 0 90 120" },
      s("g", { class: "p-top" }, stem, leaves.map(([side, d], i) => s("path", { d, class: `p-leaf ${side}${i < on ? " on" : ""}${i < on && i >= before ? " new" : ""}` })),
        s("g", { class: `p-flower${closed ? " on" : ""}` }, [[45, 18], [53, 23], [37, 23], [40, 31], [50, 31]].map(([cx, cy]) => s("circle", { cx: String(cx), cy: String(cy), r: "6", class: "p-petal" })),
          s("circle", { cx: "45", cy: "25", r: "4.5", class: "p-core" }))),
      s("path", { d: "M28 104 H62 L58 118 H32 Z", class: "p-pot" }), s("rect", { x: "26", y: "100", width: "38", height: "6", rx: "2", class: "p-rim" })));
  }
  /** The release train under the release's flow: a locomotive pulling its milestones, stopped at a red signal until you approve. */
  function relTrain(r, nodes) {
    if (!funOn()) return null;
    const at = Math.max(0, nodes.findIndex((n) => n.here));
    const slot = (i) => ((i + 0.5) / nodes.length) * 100;
    const approval = nodes.findIndex((n) => n.key === "approval");
    const pos = r.status === "released" ? 100 : r.status === "in_progress" ? 0 : r.status === "awaiting_approval" ? slot(Math.max(0, approval - 1)) : slot(at);
    const moving = r.status !== "released" && r.status !== "awaiting_approval"
      && (runsAt("releases").length > 0 || r.milestones.some((id) => tasksOf(data.milestones.find((x) => x.id === id)).some((t) => t.status === "in_progress")));
    const wagons = r.milestones.slice(-4);
    const train = h("span", { class: `train${moving ? " moving" : ""}` },
      r.milestones.length > wagons.length ? h("span", { class: "wagon more", text: `+${r.milestones.length - wagons.length}` }) : null,
      wagons.map((id) => h("span", { class: `wagon${(r.closed || []).includes(id) ? " full" : ""}`, text: id })),
      s("svg", { class: "loco", viewBox: "0 0 58 46" },
        s("circle", { cx: "44", cy: "6", r: "5", class: "t-puff p1" }), s("circle", { cx: "44", cy: "6", r: "5", class: "t-puff p2" }),
        s("rect", { x: "40", y: "10", width: "8", height: "10", rx: "2", class: "t-dark" }),
        s("rect", { x: "2", y: "8", width: "22", height: "24", rx: "4", class: "t-body" }),
        s("rect", { x: "6", y: "12", width: "14", height: "9", rx: "2", class: "t-window" }),
        s("rect", { x: "22", y: "18", width: "32", height: "14", rx: "6", class: "t-body" }),
        s("path", { d: "M54 32 L58 38 H48 Z", class: "t-dark" }),
        [[12, 38, 6], [30, 39, 5], [44, 39, 5]].map(([cx, cy, rr]) => s("g", { class: "t-wheel" }, s("circle", { cx: String(cx), cy: String(cy), r: String(rr) }),
          s("path", { d: `M${cx - rr + 1} ${cy} H${cx + rr - 1}` })))));
    train.style.left = `${pos}%`;
    train.style.transform = `translateX(-${pos}%)`;
    const sig = approval >= 0 ? h("span", { class: `signal${["deploying_prod", "released"].includes(r.status) ? " go" : r.status === "awaiting_approval" ? " stop" : ""}` },
      h("span", { class: "lamp" }), h("span", { class: "pole" })) : null;
    if (sig) sig.style.left = `${slot(approval) - 100 / nodes.length / 2}%`;
    const label = r.status === "awaiting_approval" ? tr("{id} stopped at the signal: waiting for your approval", { id: r.id }) : tr("{id} train: {v}", { id: r.id, v: REL_WORD[r.status] || r.status });
    return h("div", { class: "rail", role: "img", "aria-label": label, title: label }, h("span", { class: "rail-track" }), sig, train);
  }

  // ---- the other blocks (3.10): writer and reviewer on conception steps, the roadmap road, the backlog's mail carrier,
  // the high jump over a score's cut-off, release trophies, the health check's heartbeat, flag poles, the expedite siren, empty states
  const face = (cx, cy, r) => [s("circle", { cx: String(cx), cy: String(cy), r: String(r) }),
    s("circle", { cx: String(cx + r * 0.3), cy: String(cy - r * 0.1), r: String(r * 0.22), class: "m-eye" }), s("circle", { cx: String(cx - r * 0.35), cy: String(cy - r * 0.1), r: String(r * 0.22), class: "m-eye" }),
    s("circle", { cx: String(cx + r * 0.35), cy: String(cy - r * 0.05), r: String(r * 0.11), class: "m-pupil" }), s("circle", { cx: String(cx - r * 0.3), cy: String(cy - r * 0.05), r: String(r * 0.11), class: "m-pupil" })];
  /** A conception step being written: its agent writes on a clipboard, the lines appear. */
  function stepWriter(name) {
    return s("svg", { class: `mascot step-fun writer ag-${agColor(name)}`, viewBox: "0 0 46 44", "aria-hidden": "true" },
      s("rect", { x: "22", y: "14", width: "20", height: "26", rx: "2", class: "m-paper" }),
      s("path", { d: "M25 21 H39 M25 26 H39 M25 31 H34", pathLength: "40", class: "m-ink" }),
      face(12, 12, 7), s("rect", { x: "6", y: "20", width: "12", height: "14", rx: "4" }),
      s("path", { d: "M9 34 V42 M15 34 V42", class: "m-limb" }), s("path", { d: "M16 26 L26 30", class: "m-limb m-pen" }));
  }
  /** A conception step waiting for its review: the reviewer reads it with glasses, eyes going left and right. */
  function stepReader(name) {
    return s("svg", { class: `mascot step-fun reader ag-${agColor(name)}`, viewBox: "0 0 46 44", "aria-hidden": "true" },
      s("circle", { cx: "22", cy: "12", r: "8" }),
      s("g", { class: "m-eyes" }, s("circle", { cx: "19", cy: "12", r: "3", class: "m-glasses" }), s("circle", { cx: "26", cy: "12", r: "3", class: "m-glasses" }),
        s("circle", { cx: "19.5", cy: "13", r: "1", class: "m-pupil" }), s("circle", { cx: "26.5", cy: "13", r: "1", class: "m-pupil" })),
      s("rect", { x: "15", y: "21", width: "14", height: "14", rx: "4" }),
      s("rect", { x: "8", y: "24", width: "28", height: "12", rx: "2", class: "m-paper" }), s("path", { d: "M22 24 V36", class: "m-fold" }));
  }
  /** The roadmap as a road, newest on the left: a sign per milestone being worked on (green once closed), one sign per
   *  folded range, the car parked at the current milestone facing the newer ones, driving in when it changes. */
  let roadSeen = null;
  function roadStrip(signs) {
    if (!funOn() || !signs.length) return null;
    const cur = Math.max(0, signs.findIndex((g) => g.cur));
    const at = (i) => ((i + 0.5) / signs.length) * 100;
    const drive = roadSeen !== null && roadSeen !== data.current_milestone;
    roadSeen = data.current_milestone;
    const car = s("svg", { class: `road-car rev${drive ? " drive" : ""}`, viewBox: "0 0 46 24" },
      s("path", { d: "M4 14 L10 6 H30 L38 14 H43 Q45 14 45 16 V19 H2 V16 Q2 14 4 14 Z", class: "car-body" }),
      s("path", { d: "M12 8 H20 V14 H8 Z M22 8 H29 L35 14 H22 Z", class: "car-glass" }),
      [11, 35].map((x) => s("g", { class: "car-wheel" }, s("circle", { cx: String(x), cy: "19", r: "4.5" }), s("path", { d: `M${x - 3} 19 H${x + 3}` }))));
    car.style.setProperty("--to", `${at(cur)}%`);
    const cone = s("svg", { class: "road-cone", viewBox: "0 0 12 16" }, s("path", { d: "M6 0 L11 14 H1 Z", class: "cone-body" }), s("path", { d: "M3.5 8 H8.5", class: "cone-band" }),
      s("rect", { x: "0", y: "14", width: "12", height: "2", class: "cone-base" }));
    cone.style.left = `calc(${at(cur)}% - 37px)`;
    return h("div", { class: "road-strip", "aria-hidden": "true" },
      signs.map((g, i) => { const sg = h("span", { class: `road-sign${g.done ? " done" : ""}${g.cur ? " cur" : ""}${g.fold ? " fold" : ""}` }, h("b", { text: g.label }), h("i")); sg.style.left = `${at(i)}%`; return sg; }),
      signs[cur] && signs[cur].cur && !signs[cur].done ? cone : null, signs.some((g) => g.cur) ? car : null);
  }
  /** The backlog's mail carrier: when a new issue reaches the queue, an envelope flies in and the new row shakes. */
  let issuesSeen = null;
  function mailCarrier(toss) {
    return s("svg", { class: `mascot carrier ag-orange${toss ? " toss" : ""}`, viewBox: "0 0 80 62", "aria-hidden": "true" },
      s("rect", { x: "9", y: "2", width: "22", height: "6", rx: "2", class: "m-cap" }), s("rect", { x: "5", y: "7", width: "26", height: "3", rx: "1.5", class: "m-cap" }),
      face(19, 17, 8), s("rect", { x: "11", y: "26", width: "16", height: "18", rx: "5" }),
      s("path", { d: "M9 30 L3 46", class: "m-limb" }), s("rect", { x: "0", y: "40", width: "14", height: "12", rx: "3", class: "m-bag" }),
      s("path", { d: "M26 30 L36 26", class: "m-limb m-arm" }), s("path", { d: "M15 44 V58 M23 44 V58", class: "m-limb" }),
      s("g", { class: "m-env" }, s("rect", { x: "38", y: "16", width: "16", height: "11", rx: "2", class: "m-paper" }), s("path", { d: "M38 17 L46 23 L54 17", class: "m-fold" })));
  }
  /** A score bar with a cut-off as a high-jump lane: the mascot clears the mark when the score passes, trips before it when not. */
  function jumpLane(score, cut, ok, bad) {
    if (!funOn() || score == null || (!ok && !bad)) return null;
    const j = s("svg", { class: `mascot jumper ag-pink ${bad ? "trip" : "clear"}`, viewBox: "0 0 30 40", "aria-hidden": "true" },
      s("g", { class: "m-body" }, face(13, 9, 7), s("rect", { x: "8", y: "16", width: "10", height: "12", rx: "4" }), s("path", { d: "M17 19 L25 14 M9 19 L3 24", class: "m-limb" })),
      s("path", { d: "M11 27 L11 38", class: "m-limb leg-a" }), s("path", { d: "M15 27 L15 38", class: "m-limb leg-b" }));
    const lane = h("div", { class: "jump-lane", "aria-hidden": "true" }, j);
    lane.style.setProperty("--cut", `${Math.min(100, cut)}%`);
    lane.style.setProperty("--to", `${Math.min(100, Math.max(0, score))}%`);
    return lane;
  }
  /** Released versions as trophies on a shelf, the next planned release as a dashed one. */
  function trophyShelf(rel) {
    if (!funOn() || !rel.length) return null;
    const next = relPlan().find((r) => r.status !== "released");
    const cup = (label, empty) => h("span", { class: `trophy${empty ? " next" : ""}` },
      s("svg", { viewBox: "0 0 34 40" },
        s("path", { d: "M8 3 H26 V12 Q26 22 17 23 Q8 22 8 12 Z", class: "tr-cup" }), s("path", { d: "M8 6 H3 Q3 14 9 15 M26 6 H31 Q31 14 25 15", class: "tr-ear" }),
        empty ? null : s("rect", { x: "14", y: "23", width: "6", height: "7", class: "tr-cup" }),
        s("rect", { x: "9", y: "30", width: "16", height: "6", rx: "1.5", class: "tr-base" }), empty ? null : s("path", { d: "M12 6 L14 6 L12 16 L10 16 Z", class: "tr-shine" })),
      h("span", { class: "trophy-label", text: label }));
    return h("div", { class: "trophy-shelf", "aria-hidden": "true" }, rel.slice(-5).map((r) => cup(r.tag || r.version || "")), next ? cup(next.id, true) : null);
  }
  /** The health check as a heartbeat: a heart that beats while production is healthy, a trace with a spike per check (red when it failed). */
  function heartbeat(hc) {
    if (!funOn() || !hc || !hc.last) return null;
    const hist = (hc.history || []).slice(-12);
    const n = Math.max(1, hist.length), w = 400 / n;
    let d = "M0 30", bad = "";
    hist.forEach((c, i) => {
      const x = i * w, m = x + w / 2;
      d += ` H${(m - 8).toFixed(1)}`;
      const spike = c.ok ? ` L${(m - 4).toFixed(1)} 10 L${m.toFixed(1)} 48 L${(m + 4).toFixed(1)} 30` : ` L${(m - 3).toFixed(1)} 38 L${(m + 1).toFixed(1)} 22 L${(m + 4).toFixed(1)} 30`;
      d += spike;
      if (!c.ok) bad += ` M${(m - 8).toFixed(1)} 30${spike}`;
    });
    d += " H400";
    return h("div", { class: `heartbeat${hc.last.ok ? "" : " down"}`, "aria-hidden": "true" },
      s("svg", { class: "hb-heart", viewBox: "0 0 22 20" }, s("path", { d: "M11 19 C-6 8 3 -4 11 4 C19 -4 28 8 11 19 Z" })),
      s("svg", { class: "hb-trace", viewBox: "0 0 400 56", preserveAspectRatio: "none" }, s("path", { d, pathLength: "100", class: "hb-line" }), bad ? s("path", { d: bad, class: "hb-bad" }) : null));
  }
  /** A release flag on its pole: up and waving when on, lowered and grey when off. */
  const flagPole = (state) => (funOn() ? s("svg", { class: `flag-pole f-${state}`, viewBox: "0 0 40 34", "aria-hidden": "true" },
    s("rect", { x: "3", y: "2", width: "2.4", height: "32", class: "fp-pole" }), s("path", { d: "M5 3 H30 L25 10 L30 17 H5 Z", class: "fp-cloth" })) : null);
  /** The expedite lane's siren while a hotfix is open, the standard lane's bus while something waits for the next milestone. */
  function laneFun(k, count) {
    if (!funOn() || !count) return null;
    if (k === "expedite") return s("svg", { class: "siren", viewBox: "0 0 26 22", "aria-hidden": "true" },
      s("path", { d: "M13 8 L0 0 V16 Z", class: "sr-beam b1" }), s("path", { d: "M13 8 L26 0 V16 Z", class: "sr-beam b2" }),
      s("path", { d: "M7 18 Q7 6 13 6 Q19 6 19 18 Z", class: "sr-light" }), s("rect", { x: "5", y: "18", width: "16", height: "4", rx: "1.5", class: "sr-base" }));
    if (k === "standard") return s("svg", { class: "bus", viewBox: "0 0 40 22", "aria-hidden": "true" },
      s("rect", { x: "1", y: "2", width: "36", height: "15", rx: "4", class: "bus-body" }), s("path", { d: "M5 5 H11 V10 H5 Z M14 5 H20 V10 H14 Z M23 5 H29 V10 H23 Z", class: "car-glass" }),
      s("circle", { cx: "9", cy: "18", r: "3.5", class: "bus-wheel" }), s("circle", { cx: "29", cy: "18", r: "3.5", class: "bus-wheel" }));
    return null;
  }
  /** Good empty states: a mascot resting in a hammock (nothing blocked, nothing waiting) or sweeping (an empty column). */
  function emptyFun(kind) {
    if (!funOn()) return null;
    if (kind === "rest") return s("svg", { class: "empty-fun rest", viewBox: "0 0 84 50", "aria-hidden": "true" },
      s("path", { d: "M4 2 V48 M80 2 V48", class: "ef-post" }),
      s("g", { class: "ef-hammock" }, s("path", { d: "M4 8 Q42 40 80 8", class: "ef-net" }), s("circle", { cx: "30", cy: "22", r: "6", class: "ef-skin" }),
        s("path", { d: "M27 22 q1.5 1.5 3 0 M31 21 q1.5 1.5 3 0", class: "m-line" }), s("path", { d: "M34 26 Q46 32 58 24", class: "ef-body" })));
    return s("svg", { class: "mascot empty-fun sweep ag-blue", viewBox: "0 0 84 50", "aria-hidden": "true" },
      s("g", { class: "ef-dust" }, s("circle", { cx: "58", cy: "44", r: "2" }), s("circle", { cx: "63", cy: "42", r: "1.5" })),
      face(34, 12, 7), s("rect", { x: "28", y: "20", width: "12", height: "14", rx: "4" }), s("path", { d: "M31 34 V46 M37 34 V46", class: "m-limb" }),
      s("g", { class: "ef-broom" }, s("path", { d: "M42 22 L54 42", class: "ef-stick" }), s("path", { d: "M50 40 L60 46 L56 48 L48 44 Z", class: "ef-straw" })));
  }

  // ------------------------------------------------------------------ header
  // ------------------------------------------------------------------ what Claude Code runs now: skills (outermost first) and agents
  const skillRuns = () => ((data && data.agents && data.agents.runs) || []).filter((r) => r.skill !== "board");  // the board is not work
  const runCmd = (r) => `/dev-kit:${r.skill}${r.scope ? ` ${r.scope}` : ""}`;
  const since = (t) => h("span", { class: "agent-time", "data-start": t, text: dur((Date.now() - parseT(t)) / 1000) });
  // Every skill that runs has a place on the board, so work that is not a task card is visible where it happens.
  // Orchestrators (autopilot, start…) only show in the top bar; the work they start shows in its place.
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
  function renderRunning() {
    const runs = skillRuns(), ags = activeAgents();
    const nx = data.next && data.next.command;
    const n = runs.length + ags.length;
    const badge = $("live-n");
    badge.hidden = !n;
    badge.textContent = String(n);
    $("live").setAttribute("aria-label", n ? tr("Live: {v} running. Show what runs", { v: String(n) }) : tr("Live: nothing running. Show details"));
    fill($("live-pop"), h("p", { class: "pop-title", text: n ? tr("Running now") : tr("Nothing is running now") }),
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

  // ------------------------------------------------------------------ Autopilot: shown while /dev-kit:autopilot runs in a Claude Code session (read-only)
  const autopilotRun = () => skillRuns().find((r) => r.skill === "autopilot") || null;
  function renderAutopilot() {
    const ap = autopilotRun();
    const wrap = $("ap-wrap");
    wrap.hidden = !ap;
    if (!ap) return;
    fill($("ap-word"), tr("running"), ap.started_at ? [" · ", since(ap.started_at)] : null);
    $("ap-state").setAttribute("title", tr("{text} runs in a Claude Code session; it is started and stopped there", { text: runCmd(ap) }));
  }

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
    requestAnimationFrame(tabInSight);  // after the redraw: reading the layout mid-render costs a layout per change
  }
  // on a narrow screen the tabs scroll sideways: keep the one shown in sight
  const tabInSight = () => { const el = $(`ph-${shownPhase()}`); const bar = document.querySelector(".phasebar");
    if (el && bar && bar.scrollWidth > bar.clientWidth) bar.scrollLeft = Math.max(0, el.offsetLeft - 80); };
  function setPhase(p, focus) {
    closeDrawers(); closeList();
    phasePick = data && p === data.phase ? null : p;   // picking the current phase goes back to following it
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
      n.agents && n.agents.length ? h("span", { class: "fnode-agents", "aria-hidden": "true" }, n.agents.slice(0, 6).map((a) => h("span", { class: agentDot(a.agent), title: a.agent }))) : null,
      !compact && n.fun && funOn() ? n.fun() : null));
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
  /** The release decision is taken in Claude Code (approve or reject with what must change). */
  const releaseDecision = () => h("span", { class: "sub" }, tr("Decide in Claude Code with "), cmd("/dev-kit:release"));

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

  // ------------------------------------------------------------------ timeline (3.14): releases and milestones, newest first, the past folded
  // One order for every selector and list, so a project with 60 milestones reads like one with 6: the future that has
  // not started folds into one chip, then the releases being worked on (newest first), then the released ones, newest
  // first; past the most recent TL_PAST, released ones fold into one range. A fold opens on click and stays open until
  // the page reloads; whatever the user picked (or the project is on) is never hidden inside a fold.
  const TL_PAST = 2;           // released releases shown before the older ones fold into a range
  const TL_MS = 4;             // closed milestones shown when the plan has no releases
  const tlOpen = new Set();
  const tlToggle = (key) => { if (tlOpen.has(key)) tlOpen.delete(key); else tlOpen.add(key); render(); };
  /** Entries in timeline order: { rel } a release; { fold, key, rels, future } a folded range; { loose } milestones in no release. */
  function tlEntries(keepRel) {
    const rp = relPlan();
    const keep = (rels) => rels.some((r) => keepRel.includes(r.id));
    const unrel = rp.filter((r) => r.status !== "released");
    const started = (r) => r === unrel[0] || r.status !== "in_progress" || (r.closed || []).length > 0 || r.milestones.includes(data.current_milestone);
    const live = unrel.filter(started), next = unrel.filter((r) => !started(r));
    const past = rp.filter((r) => r.status === "released").reverse();
    const out = [];
    if (next.length) {
      if (tlOpen.has("next") || keep(next)) next.slice().reverse().forEach((r, i) => out.push({ rel: r, closeKey: !i && tlOpen.has("next") ? "next" : null }));
      else out.push({ fold: true, key: "next", rels: next, future: true });
    }
    live.slice().reverse().forEach((r) => out.push({ rel: r, live: true }));
    const inRel = new Set(rp.flatMap((r) => r.milestones));
    const loose = data.milestones.filter((m) => !inRel.has(m.id));
    if (loose.length) out.push({ loose: loose.slice().reverse() });
    past.slice(0, TL_PAST).forEach((r) => out.push({ rel: r, past: true }));
    const older = past.slice(TL_PAST);
    if (older.length) {
      if (tlOpen.has("older") || keep(older)) older.forEach((r, i) => out.push({ rel: r, past: true, closeKey: !i && tlOpen.has("older") ? "older" : null }));
      else out.push({ fold: true, key: "older", rels: older });
    }
    return out;
  }
  /** The release that holds a milestone, if any. */
  const relOf = (id) => relPlan().find((r) => r.milestones.includes(id)) || null;
  /** "R1–R4" for a range of releases (any order), "R3" for one. */
  const tlRange = (rels) => { const ids = rels.map((r) => r.id).sort((a, b) => Number(a.slice(1)) - Number(b.slice(1))); return ids.length > 1 ? `${ids[0]}–${ids.at(-1)}` : ids[0] || ""; };
  /** A folded range as a chip: it opens in place. */
  function tlFoldBtn(e, cls) {
    const n = e.rels.reduce((k, r) => k + r.milestones.length, 0);
    const label = e.future ? tr("Next: {v}", { v: tlRange(e.rels) }) : tlRange(e.rels);
    const meta = e.future ? plural(n, "milestone") : tr("✓ {v}", { v: plural(n, "milestone") });
    return h("button", { type: "button", class: `tl-fold ${cls || ""}${e.future ? " future" : " past"}`, "aria-expanded": "false",
      title: e.future ? tr("{v} not started yet: show them", { v: e.rels.map((r) => r.id).join(", ") }) : tr("{v} released: show them", { v: e.rels.map((r) => r.id).join(", ") }),
      onclick: () => tlToggle(e.key) }, h("strong", { text: label }), h("span", { class: "sel-meta", text: meta }));
  }
  /** Milestones newest first: the closed ones past the latest TL_MS fold, unless opened, kept in sight or shown in full. */
  function tlMs(list, key, keep, full) {
    const hide = list.filter(isClosed).slice(TL_MS);
    if (full || !hide.length || tlOpen.has(key) || hide.some((m) => keep.includes(m.id))) return { shown: list, hidden: [], open: tlOpen.has(key) && hide.length > 0 };
    const hs = new Set(hide.map((m) => m.id));
    return { shown: list.filter((m) => !hs.has(m.id)), hidden: hide, open: false };
  }
  /** "M1–M14" for milestones listed newest first. */
  const msRange = (list) => (list.length > 1 ? `${list.at(-1).id}–${list[0].id}` : list[0].id);
  /** The folded older closed milestones as a chip. */
  const msFoldBtn = (hidden, key, cls) => h("button", { type: "button", class: `tl-fold past ${cls || ""}`, "aria-expanded": "false", title: tr("Show the older closed milestones"), onclick: () => tlToggle(key) },
    h("strong", { text: msRange(hidden) }), h("span", { class: "sel-meta", text: tr("✓ {v}", { v: plural(hidden.length, "milestone") }) }));
  /** The chip that folds a range the user opened back. */
  const tlCloseBtn = (key) => h("button", { type: "button", class: "tl-close", "aria-expanded": "true", title: tr("Fold these back"), "aria-label": tr("Fold these back"), text: "‹", onclick: () => tlToggle(key) });
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
    const relBtn = (x) => {
      const done = x.status === "released", sel = x.id === r.id;
      const ver = (data.releases || []).filter((v) => v.release === x.id).map((v) => v.tag || v.version).pop();
      return h("button", { type: "button", role: "tab", id: `rel-${x.id}`, "aria-selected": String(sel), tabindex: sel ? "0" : "-1", class: `sel-btn${done ? " ok" : ""}${sel ? " sel" : ""}${x.status === "awaiting_approval" ? " wait" : ""}`,
        title: `${x.id} · ${x.title}: ${REL_WORD[x.status]}${relTook(x) ? ` · ${tr("took {v}", { v: relTook(x).text })}` : ""}`, onclick: () => { relView = x.id; render(); $(`rel-${x.id}`) && $(`rel-${x.id}`).focus(); } },
      h("strong", { text: x.id }), done ? h("span", { class: "sel-meta", text: `✓ ${ver || ""}`.trim() }) : h("span", { class: "sel-meta", text: `${x.closed.length}/${x.milestones.length}` }));
    };
    // the timeline, newest first: the next releases fold before, the older released ones fold after
    const relEntries = tlEntries([r.id]);
    const selector = h("div", { class: "selector" }, h("span", { class: "sel-label", text: tr("Release") }),
      h("div", { class: "sel-groups", role: "tablist", id: "rel-tabs", "aria-label": tr("Releases") }, h("div", { class: "sel-group" }, relEntries.flatMap((e) =>
        e.fold ? [tlFoldBtn(e)] : e.loose ? [] : [e.closeKey ? tlCloseBtn(e.closeKey) : null, relBtn(e.rel)]))));
    const rej = (r.history || []).filter((x) => x.event === "rejected");
    const waiting = r.status === "in_progress" ? r.milestones.filter((id) => { const m = data.milestones.find((x) => x.id === id); return m && !isClosed(m); }) : [];
    const rt = relTook(r);
    const sub = [h("strong", { text: `${r.id} · ${r.title || r.id}` }), ` · ${REL_WORD[r.status] || r.status}`,
      rt ? h("span", { class: "took", title: rt.title, text: tr(" in {v}", { v: rt.text }) }) : "",
      waiting.length ? tr(" · starts when {v} pass their gate", { v: waiting.join(", ") }) : ""];
    const nodes = relNodes(r);
    const here = nodes.find((n) => n.here);
    const fc = fcFor("releases", "release", r.id);
    fill(strip, stripHead("releases", sub, selector), flowList(nodes, false, tr("Stages of {id}", { id: r.id })), relTrain(r, nodes),
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
    const msRows = () => t.ms.slice().reverse().map((m) => {
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
    // the timeline, newest first: releases not started fold before, released ones fold after (one chip each, older ones in a range)
    const keepMs = [cur, data.current_milestone].filter(Boolean);
    const keepRel = keepMs.map((id) => (relOf(id) || {}).id).filter(Boolean);
    const group = (rid, list, closeKey) => h("div", { class: "sel-group", role: "presentation" },
      closeKey ? tlCloseBtn(closeKey) : null,
      rid ? h("button", { type: "button", class: "sel-rel", title: tr("Open {id} in Releases", { id: rid }), tabindex: "-1", text: rid, onclick: () => openRelease(rid) }) : null,
      list.map(btn));
    const groups = [];
    const foldGroup = (...kids) => h("div", { class: "sel-group fold", role: "presentation" }, kids);
    const msGroup = (rid, list, key, closeKey) => {
      const f = tlMs(list, key, keepMs);
      groups.push(group(rid, f.shown, closeKey || (f.open ? key : null)));
      if (f.hidden.length) groups.push(foldGroup(msFoldBtn(f.hidden, key)));
    };
    if (rp.length) {
      tlEntries(keepRel).forEach((e) => {
        if (e.fold) { groups.push(foldGroup(tlFoldBtn(e))); return; }
        if (e.loose) { msGroup("", e.loose, "old:loose"); return; }
        const r = e.rel, list = relMs(r).slice().reverse();
        const key = `ms:${r.id}`;
        if (e.past && !tlOpen.has(key) && !list.some((m) => keepMs.includes(m.id))) {
          const ver = (data.releases || []).filter((v) => v.release === r.id).map((v) => v.tag || v.version).pop();
          groups.push(foldGroup(e.closeKey ? tlCloseBtn(e.closeKey) : null,
            h("button", { type: "button", class: "tl-fold past", "aria-expanded": "false", title: tr("{id} released: show its milestones", { id: r.id }), onclick: () => tlToggle(key) },
              h("strong", { text: r.id }), h("span", { class: "sel-meta", text: tr("✓ {v}", { v: ver || plural(list.length, "milestone") }) }))));
          return;
        }
        if (e.past) groups.push(group(r.id, list, e.closeKey || (tlOpen.has(key) ? key : null)));
        else msGroup(r.id, list, `old:${r.id}`, e.closeKey);
      });
    } else msGroup("", ms.slice().reverse(), "old:all");
    fill($("tabs"), ms.length ? groups : h("span", { class: "card-sub" }, tr("No milestones yet. They appear after "), cmd("/dev-kit:plan"), "."));
    $("tabs-back").hidden = !data.current_milestone || cur === data.current_milestone;
    // keep the selected milestone in sight when the selector scrolls sideways
    requestAnimationFrame(() => { const selBtn = $(`tab-${currentId()}`); if (selBtn && selBtn.scrollIntoView) selBtn.scrollIntoView({ block: "nearest", inline: "nearest" }); });
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
    msFun(m, prog, Boolean(closedNow));
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
  // the gate's problems come from dev_state.py as English sentences; the known shapes are said in the reader's language
  // (an unknown one is shown as sent, so a new server message is never lost)
  const GATE_TEXT = [
    [/^hard floor: (\S+) fails(?: \(([^)]+)\))?(?: -> (\S+))?$/, (x) => tr("Hard floor: {check} fails{v}{v2}", { check: x[1], v: x[2] ? ` (${iw(x[2])})` : "", v2: x[3] ? ` → ${x[3]}` : "" })],
    [/^hard floor: no deterministic checks recorded for (\S+) \(run `([^`]+)`\)$/, (x) => tr("Hard floor: no deterministic checks recorded for {id} (run {v})", { id: x[1], v: x[2] })],
    [/^exit_check: no result in scores\.json \(spec-tracer runs (\S+)'s exit_check\)$/, (x) => tr("Exit check: no result yet (the spec-tracer runs the exit check of {id})", { id: x[1] })],
    [/^exit_check failed(?:: (.+))?$/, (x) => (x[1] ? tr("Exit check failed: {v}", { v: x[1] }) : tr("Exit check failed"))],
    [/^ci: no (\S+) result recorded for the round's commit \(run `([^`]+)`\)$/, (x) => tr("CI: no {v} result for the round's commit (run {v2})", { v: x[1], v2: x[2] })],
    [/^ci: (\S+) is (\S+) at (\S+) \(the CI verdict wins over local runs\)$/, (x) => tr("CI: {v} is {v2} at {sha} (the CI verdict wins over local runs)", { v: x[1], v2: x[2], sha: x[3] })],
  ];
  const gateText = (t) => { for (const [re, f] of GATE_TEXT) { const x = re.exec(t || ""); if (x) return f(x); } return t; };
  const TASK_WORD = tmap({ feature: N_("feature"), fix: N_("fix"), chore: N_("chore"), test: N_("test"), docs: N_("docs"), hotfix: N_("hotfix") });
  const tw = (v) => (v ? TASK_WORD[v] || v : v);
  function taskCard(t) {
    const isNext = data.next && data.next.task === t.id;
    const wait = t.status === "done" ? [] : waitingOn(t);
    const here = agentsOn(t.id);
    const nap = funOn() && t.status === "blocked";
    return h("article", { class: `tcard s-${t.status}${isNext ? " next" : ""}${nap ? " napping" : ""}`, "aria-label": tr("{id} {title}, {v}{v2}. Open details", { id: t.id, title: t.title, v: stLabel(t.status), v2: wait.length ? tr(", waiting on {v}", { v: wait.join(", ") }) : "" }),
      tabindex: "0", role: "button", "aria-haspopup": "dialog", "data-tid": t.id,
      onclick: () => openTask(t.id), onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openTask(t.id); } } },
      h("div", { class: "tcard-top" }, h("span", { class: "tid", text: t.id }), h("span", { class: "chip", text: tw(t.type) }),
        t.lane ? h("span", { class: `chip lane-${t.lane}`, text: tw(t.lane) }) : null,
        isNext ? h("span", { class: "chip next-chip", text: tr("next up") }) : null),
      h("div", { class: "tcard-title", title: String(t.title || "").length > 90 ? t.title : null, text: t.title }),
      here.length ? h("div", { class: "tcard-agents" }, here.map((x) => h("span", { class: "agent-chip" }, agentBits(x))),
        funOn() && t.status === "in_progress" ? walkTrack(here.map((x) => x.agent)) : null) : null,
      nap ? sleeper("implementer") : null,
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

  const COL_DOM = 24;
  function renderKanban(m) {
    if (view !== "tasks") return;
    const ts = tasksOf(m);
    const types = [...new Set(ts.map((t) => t.type).filter(Boolean))].sort();
    const sel = $("type-filter");
    if (typeFilter && !types.includes(typeFilter)) typeFilter = "";
    if (sel.dataset.types !== types.join(",")) {
      sel.dataset.types = types.join(",");
      fill(sel, h("option", { value: "", text: tr("All types") }), types.map((t) => h("option", { value: t, text: tw(t) })));
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
    // Blocked: grouped by what they wait on, the biggest group first, so one answer clears the most cards
    const whyN = {};
    by.blocked.forEach((t) => { const k = t.blocked_reason || ""; whyN[k] = (whyN[k] || 0) + 1; });
    by.blocked.sort((a, b) => whyN[b.blocked_reason || ""] - whyN[a.blocked_reason || ""] || String(a.blocked_reason || "").localeCompare(String(b.blocked_reason || "")) || Number(a.id.slice(2)) - Number(b.id.slice(2)));
    const col = mobileCol || ["in_progress", "blocked", "todo", "done"].find((k) => by[k].length) || "todo";
    box.dataset.col = col;
    fill($("col-tabs"), STATUS.map((st) => h("button", { type: "button", class: "seg-btn", "aria-pressed": String(col === st.key),
      text: `${st.label} ${by[st.key].length}`, onclick: () => { mobileCol = st.key; renderKanban(currentMilestone()); } })));
    // every column has the same height; the cards that do not fit become "+N more", which opens the whole column.
    // A column never shows more than COL_DOM cards, so only those are drawn: the rest only add to "+N more".
    fill(box, STATUS.map((st) => {
      const list = by[st.key];
      const all = () => openList(`${m.id} · ${st.label} (${list.length})`, st.key === "blocked" && list.length > 1
        ? groupBy(list, (t) => t.blocked_reason || "").map(([why, ts]) => h("div", { class: "modal-group" },
          h("div", { class: "list-title" }, h("span", { class: "group-name", text: why || tr("No reason recorded") }), h("span", { class: "chip", text: String(ts.length) })),
          h("div", { class: "modal-cards" }, ts.map(taskCard))))
        : h("div", { class: "modal-cards" }, list.map(taskCard)));
      return h("section", { class: "col", "data-st": st.key, "aria-label": `${st.label}, ${plural(list.length, "task")}` },
        h("div", { class: "col-head" }, h("span", { class: `swatch st-${st.key}`, "aria-hidden": "true" }), st.label,
          h("span", { class: "count", text: String(list.length) })),
        h("div", { class: `col-cards${filtering ? " scroll" : ""}`, "data-clamp": filtering ? null : "cards", "data-extra": !filtering && list.length > COL_DOM ? String(list.length - COL_DOM) : null },
          list.length ? (filtering ? list : list.slice(0, COL_DOM)).map(taskCard) : h("div", { class: "col-empty" }, filtering ? null : emptyFun(st.key === "blocked" ? "rest" : "sweep"),
            h("span", { text: filtering ? tr("No match") : st.key === "blocked" ? tr("Nothing blocked") : tr("Empty") }))),
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
  // the charts show the last VEL_WINDOW milestones (a sprint-like window that keeps the bars readable); the table has all
  const VEL_WINDOW = 12;
  let velAll = false;
  function renderVelocity(cur) {
    const box = $("velocity");
    const every = data.milestones.map((m) => {
      const ts = tasksOf(m);
      return { id: m.id, title: m.title, done: ts.filter((t) => t.status === "done").length, total: ts.length, time: msTiming(m), spend: msSpend(m.id) };
    }).filter((r) => r.total);
    const rows = velAll || every.length <= VEL_WINDOW ? every : every.slice(-VEL_WINDOW);
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
      if (band >= 34 || i % Math.ceil(34 / band) === 0 || r.id === cur) svg.append(s("text", { x: cx, y: H - 8, "text-anchor": "middle", text: r.id }));
    });
    fill(box, every.length > VEL_WINDOW ? h("div", { class: "chart-window" }, h("span", { class: "sub", text: velAll ? tr("All {n} milestones", { n: every.length }) : tr("Last {n} of {v} milestones", { n: VEL_WINDOW, v: every.length }) }),
      h("button", { type: "button", class: "link-btn", "aria-pressed": String(velAll), text: velAll ? tr("Last {n}", { n: VEL_WINDOW }) : tr("Show all"), onclick: () => { velAll = !velAll; renderVelocity(cur); } })) : null, svg);
    renderHours(rows, W);
    // the table is a list: newest first (the charts keep time order)
    fill($("velocity-table"), h("table", {}, h("thead", {}, h("tr", {}, [tr("Milestone"), tr("Done"), tr("Total"), tr("Elapsed"), tr("Working"), tr("Cost or tokens")].map((x) => h("th", { text: x })))),
      h("tbody", {}, every.slice().reverse().map((r) => h("tr", {}, h("td", { text: `${r.id} ${r.title || ""}` }), h("td", { text: String(r.done) }), h("td", { text: String(r.total) }),
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
      const thin = band < 56 && i % Math.ceil(56 / band) !== 0 && i !== rows.length - 1;  // labels never overlap
      if (!thin) svg.append(s("text", { x: cx(i), y: H - 24, "text-anchor": "middle", text: r.id }));
      if (r.spend && !thin) svg.append(s("text", { class: "spend", x: cx(i), y: H - 8, "text-anchor": "middle", text: r.spend.text }));
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
      items.length ? h("ul", { class: "list" }, items) : h("div", { class: `empty${good ? " good" : ""}` }, good && emptyText ? emptyFun("rest") : null, h("span", { text: emptyText })));
  }

  // grouped lists (3.14): a list that folds, its open state kept until the page reloads; past the cap, the rest waits
  // behind one button, so 60 questions or 30 blocked cards take the room of a few
  const groupOpen = new Map();
  const GROUP_CAP = 6;
  /** A folding list: the summary carries the title, the count and the phase; rows past `cap` show on request. */
  function foldList(key, title, items, opt = {}) {
    const det = h("details", { class: "fold-list" });
    det.open = groupOpen.has(key) ? groupOpen.get(key) : Boolean(opt.open);
    det.addEventListener("toggle", () => groupOpen.set(key, det.open));
    const cap = opt.cap || GROUP_CAP;
    const shown = groupOpen.get(`${key}:all`) || items.length <= cap + 1 ? items : items.slice(0, cap);
    const more = items.length - shown.length;
    det.append(h("summary", { class: "list-title" }, h("span", { class: "fold-caret", "aria-hidden": "true" }), title,
      h("span", { class: "chip", text: String(opt.count != null ? opt.count : items.length) }), opt.phase ? phaseTag(opt.phase) : null),
      h("ul", { class: "list" }, shown),
      more > 0 ? h("button", { type: "button", class: "link-btn more-btn", text: tr("Show {v} more", { v: more }), onclick: () => { groupOpen.set(`${key}:all`, true); render(); } }) : "",
      opt.foot || "");
    return det;
  }
  /** Items grouped by a key, the biggest group first (ties keep their order). */
  function groupBy(items, keyOf) {
    const m = new Map();
    items.forEach((x) => { const k = keyOf(x); if (!m.has(k)) m.set(k, []); m.get(k).push(x); });
    return [...m.entries()].sort((a, b) => b[1].length - a[1].length);
  }
  /** A heading row inside a grouped list. */
  const groupHead = (text, n) => h("li", { class: "group-head" }, h("span", { class: "group-name", text }), h("span", { class: "chip", text: String(n) }));

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
    const denied = data.denied || [];
    const waitingRel = relPlan().filter((r) => r.status === "awaiting_approval");
    const allNeeds = b.needs || [];
    const cneeds = allNeeds.filter((x) => x.kind === "checkpoint");
    const dneeds = allNeeds.filter((x) => x.kind === "debt_over_cap");
    const lneeds = allNeeds.filter((x) => x.kind === "lesson");
    const hneeds = allNeeds.filter((x) => x.kind === "prod_health");
    const qneeds = allNeeds.filter((x) => !["checkpoint", "debt_over_cap", "lesson", "prod_health"].includes(x.kind));
    const n = blocked.length + data.questions.length + hot.length + stuck.length + denied.length + waitingRel.length + allNeeds.length;
    // which phase each item belongs to: the tabs show the count, the rows a tag that opens the phase
    const cpPrd = cneeds.filter((x) => x.target === "prd").length;
    needsBy = { conception: cpPrd, planning: qneeds.length + cneeds.length - cpPrd, construction: blocked.length + hot.length + stuck.length + dneeds.length, stable: hneeds.length, releases: waitingRel.length };
    if (denied.length) needsBy[data.phase] = (needsBy[data.phase] || 0) + denied.length;
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
    // a new item makes the button ring once (the favicon and the title of the tab change too); the bell of the drawer
    // swings while something waits and rings harder once when a new item arrives
    const nd = $("needs-dialog");
    nd.classList.toggle("waiting", n > 0);
    if (n > before && !firstRender) { nb.classList.remove("ping"); nd.classList.remove("ring"); void nb.offsetWidth; nb.classList.add("ping"); nd.classList.add("ring"); }
    if (!n) { fill($("impediments"), h("div", { class: "empty good needs-empty" }, h("strong", { text: tr("Nothing needs you now.") }), h("span", { text: tr("Questions, confirmations, approvals and blocked work show up here.") }))); return; }
    // management by exception, in the order that costs most to leave waiting: production, approvals, decisions,
    // then the work that waits on an answer; the first two groups open, the rest fold to a line each
    const reasons = groupBy(blocked, ([, t]) => t.blocked_reason || "");
    const blockedItems = blocked.length > 1 ? reasons.flatMap(([why, list]) => [groupHead(why || tr("No reason recorded"), list.length), ...list.map(([id, t]) => blockedRow(id, t, true))])
      : blocked.map(([id, t]) => blockedRow(id, t));
    const qRow = (q) => h("li", {}, hasDoc("open-questions.md") ? docLink("open-questions.md", q.id, q.id, "id") : h("span", { class: "id", text: q.id }),
      h("span", { class: "clamp2", title: tr("Click to read it all"), onclick: (e) => e.currentTarget.classList.toggle("open") }, linkify(q.question)),
      h("span", { class: "q-tags" }, h("span", { class: "chip", text: q.by || "?" }), phaseTag(questionPhase(q))), q.assumption ? h("span", { class: "sub", text: tr("Assumed meanwhile: {assumption}", { assumption: q.assumption }) }) : null,
      q.options && q.options.length ? h("span", { class: "sub clamp2", text: tr("Options: {v}", { v: q.options.map((o) => (o === q.recommended ? `${o} (${tr("recommended")})` : o)).join(" · ") }) }) : null);
    const deniedGroups = groupBy(denied, (m) => `${m.agent || ""}|${m.tool || ""}`);
    const hidden = Math.max(0, (data.denied_total || 0) - denied.length);
    const groups = [
      ["health", tr("Production is failing its health check"), hneeds.map(healthRow), "stable"],
      ["approve", tr("Releases waiting for your approval"), waitingRel.map((r) => h("li", {}, h("span", { class: "id", text: r.id }),
        h("span", { text: tr("{title} · {v} closed", { title: r.title, v: plural(r.closed.length, "milestone") }) }),
        h("button", { type: "button", class: "link-btn", text: tr("Open"), onclick: () => openRelease(r.id) }),
        r.review_doc ? h("span", { class: "sub" }, docLink(r.review_doc, tr("Open the release review"))) : null,
        releaseDecision(r))), "releases"],
      ["qa", tr("QA rounds used up"), stuck.map(qaDecisionRow), "construction"],
      ["confirm", tr("Confirm before building"), cneeds.map(checkpointRow), cpPrd ? "conception" : "planning"],
      ["hotfix", tr("Open hotfixes"), hot.map((id) => hotfixRow(id, b)), "construction"],
      ["blocked", tr("Blocked tasks"), blockedItems, "construction", { count: blocked.length }],
      ["questions", tr("Open questions"), data.questions.map(qRow), null],
      ["queue", tr("Issue queue"), qneeds.map(queueNeedRow), "planning"],
      ["debt", tr("Deferred debt above the cap"), dneeds.map(debtRow), "construction"],
      ["lessons", tr("Proposed lessons"), lneeds.map(lessonRow), "construction"],
      ["denied", tr("Denied because nobody answered"), deniedGroups.map(([, list]) => deniedRow(list[0], list.length)), null,
        { count: denied.length + hidden, foot: hidden ? h("p", { class: "needs-hint", text: tr("{v} more not listed here: see them in Claude Code with /dev-kit:settings.", { v: hidden }) }) : null }],
      ["warnings", tr("Warnings"), warns.map((w) => h("li", {}, h("span", { class: "id", text: "!" }), h("span", { class: "clamp2", text: w }))), null],
    ].filter((g) => g[2].length);
    fill($("impediments"), groups.map(([key, title, items, phase, opt], i) => foldList(`needs:${key}`, title, items, { phase, open: i < 2, ...(opt || {}) })),
      data.questions.length || blocked.length ? h("p", { class: "needs-hint" }, tr("Answer in Claude Code with "), cmd("/dev-kit:interview --gaps")) : null);
  }
  /** Needs you › QA rounds used up (conventions §7): keep fixing (+1 round), accept with an ADR (a justification), or replan. */
  function qaDecisionRow(m) {
    const q = qaState(m);
    const head = [h("span", { class: "id", text: m.id }),
      h("span", { text: tr("{v} fix rounds used of {max} ({v2}).", { v: Math.max(0, q.qa.runs - 1), max: q.max, v2: qaReason(q.qa, m) || tr("see the QA report") }) })];
    return h("li", {}, ...head, h("span", { class: "sub" }, tr("Decide in Claude Code with "), cmd(`/dev-kit:qa ${m.id}`)));
  }
  /** Needs you › a blocked task, and the question it waits on (decided in Claude Code). */
  function blockedRow(id, t, grouped) {
    const q = data.questions.find((x) => x.task === id);
    const head = h("button", { type: "button", class: "row-btn", "data-tid": id, "aria-haspopup": "dialog", onclick: () => openTask(id) },
      h("span", { class: "id", text: id }), h("span", { text: t.title }), h("span", { class: "chip", text: t.milestone }),
      grouped ? null : h("span", { class: "sub bad clamp2", text: t.blocked_reason || tr("No reason recorded") }));
    return h("li", { class: "has-btn" }, head, q ? h("span", { class: "sub" }, tr("Waiting on {id}: ", { id: q.id }), linkify(q.question)) : null);
  }
  /** Needs you › an open hotfix and where it is. */
  function hotfixRow(id, b) {
    const t = data.tasks[id] || {};
    const head = [issueId(id), h("span", { text: t.title || ((b.issues || {})[id] || {}).title || "" }), h("span", { class: "chip lane-hotfix", text: tr("hotfix") }),
      t.status ? h("span", { class: "chip", text: stLabel(t.status) }) : null];
    return h("li", {}, ...head);
  }
  /** Needs you › Confirm PRD / Confirm plan (conventions §19): the document opens formatted in the side drawer; the
   * confirmation (or the changes asked) is given in Claude Code. */
  function checkpointRow(x) {
    const doc = hasDoc(x.doc) ? docLink(x.doc, tr("Open {doc}", { doc: x.doc })) : h("span", { class: "sub", text: x.doc });
    const head = [h("span", { class: "id", text: x.target === "prd" ? tr("PRD") : tr("Plan") }),
      h("span", { text: tr("{title}{v}: the review passed; nothing {v2} until you confirm.", { title: x.title, v: x.round > 1 ? tr(" · round {round}", { round: x.round }) : "", v2: x.target === "prd" ? tr("after the PRD") : tr("new is built") }) }),
      h("span", { class: "sub" }, doc)];
    const summary = x.summary ? h("div", { class: "sub cp-summary" }, linkify(x.summary)) : null;
    return h("li", {}, ...head, summary, h("span", { class: "sub" }, tr("Confirm in Claude Code with "), cmd("/dev-kit:backlog")));
  }
  /** Needs you › deferred debt above the cap (conventions §7): promote, accept or cool-down, decided in Claude Code. */
  function debtRow(x) {
    const head = [h("span", { class: "id", text: "!" }), h("span", { text: tr("{total} deferred findings open (cap {cap_total}) · {medium} medium (cap {cap_medium}).", { total: x.total, cap_total: x.cap_total, medium: x.medium, cap_medium: x.cap_medium }) })];
    return h("li", {}, ...head, h("span", { class: "sub" }, tr("Decide in Claude Code with "), cmd("/dev-kit:backlog")));
  }
  /** Needs you › a proposed lesson of method for one agent (conventions §13), with the evidence that raised it; it is
   * approved or dismissed in Claude Code. An approved lesson goes into every prompt of that agent. */
  function lessonRow(x) {
    const head = [h("span", { class: "id", text: x.agent }), h("span", { text: x.text }), h("span", { class: "sub", text: tr("Why: {evidence}", { evidence: x.evidence }) })];
    return h("li", {}, ...head, h("span", { class: "sub" }, tr("Decide in Claude Code with "), cmd("/dev-kit:feedback")));
  }
  /** A failing production health check: its expedite issue, how many checks failed, and the way to a hotfix. */
  function healthRow(x) {
    const fix = x.tasks && x.tasks.length ? `/dev-kit:implement ${x.tasks[x.tasks.length - 1]}` : `/dev-kit:issue ${x.issue}`;
    return h("li", {}, h("span", { class: "id", text: x.issue }),
      h("span", { text: tr("{v} · last: {detail}", { v: plural(x.failures, "failed check"), detail: x.detail || "?" }) }),
      h("span", { class: "chip lane-hotfix", text: tr("expedite") }),
      h("span", { class: "sub", text: x.target || "" }),
      cmd(fix));
  }
  /** Needs you › the issue queue (conventions §15): above the limit, or an issue waiting too long; planned in Claude Code. */
  function queueNeedRow(x) {
    if (x.kind === "queue_over_limit") {
      return h("li", {}, h("span", { class: "id", text: "!" }),
        h("span", { text: tr("Queue above the limit: {v} waiting (limit {limit}).", { v: plural(x.count, "issue"), limit: x.limit }) }),
        h("span", { class: "sub" }, tr("Plan it in Claude Code with "), cmd("/dev-kit:backlog")));
    }
    return h("li", {}, issueId(x.issue),
      h("span", { text: tr("{v} · waiting for {v2}", { v: (issueOf(x.issue) || {}).title || "", v2: plural(x.milestones, "closed milestone") }) }),
      h("span", { class: "sub" }, tr("Decide in Claude Code with "), cmd("/dev-kit:backlog")));
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
  /** One line of who is at work: the first `n` chips, then one "+N" chip (named by role) that opens them all, so 23
   *  agents do not push the kanban off the screen. `make` builds fresh chips each time (the list keeps its handlers). */
  const CHIP_CAP = 3;
  function capChips(make, title, roles) {
    const all = make();
    if (all.length <= CHIP_CAP + 1) return all;
    const rest = all.length - CHIP_CAP;
    const who = groupBy(roles.slice(CHIP_CAP), (r) => r).map(([r, l]) => `${r} ×${l.length}`).join(", ");
    return [...all.slice(0, CHIP_CAP), h("button", { type: "button", class: "run-chip more-chip", title: tr("{v} more at work: {v2}. Show them all", { v: rest, v2: who }),
      text: tr("+{n} more", { n: rest }), onclick: () => openList(title, h("div", { class: "chip-list" }, make())) })];
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
        fun: x.running ? () => inspector(((x.agents || [])[0] || {}).agent || "qa") : null,
        sub: x.passed ? tr("passed{v}", { v: m.score != null ? ` · ${m.score}` : "" }) : x.running ? tr("auditing · round {n}", { n: x.round }) : x.fixActive.length ? tr("fixes {v}/{n}", { v: x.fixes.length - x.fixOpen.length, n: x.fixes.length }) : x.qa.runs ? plural(x.qa.runs, "round") : tr("auditors") } : null,
      qaNode ? { key: "gate", label: tr("Gate"), kind: "gate", stage: qaNode, about: tr("Hard floor, exit check and cut-offs: a failed gate creates fix tasks and a new round"),
        state: x.passed ? "done" : gateFailed ? "failed" : "todo", here: gateFailed,
        fun: () => trafficLight(x.passed ? "passed" : gateFailed ? "failed" : x.running ? "checking" : "waiting", gateFailed ? gateFailedRule(m) : 0), need: gateFailed ? 1 : 0, needText: tr("decide"),
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
      const running = here.tasks.filter((t) => t.status === "in_progress").sort((a, b) => (parseT(a.started_at) || 0) - (parseT(b.started_at) || 0));
      const blocked = here.tasks.filter((t) => t.status === "blocked");
      running.forEach((t) => shown.add(t.id));
      const roleName = (a) => (a ? a.agent || "?" : tr("no agent"));
      const chips = capChips(() => [...running.map(runChip), ...(here.agents || []).map((a) => h("span", { class: "run-chip auditor", title: roleOf(a.agent).about || a.agent }, agentBits(a, true)))],
        tr("At work in {id}", { id: m.id }), [...running.map((t) => roleName(agentsOn(t.id)[0])), ...(here.agents || []).map(roleName)]);
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
    const outTasks = Object.entries(data.tasks).filter(([id, t]) => t.status === "in_progress" && !shown.has(id) && t.milestone !== m.id);
    const taskIds = new Set(Object.keys(data.tasks));
    const outAgents = activeAgents().filter((a) => !(a.node && (taskIds.has(a.node) || a.node === `GATE:${m.id}`)));
    const elsewhere = outTasks.length + outAgents.length ? capChips(() => [...outTasks.map(([id, t]) => runChip({ id, ...t })),
      ...outAgents.map((a) => h("span", { class: "run-chip", title: `${roleOf(a.agent).about || a.agent}${a.node ? "" : tr(". Not linked to a task or a QA gate")}` },
        a.node ? h("span", { class: "tid", text: a.node.replace("GATE:", "QA ") }) : h("span", { class: "unlinked", text: tr("not linked") }), agentBits(a, true)))],
    tr("Running outside this milestone"), [...outTasks.map(([id]) => ((agentsOn(id)[0]) || {}).agent || tr("no agent")), ...outAgents.map((a) => a.agent || "?")]) : [];
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
  const feedOpen = new Set();  // bursts the user opened, until the page reloads
  function renderFeed() {
    fill($("log-link"), h("button", { type: "button", class: "link-btn", "aria-pressed": String(fullLog), text: fullLog ? tr("Activity") : tr("Full log"),
      title: fullLog ? tr("Back to what happened") : tr("Every line of .dev/log.md and the session log"), onclick: () => { fullLog = !fullLog; renderFeed(); } }),
      fullLog && hasDoc("log.md") ? [" · ", docLink("log.md", "log.md")] : null);
    const rows = fullLog ? data.log : (data.feed || []);
    const line = (r) => {
      const t = parseT(r.at);
      return h("li", { class: r.kind === "live" ? "feed-live" : r.kind ? `feed-${r.kind}` : null }, h("time", { datetime: r.at, title: Number.isFinite(t) ? fmtDT(t) : r.at, text: Number.isFinite(t) ? agoShort(t) : r.at }),
        h("span", { class: "txt" }, linkify(fullLog ? r.text : feedText(r))));
    };
    // a heading per day, and a burst of the same event (40 issues filed at once) as its newest line plus "N more like it"
    const out = [];
    let day = null;
    for (let i = 0; i < rows.length;) {
      const r = rows[i], t = parseT(r.at);
      const d = Number.isFinite(t) ? new Date(t).toLocaleDateString(LANG, { weekday: "short", month: "short", day: "numeric" }) : "";
      if (d && d !== day) { day = d; out.push(h("li", { class: "feed-day", "aria-hidden": "true", text: d })); }
      let j = i + 1;
      while (!fullLog && r.kind && r.kind !== "live" && j < rows.length && rows[j].kind === r.kind) j += 1;
      const key = `${r.kind}@${r.at}`;
      out.push(line(r));
      if (j - i >= 3 && !feedOpen.has(key)) {
        out.push(h("li", { class: "feed-burst" }, h("button", { type: "button", class: "link-btn", text: tr("{v} more like this", { v: j - i - 1 }),
          onclick: () => { feedOpen.add(key); renderFeed(); } })));
      } else rows.slice(i + 1, j).forEach((x) => out.push(line(x)));
      i = j;
    }
    fill($("feed"), rows.length ? out : h("li", {}, h("span", { class: "txt", text: tr("No activity logged yet.") })));
    fill($("foot"), tr("Read-only view of {project}/.dev · autonomy {v}", { project: data.project, v: data.autonomy || "?" }));
    const b = data.board;
    fill($("server-about"), b ? tr("Server pid {pid} on port {port}", { pid: b.pid, port: b.port }) : tr("Server details unknown"), tr(". Stop it here or with "), cmd("/dev-kit:board stop"), ".");
  }

  // ------------------------------------------------------------------ insights: quality (definition of done) and backlog
  const VERDICT_WORD = tmap({ pass: N_("pass"), passed: N_("passed"), skipped: N_("skipped"), "n/a": N_("not needed"), fail: N_("fail"), pending: N_("pending") });
  function dodRow(name, score, cut, verdict, links) {
    const mm = h("div", { class: "meter" });
    const sp = h("span"); sp.style.width = `${score != null ? Math.min(100, score) : 0}%`;
    const c = h("span", { class: "cut", title: tr("cut-off {cut}", { cut }) }); c.style.left = `calc(${cut}% - 1px)`;
    mm.append(sp, c);
    const ok = verdict === "pass" || verdict === "passed" || verdict === "skipped" || verdict === "n/a";
    const bad = verdict === "fail" || (score != null && score < cut && !ok);
    return h("div", { class: "dod-row" }, h("span", { class: "name" }, name, " ",
      h("span", { class: `badge ${ok ? "good" : bad ? "bad" : "neutral"}`, text: ok ? `✓ ${VERDICT_WORD[verdict] || verdict}` : bad ? tr("✕ below cut-off") : VERDICT_WORD[verdict || "pending"] || verdict }),
      links && links.length ? h("span", { class: "dod-links" }, links) : null),
      h("span", { class: "score", text: score != null ? `${score} / ${cut}` : `— / ${cut}` }), jumpLane(score, cut, ok, bad), mm);
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
    const gRow = (m) => dodRow(`${m.id} ${m.title || ""}`, m.score ?? null, q.min_overall, m.gate === "pending" ? "fail" : m.gate,
      [`qa/${m.id}/report.md`, `qa/${m.id}/risk-report.md`].filter(hasDoc).map((p) => docLink(p, p.endsWith("risk-report.md") ? tr("risk report") : tr("report"))));
    const ran = data.milestones.filter(gStarted).reverse();
    const pending = data.milestones.filter((m) => !gStarted(m)).map((m) => m.id);
    const debt = (data.backlog || {}).debt;
    // many gates: one folding group per release, newest first; released ones fold, and each group says its exceptions
    // (a gate that took fix rounds or is still failing) so the past is read by exception, not row by row
    const rp = relPlan();
    let body;
    if (rp.length && ran.length > 8) {
      const odd = (m) => (m.qa && m.qa.runs > 1) || !isClosed(m);
      const inRel = new Set(rp.flatMap((r) => r.milestones));
      const sets = rp.slice().reverse().map((r) => ({ key: r.id, title: `${r.id} · ${r.title || ""}`, open: r.status !== "released", ms: ran.filter((m) => r.milestones.includes(m.id)) }))
        .concat([{ key: "none", title: tr("In no release"), open: true, ms: ran.filter((m) => !inRel.has(m.id)) }]).filter((g) => g.ms.length);
      body = sets.map((g) => {
        const n = g.ms.filter(odd).length;
        return foldList(`gates:${g.key}`, [g.title, n ? h("span", { class: "chip bad", text: tr("{v} with fix rounds or failing", { v: n }) }) : null],
          g.ms.map((m) => h("li", { class: `dod-li${odd(m) ? " odd" : ""}` }, gRow(m))), { open: g.open || n > 0 && !isClosed(g.ms[0]), cap: 8 });
      });
    } else body = ran.length ? h("div", { class: "list" }, ran.map(gRow)) : null;
    fill($("dod"), body || (!pending.length ? h("div", { class: "empty", text: tr("No milestones yet.") }) : null),
      pending.length ? h("p", { class: "pending-line clamp2", title: pending.join(", "), text: tr("Not run yet: {v}", { v: pending.length > 12 ? `${pending.slice(0, 12).join(", ")} … (${pending.length})` : pending.join(", ") }) }) : null,
      debt && debt.total ? h("p", { class: `pending-line${debt.over ? " bad" : ""}`, text: debtLine(debt) }) : null);
  }

  const issueId = (id) => (hasDoc("issues.md") ? docLink("issues.md", String(id), String(id), "id") : h("span", { class: "id", text: String(id) }));
  // the server sends issue fields as codes; the board says them in the reader's language
  const ISSUE_WORD = tmap({ bug: N_("bug"), improvement: N_("improvement"), change: N_("change"), feature: N_("feature"),
    expedite: N_("expedite"), current: N_("current"), standard: N_("standard"), intangible: N_("intangible"),
    open: N_("open"), scheduled: N_("scheduled"), in_progress: N_("in progress"), done: N_("done"), wontfix: N_("won't fix"), duplicate: N_("duplicate"), parked: N_("parked"),
    critical: N_("critical"), high: N_("high"), medium: N_("medium"), low: N_("low") });
  const iw = (v) => (v ? ISSUE_WORD[v] || v : v);
  const SEV_RANK = { critical: 0, high: 1, medium: 2, low: 3 };
  const issueLi = (i) => h("li", {}, issueId(i.id), h("span", { class: "clamp2", text: i.title || "" }),
    h("span", { class: `chip${i.c === "expedite" ? " lane-hotfix" : ""}${i.severity === "critical" || i.severity === "high" ? " sev-high" : ""}`, text: iw(i.c || i.status) }),
    h("span", { class: "sub", text: [iw(i.type), iw(i.severity), i.origin === "baseline" ? tr("pre-existing") : null, i.scheduled_in ? `→ ${i.scheduled_in}` : null, i.c && i.status && i.c !== i.status ? iw(i.status) : null].filter(Boolean).join(" · ") }));
  /** Shows a milestone in Construction, from anywhere on the board. */
  function openMilestone(id) {
    selected = id; mobileCol = null;
    setPhase("construction");
  }

  // ------------------------------------------------------------------ QA panel: what the QA & fixes stage is doing now
  // The tab follows the stage the milestone is in: QA & fixes opens the QA tab, Plan and Build the task board.
  // It moves only when the milestone or its stage changes, so a tab the user picks is kept until then
  // (without the way back, the QA tab of the last milestone stayed open on the next one's build).
  let viewFor = null;    // "<milestone>:<stage>" the tab was last moved for
  function autoQaView(m) {
    const here = m && stagesOf(m).find((x) => x.here);
    const key = here ? `${m.id}:${here.key}` : null;
    if (!key || key === viewFor) return;
    viewFor = key;
    const want = here.key === "qa" ? "qa" : here.key === "plan" || here.key === "build" ? "tasks" : null;
    if (want && view !== want) { view = want; applyView(); }
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
    const openBugs = !x.passed && last && last.blocking ? last.blocking.length : 0;
    const fixedN = x.fixes.filter((t) => t.status === "done").length;
    const cols = ["todo", "in_progress", "blocked", "done"].map((k) => [k, x.fixes.filter((t) => t.status === k)]).filter(([, v]) => v.length);
    const fixes = cols.length ? h("div", { class: "qa-fixes" }, cols.map(([k, v]) => h("div", { class: `qa-fix-col s-${k}` },
      h("div", { class: "list-title", text: `${stLabel(k)} ${v.length}` }), v.map((t) => h("button", { type: "button", class: "run-chip", "data-tid": t.id, title: `${t.id} ${t.title || ""}`, onclick: () => openTask(t.id) },
        h("span", { class: "tid", text: t.id }), h("span", { class: "run-title", text: t.title })))))) : h("div", { class: "empty", text: tr("No fix tasks") });
    const hf = m.hard_floor && m.hard_floor.checks ? h("ul", { class: "list" }, Object.entries(m.hard_floor.checks).map(([n, c]) => h("li", {},
      h("span", { class: "id", text: c.status === "fail" ? "✕" : c.status === "pass" ? "✓" : "–" }), h("span", { text: n }),
      c.severity ? h("span", { class: "chip", text: c.severity }) : null, c.task ? h("span", { class: "sub", text: c.task }) : null)))
      : h("div", { class: "empty", text: tr("No deterministic checks recorded yet") });
    const ex = m.exit_check ? h("div", { class: "sub" }, [m.exit_check.cmd ? `cmd: ${m.exit_check.cmd}` : null, m.exit_check.e2e ? `e2e: ${m.exit_check.e2e}` : null,
      (m.exit_check.acs || []).length ? tr("acs: {v}", { v: (m.exit_check.acs || []).join(", ") }) : null].filter(Boolean).join(" · "))
      : h("div", { class: "empty", text: tr("No exit_check in the plan for this milestone") });
    const problems = (m.gate_checks || []).length ? h("ul", { class: "list" }, m.gate_checks.map((g) => h("li", {}, h("span", { class: "id", text: g.hard ? "⛔" : "!" }), h("span", { text: gateText(g.text) })))) : null;
    fill(box, sect(tr("Auditors{v}", { v: r ? tr(" · round {n}", { n: r.n }) : "" }), auditors), sect(tr("Blocking findings open"), openBugs && funOn() ? bugTrail(openBugs) : null, blocking, report ? h("p", { class: "sub" }, docLink(report, tr("Open the QA report"))) : null),
      sect(tr("Fixes"), fixedN && funOn() ? swatter(fixedN) : null, fixes), sect(tr("Hard floor"), hf), sect(tr("Exit check"), ex), problems ? sect(tr("What still stops the gate"), problems) : null);
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
  // Clamping reads every box first and writes after, so a redraw costs two layouts, not two per box and one per card
  // (3.14: a 120-card column and a dozen tiles took 110-180 ms per live update on the stress project).
  /** Read only: what does not fit in one box, and how many rows that is. */
  function clampMeasure(box) {
    const limit = box.getBoundingClientRect().bottom + 1;
    if (box.dataset.clamp === "cards") {
      // a column keeps its first cards: once one does not fit, the ones below it go too
      const kids = [...box.children];
      const first = kids.findIndex((el) => el.getBoundingClientRect().bottom > limit);
      const hide = first >= 0 ? kids.slice(first) : [];
      const extra = Number(box.dataset.extra) || 0;  // cards not drawn at all
      return { hide, cut: hide.length + extra, any: hide.length + extra > 0 };
    }
    // last rows first, so a list keeps its first rows and a block goes as a whole only when none of it fits; hiding a
    // row never moves the rows above it, so every bottom is read from the same layout
    const rows = [...box.querySelectorAll(CLAMP_ROWS)].reverse();
    const bottoms = rows.map((el) => el.getBoundingClientRect().bottom);
    const hide = [];
    const hidden = (el) => hide.some((x) => x.contains(el));
    let cut = 0;
    rows.forEach((el, i) => {
      if (bottoms[i] <= limit || hidden(el)) return;
      cut += el.matches(COUNTED) ? 1 : [...el.querySelectorAll(COUNTED)].filter((c) => !hidden(c)).length;
      hide.push(el);
    });
    return { hide, cut, any: hide.length > 0, rows };
  }
  /** Write only: hides what clampMeasure found; a block left with nothing visible goes too (its title alone says nothing). */
  function clampApply(m) {
    m.hide.forEach((el) => el.classList.add("clamped"));
    (m.rows || []).forEach((el) => { if (!el.classList.contains("clamped") && el.children.length && [...el.children].every((c) => c.classList.contains("clamped") || c.classList.contains("list-title"))) el.classList.add("clamped"); });
  }
  /** Every tile and kanban column keeps the size of the grid: what does not fit goes behind "See all" / "+N more". */
  function clampAll() {
    clampRaf = 0;
    const boxes = [...document.querySelectorAll("[data-clamp]")].filter((box) => box.offsetParent).map((box) => {
      const cards = box.dataset.clamp === "cards";
      return { box, cards, more: box.parentElement.querySelector(cards ? ".col-more" : ".tile-more") };
    });
    const label = (x, n) => (x.cards ? tr("+{n} more", { n }) : n ? tr("See all ({n} more)", { n }) : tr("See all"));
    const reset = (x) => { x.box.querySelectorAll(".clamped").forEach((el) => el.classList.remove("clamped")); };
    boxes.forEach((x) => { reset(x); if (x.more) x.more.hidden = true; });
    boxes.forEach((x) => { x.m = clampMeasure(x.box); });
    boxes.forEach((x) => { clampApply(x.m); if (x.more && x.m.any) { x.more.hidden = false; x.more.textContent = label(x, x.m.cut); } });
    // the button takes room (with its text): measure the boxes that show it again, with it shown
    const again = boxes.filter((x) => x.more && x.m.any);
    again.forEach(reset);
    again.forEach((x) => { x.m = clampMeasure(x.box); });
    again.forEach((x) => clampApply(x.m));
    boxes.forEach((x) => { if (!x.more) return; x.more.hidden = !x.m.any; x.more.textContent = label(x, x.m.cut); });
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
    const fun = !funOn() ? null : x.state === "doing" || (running.length && x.state !== "review") ? stepWriter("architect") : x.state === "review" ? stepReader("requirements-reviewer") : null;
    return h("div", { class: `step-card s-${x.state}${running.length ? " running" : ""}${fun ? " has-fun" : ""}` },
      runBanner(running), fun,
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
        body: [listBlock(tr("Open"), open.map(issueLi), tr("No scope change waiting."), true), issues.length > open.length ? h("p", { class: "pending-line", text: tr("{v} closed", { v: issues.length - open.length }) }) : null] }));
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
  function renderPlanning() {
    const nodes = planNodes();
    const p = phaseOf("planning");
    fill($("pl-strip"), stripHead("planning", tr("The plan and every replan; no milestone starts before the plan is confirmed"),
      h("span", { class: `chip lane-chip st-${laneState("planning")}`, text: PHASE_WORD[p.state === "active" ? "current" : p.state] || "" })),
      flowList(nodes, false, tr("Steps of planning")), stepDetail(nodes));
    // roadmap: releases and their milestones, newest first
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
    // the roadmap is the timeline, newest first: the next releases fold, the past folds, each release's older closed milestones fold
    const keep = [data.current_milestone].filter(Boolean);
    const foldLi = (btn) => h("li", { class: "road-fold" }, btn);
    const relHead = (r, extra) => h("li", { class: `road-rel s-${r.status}` }, extra, h("strong", { text: r.id }), h("span", { class: "road-rel-title", text: r.title }),
      h("span", { class: `chip rel-st-${r.status}`, text: REL_WORD[r.status] }));
    const msPart = (list, key, full) => {
      const f = tlMs(list, key, keep, full);
      return [f.open ? foldLi(tlCloseBtn(key)) : null, ...f.shown.map(row), f.hidden.length ? foldLi(msFoldBtn(f.hidden, key, "road-fold-btn")) : null];
    };
    const roadRows = (full) => {
      if (!rp.length) return msPart(ms.slice().reverse(), "old:all", full);
      if (full) return [...msPart(ms.filter((m) => !relOf(m.id)).reverse(), "", true), ...rp.slice().reverse().flatMap((r) => [relHead(r), ...relMs(r).reverse().map(row)])];
      return tlEntries(keep.map((id) => (relOf(id) || {}).id).filter(Boolean)).flatMap((e) => {
        if (e.fold) return [foldLi(tlFoldBtn(e, "road-fold-btn"))];
        if (e.loose) return msPart(e.loose, "old:loose");
        const r = e.rel, key = `road:${r.id}`, close = e.closeKey ? tlCloseBtn(e.closeKey) : null;
        if (e.past) {
          const opened = tlOpen.has(key);
          const ver = (data.releases || []).filter((v) => v.release === r.id).map((v) => v.tag || v.version).pop();
          return [h("li", { class: `road-rel s-${r.status} has-btn` }, close, h("button", { type: "button", class: "road-rel-btn", "aria-expanded": String(opened),
            title: opened ? tr("Fold these back") : tr("{id} released: show its milestones", { id: r.id }), onclick: () => tlToggle(key) },
            h("span", { class: "road-caret", "aria-hidden": "true", text: opened ? "▾" : "▸" }), h("strong", { text: r.id }), h("span", { class: "road-rel-title", text: r.title }),
            h("span", { class: `chip rel-st-${r.status}`, text: ver ? `✓ ${ver}` : REL_WORD[r.status] }), h("span", { class: "road-count", text: plural(r.milestones.length, "milestone") }))),
            ...(opened ? relMs(r).reverse().map(row) : [])];
        }
        return [relHead(r, close), ...msPart(relMs(r).reverse(), `old:${r.id}`)];
      });
    };
    // the road strip follows the same timeline: one sign per fold, per past release, per milestone in sight
    const roadSigns = () => {
      const sg = [];
      const msSigns = (list, key) => { const f = tlMs(list, key, keep); f.shown.forEach((m) => sg.push({ label: m.id, done: isClosed(m), cur: m.id === data.current_milestone }));
        if (f.hidden.length) sg.push({ label: msRange(f.hidden), done: true, fold: true }); };
      if (!rp.length) { msSigns(ms.slice().reverse(), "old:all"); return sg; }
      tlEntries([]).forEach((e) => {
        if (e.fold) sg.push({ label: tlRange(e.rels), done: !e.future, fold: true });
        else if (e.loose) msSigns(e.loose, "old:loose");
        else if (e.past) sg.push({ label: e.rel.id, done: true, fold: true });
        else msSigns(relMs(e.rel).reverse(), `old:${e.rel.id}`);
      });
      return sg;
    };
    // backlog: the issue queue by class of service, the issues already scheduled, and what later milestones hold
    const b = data.backlog || {};
    const issues = b.issues || {};
    const order = ["expedite", "current", "standard", "intangible", "change"];
    // within a class of service, the most severe first (cost of delay), then the oldest
    const queued = order.flatMap((c) => ((b.queue || {})[c] || []).map((id, k) => ({ id, c, k, ...issues[id] }))
      .sort((x, y) => (SEV_RANK[x.severity] ?? 2) - (SEV_RANK[y.severity] ?? 2) || x.k - y.k));
    const scheduled = Object.entries(issues).filter(([, v]) => ["scheduled", "in_progress"].includes(v.status));
    const curIdx = ms.findIndex((m) => m.id === data.current_milestone);
    const later = ms.slice(curIdx + 1).map((m) => ({ m, left: tasksOf(m).filter((t) => t.status !== "done").length })).filter((x) => x.left);
    const laterTasks = later.reduce((n, x) => n + x.left, 0);
    const fresh = issuesSeen ? queued.filter((i) => !issuesSeen.has(i.id)).map((i) => i.id) : [];
    issuesSeen = new Set(queued.map((i) => i.id));
    const queueBlock = () => {
      const qb = listBlock(tr("Issue queue"), queued.map((i) => { const li = issueLi(i); if (funOn() && fresh.includes(i.id)) li.classList.add("arrived"); return li; }), tr("No issues waiting."), true);
      if (funOn()) qb.firstChild.append(mailCarrier(fresh.length > 0));
      return qb;
    };
    const backBody = () => [queueBlock(),
      scheduled.length ? listBlock(tr("Scheduled issues"), scheduled.map(([id, v]) => issueLi({ id, c: v.class, ...v })), "") : null,
      listBlock(tr("Later milestones"), later.map(({ m, left }) => h("li", { class: "has-btn" },
        h("button", { type: "button", class: "row-btn", title: tr("Show {id} in construction", { id: m.id }), onclick: () => { closeList(); openMilestone(m.id); } },
          h("span", { class: "id", text: m.id }), h("span", { text: m.title || "" }), h("span", { class: "chip", text: plural(left, "task") })))),
      tr("Nothing planned after the current milestone."))];
    const tasks = Object.values(data.tasks).filter((t) => t.status !== "dropped").length;
    const kpi = (label, value) => h("div", { class: "kpi" }, h("span", { class: "fact-label", text: label }), h("strong", { text: String(value) }));
    fill($("pl-tiles"),
      tile({ title: tr("Roadmap"), count: ms.length || null, sub: ms.length ? tr("{closed} of {v} closed", { closed, v: plural(ms.length, "milestone") }) : "",
        body: ms.length ? [roadStrip(roadSigns()), h("ol", { class: "list road" }, roadRows())] : h("div", { class: "empty" }, tr("No milestones yet. They appear after "), cmd("/dev-kit:plan"), "."), all: () => h("ol", { class: "list road" }, roadRows(true)) }),
      tile({ title: tr("Backlog"), count: queued.length + laterTasks || null, sub: tr("{v} · {v2} in later milestones", { v: plural(queued.length, "queued issue"), v2: plural(laterTasks, "task") }),
        body: [runBanner(runsAt("backlog")), ...backBody()], all: backBody }),
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
        need: qneeds, needText: tr("queue"), about: tr("A bug, an improvement or a change: Claude Code classifies it"),
        detail: () => [h("p", {}, tr("Report it in Claude Code with "), cmd("/dev-kit:issue"))] },
      { key: "branch", label: tr("Expedite · standard · change"), kind: "gate", sub: tr("hotfix · next milestone · PRD"), state: "todo", branch: [
        ["expedite", tr("Expedite"), tr("hotfix lane, patch release"), n("expedite")], ["standard", tr("Standard"), tr("the next milestone"), n("standard") + n("current") + n("intangible")],
        ["change", tr("Change"), tr("the PRD, then a replan"), n("change")]] }]));
  }
  /** The last node of Stable branches out like the diagram: three classes of service, each with its queue. */
  function branchNode(n) {
    return h("li", { class: "fnode k-branch" }, h("div", { class: "branch", role: "group", "aria-label": n.label },
      n.branch.map(([k, name, what, count]) => h("button", { type: "button", class: `branch-row b-${k}`, title: what, onclick: () => setPhase(k === "change" ? "conception" : "planning") },
        laneFun(k, count), h("strong", { text: name }), h("span", { class: "branch-what", text: what }), h("span", { class: `branch-n${count ? " on" : ""}`, text: String(count) })))));
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
        : fact(tr("Cost"), tr("not computed"), h("span", { class: "fact-cmd" }, cmd("/dev-kit:costs"))));
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
    // the deploy history, newest first, one line per milestone; failures carry a red badge so they read at a glance
    const deps = ms.filter((m) => m.deploy && m.deploy.at).sort((a, b) => (parseT(b.deploy.at) || 0) - (parseT(a.deploy.at) || 0));
    const depRows = (list) => list.map((m) => h("li", { class: m.deploy.status === "ok" ? null : "odd" }, h("span", { class: "id", text: m.id }),
      h("span", { class: "mono-wrap", text: (m.deploy.sha || "").slice(0, 7) }),
      h("span", { class: `badge ${m.deploy.status === "ok" ? "good" : "bad"}`, text: m.deploy.status === "ok" ? tr("✓ ok") : stLabel(m.deploy.status) }),
      h("span", { class: "sub", text: Number.isFinite(parseT(m.deploy.at)) ? fmtDT(parseT(m.deploy.at)) : "" })));
    const depFails = deps.filter((m) => m.deploy.status !== "ok").length;
    const depBlock = (all) => (deps.length > 1 ? listBlock(depFails ? tr("Deploys · {v} failed", { v: depFails }) : tr("Deploys"), depRows(all ? deps : deps.slice(0, 5)), "") : null);
    const others = Object.keys(data.reviews).filter((k) => !OWN_REVIEWS.includes(k));
    const relRows = () => rel.slice().reverse().map((r) => h("li", {},
      hasDoc(`release-notes-${r.version}.md`) ? docLink(`release-notes-${r.version}.md`, r.tag || r.version, null, "id") : h("span", { class: "id", text: r.tag || r.version || "release" }),
      h("span", { text: (r.release ? `${r.release} · ` : "") + (r.hotfix ? tr("Hotfix {hotfix}", { hotfix: r.hotfix }) : (r.milestones || []).join(", ") || "—") }),
      h("span", { class: "chip", text: r.version || "" }), r.at && Number.isFinite(parseT(r.at)) ? h("span", { class: "sub", text: fmtDate(parseT(r.at)) }) : null));
    const fl = data.flags || [];
    fill($("st-tiles"),
      tile({ title: tr("Project"), sub: data.phase === "stable" ? tr("stable") : PHASE_NAME[data.phase], body: summary }),
      tile({ title: tr("Production"), sub: h("span", { id: "st-prod-sub", text: tr("Deploys {v}", { v: when[lc.deploy_when] || lc.deploy_when || "?" }) }), bodyId: "st-prod", body: [runBanner(runsAt("prod")), ...prod, depBlock(false)], all: () => [...prod.map((n) => n && n.cloneNode(true)), depBlock(true)] }),
      tile({ title: tr("Health check"), sub: data.prod_health ? tr("every {n} min · {target}", { n: data.prod_health.interval_min, target: data.prod_health.target }) : "", bodyId: "st-health",
        body: healthBlock() || h("div", { class: "empty", text: tr("No health check: set autonomy.production.health to watch production.") }) }),
      tile({ title: tr("Release flags"), count: fl.length || null, bodyId: "st-flags", body: flagsBlock() || h("div", { class: "empty", text: tr("No release flags.") }), all: () => flagsBlock() }),
      tile({ title: tr("Release checks"), sub: tr("Cut-off: reviews {review_min_overall} · usability {min_overall}", { review_min_overall: data.quality.review_min_overall, min_overall: data.quality.min_overall }),
        body: [runBanner(runsAt("checks")), reviewList(["ux", "docs", ...others], tr("No checks."))], all: () => reviewList(["ux", "docs", ...others], tr("No checks.")) }),
      tile({ title: tr("Releases"), count: rel.length || null, sub: tr("Newest first"),
        body: [runBanner(runsAt("releases")), trophyShelf(rel), rel.length ? h("ul", { class: "list" }, relRows()) : h("div", { class: "empty", text: tr("No release yet. Closed milestones wait for the next release.") })], all: () => h("ul", { class: "list" }, relRows()) }));
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
      heartbeat(hc),
      last ? h("p", { class: "hc-hist" }, dots) : h("p", { class: "pending-line" }, tr("Not run yet: the board runs it while it is open, or run "), cmd("/dev-kit:deploy --health")));
  }
  /** Release flags (autonomy.release_flags): which release is switched on in production. */
  function flagsBlock() {
    const fl = data.flags || [];
    if (!fl.length) return null;
    const word = tmap({ on: N_("on"), off: N_("off"), removed: N_("removed") });
    // newest release first (the flag you are about to switch), removed ones last
    const num = (f) => Number(String(f.release || "").replace(/\D/g, "")) || 0;
    const sorted = fl.slice().sort((a, b) => (a.state === "removed") - (b.state === "removed") || num(b) - num(a));
    return h("ul", { class: "list" }, sorted.map((f) => h("li", {}, flagPole(f.state), h("span", { class: "id", text: f.release }), h("span", {}, h("code", { text: f.name })),
      h("span", { class: `badge ${f.state === "on" ? "good" : ""}`, text: word[f.state] || f.state }),
      f.cleanup_task && f.cleanup_task !== "pending" ? h("span", { class: "sub", text: tr("removal: {id}", { id: f.cleanup_task }) }) : null)));
  }

  // ------------------------------------------------------------------ the map: the five lanes of the flow at once, with where the project is
  // ------------------------------------------------------------------ architecture: the diagram of the system being built
  // docs/diagrams/architecture.svg (served by /api/diagram) drawn by /dev-kit:diagram in Claude Code; the board only shows it
  const DIAGRAM_NEW = "/dev-kit:diagram", DIAGRAM_UPDATE = "/dev-kit:diagram update";
  let archZoom = false;
  const diagramBusy = () => [DIAGRAM_NEW, DIAGRAM_UPDATE].map((c) => runningRun(c)).find(Boolean) || null;
  function renderArch() {
    const d = data.diagram || { exists: false };
    const busy = diagramBusy();
    const sub = $("arch-sub");
    if (d.exists) {
      fill(sub, d.at ? tr("High-level view of the system being built, drawn on {v}", { v: fmtDT(d.at) }) : tr("High-level view of the system being built"),
        d.stale || !d.current ? h("span", { class: "stale", text: ` · ${tr("out of date: the architecture changed since")}` }) : null,
        d.stale || !d.current ? [" · ", tr("update it in Claude Code with "), cmd(DIAGRAM_UPDATE)] : null,
        busy ? ` · ${tr("Claude Code is drawing it now")}` : null);
    } else fill(sub, tr("High-level view of the system being built"));
    const v = encodeURIComponent(d.at || "");
    fill($("arch-actions"), d.exists ? h("a", { class: "btn btn-sm", href: `/api/diagram?v=${v}`, target: "_blank", rel: "noopener", text: tr("Open full size") }) : null);
    const view = $("arch-view");
    view.classList.toggle("zoom", archZoom && d.exists);
    view.classList.toggle("has-img", Boolean(d.exists));
    if (d.exists) {
      const img = h("img", { src: `/api/diagram?v=${v}`, alt: tr("Architecture diagram of the system being built"), title: tr("Click to zoom") });
      img.addEventListener("click", () => { archZoom = !archZoom; view.classList.toggle("zoom", archZoom); });
      fill(view, img);
      return;
    }
    fill(view, h("div", { class: "empty" },
      busy ? tr("No diagram yet: Claude Code is drawing it with /dev-kit:diagram. It shows here when it is done.")
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
    const c = data.costs;
    fill($("map-any"), h("strong", { class: "any-title", text: tr("Anytime") }),
      h("button", { type: "button", class: "link-btn", onclick: goNeeds }, tr("Needs you: {n}", { n: needsN })),
      c && Number(c.usd) > 0 ? h("span", { class: "sub", text: tr("Cost so far: US$ {v}", { v: Number(c.usd).toFixed(2) }) }) : null,
      h("span", { class: "any-sp" }),
      h("button", { type: "button", class: "btn btn-sm", text: tr("Activity"), onclick: () => openDrawer(adlg) }));
  }

  function tickAgents() {
    document.querySelectorAll(".agent-time[data-start]").forEach((el) => { el.textContent = dur((Date.now() - parseT(el.dataset.start)) / 1000); });
  }
  setInterval(tickAgents, 1000);

  const issueOf = (id) => ((data.backlog || {}).issues || {})[id];
  /** A permission a round child was denied because nobody answered (information only: the board does not act). */
  function deniedRow(m, n) {
    return h("li", {}, h("span", { class: "id", text: m.tool || "tool" }), h("span", { class: "mono-wrap clamp2", text: m.target || "" }),
      h("span", { class: "q-tags" }, m.agent ? h("span", { class: "chip", text: m.agent }) : null, n > 1 ? h("span", { class: "chip", title: tr("Denied {v} with the same agent and tool", { v: plural(n, "time") }), text: `×${n}` }) : null),
      h("span", { class: "sub", text: m.how === "auditor_skipped"
        ? tr("The auditor went on without it; the round did not stop.") : tr("Denied after the wait; what needed it stopped.") }),
      m.rule ? h("span", { class: "sub" }, tr("Rule to allow it: "), h("code", { text: m.rule })) : null,
      h("span", { class: "sub" }, tr("Allow it in Claude Code with "), cmd("/dev-kit:settings")));
  }

  // the tab says when something waits on the user: "(2) Needs you" in the title and a dot on the icon
  let needsN = 0;
  function updateAttention() {
    if (!data || !data.ok) return;
    const n = needsN;
    document.title = n ? tr("({n}) Needs you · {project}", { n, project: data.project }) : tr("{project} · dev-kit board", { project: data.project });
    const icon = document.querySelector('link[rel="icon"]');
    const want = n ? "/assets/favicon-alert.svg" : "/assets/favicon.svg";
    if (icon && icon.getAttribute("href") !== want) icon.setAttribute("href", want);
  }

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

  // ------------------------------------------------------------------ drawers (Needs you, Activity) and the metrics modal
  const ndlg = $("needs-dialog"), adlg = $("act-dialog"), mdlg = $("metrics-dialog");
  const DRAWERS = [ndlg, adlg, mdlg];
  const drawerFrom = new Map();
  /** One drawer at a time; closing it gives the focus back to what opened it. */
  function openDrawer(d) {
    DRAWERS.forEach((x) => { if (x !== d && x.open) { drawerFrom.delete(x); x.close(); } });
    if (d.open) return;
    drawerFrom.set(d, document.activeElement);
    if (d.showModal) d.showModal(); else d.setAttribute("open", "");
  }
  const closeDrawers = () => DRAWERS.forEach((x) => { if (x.open) { drawerFrom.delete(x); x.close(); } });
  [[ndlg, "needs-close"], [adlg, "act-close"], [mdlg, "metrics-close"]].forEach(([d, c]) => {
    $(c).addEventListener("click", () => d.close());
    d.addEventListener("click", (e) => { if (e.target === d) d.close(); });  // a click on the backdrop
    d.addEventListener("close", () => { const o = drawerFrom.get(d); drawerFrom.delete(d); if (o && o.isConnected) o.focus({ preventScroll: true }); });
  });
  $("needs-btn").addEventListener("click", () => openDrawer(ndlg));
  $("act-btn").addEventListener("click", () => openDrawer(adlg));

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
    const panel = ph;
    syncClock();
    keepFocus(() => {
      // global: the lane tabs, Needs you and activity; below, only the screen of the lane shown
      ["map", "arch", ...LANES].forEach((k) => { $(`phase-${k}`).hidden = k !== panel; });
      document.body.dataset.screen = panel;
      renderImpediments(); renderHeader(); renderFeed();
      applyView();
      if (panel === "map") renderMap();
      else if (panel === "arch") renderArch();
      else if (panel === "conception") renderConception();
      else if (panel === "planning") renderPlanning();
      else if (panel === "construction") {
        renderTabs(); renderMilestone(m); renderStages(m); autoQaView(m);
        if (view === "qa") renderQaPanel(m); else renderKanban(m);
      } else if (panel === "releases") renderReleasesPanel();
      else renderStable();
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
      const text = await r.text();
      // a change on disk that does not change what the board shows (a telemetry line, a heartbeat) costs no redraw
      const same = text.replace(/"generated_at":"[^"]*"/, "");
      if (data && data.ok && same === lastText) { lastUpdate = Date.now(); tickUpdated(); return; }
      lastText = same;
      const next = JSON.parse(text);
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
    const orch = runs.find((r) => r.skill === "autopilot");
    const work = [...runs].reverse().find((r) => !["autopilot", "board"].includes(r.skill));
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
    fill($("doc-path"), h("code", { text: `.dev/${path}` }));
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
