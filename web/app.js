'use strict';

// ── Palette donut ──────────────────────────────────────────────────────────
const COLORS = ['#4a9eff','#22c55e','#f97316','#e05252',
                '#a855f7','#06b6d4','#facc15','#ec4899'];
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
    mode: 'week',
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
function _toLocalISO(d) {
  const p = n => String(n).padStart(2,'0');
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
function _startOfDay(d) {
  const r = new Date(d); r.setHours(0,0,0,0); return r;
}
function _endOfDay(d) {
  const r = new Date(d); r.setHours(23,59,59,999); return r;
}
function _startOfMonth(d) {
  return new Date(d.getFullYear(), d.getMonth(), 1, 0, 0, 0, 0);
}
function _endOfMonth(d) {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0, 23, 59, 59, 999);
}
function _fmtMonth(d) {
  return `${MONTHS_FR[d.getMonth()]} ${d.getFullYear()}`;
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
  if (secs >= 3600) {
    const h = Math.floor(secs / 3600 * 10) / 10;
    return `${h} h`;
  }
  const m = Math.floor(secs / 60);
  if (m > 0) return `${m} min`;
  return `${secs} s`;
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
function _nameInitials(name) {
  const words = name.replace(/[^a-zA-Z0-9\s]/g, ' ').split(/\s+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}
function _initColor(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (Math.imul(31, h) + name.charCodeAt(i)) | 0;
  const hue = (((h >>> 0) % 360) + 360) % 360;
  return `hsl(${hue},40%,20%)`;
}
function el(id) { return document.getElementById(id); }
function make(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls)  e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}

// ── Poll ───────────────────────────────────────────────────────────────────
let _pollBusy = false;
async function poll() {
  if (_pollBusy) return;
  _pollBusy = true;
  try {
    const data = await api('poll');
    if (!data) return;
    const prevActiveKey = Object.keys(S.active).sort().join('\0');
    S.active = data.active || {};
    const activeChanged = Object.keys(S.active).sort().join('\0') !== prevActiveKey;
    _updateTimers();
    for (const ev of (data.events || [])) _handleEvent(ev);
    if (data.version !== S.version || activeChanged) {
      S.version = data.version;
      S.games   = data.games || {};
      if (S.tab === 'games')   renderGames();
      if (S.tab === 'history') renderHistory();
      if (S.tab === 'stats')   renderStats();
      _refreshHistoryFilter();
    }
  } catch(e) { /* ignore */ }
  finally { _pollBusy = false; }
}

function _updateTimers() {
  for (const [name, info] of Object.entries(S.active)) {
    document.querySelectorAll(`.live-time[data-game="${CSS.escape(name)}"]`).forEach(node => {
      node.textContent = _fmtDuration(info.total);
    });
  }
}

function _handleEvent(ev) {
  if (ev.type === 'start') {
    api('show_notification', ev.name, 'Suivi démarré', 'green', null);
  } else if (ev.type === 'stop') {
    api('show_notification', ev.name,
      `Session : ${_fmtDuration(ev.duration)}  •  Total : ${_fmtDuration(ev.total)}`,
      'blue', null);
  } else if (ev.type === 'suggestion') {
    const msg = ev.exe_path ? ev.exe_path.split('\\').slice(-2).join('\\') : ev.proc_name;
    api('show_notification', `Nouveau jeu détecté : ${ev.game_name}`, msg, 'blue', {
      game_name: ev.game_name, proc_name: ev.proc_name, exe_path: ev.exe_path,
    });
  }
}

let _pendingSuggestion = null;

async function _quickAdd(ev) {
  const res = await api('add_game', ev.game_name, ev.proc_name, ev.exe_path);
  if (res?.ok) { S.version = -1; } // force refresh
}

function _showSuggestionBanner(ev) {
  let banner = document.getElementById('suggestion-banner');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'suggestion-banner';
    banner.className = 'suggestion-banner';
    document.getElementById('tab-games').prepend(banner);
  }
  banner.innerHTML = `
    <span class="suggestion-text">Nouveau jeu détecté : <strong>${ev.game_name}</strong></span>
    <div class="suggestion-actions">
      <button class="btn-muted suggestion-ignore">Ignorer</button>
      <button class="btn-green suggestion-add">Ajouter</button>
    </div>`;
  banner.querySelector('.suggestion-ignore').onclick = () => {
    _pendingSuggestion = null;
    banner.remove();
  };
  banner.querySelector('.suggestion-add').onclick = async () => {
    await _quickAdd(ev);
    _pendingSuggestion = null;
    banner.remove();
  };
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

  const sorted  = _sortedGames(games);
  const maxSecs = sorted.reduce((m, [,d]) => Math.max(m, d.total_seconds || 0), 0);

  let html = '';

  html += `<div class="section-header">Récents <span class="section-count">${recent.length}</span></div>`;
  if (recent.length === 0) {
    html += '<p class="empty-msg" style="padding:16px 6px">Aucun jeu joué récemment.</p>';
  } else {
    html += '<div class="recent-list">';
    recent.forEach(([name, data]) => { html += _gameCardHTML(name, data); });
    html += '</div>';
  }

  html += `<div class="section-header" style="margin-top:8px">Bibliothèque <span class="section-count">${sorted.length}</span></div>`;
  html += _libSortHdrHTML();
  sorted.forEach(([name, data]) => { html += _libRowHTML(name, data, maxSecs); });

  container.innerHTML = html;

  [...recent, ...sorted].forEach(([name, data]) => {
    _loadIconsForGame(name, data.exe_path || '');
  });

  container.querySelectorAll('.row-menu').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      showCtxMenu(e, btn.dataset.game);
    });
  });
}

function _libSortHdrHTML() {
  const { key, asc } = S.sort;
  const arr = asc ? ' ↑' : ' ↓';
  const col = k => key === k ? `sorted" data-sort="${k}` : `" data-sort="${k}`;
  return `<div class="lib-sort-hdr">
    <div class="lsh-name"><button class="${col('name')}">${key==='name'?'Jeu'+arr:'Jeu'}</button></div>
    <div class="lsh-last"><button class="${col('recent')}">${key==='recent'?'Dernière partie'+arr:'Dernière partie'}</button></div>
    <div class="lsh-time"><button class="${col('time')}">${key==='time'?'Temps'+arr:'Temps'}</button></div>
    <div class="lsh-menu"></div>
  </div>`;
}

function _gameCardHTML(name, data) {
  const isActive   = name in S.active;
  const activeInfo = S.active[name];
  const sessions   = data.sessions || [];
  const secs       = isActive ? activeInfo.total : (data.total_seconds || 0);
  const time       = _fmtDuration(secs);
  const last       = _fmtLastPlayed(sessions);
  const activeClass = isActive ? ' active-game' : '';
  const liveAttr   = ` data-game="${name.replace(/"/g,'&quot;')}"`;
  const initials   = _nameInitials(name);
  const initColor  = _initColor(name);

  const statusHtml = isActive
    ? `<div class="card-status live-status" style="color:var(--blue)"${liveAttr}>● IN GAME</div>`
    : `<div class="card-status live-status" style="color:var(--subtext0)"${liveAttr}>${last}</div>`;

  return `<div class="game-card${activeClass}">
    <div class="card-icon row-icon" data-icon="${_esc(name)}">
      <div class="icon-initials" style="background:${initColor}">${initials}</div>
    </div>
    <div class="card-body">
      <div class="card-name">${_esc(name)}</div>
      ${statusHtml}
    </div>
    <div class="card-right">
      <div class="card-time live-time"${liveAttr}>${time}</div>
    </div>
    <div class="row-menu lib-menu" data-game="${_esc(name)}">⋮</div>
  </div>`;
}

function _libRowHTML(name, data, maxSecs) {
  const isActive   = name in S.active;
  const activeInfo = S.active[name];
  const sessions   = data.sessions || [];
  const secs       = isActive ? activeInfo.total : (data.total_seconds || 0);
  const time       = _fmtDuration(secs);
  const last       = _fmtLastPlayed(sessions);
  const activeClass = isActive ? ' active-game' : '';
  const liveAttr   = ` data-game="${name.replace(/"/g,'&quot;')}"`;
  const barPct     = maxSecs > 0 ? Math.max(2, Math.round((secs / maxSecs) * 100)) : 0;
  const initials   = _nameInitials(name);
  const initColor  = _initColor(name);

  return `<div class="lib-row${activeClass}">
    <div class="lib-icon row-icon" data-icon="${_esc(name)}">
      <div class="icon-initials" style="background:${initColor}">${initials}</div>
    </div>
    <div class="lib-name${isActive?' active-text':''}">${_esc(name)}</div>
    <div class="lib-last">${last}</div>
    <div class="lib-time-wrap">
      <div class="lib-time${isActive?' active-text':''} live-time"${liveAttr}>${time}</div>
      <div class="lib-bar"><div class="lib-bar-fill" style="width:${barPct}%"></div></div>
    </div>
    <div class="row-menu lib-menu" data-game="${_esc(name)}">⋮</div>
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
  if (S.icons[name] !== undefined) {
    _applyIcon(name);
    return;
  }
  S.icons[name] = null; // mark as loading
  const b64 = await api('get_icon_b64', name, exe);
  if (b64) S.icons[name] = `data:image/png;base64,${b64}`;
  _applyIcon(name);
}

function _applyIcon(name) {
  const src = S.icons[name];
  if (!src) return;
  document.querySelectorAll(`.row-icon[data-icon="${CSS.escape(name)}"]`).forEach(wrap => {
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
    _toLocalISO(start), _toLocalISO(end), filter);
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
      <div class="history-day-hdr" onclick="this.closest('.history-day').classList.toggle('collapsed')">
        <span class="day-toggle">▼</span>
        <span>${_fmtDay(dt)}</span>
        <span class="day-total">${_fmtDuration(dayTotal)}</span>
      </div>
      <div class="history-sessions">${sessRows}</div>
    </div>`;
  }).join('');
}

function _historyRange() {
  const h = S.history;
  if (h.mode === 'day') {
    return { start: _startOfDay(h.ref), end: _endOfDay(h.ref) };
  } else if (h.mode === 'week') {
    return { start: _startOfWeek(h.ref), end: _endOfWeek(h.ref) };
  } else if (h.mode === 'month') {
    return { start: _startOfMonth(h.ref), end: _endOfMonth(h.ref) };
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

  if (h.mode === 'day' || h.mode === 'week' || h.mode === 'month') {
    const label = h.mode === 'day'
      ? _fmtDay(h.ref)
      : h.mode === 'week'
      ? _fmtWeek(_startOfWeek(h.ref), _endOfWeek(h.ref))
      : _fmtMonth(h.ref);
    const todayLbl = h.mode === 'day' ? "Aujourd'hui" : h.mode === 'week' ? 'Cette semaine' : 'Ce mois';
    nav.innerHTML = `
      <button id="nav-prev">&lt;</button>
      <span class="nav-label">${label}</span>
      <button id="nav-next">&gt;</button>
      <button class="nav-today">${todayLbl}</button>`;
    el('nav-prev').onclick = () => {
      if (h.mode === 'day')        h.ref = new Date(h.ref - 86400000);
      else if (h.mode === 'week')  h.ref = new Date(h.ref - 7 * 86400000);
      else { const d = new Date(h.ref); d.setMonth(d.getMonth() - 1); h.ref = d; }
      renderHistory();
    };
    el('nav-next').onclick = () => {
      if (h.mode === 'day')        h.ref = new Date(+h.ref + 86400000);
      else if (h.mode === 'week')  h.ref = new Date(+h.ref + 7 * 86400000);
      else { const d = new Date(h.ref); d.setMonth(d.getMonth() + 1); h.ref = d; }
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
const STAT_PERIODS = [
  { label: '7 derniers jours',  days: 7  },
  { label: '30 derniers jours', days: 30 },
  { label: '3 derniers mois',   days: 90 },
];

async function renderStats() {
  const container = el('stats-list');
  if (!container) return;

  const now = new Date();
  const results = await Promise.all(STAT_PERIODS.map(p => {
    const start = new Date(now - p.days * 86400000);
    return api('get_stats', _toLocalISO(start), _toLocalISO(now));
  }));

  let html = '';
  STAT_PERIODS.forEach((p, i) => {
    const data    = results[i];
    const entries = data ? Object.entries(data).sort(([,a],[,b]) => b - a) : [];
    html += `<div class="stats-period">
      <div class="section-header">${p.label}</div>
      ${entries.length === 0
        ? '<p class="empty-msg" style="padding:12px 6px">Aucune donnée.</p>'
        : `<div class="stats-period-body">
            <canvas id="donut-${p.days}" class="stats-donut"></canvas>
            <div class="stats-period-legend" id="legend-${p.days}"></div>
           </div>`
      }
    </div>`;
  });
  container.innerHTML = html;

  STAT_PERIODS.forEach((p, i) => {
    const data    = results[i];
    if (!data) return;
    const entries = Object.entries(data).sort(([,a],[,b]) => b - a);
    if (!entries.length) return;
    const total = entries.reduce((a,[,v]) => a+v, 0);
    _drawDonut(entries, total, `donut-${p.days}`, 220);
    el(`legend-${p.days}`).innerHTML = entries.map(([name, secs], j) => `
      <div class="legend-item">
        <div class="legend-dot" style="background:${COLORS[j % COLORS.length]}"></div>
        <span class="legend-name">${_esc(name)}</span>
        <span class="legend-time">${_fmtDuration(secs)}</span>
      </div>`).join('');
  });
}

function _drawDonut(entries, total, canvasId = 'donut', size = 0) {
  const canvas = el(canvasId);
  if (!canvas) return;
  if (!size) size = Math.min(window.innerWidth * 0.35, 280);
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
    const fraction = val / total;
    const sweep = fraction * 2 * Math.PI - GAP;
    if (sweep > 0) {
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, R, angle + GAP/2, angle + GAP/2 + sweep);
      ctx.closePath();
      ctx.fillStyle = COLORS[i % COLORS.length];
      ctx.fill();
    }
    angle += fraction * 2 * Math.PI;
  });

  // Inner cutout
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, 2 * Math.PI);
  ctx.fillStyle = '#161616';
  ctx.fill();

  // Total in center
  ctx.fillStyle = '#f0f0f0';
  ctx.font = `bold ${Math.round(size * 0.09)}px Segoe UI`;
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
      ctx.fillStyle = 'rgba(0,0,0,0.75)';
      ctx.font = `bold ${Math.round(size * 0.068)}px Segoe UI`;
      ctx.fillText(`${pct.toFixed(0)}%`, cx + lr * Math.cos(mid), cy + lr * Math.sin(mid));
    }
    angle += sweep;
  });
}

// ── Modals helpers ─────────────────────────────────────────────────────────
function closeModal() {
  if (_authRequired) return;
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
      <div class="proc-icon" data-icon="${_esc(p.name)}">
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
  const b64 = await api('get_icon_b64', name, exe);
  if (b64) S.icons[exe] = `data:image/png;base64,${b64}`;
  _applyProcIcon(name, exe);
}
function _applyProcIcon(name, exe) {
  const src = S.icons[exe]; if (!src) return;
  const wrap = document.querySelector(`.proc-icon[data-icon="${CSS.escape(name)}"]`);
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
  if (S.icons[S.renameTarget] !== undefined) {
    S.icons[newName] = S.icons[S.renameTarget];
    delete S.icons[S.renameTarget];
  }
  closeModal();
}

function openDeleteModal(name) {
  S.deleteTarget = name;
  el('delete-msg').textContent = `Supprimer "${name}" ?`;
  _showOverlay('modal-delete');
}

async function _confirmDelete() {
  await api('delete_game', S.deleteTarget);
  S.version = -1;
  closeModal();
}

async function _confirmRetro() {
  const { gameName, startIso } = S.retro;
  await api('record_session', gameName, startIso, _toLocalISO(new Date()));
  closeModal();
}

// ── Toasts ─────────────────────────────────────────────────────────────────
let _toastId = 0;
function showToast(title, body, type = 'blue', actions = []) {
  const id    = ++_toastId;
  const color = type === 'green' ? '#76b900' : '#4a9eff';
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

// ── Compte / Sync ──────────────────────────────────────────────────────────

let _accountMode    = 'login';  // 'login' | 'register'
let _authRequired   = false;    // true → modal non-fermable

// Vérification au démarrage : bloque l'UI si non connecté
async function checkAuth() {
  const s = await api('sync_status');
  if (!s || !s.available) { _startApp(); return; }

  if (s.logged_in) {
    _updateAccountBtn(s.email);
    _startApp();
    api('sync_pull_on_start').then(() => api('sync_push_now')); // pull puis push initial
  } else {
    _showLoginModal(/*mandatory=*/true);
  }
}

function _startApp() {
  poll();
  setInterval(poll, 1000);
  setInterval(_refreshSyncStatus, 5000);
}

function _updateAccountBtn(email) {
  const btn = el('btn-account');
  btn.classList.add('logged-in');
  btn.title = email || 'Mon compte';
}

async function _refreshSyncStatus() {
  const info = await api('sync_get_info');
  if (!info || !info.logged_in) return;
  _applySyncStatus(info);
}

function _applySyncStatus(info) {
  // Bouton : point coloré
  const btn = el('btn-account');
  let dot = btn.querySelector('.sync-dot');
  if (!dot) { dot = document.createElement('span'); dot.className = 'sync-dot'; btn.appendChild(dot); }

  if (info.pending) {
    dot.className = 'sync-dot pending';
    btn.title = 'Synchronisation en cours…';
  } else if (info.synced) {
    dot.className = 'sync-dot ok';
    btn.title = `Synchronisé — ${info.last_sync || ''}`;
  } else if (info.error) {
    dot.className = 'sync-dot error';
    btn.title = `Erreur de sync — clique pour détails`;
  } else {
    dot.className = 'sync-dot unknown';
    btn.title = 'Mon compte';
  }

  // Modal : ligne de statut
  const dotEl  = document.getElementById('sync-status-dot');
  const textEl = document.getElementById('sync-status-text');
  if (!dotEl || !textEl) return;

  if (info.pending) {
    dotEl.className = 'sync-status-indicator pending';
    textEl.textContent = 'Synchronisation en cours…';
  } else if (info.synced) {
    dotEl.className = 'sync-status-indicator ok';
    textEl.textContent = `Données synchronisées — ${info.last_sync || ''}`;
  } else if (info.error) {
    dotEl.className = 'sync-status-indicator error';
    textEl.textContent = `Erreur — ${info.error}`;
  } else {
    dotEl.className = 'sync-status-indicator unknown';
    textEl.textContent = 'Pas encore synchronisé';
  }
}

// Ouvre le modal (depuis le bouton compte, quand déjà connecté)
async function _openAccount() {
  const info = await api('sync_get_info');
  if (!info) return;
  if (info.logged_in) {
    _showAccountLoggedIn(info.email);
    _applySyncStatus(info);
    _showOverlay('modal-account', /*canClose=*/true);
  } else {
    _showLoginModal(/*mandatory=*/false);
  }
}

function _showLoginModal(mandatory) {
  _authRequired = mandatory;
  el('account-title').textContent = 'Connexion';
  el('account-auth-panel').classList.remove('hidden');
  el('account-logged-panel').classList.add('hidden');
  el('modal-close-account').classList.toggle('hidden', mandatory);
  el('account-error').textContent = '';
  _setAccountTab('login');
  _showOverlay('modal-account', !mandatory);
}

function _showAccountLoggedIn(email) {
  _authRequired = false;
  el('account-title').textContent = 'Mon compte';
  el('account-auth-panel').classList.add('hidden');
  el('account-newpwd-panel').classList.add('hidden');
  el('account-changepwd-panel').classList.add('hidden');
  el('account-logged-panel').classList.remove('hidden');
  el('account-logged-email').textContent = email;
  el('modal-close-account').classList.remove('hidden');
}

function _showOverlay(modalId, canClose = true) {
  document.querySelectorAll('.modal').forEach(m => m.classList.add('hidden'));
  el(modalId).classList.remove('hidden');
  el('overlay').classList.remove('hidden');
  el('overlay')._canClose = canClose;
}

function _setAccountTab(mode) {
  _accountMode = mode;
  const isReset = mode === 'reset';
  document.querySelectorAll('.account-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.atab === mode));
  el('account-password').closest('input') || el('account-password');
  el('account-password').style.display = isReset ? 'none' : '';
  el('btn-forgot').style.display       = isReset ? 'none' : '';
  el('btn-account-submit').textContent  =
    mode === 'login' ? 'Se connecter' : mode === 'register' ? "S'inscrire" : 'Envoyer le lien';
  const errEl = el('account-error');
  errEl.textContent = '';
  errEl.style.color = '';
}

async function _submitAccount() {
  const email    = el('account-email').value.trim();
  const password = el('account-password').value;
  const errEl    = el('account-error');

  if (_accountMode === 'reset') { await _submitReset(); return; }

  if (!email || !password) { errEl.textContent = 'Remplis tous les champs.'; return; }

  const btn = el('btn-account-submit');
  btn.disabled = true; btn.textContent = '…'; errEl.textContent = '';

  const fn = _accountMode === 'login' ? 'sync_sign_in' : 'sync_sign_up';
  const r  = await api(fn, email, password);

  btn.disabled = false;
  btn.textContent = _accountMode === 'login' ? 'Se connecter' : "S'inscrire";

  if (r && r.ok) {
    const wasRequired = _authRequired;
    _authRequired = false;  // débloquer avant closeModal
    _updateAccountBtn(r.email);
    closeModal();
    api('sync_pull_on_start');  // fusionne les données depuis le cloud
    if (wasRequired) _startApp();
  } else {
    errEl.textContent = (r && r.error) || 'Erreur inconnue';
  }
}

let _resetPollInterval = null;
let _capturedResetToken = null;

async function _submitReset() {
  const email = el('account-email').value.trim();
  const errEl = el('account-error');
  if (!email) { errEl.textContent = 'Saisis ton email.'; return; }

  const btn = el('btn-account-submit');
  btn.disabled = true; btn.textContent = '…'; errEl.textContent = '';

  try {
    const r = await api('sync_start_reset_flow', email);
    if (r && r.ok) {
      errEl.style.color = 'var(--green)';
      errEl.textContent = 'Email envoyé — clique sur le lien dans ta boîte mail.';
      _startResetTokenPolling();
    } else {
      errEl.style.color = '';
      errEl.textContent = (r && r.error) || 'Erreur inconnue';
    }
  } catch (e) {
    errEl.style.color = '';
    errEl.textContent = 'Erreur — relance l\'application.';
  } finally {
    btn.disabled = false; btn.textContent = 'Envoyer le lien';
  }
}

function _startResetTokenPolling() {
  if (_resetPollInterval) clearInterval(_resetPollInterval);
  _resetPollInterval = setInterval(async () => {
    const tok = await api('sync_check_reset_token');
    if (tok) {
      clearInterval(_resetPollInterval);
      _resetPollInterval = null;
      _capturedResetToken = tok;
      _showNewPasswordPanel();
    }
  }, 1000);
}

function _showNewPasswordPanel() {
  _authRequired = false;
  el('account-title').textContent = 'Nouveau mot de passe';
  el('account-auth-panel').classList.add('hidden');
  el('account-logged-panel').classList.add('hidden');
  el('account-newpwd-panel').classList.remove('hidden');
  el('modal-close-account').classList.remove('hidden');
  el('overlay').classList.remove('hidden');
  el('modal-account').classList.remove('hidden');
  el('newpwd-error').textContent = '';
  el('account-newpwd').value = '';
  el('account-newpwd2').value = '';
  el('account-newpwd').focus();
}

async function _submitNewPassword() {
  const pwd1  = el('account-newpwd').value;
  const pwd2  = el('account-newpwd2').value;
  const errEl = el('newpwd-error');
  if (!pwd1) { errEl.textContent = 'Saisis un mot de passe.'; return; }
  if (pwd1 !== pwd2) { errEl.textContent = 'Les mots de passe ne correspondent pas.'; return; }
  if (pwd1.length < 6) { errEl.textContent = 'Minimum 6 caractères.'; return; }

  const btn = el('btn-newpwd-submit');
  btn.disabled = true; btn.textContent = '…'; errEl.textContent = '';

  try {
    const r = await api('sync_update_password', _capturedResetToken, pwd1);
    if (r && r.ok) {
      _capturedResetToken = null;
      closeModal();
      showToast('Mot de passe mis à jour', 'Reconnecte-toi avec ton nouveau mot de passe.', 'green');
      _showLoginModal(/*mandatory=*/true);
    } else {
      errEl.textContent = (r && r.error) || 'Erreur inconnue';
    }
  } catch (e) {
    errEl.textContent = 'Erreur — réessaie.';
  } finally {
    btn.disabled = false; btn.textContent = 'Mettre à jour';
  }
}

function _showChangePwdPanel() {
  el('account-logged-panel').classList.add('hidden');
  el('account-changepwd-panel').classList.remove('hidden');
  el('account-title').textContent = 'Changer le mot de passe';
  el('changepwd-error').textContent = '';
  el('account-changepwd1').value = '';
  el('account-changepwd2').value = '';
  el('account-changepwd1').focus();
}

async function _submitChangePassword() {
  const pwd1  = el('account-changepwd1').value;
  const pwd2  = el('account-changepwd2').value;
  const errEl = el('changepwd-error');
  if (!pwd1) { errEl.textContent = 'Saisis un mot de passe.'; return; }
  if (pwd1 !== pwd2) { errEl.textContent = 'Les mots de passe ne correspondent pas.'; return; }
  if (pwd1.length < 6) { errEl.textContent = 'Minimum 6 caractères.'; return; }

  const btn = el('btn-changepwd-submit');
  btn.disabled = true; btn.textContent = '…';

  try {
    const r = await api('sync_change_password', pwd1);
    if (r && r.ok) {
      closeModal();
      showToast('Mot de passe modifié', '', 'green');
    } else {
      errEl.textContent = (r && r.error) || 'Erreur inconnue';
    }
  } catch (e) {
    errEl.textContent = 'Erreur — réessaie.';
  } finally {
    btn.disabled = false; btn.textContent = 'Mettre à jour';
  }
}

async function _signOut() {
  await api('sync_sign_out');
  el('btn-account').classList.remove('logged-in');
  el('btn-account').title = 'Compte';
  closeModal();
  // Affiche le modal de connexion obligatoire
  _showLoginModal(/*mandatory=*/true);
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
    if (e.target === el('overlay') && el('overlay')._canClose !== false) closeModal();
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

  // F5 → reload frontend
  document.addEventListener('keydown', e => {
    if (e.key === 'F5') { e.preventDefault(); location.href = location.pathname + '?v=' + Date.now(); }
  });

  // Account / sync
  el('btn-account').addEventListener('click', _openAccount);
  document.querySelectorAll('.account-tab').forEach(t =>
    t.addEventListener('click', () => _setAccountTab(t.dataset.atab)));
  el('btn-account-submit').addEventListener('click', _submitAccount);
  el('account-password').addEventListener('keydown', e => {
    if (e.key === 'Enter') _submitAccount();
  });
  el('btn-forgot').addEventListener('click', () => _setAccountTab('reset'));
  el('btn-sign-out').addEventListener('click', _signOut);
  el('btn-change-pwd').addEventListener('click', _showChangePwdPanel);
  el('btn-changepwd-cancel').addEventListener('click', async () => {
    const s = await api('sync_status');
    if (s && s.logged_in) _showAccountLoggedIn(s.email);
  });
  el('btn-changepwd-submit').addEventListener('click', _submitChangePassword);
  el('account-changepwd2').addEventListener('keydown', e => {
    if (e.key === 'Enter') _submitChangePassword();
  });
  el('btn-newpwd-submit').addEventListener('click', _submitNewPassword);
  el('account-newpwd2').addEventListener('keydown', e => {
    if (e.key === 'Enter') _submitNewPassword();
  });

  // Auth check → démarre l'app (poll) seulement si connecté
  checkAuth();
}

// Wait for pywebview bridge or fallback to DOMContentLoaded
if (window.pywebview) {
  window.addEventListener('pywebviewready', init);
} else {
  window.addEventListener('pywebviewready', init);
  document.addEventListener('DOMContentLoaded', init);
}
