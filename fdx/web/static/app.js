// fdx-studio dashboard — no build step, feature-detected per-page init.

async function fdxFetch(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
}

function fdxPostJSON(url, body) {
  return fdxFetch(url, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body || {}),
  });
}

function fdxPutJSON(url, body) {
  return fdxFetch(url, {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body || {}),
  });
}

function escapeHtml(s) {
  return (s || '').replace(/[&<>"']/g, c => (
    {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}

// --- live job watcher: streams log/progress/status via SSE -----------------

function watchJob(slug, jobId, handlers) {
  const es = new EventSource(`/api/projects/${slug}/jobs/${jobId}/stream`);
  es.addEventListener('log', e => handlers.onLog && handlers.onLog(JSON.parse(e.data)));
  es.addEventListener('progress', e => handlers.onProgress && handlers.onProgress(JSON.parse(e.data)));
  es.addEventListener('heartbeat', () => handlers.onHeartbeat && handlers.onHeartbeat());
  es.addEventListener('status', e => {
    const data = JSON.parse(e.data);
    handlers.onStatus && handlers.onStatus(data);
    if (data.status !== 'running') es.close();
  });
  es.onerror = () => { /* browser auto-retries; nothing to do here */ };
  return es;
}

// A reusable log-panel + progress-bar block. `root` is a container element
// that already has .log-panel, .progress-bar > .fill, .progress-note,
// .job-status children (see pipeline.html / scenes.html).
function bindJobUI(root, slug, jobId) {
  const logEl = root.querySelector('.log-panel');
  const fillEl = root.querySelector('.progress-bar .fill');
  const barEl = root.querySelector('.progress-bar');
  const noteEl = root.querySelector('.progress-note');
  const statusEl = root.querySelector('.job-status');

  function appendLine(line) {
    if (!logEl) return;
    const div = document.createElement('div');
    div.className = 'line';
    div.textContent = line;
    logEl.appendChild(div);
    logEl.scrollTop = logEl.scrollHeight;
  }

  return watchJob(slug, jobId, {
    onLog: d => appendLine(d.line),
    onProgress: p => {
      if (!barEl) return;
      if (p.mode === 'indeterminate') {
        barEl.classList.add('indeterminate');
      } else {
        barEl.classList.remove('indeterminate');
        const pct = p.total ? Math.min(100, (p.done / p.total) * 100) : 0;
        if (fillEl) fillEl.style.width = pct + '%';
      }
      if (noteEl) noteEl.textContent = p.note || (p.total ? `${p.done}/${p.total}` : '');
    },
    onStatus: s => {
      if (statusEl) {
        statusEl.textContent = s.status;
        statusEl.className = 'job-status ' + s.status;
      }
      document.dispatchEvent(new CustomEvent('fdx:job-done', {detail: s}));
    },
  });
}

// --- page init ---------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('new-project-form')) initProjectsPage();
  if (document.getElementById('sections')) initEditorPage();
  if (document.getElementById('pipeline-panel')) initPipelinePage();
  if (document.getElementById('scenes-root')) initScenesPage();
  if (document.getElementById('upload-root')) initUploadPage();
});

// --- projects.html -------------------------------------------------------

function initProjectsPage() {
  const form = document.getElementById('new-project-form');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('new-project-error');
    errEl.textContent = '';
    try {
      const data = await fdxPostJSON('/api/projects', {
        slug: form.slug.value.trim(),
        title: form.title.value.trim() || null,
      });
      window.location.href = `/projects/${data.slug}/script`;
    } catch (err) {
      errEl.textContent = err.message;
    }
  });
}

// --- editor.html -----------------------------------------------------------

function wpmNote(words, minutes) {
  if (!minutes) return '';
  const wpm = words / minutes;
  if (wpm > 170) return {cls: 'fast', text: `${Math.round(wpm)} wpm — fast, try --speed 0.85`};
  if (wpm < 120) return {cls: 'slow', text: `${Math.round(wpm)} wpm — slow, try --speed 1.1`};
  return {cls: '', text: `${Math.round(wpm)} wpm`};
}

function initEditorPage() {
  const slug = window.FDX_SLUG;
  const script = window.FDX_SCRIPT;
  const sectionsEl = document.getElementById('sections');
  const tmpl = document.getElementById('section-template');
  let nextIndex = 1;

  function addSection(data) {
    data = data || {index: nextIndex, title: '', anim: '', narration: ''};
    nextIndex = Math.max(nextIndex, data.index + 1);
    const node = tmpl.content.cloneNode(true);
    const card = node.querySelector('.section-card');
    card.dataset.index = data.index;
    card.querySelector('.section-num').textContent = data.index;
    card.querySelector('.sec-title').value = data.title || '';
    card.querySelector('.sec-anim').value = data.anim || '';
    card.querySelector('.sec-narration').value = data.narration || '';
    card.querySelector('.remove-section').addEventListener('click', () => {
      card.remove();
      updatePace();
    });
    card.querySelector('.sec-narration').addEventListener('input', updatePace);
    sectionsEl.appendChild(node);
  }

  (script.sections || []).forEach(addSection);

  document.getElementById('add-section').addEventListener('click', () => {
    addSection();
  });

  function collect() {
    const meta = {
      title: document.getElementById('meta-title').value,
      topic: document.getElementById('meta-topic').value,
      audience: document.getElementById('meta-audience').value,
    };
    const sections = Array.from(sectionsEl.querySelectorAll('.section-card')).map((card, i) => ({
      index: i + 1,
      title: card.querySelector('.sec-title').value,
      anim: card.querySelector('.sec-anim').value,
      narration: card.querySelector('.sec-narration').value,
    }));
    return {meta, sections};
  }

  function updatePace() {
    const {sections} = collect();
    const words = sections.reduce((n, s) => n + (s.narration.split(/\s+/).filter(Boolean).length), 0);
    // ~140 spoken wpm is this project's own target (see script.md template).
    const estMinutes = words / 140;
    const note = wpmNote(words, estMinutes);
    const el = document.getElementById('pace-note');
    el.textContent = `${words} words, ~${estMinutes.toFixed(1)} min` + (note.text ? ` — ${note.text}` : '');
    el.className = note.cls || '';
    sectionsEl.querySelectorAll('.section-card').forEach((card, i) => {
      const w = sections[i].narration.split(/\s+/).filter(Boolean).length;
      card.querySelector('.sec-wordcount').textContent = `${w} words`;
    });
  }
  updatePace();
  ['meta-title', 'meta-topic', 'meta-audience'].forEach(id =>
    document.getElementById(id).addEventListener('input', updatePace));

  document.getElementById('save-script').addEventListener('click', async () => {
    const statusEl = document.getElementById('save-status');
    statusEl.textContent = 'saving…';
    statusEl.className = '';
    try {
      await fdxPutJSON(`/api/projects/${slug}/script`, collect());
      statusEl.textContent = 'saved';
      statusEl.className = 'ok-note';
      sectionsEl.querySelectorAll('.draft-badge').forEach(b => b.hidden = true);
    } catch (err) {
      statusEl.textContent = err.message;
      statusEl.className = 'error';
    }
  });

  document.getElementById('draft-ai').addEventListener('click', async (e) => {
    e.target.disabled = true;
    const statusEl = document.getElementById('save-status');
    statusEl.textContent = 'asking the model for a rough draft…';
    statusEl.className = '';
    try {
      const data = await fdxPostJSON(`/api/projects/${slug}/script/draft`, collect());
      document.getElementById('meta-title').value = data.title || '';
      document.getElementById('meta-topic').value = data.topic || '';
      document.getElementById('meta-audience').value = data.audience || '';
      sectionsEl.innerHTML = '';
      nextIndex = 1;
      (data.sections || []).forEach(s => {
        addSection(s);
        const card = sectionsEl.lastElementChild;
        const badge = card.querySelector('.draft-badge');
        badge.hidden = false;
      });
      updatePace();
      statusEl.textContent = 'draft filled in — review, edit, then Save (nothing written to disk yet)';
      statusEl.className = 'ok-note';
    } catch (err) {
      statusEl.textContent = err.message;
      statusEl.className = 'error';
    } finally {
      e.target.disabled = false;
    }
  });
}

// --- pipeline.html -----------------------------------------------------

function initPipelinePage() {
  const slug = window.FDX_SLUG;
  const runningJob = window.FDX_CURRENT_JOB;
  const jobRoot = document.getElementById('job-panel');

  function attach(jobId) {
    jobRoot.hidden = false;
    bindJobUI(jobRoot, slug, jobId);
  }

  if (runningJob) attach(runningJob.id);

  document.querySelectorAll('.stage-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const stage = btn.dataset.stage;
      try {
        const job = await fdxPostJSON(`/api/projects/${slug}/stages/${stage}/run`, {});
        jobRoot.querySelector('.log-panel').innerHTML = '';
        attach(job.id);
      } catch (err) {
        alert(err.message);
      }
    });
  });

  const buildBtn = document.getElementById('build-all');
  if (buildBtn) {
    buildBtn.addEventListener('click', async () => {
      try {
        const job = await fdxPostJSON(`/api/projects/${slug}/build`, {});
        jobRoot.querySelector('.log-panel').innerHTML = '';
        attach(job.id);
      } catch (err) {
        alert(err.message);
      }
    });
  }

  document.addEventListener('fdx:job-done', () => {
    setTimeout(() => window.location.reload(), 1200);
  });
}

// --- scenes.html ---------------------------------------------------------

function initScenesPage() {
  const slug = window.FDX_SLUG;
  document.querySelectorAll('.regen-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const index = btn.dataset.index;
      if (!confirm(`Regenerate section ${index}? This deletes its current storyboard and stills.`)) return;
      btn.disabled = true;
      try {
        const job = await fdxPostJSON(`/api/projects/${slug}/scenes/${index}/regenerate`, {});
        const jobRoot = document.getElementById('scenes-job-panel');
        jobRoot.hidden = false;
        jobRoot.querySelector('.log-panel').innerHTML = '';
        bindJobUI(jobRoot, slug, job.id);
        document.addEventListener('fdx:job-done', () => setTimeout(() => window.location.reload(), 1200), {once: true});
      } catch (err) {
        alert(err.message);
        btn.disabled = false;
      }
    });
  });
}

// --- upload.html -----------------------------------------------------------

function initUploadPage() {
  const slug = window.FDX_SLUG;
  document.querySelectorAll('.audio-upload-form').forEach(form => {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const stem = form.dataset.stem;
      const file = form.querySelector('input[type=file]').files[0];
      const statusEl = form.querySelector('.upload-status');
      if (!file) return;
      const fd = new FormData();
      fd.append('file', file);
      statusEl.textContent = 'uploading…';
      try {
        const res = await fetch(`/api/projects/${slug}/audio/${stem}`, {method: 'POST', body: fd});
        if (!res.ok) throw new Error((await res.json()).detail);
        statusEl.textContent = 'saved — will be used on the next `fdx voice` run';
        statusEl.className = 'upload-status ok-note';
      } catch (err) {
        statusEl.textContent = err.message;
        statusEl.className = 'upload-status error';
      }
    });
  });

  const importForm = document.getElementById('import-form');
  if (importForm) {
    importForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const statusEl = document.getElementById('import-status');
      try {
        const data = await fdxPostJSON(`/api/projects/${slug}/import`,
          {src_dir: importForm.src_dir.value});
        statusEl.textContent = `imported: ${data.imported.join(', ')}`;
        statusEl.className = 'ok-note';
      } catch (err) {
        statusEl.textContent = err.message;
        statusEl.className = 'error';
      }
    });
  }
}
