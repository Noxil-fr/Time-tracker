'use strict';

// ── Palette donut ──────────────────────────────────────────────────────────
const COLORS = ['#89b4fa','#a6e3a1','#fab387','#f38ba8',
                '#cba6f7','#94e2d5','#f9e2af','#74c7ec'];
const ARCHIVE_DAYS = 30;

// ── State ──────────────────────────────────────────────────────────────────
const S = {
  games:   {},
  active:  {},        // { name: {elapsed, total} }
  version: -1,
  tab:     'games',
  sort:    { key: 'name', asc: true },
  icons:   {},        // exe_path -> base64 data-URI
  history: {
    mode: 'day',
    ref:  _today(),
    gameFilter: null,
    customStart: null,
    customEnd:   null,
  },
  stats: {
    days:        7,
    customStart: null,
    customEnd:   null,
  },
  addDlg: {
    allProcs:    [],
    snapshot:    [],
    newProcs:    [],
    filterNew:   false,
    selectedProc: null,
    selectedExe:  '',
    chipsBuilt:   false,
  },
  retro: { gameName: '', procName: '', startIso: '' },
  deleteTarget: '',
  renameTarget: '',
};

// ── API bridge ─────────────────────────────────────────────────────────────
async function api(method, ...args) {
  if (typeof window.pywebview === 'undefined') return null;
  return window.pywebview.api[method](...args);
}

// ── Helpers ────────────────────────────────────────────────────────────────
function _today() {
  const d = new Date(); d.setHours(0,0,0,0); return d;
}
function _isoDate(d) { return d.toISOString().slice(0,10); }
function _startOfDay(d) {
  const r = new Date(d); r.setHours(0,0,0,0); return r;
}
function _endOfDay(d) {
  const r = new Date(d); r.setHours(23,59,59,999); return r;
}
function _startOfWeek(d) {
  const r = new Date(d);
  r.setDate(r.getDate() - r.getDay() + (r.getDay() === 0 ? -6 : 1));
  r.setHours(0,0,0,0); return r;
}
function _endOfWeek(d) {
  const s = _startOfWeek(d);
  const e = new Date(s); e.setDate(s.getDate() + 6); e.setHours(23,59,59,999); return e;
}
const MONTHS_FR = ['janvier','février','mars','avril','mai','juin',
                   'juillet','août','septembre','octobre','novembre','décembre'];
const DAYS_FR   = ['Dimanche','Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi'];
function _fmtDay(d) {
  return `${DAYS_FR[d.getDay()]} ${d.getDate()} ${MONTHS_FR[d.getMonth()]} ${d.getFullYear()}`;
}
function _fmtWeek(s, e) {
  if (s.getMonth() === e.getMonth())
    return `${s.getDate()} – ${e.getDate()} ${MONTHS_FR[e.getMonth()]} ${e.getFullYear()}`;
  return `${s.getDate()} ${MONTHS_FR[s.getMonth()]} – ${e.getDate()} ${MONTHS_FR[e.getMonth()]} ${e.getFullYear()}`;
}
function _fmtDuration(secs) {
  secs = Math.floor(secs);
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2,'0')}min`;
  if (m > 0) return `${m}min`;
  return `${s}s`;
}
function _fmtLastPlayed(sessions) {
  if (!sessions || sessions.length === 0) return 'Jamais';
  const last = new Date(sessions[sessions.length-1].end);
  const days = Math.floor((Date.now() - last) / 86400000);
  if (days === 0) return "Aujourd'hui";
  if (days === 1) return 'Hier';
  if (days < 7)  return `il y a ${days}j`;
  if (days < 30) return `il y a ${Math.floor(days/7)} sem.`;
  if (days < 365) return `il y a ${Math.floor(days/30)} mois`;
  return `${last.getDate()} ${['jan.','fév.','mar.','avr.','mai','juin',
    'juil.','août','sep.','oct.','nov.','déc.'][last.getMonth()]} ${last.getFullYear()}`;
}
function _cleanName(proc) {
  let n = proc.replace(/\.exe$/i, '');
  n = n.replace(/[\s_-]*(64|32|x64|x86|win64|win32)$/i, '');
  return n.replace(/[_-]/g, ' ').split(' ')
    .filter(Boolean).map(w => w[0].toUpperCase() + w.slice(1)).join(' ');
}
function el(id) { return document.getElementById(id); }
function make(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls)  e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}

// ── Poll ───────────────────────────────────────────────────────────────────
async function poll() {
  try {
    const data = await api('poll');
    if (!data) return;
    S.active = data.active || {};
    _updateTimers();
    for (const ev of (data.events || [])) _handleEvent(ev);
    if (data.version !== S.version) {
      S.version = data.version;
      S.games   = data.games || {};
      if (S.tab === 'games')   renderGames();
      if (S.tab === 'history') renderHistory();
      if (S.tab === 'stats')   renderStats();
      _refreshHistoryFilter();
    }
  } catch(e) { /* ignore */ }
}

function _updateTimers() {
  for (const [name, info] of Object.entries(S.active)) {
    const el_time   = document.querySelector(`.live-time[data-game="${CSS.escape(name)}"]`);
    const el_status = document.querySelector(`.live-status[data-game="${CSS.escape(name)}"]`);
    if (el_time) el_time.textContent = _fmtDuration(info.total);
    if (el_status && !el_status.textContent) el_status.textContent = '● In Game';
  }
}

function _handleEvent(ev) {
  if (ev.type === 'start') {
    showToast(ev.name, 'Suivi démarré', 'blue');
  } else if (ev.type === 'stop') {
    showToast(ev.name,
      `Session : ${_fmtDuration(ev.duration)}  •  Total : ${_fmtDuration(ev.total)}`,
      'green');
  } else if (ev.type === 'suggestion') {
    showToast(`Nouveau jeu détecté : ${ev.game_name}`,
      ev.exe_path ? ev.exe_path.split('\\').slice(-2).join('\\') : '',
      'blue',
      [
        { label: 'Ignorer', action: () => {} },
        { label: 'Ajouter', cls: 'btn-green', action: () => _quickAdd(ev) },
      ]
    );
  }
}

async function _quickAdd(ev) {
  const res = await api('add_game', ev.game_name, ev.proc_name, ev.exe_path);
  if (res?.ok) { S.version = -1; } // force refresh
}

// ── Tab switching ──────────────────────────────────────────────────────────
function switchTab(tab) {
  S.tab = tab;
  document.querySelectorAll('.tab-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.tab-pane').forEach(p =>
    p.classList.toggle('active', p.id === `tab-${tab}`));
  if (tab === 'history') renderHistory();
  if (tab === 'stats')   renderStats();
}

// ── Games tab ──────────────────────────────────────────────────────────────
function renderGames() {
  const container = el('games-list');
  if (!container) return;
  const games = S.games;

  if (Object.keys(games).length === 0) {
    container.innerHTML = '<p class="empty-msg">Aucun jeu ajouté.<br>Cliquez sur « + Ajouter » pour commencer.</p>';
    return;
  }

  const now       = new Date();
  const threshold = new Date(now - ARCHIVE_DAYS * 86400000);
  const activeSet = new Set(Object.keys(S.active));

  // Recent: active OR played in last 30 days
  const recent = Object.entries(games).filter(([n, d]) => {
    if (activeSet.has(n)) return true;
    const sessions = d.sessions || [];
    if (!sessions.length) return false;
    return new Date(sessions[sessions.length-1].end) > threshold;
  }).sort(([an,ad],[bn,bd]) => {
    const aAct = activeSet.has(an), bAct = activeSet.has(bn);
    if (aAct !== bAct) return aAct ? -1 : 1;
    const aLast = ad.sessions?.length ? new Date(ad.sessions[ad.sessions.length-1].end) : new Date(0);
    const bLast = bd.sessions?.length ? new Date(bd.sessions[bd.sessions.length-1].end) : new Date(0);
    return bLast - aLast;
  });

  // All games sorted
  const sorted = _sortedGames(games);

  let html = '';

  // ── Mes jeux récents
  html += '<div class="section-header">Mes jeux récents</div>';
  if (recent.length === 0) {
    html += '<p class="empty-msg" style="padding:20px">Aucun jeu joué récemment.</p>';
  } else {
    recent.forEach(([name, data]) => {
      html += _gameRowHTML(name, data, 'recent', 0);
    });
  }

  // ── Ma bibliothèque
  html += '<div class="section-header" style="margin-top:8px">Ma bibliothèque</div>';
  html += _listHeadersHTML();
  sorted.forEach(([name, data], i) => {
    html += _gameRowHTML(name, data, 'lib', i);
  });

  container.innerHTML = html;

  // Load icons async
  [...recent, ...sorted].forEach(([name, data]) => {
    const exe = data.exe_path || '';
    if (exe) _loadIconsForGame(name, exe);
  });

  // Bind menus
  container.querySelectorAll('.row-menu').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      showCtxMenu(e, btn.dataset.game);
    });
  });
}

function _listHeadersHTML() {
  const { key, asc } = S.sort;
  const arr = asc ? ' ↑' : ' ↓';
  const col = k => key === k ? `sorted" data-sort="${k}` : `" data-sort="${k}`;
  return `<div class="list-headers">
    <div class="h-name"><button class="${col('name')}">${key==='name'?'Jeu'+arr:'Jeu'}</button></div>
    <div class="h-last"><button class="${col('recent')}">${key==='recent'?'Dernier lancement'+arr:'Dernier lancement'}</button></div>
    <div class="h-time"><button class="${col('time')}">${key==='time'?'Temps total'+arr:'Temps total'}</button></div>
    <div class="h-status"></div>
    <div class="h-menu"></div>
  </div>`;
}

function _gameRowHTML(name, data, type, idx) {
  const isActive = name in S.active;
  const activeInfo = S.active[name];
  const sessions = data.sessions || [];
  const isRecent = type === 'recent';
  const isLib    = type === 'lib';
  const altClass = (isLib && idx % 2 === 1) ? ' alt' : '';
  const activeClass = isActive ? ' active-game' : '';

  const time = isActive ? _fmtDuration(activeInfo.total) : _fmtDuration(data.total_seconds || 0);
  const last  = _fmtLastPlayed(sessions);

  const iconId = `icon-${CSS.escape(name)}-${type}`;
  const iconHtml = `<div class="row-icon" id="${iconId}">
    <div class="icon-placeholder">🎮</div>
  </div>`;

  const liveAttr  = isRecent ? ` data-game="${name.replace(/"/g,'&quot;')}"` : '';
  const timeClass = isRecent ? 'row-time' : 'row-time dim';
  const nameClass = isRecent ? 'row-name' : 'row-name dim';
  const lastClass = isRecent ? 'row-last' : 'row-last dim';

  const statusHtml = isRecent
    ? `<div class="row-status live-status"${liveAttr}>${isActive ? '● In Game' : ''}</div>`
    : `<div class="row-status live-status"${liveAttr}>${isActive ? '● In Game' : ''}</div>`;

  const timeHtml = `<div class="${timeClass} live-time"${liveAttr}>${time}</div>`;

  return `<div class="game-row-outer">
    <div class="game-row ${type}${altClass}${activeClass}">
      ${iconHtml}
      <div class="${nameClass}">${_esc(name)}</div>
      <div class="${lastClass}">${last}</div>
      ${timeHtml}
      ${statusHtml}
      <div class="row-menu" data-game="${_esc(name)}">⋮</div>
    </div>
    <div class="game-row-sep"></div>
  </div>`;
}

function _esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function _sortedGames(games) {
  const entries = Object.entries(games);
  const { key, asc } = S.sort;
  const dir = asc ? 1 : -1;
  if (key === 'name') {
    entries.sort(([a],[b]) => dir * a.localeCompare(b));
  } else if (key === 'time') {
    entries.sort(([,a],[,b]) => dir * ((a.total_seconds||0) - (b.total_seconds||0)));
  } else {
    entries.sort(([,a],[,b]) => {
      const as = a.sessions||[], bs = b.sessions||[];
      const at = as.length ? new Date(as[as.length-1].end) : new Date(0);
      const bt = bs.length ? new Date(bs[bs.length-1].end) : new Date(0);
      return dir * (at - bt);
    });
  }
  return entries;
}

// ── Icon loading ────────────────────────────────────────────────────────────
async function _loadIconsForGame(name, exe) {
  if (S.icons[exe] !== undefined) {
    _applyIcon(name, exe);
    return;
  }
  S.icons[exe] = null; // mark as loading
  const b64 = await api('get_icon_b64', exe);
  if (b64) S.icons[exe] = `data:image/png;base64,${b64}`;
  _applyIcon(name, exe);
}

function _applyIcon(name, exe) {
  const src = S.icons[exe];
  if (!src) return;
  document.querySelectorAll(`[id^="icon-${CSS.escape(name)}-"]`).forEach(wrap => {
    wrap.innerHTML = `<img src="${src}" alt="">`;
  });
}

// ── Context menu ───────────────────────────────────────────────────────────
function showCtxMenu(e, name) {
  document.querySelectorAll('.ctx-menu').forEach(m => m.remove());
  const menu = make('div', 'ctx-menu');
  const btnRename = make('button', '', 'Renommer');
  const btnDelete = make('button', 'danger', 'Supprimer');
  btnRename.onclick = () => { menu.remove(); openRenameModal(name); };
  btnDelete.onclick = () => { menu.remove(); openDeleteModal(name); };
  menu.appendChild(btnRename);
  menu.appendChild(document.createElement('hr'));
  menu.appendChild(btnDelete);

  const x = Math.min(e.clientX, window.innerWidth  - 170);
  const y = Math.min(e.clientY, window.innerHeight - 80);
  menu.style.left = x + 'px';
  menu.style.top  = y + 'px';
  document.body.appendChild(menu);
  setTimeout(() => document.addEventListener('click', () => menu.remove(), { once: true }), 0);
}

// ── History tab ────────────────────────────────────────────────────────────
function _refreshHistoryFilter() {
  const sel = el('history-game-filter');
  if (!sel) return;
  const cur = sel.value;
  sel.innerHTML = '<option value="">Tous les jeux</option>' +
    Object.keys(S.games).sort().map(n => `<option value="${_esc(n)}"${n===cur?' selected':''}>${_esc(n)}</option>`).join('');
}

async function renderHistory() {
  _refreshHistoryFilter();
  _buildHistoryNav();
  const { start, end } = _historyRange();
  const filter = S.history.gameFilter || null;
  const sessions = await api('get_sessions',
    start.toISOString(), end.toISOString(), filter);
  if (!sessions) return;

  const list = el('history-list');
  if (!sessions.length) {
    list.innerHTML = '<p class="empty-msg">Aucune session sur cette période.</p>';
    return;
  }

  // Group by day
  const byDay = {};
  sessions.forEach(s => {
    const key = s.start.slice(0, 10);
    (byDay[key] = byDay[key] || []).push(s);
  });

  list.innerHTML = Object.keys(byDay).sort().reverse().map(dayKey => {
    const daySessions = byDay[dayKey];
    const dayTotal = daySessions.reduce((a, s) => a + s.duration, 0);
    const dt = new Date(dayKey + 'T12:00:00');
    const sessRows = daySessions.sort((a,b) => a.start.localeCompare(b.start)).map(s => {
      const st = new Date(s.start), en = new Date(s.end);
      const hm = d => `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
      const gameCol = !filter ? `<span class="s-game">${_esc(s.game)}</span>` : '';
      return `<div class="history-session">
        <span class="s-time">${hm(st)} → ${hm(en)}</span>
        ${gameCol}
        <span class="s-dur">${_fmtDuration(s.duration)}</span>
      </div>`;
    }).join('');
    return `<div class="history-day">
      <div class="history-day-hdr">
        <span>${_fmtDay(dt)}</span>
        <span class="day-total">${_fmtDuration(dayTotal)}</span>
      </div>
      ${sessRows}
    </div>`;
  }).join('');
}

function _historyRange() {
  const h = S.history;
  if (h.mode === 'day') {
    return { start: _startOfDay(h.ref), end: _endOfDay(h.ref) };
  } else if (h.mode === 'week') {
    return { start: _startOfWeek(h.ref), end: _endOfWeek(h.ref) };
  } else {
    const s = h.customStart || _startOfDay(h.ref);
    const e = h.customEnd   || _endOfDay(h.ref);
    return { start: s, end: e };
  }
}

function _buildHistoryNav() {
  const nav = el('history-nav');
  const h   = S.history;
  if (!nav) return;

  if (h.mode === 'day' || h.mode === 'week') {
    const label = h.mode === 'day'
      ? _fmtDay(h.ref)
      : _fmtWeek(_startOfWeek(h.ref), _endOfWeek(h.ref));
    const todayLbl = h.mode === 'day' ? "Aujourd'hui" : 'Cette semaine';
    nav.innerHTML = `
      <button id="nav-prev">&lt;</button>
      <span class="nav-label">${label}</span>
      <button id="nav-next">&gt;</button>
      <button class="nav-today">${todayLbl}</button>`;
    el('nav-prev').onclick = () => {
      const d = h.mode === 'day' ? 1 : 7;
      h.ref = new Date(h.ref - d * 86400000);
      renderHistory();
    };
    el('nav-next').onclick = () => {
      const d = h.mode === 'day' ? 1 : 7;
      h.ref = new Date(+h.ref + d * 86400000);
      renderHistory();
    };
    nav.querySelector('.nav-today').onclick = () => { h.ref = _today(); renderHistory(); };
  } else {
    nav.innerHTML = `
      <div class="custom-range">
        Du <input type="date" id="hist-start" value="${h.customStart ? _isoDate(h.customStart) : _isoDate(_today())}">
        au <input type="date" id="hist-end"   value="${h.customEnd   ? _isoDate(h.customEnd)   : _isoDate(_today())}">
        <button class="btn-blue" id="hist-apply">Appliquer</button>
      </div>`;
    el('hist-apply').onclick = () => {
      const sv = el('hist-start').value, ev = el('hist-end').value;
      if (sv && ev) {
        h.customStart = new Date(sv + 'T00:00:00');
        h.customEnd   = new Date(ev + 'T23:59:59');
        renderHistory();
      }
    };
  }
}

// ── Stats tab ──────────────────────────────────────────────────────────────
async function renderStats() {
  const { start, end } = _statsRange();
  const data = await api('get_stats', start.toISOString(), end.toISOString());
  if (!data) return;

  const chartArea = el('chart-area');
  const emptyMsg  = el('stats-empty');
  const entries   = Object.entries(data).sort(([,a],[,b]) => b - a);

  if (!entries.length) {
    chartArea.classList.add('hidden');
    emptyMsg.classList.remove('hidden');
    return;
  }
  chartArea.classList.remove('hidden');
  emptyMsg.classList.add('hidden');

  const total = entries.reduce((a,[,v]) => a+v, 0);
  _drawDonut(entries, total);

  el('chart-legend').innerHTML = entries.map(([name, secs], i) => `
    <div class="legend-item">
      <div class="legend-dot" style="background:${COLORS[i % COLORS.length]}"></div>
      <span class="legend-name">${_esc(name)}</span>
      <span class="legend-time">${_fmtDuration(secs)}</span>
    </div>`).join('');
}

function _statsRange() {
  const st = S.stats;
  const end = new Date();
  if (st.customStart && st.customEnd)
    return { start: st.customStart, end: st.customEnd };
  const start = new Date(end - st.days * 86400000);
  return { start, end };
}

function _drawDonut(entries, total) {
  const canvas = el('donut');
  const size   = Math.min(window.innerWidth * 0.35, 280);
  canvas.width  = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  const cx = size/2, cy = size/2;
  const R  = size/2 * 0.88;
  const r  = R * 0.56;

  ctx.clearRect(0, 0, size, size);

  // Gap between slices
  const GAP = 0.018;
  let angle = -Math.PI / 2;
  entries.forEach(([, val], i) => {
    const sweep = (val / total) * (2 * Math.PI) - GAP;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, R, angle + GAP/2, angle + GAP/2 + sweep);
    ctx.closePath();
    ctx.fillStyle = COLORS[i % COLORS.length];
    ctx.fill();
    angle += (val / total) * (2 * Math.PI);
  });

  // Inner cutout
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, 2 * Math.PI);
  ctx.fillStyle = '#1e1e2e';
  ctx.fill();

  // Total in center
  ctx.fillStyle = '#cdd6f4';
  ctx.font = `bold ${Math.round(size * 0.052)}px Segoe UI`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(_fmtDuration(total), cx, cy);

  // Percentage labels on slices
  angle = -Math.PI / 2;
  entries.forEach(([, val]) => {
    const sweep = (val / total) * (2 * Math.PI);
    const pct   = val / total * 100;
    if (pct >= 5) {
      const mid = angle + sweep / 2;
      const lr  = (R + r) / 2;
      ctx.fillStyle = 'rgba(17,17,27,0.85)';
      ctx.font = `bold ${Math.round(size * 0.042)}px Segoe UI`;
      ctx.fillText(`${pct.toFixed(0)}%`, cx + lr * Math.cos(mid), cy + lr * Math.sin(mid));
    }
    angle += sweep;
  });
}

// ── Modals helpers ─────────────────────────────────────────────────────────
function _showOverlay(modalId) {
  el('overlay').classList.remove('hidden');
  document.querySelectorAll('.modal').forEach(m => m.classList.add('hidden'));
  el(modalId).classList.remove('hidden');
}
function closeModal() {
  el('overlay').classList.add('hidden');
  document.querySelectorAll('.modal').forEach(m => m.classList.add('hidden'));
}

// ── Add game dialog ────────────────────────────────────────────────────────
function openAddDialog() {
  const d = S.addDlg;
  d.allProcs = []; d.newProcs = []; d.filterNew = false;
  d.selectedProc = null; d.selectedExe = ''; d.chipsBuilt = false;
  el('proc-search').value = '';
  el('game-name-input').value = '';
  el('add-error').textContent = '';
  el('btn-confirm-add').disabled = true;
  el('proc-chips').classList.add('hidden');
  el('proc-list').innerHTML = '<div class="proc-status">Chargement des processus…</div>';
  _showOverlay('modal-add');
  el('proc-search').focus();

  api('get_snapshot').then(snap => { d.snapshot = snap || []; });
  api('get_all_processes').then(procs => {
    if (!procs) return;
    d.allProcs = procs;
    _renderProcList();
  });
}

function _renderProcList() {
  const d = S.addDlg;
  const search = el('proc-search').value.toLowerCase();
  const list = el('proc-list');
  if (!list) return;

  const filtered = d.allProcs.filter(p => {
    if (d.filterNew && !d.newProcs.includes(p.name.toLowerCase())) return false;
    if (search && !p.name.toLowerCase().includes(search)) return false;
    return true;
  });

  if (!filtered.length) {
    list.innerHTML = '<div class="proc-status">Aucun processus trouvé.</div>';
    return;
  }

  const shown = d.filterNew || search ? filtered : filtered.slice(0, 120);
  list.innerHTML = shown.map(p => {
    const sel   = d.selectedProc === p.name;
    const parts = p.exe.replace(/\\/g,'/').split('/');
    const short = parts.length >= 3 ? `…/${parts.slice(-2).join('/')}` : p.exe;
    return `<div class="proc-row${sel?' selected':''}" data-name="${_esc(p.name)}" data-exe="${_esc(p.exe)}">
      <div class="proc-icon" id="picon-${CSS.escape(p.name)}">
        <div class="icon-placeholder" style="width:28px;height:28px;font-size:14px">🎮</div>
      </div>
      <div class="proc-text">
        <div class="proc-name">${_esc(p.name)}</div>
        ${p.exe ? `<div class="proc-path">${_esc(short)}</div>` : ''}
      </div>
      <div class="proc-check">✓</div>
    </div>`;
  }).join('');

  if (!d.filterNew && !search && filtered.length > 120)
    list.innerHTML += `<div class="proc-status">… ${filtered.length - 120} autres — utilisez la recherche</div>`;

  // Click to select
  list.querySelectorAll('.proc-row').forEach(row => {
    row.addEventListener('click', () => _selectProc(row.dataset.name, row.dataset.exe));
  });

  // Load icons
  shown.forEach(p => {
    if (p.exe && !p.exe.toLowerCase().includes('\\windows\\')) {
      _loadProcIcon(p.name, p.exe);
    }
  });
}

async function _loadProcIcon(name, exe) {
  if (S.icons[exe] !== undefined) {
    _applyProcIcon(name, exe); return;
  }
  S.icons[exe] = null;
  const b64 = await api('get_icon_b64', exe);
  if (b64) S.icons[exe] = `data:image/png;base64,${b64}`;
  _applyProcIcon(name, exe);
}
function _applyProcIcon(name, exe) {
  const src = S.icons[exe]; if (!src) return;
  const wrap = document.getElementById(`picon-${CSS.escape(name)}`);
  if (wrap) wrap.innerHTML = `<img src="${src}" alt="" style="width:28px;height:28px">`;
}

function _selectProc(name, exe) {
  S.addDlg.selectedProc = name;
  S.addDlg.selectedExe  = exe;
  document.querySelectorAll('.proc-row').forEach(r =>
    r.classList.toggle('selected', r.dataset.name === name));
  el('game-name-input').value = _cleanName(name);
  el('btn-confirm-add').disabled = false;
  el('add-error').textContent = '';
  el('game-name-input').focus();
  el('game-name-input').select();
}

async function _detectProcs() {
  const d = S.addDlg;
  const snap = await api('get_snapshot');
  if (!snap) return;
  d.newProcs = snap.filter(n => !d.snapshot.includes(n));
  const count = d.newProcs.length;

  if (!d.chipsBuilt) {
    d.chipsBuilt = true;
    el('proc-chips').classList.remove('hidden');
  }
  el('proc-chips').querySelector('[data-filter="new"]').textContent = `Nouveaux (${count})`;
  d.filterNew = count > 0;
  _updateChips();
  _renderProcList();
}

function _updateChips() {
  el('proc-chips').querySelectorAll('.chip').forEach(c =>
    c.classList.toggle('active', c.dataset.filter === (S.addDlg.filterNew ? 'new' : 'all')));
}

async function _confirmAdd() {
  const name = el('game-name-input').value.trim();
  const d    = S.addDlg;
  if (!name || !d.selectedProc) return;

  const res = await api('add_game', name, d.selectedProc, d.selectedExe);
  if (!res?.ok) {
    el('add-error').textContent = res?.error || 'Erreur.';
    return;
  }

  // Check retroactive session
  const startIso = await api('get_process_start', d.selectedProc);
  closeModal();
  S.version = -1;

  if (startIso) {
    const elapsed = Math.floor((Date.now() - new Date(startIso)) / 1000);
    if (elapsed >= 60) {
      S.retro = { gameName: name, procName: d.selectedProc, startIso };
      const h = Math.floor(elapsed/3600), m = Math.floor((elapsed%3600)/60);
      el('retro-msg').textContent =
        `${name} est en cours depuis ${h > 0 ? h+'h '+String(m).padStart(2,'0')+'min' : m+' min'}.`;
      _showOverlay('modal-retro');
    }
  }
}

// ── Rename / Delete modals ─────────────────────────────────────────────────
function openRenameModal(name) {
  S.renameTarget = name;
  el('rename-input').value = name;
  el('rename-error').textContent = '';
  _showOverlay('modal-rename');
  el('rename-input').focus();
  el('rename-input').select();
}

async function _confirmRename() {
  const newName = el('rename-input').value.trim();
  if (!newName) return;
  const res = await api('rename_game', S.renameTarget, newName);
  if (!res?.ok) { el('rename-error').textContent = res?.error; return; }
  closeModal();
}

function openDeleteModal(name) {
  S.deleteTarget = name;
  el('delete-msg').textContent = `Supprimer "${name}" ?`;
  _showOverlay('modal-delete');
}

async function _confirmDelete() {
  await api('delete_game', S.deleteTarget);
  closeModal();
}

async function _confirmRetro() {
  const { gameName, startIso } = S.retro;
  await api('record_session', gameName, startIso, new Date().toISOString());
  closeModal();
}

// ── Toasts ─────────────────────────────────────────────────────────────────
let _toastId = 0;
function showToast(title, body, type = 'blue', actions = []) {
  const id    = ++_toastId;
  const color = type === 'green' ? '#a6e3a1' : '#89b4fa';
  const toast = make('div', 'toast');
  toast.dataset.id = id;
  toast.innerHTML = `
    <div class="toast-header">
      <span class="toast-title" style="color:${color}">${_esc(title)}</span>
      <button class="toast-close">✕</button>
    </div>
    ${body ? `<div class="toast-body">${_esc(body)}</div>` : ''}
    ${actions.length ? `<div class="toast-actions"></div>` : ''}`;

  if (actions.length) {
    const actWrap = toast.querySelector('.toast-actions');
    actions.forEach(a => {
      const btn = make('button', a.cls || 'btn-muted', a.label);
      btn.onclick = () => { _removeToast(id); a.action(); };
      actWrap.appendChild(btn);
    });
  }

  toast.querySelector('.toast-close').onclick = () => _removeToast(id);
  el('toasts').appendChild(toast);

  // Auto-dismiss non-action toasts after 5s
  if (!actions.length) setTimeout(() => _removeToast(id), 5000);
}

function _removeToast(id) {
  const t = el('toasts').querySelector(`[data-id="${id}"]`);
  if (!t) return;
  t.classList.add('removing');
  setTimeout(() => t.remove(), 200);
}

// ── Init ───────────────────────────────────────────────────────────────────
function init() {
  // Tab buttons
  document.querySelectorAll('.tab-btn').forEach(b =>
    b.addEventListener('click', () => switchTab(b.dataset.tab)));

  // Add button
  el('btn-add').addEventListener('click', openAddDialog);

  // History mode buttons
  document.querySelectorAll('.mode-btn').forEach(b =>
    b.addEventListener('click', () => {
      document.querySelectorAll('.mode-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      S.history.mode = b.dataset.mode;
      renderHistory();
    }));

  // History game filter
  el('history-game-filter').addEventListener('change', e => {
    S.history.gameFilter = e.target.value || null;
    renderHistory();
  });

  // Stats period buttons
  document.querySelectorAll('.period-btn').forEach(b =>
    b.addEventListener('click', () => {
      document.querySelectorAll('.period-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      if (b.dataset.period === 'custom') {
        el('stats-custom').classList.remove('hidden');
      } else {
        S.stats.days = parseInt(b.dataset.period);
        S.stats.customStart = S.stats.customEnd = null;
        el('stats-custom').classList.add('hidden');
        renderStats();
      }
    }));

  el('stats-apply').addEventListener('click', () => {
    const sv = el('stats-start').value, ev = el('stats-end').value;
    if (sv && ev) {
      S.stats.customStart = new Date(sv + 'T00:00:00');
      S.stats.customEnd   = new Date(ev + 'T23:59:59');
      renderStats();
    }
  });

  // List header sort
  document.addEventListener('click', e => {
    const btn = e.target.closest('[data-sort]');
    if (!btn) return;
    const k = btn.dataset.sort;
    if (S.sort.key === k) S.sort.asc = !S.sort.asc;
    else { S.sort.key = k; S.sort.asc = k === 'name'; }
    renderGames();
  });

  // Modal close buttons
  document.querySelectorAll('.modal-close, .modal-cancel').forEach(b =>
    b.addEventListener('click', closeModal));
  el('overlay').addEventListener('click', e => {
    if (e.target === el('overlay')) closeModal();
  });

  // Add game modal actions
  el('proc-search').addEventListener('input', _renderProcList);
  el('btn-detect').addEventListener('click', _detectProcs);
  el('proc-chips').addEventListener('click', e => {
    const chip = e.target.closest('.chip');
    if (!chip) return;
    S.addDlg.filterNew = chip.dataset.filter === 'new';
    _updateChips();
    _renderProcList();
  });
  el('btn-confirm-add').addEventListener('click', _confirmAdd);
  el('game-name-input').addEventListener('keydown', e => { if (e.key === 'Enter') _confirmAdd(); });

  // Rename modal
  el('btn-confirm-rename').addEventListener('click', _confirmRename);
  el('rename-input').addEventListener('keydown', e => { if (e.key === 'Enter') _confirmRename(); });

  // Delete modal
  el('btn-confirm-delete').addEventListener('click', _confirmDelete);

  // Retro modal
  el('btn-confirm-retro').addEventListener('click', _confirmRetro);

  // Close ctx menu on scroll
  document.addEventListener('scroll', () => document.querySelectorAll('.ctx-menu').forEach(m => m.remove()), true);

  // Initial render
  poll();
  setInterval(poll, 1000);
}

// Wait for pywebview bridge or fallback to DOMContentLoaded
if (window.pywebview) {
  window.addEventListener('pywebviewready', init);
} else {
  window.addEventListener('pywebviewready', init);
  document.addEventListener('DOMContentLoaded', init);
}
