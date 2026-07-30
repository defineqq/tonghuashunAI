// app.js — 前端逻辑
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

// ---------- Tab 切换 ----------
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
    btn.classList.add('active');
    document.getElementById(`tab-${btn.dataset.tab}`).classList.remove('hidden');
    if (btn.dataset.tab === 'qbot') loadQbotLists();
    if (btn.dataset.tab === 'report') loadReportList();
  });
});

// ---------- Status ----------
async function refreshStatus() {
  try {
    const s = await API('/status');
    const badge = document.getElementById('status-badge');
    const llmOk = s.llm.configured;
    badge.textContent = llmOk ? `LLM: ${s.llm.provider}` : 'LLM: stub';
    badge.className = 'px-2 py-1 rounded text-xs ' + (llmOk ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700');
    document.getElementById('s-llm').textContent = llmOk ? '✅ ' + s.llm.provider : '⚠️ stub';
    document.getElementById('s-feishu').textContent = s.notify.feishu ? '✅ 已配置' : '未配置';
    document.getElementById('s-dingtalk').textContent = s.notify.dingtalk ? '✅ 已配置' : '未配置';
    document.getElementById('s-email').textContent = s.notify.email ? '✅ 已配置' : '未配置';
  } catch (e) {
    document.getElementById('status-badge').textContent = '离线';
  }
}
refreshStatus();

// ---------- Score ----------
async function doScore() {
  const symbol = document.getElementById('score-symbol').value.trim();
  if (!symbol) return alert('请输入股票代码');
  const btn = event.target;
  btn.disabled = true; btn.textContent = '评分中...';
  try {
    const r = await API('/score', {
      method: 'POST',
      body: JSON.stringify({
        symbol,
        as_of: document.getElementById('score-asof').value || null,
        use_llm: document.getElementById('score-llm').checked,
      }),
    });
    document.getElementById('score-result').classList.remove('hidden');
    document.getElementById('score-total').textContent = r.total.toFixed(1);
    document.getElementById('score-tech').textContent = r.technical.toFixed(1);
    document.getElementById('score-fund').textContent = r.fundamental.toFixed(1);
    document.getElementById('score-sent').textContent = r.sentiment.toFixed(1);
    document.getElementById('score-money').textContent = r.moneyflow.toFixed(1);
    document.getElementById('score-detail').textContent = JSON.stringify(r.detail, null, 2);
  } catch (e) {
    alert('评分失败: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = '开始评分';
  }
}

// ---------- Rank ----------
async function doRank() {
  const pool = document.getElementById('rank-pool').value;
  const limit = parseInt(document.getElementById('rank-limit').value) || 30;
  const topn = parseInt(document.getElementById('rank-topn').value) || 10;
  const useLlm = document.getElementById('rank-llm').checked;
  const status = document.getElementById('rank-status');
  const btn = event.target;
  btn.disabled = true; btn.textContent = '排名中...';
  status.textContent = `拉取 ${pool} 成分股...`;
  try {
    const uni = await API(`/universe/${pool}?limit=${limit}`);
    const symbols = uni.items.map(x => x.code);
    status.textContent = `对 ${symbols.length} 只股票打分中（${useLlm ? '含' : '不含'} LLM，可能需要几分钟）...`;
    const r = await API('/rank', {
      method: 'POST',
      body: JSON.stringify({ symbols, top_n: topn, use_llm: useLlm }),
    });
    status.textContent = `完成，共 ${r.count} 只。`;
    const rows = r.data.map((row, i) => `
      <tr class="border-b">
        <td class="px-3 py-2">${i + 1}</td>
        <td class="px-3 py-2 font-mono">${row.symbol}</td>
        <td class="px-3 py-2 font-semibold text-blue-600">${row.total.toFixed(1)}</td>
        <td class="px-3 py-2">${row.technical.toFixed(1)}</td>
        <td class="px-3 py-2">${row.fundamental.toFixed(1)}</td>
        <td class="px-3 py-2">${row.sentiment.toFixed(1)}</td>
        <td class="px-3 py-2">${row.moneyflow.toFixed(1)}</td>
      </tr>`).join('');
    document.getElementById('rank-result').innerHTML = `
      <table class="min-w-full text-sm">
        <thead class="bg-slate-100"><tr>
          <th class="px-3 py-2 text-left">#</th>
          <th class="px-3 py-2 text-left">代码</th>
          <th class="px-3 py-2 text-left">综合</th>
          <th class="px-3 py-2 text-left">技术</th>
          <th class="px-3 py-2 text-left">基本</th>
          <th class="px-3 py-2 text-left">情绪</th>
          <th class="px-3 py-2 text-left">资金</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  } catch (e) {
    status.textContent = '失败: ' + e.message;
  } finally {
    btn.disabled = false; btn.textContent = '生成排名';
  }
}

// ---------- Report ----------
async function genReport() {
  const symbols = document.getElementById('report-symbols').value.split(',').map(s => s.trim()).filter(Boolean);
  const topn = parseInt(document.getElementById('report-topn').value) || 10;
  const status = document.getElementById('report-status');
  status.textContent = '生成中...';
  try {
    const r = await API('/report/daily', {
      method: 'POST',
      body: JSON.stringify({ symbols: symbols.length ? symbols : null, top_n: topn, save: true }),
    });
    status.textContent = `完成，保存在 ${r.path || '内存'}`;
    document.getElementById('report-view').innerHTML = marked.parse(r.markdown);
    loadReportList();
  } catch (e) {
    status.textContent = '失败: ' + e.message;
  }
}

async function loadReportList() {
  try {
    const r = await API('/report/list');
    const list = document.getElementById('report-list');
    list.innerHTML = r.reports.map(name => `
      <li><a href="#" onclick="viewReport('${name}');return false" class="text-blue-600 hover:underline">${name}</a></li>
    `).join('') || '<li class="text-slate-400">暂无</li>';
  } catch {}
}

window.viewReport = async function(name) {
  const r = await API(`/report/${name}`);
  document.getElementById('report-view').innerHTML = marked.parse(r.markdown);
};

// ---------- Portfolio ----------
async function loadAccount() {
  const name = document.getElementById('acct-name').value.trim();
  if (!name) return alert('请输入账户名');
  try {
    const p = await API(`/portfolio/${name}`);
    renderAccount(p);
  } catch (e) {
    document.getElementById('acct-view').textContent = `账户 ${name} 未找到，可点"新建"`;
  }
}
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
async function runPaper() {
  const name = document.getElementById('acct-name').value.trim() || 'swing_v1';
  const cash = parseFloat(document.getElementById('acct-cash').value) || 100000;
  const btn = event.target;
  btn.disabled = true; btn.textContent = '撮合中...';
  try {
    const r = await API('/paper/run', {
      method: 'POST',
      body: JSON.stringify({ account: name, initial_cash: cash, limit: 30, use_llm: false }),
    });
    renderAccount(r.portfolio);
  } catch (e) {
    alert('失败: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = '跑一次撮合';
  }
}
function renderAccount(p) {
  const total = p.cash + Object.values(p.positions).reduce((s, x) => s + x.shares * x.last_price, 0);
  const pnl = ((total - p.initial_cash) / p.initial_cash * 100).toFixed(2);
  const positions = Object.entries(p.positions).map(([sym, pos]) => {
    const pnlPct = ((pos.last_price - pos.avg_cost) / pos.avg_cost * 100).toFixed(2);
    return `<tr class="border-b">
      <td class="px-3 py-2 font-mono">${sym}</td>
      <td class="px-3 py-2">${pos.shares}</td>
      <td class="px-3 py-2">¥${pos.avg_cost.toFixed(2)}</td>
      <td class="px-3 py-2">¥${pos.last_price.toFixed(2)}</td>
      <td class="px-3 py-2 ${pnlPct >= 0 ? 'text-red-600' : 'text-emerald-600'}">${pnlPct >= 0 ? '+' : ''}${pnlPct}%</td>
      <td class="px-3 py-2 text-xs text-slate-500">${pos.open_date}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="6" class="px-3 py-4 text-slate-400 text-center">当前无持仓</td></tr>';
  const trades = p.trades.slice(-10).reverse().map(t => `<tr class="border-b">
      <td class="px-3 py-2">${t.date}</td>
      <td class="px-3 py-2 ${t.side === 'buy' ? 'text-red-600' : 'text-emerald-600'}">${t.side}</td>
      <td class="px-3 py-2 font-mono">${t.symbol}</td>
      <td class="px-3 py-2">${t.shares} × ¥${t.price.toFixed(2)}</td>
      <td class="px-3 py-2 text-xs text-slate-500">${t.reason}</td>
    </tr>`).join('');
  document.getElementById('acct-view').innerHTML = `
    <div class="grid grid-cols-3 gap-4 mb-4">
      <div class="p-3 bg-slate-50 rounded"><div class="text-xs text-slate-500">现金</div><div class="text-lg font-semibold">¥${p.cash.toLocaleString()}</div></div>
      <div class="p-3 bg-slate-50 rounded"><div class="text-xs text-slate-500">总市值</div><div class="text-lg font-semibold">¥${total.toLocaleString(undefined, {maximumFractionDigits: 2})}</div></div>
      <div class="p-3 bg-slate-50 rounded"><div class="text-xs text-slate-500">累计 PnL</div><div class="text-lg font-semibold ${pnl >= 0 ? 'text-red-600' : 'text-emerald-600'}">${pnl >= 0 ? '+' : ''}${pnl}%</div></div>
    </div>
    <div class="mb-3 font-semibold text-slate-700">当前持仓</div>
    <div class="overflow-x-auto"><table class="min-w-full text-sm">
      <thead class="bg-slate-100"><tr>
        <th class="px-3 py-2 text-left">代码</th><th class="px-3 py-2 text-left">数量</th>
        <th class="px-3 py-2 text-left">成本</th><th class="px-3 py-2 text-left">现价</th>
        <th class="px-3 py-2 text-left">浮盈%</th><th class="px-3 py-2 text-left">建仓</th>
      </tr></thead><tbody>${positions}</tbody></table></div>
    <div class="mt-6 mb-3 font-semibold text-slate-700">最近 10 笔成交</div>
    <div class="overflow-x-auto"><table class="min-w-full text-sm">
      <thead class="bg-slate-100"><tr>
        <th class="px-3 py-2 text-left">日期</th><th class="px-3 py-2 text-left">方向</th>
        <th class="px-3 py-2 text-left">代码</th><th class="px-3 py-2 text-left">量·价</th>
        <th class="px-3 py-2 text-left">原因</th>
      </tr></thead><tbody>${trades || '<tr><td colspan="5" class="px-3 py-4 text-slate-400 text-center">无</td></tr>'}</tbody></table></div>`;
}

// ---------- Backtest ----------
let btChart = null;
async function runBacktest() {
  const start = document.getElementById('bt-start').value;
  const end = document.getElementById('bt-end').value;
  const pool = document.getElementById('bt-pool').value;
  const limit = parseInt(document.getElementById('bt-limit').value) || 20;
  if (!start || !end) return alert('请选择起止日期');
  const status = document.getElementById('bt-status');
  const btn = event.target;
  btn.disabled = true; btn.textContent = '回测中（可能几分钟）...';
  status.textContent = '拉取数据 + 逐日撮合中...';
  try {
    const r = await API('/backtest/run', {
      method: 'POST',
      body: JSON.stringify({ start, end, pool, limit, initial_cash: 100000 }),
    });
    status.textContent = `完成 · 成交 ${r.trades_count} 笔 · 报告 ${r.report_path}`;
    document.getElementById('bt-result').classList.remove('hidden');
    const m = r.metrics;
    const cards = [
      ['累计收益', (m.cumulative_return * 100).toFixed(2) + '%', m.cumulative_return >= 0],
      ['年化收益', (m.annualized_return * 100).toFixed(2) + '%', m.annualized_return >= 0],
      ['最大回撤', (m.max_drawdown * 100).toFixed(2) + '%', false],
      ['夏普比率', m.sharpe.toFixed(2), m.sharpe >= 1],
    ];
    document.getElementById('bt-metrics').innerHTML = cards.map(([k, v, good]) => `
      <div class="p-3 border rounded">
        <div class="text-xs text-slate-500">${k}</div>
        <div class="text-xl font-semibold ${good ? 'text-red-600' : 'text-slate-700'}">${v}</div>
      </div>`).join('');
    if (btChart) btChart.destroy();
    btChart = new Chart(document.getElementById('bt-chart'), {
      type: 'line',
      data: {
        labels: r.snapshots.map(s => s.date),
        datasets: [{
          label: '净值 (¥)',
          data: r.snapshots.map(s => s.total),
          borderColor: '#2563eb',
          backgroundColor: 'rgba(37,99,235,0.1)',
          tension: 0.1,
          pointRadius: 0,
        }],
      },
      options: {
        scales: { x: { ticks: { maxTicksLimit: 12 } } },
        plugins: { legend: { display: false } },
      },
    });
  } catch (e) {
    status.textContent = '失败: ' + e.message;
  } finally {
    btn.disabled = false; btn.textContent = '开始回测';
  }
}

// ---------- Qbot ----------
async function loadQbotLists() {
  try {
    const r = await API('/qbot/strategies');
    document.getElementById('qbot-strategy-list').innerHTML = r.strategies.map(s => `
      <li><a href="#" onclick="viewQbotStrategy('${s.name}');return false" class="text-blue-600 hover:underline">${s.name}</a></li>
    `).join('');
    const d = await API('/qbot/docs');
    document.getElementById('qbot-doc-list').innerHTML = d.docs.slice(0, 100).map(x => `
      <li><a href="#" onclick="viewQbotDoc('${x.path.replace(/'/g, "\\'")}');return false" class="text-blue-600 hover:underline text-xs">${x.path}</a></li>
    `).join('');
  } catch (e) { console.error(e); }
}
window.viewQbotStrategy = async function(name) {
  const r = await API(`/qbot/strategy/${name}`);
  document.getElementById('qbot-strategy-src').textContent = r.source;
};
window.viewQbotDoc = async function(path) {
  const r = await API(`/qbot/doc?path=${encodeURIComponent(path)}`);
  document.getElementById('qbot-doc-view').innerHTML = marked.parse(r.markdown);
};

// ---------- Notify ----------
async function testNotify() {
  const title = document.getElementById('notify-title').value;
  const text = document.getElementById('notify-text').value;
  const btn = event.target;
  btn.disabled = true; btn.textContent = '发送中...';
  try {
    const r = await API('/notify/test', { method: 'POST', body: JSON.stringify({ title, text }) });
    document.getElementById('notify-result').textContent = r.summary;
  } catch (e) {
    document.getElementById('notify-result').textContent = '失败: ' + e.message;
  } finally {
    btn.disabled = false; btn.textContent = '发送测试';
  }
}
