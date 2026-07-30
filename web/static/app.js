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
  });
});

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

// -------- 预设 --------
let presets = [];
let selectedPreset = 'balanced';

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
  const html = presets.map(p => `
    <button
      data-preset="${p.key}"
      onclick="selectPreset('${p.key}')"
      class="preset-card p-4 rounded-lg border-2 transition-all text-left ${p.key === selectedPreset ? 'border-blue-500 bg-blue-50' : 'border-slate-200 bg-white hover:border-slate-300'}"
    >
      <div class="text-2xl mb-1">${emojiMap[p.key] || '📊'}</div>
      <div class="font-semibold text-sm">${p.name}</div>
      <div class="text-xs text-slate-500 mt-1 leading-relaxed">${p.desc}</div>
    </button>
  `).join('');
  document.getElementById('preset-cards').innerHTML = html;
}

window.selectPreset = function(key) {
  selectedPreset = key;
  renderPresetCards();
};

loadPresets();

// -------- 选股 --------
async function runScreen() {
  const btn = document.getElementById('screen-btn');
  const status = document.getElementById('screen-status');
  const resultEl = document.getElementById('screen-result');
  btn.disabled = true;
  document.getElementById('screen-btn-text').innerHTML = '<span class="spinner"></span> 筛选中...';
  status.innerHTML = `<div class="flex items-center gap-2"><span class="spinner"></span> 首次运行会拉数据，请耐心等待…（首次成分股+行情缓存后，后续会快很多）</div>`;
  resultEl.innerHTML = '';

  try {
    const body = {
      pool: document.getElementById('screen-pool').value,
      pool_limit: parseInt(document.getElementById('screen-pool-limit').value),
      preset: selectedPreset,
      min_score: parseFloat(document.getElementById('screen-min-score').value) || 0,
      top_n: parseInt(document.getElementById('screen-top-n').value) || 10,
      use_llm: document.getElementById('screen-llm').checked,
    };
    const r = await API('/screen', { method: 'POST', body: JSON.stringify(body) });
    status.innerHTML = `已从 <b>${r.pool_size}</b> 只中筛选出综合分 ≥ ${body.min_score} 的 <b>${r.matched}</b> 只，展示前 <b>${r.results.length}</b> 只 · 风格 <b>${r.preset_name}</b>`;

    if (r.results.length === 0) {
      resultEl.innerHTML = '<div class="p-8 text-center text-slate-500">没有股票达到筛选条件，试试降低"综合分下限"？</div>';
    } else {
      resultEl.innerHTML = renderScreenResults(r.results, r.weights);
    }
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
    const r = await API('/score', {
      method: 'POST',
      body: JSON.stringify({ symbol: code, use_llm: document.getElementById('detail-llm').checked }),
    });
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

function renderDetail(r) {
  const dimensions = [
    { key: 'technical',   label: '技术面', desc: 'K 线走势、均线、动量、RSI、量能、波动率' },
    { key: 'fundamental', label: '基本面', desc: '估值分位、ROE、营收增长' },
    { key: 'sentiment',   label: '情绪面', desc: 'AI 读公告 & 新闻的情绪评分' },
    { key: 'moneyflow',   label: '资金面', desc: '北向增持、主力净流入、换手率' },
  ];
  const sentDetail = r.detail?.sentiment || {};
  const sentHighlights = sentDetail.highlights || [];
  const sentRisks = sentDetail.risk_flags || [];

  return `
    <div class="card p-6">
      <div class="flex items-center justify-between mb-6">
        <div>
          <div class="text-lg font-mono text-slate-500">${r.symbol}</div>
          <div class="text-2xl font-semibold mt-1">${sentDetail.reason ? sentDetail.reason : '综合评分分析'}</div>
        </div>
        <div class="text-right">
          <div class="text-5xl font-bold ${scoreColor(r.total)}">${r.total.toFixed(1)}</div>
          <div class="text-xs text-slate-400 mt-1">综合分 · 满分 100</div>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        ${dimensions.map(d => `
          <div class="border border-slate-200 rounded-lg p-4">
            <div class="flex items-center justify-between mb-1">
              <div>
                <div class="font-semibold text-sm">${d.label}</div>
                <div class="text-xs text-slate-400 mt-0.5">${d.desc}</div>
              </div>
              <div class="text-2xl font-bold ${scoreColor(r[d.key])}">${r[d.key].toFixed(0)}</div>
            </div>
            <div class="score-bar mt-2"><div style="width:${r[d.key]}%; background:${scoreBarColor(r[d.key])}"></div></div>
            ${d.key === 'sentiment' && sentDetail.reason ? `<div class="mt-2 text-xs text-slate-600">${sentDetail.reason}</div>` : ''}
          </div>
        `).join('')}
      </div>

      ${sentHighlights.length ? `
        <div class="mt-6 p-4 bg-emerald-50 rounded-lg">
          <div class="text-sm font-semibold text-emerald-800 mb-2">✅ AI 识别到的利好点</div>
          <ul class="text-sm text-emerald-700 list-disc list-inside space-y-1">
            ${sentHighlights.map(h => `<li>${h}</li>`).join('')}
          </ul>
        </div>
      ` : ''}
      ${sentRisks.length ? `
        <div class="mt-3 p-4 bg-red-50 rounded-lg">
          <div class="text-sm font-semibold text-red-800 mb-2">⚠️ AI 识别到的风险</div>
          <ul class="text-sm text-red-700 list-disc list-inside space-y-1">
            ${sentRisks.map(h => `<li>${h}</li>`).join('')}
          </ul>
        </div>
      ` : ''}

      <details class="mt-6 text-xs">
        <summary class="cursor-pointer text-slate-500">四个维度的子项明细（JSON）</summary>
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

// -------- 回测 --------
let btChart = null;
async function runBacktest() {
  const start = document.getElementById('bt-start').value;
  const end = document.getElementById('bt-end').value;
  const pool = document.getElementById('bt-pool').value;
  const limit = parseInt(document.getElementById('bt-limit').value) || 20;
  if (!start || !end) return alert('请选择起止日期');
  const btn = document.getElementById('bt-btn');
  const status = document.getElementById('bt-status');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 回测中...';
  status.innerHTML = '<span class="spinner"></span> 逐日撮合中，几十秒到几分钟...';
  try {
    const r = await API('/backtest/run', {
      method: 'POST', body: JSON.stringify({ start, end, pool, limit, initial_cash: 100000 }),
    });
    status.textContent = `完成 · 成交 ${r.trades_count} 笔`;
    document.getElementById('bt-result').classList.remove('hidden');
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
  } catch (e) {
    status.innerHTML = `<span class="text-red-500">失败: ${e.message}</span>`;
  } finally {
    btn.disabled = false;
    btn.textContent = '开始回测';
  }
}
window.runBacktest = runBacktest;

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
      // position_size_pct = position_size * 100
      if (key === 'position_size_pct') {
        input.value = ((s.position_size || 0.18) * 100).toFixed(0);
      } else if (key === 'stop_loss_pct' || key === 'take_profit_pct') {
        input.value = ((s[key] || 0.05) * 100).toFixed(1);
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

// -------- 初始化 --------
// 默认日期填过去半年
(function initDates() {
  const end = new Date();
  const start = new Date();
  start.setMonth(start.getMonth() - 6);
  document.getElementById('bt-start').value = start.toISOString().slice(0, 10);
  document.getElementById('bt-end').value = end.toISOString().slice(0, 10);
})();
