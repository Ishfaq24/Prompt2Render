/* ==========================================================================
   Prompt2Render Studio — front-end controller
   Two sections: Create (topic → build / harness run with live logs) and
   Library (curated videos from `Final Results/`).
   ========================================================================== */
(() => {
  "use strict";

  // ---------------------------------------------------------------- utils --
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const icon = (name) => `<svg><use href="#i-${name}"/></svg>`;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...opts,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch (_) { /* non-JSON */ }
    if (!res.ok) throw new Error((data && data.detail) || `Request failed (${res.status})`);
    return data;
  }

  /** Mirror of cfg.slugify() so the UI can resolve topics instantly. */
  function slugify(text) {
    let c = String(text || "").trim().toLowerCase();
    if (!c) return "";
    c = c.replace(/[\s_/\\]+/g, "-").replace(/[^a-z0-9.-]/g, "").replace(/-+/g, "-")
         .replace(/^[^a-z0-9]+/, "").replace(/[.-]+$/, "");
    return c || "project";
  }

  function fmtDuration(sec) {
    if (sec == null || isNaN(sec)) return "";
    sec = Math.round(sec);
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
  }
  function fmtRuntime(sec) {
    if (!sec) return "0m";
    const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60);
    return h ? `${h}h ${m}m` : `${m}m`;
  }
  function fmtSize(mb) { return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${Math.round(mb)} MB`; }
  function timeAgo(ts) {
    const d = Math.max(0, Date.now() / 1000 - ts);
    if (d < 60) return "just now";
    if (d < 3600) return `${Math.floor(d / 60)}m ago`;
    if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
    return `${Math.floor(d / 86400)}d ago`;
  }

  // --------------------------------------------------------------- toasts --
  function toast(msg, kind = "info", ms = 4200) {
    const el = document.createElement("div");
    el.className = `toast toast--${kind}`;
    el.innerHTML = `${icon(kind === "ok" ? "check" : kind === "err" ? "x" : "sparkles")}<span>${esc(msg)}</span>`;
    $("#toasts").appendChild(el);
    setTimeout(() => { el.classList.add("is-leaving"); setTimeout(() => el.remove(), 260); }, ms);
  }

  async function copyText(text, btn) {
    try {
      await navigator.clipboard.writeText(text);
    } catch (_) {
      const ta = Object.assign(document.createElement("textarea"), { value: text });
      document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove();
    }
    if (btn) {
      btn.classList.add("is-done"); btn.innerHTML = icon("check");
      setTimeout(() => { btn.classList.remove("is-done"); btn.innerHTML = icon("copy"); }, 1400);
    }
  }

  // --------------------------------------------------------------- router --
  const views = ["create", "library"];
  function route() {
    const name = (location.hash || "#create").slice(1);
    const view = views.includes(name) ? name : "create";
    $$("[data-view-panel]").forEach((p) => { p.hidden = p.dataset.viewPanel !== view; });
    $$(".tabs__item").forEach((t) => t.setAttribute("aria-selected", String(t.dataset.view === view)));
    document.title = view === "library" ? "Library · Prompt2Render Studio" : "Prompt2Render Studio";
    if (view === "library" && !Library.loaded) Library.load();
    window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", route);

  // ================================================================ PLAYER ==
  const Player = {
    list: [], index: 0,
    el: $("#player-modal"), video: $("#player-video"),

    open(list, index = 0) {
      this.list = list; this.index = index;
      this.el.hidden = false;
      document.body.style.overflow = "hidden";
      this.render();
    },
    render() {
      const item = this.list[this.index];
      if (!item) return;
      $("#player-title").textContent = item.title;
      $("#player-meta").textContent = item.meta || "";
      const dl = $("#player-download");
      dl.href = item.download || item.src;
      dl.hidden = !item.download;
      this.video.src = item.src;
      this.video.play().catch(() => {});
      const multi = this.list.length > 1;
      $("#player-prev").hidden = !multi;
      $("#player-next").hidden = !multi;
    },
    step(d) {
      if (this.list.length < 2) return;
      this.index = (this.index + d + this.list.length) % this.list.length;
      this.render();
    },
    close() {
      this.video.pause();
      this.video.removeAttribute("src");
      this.video.load();
      this.el.hidden = true;
      document.body.style.overflow = "";
    },
  };
  $$("[data-close]", Player.el).forEach((b) => b.addEventListener("click", () => Player.close()));
  $("#player-prev").addEventListener("click", () => Player.step(-1));
  $("#player-next").addEventListener("click", () => Player.step(1));
  document.addEventListener("keydown", (e) => {
    if (Player.el.hidden) return;
    if (e.key === "Escape") Player.close();
    else if (document.activeElement !== Player.video && e.key === "ArrowRight") Player.step(1);
    else if (document.activeElement !== Player.video && e.key === "ArrowLeft") Player.step(-1);
  });

  // ================================================================ CREATE ==
  const STAGES = {
    build:   ["voice", "align", "scenes", "render", "finish", "qc"],
    harness: ["script", "voice", "align", "scenes", "render", "finish", "qc"],
  };
  const STAGE_LABEL = { script: "Script", voice: "Voice", align: "Align", scenes: "Scenes", render: "Render", finish: "Finish", qc: "QC" };
  const STAGE_RE = {
    script: /\b(outline|draft(ing)?|planner|narration|scaffold)/i,
    voice:  /\b(voice|kokoro|tts|synthes)/i,
    align:  /\b(align|whisper|asr)\b/i,
    scenes: /\b(scenes?|storyboard|generator_manim)\b/i,
    render: /\b(render(ing)?|stills|encode|nvenc|libx264)\b/i,
    finish: /\b(finish|concat|mux|captions?|chapters?|final\.mp4)\b/i,
    qc:     /\b(check|qc|quality gates?|verifier)\b/i,
  };

  const Create = {
    mode: "build",
    minutes: "",
    projects: [],
    pickedSlug: null,
    sugIndex: -1,
    job: null,
    es: null,
    timer: null,
    stageIdx: -1,
    pending: [],
    lineCount: 0,

    input: $("#topic-input"),
    sug: $("#suggestions"),
    term: $("#terminal"),

    async init() {
      this.bind();
      this.setMode("build");
      await this.loadProjects();
      await this.restoreJobs();
    },

    bind() {
      this.input.addEventListener("input", () => { this.pickedSlug = null; this.update(); this.showSuggestions(); });
      this.input.addEventListener("focus", () => this.showSuggestions());
      this.input.addEventListener("blur", () => setTimeout(() => this.hideSuggestions(), 150));
      this.input.addEventListener("keydown", (e) => this.onKey(e));

      $$(".mode").forEach((b) => b.addEventListener("click", () => this.setMode(b.dataset.mode)));
      $$("#duration-group .segmented button").forEach((b) => b.addEventListener("click", () => {
        this.minutes = b.dataset.min;
        $$("#duration-group .segmented button").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
        this.update();
      }));
      $("#opt-manim").addEventListener("change", () => this.update());
      $("#opt-strict").addEventListener("change", () => this.update());
      $("#opt-dialogue").addEventListener("change", () => this.update());
      $("#opt-lang").addEventListener("change", () => this.update());
      $("#copy-cmd").addEventListener("click", (e) => copyText($("#cmd-preview").textContent, e.currentTarget));
      $("#run-btn").addEventListener("click", () => this.run());
      $("#cancel-btn").addEventListener("click", () => this.cancel());
      $("#result-save-lib").addEventListener("click", () => this.saveToLibrary());
    },

    async loadProjects() {
      try { this.projects = await api("/api/studio/projects"); }
      catch (e) { this.projects = []; toast(`Could not load projects: ${e.message}`, "err"); }
      this.renderQuickPicks();
      this.update();
    },

    // ---- topic resolution -------------------------------------------------
    resolve() {
      const topic = this.input.value.trim();
      const slug = this.pickedSlug || slugify(topic);
      if (!slug) return { topic, slug: "", project: null };
      const low = topic.toLowerCase();
      let project = this.projects.find((p) => p.slug === slug)
        || this.projects.find((p) => p.title.toLowerCase() === low) || null;
      if (!project && this.mode === "build" && topic) {
        const fuzzy = this.matches();
        if (fuzzy.length) project = fuzzy[0];
      }
      return { topic, slug: project ? project.slug : slug, project };
    },

    setMode(mode) {
      this.mode = mode;
      $$(".mode").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.mode === mode)));
      const isHarness = mode === "harness";
      $("#duration-group").hidden = !isHarness;
      $("#dialogue-group").hidden = !isHarness;
      $("#lang-group").hidden = !isHarness;
      $("#opt-strict").checked = isHarness;
      $("#run-label").textContent = isHarness ? "Run Harness" : "Run Build";
      this.update();
    },

    commandFor(r) {
      const slug = r.slug || "<topic>";
      const parts = ["python prompt2render.py"];
      if (this.mode === "build") {
        parts.push("build", `<b>${esc(slug)}</b>`);
      } else {
        parts.push("auto", `<b>${esc(slug)}</b>`, "--harness");
        if (r.topic && !r.project) {
          const title = r.topic.charAt(0).toUpperCase() + r.topic.slice(1);
          parts.push(`--title "${esc(title)}"`);
        }
        if (this.minutes) parts.push(`--minutes ${this.minutes}`);
        if ($("#opt-dialogue").checked) parts.push("--dialogue");
        const lang = $("#opt-lang").value;
        if (lang && lang !== "en") parts.push(`--lang ${esc(lang)}`);
      }
      if ($("#opt-manim").checked) parts.push("--manim");
      if ($("#opt-strict").checked) parts.push("--strict");
      return parts.join(" ");
    },

    update() {
      const r = this.resolve();
      $("#cmd-preview").innerHTML = this.commandFor(r);
      const status = $("#topic-status");
      const runBtn = $("#run-btn");
      const busy = this.job && ["queued", "running"].includes(this.job.status) && this.job.slug === r.slug;

      if (!r.slug) {
        status.innerHTML = `<span>Type a topic, or pick one of your existing projects below.</span>`;
        runBtn.disabled = true;
        return;
      }
      const p = r.project;
      let html = "";
      if (p) {
        html += `<span class="st st--ok">${icon("check")} Existing project</span><code>${esc(p.slug)}</code>`;
        html += p.has_video
          ? `<span>· Video ready (${p.video_size_mb} MB)</span><a href="#" data-watch="${esc(p.slug)}">${icon("play")} Watch current video</a>`
          : `<span>· Not rendered yet</span>`;
        if (this.mode === "harness") html += `<span>· Harness will resume it and only redo what fails.</span>`;
      } else if (this.mode === "build") {
        html += `<span class="st st--warn">${icon("x")} No project named</span><code>${esc(r.slug)}</code>`;
        html += `<a href="#" data-use-harness>${icon("layers")} Create it with Harness</a>`;
      } else {
        html += `<span class="st st--new">${icon("sparkles")} New project</span><span>will be created at</span><code>projects/${esc(r.slug)}</code>`;
      }
      status.innerHTML = html;
      runBtn.disabled = Boolean(busy) || (this.mode === "build" && !(p && p.has_script));

      const watch = $("[data-watch]", status);
      if (watch) watch.addEventListener("click", (e) => { e.preventDefault(); this.watchProject(p); });
      const useH = $("[data-use-harness]", status);
      if (useH) useH.addEventListener("click", (e) => { e.preventDefault(); this.setMode("harness"); });
    },

    watchProject(p) {
      Player.open([{
        title: p.title,
        src: `${p.video_url}?v=${p.updated || Date.now()}`,
        download: null,
        meta: `projects/${p.slug}/out/final.mp4 · ${p.video_size_mb} MB`,
      }]);
    },

    // ---- suggestions -----------------------------------------------------
    matches() {
      const q = this.input.value.trim().toLowerCase();
      const scored = this.projects.map((p) => {
        const hay = `${p.title} ${p.slug}`.toLowerCase();
        let score = 0;
        if (!q) score = p.has_video ? 2 : 1;
        else if (p.slug === slugify(q)) score = 100;
        else if (p.title.toLowerCase().startsWith(q) || p.slug.startsWith(slugify(q))) score = 50;
        else if (q.split(/\s+/).every((t) => hay.includes(t))) score = 20;
        return { p, score };
      }).filter((x) => x.score > 0);
      scored.sort((a, b) => b.score - a.score || a.p.title.localeCompare(b.p.title));
      return scored.slice(0, 8).map((x) => x.p);
    },

    showSuggestions() {
      if (document.activeElement !== this.input) return;
      const list = this.matches();
      this.sugIndex = -1;
      if (!list.length) { this.hideSuggestions(); return; }
      const q = this.input.value.trim();
      const hl = (text) => {
        const safe = esc(text);
        if (!q) return safe;
        const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").split(/\s+/).join("|")})`, "ig");
        return safe.replace(re, "<mark>$1</mark>");
      };
      this.sug.innerHTML = list.map((p, i) => `
        <li role="option" data-i="${i}" data-slug="${esc(p.slug)}" aria-selected="false">
          <span class="dot ${p.has_video ? "dot--ok" : ""}" title="${p.has_video ? "Video ready" : "Not rendered"}"></span>
          <span class="suggest__title">${hl(p.title)}</span>
          <span class="suggest__slug">${esc(p.slug)}</span>
        </li>`).join("");
      $$("li", this.sug).forEach((li) => li.addEventListener("mousedown", (e) => {
        e.preventDefault();
        this.pick(this.projects.find((p) => p.slug === li.dataset.slug));
      }));
      this.sug.hidden = false;
    },
    hideSuggestions() { this.sug.hidden = true; this.sugIndex = -1; },

    pick(p) {
      if (!p) return;
      this.input.value = p.title;
      this.pickedSlug = p.slug;
      this.hideSuggestions();
      this.update();
    },

    onKey(e) {
      const items = $$("li", this.sug);
      if (!this.sug.hidden && items.length && ["ArrowDown", "ArrowUp"].includes(e.key)) {
        e.preventDefault();
        this.sugIndex = (this.sugIndex + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        items.forEach((li, i) => li.setAttribute("aria-selected", String(i === this.sugIndex)));
        items[this.sugIndex].scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (!this.sug.hidden && this.sugIndex >= 0) {
          this.pick(this.projects.find((p) => p.slug === items[this.sugIndex].dataset.slug));
        } else {
          this.hideSuggestions();
          this.run();
        }
      } else if (e.key === "Escape") {
        this.hideSuggestions();
      }
    },

    renderQuickPicks() {
      const picks = this.projects.filter((p) => p.has_script)
        .sort((a, b) => Number(b.has_video) - Number(a.has_video) || a.title.localeCompare(b.title))
        .slice(0, 8);
      $("#quick-picks").hidden = !picks.length;
      $("#quick-chips").innerHTML = picks.map((p) => `
        <button type="button" class="chip" data-slug="${esc(p.slug)}">
          <span class="dot ${p.has_video ? "dot--ok" : ""}"></span>${esc(p.title)}
        </button>`).join("");
      $$("#quick-chips .chip").forEach((c) => c.addEventListener("click", () => {
        this.setMode("build");
        this.pick(this.projects.find((p) => p.slug === c.dataset.slug));
        this.input.focus();
      }));
    },

    // ---- run lifecycle ---------------------------------------------------
    async run() {
      const r = this.resolve();
      if (!r.slug) { this.input.focus(); toast("Type a topic first."); return; }
      if ($("#run-btn").disabled) {
        if (this.mode === "build" && !r.project) toast(`No project "${r.slug}" yet — switch to Harness to create it.`, "err");
        return;
      }
      $("#run-btn").disabled = true;
      try {
        const job = await api("/api/studio/run", {
          method: "POST",
          body: {
            topic: r.topic,
            slug: r.slug,
            mode: this.mode,
            manim: $("#opt-manim").checked,
            strict: $("#opt-strict").checked,
            dialogue: this.mode === "harness" && $("#opt-dialogue").checked,
            language: this.mode === "harness" ? $("#opt-lang").value : "en",
            minutes: this.mode === "harness" && this.minutes ? Number(this.minutes) : null,
          },
        });
        toast(`${this.mode === "harness" ? "Harness" : "Build"} started for ${job.slug}`, "ok");
        this.attach(job, true);
        this.loadRecent();
      } catch (e) {
        toast(e.message, "err", 6000);
        this.update();
      }
    },

    attach(job, scroll = false) {
      if (this.es) { this.es.close(); this.es = null; }
      this.job = job;
      this.stageIdx = -1;
      this.lineCount = 0;
      this.pending = [];
      this.term.innerHTML = "";

      $("#run-panel").hidden = false;
      $("#run-result").hidden = true;
      $("#run-mode").textContent = job.mode === "harness" ? "Harness · end-to-end" : "Build · existing project";
      $("#run-topic").textContent = this.titleFor(job);
      $("#run-slug").textContent = job.command;
      $("#logs").open = true;
      const existing = this.projects.find((x) => x.slug === job.slug);
      if (job.mode === "build" && existing && existing.has_video) {
        this.showResult(existing, false);
      }
      this.renderStages(job.mode);
      this.setStatus(job.status);
      this.startTimer(job);
      if (scroll) $("#run-panel").scrollIntoView({ behavior: "smooth", block: "start" });

      this.stream(job);
      this.update();
    },

    titleFor(job) {
      const p = this.projects.find((x) => x.slug === job.slug);
      return p ? p.title : (job.topic || job.slug);
    },

    stream(job) {
      const es = new EventSource(`/api/jobs/${job.job_id}/stream`);
      this.es = es;
      es.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.text) this.pushLine(msg.text);
        if (msg.status && msg.status !== this.job.status) this.setStatus(msg.status);
        if (msg.done) { es.close(); this.es = null; this.finish(msg.status); }
      };
      es.onerror = () => {
        // The stream replays from the start on reconnect, so reattach cleanly.
        es.close();
        if (this.es !== es) return;
        this.es = null;
        setTimeout(async () => {
          try {
            const fresh = await api(`/api/jobs/${job.job_id}`);
            if (this.job && this.job.job_id === fresh.job_id) this.attach(fresh);
          } catch (_) { this.setStatus("failed"); this.stopTimer(); }
        }, 1500);
      };
    },

    pushLine(raw) {
      // Strip ANSI and keep only the last carriage-return segment (progress bars).
      let text = raw.replace(/\x1b\[[0-9;?]*[A-Za-z]/g, "").replace(/\n$/, "");
      if (text.includes("\r")) text = text.split("\r").filter(Boolean).pop() || "";
      this.detectStage(text);
      this.pending.push(text);
      if (!this.flushQueued) {
        this.flushQueued = true;
        requestAnimationFrame(() => this.flush());
      }
    },

    flush() {
      this.flushQueued = false;
      const t = this.term;
      const stick = t.scrollHeight - t.scrollTop - t.clientHeight < 60;
      const frag = document.createDocumentFragment();
      for (const text of this.pending) {
        const ln = document.createElement("span");
        ln.className = "ln" + this.classify(text);
        ln.textContent = text || " ";
        frag.appendChild(ln);
      }
      this.lineCount += this.pending.length;
      this.pending = [];
      t.appendChild(frag);
      while (t.childElementCount > 4000) t.firstElementChild.remove();
      $("#log-count").textContent = `${this.lineCount.toLocaleString()} lines`;
      if (stick) t.scrollTop = t.scrollHeight;
    },

    classify(text) {
      if (/^\[(START|DONE)\]/.test(text)) return " ln--sys";
      if (/(traceback|\berror\b|exception|\bfailed\b|✗)/i.test(text) && !/\b0 (errors?|failed)\b/i.test(text)) return " ln--err";
      if (/\bwarn(ing)?\b/i.test(text)) return " ln--warn";
      if (/(✓|\bpassed\b|\bsuccess|\bok\b)/i.test(text)) return " ln--ok";
      return "";
    },

    renderStages(mode) {
      const keys = STAGES[mode] || STAGES.build;
      $("#stages").innerHTML = keys.map((k, i) => `
        <li class="stage" data-key="${k}"><span class="stage__dot">${i + 1}</span><span>${STAGE_LABEL[k]}</span></li>`).join("");
    },

    detectStage(text) {
      if (!this.job || /^\[(START|DONE)\]/.test(text)) return;
      const keys = STAGES[this.job.mode] || STAGES.build;
      for (let i = keys.length - 1; i > this.stageIdx; i--) {
        if (STAGE_RE[keys[i]].test(text)) { this.setStage(i); break; }
      }
    },

    setStage(idx, final = null) {
      this.stageIdx = idx;
      $$("#stages .stage").forEach((el, i) => {
        el.classList.toggle("is-done", final === "completed" || i < idx);
        el.classList.toggle("is-active", !final && i === idx);
        el.classList.toggle("is-failed", final === "failed" && i === Math.max(idx, 0));
        const dot = $(".stage__dot", el);
        dot.innerHTML = el.classList.contains("is-done") ? icon("check")
          : el.classList.contains("is-failed") ? icon("x") : String(i + 1);
      });
    },

    setStatus(status) {
      if (this.job) this.job.status = status;
      const pill = $("#run-status");
      const label = { queued: "Queued", running: "Running", completed: "Completed", failed: "Failed", cancelled: "Cancelled" }[status] || status;
      pill.textContent = label;
      pill.className = `pill pill--${status}`;
      const active = ["queued", "running"].includes(status);
      $("#cancel-btn").hidden = !active;
      const eng = $("#engine-status");
      eng.classList.toggle("is-busy", active);
      $(".engine__label", eng).textContent = active ? "Rendering…" : "Engine ready";
      if (active && this.stageIdx < 0) this.setStage(0);
    },

    startTimer(job) {
      this.stopTimer();
      const base = job.elapsed_s || 0;
      const t0 = performance.now();
      const tick = () => {
        const running = this.job && ["queued", "running"].includes(this.job.status);
        const secs = running ? base + (performance.now() - t0) / 1000 : (this.job.final_elapsed ?? base);
        $("#run-elapsed").textContent = fmtDuration(secs);
      };
      tick();
      this.timer = setInterval(tick, 1000);
    },
    stopTimer() { if (this.timer) clearInterval(this.timer); this.timer = null; },

    async finish(status) {
      this.setStatus(status);
      try {
        const fresh = await api(`/api/jobs/${this.job.job_id}`);
        this.job.final_elapsed = fresh.elapsed_s;
        $("#run-elapsed").textContent = fmtDuration(fresh.elapsed_s);
      } catch (_) { /* ignore */ }
      this.stopTimer();
      this.setStage(status === "completed" ? (STAGES[this.job.mode] || []).length : this.stageIdx, status);

      await this.loadProjects();
      this.loadRecent();
      if (status === "completed") {
        const p = this.projects.find((x) => x.slug === this.job.slug);
        if (p && p.has_video) this.showResult(p);
        Library.load();
        toast(`${this.titleFor(this.job)} finished and saved to Library`, "ok", 6000);
      } else if (status === "failed") {
        toast(`Run failed — check the live output for details.`, "err", 7000);
      } else if (status === "cancelled") {
        toast("Run cancelled.");
      }
    },

    showResult(p, collapseLogs = true) {
      this.resultProject = p;
      const src = `${p.video_url}?v=${p.updated || Date.now()}`;
      $("#run-result").hidden = false;
      $("#result-video").src = src;
      $("#result-title").textContent = p.title;
      $("#result-meta").textContent = `projects/${p.slug} · ${p.video_size_mb} MB`;
      $("#result-open").href = src;
      $("#result-download").href = src;
      $("#result-download").setAttribute("download", `${p.slug}.mp4`);
      if (collapseLogs) $("#logs").open = false;
    },

    async saveToLibrary() {
      const slug = (this.resultProject && this.resultProject.slug) || (this.job && this.job.slug);
      if (!slug) return;
      const btn = $("#result-save-lib");
      btn.disabled = true;
      try {
        const res = await api(`/api/projects/${encodeURIComponent(slug)}/publish-library`, { method: "POST" });
        toast(`Saved to Final Results/${res.item.filename}`, "ok");
        await Library.load();
      } catch (e) {
        toast(e.message, "err");
      } finally {
        btn.disabled = false;
      }
    },

    async cancel() {
      if (!this.job) return;
      try {
        await api(`/api/jobs/${this.job.job_id}/cancel`, { method: "POST" });
        toast("Stopping run…");
      } catch (e) { toast(e.message, "err"); }
    },

    // ---- recent runs -----------------------------------------------------
    async restoreJobs() {
      const jobs = await this.loadRecent();
      const live = jobs.find((j) => ["queued", "running"].includes(j.status));
      if (live) this.attach(live);
    },

    async loadRecent() {
      let jobs = [];
      try { jobs = await api("/api/jobs?limit=8"); } catch (_) { return []; }
      $("#recent").hidden = !jobs.length;
      $("#recent-list").innerHTML = jobs.map((j) => `
        <li class="recent__item" data-id="${esc(j.job_id)}" tabindex="0">
          <span class="pill pill--${esc(j.status)}">${esc(j.status)}</span>
          <span style="min-width:0">
            <span class="recent__name">${esc(this.titleFor(j))}</span>
            <span class="recent__cmd">${esc(j.command)}</span>
          </span>
          <span class="tag">${j.mode === "harness" ? "Harness" : "Build"}</span>
          <span class="recent__time">${timeAgo(j.created_at)}</span>
        </li>`).join("");
      $$("#recent-list .recent__item").forEach((li) => {
        const open = () => {
          const j = jobs.find((x) => x.job_id === li.dataset.id);
          if (j) this.attach(j, true);
        };
        li.addEventListener("click", open);
        li.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
      });
      return jobs;
    },
  };

  // =============================================================== LIBRARY ==
  const Library = {
    loaded: false,
    items: [],
    lang: "All",
    query: "",
    sort: "name",

    async load() {
      this.loaded = true;
      this.skeleton();
      try {
        const data = await api("/api/library");
        this.items = data.items;
        $("#nav-lib-count").textContent = data.count;
        $("#stat-count").textContent = data.count;
        $("#stat-runtime").textContent = fmtRuntime(data.total_duration_s);
        $("#stat-size").textContent = fmtSize(data.total_size_mb);
        $("#lib-empty-msg").textContent = data.count
          ? "Try a different search or filter."
          : `Drop .mp4 files into the "${data.directory}" folder and refresh.`;
        this.renderChips();
        this.render();
      } catch (e) {
        this.loaded = false;
        $("#lib-grid").innerHTML = "";
        toast(`Could not load library: ${e.message}`, "err");
      }
    },

    skeleton() {
      $("#lib-grid").innerHTML = Array.from({ length: 8 }, () => `
        <div class="skeleton"><div class="skeleton__thumb"></div><div class="skeleton__line"></div><div class="skeleton__line"></div></div>`).join("");
    },

    renderChips() {
      const counts = this.items.reduce((acc, v) => ((acc[v.language] = (acc[v.language] || 0) + 1), acc), {});
      const langs = ["All", ...Object.keys(counts).sort((a, b) => counts[b] - counts[a])];
      const wrap = $("#lang-chips");
      wrap.hidden = langs.length <= 2;
      wrap.innerHTML = langs.map((l) => `
        <button type="button" class="chip" role="radio" data-lang="${esc(l)}" aria-checked="${l === this.lang}">
          ${esc(l)} <span class="chip__count">${l === "All" ? this.items.length : counts[l]}</span>
        </button>`).join("");
      $$(".chip", wrap).forEach((c) => c.addEventListener("click", () => {
        this.lang = c.dataset.lang;
        $$(".chip", wrap).forEach((x) => x.setAttribute("aria-checked", String(x === c)));
        this.render();
      }));
    },

    filtered() {
      const q = this.query.trim().toLowerCase();
      const list = this.items.filter((v) =>
        (this.lang === "All" || v.language === this.lang) &&
        (!q || `${v.title} ${v.filename} ${v.language}`.toLowerCase().includes(q)));
      const by = {
        name: (a, b) => a.title.localeCompare(b.title),
        recent: (a, b) => b.modified - a.modified,
        duration: (a, b) => (b.duration_s || 0) - (a.duration_s || 0),
        size: (a, b) => b.size_bytes - a.size_bytes,
      }[this.sort];
      return list.sort(by);
    },

    render() {
      const list = this.filtered();
      this.current = list;
      $("#lib-empty").hidden = list.length > 0;
      $("#lib-grid").innerHTML = list.map((v, i) => {
        const enc = encodeURIComponent(v.filename);
        const initials = v.title.split(/\s+/).map((w) => w[0]).join("").slice(0, 2);
        return `
        <button type="button" class="vcard" data-i="${i}" style="animation-delay:${Math.min(i, 12) * 35}ms" aria-label="Play ${esc(v.title)}">
          <div class="vcard__thumb is-loading">
            <img src="/library/${enc}/thumbnail" alt="" loading="lazy" decoding="async" data-initials="${esc(initials)}" />
            <div class="vcard__overlay"><span class="vcard__play">${icon("play")}</span></div>
            ${v.duration_s ? `<span class="vcard__dur">${fmtDuration(v.duration_s)}</span>` : ""}
          </div>
          <div class="vcard__body">
            <h3 class="vcard__title">${esc(v.title)}</h3>
            <div class="vcard__meta">
              <span class="tag">${esc(v.language)}</span>
              <span>${v.size_mb} MB</span><span class="sep"></span><span>${esc(v.format.toUpperCase())}</span>
            </div>
            <span class="vcard__file">${esc(v.filename)}</span>
          </div>
        </button>`;
      }).join("");

      $$("#lib-grid .vcard").forEach((card) => {
        const img = $("img", card);
        const thumb = $(".vcard__thumb", card);
        const done = () => { thumb.classList.remove("is-loading"); img.classList.add("is-loaded"); };
        if (img.complete && img.naturalWidth) done();
        img.addEventListener("load", done);
        img.addEventListener("error", () => {
          thumb.classList.remove("is-loading");
          img.remove();
          const fb = document.createElement("div");
          fb.className = "vcard__fallback";
          fb.textContent = img.dataset.initials;
          thumb.prepend(fb);
        });
        card.addEventListener("click", () => this.play(Number(card.dataset.i)));
      });
    },

    play(i) {
      const list = this.current.map((v) => {
        const enc = encodeURIComponent(v.filename);
        return {
          title: v.title,
          src: `/library/${enc}/video`,
          download: `/library/${enc}/video?download=true`,
          meta: [v.language, v.duration_s ? fmtDuration(v.duration_s) : null, `${v.size_mb} MB`, v.filename]
            .filter(Boolean).join("  ·  "),
        };
      });
      Player.open(list, i);
    },
  };

  let searchTimer = null;
  $("#lib-search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { Library.query = e.target.value; Library.render(); }, 120);
  });
  $("#lib-sort").addEventListener("change", (e) => { Library.sort = e.target.value; Library.render(); });

  // ----------------------------------------------------------------- boot --
  route();
  Create.init();
  if (!Library.loaded) Library.load();   // warm the nav count + thumbnails
})();
