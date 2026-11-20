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
    else b = h("span", { class: "badge warn" }, "◌ Gate pending");
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
  const INS = ["quality", "burndown", "velocity", "backlog"];
  const COL_LIMIT = 3;       // cards shown per kanban column before "Show all"
  let query = "";            // text filter of the kanban
  let typeFilter = "";       // task type filter of the kanban
  let expanded = new Set();  // kanban columns showing every card
  let mobileCol = null;      // column shown on narrow screens (null = pick the most useful one)
  let goalOpen = false;      // milestone goal expanded
  const INS_KEY = "board-insight-v2";  // v2: Quality became the default tab
  let insTab = INS.includes(store.get(INS_KEY, "")) ? store.get(INS_KEY, "") : "quality";
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
  const agentBits = (x, withRole) => [h("span", { class: "agent-dot", "aria-hidden": "true" }),
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
  function renderHeader() {
    $("project").textContent = data.project;
    $("kit-ver").textContent = data.kit && data.kit !== "unknown" ? `v${data.kit}` : "";
    $("bf-mode").textContent = data.brownfield ? `existing project · ${data.brownfield.mode || "feature"} · since ${data.brownfield.baseline_ref || "baseline"}` : "";
    const phases = data.phases.filter((p) => p !== "init");
    const idx = phases.indexOf(data.phase);
    const done = data.phase === "done";
    const state = (i) => (i < idx || done ? "done" : i === idx ? "current" : "upcoming");
    $("phase-step").textContent = idx >= 0 ? (done ? "All phases complete" : `Step ${idx + 1} of ${phases.length}`) : "";
    // one chevron per phase: done ✓, the current one filled with the accent, the rest waiting
    fill($("phases"), phases.map((p, i) => {
      const st = state(i);
      return h("li", { class: `chev st-${st}${i === idx && !done ? " here" : ""}${Math.abs(i - idx) === 1 || (done && i === phases.length - 1) ? " near" : ""}`, "aria-current": i === idx ? "step" : null, title: `${PHASE_LABEL[p] || p}: ${STAGE_WORD[st]}` },
        h("span", { class: "chev-ico", "aria-hidden": "true", text: st === "done" ? "✓" : String(i + 1) }),
        h("span", { class: "chev-name", text: PHASE_LABEL[p] || p }),
        h("span", { class: "visually-hidden", text: `: ${STAGE_WORD[st]}.` }));
    }));
  }

  function currentId() {
    const ids = data.milestones.map((m) => m.id);
    if (selected && ids.includes(selected)) return selected;
    return data.current_milestone || ids[0] || null;
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
    const ms = data.milestones;
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
    side("earlier", ms.slice(0, a), "earlier");
    side("later", ms.slice(b), "later");
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
    const p = data.progress, c = data.costs;
    const badge = gateBadge(m);
    fill($("ms-facts"),
      h("span", { title: "Tasks done in the whole project", text: `Project ${p.done}/${p.total}` }),
      c && (Number(c.usd) > 0 || Number(c.tokens) > 0) ? h("span", { title: `${compact(c.tokens || 0)} tokens (API-equivalent estimate)`, text: `Cost US$ ${Number(c.usd || 0).toFixed(2)}` })
        : h("span", { class: "fact-cmd", title: "Run /dev-kit:costs to compute the estimated cost" }, "Cost not computed", copyBtn("/dev-kit:costs")),
      badge);
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
    if (view === "plan") return;
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

  // ------------------------------------------------------------------ velocity (one series: done per milestone)
  function renderVelocity(cur) {
    const box = $("velocity");
    const rows = data.milestones.map((m) => {
      const ts = tasksOf(m);
      return { id: m.id, title: m.title, done: ts.filter((t) => t.status === "done").length, total: ts.length };
    }).filter((r) => r.total);
    if (!rows.length) {
      fill(box, h("div", { class: "chart-empty", text: "Velocity appears once milestones have tasks." }));
      fill($("velocity-table"));
      return;
    }
    const W = Math.max(260, Math.round(box.clientWidth || 420)), H = 240, L = 30, R = 8, T = 22, B = 28;
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
      const tipFn = (evt) => showTip(evt, `${r.id} · ${r.title || ""}`, [[`${r.done}`, `done of ${r.total}`, "s1"]]);
      hit.addEventListener("pointermove", tipFn); hit.addEventListener("focus", tipFn);
      hit.addEventListener("pointerleave", hideTip); hit.addEventListener("blur", hideTip);
      svg.append(hit, s("path", { class: `bar${r.id === cur ? " current" : ""}`, d }));
      svg.append(s("text", { class: "label-strong", x: cx, y: top - 6, "text-anchor": "middle", text: String(r.done) }));
      svg.append(s("text", { x: cx, y: H - 8, "text-anchor": "middle", text: r.id }));
    });
    fill(box, svg);
    fill($("velocity-table"), h("table", {}, h("thead", {}, h("tr", {}, h("th", { text: "Milestone" }), h("th", { text: "Done" }), h("th", { text: "Total" }))),
      h("tbody", {}, rows.map((r) => h("tr", {}, h("td", { text: `${r.id} ${r.title || ""}` }), h("td", { text: String(r.done) }), h("td", { text: String(r.total) }))))));
  }

  // ------------------------------------------------------------------ needs you, activity
  function listBlock(title, items, emptyText, good) {
    return h("div", {}, h("div", { class: "list-title" }, title, items.length ? h("span", { class: "chip", text: String(items.length) }) : null),
      items.length ? h("ul", { class: "list" }, items) : h("div", { class: `empty${good ? " good" : ""}`, text: emptyText }));
  }

  function renderImpediments() {
    const blocked = Object.entries(data.tasks).filter(([, t]) => t.status === "blocked");
    const b = data.backlog || {};
    const hot = b.hotfix_open || [];
    const warns = b.warnings || [];
    // milestones past the QA limit with no blocked card to show it (the round failed on scores alone)
    const stuck = data.milestones.filter((m) => qaState(m).exhausted && !qaState(m).fixBlocked.length);
    const approvals = actionsOn() ? inbox().approvals : [];
    const n = blocked.length + data.questions.length + hot.length + stuck.length + approvals.length;
    // the strip exists only while something needs the user; warnings alone ride along but do not open it
    const strip = $("needs");
    strip.hidden = !n;
    $("needs-count").textContent = n ? plural(n, "item") : "";
    needsN = n;
    if (!n) { fill($("impediments")); return; }
    fill($("impediments"),
      approvals.length ? listBlock("Claude Code asks permission", approvals.map(approvalRow), "") : null,
      stuck.length ? listBlock("QA rounds used up", stuck.map((m) => h("li", {}, h("span", { class: "id", text: m.id }),
        h("span", { text: `${qaState(m).qa.runs - 1} fix rounds used of ${qaState(m).max} (${qaReason(qaState(m).qa, m) || "see the QA report"}). Keep fixing, accept with an ADR, or replan.` }),
        h("span", { class: "sub" }, cmd(`/dev-kit:qa ${m.id}`)))), "") : null,
      hot.length ? listBlock("Open hotfixes", hot.map((id) => h("li", {}, h("span", { class: "id", text: String(id) }),
        h("span", { text: (data.tasks[id] || (b.issues || {})[id] || {}).title || "" }), h("span", { class: "chip lane-hotfix", text: "hotfix" }))), "") : null,
      blocked.length ? listBlock("Blocked tasks", blocked.map(([id, t]) => h("li", { class: "has-btn" },
        h("button", { type: "button", class: "row-btn", "data-tid": id, "aria-haspopup": "dialog", onclick: () => openTask(id) },
          h("span", { class: "id", text: id }), h("span", { text: t.title }), h("span", { class: "chip", text: t.milestone }),
          h("span", { class: "sub bad", text: t.blocked_reason || "No reason recorded" })))), "") : null,
      data.questions.length ? listBlock("Open questions", data.questions.map((q) => h("li", {}, h("span", { class: "id", text: q.id }), h("span", {}, linkify(q.question)),
        h("span", { class: "chip", text: q.by || "?" }), q.assumption ? h("span", { class: "sub", text: `Assumed meanwhile: ${q.assumption}` }) : null,
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
  const isFix = (t) => t.type === "fix" && Boolean(t.source);
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
    else if (x.qa.runs) { qaStateName = "current"; qaNote = `Fixes done; round ${x.round} not started. Run`; qaCmdShown = qaCmd; }
    else { qaStateName = "current"; qaNote = "Tasks done; round 1 not started. Run"; qaCmdShown = qaCmd; }
    st.push({ key: "qa", name: "QA & fixes", tasks: x.fixes, agents: x.agents, state: qaStateName, note: qaNote, cmd: qaCmdShown,
      trail: qaTrail(m, x), decide: x.exhausted && !x.fixBlocked.length });
    st.push({ key: "smoke", name: "Smoke test", tasks: [],
      state: !smokeOn ? "na" : m.preview ? "done" : "upcoming",
      note: !smokeOn ? "Local preview off" : m.preview ? (m.preview.pid != null ? "Preview running" : "Passed") : passed ? "Not recorded" : "Runs inside QA" });
    st.push({ key: "deploy", name: "Deploy", tasks: [],
      state: !deployOn ? "na" : dep && dep.status === "ok" ? "done" : dep ? "failed" : passed ? "current" : "upcoming",
      note: !deployOn ? (lc.deploy_when === "on_release" ? "At release" : "Not per milestone")
        : dep && dep.status === "ok" ? `${(dep.sha || "").slice(0, 7)}${dep.at && Number.isFinite(parseT(dep.at)) ? ` · ${fmtDate(parseT(dep.at))}` : ""}`
        : dep ? stLabel(dep.status) : passed ? "Waiting for" : "After the gate",
      cmd: deployOn && passed && !(dep && dep.status === "ok") ? "/dev-kit:deploy" : null });
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
      return h("li", { class: `chev stage st-${x.state}${x.here ? " here" : ""}`, "aria-current": x.here ? "step" : null },
        h("div", { class: "stage-top" }, h("span", { class: "stage-ico", "aria-hidden": "true", text: STAGE_ICON[x.state] }),
          h("span", { class: "stage-name", text: x.name }), h("span", { class: "visually-hidden", text: `: ${STAGE_WORD[x.state]}.` })),
        x.note ? h("span", { class: "stage-note" }, x.note, x.cmd ? [" ", cmd(x.cmd)] : null) : null,
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
    $("dod-sub").textContent = `Cut-off: gates ${q.min_overall} · reviews ${q.review_min_overall}. Rows show the score against its cut-off mark.`;
    const base = ["prd", "design", "plan", "ux", "docs"];
    const revs = [...base.map((k) => [k, data.reviews[k] || {}]), ...Object.entries(data.reviews).filter(([k]) => !base.includes(k))];
    const rname = (k) => (k.length <= 3 ? k.toUpperCase() : k[0].toUpperCase() + k.slice(1));
    const started = (v) => v.score != null || (v.verdict && v.verdict !== "pending");
    const revRows = revs.filter(([, v]) => started(v)).map(([k, v]) => dodRow(rname(k), v.score ?? null, k === "ux" ? q.min_overall : q.review_min_overall, v.verdict));
    const revPending = revs.filter(([, v]) => !started(v)).map(([k]) => rname(k));
    const gStarted = (m) => m.score != null || m.gate !== "pending";
    const gateRows = data.milestones.filter(gStarted).map((m) => dodRow(`${m.id} ${m.title || ""}`, m.score ?? null, q.min_overall, m.gate === "pending" ? "fail" : m.gate));
    const gatePending = data.milestones.filter((m) => !gStarted(m)).map((m) => m.id);
    const block = (title, rows, pending, emptyText) => h("div", {}, h("div", { class: "list-title", text: title }),
      rows.length ? h("div", { class: "list" }, rows) : !pending.length ? h("div", { class: "empty", text: emptyText }) : null,
      pending.length ? h("p", { class: "pending-line", text: `Not run yet: ${pending.join(", ")}` }) : null);
    fill($("dod"), block("Reviews", revRows, revPending, "No reviews."), block("Milestone gates", gateRows, gatePending, "No milestones yet."));
  }

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
    const issueLi = (i) => h("li", {}, h("span", { class: "id", text: i.id }), h("span", { text: i.title || "" }),
      h("span", { class: `chip${i.c === "expedite" ? " lane-hotfix" : ""}`, text: i.c || i.status }),
      h("span", { class: "sub", text: [i.type, i.severity, i.origin === "baseline" ? "pre-existing" : null, i.scheduled_in ? `→ ${i.scheduled_in}` : null].filter(Boolean).join(" · ") }));
    const buf = b.buffer;
    let meter = null;
    if (buf) {
      meter = h("div", { class: "meter" });
      const sp = h("span"); sp.style.width = `${Math.min(100, buf.capacity ? (buf.used / buf.capacity) * 100 : 0)}%`;
      meter.append(sp);
    }
    fill($("product-backlog"),
      listBlock("Issue queue", queued.map(issueLi), "No issues waiting.", true),
      scheduled.length || buf ? h("div", { class: "list-wrap" },
        scheduled.length ? listBlock("Scheduled issues", scheduled.map(([id, v]) => issueLi({ id, c: v.class, ...v })), "") : null,
        buf ? h("div", {}, h("div", { class: "list-title", text: `Issue buffer of ${buf.milestone}` }),
          h("div", { class: "score", text: `${buf.used} of ${plural(buf.capacity, "slot")} used (${buf.pct}% of the milestone reserved for issues)` }), meter) : null) : null,
      listBlock("Later milestones", later.map(({ m, left }) => h("li", { class: "has-btn" },
        h("button", { type: "button", class: "row-btn", title: `Show ${m.id} on the board`, onclick: () => { selectMilestone(m.id, false); $("main").scrollIntoView({ block: "start" }); } },
          h("span", { class: "id", text: m.id }), h("span", { text: m.title || "" }), h("span", { class: "chip", text: plural(left, "task") })))),
        "Nothing planned after this milestone."));
  }

  function renderInsights(m, curId) {
    INS.forEach((k) => {
      const tab = $(`ins-tab-${k}`);
      tab.setAttribute("aria-selected", String(k === insTab));
      tab.tabIndex = k === insTab ? 0 : -1;
      $(`ins-${k}`).hidden = k !== insTab;
    });
    if (insTab === "burndown") renderBurndown(m);
    else if (insTab === "velocity") renderVelocity(curId);
    else if (insTab === "quality") renderDoD();
    else renderBacklog(curId);
  }
  function pickInsight(k, focus) {
    insTab = k; store.set(INS_KEY, k);
    if (data && data.ok) renderInsights(currentMilestone(), currentId());
    if (focus) $(`ins-tab-${k}`).focus();
  }
  $("ins-tabs").addEventListener("click", (e) => { const t = e.target.closest("[data-ins]"); if (t) pickInsight(t.dataset.ins, false); });
  $("ins-tabs").addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    let i = INS.indexOf(insTab);
    i = e.key === "Home" ? 0 : e.key === "End" ? INS.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + INS.length) % INS.length;
    pickInsight(INS[i], true); e.preventDefault();
  });

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
    return x.action;
  }
  const REQ_WORD = { pending: "waiting", running: "running", needs_input: "needs your answer", done: "done", failed: "failed", cancelled: "cancelled", stale: "stopped" };
  function execLabel(ex) {
    if (!ex.online) return ["off", "Claude Code: not running"];
    if (ex.paused) return ["paused", "Claude Code: paused"];
    if (ex.state === "running") return ["on", `Claude Code: working${ex.item ? ` on ${ex.item}` : ""}`];
    if (ex.listening) return ["on", "Claude Code: listening"];
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
  function approvalRow(a) {
    const decide = async (decision, el) => {
      el.disabled = true;
      try { await api(`/api/approvals/${a.id}`, { decision }); toast(`${decision === "allow" ? "Allowed" : "Denied"}: ${a.tool}.`); load(); } catch (e) { el.disabled = false; toast(e.message, true); }
    };
    return h("li", {}, h("span", { class: "id", text: a.tool || "tool" }), h("span", { class: "mono-wrap", text: a.target || "" }),
      h("span", { class: "chip", text: a.request || "" }),
      h("div", { class: "sub answer" },
        h("button", { type: "button", class: "btn btn-sm btn-primary", text: "Allow", onclick: (e) => decide("allow", e.currentTarget) }),
        h("button", { type: "button", class: "btn btn-sm btn-danger", text: "Deny", onclick: (e) => decide("deny", e.currentTarget) })));
  }

  // ------------------------------------------------------------------ plan: drag tasks and issues between open milestones, add the next milestone, send the draft
  let view = "tasks";
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
      h("div", { class: "tcard-title", text: x.title || "" }),
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
  function renderPlan() {
    const box = $("planner");
    if (view !== "plan" || !data || !data.ok) { box.hidden = true; return; }
    if (dragging) return;  // a live update in the middle of a drag would pull the card from under the pointer
    box.hidden = false;
    const model = planModel();
    const column = (key, title, sub, cards, extra, isNew) => {
      const list = h("ol", { class: "pcol-list", "aria-label": `${title}, ${plural(cards.length, "card")}` }, cards.map((c) => planCard(c, model, key === "queue" ? null : key)).filter(Boolean));
      if (!cards.length) list.append(h("li", { class: "col-empty", text: key === "queue" ? "No open issue" : "Drop tasks or issues here" }));
      dropZone(list, key, model);
      return h("section", { class: `pcol${key === "queue" ? " queue" : ""}${isNew ? " new" : ""}` },
        h("div", { class: "col-head" }, h("strong", { text: key === "queue" ? "Issue queue" : key }), key === "queue" || title === key ? null : h("span", { class: "pcol-title", text: title, title }),
          h("span", { class: "count", text: String(cards.length) })),
        sub ? h("p", { class: "card-sub", text: sub }) : null, list, extra);
    };
    const newNum = `M${Math.max(0, ...data.milestones.map((m) => MS_NUM(m.id)), ...draft.ops.filter((o) => o.op === "new_milestone").map((o) => MS_NUM(o.milestone))) + 1}`;
    const hasNew = draft.ops.some((o) => o.op === "new_milestone");
    const b = (data.backlog || {}).buffer;
    const cols = [column("queue", "Issue queue", "Expedite and change issues go through /dev-kit:issue.", model.queued)]
      .concat(model.ms.map((m) => column(m.id, m.title || m.id, m.isNew ? "New in this draft" : b && b.milestone === m.id ? `Issue buffer ${b.used}/${b.capacity}` : null, model.cols[m.id] || [], null, m.isNew)));
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
  }
  function setView(v) {
    view = v;
    document.querySelectorAll("[data-view]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === v)));
    $("board-card").classList.toggle("planning", v === "plan");
    $("board-h").textContent = v === "plan" ? "Plan the milestones" : "Task board";
    renderKanban(currentMilestone());
    renderPlan();
  }
  $("view-switch").addEventListener("click", (e) => { const b = e.target.closest("[data-view]"); if (b) setView(b.dataset.view); });

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
    keepFocus(() => {
      $("view-switch").hidden = !actionsOn();
      if (!actionsOn() && view === "plan") { view = "tasks"; $("board-card").classList.remove("planning"); $("board-h").textContent = "Task board"; }
      renderHeader(); renderTabs(); renderMilestone(m); renderImpediments(); renderStages(m); renderKanban(m); renderPlan();
      renderRequests(); renderFeed(); renderInsights(m, curId);
    });
    updateAttention();
    $("main").setAttribute("aria-busy", "false");
    if (firstRender) {
      firstRender = false;
      const tid = decodeURIComponent(location.hash.slice(1));
      if (TASK_RE.test(tid)) openTask(tid);
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
        d.issue.note ? h("span", { class: "td-note", text: d.issue.note }) : null) : (d.source ? h("p", { text: d.source }) : null)),
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
    if (location.hash) history.replaceState(null, "", location.pathname + location.search);
    if (back) back.focus();
  });
  window.addEventListener("hashchange", () => {
    const tid = decodeURIComponent(location.hash.slice(1));
    if (TASK_RE.test(tid) && tid !== tdCur) openTask(tid);
    else if (!tid && tdlg.open) tdlg.close();
  });

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
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key) || !data || !data.milestones.length) return;
    const ids = data.milestones.map((m) => m.id);
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

  setInterval(tickUpdated, 1000);
  load();
  connect();
})();
