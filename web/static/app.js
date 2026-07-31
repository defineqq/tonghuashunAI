// app.js — 面向普通用户的前端逻辑
'use strict';

const API = (path, opts = {}) => {
  const headers = {'Content-Type': 'application/json', ...(opts.headers || {})};
  return fetch(`/api${path}`, { ...opts, headers })
    .then(async r => {
      const text = await r.text();
      let data;
      try { data = JSON.parse(text); } catch { data = { raw: text }; }
      if (!r.ok) throw new Error(data.detail || data.raw || `HTTP ${r.status}`);
      return data;
    });
};

// -------- Tab 切换 --------
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => {
      b.classList.remove('active');
      b.classList.remove('text-slate-700', 'font-medium');
      b.classList.add('text-slate-500');
    });
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
    btn.classList.add('active', 'text-slate-700', 'font-medium');
    btn.classList.remove('text-slate-500');
    document.getElementById(`tab-${btn.dataset.tab}`).classList.remove('hidden');
    if (btn.dataset.tab === 'settings') loadSettings();
    if (btn.dataset.tab === 'strategies') loadStrategiesLab();
    if (btn.dataset.tab === 'backtest') { loadBacktestStrategies(); loadBacktestHistory(); }
    if (btn.dataset.tab === 'portfolio') { loadAgentHistory(); autoResumeRunningAgent(); }
  });
});

// Lab sub-tabs
document.querySelectorAll('.lab-subtab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.lab-subtab').forEach(b => {
      b.classList.remove('active', 'border-blue-500', 'text-blue-600', 'font-medium');
      b.classList.add('border-transparent', 'text-slate-500');
    });
    btn.classList.add('active', 'border-blue-500', 'text-blue-600', 'font-medium');
    btn.classList.remove('border-transparent', 'text-slate-500');
    document.querySelectorAll('.lab-panel').forEach(p => p.classList.add('hidden'));
    document.getElementById(`lab-${btn.dataset.subtab}`).classList.remove('hidden');
    if (btn.dataset.subtab === 'builder') loadIndicators();
    if (btn.dataset.subtab === 'python') loadPythonList();
  });
});

// Backtest strategy type toggle
function _applyBtType(type) {
  window.btStrategyType = type;
  document.getElementById('bt-desc-score').classList.toggle('hidden', type !== 'score');
  document.getElementById('bt-params-score').classList.toggle('hidden', type !== 'score');
  document.getElementById('bt-desc-technical').classList.toggle('hidden', type !== 'technical');
  document.getElementById('bt-params-technical').classList.toggle('hidden', type !== 'technical');
  // 综合分下限只对打分策略生效，技术策略下隐藏避免混淆
  const wrap = document.getElementById('bt-min-score-wrap');
  if (wrap) wrap.classList.toggle('hidden', type !== 'score');
}
document.querySelectorAll('.bt-type').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.bt-type').forEach(b => {
      b.classList.remove('active', 'border-blue-500', 'bg-blue-50', 'text-blue-700');
      b.classList.add('border-slate-200', 'text-slate-700');
    });
    btn.classList.add('active', 'border-blue-500', 'bg-blue-50', 'text-blue-700');
    btn.classList.remove('border-slate-200', 'text-slate-700');
    _applyBtType(btn.dataset.type);
  });
});
window.btStrategyType = 'score';
// 初始化时同步一次可见性
setTimeout(() => _applyBtType('score'), 0);

// -------- Status --------
async function refreshStatus() {
  try {
    const s = await API('/status');
    const badge = document.getElementById('status-badge');
    const llmOk = s.llm.configured;
    if (llmOk) {
      badge.textContent = `AI: ${s.llm.provider}`;
      badge.className = 'px-2.5 py-1 rounded-full text-xs bg-emerald-50 text-emerald-700';
    } else {
      badge.textContent = 'AI 未配置';
      badge.className = 'px-2.5 py-1 rounded-full text-xs bg-amber-50 text-amber-700';
    }
  } catch (e) {
    document.getElementById('status-badge').textContent = '离线';
  }
}
refreshStatus();

// 数据接口情况（每 60s 定时刷新）
window.refreshHealth = async function refreshHealth() {
  const banner = document.getElementById('health-banner');
  const icon = document.getElementById('health-icon');
  const title = document.getElementById('health-title');
  const subtitle = document.getElementById('health-subtitle');
  const detail = document.getElementById('health-detail');
  const last = document.getElementById('health-last');
  if (!banner) return;
  banner.classList.remove('hidden');
  if (!banner.dataset.everLoaded) {
    title.textContent = '正在检查数据接口...';
    subtitle.textContent = '首次检查约 5 秒';
    icon.textContent = '⏳';
  }
  try {
    const r = await API('/status/datasources');
    banner.dataset.everLoaded = '1';
    if (r.healthy) {
      icon.textContent = '✅';
      banner.className = 'card p-4 border-l-4 border-emerald-400';
      title.textContent = `数据接口情况：全部可用 (${r.ok_count}/${r.total})`;
      subtitle.textContent = '打分和回测能得到真实数据';
    } else if (r.ok_count > 0) {
      icon.textContent = '⚠️';
      banner.className = 'card p-4 border-l-4 border-amber-400';
      title.textContent = `数据接口情况：${r.ok_count}/${r.total} 可用`;
      subtitle.textContent = '缺失的维度会用中性 50 分兜底';
    } else {
      icon.textContent = '❌';
      banner.className = 'card p-4 border-l-4 border-red-400';
      title.textContent = '数据接口情况：全部不可用';
      subtitle.textContent = '网络问题？打分会全部返回 50';
    }
    if (last) last.textContent = '刷新于 ' + new Date(r.checked_at).toLocaleTimeString();

    detail.innerHTML = r.checks.map(c => {
      const sourcesHtml = (c.sources || []).map(s => `
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px]
          ${s.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}">
          <span>${s.ok ? '●' : '○'}</span>
          <span>${s.source}</span>
          <span class="text-slate-400">${s.latency_ms}ms</span>
        </span>
      `).join('');
      return `
        <div class="border border-slate-100 rounded p-2">
          <div class="flex items-center justify-between mb-1">
            <span class="flex items-center gap-2">
              <span>${c.ok ? '✅' : '❌'}</span>
              <span class="font-medium">${c.name}</span>
              ${c.active_source && c.active_source !== '—' ? `
                <span class="ml-1 text-[11px] px-2 py-0.5 rounded bg-blue-50 text-blue-700">
                  当前使用：${c.active_source}
                </span>
              ` : ''}
            </span>
          </div>
          ${c.note ? `<div class="text-[11px] text-slate-500 mb-1.5">${c.note}</div>` : ''}
          <div class="flex flex-wrap gap-1.5">${sourcesHtml || '<span class="text-slate-400 text-[11px]">无备选源信息</span>'}</div>
        </div>
      `;
    }).join('');
  } catch (e) {
    icon.textContent = '❌';
    banner.className = 'card p-4 border-l-4 border-red-400';
    title.textContent = '数据接口情况检查失败';
    subtitle.textContent = e.message;
  }
};
refreshHealth();
// 每 60 秒自动刷新一次
if (!window._healthTimer) {
  window._healthTimer = setInterval(() => refreshHealth(), 60_000);
}

window.toggleHealthPanel = function() {
  const detail = document.getElementById('health-detail');
  const toggle = document.getElementById('health-toggle');
  detail.classList.toggle('hidden');
  toggle.textContent = detail.classList.contains('hidden') ? '▼' : '▲';
};

// -------- 预设 + 自定义权重 --------
let presets = [];
let selectedPreset = 'balanced';
let customWeights = null;  // {technical, fundamental, sentiment, moneyflow}

async function loadPresets() {
  try {
    const r = await API('/screen/presets');
    presets = r.presets;
    renderPresetCards();
  } catch (e) {
    document.getElementById('preset-cards').innerHTML =
      '<div class="col-span-full text-sm text-red-500">加载预设失败: ' + e.message + '</div>';
  }
}

function renderPresetCards() {
  const emojiMap = { balanced: '⚖️', momentum: '🚀', value: '💎', growth: '🌱', dividend: '💰' };
  const cardHtml = presets.map(p => {
    const active = p.key === selectedPreset && selectedPreset !== 'custom';
    return `
      <button
        onclick="selectPreset('${p.key}')"
        class="p-4 rounded-lg border-2 transition-all text-left ${active ? 'border-blue-500 bg-blue-50' : 'border-slate-200 bg-white hover:border-slate-300'}"
      >
        <div class="text-2xl mb-1">${emojiMap[p.key] || '📊'}</div>
        <div class="font-semibold text-sm">${p.name}</div>
        <div class="text-xs text-slate-500 mt-1 leading-relaxed">${p.desc}</div>
      </button>
    `;
  }).join('') + `
    <button
      onclick="openCustomWeight()"
      class="p-4 rounded-lg border-2 transition-all text-left ${selectedPreset === 'custom' ? 'border-blue-500 bg-blue-50' : 'border-dashed border-slate-300 hover:border-blue-400 bg-slate-50'}"
    >
      <div class="text-2xl mb-1">🎛️</div>
      <div class="font-semibold text-sm">自定义</div>
      <div class="text-xs text-slate-500 mt-1 leading-relaxed">自己拉滑块设权重</div>
    </button>
  `;
  document.getElementById('preset-cards').innerHTML = cardHtml;

  // 显示当前使用的权重
  const currentEl = document.getElementById('preset-current');
  if (currentEl) {
    let w;
    if (selectedPreset === 'custom' && customWeights) {
      w = customWeights;
      currentEl.innerHTML = `当前权重（自定义）: 技术 <b>${(w.technical*100).toFixed(0)}%</b> · 基本 <b>${(w.fundamental*100).toFixed(0)}%</b> · 情绪 <b>${(w.sentiment*100).toFixed(0)}%</b> · 资金 <b>${(w.moneyflow*100).toFixed(0)}%</b>`;
    } else {
      const p = presets.find(x => x.key === selectedPreset);
      if (p) {
        w = p.weights;
        currentEl.innerHTML = `当前权重: 技术 <b>${(w.technical*100).toFixed(0)}%</b> · 基本 <b>${(w.fundamental*100).toFixed(0)}%</b> · 情绪 <b>${(w.sentiment*100).toFixed(0)}%</b> · 资金 <b>${(w.moneyflow*100).toFixed(0)}%</b>`;
      }
    }
  }
}

window.selectPreset = function(key) {
  selectedPreset = key;
  renderPresetCards();
};

// 自定义权重弹窗
window.openCustomWeight = function() {
  document.getElementById('custom-weight-modal').classList.remove('hidden');
  // 初始化滑块（若已有自定义值则用之）
  const w = customWeights || { technical: 0.35, fundamental: 0.20, sentiment: 0.20, moneyflow: 0.25 };
  const map = { tech: 'technical', fund: 'fundamental', sent: 'sentiment', money: 'moneyflow' };
  Object.entries(map).forEach(([k, v]) => {
    const raw = Math.round((w[v] || 0) * 100);
    document.getElementById(`cw-${k}`).value = raw;
    document.getElementById(`cw-${k}-val`).textContent = raw;
  });
  updateCwTotal();
};

window.closeCustomWeight = function() {
  document.getElementById('custom-weight-modal').classList.add('hidden');
};

['tech','fund','sent','money'].forEach(k => {
  document.getElementById(`cw-${k}`).addEventListener('input', (e) => {
    document.getElementById(`cw-${k}-val`).textContent = e.target.value;
    updateCwTotal();
  });
});

function updateCwTotal() {
  const t = parseFloat(document.getElementById('cw-tech').value) || 0;
  const f = parseFloat(document.getElementById('cw-fund').value) || 0;
  const s = parseFloat(document.getElementById('cw-sent').value) || 0;
  const m = parseFloat(document.getElementById('cw-money').value) || 0;
  const sum = t + f + s + m;
  const totalEl = document.getElementById('cw-total');
  if (sum === 0) {
    totalEl.textContent = '0%（无效）';
    totalEl.className = 'font-semibold text-red-500';
  } else {
    totalEl.textContent = `${(t/sum*100).toFixed(0)}% + ${(f/sum*100).toFixed(0)}% + ${(s/sum*100).toFixed(0)}% + ${(m/sum*100).toFixed(0)}% = 100%`;
    totalEl.className = 'font-semibold text-emerald-600';
  }
}

window.applyCustomWeight = function() {
  const t = parseFloat(document.getElementById('cw-tech').value) || 0;
  const f = parseFloat(document.getElementById('cw-fund').value) || 0;
  const s = parseFloat(document.getElementById('cw-sent').value) || 0;
  const m = parseFloat(document.getElementById('cw-money').value) || 0;
  const sum = t + f + s + m;
  if (sum === 0) { alert('至少一个维度权重要大于 0'); return; }
  customWeights = {
    technical: t / sum,
    fundamental: f / sum,
    sentiment: s / sum,
    moneyflow: m / sum,
  };
  selectedPreset = 'custom';
  closeCustomWeight();
  renderPresetCards();
};

// 预设说明弹窗
window.showPresetHelp = function(e) {
  if (e) e.preventDefault();
  document.getElementById('preset-help-modal').classList.remove('hidden');
};
window.closePresetHelp = function() {
  document.getElementById('preset-help-modal').classList.add('hidden');
};

loadPresets();

// 页面加载时：恢复上一次的筛选结果（如果 24 小时内的）
(function restoreLastScreen() {
  try {
    const raw = localStorage.getItem('screen_last_result');
    if (!raw) return;
    const saved = JSON.parse(raw);
    if (!saved.at || !saved.resultHtml) return;
    const ageHr = (Date.now() - new Date(saved.at).getTime()) / 3_600_000;
    if (ageHr > 24) { localStorage.removeItem('screen_last_result'); return; }
    // 回填 UI，加提示
    document.getElementById('screen-status').innerHTML =
      `<span class="text-slate-500">上次筛选结果（${new Date(saved.at).toLocaleString()}） · </span>` + saved.statusText +
      ` <button onclick="clearLastScreen()" class="ml-2 text-xs text-slate-400 hover:text-red-500 underline">清除</button>`;
    document.getElementById('screen-result').innerHTML = saved.resultHtml;
    window.lastScreenContext = saved.context;
  } catch {}
})();

window.clearLastScreen = function() {
  localStorage.removeItem('screen_last_result');
  document.getElementById('screen-status').innerHTML = '';
  document.getElementById('screen-result').innerHTML = '';
  window.lastScreenContext = null;
};

// -------- 选股 --------
// 记住上一次筛选用的权重信息，供个股分析跳转时复用
window.lastScreenContext = null;

window.onScreenPoolChange = function() {
  const sel = document.getElementById('screen-pool');
  const panel = document.getElementById('all-a-filters');
  if (!sel || !panel) return;
  panel.classList.toggle('hidden', sel.value !== 'all');
};

// 双保险：直接注册 change 监听，避免 inline onchange 被 CSP 拦或被覆盖
document.addEventListener('DOMContentLoaded', () => {
  const sel = document.getElementById('screen-pool');
  if (sel) {
    sel.addEventListener('change', window.onScreenPoolChange);
    window.onScreenPoolChange();  // 页面初始时也同步一次
  }
});
// DOMContentLoaded 可能已经触发（脚本在底部），再兜底一次
setTimeout(() => window.onScreenPoolChange && window.onScreenPoolChange(), 0);

async function runScreen() {
  const btn = document.getElementById('screen-btn');
  const status = document.getElementById('screen-status');
  const resultEl = document.getElementById('screen-result');
  btn.disabled = true;
  document.getElementById('screen-btn-text').innerHTML = '<span class="spinner"></span> 筛选中...';
  status.innerHTML = `<div class="flex items-center gap-2"><span class="spinner"></span> 首次运行会拉数据，请耐心等待…（首次成分股+行情缓存后，后续会快很多）</div>`;
  resultEl.innerHTML = '';

  try {
    const pool = document.getElementById('screen-pool').value;
    const body = {
      pool,
      pool_limit: parseInt(document.getElementById('screen-pool-limit').value),
      preset: selectedPreset === 'custom' ? 'balanced' : selectedPreset,
      min_score: parseFloat(document.getElementById('screen-min-score').value) || 0,
      top_n: parseInt(document.getElementById('screen-top-n').value) || 10,
      use_llm: document.getElementById('screen-llm').checked,
    };
    if (selectedPreset === 'custom' && customWeights) {
      body.custom_weights = customWeights;
    }
    // 全 A 池附加过滤
    if (pool === 'all') {
      body.exchange = document.getElementById('all-a-exchange').value || 'all';
      const mp = parseFloat(document.getElementById('all-a-min-price').value);
      const xp = parseFloat(document.getElementById('all-a-max-price').value);
      const mm = parseFloat(document.getElementById('all-a-min-mcap').value);
      const xm = parseFloat(document.getElementById('all-a-max-mcap').value);
      if (!isNaN(mp)) body.min_price = mp;
      if (!isNaN(xp)) body.max_price = xp;
      if (!isNaN(mm)) body.min_market_cap = mm;
      if (!isNaN(xm)) body.max_market_cap = xm;
      body.exclude_st = document.getElementById('all-a-exclude-st').checked;
    }

    const r = await API('/screen', { method: 'POST', body: JSON.stringify(body) });
    window.lastScreenContext = {
      preset: r.preset,
      preset_name: r.preset_name,
      weights: r.weights,
      custom_weights: body.custom_weights || null,
    };
    const statusText = `已从 <b>${r.pool_size}</b> 只中筛选出综合分 ≥ ${body.min_score} 的 <b>${r.matched}</b> 只，展示前 <b>${r.results.length}</b> 只 · 风格 <b>${r.preset_name}</b>`;
    status.innerHTML = statusText;

    let resultHtml;
    if (r.results.length === 0) {
      resultHtml = '<div class="p-8 text-center text-slate-500">没有股票达到筛选条件，试试降低"综合分下限"或放宽过滤？</div>';
    } else {
      resultHtml = renderScreenResults(r.results, r.weights);
    }
    resultEl.innerHTML = resultHtml;

    // 缓存到 localStorage：刷新后自动回填
    try {
      localStorage.setItem('screen_last_result', JSON.stringify({
        at: new Date().toISOString(),
        body, statusText, resultHtml,
        context: window.lastScreenContext,
      }));
    } catch {}
  } catch (e) {
    status.innerHTML = `<span class="text-red-500">失败: ${e.message}</span>`;
  } finally {
    btn.disabled = false;
    document.getElementById('screen-btn-text').textContent = '开始筛选';
  }
}
window.runScreen = runScreen;

function scoreColor(v) {
  if (v >= 80) return 'text-red-600';
  if (v >= 65) return 'text-orange-500';
  if (v >= 50) return 'text-slate-600';
  return 'text-emerald-600';
}
function scoreBarColor(v) {
  if (v >= 80) return '#dc2626';
  if (v >= 65) return '#f97316';
  if (v >= 50) return '#64748b';
  return '#10b981';
}

function renderScreenResults(results, weights) {
  return `
    <div class="text-xs text-slate-400 mb-3">
      当前权重：技术 ${(weights.technical*100).toFixed(0)}% · 基本 ${(weights.fundamental*100).toFixed(0)}% · 情绪 ${(weights.sentiment*100).toFixed(0)}% · 资金 ${(weights.moneyflow*100).toFixed(0)}%
    </div>
    <div class="space-y-3">
      ${results.map((r, i) => `
        <div class="border border-slate-200 rounded-lg p-4 bg-white hover:shadow-md transition-shadow cursor-pointer" onclick="viewDetailFrom('${r.symbol}', '${r.name}')">
          <div class="flex items-center gap-4">
            <div class="w-8 text-xl font-bold text-slate-400">${i + 1}</div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="font-semibold">${r.name || r.symbol}</span>
                <span class="text-xs text-slate-400 font-mono">${r.symbol}</span>
              </div>
              <div class="mt-2 grid grid-cols-4 gap-3">
                ${['technical','fundamental','sentiment','moneyflow'].map(k => {
                  const label = {technical:'技术',fundamental:'基本',sentiment:'情绪',moneyflow:'资金'}[k];
                  const v = r[k];
                  return `
                    <div class="text-xs">
                      <div class="flex justify-between text-slate-500 mb-0.5">
                        <span>${label}</span><span class="${scoreColor(v)}">${v.toFixed(0)}</span>
                      </div>
                      <div class="score-bar"><div style="width:${v}%; background:${scoreBarColor(v)}"></div></div>
                    </div>
                  `;
                }).join('')}
              </div>
            </div>
            <div class="text-right">
              <div class="text-3xl font-bold ${scoreColor(r.total)}">${r.total.toFixed(1)}</div>
              <div class="text-xs text-slate-400">综合分</div>
            </div>
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

window.viewDetailFrom = function(symbol, name) {
  document.querySelector('[data-tab="detail"]').click();
  document.getElementById('detail-search').value = name || symbol;
  document.getElementById('detail-search').dataset.code = symbol;
  // 跳转来源：继承选股页的权重上下文
  window.detailWeightsFromScreen = window.lastScreenContext || null;
  runDetail();
};

// -------- 个股分析 --------
let searchTimer = null;
document.getElementById('detail-search').addEventListener('input', (e) => {
  clearTimeout(searchTimer);
  const q = e.target.value.trim();
  if (!q) {
    document.getElementById('detail-suggest').classList.add('hidden');
    return;
  }
  searchTimer = setTimeout(async () => {
    try {
      const r = await API(`/market/search?q=${encodeURIComponent(q)}&limit=8`);
      const el = document.getElementById('detail-suggest');
      if (!r.items.length) {
        el.classList.add('hidden');
        return;
      }
      el.innerHTML = r.items.map(x => `
        <div class="px-3 py-2 hover:bg-slate-100 cursor-pointer text-sm" onclick="pickStock('${x.code}','${x.name}')">
          <span class="font-mono text-slate-500 mr-2">${x.code}</span>${x.name}
        </div>
      `).join('');
      el.classList.remove('hidden');
    } catch {}
  }, 250);
});

window.pickStock = function(code, name) {
  document.getElementById('detail-search').value = `${name} (${code})`;
  document.getElementById('detail-search').dataset.code = code;
  document.getElementById('detail-suggest').classList.add('hidden');
};

document.addEventListener('click', (e) => {
  if (!e.target.closest('#detail-search') && !e.target.closest('#detail-suggest')) {
    document.getElementById('detail-suggest').classList.add('hidden');
  }
});

async function runDetail() {
  const inputEl = document.getElementById('detail-search');
  let code = inputEl.dataset.code;
  if (!code) {
    // 尝试直接从输入里提取 6 位数字
    const m = inputEl.value.match(/\d{6}/);
    if (m) code = m[0];
  }
  if (!code) {
    alert('请输入股票代码或选一个建议项');
    return;
  }
  const btn = document.getElementById('detail-btn');
  const status = document.getElementById('detail-status');
  const resultEl = document.getElementById('detail-result');
  btn.disabled = true;
  status.innerHTML = '<span class="spinner"></span> 分析中...';
  resultEl.classList.add('hidden');

  try {
    const body = { symbol: code, use_llm: document.getElementById('detail-llm').checked };
    // 若从选股页跳过来，带上当时的权重；否则用当前所选的 preset/custom
    const ctx = window.detailWeightsFromScreen;
    if (ctx) {
      if (ctx.custom_weights) body.custom_weights = ctx.custom_weights;
      else if (ctx.preset) body.preset = ctx.preset;
    } else {
      if (selectedPreset === 'custom' && customWeights) body.custom_weights = customWeights;
      else if (selectedPreset) body.preset = selectedPreset;
    }
    const r = await API('/score', { method: 'POST', body: JSON.stringify(body) });
    // 用完就清，避免手动搜索时被复用
    window.detailWeightsFromScreen = null;
    status.textContent = `分析完成 · ${code}`;
    resultEl.classList.remove('hidden');
    resultEl.innerHTML = renderDetail(r);
  } catch (e) {
    status.innerHTML = `<span class="text-red-500">失败: ${e.message}</span>`;
  } finally {
    btn.disabled = false;
  }
}
window.runDetail = runDetail;

// 每个子项的中文标签 + 一句话解释，跟后端 analysis/*.py 的实际实现对齐
const SUB_LABELS = {
  technical: {
    trend:      { label: '趋势（均线多头）', help: '价 > MA5 > MA20 > MA60 满 3 项=100，满 2=75，满 1=50，全不满=25' },
    momentum:   { label: '动量（近 20 日涨幅）', help: '涨幅 -15% 起 20 分，0% 约 55，+5% 约 70，+15% 约 90' },
    rsi:        { label: 'RSI 强弱',       help: 'RSI(14) 在 45–65 健康区 85–100；<35 超卖或 >75 超买则减分' },
    volume:     { label: '量能（放量比）', help: '近 5 日均量 / 近 20 日均量：1.0 中性，>1.5 放量 80+，<0.5 缩量 30-' },
    volatility: { label: '波动率（ATR%）', help: 'ATR/价 1.5%–3.5% 为健康区 85+，过低（呆滞）或过高（剧烈）均减分' },
  },
  fundamental: {
    valuation:     { label: '估值分位',   help: '当前 PE/PB 在过去 3 年中的分位，越低（越便宜）打分越高' },
    profitability: { label: '盈利能力',   help: 'ROE > 15% 接近满分，8% 为中性 50，< 5% 差' },
    growth:        { label: '成长性',     help: '营业收入同比增速，每 +1% 加 2 分（+25% 就 100）' },
  },
  moneyflow: {
    northbound:  { label: '北向持仓变化', help: '近 5 日陆股通持股比例增减 0.5% ≈ 满分/零分' },
    main_inflow: { label: '主力净流入',   help: '近 5 日主力资金净流入为正的天数占比 → 得分' },
    turnover:    { label: '换手率',       help: '近 5 日平均换手率 4% 附近最高分；过低滞涨、过高异动均减分' },
  },
};

function _subScoreList(subDict, dim) {
  const labelMap = SUB_LABELS[dim] || {};
  const keys = Object.keys(subDict || {});
  if (!keys.length) return '<div class="text-xs text-slate-400 mt-2">（子项数据不可用，本维度按中性 50 分兜底）</div>';
  return `
    <div class="mt-3 space-y-2">
      ${keys.map(k => {
        const v = subDict[k];
        const numeric = typeof v === 'number' ? v : parseFloat(v);
        if (isNaN(numeric)) return '';
        const info = labelMap[k] || { label: k, help: '' };
        return `
          <div>
            <div class="flex justify-between text-xs">
              <span class="text-slate-600" title="${info.help}">${info.label}</span>
              <span class="${scoreColor(numeric)} font-medium">${numeric.toFixed(1)}</span>
            </div>
            <div class="score-bar"><div style="width:${Math.max(0,Math.min(100,numeric))}%; background:${scoreBarColor(numeric)}"></div></div>
            ${info.help ? `<div class="text-[11px] text-slate-400 mt-0.5">${info.help}</div>` : ''}
          </div>
        `;
      }).join('')}
      <div class="text-[11px] text-slate-400 pt-1 border-t border-slate-100">
        本维度得分 = 上述子项的<b>算术平均</b>
      </div>
    </div>
  `;
}

function renderDetail(r) {
  const w = r.weights || { technical: 0.35, fundamental: 0.20, sentiment: 0.20, moneyflow: 0.25 };
  const dimensions = [
    { key: 'technical',   label: '技术面', color: '#3b82f6', desc: '看 K 线走势健不健康' },
    { key: 'fundamental', label: '基本面', color: '#f59e0b', desc: '看公司质地好不好' },
    { key: 'sentiment',   label: '情绪面', color: '#a855f7', desc: 'AI 读近期公告 / 新闻' },
    { key: 'moneyflow',   label: '资金面', color: '#10b981', desc: '看聪明钱在不在买' },
  ];
  const sentDetail = r.detail?.sentiment || {};
  const sentHighlights = sentDetail.highlights || [];
  const sentRisks = sentDetail.risk_flags || [];

  // 按权重算每一项的加权贡献（可能会因权重浮点略有偏差，用实际返回的 total 展示更准确）
  const contribs = dimensions.map(d => ({
    ...d,
    score: r[d.key],
    weight: (w[d.key] || 0),
    contrib: (r[d.key] || 0) * (w[d.key] || 0),
  }));
  const sumContrib = contribs.reduce((s, c) => s + c.contrib, 0);

  // 权重来源标签
  const wsName = r.weights_source_name || '默认';
  const wsColor = r.weights_source === 'custom' ? 'bg-blue-100 text-blue-700' :
                  r.weights_source === 'default' ? 'bg-slate-100 text-slate-600' :
                                                   'bg-emerald-100 text-emerald-700';

  return `
    <div class="card p-6 space-y-6">
      <!-- 顶部：股票 + 总分 -->
      <div class="flex items-center justify-between">
        <div>
          <div class="text-lg font-mono text-slate-500">${r.symbol}</div>
          <div class="text-2xl font-semibold mt-1">
            综合评分分析
            <span class="ml-2 text-xs px-2 py-0.5 rounded ${wsColor} font-normal">权重来源：${wsName}</span>
          </div>
          <div class="text-xs text-slate-500 mt-1">分析日期：${r.as_of || '—'}</div>
        </div>
        <div class="text-right">
          <div class="text-5xl font-bold ${scoreColor(r.total)}">${r.total.toFixed(2)}</div>
          <div class="text-xs text-slate-400 mt-1">综合分 · 满分 100</div>
        </div>
      </div>

      <!-- 本次打分的权重占比 -->
      <div class="p-4 bg-slate-50 border border-slate-200 rounded-lg">
        <div class="text-sm font-semibold text-slate-700 mb-3">📐 本次打分使用的权重占比</div>
        <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
          ${contribs.map(c => `
            <div class="p-3 bg-white rounded border border-slate-100">
              <div class="flex items-center justify-between mb-1">
                <span class="text-xs text-slate-500">${c.label}</span>
                <span class="text-sm font-semibold">${(c.weight*100).toFixed(0)}%</span>
              </div>
              <div class="h-2 rounded overflow-hidden bg-slate-100">
                <div style="width:${c.weight*100}%; background:${c.color}; height:100%"></div>
              </div>
            </div>
          `).join('')}
        </div>
        <div class="text-xs text-slate-500 mt-3 leading-relaxed">
          综合分 = 技术面 × ${(w.technical*100).toFixed(0)}%
          + 基本面 × ${(w.fundamental*100).toFixed(0)}%
          + 情绪面 × ${(w.sentiment*100).toFixed(0)}%
          + 资金面 × ${(w.moneyflow*100).toFixed(0)}%
        </div>
      </div>

      <!-- 四个维度 · 子项明细 -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        ${dimensions.map(d => {
          const subDict = r.detail?.[d.key];
          const isSent = d.key === 'sentiment';
          const sub = isSent ? null : (subDict || {});
          return `
            <div class="border border-slate-200 rounded-lg p-4">
              <div class="flex items-center justify-between mb-1">
                <div>
                  <div class="font-semibold text-sm flex items-center gap-2">
                    <span>${d.label}</span>
                    <span class="text-[11px] px-1.5 py-0.5 rounded" style="background:${d.color}22; color:${d.color}">权重 ${(w[d.key]*100).toFixed(0)}%</span>
                  </div>
                  <div class="text-xs text-slate-400 mt-0.5">${d.desc}</div>
                </div>
                <div class="text-2xl font-bold ${scoreColor(r[d.key])}">${r[d.key].toFixed(0)}</div>
              </div>
              <div class="score-bar mt-2"><div style="width:${r[d.key]}%; background:${scoreBarColor(r[d.key])}"></div></div>
              ${isSent
                ? (sentDetail.reason
                    ? `<div class="mt-3 text-xs text-slate-600 leading-relaxed">${sentDetail.reason}</div>
                       <div class="mt-2 text-[11px] text-slate-400">AI provider: ${sentDetail.provider || '未知'}${sentDetail.error ? ' · 错误：'+sentDetail.error : ''}</div>`
                    : '<div class="mt-3 text-xs text-slate-400">未启用 AI 情绪或数据不可用，按中性 50 分兜底</div>')
                : _subScoreList(sub, d.key)}
              <div class="mt-3 text-xs bg-slate-50 rounded p-2 leading-relaxed">
                <b>加权贡献</b>：${r[d.key].toFixed(1)} × ${(w[d.key]*100).toFixed(0)}%
                = <span class="font-semibold ${scoreColor(r[d.key])}">${(r[d.key]*w[d.key]).toFixed(2)}</span> 分
              </div>
            </div>
          `;
        }).join('')}
      </div>

      <!-- 计算公式复盘 -->
      <div class="p-4 bg-blue-50 border border-blue-100 rounded-lg text-sm">
        <div class="font-semibold text-blue-900 mb-2">🧮 综合分是这么算出来的</div>
        <div class="font-mono text-xs md:text-sm text-blue-900 leading-relaxed break-all">
          ${contribs.map(c => `${c.score.toFixed(1)} × ${(c.weight*100).toFixed(0)}%`).join('  +  ')}
          <br>= ${contribs.map(c => c.contrib.toFixed(2)).join('  +  ')}
          <br>= <span class="text-lg font-bold ${scoreColor(r.total)}">${sumContrib.toFixed(2)}</span> ≈ <b>${r.total.toFixed(2)}</b> 分
        </div>
      </div>

      ${sentHighlights.length ? `
        <div class="p-4 bg-emerald-50 rounded-lg">
          <div class="text-sm font-semibold text-emerald-800 mb-2">✅ AI 识别到的利好点</div>
          <ul class="text-sm text-emerald-700 list-disc list-inside space-y-1">
            ${sentHighlights.map(h => `<li>${h}</li>`).join('')}
          </ul>
        </div>
      ` : ''}
      ${sentRisks.length ? `
        <div class="p-4 bg-red-50 rounded-lg">
          <div class="text-sm font-semibold text-red-800 mb-2">⚠️ AI 识别到的风险</div>
          <ul class="text-sm text-red-700 list-disc list-inside space-y-1">
            ${sentRisks.map(h => `<li>${h}</li>`).join('')}
          </ul>
        </div>
      ` : ''}

      <details class="text-xs">
        <summary class="cursor-pointer text-slate-500">查看原始 JSON（调试用）</summary>
        <pre class="mt-2 p-3 bg-slate-50 rounded text-xs overflow-auto">${JSON.stringify(r.detail, null, 2)}</pre>
      </details>
    </div>
  `;
}

// -------- 账户 --------
async function loadAccount() {
  const name = document.getElementById('acct-name').value.trim();
  if (!name) return alert('请输入账户名');
  try {
    const p = await API(`/portfolio/${name}`);
    renderAccount(p);
  } catch (e) {
    document.getElementById('acct-view').innerHTML = `<span class="text-amber-600">账户 <b>${name}</b> 未找到，可点"新建账户"</span>`;
  }
}
window.loadAccount = loadAccount;

async function newAccount() {
  const name = document.getElementById('acct-name').value.trim();
  const cash = parseFloat(document.getElementById('acct-cash').value) || 100000;
  if (!name) return alert('请输入账户名');
  try {
    const r = await API('/portfolio/new', { method: 'POST', body: JSON.stringify({ account_id: name, initial_cash: cash }) });
    renderAccount(r.account);
  } catch (e) {
    alert('失败: ' + e.message);
  }
}
window.newAccount = newAccount;

async function runPaper() {
  const name = document.getElementById('acct-name').value.trim() || 'swing_v1';
  const cash = parseFloat(document.getElementById('acct-cash').value) || 100000;
  const btn = document.getElementById('paper-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 运行中...';
  try {
    const r = await API('/paper/run', {
      method: 'POST',
      body: JSON.stringify({ account: name, initial_cash: cash, limit: 30, use_llm: false }),
    });
    renderAccount(r.portfolio);
  } catch (e) {
    alert('失败: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '运行今日策略';
  }
}
window.runPaper = runPaper;

function renderAccount(p) {
  const total = p.cash + Object.values(p.positions).reduce((s, x) => s + x.shares * x.last_price, 0);
  const pnl = ((total - p.initial_cash) / p.initial_cash * 100);
  const positions = Object.entries(p.positions);
  const posHtml = positions.length ? positions.map(([sym, pos]) => {
    const pnlPct = ((pos.last_price - pos.avg_cost) / pos.avg_cost * 100);
    return `<tr class="border-b border-slate-100">
      <td class="px-3 py-2 font-mono">${sym}</td>
      <td class="px-3 py-2">${pos.shares}</td>
      <td class="px-3 py-2">¥${pos.avg_cost.toFixed(2)}</td>
      <td class="px-3 py-2">¥${pos.last_price.toFixed(2)}</td>
      <td class="px-3 py-2 ${pnlPct >= 0 ? 'text-red-600' : 'text-emerald-600'}">${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%</td>
      <td class="px-3 py-2 text-xs text-slate-400">${pos.open_date}</td>
    </tr>`;
  }).join('') : '<tr><td colspan="6" class="px-3 py-6 text-slate-400 text-center">暂无持仓</td></tr>';
  const trades = p.trades.slice(-10).reverse();
  const trHtml = trades.length ? trades.map(t => `<tr class="border-b border-slate-100">
      <td class="px-3 py-2 text-xs">${t.date}</td>
      <td class="px-3 py-2 text-xs font-semibold ${t.side === 'buy' ? 'text-red-600' : 'text-emerald-600'}">${t.side === 'buy' ? '买' : '卖'}</td>
      <td class="px-3 py-2 font-mono text-xs">${t.symbol}</td>
      <td class="px-3 py-2 text-xs">${t.shares} 股 @ ¥${t.price.toFixed(2)}</td>
      <td class="px-3 py-2 text-xs text-slate-500">${t.reason}</td>
    </tr>`).join('') : '<tr><td colspan="5" class="px-3 py-6 text-slate-400 text-center">暂无成交</td></tr>';

  document.getElementById('acct-view').innerHTML = `
    <div class="grid grid-cols-3 gap-4 mb-6">
      <div class="p-4 bg-slate-50 rounded-lg">
        <div class="text-xs text-slate-500">可用现金</div>
        <div class="text-xl font-semibold mt-1">¥${p.cash.toLocaleString(undefined,{maximumFractionDigits:0})}</div>
      </div>
      <div class="p-4 bg-slate-50 rounded-lg">
        <div class="text-xs text-slate-500">账户总值</div>
        <div class="text-xl font-semibold mt-1">¥${total.toLocaleString(undefined,{maximumFractionDigits:0})}</div>
      </div>
      <div class="p-4 rounded-lg ${pnl >= 0 ? 'bg-red-50' : 'bg-emerald-50'}">
        <div class="text-xs ${pnl >= 0 ? 'text-red-600' : 'text-emerald-600'}">累计盈亏</div>
        <div class="text-xl font-semibold mt-1 ${pnl >= 0 ? 'text-red-600' : 'text-emerald-600'}">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%</div>
      </div>
    </div>

    <div class="font-semibold text-sm text-slate-700 mb-2">当前持仓</div>
    <div class="overflow-x-auto mb-6"><table class="min-w-full text-sm">
      <thead class="bg-slate-50 text-xs text-slate-500"><tr>
        <th class="px-3 py-2 text-left">代码</th>
        <th class="px-3 py-2 text-left">数量</th>
        <th class="px-3 py-2 text-left">成本</th>
        <th class="px-3 py-2 text-left">现价</th>
        <th class="px-3 py-2 text-left">浮盈</th>
        <th class="px-3 py-2 text-left">建仓日</th>
      </tr></thead><tbody>${posHtml}</tbody></table></div>

    <div class="font-semibold text-sm text-slate-700 mb-2">最近成交</div>
    <div class="overflow-x-auto"><table class="min-w-full text-sm">
      <thead class="bg-slate-50 text-xs text-slate-500"><tr>
        <th class="px-3 py-2 text-left">日期</th>
        <th class="px-3 py-2 text-left">方向</th>
        <th class="px-3 py-2 text-left">代码</th>
        <th class="px-3 py-2 text-left">数量/价格</th>
        <th class="px-3 py-2 text-left">原因</th>
      </tr></thead><tbody>${trHtml}</tbody></table></div>
  `;
}

// -------- AI 行动（Agent） --------
window._agentPollTimer = null;
window._agentCurrentTaskId = null;

async function refreshAgentProviderBadge() {
  const badge = document.getElementById('agent-provider-badge');
  if (!badge) return;
  try {
    const s = await API('/status');
    if (s.llm.configured) {
      badge.textContent = 'AI: ' + s.llm.provider;
      badge.className = 'ml-auto text-[11px] px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200';
    } else {
      badge.textContent = 'AI 未配置 · 走 stub 示例';
      badge.className = 'ml-auto text-[11px] px-2 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200';
    }
  } catch {}
}
refreshAgentProviderBadge();

async function autoResumeRunningAgent() {
  // 有 running 任务就自动挂上、开始轮询；即使当前不在 portfolio tab 也做
  try {
    const r = await API('/agent?limit=5');
    const running = r.tasks.find(t => t.status === 'running');
    if (running && !window._agentCurrentTaskId) {
      attachAgentTask(running.task_id);
    }
  } catch {}
}
// 页面加载时先检查一次，避免用户刷新后 running 任务被"孤儿化"
autoResumeRunningAgent();

window.startAgent = async function() {
  const goal = document.getElementById('agent-goal').value.trim();
  if (!goal) { alert('请输入你的目标'); return; }
  const maxIter = parseInt(document.getElementById('agent-max-iter').value) || 8;
  const btn = document.getElementById('agent-start-btn');
  const btnText = document.getElementById('agent-start-btn-text');
  const status = document.getElementById('agent-status');
  btn.disabled = true;
  btnText.innerHTML = '<span class="spinner"></span> 启动中...';
  status.innerHTML = '';
  document.getElementById('agent-log').innerHTML = '';
  document.getElementById('agent-final').classList.add('hidden');
  try {
    const r = await API('/agent/run', {
      method: 'POST',
      body: JSON.stringify({ goal, max_iterations: maxIter }),
    });
    window._agentCurrentTaskId = r.task_id;
    document.getElementById('agent-task-id').textContent = r.task_id;
    document.getElementById('agent-panel').classList.remove('hidden');
    status.innerHTML = `<span class="text-emerald-600">✓ 任务已启动，AI (${r.provider}) 正在思考...</span>`;
    // 1.5 秒轮询：LLM 思考中也能看到最新占位 step
    if (window._agentPollTimer) clearInterval(window._agentPollTimer);
    window._agentPollTimer = setInterval(refreshAgent, 1500);
    refreshAgent();
  } catch (e) {
    status.innerHTML = `<span class="text-red-500">失败: ${e.message}</span>`;
  } finally {
    btn.disabled = false;
    btnText.textContent = '🚀 启动 AI 研究';
  }
};

window.refreshAgent = async function() {
  const id = window._agentCurrentTaskId;
  if (!id) return;
  try {
    const t = await API(`/agent/${id}`);
    document.getElementById('agent-step-count').textContent = `${t.steps.length}/${t.max_iterations}`;
    document.getElementById('agent-stop-btn').classList.toggle('hidden', t.status !== 'running');
    const pill = document.getElementById('agent-status-pill');
    const pillCls = {
      running: 'bg-blue-100 text-blue-700',
      done: 'bg-emerald-100 text-emerald-700',
      failed: 'bg-red-100 text-red-700',
      cancelled: 'bg-slate-100 text-slate-700',
    }[t.status] || 'bg-slate-100 text-slate-700';
    pill.className = `text-[11px] px-2 py-0.5 rounded ${pillCls}`;
    pill.textContent = t.status;
    renderAgentSteps(t);
    if (t.status !== 'running') {
      if (window._agentPollTimer) clearInterval(window._agentPollTimer);
      window._agentPollTimer = null;
      renderAgentFinal(t);
      loadAgentHistory();
    }
  } catch (e) {
    console.warn('agent poll error', e);
  }
};

window.viewAgentMarkdown = async function() {
  const id = window._agentCurrentTaskId;
  if (!id) return;
  const modal = document.getElementById('agent-md-modal');
  const content = document.getElementById('agent-md-content');
  const dl = document.getElementById('agent-md-download');
  modal.classList.remove('hidden');
  content.innerHTML = '<div class="text-slate-400 text-center py-8"><span class="spinner"></span> 加载中...</div>';
  dl.href = `/api/agent/${id}/download`;
  try {
    const r = await API(`/agent/${id}/markdown`);
    // marked 已在 index.html 里加载
    content.innerHTML = window.marked ? window.marked.parse(r.markdown) : `<pre>${r.markdown}</pre>`;
  } catch (e) {
    content.innerHTML = `<div class="text-red-500">加载失败: ${e.message}</div>`;
  }
};

window.closeAgentMarkdown = function() {
  document.getElementById('agent-md-modal').classList.add('hidden');
};

window.stopAgent = async function() {
  const id = window._agentCurrentTaskId;
  if (!id) return;
  if (!confirm('确定停止当前 AI 任务？已跑过的步骤会保留。')) return;
  try {
    await API(`/agent/${id}/cancel`, { method: 'POST' });
    document.getElementById('agent-status').innerHTML = '<span class="text-slate-500">⏹ 已请求停止，等待下一轮退出...</span>';
    refreshAgent();
  } catch (e) {
    alert('停止失败: ' + e.message);
  }
};

async function loadAgentHistory() {
  try {
    const r = await API('/agent?limit=15');
    const el = document.getElementById('agent-history-list');
    if (!el) return;
    if (!r.tasks.length) { el.innerHTML = '<div class="text-xs text-slate-400">暂无历史任务</div>'; return; }
    el.innerHTML = r.tasks.map(t => {
      const cls = {
        running: 'bg-blue-50 text-blue-700 border-blue-200',
        done: 'bg-emerald-50 text-emerald-700 border-emerald-200',
        failed: 'bg-red-50 text-red-600 border-red-200',
        cancelled: 'bg-slate-50 text-slate-600 border-slate-200',
      }[t.status] || 'bg-slate-50 text-slate-600 border-slate-200';
      return `
        <div class="border rounded p-2 flex items-center gap-2 ${cls}">
          <span class="text-[11px] px-1.5 py-0.5 rounded bg-white/60 font-mono">${t.task_id}</span>
          <span class="text-[11px] px-1.5 py-0.5 rounded bg-white/60">${t.status}</span>
          <span class="text-xs flex-1 truncate">${t.goal}</span>
          <span class="text-[11px] text-slate-400 whitespace-nowrap">${t.step_count} 步 · ${(t.started_at||'').split('T')[0]}</span>
          <button onclick="attachAgentTask('${t.task_id}')" class="text-xs px-2 py-0.5 rounded bg-white/70 hover:bg-white">查看</button>
        </div>
      `;
    }).join('');
  } catch (e) {
    console.warn('load agent history failed', e);
  }
}

window.attachAgentTask = function(taskId) {
  window._agentCurrentTaskId = taskId;
  document.getElementById('agent-task-id').textContent = taskId;
  document.getElementById('agent-panel').classList.remove('hidden');
  document.getElementById('agent-log').innerHTML = '';
  document.getElementById('agent-final').classList.add('hidden');
  document.getElementById('agent-status').innerHTML = '<span class="text-slate-500">已加载任务，正在拉取详情...</span>';
  refreshAgent();
  // 如果正在跑，自动轮询
  API(`/agent/${taskId}`).then(t => {
    if (t.status === 'running') {
      if (window._agentPollTimer) clearInterval(window._agentPollTimer);
      window._agentPollTimer = setInterval(refreshAgent, 1500);
    }
  });
};

function renderAgentSteps(t) {
  const el = document.getElementById('agent-log');
  const actionColors = {
    list_strategies: 'bg-slate-100 text-slate-700',
    backtest_score: 'bg-blue-100 text-blue-700',
    backtest_technical: 'bg-emerald-100 text-emerald-700',
    create_strategy_from_text: 'bg-purple-100 text-purple-700',
    finish: 'bg-amber-100 text-amber-800',
    thinking: 'bg-indigo-100 text-indigo-700',
    llm_error: 'bg-red-100 text-red-700',
  };
  const phaseHint = {
    thinking: '<span class="spinner"></span> <span class="text-indigo-600">正在思考 · 等待 LLM 决策</span>',
    executing: '<span class="spinner"></span> <span class="text-blue-600">决策已得出，正在执行工具</span>',
    done: '',
    failed: '',
  };
  const phaseBorder = {
    thinking: 'border-indigo-300 bg-indigo-50/30 animate-pulse',
    executing: 'border-blue-300 bg-blue-50/30',
    done: 'border-slate-200 bg-white',
    failed: 'border-red-200 bg-red-50/40',
  };
  el.innerHTML = t.steps.map(s => {
    const badge = actionColors[s.action] || 'bg-slate-100 text-slate-700';
    const phase = s.phase || 'done';
    const borderCls = phaseBorder[phase] || 'border-slate-200 bg-white';
    let body = '';
    if (phase === 'thinking') {
      body = `<div class="text-xs text-indigo-700 mt-1">${phaseHint.thinking}</div>`;
    } else if (phase === 'executing') {
      body = `<div class="text-xs text-blue-700 mt-1">${phaseHint.executing}</div>`;
    }
    if (s.error) {
      body += `<div class="text-xs text-red-600 mt-1">❌ ${s.error}</div>`;
    } else if (s.action === 'backtest_score' || s.action === 'backtest_technical') {
      const m = s.result?.metrics || {};
      const cfg = s.result?.config || {};
      if (Object.keys(m).length) {
        body += `
          <div class="text-xs text-slate-600 mt-1">
            <b>配置：</b>${JSON.stringify(cfg, null, 0)}
          </div>
          <div class="mt-1 flex flex-wrap gap-3 text-xs">
            <span>累计: <b class="${(m.cumulative_return||0)>=0?'text-red-600':'text-emerald-600'}">${((m.cumulative_return||0)*100).toFixed(1)}%</b></span>
            <span>年化: <b>${((m.annualized_return||0)*100).toFixed(1)}%</b></span>
            <span>回撤: <b class="text-emerald-600">-${((m.max_drawdown||0)*100).toFixed(1)}%</b></span>
            <span>夏普: <b>${(m.sharpe||0).toFixed(2)}</b></span>
            <span>成交: <b>${s.result?.trades_count||0}</b></span>
          </div>
        `;
      }
    } else if (s.action === 'list_strategies' && s.result) {
      const n = s.result.strategies?.length || 0;
      body += `<div class="text-xs text-slate-600 mt-1">拿到 ${n} 个策略</div>`;
    } else if (s.action === 'create_strategy_from_text' && s.result) {
      body += `<div class="text-xs text-slate-600 mt-1">✓ 新建策略 <code>${s.result.strategy_id}</code>：${s.result.notes || ''}</div>`;
    }
    return `
      <div class="border rounded p-3 transition-all ${borderCls}">
        <div class="flex items-center gap-2">
          <span class="text-xs text-slate-400 font-mono">#${s.idx}</span>
          <span class="text-xs px-2 py-0.5 rounded ${badge} font-medium">${s.action}</span>
          <span class="text-xs text-slate-400 ml-auto">${s.duration_ms||0}ms · ${(s.at||'').split('T')[1] || ''}</span>
        </div>
        ${s.reason ? `<div class="text-xs text-slate-600 mt-1">💭 ${s.reason}</div>` : ''}
        ${body}
      </div>
    `;
  }).join('') || '<div class="text-sm text-slate-400 p-4 text-center">AI 正在思考中...</div>';
  el.scrollTop = el.scrollHeight;
}

function renderAgentFinal(t) {
  const el = document.getElementById('agent-final');
  el.classList.remove('hidden');
  const status = document.getElementById('agent-status');
  if (t.status === 'done') {
    status.innerHTML = `<span class="text-emerald-600">✅ AI 研究完成</span>`;
    const best = t.final?.best;
    const alts = t.final?.alternatives || [];
    el.innerHTML = `
      <div class="text-sm font-semibold text-emerald-900 mb-2">🎯 AI 结论</div>
      <div class="text-sm text-emerald-800 leading-relaxed mb-3">${t.final?.summary || '（无总结）'}</div>
      ${best ? `
        <div class="p-3 bg-white rounded border border-emerald-200 mb-2">
          <div class="text-xs text-slate-500 mb-1">推荐配置</div>
          <pre class="text-xs overflow-auto">${JSON.stringify(best, null, 2)}</pre>
        </div>
      ` : ''}
      ${alts.length ? `
        <div class="text-xs text-slate-500 mt-2">备选方案 ${alts.length} 个：</div>
        <details class="text-xs mt-1">
          <summary class="cursor-pointer text-emerald-700">展开</summary>
          <pre class="mt-1 overflow-auto">${JSON.stringify(alts, null, 2)}</pre>
        </details>
      ` : ''}
    `;
  } else if (t.status === 'failed') {
    status.innerHTML = `<span class="text-red-500">❌ 任务失败</span>`;
    el.className = 'mt-4 p-4 bg-red-50 border border-red-200 rounded';
    el.innerHTML = `<pre class="text-xs text-red-700 whitespace-pre-wrap">${t.error || '未知错误'}</pre>`;
  } else if (t.status === 'cancelled') {
    status.innerHTML = `<span class="text-slate-500">⏹ 已取消</span>`;
    el.innerHTML = '<div class="text-sm text-slate-500">任务已被取消</div>';
  }
}

// -------- 回测（任务化 · 后台跑 + 轮询 + 历史 + 可停） --------
let btChart = null;
window._btPollTimer = null;
window._btCurrentTaskId = null;

async function runBacktest() {
  const start = document.getElementById('bt-start').value;
  const end = document.getElementById('bt-end').value;
  const pool = document.getElementById('bt-pool').value;
  const limit = parseInt(document.getElementById('bt-limit').value) || 20;
  if (!start || !end) return alert('请选择起止日期');
  const btn = document.getElementById('bt-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 提交中...';

  const body = { start, end, pool, limit, initial_cash: 100000 };
  if (window.btStrategyType !== 'technical') {
    body.min_score = parseFloat(document.getElementById('bt-min-score').value) || 0;
  }
  if (window.btStrategyType === 'technical') {
    const id = document.getElementById('bt-strategy-id').value;
    if (!id) { alert('请选择技术策略'); btn.disabled = false; btn.textContent = '开始回测'; return; }
    const params = {};
    document.querySelectorAll('#bt-strategy-params [data-param]').forEach(inp => {
      params[inp.dataset.param] = parseFloat(inp.value);
    });
    body.strategy_type = 'technical';
    body.strategy_id = id;
    body.strategy_params = params;
  } else {
    body.strategy_type = 'score';
    body.preset = document.getElementById('bt-preset').value;
  }

  try {
    const r = await API('/backtest/run', { method: 'POST', body: JSON.stringify(body) });
    attachBacktestTask(r.task_id, r.label);
    loadBacktestHistory();
  } catch (e) {
    document.getElementById('bt-status').innerHTML = `<span class="text-red-500">失败: ${e.message}</span>`;
    btn.disabled = false;
    btn.textContent = '开始回测';
  }
}
window.runBacktest = runBacktest;

window.attachBacktestTask = function(taskId, label) {
  window._btCurrentTaskId = taskId;
  document.getElementById('bt-status').innerHTML = `<span class="spinner"></span> 任务 <span class="font-mono text-xs">${taskId}</span> · ${label || ''}`;
  document.getElementById('bt-progress').classList.remove('hidden');
  document.getElementById('bt-stop-btn').classList.remove('hidden');
  document.getElementById('bt-btn').textContent = '开始回测';
  document.getElementById('bt-btn').disabled = false;
  document.getElementById('bt-result').classList.add('hidden');
  if (window._btPollTimer) clearInterval(window._btPollTimer);
  window._btPollTimer = setInterval(refreshBacktest, 2000);
  refreshBacktest();
};

async function refreshBacktest() {
  const id = window._btCurrentTaskId;
  if (!id) return;
  try {
    const t = await API(`/backtest/tasks/${id}`);
    const status = document.getElementById('bt-status');
    const pb = document.getElementById('bt-progress-bar');
    const pt = document.getElementById('bt-progress-text');
    const stopBtn = document.getElementById('bt-stop-btn');
    if (t.status === 'running') {
      const p = t.progress || {};
      const pct = p.total ? (p.done / p.total * 100) : 0;
      pb.style.width = pct + '%';
      pt.textContent = `${p.done || 0} / ${p.total || '?'} 交易日 · 当前 ${p.day || '—'}`;
      status.innerHTML = `<span class="spinner"></span> ${t.label} · 进行中`;
      stopBtn.classList.remove('hidden');
    } else {
      stopBtn.classList.add('hidden');
      if (window._btPollTimer) clearInterval(window._btPollTimer);
      window._btPollTimer = null;
      if (t.status === 'done' && t.result) {
        document.getElementById('bt-progress').classList.add('hidden');
        status.innerHTML = `<span class="text-emerald-600">✓ 完成</span> · 成交 ${t.result.trades_count} 笔 · <span class="text-xs text-slate-400 font-mono">${id}</span>`;
        renderBacktestResult(t.result);
      } else if (t.status === 'failed') {
        status.innerHTML = `<span class="text-red-500">失败: ${(t.error || '').split('\n')[0]}</span>`;
      } else if (t.status === 'cancelled') {
        status.innerHTML = `<span class="text-slate-500">⏹ 已取消 · <span class="font-mono text-xs">${id}</span></span>`;
      }
      loadBacktestHistory();
    }
  } catch (e) {
    console.warn('bt poll error', e);
  }
}
window.refreshBacktest = refreshBacktest;

window.stopBacktest = async function() {
  const id = window._btCurrentTaskId;
  if (!id) return;
  if (!confirm('确定停止当前回测？已计算的进度不会保留（结果 = 空）。')) return;
  try {
    await API(`/backtest/tasks/${id}/cancel`, { method: 'POST' });
    document.getElementById('bt-status').innerHTML = '<span class="text-slate-500">⏹ 已请求停止，等待引擎在下一个交易日退出...</span>';
    refreshBacktest();
  } catch (e) {
    alert('停止失败: ' + e.message);
  }
};

function renderBacktestResult(r) {
  document.getElementById('bt-result').classList.remove('hidden');
  if (r.strategy_type === 'technical') {
    const paramStr = Object.entries(r.params || {}).map(([k, v]) => `${k}=${v}`).join(' ');
    document.getElementById('bt-meta').innerHTML = `
      策略类型：<b>技术指标</b> · 策略：<b>${r.strategy_id}</b>
      <span class="text-slate-400">${paramStr}</span>
    `;
  } else {
    const w = r.weights || {};
    document.getElementById('bt-meta').innerHTML = `
      策略：<b>swing_v1</b> · 风格：<b>${r.preset_name}</b>
      <span class="text-slate-400">
        (技术 ${(w.technical*100).toFixed(0)}% · 基本 ${(w.fundamental*100).toFixed(0)}%
        · 情绪 ${(w.sentiment*100).toFixed(0)}% · 资金 ${(w.moneyflow*100).toFixed(0)}%)
      </span>
    `;
  }
  const m = r.metrics;
  const cards = [
    ['累计收益', (m.cumulative_return * 100).toFixed(2) + '%', m.cumulative_return >= 0],
    ['年化收益', (m.annualized_return * 100).toFixed(2) + '%', m.annualized_return >= 0],
    ['最大回撤', '-' + (m.max_drawdown * 100).toFixed(2) + '%', false],
    ['夏普比率', m.sharpe.toFixed(2), m.sharpe >= 1],
  ];
  document.getElementById('bt-metrics').innerHTML = cards.map(([k, v, good]) => `
    <div class="p-4 border border-slate-200 rounded-lg">
      <div class="text-xs text-slate-500">${k}</div>
      <div class="text-xl font-semibold mt-1 ${good ? 'text-red-600' : 'text-slate-700'}">${v}</div>
    </div>`).join('');
  if (btChart) btChart.destroy();
  btChart = new Chart(document.getElementById('bt-chart'), {
    type: 'line',
    data: {
      labels: r.snapshots.map(s => s.date),
      datasets: [{
        label: '净值 (¥)', data: r.snapshots.map(s => s.total),
        borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)',
        tension: 0.1, pointRadius: 0, fill: true,
      }],
    },
    options: {
      scales: { x: { ticks: { maxTicksLimit: 12 } } },
      plugins: { legend: { display: false } },
    },
  });
  const trades = r.trades_sample || [];
  document.getElementById('bt-trades').innerHTML = trades.length ? `
    <div class="font-semibold text-sm text-slate-700 mb-2">最后 ${trades.length} 笔成交</div>
    <div class="overflow-x-auto"><table class="min-w-full text-sm">
      <thead class="bg-slate-50 text-xs text-slate-500"><tr>
        <th class="px-3 py-2 text-left">日期</th>
        <th class="px-3 py-2 text-left">方向</th>
        <th class="px-3 py-2 text-left">代码</th>
        <th class="px-3 py-2 text-left">数量/价格</th>
        <th class="px-3 py-2 text-left">原因</th>
      </tr></thead><tbody>
        ${trades.map(t => `<tr class="border-b border-slate-100">
          <td class="px-3 py-2 text-xs">${t.date}</td>
          <td class="px-3 py-2 text-xs font-semibold ${t.side === 'buy' ? 'text-red-600' : 'text-emerald-600'}">${t.side === 'buy' ? '买' : '卖'}</td>
          <td class="px-3 py-2 font-mono text-xs">${t.symbol}</td>
          <td class="px-3 py-2 text-xs">${t.shares} 股 @ ¥${t.price.toFixed(2)}</td>
          <td class="px-3 py-2 text-xs text-slate-500">${t.reason}</td>
        </tr>`).join('')}
      </tbody></table></div>
  ` : '';
}

async function loadBacktestHistory() {
  const el = document.getElementById('bt-history-list');
  if (!el) return;
  try {
    const r = await API('/backtest/tasks?limit=20');
    if (!r.tasks.length) { el.innerHTML = '<div class="text-xs text-slate-400">暂无历史任务</div>'; return; }
    el.innerHTML = r.tasks.map(t => {
      const cls = {
        running: 'bg-blue-50 text-blue-700 border-blue-200',
        done: 'bg-emerald-50 text-emerald-700 border-emerald-200',
        failed: 'bg-red-50 text-red-600 border-red-200',
        cancelled: 'bg-slate-50 text-slate-600 border-slate-200',
      }[t.status] || 'bg-slate-50 text-slate-600 border-slate-200';
      const m = t.metrics_summary || {};
      const metrics = t.status === 'done' && m.cumulative_return != null
        ? `累计 ${(m.cumulative_return*100).toFixed(1)}% · 年化 ${(m.annualized_return*100).toFixed(1)}% · 夏普 ${m.sharpe.toFixed(2)}`
        : (t.status === 'running' && t.progress?.total
            ? `进度 ${t.progress.done}/${t.progress.total}`
            : '—');
      const safeLabel = (t.label||'').replace(/'/g, '\\\'');
      return `
        <div class="border rounded p-2 flex items-center gap-2 ${cls}">
          <span class="text-[11px] px-1.5 py-0.5 rounded bg-white/60 font-mono">${t.task_id}</span>
          <span class="text-[11px] px-1.5 py-0.5 rounded bg-white/60">${t.status}</span>
          <span class="text-xs flex-1 truncate">${t.label || '—'}</span>
          <span class="text-[11px] text-slate-500 whitespace-nowrap">${metrics}</span>
          <button onclick="attachBacktestTask('${t.task_id}','${safeLabel}')"
            class="text-xs px-2 py-0.5 rounded bg-white/70 hover:bg-white">查看</button>
        </div>
      `;
    }).join('');
  } catch (e) {
    console.warn('load bt history failed', e);
  }
}

async function autoResumeRunningBacktest() {
  try {
    const r = await API('/backtest/tasks?limit=5');
    const running = r.tasks.find(t => t.status === 'running');
    if (running && !window._btCurrentTaskId) {
      attachBacktestTask(running.task_id, running.label);
    }
  } catch {}
}
autoResumeRunningBacktest();

// -------- 设置 --------
async function loadSettings() {
  try {
    const r = await API('/settings');
    document.querySelectorAll('[data-env]').forEach(input => {
      const key = input.dataset.env;
      const item = r.env[key];
      if (!item) return;
      if (item.masked) {
        input.placeholder = item.value ? `已配置：${item.value}` : '未配置';
        input.value = '';
      } else {
        input.value = item.value || '';
      }
    });
    const s = r.strategy?.swing_v1 || {};
    document.querySelectorAll('[data-strategy]').forEach(input => {
      const key = input.dataset.strategy;
      if (key === 'position_size_pct') {
        // position_size 应该是 0-1 的比例。如果错存成 > 1（曾经的 bug），做个夹持
        const raw = s.position_size !== undefined ? s.position_size : 0.18;
        const clamped = raw > 1 ? 0.18 : raw;  // > 1 视为脏数据，恢复默认
        input.value = (clamped * 100).toFixed(0);
      } else if (key === 'stop_loss_pct' || key === 'take_profit_pct') {
        const raw = s[key] !== undefined ? s[key] : (key === 'stop_loss_pct' ? 0.05 : 0.15);
        const clamped = raw > 1 ? raw / 100 : raw;  // 兜底：> 1 说明存的是百分比
        input.value = (clamped * 100).toFixed(1);
      } else {
        input.value = s[key] !== undefined ? s[key] : '';
      }
    });
  } catch (e) {
    document.getElementById('settings-status').innerHTML = `<span class="text-red-500">加载失败: ${e.message}</span>`;
  }
}
window.loadSettings = loadSettings;

async function saveSettings() {
  const btn = document.getElementById('save-settings-btn');
  const status = document.getElementById('settings-status');
  btn.disabled = true;
  status.textContent = '保存中...';
  try {
    const env = {};
    document.querySelectorAll('[data-env]').forEach(input => {
      env[input.dataset.env] = input.value;
    });
    const strategy = { swing_v1: {} };
    document.querySelectorAll('[data-strategy]').forEach(input => {
      const key = input.dataset.strategy;
      let v = parseFloat(input.value);
      if (isNaN(v)) return;
      if (key === 'position_size_pct') {
        strategy.swing_v1.position_size = v / 100;
      } else if (key === 'stop_loss_pct' || key === 'take_profit_pct') {
        strategy.swing_v1[key] = v / 100;
      } else {
        strategy.swing_v1[key] = v;
      }
    });
    // 保留默认 weights（不通过 UI 改）
    strategy.swing_v1.weights = { technical: 0.35, fundamental: 0.20, sentiment: 0.20, moneyflow: 0.25 };

    await API('/settings', { method: 'POST', body: JSON.stringify({ env, strategy }) });
    status.innerHTML = '<span class="text-emerald-600">✓ 保存成功</span>';
    refreshStatus();
    setTimeout(loadSettings, 500);
  } catch (e) {
    status.innerHTML = `<span class="text-red-500">失败: ${e.message}</span>`;
  } finally {
    btn.disabled = false;
  }
}
window.saveSettings = saveSettings;

async function testNotify() {
  const status = document.getElementById('settings-status');
  status.textContent = '发送中...';
  try {
    const r = await API('/notify/test', {
      method: 'POST',
      body: JSON.stringify({ title: 'tonghuashunAI 测试', text: '如收到此消息说明配置成功' })
    });
    status.innerHTML = '结果：' + r.summary;
  } catch (e) {
    status.innerHTML = `<span class="text-red-500">失败: ${e.message}</span>`;
  }
}
window.testNotify = testNotify;

// -------- 策略实验室 --------
let allStrategies = [];
let indicators = [];
let builderBuyRules = [];
let builderSellRules = [];

async function loadStrategiesLab() {
  await loadPresetStrategies();
}

async function loadPresetStrategies() {
  try {
    const r = await API('/strategies');
    allStrategies = r.strategies;
    const preset = r.strategies.filter(s => s.kind === 'preset');
    const builder = r.strategies.filter(s => s.kind === 'builder');
    const python = r.strategies.filter(s => s.kind === 'python');
    const list = document.getElementById('preset-strategy-list');
    list.innerHTML = preset.map(s => `
      <div class="border border-slate-200 rounded-lg p-4 hover:shadow-md transition-shadow">
        <div class="flex items-start justify-between mb-2">
          <div>
            <div class="font-semibold">${s.name}</div>
            <div class="text-xs text-slate-400 mt-0.5">${s.category} · ${s.tags.join(' · ')}</div>
          </div>
        </div>
        <div class="text-sm text-slate-600 leading-relaxed">${s.description}</div>
        <details class="mt-2 text-xs">
          <summary class="cursor-pointer text-blue-500">参数</summary>
          <div class="mt-2 space-y-1">
            ${s.params.map(p => `<div class="flex justify-between"><span>${p.label}</span><span class="text-slate-400">默认 ${p.default}</span></div>`).join('')}
          </div>
        </details>
      </div>
    `).join('');
    // 若有 builder 或 python 策略，也追加显示
    if (builder.length || python.length) {
      list.innerHTML += `<div class="col-span-full mt-4 text-sm font-semibold text-slate-700">你创建的策略</div>` + [...builder, ...python].map(s => `
        <div class="border border-blue-200 bg-blue-50 rounded-lg p-4">
          <div class="flex items-start justify-between mb-2">
            <div>
              <div class="font-semibold">${s.name}</div>
              <div class="text-xs text-slate-400 mt-0.5">${s.kind === 'builder' ? '🎛️ 条件构建' : '🐍 Python'} · ${s.tags.join(' · ')}</div>
            </div>
          </div>
          <div class="text-sm text-slate-600">${s.description}</div>
        </div>
      `).join('');
    }
  } catch (e) {
    document.getElementById('preset-strategy-list').innerHTML = `<div class="text-red-500">加载失败: ${e.message}</div>`;
  }
}

async function loadIndicators() {
  if (indicators.length) return;
  try {
    const r = await API('/strategies/builder/indicators');
    indicators = r.indicators;
    if (builderBuyRules.length === 0) addRule('buy');
    if (builderSellRules.length === 0) addRule('sell');
  } catch (e) {
    document.getElementById('buy-rules').innerHTML = `<div class="text-red-500 text-xs">加载指标失败: ${e.message}</div>`;
  }
  // 同步更新 AI 徽章
  refreshAiProviderBadge();
}

async function refreshAiProviderBadge() {
  const badge = document.getElementById('ai-provider-badge');
  if (!badge) return;
  try {
    const s = await API('/status');
    if (s.llm.configured) {
      badge.textContent = 'AI: ' + s.llm.provider;
      badge.className = 'ml-auto text-[11px] px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200';
    } else {
      badge.textContent = 'AI 未配置 · 走 stub 示例';
      badge.className = 'ml-auto text-[11px] px-2 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200';
    }
  } catch {}
}

// AI 生成策略 —— 把结果 spec 填到 builder 表单里
window.runAiGenerate = async function(save) {
  const prompt = document.getElementById('ai-prompt').value.trim();
  if (!prompt) { alert('请先输入策略描述'); return; }
  const suggestedId = document.getElementById('builder-id').value.trim();
  const suggestedName = document.getElementById('builder-name').value.trim();
  const status = document.getElementById('ai-gen-status');
  const btn = document.getElementById('ai-gen-btn');
  const btnText = document.getElementById('ai-gen-btn-text');
  const saveBtn = document.getElementById('ai-save-btn');
  btn.disabled = true; saveBtn.disabled = true;
  btnText.innerHTML = '<span class="spinner"></span> AI 分析中...';
  status.textContent = '';
  document.getElementById('ai-notes').classList.add('hidden');
  try {
    const r = await API('/strategies/builder/from_ai', {
      method: 'POST',
      body: JSON.stringify({
        prompt,
        suggested_id: suggestedId || undefined,
        suggested_name: suggestedName || undefined,
        save,
      }),
    });
    const spec = r.spec;
    // 1) 填 id / name
    document.getElementById('builder-id').value = spec.id || '';
    document.getElementById('builder-name').value = spec.name || '';
    // 2) 填买/卖规则
    builderBuyRules = (spec.buy?.rules || []).map(r => ({
      indicator: r.indicator, op: r.op,
      params: r.params || {}, value: r.value ?? null,
    }));
    builderSellRules = (spec.sell?.rules || []).map(r => ({
      indicator: r.indicator, op: r.op,
      params: r.params || {}, value: r.value ?? null,
    }));
    // 3) 设置 logic
    const buyLogic = (spec.buy?.logic || 'AND').toUpperCase();
    const sellLogic = (spec.sell?.logic || 'OR').toUpperCase();
    document.querySelectorAll('input[name="buy-logic"]').forEach(el => el.checked = el.value === buyLogic);
    document.querySelectorAll('input[name="sell-logic"]').forEach(el => el.checked = el.value === sellLogic);
    renderRules('buy');
    renderRules('sell');
    // 4) 展示 AI 说明
    const notes = document.getElementById('ai-notes');
    notes.classList.remove('hidden');
    notes.innerHTML = `
      <div><b>AI 说明</b>（provider: ${r.provider}）</div>
      <div class="mt-1">${r.notes || '（无）'}</div>
      ${r.saved_to ? `<div class="mt-2 text-emerald-600">✓ 已保存到 ${r.saved_to}，可直接在回测里选择</div>` : ''}
    `;
    status.innerHTML = save
      ? '<span class="text-emerald-600">✓ AI 已生成并保存</span>'
      : '<span class="text-emerald-600">✓ AI 已把规则填到下方，检查后点「保存策略」</span>';
    if (save) loadPresetStrategies();
  } catch (e) {
    status.innerHTML = `<span class="text-red-500">失败: ${e.message}</span>`;
  } finally {
    btn.disabled = false; saveBtn.disabled = false;
    btnText.textContent = '✨ 生成到下面表单';
  }
};

window.addRule = function(side) {
  const rules = side === 'buy' ? builderBuyRules : builderSellRules;
  rules.push({ indicator: 'MA', op: 'cross_up', params: {}, value: null });
  renderRules(side);
};

window.removeRule = function(side, idx) {
  const rules = side === 'buy' ? builderBuyRules : builderSellRules;
  rules.splice(idx, 1);
  renderRules(side);
};

window.changeRuleIndicator = function(side, idx, ind) {
  const rules = side === 'buy' ? builderBuyRules : builderSellRules;
  rules[idx].indicator = ind;
  const indDef = indicators.find(i => i.key === ind);
  if (indDef) {
    rules[idx].op = indDef.ops[0].name;
    rules[idx].params = {};
    indDef.params.forEach(p => { rules[idx].params[p.name] = p.default; });
    const opDef = indDef.ops[0];
    if (opDef.value_type === 'number') rules[idx].value = opDef.value_default;
    else rules[idx].value = null;
  }
  renderRules(side);
};

window.changeRuleOp = function(side, idx, op) {
  const rules = side === 'buy' ? builderBuyRules : builderSellRules;
  rules[idx].op = op;
  const indDef = indicators.find(i => i.key === rules[idx].indicator);
  const opDef = indDef?.ops.find(o => o.name === op);
  if (opDef && opDef.value_type === 'number') {
    rules[idx].value = opDef.value_default;
  } else {
    rules[idx].value = null;
  }
  renderRules(side);
};

window.changeRuleValue = function(side, idx, value) {
  const rules = side === 'buy' ? builderBuyRules : builderSellRules;
  rules[idx].value = parseFloat(value);
};

window.changeRuleParam = function(side, idx, paramName, value) {
  const rules = side === 'buy' ? builderBuyRules : builderSellRules;
  rules[idx].params[paramName] = parseFloat(value);
};

function renderRules(side) {
  const rules = side === 'buy' ? builderBuyRules : builderSellRules;
  const container = document.getElementById(`${side}-rules`);
  container.innerHTML = rules.map((r, idx) => {
    const indDef = indicators.find(i => i.key === r.indicator);
    const opDef = indDef?.ops.find(o => o.name === r.op);
    const paramInputs = (indDef?.params || []).map(p => `
      <input type="number" class="field text-xs w-16 py-1" value="${r.params[p.name] ?? p.default}"
        onchange="changeRuleParam('${side}',${idx},'${p.name}',this.value)"
        title="${p.label}">
    `).join('');
    const valueInput = opDef?.value_type === 'number' ? `
      <input type="number" class="field text-xs w-16 py-1" value="${r.value ?? opDef.value_default}"
        step="0.1" onchange="changeRuleValue('${side}',${idx},this.value)">
    ` : '';
    return `
      <div class="flex items-center gap-2 p-2 bg-slate-50 rounded">
        <select class="field text-xs py-1 w-32" onchange="changeRuleIndicator('${side}',${idx},this.value)">
          ${indicators.map(i => `<option value="${i.key}" ${i.key === r.indicator ? 'selected' : ''}>${i.label}</option>`).join('')}
        </select>
        ${paramInputs}
        <select class="field text-xs py-1 flex-1" onchange="changeRuleOp('${side}',${idx},this.value)">
          ${(indDef?.ops || []).map(o => `<option value="${o.name}" ${o.name === r.op ? 'selected' : ''}>${o.label}</option>`).join('')}
        </select>
        ${valueInput}
        <button onclick="removeRule('${side}',${idx})" class="text-red-500 text-xs">✕</button>
      </div>
    `;
  }).join('') || '<div class="text-xs text-slate-400">还没有规则，点下面的按钮添加</div>';
}

window.saveBuilder = async function() {
  const id = document.getElementById('builder-id').value.trim();
  const name = document.getElementById('builder-name').value.trim();
  if (!id || !name) return alert('请填写策略 ID 和名称');
  if (!/^[a-zA-Z0-9_]+$/.test(id)) return alert('策略 ID 只能包含字母、数字、下划线');
  const buyLogic = document.querySelector('input[name="buy-logic"]:checked').value;
  const sellLogic = document.querySelector('input[name="sell-logic"]:checked').value;
  const btn = document.getElementById('save-builder-btn');
  const status = document.getElementById('builder-status');
  btn.disabled = true; status.textContent = '保存中...';
  try {
    const r = await API('/strategies/builder', {
      method: 'POST', body: JSON.stringify({
        id, name, description: `买入: ${buyLogic} of ${builderBuyRules.length} 规则`,
        buy: { logic: buyLogic, rules: builderBuyRules },
        sell: { logic: sellLogic, rules: builderSellRules },
      }),
    });
    status.innerHTML = `<span class="text-emerald-600">✓ 已保存为 ${r.id}，可以在回测中选择</span>`;
    loadPresetStrategies();
  } catch (e) {
    status.innerHTML = `<span class="text-red-500">失败: ${e.message}</span>`;
  } finally { btn.disabled = false; }
};

// Python 编辑器
async function loadPythonList() {
  try {
    const r = await API('/strategies/python/list');
    const list = document.getElementById('py-list');
    list.innerHTML = r.files.length ? r.files.map(f => `
      <li><a href="#" onclick="loadPythonFile('${f.filename}');return false" class="text-blue-500 hover:underline">${f.filename}</a></li>
    `).join('') : '<li class="text-slate-400 text-xs">暂无</li>';
  } catch (e) {}
}

window.loadPythonFile = async function(filename) {
  try {
    const r = await API(`/strategies/python/${filename}`);
    document.getElementById('py-filename').value = filename;
    document.getElementById('py-source').value = r.source;
  } catch (e) { alert('加载失败: ' + e.message); }
};

window.newPythonFile = async function() {
  try {
    const r = await API('/strategies/python/template');
    document.getElementById('py-filename').value = 'my_strategy.py';
    document.getElementById('py-source').value = r.template;
    document.getElementById('py-status').textContent = '';
  } catch (e) { alert('加载模板失败: ' + e.message); }
};

window.savePython = async function() {
  const filename = document.getElementById('py-filename').value.trim();
  const source = document.getElementById('py-source').value;
  if (!filename) return alert('请填文件名');
  const status = document.getElementById('py-status');
  status.textContent = '保存中...';
  try {
    const r = await API('/strategies/python', { method: 'POST', body: JSON.stringify({ filename, source }) });
    status.innerHTML = `<span class="text-emerald-600">✓ 已保存${r.strategy_id ? '并注册为 ' + r.strategy_id : ''}</span>`;
    loadPythonList();
    loadPresetStrategies();
  } catch (e) {
    status.innerHTML = `<span class="text-red-500">失败: ${e.message}</span>`;
  }
};

window.deletePython = async function() {
  const filename = document.getElementById('py-filename').value.trim();
  if (!filename) return;
  if (!confirm('确定删除 ' + filename + ' ？')) return;
  try {
    await API(`/strategies/python/${filename}`, { method: 'DELETE' });
    document.getElementById('py-filename').value = '';
    document.getElementById('py-source').value = '';
    loadPythonList();
    loadPresetStrategies();
  } catch (e) { alert('失败: ' + e.message); }
};

// -------- 回测：策略选择 --------
async function loadBacktestStrategies() {
  if (allStrategies.length === 0) {
    try {
      const r = await API('/strategies');
      allStrategies = r.strategies;
    } catch (e) { return; }
  }
  const sel = document.getElementById('bt-strategy-id');
  const optgroups = {};
  allStrategies.forEach(s => {
    if (!optgroups[s.kind]) optgroups[s.kind] = [];
    optgroups[s.kind].push(s);
  });
  const kindLabel = { preset: '📦 预置策略', builder: '🎛️ 条件构建', python: '🐍 Python' };
  sel.innerHTML = Object.entries(optgroups).map(([kind, list]) => `
    <optgroup label="${kindLabel[kind] || kind}">
      ${list.map(s => `<option value="${s.id}">${s.name} (${s.category})</option>`).join('')}
    </optgroup>
  `).join('');
  onBacktestStrategyChange();
}

window.onBacktestStrategyChange = function() {
  const id = document.getElementById('bt-strategy-id').value;
  const s = allStrategies.find(x => x.id === id);
  if (!s) return;
  document.getElementById('bt-strategy-desc').innerHTML = s.description;
  const paramsEl = document.getElementById('bt-strategy-params');
  paramsEl.innerHTML = s.params.map(p => `
    <div>
      <div class="label text-xs">${p.label} ${p.help ? `<span title="${p.help}" class="text-slate-400">ⓘ</span>` : ''}</div>
      <input data-param="${p.name}" type="number" value="${p.default}" step="${p.step || 1}"
        ${p.min !== null ? `min="${p.min}"` : ''} ${p.max !== null ? `max="${p.max}"` : ''}
        class="field text-sm">
    </div>
  `).join('');
};

// -------- 初始化 --------
// 默认日期填过去半年
(function initDates() {
  const end = new Date();
  const start = new Date();
  start.setMonth(start.getMonth() - 6);
  document.getElementById('bt-start').value = start.toISOString().slice(0, 10);
  document.getElementById('bt-end').value = end.toISOString().slice(0, 10);
})();
