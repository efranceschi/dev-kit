/* dev-kit spog - one page for every dev-kit project on this machine: its state (waiting for you, running, idle, and
   since when) and what needs you. Read-only, like the board: every decision and run happens in Claude Code. No
   dependencies. All untrusted text (names, paths, questions) goes through textContent. */
(() => {
  "use strict";

  const TOKEN = document.querySelector('meta[name="board-token"]').content;

  // ------------------------------------------------------------------ text catalogs (the board's i18n/<lang>.json)
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
  function tr(key, vars) {
    const c = cat().strings || {}, b = base().strings || {};
    return fill_(c[key] != null ? c[key] : b[key] != null ? b[key] : key, vars);
  }
  const N_ = (key) => key;
  function plural(n, one, many) {
    const forms = (cat().plurals || {})[one] || (base().plurals || {})[one];
    let rule = "other";
    try { rule = new Intl.PluralRules(LANG).select(n); } catch (e) { /* other */ }
    const s = forms ? forms[rule] || forms.other : `{n} ${n === 1 ? one : many || one + "s"}`;
    return fill_(s, { n });
  }

  const STATUS_LABEL = { waiting: N_("Waiting for you"), running: N_("Running"), idle: N_("Idle"), missing: N_("Folder not found"),
    not_project: N_("No longer a dev-kit project"), unreadable: N_("Could not read its state") };
  const NEED_LABEL = { session_permission: N_("A session waits for a permission"), session_question: N_("A session waits for your answer"),
    prod_health: N_("Production health"), long_job: N_("Long runs that need a look"), release_approval: N_("Release approvals"), qa_exhausted: N_("QA rounds used up"),
    checkpoint: N_("Confirmations"), hotfix: N_("Hotfixes"), blocked: N_("Blocked tasks"), question: N_("Questions"),
    issue_queue: N_("Issue queue"), debt: N_("Deferred debt above the cap"), lesson: N_("Proposed lessons"), denied: N_("Denied permissions") };
  const PHASE_NAME = { conception: N_("Conception"), planning: N_("Planning"), construction: N_("Construction"), stable: N_("Stable") };
  const FILTERS = [["all", N_("All")], ["waiting", N_("Need you")], ["running", N_("Running")], ["idle", N_("Idle")]];

  let data = null;
  let filter = "all";
  let lastUpdate = 0;
  let es = null;
  let stopped = false;
  let before = new Map();  // path -> needs_total of the last render: a card whose count grows rings once

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
  const fill = (el, ...kids) => { el.replaceChildren(...kids.flat().filter(Boolean)); return el; };
  const parseT = (v) => (v ? new Date(v).getTime() : NaN);
  const LRM = "\u200e";  // keeps a path's last slash at its end in the right-to-left box that cuts it from the left
  const cmd = (text) => h("code", { class: "cmd", text });
  /** How long ago, as a duration: "12 min", "3 h", "2 d". */
  function dur(t) {
    const s = Math.max(0, Math.round((Date.now() - t) / 1000));
    if (s < 60) return tr("{s} s", { s });
    if (s < 3600) return tr("{v} min", { v: Math.floor(s / 60) });
    if (s < 86400) return tr("{v} h", { v: Math.floor(s / 3600) });
    return tr("{v} d", { v: Math.floor(s / 86400) });
  }
  function ago(t) {
    const s = Math.max(0, Math.round((Date.now() - t) / 1000));
    if (s < 5) return tr("just now");
    if (s < 60) return tr("{s} s ago", { s });
    if (s < 3600) return tr("{v} min ago", { v: Math.floor(s / 60) });
    return tr("{v} h ago", { v: Math.floor(s / 3600) });
  }
  const store = { get(k, d) { try { return localStorage.getItem(k) || d; } catch (e) { return d; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } } };

  // ------------------------------------------------------------------ theme and language (the same choices as the board)
  const sysDark = matchMedia("(prefers-color-scheme: dark)");
  let themePref = store.get("board-theme", "auto");
  const effectiveTheme = () => (themePref === "light" || themePref === "dark" ? themePref : sysDark.matches ? "dark" : "light");
  function applyTheme() {
    const v = themePref === "light" || themePref === "dark" ? themePref : "auto";
    if (v === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", v);
    document.documentElement.dataset.effective = effectiveTheme();
    document.querySelectorAll("[data-theme-opt]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeOpt === v)));
    const label = effectiveTheme() === "dark" ? tr("Switch to light theme") : tr("Switch to dark theme");
    $("theme-btn").setAttribute("aria-label", label);
    $("theme-btn").title = label;
  }
  function setTheme(v) { themePref = v; store.set("board-theme", v); applyTheme(); }
  sysDark.addEventListener("change", () => { if (themePref === "auto") applyTheme(); });
  $("theme-btn").addEventListener("click", () => setTheme(effectiveTheme() === "dark" ? "light" : "dark"));
  $("theme-switch").addEventListener("click", (e) => { const b = e.target.closest("[data-theme-opt]"); if (b) setTheme(b.dataset.themeOpt); });

  const LANG_KEY = "board-lang";
  LANG = pickLang(store.get(LANG_KEY, "")) || pickLang(navigator.language) || "en";
  function applyStatic(all) {
    document.documentElement.lang = LANG;
    document.querySelectorAll(all ? "[data-i18n], [data-i18n-once]" : "[data-i18n]").forEach((el) => { el.textContent = tr(el.dataset.i18n || el.dataset.i18nOnce); });
    document.querySelectorAll("[data-i18n-aria-label]").forEach((el) => el.setAttribute("aria-label", tr(el.dataset.i18nAriaLabel)));
    fill($("lang-switch"), LANGS.map((l) => h("button", { type: "button", class: "seg-btn", "data-lang": l, "aria-pressed": String(l === LANG), lang: l, text: LANG_NAME[l] || l })));
  }
  $("lang-switch").addEventListener("click", (e) => {
    const b = e.target.closest("[data-lang]");
    if (!b) return;
    LANG = pickLang(b.dataset.lang) || "en";
    store.set(LANG_KEY, LANG);
    applyStatic(false); applyTheme(); render(); tick();
  });
  applyStatic(true);
  applyTheme();

  // ------------------------------------------------------------------ the options menu
  const menu = $("menu-pop"), menuBtn = $("menu-btn");
  const closeMenu = () => { menu.hidden = true; menuBtn.setAttribute("aria-expanded", "false"); };
  menuBtn.addEventListener("click", (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; menuBtn.setAttribute("aria-expanded", String(!menu.hidden)); });
  document.addEventListener("click", (e) => { if (!menu.hidden && !menu.contains(e.target)) closeMenu(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !menu.hidden) { closeMenu(); menuBtn.focus(); } });
  let armed = false;
  $("stop-btn").addEventListener("click", async () => {
    const btn = $("stop-btn");
    if (!armed) { armed = true; btn.querySelector("span").textContent = tr("Click again to stop"); setTimeout(() => { armed = false; applyStatic(false); }, 4000); return; }
    btn.disabled = true;
    try {
      const r = await fetch("/api/shutdown", { method: "POST", headers: { "X-Board-Token": TOKEN } });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      stopped = true;
      if (es) es.close();
      closeMenu();
      banner(tr("Server stopped. Start it again with "), cmd("/dev-kit:spog"));
      setLive("off", tr("Stopped"));
    } catch (e) {
      btn.disabled = false;
      banner(tr("Could not stop the server ({message}). Use ", { message: e.message }), cmd("/dev-kit:spog stop"));
    }
  });
  function banner(...kids) { const b = $("banner"); b.hidden = !kids.length; fill(b, kids); }

  // ------------------------------------------------------------------ filter
  function renderFilter() {
    const counts = (data && data.counts) || {};
    const n = (k) => (k === "all" ? ((data && data.projects) || []).length : counts[k] || 0);
    fill($("filter"), FILTERS.map(([k, label]) => h("button", { type: "button", class: "seg-btn", "data-filter": k, "aria-pressed": String(k === filter) },
      tr(label), h("span", { class: "seg-n", text: String(n(k)) }))));
  }
  $("filter").addEventListener("click", (e) => { const b = e.target.closest("[data-filter]"); if (b) { filter = b.dataset.filter; render(); } });

  // ------------------------------------------------------------------ one project card
  function needRow(g) {
    const items = g.items || [];
    return h("li", { class: `need need-${g.kind}` },
      h("div", { class: "need-head" }, h("span", { class: "need-label", text: tr(NEED_LABEL[g.kind] || g.kind) }), h("span", { class: "chip bad", text: String(g.n) })),
      items.length ? h("ul", { class: "need-items" }, items.map((i) => h("li", {},
        i.id ? h("span", { class: "id", text: i.id }) : null, i.text ? h("span", { class: "need-text", text: i.text, title: i.text }) : null))) : null,
      g.n > items.length ? h("span", { class: "sub", text: tr("+{n} more", { n: g.n - items.length }) }) : null);
  }
  function facts(p) {
    const out = [];
    if (p.phase) out.push(h("span", { class: "chip", text: tr(PHASE_NAME[p.phase] || p.phase) }));
    if (p.milestone) out.push(h("span", { class: "pfact" }, h("strong", { text: p.milestone.id }), " ",
      tr("{done} of {total} tasks", { done: p.milestone.done, total: p.milestone.total })));
    if (p.autopilot) out.push(h("span", { class: "chip ready", text: tr("Autopilot running") }));
    if (p.round) out.push(h("span", { class: "chip", text: tr("Headless round: {v}", { v: [p.round.skill, p.round.scope].filter(Boolean).join(" ") }) }));
    (p.runs || []).filter((r) => r.skill !== "autopilot").forEach((r) => out.push(cmd(`/dev-kit:${r.skill}${r.scope ? " " + r.scope : ""}`)));
    if (p.agents) out.push(h("span", { class: "pfact", text: plural(p.agents, "agent") }));
    const ss = p.sessions || {};
    const open = (ss.working || 0) + (ss.waiting || 0) + (ss.idle || 0);
    if (open) out.push(h("span", { class: "pfact", text: plural(open, "open session") }));
    return out.length ? h("div", { class: "facts" }, out) : null;
  }
  function card(p) {
    const st = p.status || "idle";
    const since = parseT(p.since);
    const gone = st === "missing" || st === "not_project";
    const grew = (p.needs_total || 0) > (before.get(p.path) || 0) && before.has(p.path);
    const foot = [];
    if (gone) {
      foot.push(h("p", { class: "sub", text: st === "missing" ? tr("The folder was moved or deleted. To take it off this page:") : tr("The project has no .dev/state.json any more. To take it off this page:") }),
        cmd(`/dev-kit:spog forget ${p.path}`));
    } else {
      if (p.next) foot.push(h("p", { class: "next" }, h("span", { class: "sub", text: tr("Next in Claude Code:") }), " ", cmd(p.next)));
      if (p.board && p.board.url) foot.push(h("a", { class: "btn btn-sm", href: p.board.url, target: "_blank", rel: "noopener noreferrer", text: tr("Open board") }));
      else if (p.board && p.board.exposed) foot.push(h("span", { class: "sub", text: tr("Its board is shared on the network: open it with its access link.") }));
      else foot.push(h("span", { class: "sub" }, tr("Board not running: "), cmd("/dev-kit:board")));
    }
    const needs = p.needs || [];
    return h("article", { class: `pcard st-${st}${grew ? " ping" : ""}`, "aria-labelledby": `p-${hash(p.path)}` },
      h("header", { class: "pcard-head" },
        h("h3", { id: `p-${hash(p.path)}`, class: "pname", text: p.name || p.path, title: p.name || p.path }),
        h("span", { class: `pstate s-${st}` }, h("span", { class: "pdot", "aria-hidden": "true" }), tr(STATUS_LABEL[st] || st),
          Number.isFinite(since) && !gone ? h("span", { class: "psince", "data-t": String(since), text: tr("for {v}", { v: dur(since) }), title: new Date(since).toLocaleString(LANG) }) : null)),
      h("p", { class: "ppath", text: p.path + LRM, title: p.path }),
      gone ? null : facts(p),
      needs.length ? h("ul", { class: "needs" }, needs.map(needRow)) : null,
      !gone && !needs.length && st !== "unreadable" ? h("p", { class: "calm-line", text: tr("Nothing needs you here.") }) : null,
      st === "unreadable" ? h("p", { class: "sub", text: tr("The state could not be read (it may be mid-write); it is read again on the next change.") }) : null,
      h("footer", { class: "pcard-foot" }, foot));
  }
  function hash(s) { let x = 0; for (const c of String(s)) x = (x * 31 + c.charCodeAt(0)) | 0; return (x >>> 0).toString(36); }

  // ------------------------------------------------------------------ render
  function render() {
    renderFilter();
    if (!data) return;
    const all = data.projects || [];
    const shown = all.filter((p) => filter === "all" || p.status === filter);
    $("kit-ver").textContent = data.kit ? `v${data.kit}` : "";
    const n = data.needs_total || 0;
    $("needs-n").textContent = String(n);
    $("needs-total").classList.toggle("alert", n > 0);
    $("needs-total").classList.toggle("calm", !n);
    $("needs-sr").textContent = n ? `: ${plural(n, "item")}` : tr(": nothing now");
    const waiting = (data.counts || {}).waiting || 0;
    document.title = n ? tr("({n}) Needs you · dev-kit", { n }) : tr("dev-kit · all projects");
    const icon = document.querySelector('link[rel="icon"]');
    if (icon) icon.href = waiting ? "/assets/favicon-alert.svg" : "/assets/favicon.svg";
    if (!all.length) {
      fill($("projects"), h("div", { class: "empty spog-empty" }, h("strong", { text: tr("No projects yet.") }),
        h("span", {}, tr("A project joins this page when one of these runs in it: "), cmd("/dev-kit:board"), " ", cmd("/dev-kit:spog"))));
    } else if (!shown.length) {
      fill($("projects"), h("div", { class: "empty good spog-empty" }, h("span", { text: tr("No project in this view.") })));
    } else {
      fill($("projects"), shown.map(card));
    }
    before = new Map(all.map((p) => [p.path, p.needs_total || 0]));
    $("main").setAttribute("aria-busy", "false");
  }

  // ------------------------------------------------------------------ data and live updates
  async function load() {
    if (stopped) return;
    try {
      const r = await fetch("/api/projects", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      data = await r.json();
      lastUpdate = Date.now();
      if (!stopped) banner();
      render();
      tick();
    } catch (e) {
      if (!stopped) banner(tr("Could not read the projects ({message}).", { message: e.message }));
    }
  }
  function setLive(cls, text) {
    const l = $("live");
    l.classList.remove("on", "off");
    if (cls) l.classList.add(cls);
    $("live-text").textContent = text;
  }
  function connect() {
    if (stopped || !window.EventSource) { setInterval(load, 5000); return; }
    es = new EventSource("/api/events");
    es.addEventListener("hello", () => { setLive("on", tr("Live")); load(); });
    es.addEventListener("change", load);
    es.addEventListener("bye", () => { es.close(); setLive("off", tr("Stopped")); });
    es.onerror = () => { if (!stopped) setLive("off", tr("Reconnecting…")); };
  }
  function tick() {
    $("updated").textContent = lastUpdate ? tr("Updated {v}", { v: ago(lastUpdate) }) : "";
    // the "for 12 min" of each card moves on its own
    document.querySelectorAll(".psince").forEach((el) => { const t = Number(el.dataset.t); if (Number.isFinite(t)) el.textContent = tr("for {v}", { v: dur(t) }); });
  }
  setInterval(() => { $("updated").textContent = lastUpdate ? tr("Updated {v}", { v: ago(lastUpdate) }) : ""; }, 1000);
  setInterval(() => { if (data) render(); }, 30000);
  renderFilter();
  load();
  connect();
})();
