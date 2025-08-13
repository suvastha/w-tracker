// /weighty/static/js/main.js
/* global Chart */
/**
 * Frontend logic:
 * - fetch helpers
 * - render cards, table, charts
 * - toasts, modal, theme toggle, heatmap
 */

const $ = (sel, el=document) => el.querySelector(sel);
const $$ = (sel, el=document) => Array.from(el.querySelectorAll(sel));

function showToast(msg, type='ok') {
  const wrap = $('#toasts');
  const div = document.createElement('div');
  div.className = 'toast' + (type==='error' ? ' error' : '');
  div.textContent = msg;
  wrap.appendChild(div);
  setTimeout(()=>div.remove(), 4200);
}

function showConfetti() {
  const c = $('#confetti');
  c.classList.remove('hidden');
  c.classList.add('show');
  setTimeout(() => { c.classList.remove('show'); c.classList.add('hidden'); }, 1000);
}

// Theme toggle
(function themeInit(){
  const btn = $('#themeToggle');
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const stored = localStorage.getItem('theme');
  if ((stored === 'dark') || (!stored && prefersDark)) document.documentElement.classList.add('dark');
  btn?.addEventListener('click', () => {
    document.documentElement.classList.toggle('dark');
    localStorage.setItem('theme', document.documentElement.classList.contains('dark') ? 'dark' : 'light');
  });
})();

// Modal
const modal = {
  open(data) {
    $('#modalTitle').textContent = data?.id ? 'Edit weight' : 'Add weight';
    const f = $('#weightForm');
    f.id.value = data?.id || '';
    f.date.value = data?.date || new Date().toISOString().slice(0,10);
    f.weight.value = data?.weight || '';
    $('#modalBackdrop').classList.remove('hidden');
    $('#modalBackdrop').classList.add('flex');
  },
  close() {
    $('#modalBackdrop').classList.add('hidden');
    $('#modalBackdrop').classList.remove('flex');
  }
};

// State
let state = {
  profile: null,
  items: [],
  streak: {current:0, best:0},
  charts: {trend: null, avg7: null, avg30: null, projection: null},
};

async function api(path, opts={}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = 'Request failed';
    try { const j = await res.json(); msg = j.errors ? JSON.stringify(j.errors) : (j.message || msg); } catch {}
    throw new Error(msg);
  }
  return res.json();
}

async function loadProfile() {
  const j = await api('/api/profile');
  state.profile = j.profile;
  $('#cardGoal').textContent = j.profile.goal_weight;
}

function formatDelta(n) {
  return (n>0?'+':'') + n.toFixed(1);
}

function renderCards() {
  const itemsDesc = [...state.items];
  if (itemsDesc.length === 0) return;
  const latest = itemsDesc[0];
  $('#cardCurrent').textContent = latest.weight.toFixed(1);
  $('#cardDelta').textContent = formatDelta(latest.change_from_last || 0);
  $('#cardBMI').textContent = `${latest.bmi.toFixed(1)} (${latest.bmi_category})`;
  $('#cardStreak').textContent = `${state.streak.current} / ${state.streak.best}`;
  const eta = state.charts?.projection?.eta;
  $('#cardETA').textContent = eta ? eta : (state.charts?.projection?.message || '—');
}

function renderTable() {
  const body = $('#rowsBody');
  body.innerHTML = '';
  if (state.items.length === 0) {
    $('#emptyState').style.display = 'block';
    return;
  } else {
    $('#emptyState').style.display = 'none';
  }
  for (const r of state.items) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="p-2">${r.date}</td>
      <td class="p-2">${r.weight.toFixed(1)}</td>
      <td class="p-2 ${r.change_from_last>0?'text-rose-600':'text-emerald-600'}">${(r.change_from_last>0?'+':'')}${r.change_from_last?.toFixed(1) ?? '0.0'}</td>
      <td class="p-2">${r.bmi.toFixed(1)} <span class="text-xs opacity-70">(${r.bmi_category})</span></td>
      <td class="p-2">${r.avg7.toFixed(1)}</td>
      <td class="p-2">${r.avg30.toFixed(1)}</td>
      <td class="p-2">
        <button class="btn-secondary btn-xs" data-edit="${r.id}">Edit</button>
        <button class="btn-secondary btn-xs" data-del="${r.id}">Delete</button>
      </td>
    `;
    body.appendChild(tr);
  }
  // actions
  body.addEventListener('click', async (e) => {
    const id = e.target.getAttribute('data-edit');
    if (id) {
      const row = state.items.find(x => x.id == id);
      modal.open(row);
      return;
    }
    const did = e.target.getAttribute('data-del');
    if (did) {
      if (confirm('Delete this entry?')) {
        await api(`/api/weights/${did}`, {method:'DELETE'});
        showToast('Deleted ✅');
        await refreshAll();
      }
    }
  }, {once:true});
}

let chartTrend, chartProjection;

function renderCharts() {
  const ctx1 = $('#chartTrend').getContext('2d');
  const ctx2 = $('#chartProjection').getContext('2d');

  const trend = state.charts.trend || [];
  const avg7 = state.charts.avg7 || [];
  const avg30 = state.charts.avg30 || [];

  // destroy old
  chartTrend?.destroy();
  chartProjection?.destroy();

  chartTrend = new Chart(ctx1, {
    type: 'line',
    data: {
      datasets: [
        { label: 'Weight', data: trend, parsing:false, tension:0.25 },
        { label: '7d avg', data: avg7, parsing:false, tension:0.25 },
        { label: '30d avg', data: avg30, parsing:false, tension:0.25 },
        { label: 'Goal', data: trend.map(p => ({x:p.x, y: state.profile.goal_weight })) , parsing:false, borderDash:[5,5]}
      ]
    },
    options: {
      responsive: true,
      scales: { x: { type: 'time', time: { parser: 'YYYY-MM-DD', unit: 'day' } } }
    }
  });

  // projection
  const proj = state.charts.projection || {};
  $('#etaText').textContent = proj.eta ? `ETA to goal: ${proj.eta}` : (proj.message || '');
  const last = trend[trend.length-1];
  const projLine = [];
  if (last && proj.slope !== undefined) {
    for (let i=0;i<30;i++){
      const d = new Date(last.x);
      d.setDate(d.getDate()+i);
      const y = proj.intercept + proj.slope * (i + Math.max(trend.length-1, 0));
      projLine.push({x: d.toISOString().slice(0,10), y});
    }
  }

  chartProjection = new Chart(ctx2, {
    type: 'line',
    data: {
      datasets: [
        { label: 'Weight', data: trend, parsing:false, tension:0.25 },
        { label: 'Projection', data: projLine, parsing:false, borderDash:[3,3] },
        { label: 'Goal', data: trend.map(p => ({x:p.x, y: state.profile.goal_weight })) , parsing:false, borderDash:[5,5]}
      ]
    },
    options: { responsive: true }
  });
}

function renderAveragesPanel() {
  const wrap = $('#avgCards'); wrap.innerHTML = '';
  if (state.items.length === 0) return;
  const sums = {w:0, n:0};
  for (const it of state.items) { sums.w += it.weight; sums.n++; }
  const avgAll = sums.w / Math.max(sums.n,1);
  const make = (title, val) => {
    const d = document.createElement('div');
    d.className = 'card';
    d.innerHTML = `<div class="card-title">${title}</div><div class="card-value">${val.toFixed ? val.toFixed(1) : val}</div>`;
    wrap.appendChild(d);
  };
  make('Average (all)', avgAll);
  make('Average (7d)', state.items[0]?.avg7 ?? 0);
  make('Average (30d)', state.items[0]?.avg30 ?? 0);
}

function renderHeatmap() {
  const hm = $('#heatmap'); hm.innerHTML = '';
  if (state.items.length === 0) return;
  // create a month view starting from last 35 days
  const lastDate = new Date(state.items[0].date);
  const start = new Date(lastDate); start.setDate(start.getDate() - 34);
  const set = new Set(state.items.map(x => x.date));
  for (let i=0;i<35;i++){
    const d = new Date(start); d.setDate(start.getDate()+i);
    const iso = d.toISOString().slice(0,10);
    const cell = document.createElement('div');
    cell.className = 'hm-cell ' + (set.has(iso) ? (i%7===0?'strong': i%3===0?'med':'faint') : '');
    cell.title = iso + (set.has(iso) ? ' ✔' : '');
    hm.appendChild(cell);
  }
}

async function refreshAll() {
  await loadProfile();
  const res = await api('/api/weights');
  state.items = res.items; // already DESC
  state.streak = res.streak;

  // Also fetch charts by simulating with POST without mutating? We'll derive from last known dataset after add/edit
  // Simpler: when adding/editing, API returns charts. On initial load we build locals quickly:
  // We'll trigger a fake build by adding datasets from items:
  const trend = state.items.map(x => ({x:x.date, y:x.weight})).reverse();
  const avg7 = state.items.map(x => ({x:x.date, y:x.avg7})).reverse();
  const avg30 = state.items.map(x => ({x:x.date, y:x.avg30})).reverse();
  state.charts = {trend, avg7, avg30, projection: {message:'Add a few more logs for projection 👀'}};

  // Cards + tables
  renderCards();
  renderTable();
  renderCharts();
  renderAveragesPanel();
  renderHeatmap();
}

document.addEventListener('DOMContentLoaded', async () => {
  // Toggle panels
  $$('#btnDetails, #btnAverages, #btnHeatmap').forEach(btn => btn.addEventListener('click', () => {
    const target = btn.getAttribute('data-toggle');
    $$('.toggle-panel').forEach(p => p.classList.add('hidden'));
    $('#panel-'+target).classList.remove('hidden');
  }));

  $('#btnAdd')?.addEventListener('click', ()=> modal.open());
  $('#modalCancel')?.addEventListener('click', ()=> modal.close());

  // Save in modal
  $('#weightForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = e.target.id.value;
    const body = { date: e.target.date.value, weight: +e.target.weight.value };
    try {
      let j;
      if (id) {
        j = await api(`/api/weights/${id}`, {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
      } else {
        j = await api('/api/weights', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
      }
      showToast('Saved ✅');
      if (j.unlocks?.length) {
        showToast('Achievement unlocked: ' + j.unlocks.join(', '));
        showConfetti();
      }
      // Update charts if provided
      if (j.charts) state.charts = j.charts;
      modal.close();
      await refreshAll();
    } catch (err) {
      showToast(err.message || 'Error', 'error');
    }
  });

  await refreshAll();
});
