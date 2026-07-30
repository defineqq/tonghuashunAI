# tonghuashunAI · 技术文档

> 面向想读代码、改代码、扩展功能的开发者。使用手册请看 [README.md](./README.md)。

---

## 目录

1. [整体架构](#一整体架构)
2. [目录结构](#二目录结构)
3. [数据层 `data_layer/`](#三数据层-data_layer)
4. [评分层 `analysis/`](#四评分层-analysis)
5. [LLM 层 `ai_analysis/`](#五llm-层-ai_analysis)
6. [策略层 `my_strategies/`](#六策略层-my_strategies)
7. [模拟撮合 `paper_trade/`](#七模拟撮合-paper_trade)
8. [回测层 `backtest/`](#八回测层-backtest)
9. [通知层 `notify/`](#九通知层-notify)
10. [Web 层 `web/`](#十web-层-web)
11. [Qbot 集成方式](#十一qbot-集成方式)
12. [扩展开发指南](#十二扩展开发指南)
13. [测试与 CI](#十三测试与-ci)
14. [已知问题与设计取舍](#十四已知问题与设计取舍)

---

## 一、整体架构

**分层原则**：每一层只依赖下面的层，不依赖上面的层。上层不知道下层怎么实现的，只知道接口签名。

```
┌─────────────────────────────────────────────────────────────────┐
│  Web 层 (web/)   FastAPI + 单页 HTML                             │
│  ├── HTTP API                                                    │
│  └── 静态资源                                                    │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────────┐
│  编排层 (examples/, scripts/)   命令行入口、daily.sh              │
└──────────────────────┬──────────────────────────────────────────┘
                       │
      ┌────────────────┼────────────────┬───────────────┐
      ▼                ▼                ▼               ▼
┌───────────┐   ┌──────────────┐   ┌───────────┐   ┌──────────┐
│ 交易层    │   │ 策略层       │   │ 回测层    │   │ 通知层   │
│paper_trade│   │my_strategies│   │ backtest  │   │  notify  │
└─────┬─────┘   └──────┬───────┘   └─────┬─────┘   └──────────┘
      │                │                 │
      │         ┌──────┴──────┐          │
      │         ▼             ▼          │
      │   ┌─────────┐   ┌──────────┐    │
      │   │ 评分层  │   │ LLM 层   │    │
      │   │analysis │◄──┤ai_analysis│   │
      │   └────┬────┘   └──────────┘    │
      │        │                         │
      └────────┴─────────────┬───────────┘
                             ▼
                     ┌──────────────┐
                     │ 数据层        │
                     │ data_layer/  │
                     └──────┬───────┘
                            │
                     ┌──────┴───────┐
                     │  AkShare     │
                     │  + Qbot 源码  │
                     └──────────────┘
```

### 关键设计原则

1. **惰性 import**：`data_layer/*.py`、`analysis/*.py` 顶部只 import 便宜的库（pandas/numpy），akshare 等重依赖放到函数内 `import`。这样 pytest 不装 akshare 也能测本地逻辑。
2. **stub 兜底**：LLM key 缺失 → 返回中性 50；通知渠道未配置 → 静默跳过。任何单个依赖失效都不能让整个流程 crash。
3. **JSON 持久化胜过数据库**：假想账户/日度快照都用 JSON 文件，方便肉眼审计和 diff。
4. **配置 > 代码**：策略参数（权重、止损、仓位）放 `configs/*.yaml`，改配置不用改代码。

---

## 二、目录结构

```
tonghuashunAI/
├── data_layer/           # 数据层（AkShare 封装 + 缓存）
│   ├── cache.py          #   parquet 缓存装饰器 @cached
│   ├── market.py         #   日线/分钟线/快照
│   ├── fundamental.py    #   估值/财报/行业
│   ├── moneyflow.py      #   北向/主力/板块
│   ├── sentiment.py      #   公告/新闻/龙虎榜
│   ├── universe.py       #   成分股 + stock_pool.yaml 加载
│   └── tests/
│
├── analysis/             # 规则评分层
│   ├── technical.py      #   技术面（5 子项）
│   ├── fundamental_score.py  # 基本面（3 子项）
│   ├── moneyflow_score.py    # 资金面（3 子项）
│   ├── scorer.py         #   综合打分 + rank_universe
│   └── tests/
│
├── ai_analysis/          # LLM 层
│   ├── llm_client.py     #   Claude/OpenAI/DeepSeek 统一封装
│   ├── stock_scorer.py   #   个股情绪评分
│   ├── news_scorer.py    #   大盘情绪评分
│   ├── daily_report.py   #   Markdown 报告
│   ├── prompts/          #   *.md 模板
│   └── tests/
│
├── my_strategies/        # 策略
│   └── swing_v1.py       #   日级波段
│
├── paper_trade/          # 模拟交易
│   ├── portfolio.py      #   账户/持仓/成交/快照 + JSON 序列化
│   ├── broker.py         #   撮合 + 费用模型
│   ├── risk.py           #   止损/止盈/到期
│   └── tests/
│
├── backtest/             # 回测
│   ├── engine.py         #   逐日引擎
│   ├── metrics.py        #   夏普/回撤/年化等
│   ├── report.py         #   Markdown + CSV + PNG
│   └── tests/
│
├── notify/               # 通知
│   ├── feishu.py         #   飞书
│   ├── dingtalk.py       #   钉钉（含加签）
│   ├── wechat.py         #   企业微信
│   ├── email_.py         #   SMTP
│   ├── dispatch.py       #   统一分发器
│   └── tests/
│
├── web/                  # Web 服务
│   ├── server.py         #   FastAPI 入口
│   ├── api/routes.py     #   25 个 REST endpoint
│   └── static/           #   index.html + app.js
│
├── configs/              # YAML 配置
├── examples/             # 各功能演示脚本
├── scripts/              # 一键脚本（daily.sh）
├── vendor/Qbot/          # Qbot 源码副本（77MB 精简版）
├── data/                 # 缓存目录（.gitignore）
├── logs/                 # 日志/报告/账户 JSON（.gitignore）
├── requirements.txt
├── pytest.ini
└── .env.example
```

---

## 三、数据层 `data_layer/`

### 缓存装饰器 `cache.py`

核心是 `@cached(namespace, max_age_hours)` 装饰器：

```python
from data_layer.cache import cached

@cached("market", max_age_hours=None)  # None = 永久缓存
def daily(symbol, start, end, adjust="qfq"):
    import akshare as ak
    return ak.stock_zh_a_hist(...)
```

**工作原理**：
1. 对所有参数（含 positional）做 JSON 序列化，取前 16 位 md5 作指纹
2. 缓存路径：`${DATA_DIR}/{namespace}/{fn_name}__{md5}.parquet`（默认 DATA_DIR=`./data`）
3. `max_age_hours=None` → 永久；数值 → 超过就回源
4. 装饰器只作用于**返回 DataFrame 的函数**（写 parquet）

**缓存时效策略**：

| 数据类型 | 时效 | 理由 |
|---|---|---|
| 历史日线、财报 | `None`（永久） | 历史不会变 |
| 估值、财务摘要 | 12h | 日更即可 |
| 龙虎榜 | 6h | 盘后出，当天多次不必要 |
| 主力资金流 | 2h | 盘中会变 |
| 财联社电报 | 1h | 高频变化 |
| 实时快照 | 0.1h（6 分钟）| 尽量新，防止 API 限流 |

### 拉数据的统一签名

所有面向股票的函数第一个参数都是 `symbol`（6 位字符串），返回 DataFrame。列名统一为英文：

```python
# 日线 → columns: date, open, high, low, close, volume, amount, pct_change, turnover_rate
df = market.daily("600519", start="2024-01-01", end="2024-12-31")
```

AkShare 原始列名（中文）在 `_A_HIST_RENAME` 里映射。

### 股票池加载

`universe.load_pool("configs/stock_pool.yaml")` 读 YAML → 如果 `use: index` 就调对应指数的成分股函数；如果 `use: custom` 就直接用清单。返回 `list[str]`，全部 6 位补零。

---

## 四、评分层 `analysis/`

### 打分公式（简化伪码）

**技术面** — `technical.py`
```python
sub_scores = {
    "trend":      f(price > MA5 > MA20 > MA60),   # 三条件全满足 → 100
    "momentum":   np.clip(50 + ret_20 * 200, 0, 100),
    "rsi":        f(RSI(14) ∈ [40, 70]),
    "volume":     np.clip(50 + (vol5/vol20 - 1)*100, 0, 100),
    "volatility": f(ATR14/close ∈ [0.01, 0.05]),
}
total = mean(sub_scores.values())
```

**基本面** — `fundamental_score.py`
```python
val_score = 100 - (pe_percentile_3y + pb_percentile_3y) / 2
prof_score = np.clip(50 + (roe - 8) * 3, 0, 100)
growth_score = np.clip(50 + revenue_growth * 2, 0, 100)
total = mean([val_score, prof_score, growth_score])
```

**资金面** — `moneyflow_score.py`
```python
nb_score = np.clip(50 + northbound_5d_delta * 100, 0, 100)
main_score = main_inflow_days_of_5 / 5 * 100
turnover_score = f(mean_5d_turnover ∈ [1%, 8%])
total = mean([nb_score, main_score, turnover_score])
```

### 综合打分

`analysis/scorer.py::score_one()`：

```python
total = tech * w[tech] + fund * w[fund] + sent * w[sent] + money * w[money]
```

权重从 `configs/strategy.yaml` 读，可运行时改。

`rank_universe(symbols, use_llm=True|False)`：对一组股票并行打分排序。回测里传 `use_llm=False` 避免 LLM 调用开销。

---

## 五、LLM 层 `ai_analysis/`

### 统一 LLM 接口 `llm_client.py`

```python
from ai_analysis.llm_client import chat
resp = chat("分析这段公告", provider="auto", json_mode=True)
```

`_resolve_provider("auto")` 优先级：
1. `LLM_PROVIDER` 环境变量（显式指定）
2. `ANTHROPIC_API_KEY` 存在 → claude
3. `DEEPSEEK_API_KEY` 存在 → deepseek
4. `OPENAI_API_KEY` 存在 → openai
5. 都没有 → **stub**（返回可预测的中性 JSON）

**为什么不用 LangChain**：这个场景只需要一次性 prompt → 结构化输出，LangChain 引入太多抽象层。40 行 Python + `requests` 就够了。

### Prompt 模板

`ai_analysis/prompts/*.md`，用 Python `.format()` 注入变量：

```markdown
# stock_sentiment.md
你是一个 A 股资深金融分析师...
- 股票代码：{symbol}
- 近期公告：{announcements}

严格返回 JSON: {"score": 0-100, "sentiment": "...", "highlights": [...]}
```

所有情绪评分都强制 `json_mode=True`（provider 层如果支持就用 `response_format={"type": "json_object"}`，否则在 prompt 里明说"只返回 JSON 不要 markdown"，代码里剥离 ` ```json ` 代码块）。

### 每日报告 `daily_report.py`

组装：大盘情绪（news_scorer）+ Top N 个股排名（analysis.scorer）→ Markdown。

---

## 六、策略层 `my_strategies/`

### 策略函数签名

所有策略暴露一个 `generate_signals()` 函数：

```python
def generate_signals(
    portfolio,               # paper_trade.Portfolio
    universe: list[str],     # 候选股票池
    as_of: str = None,       # YYYY-MM-DD
    **kwargs,
) -> tuple[list[BuySignal], list[SellSignal]]:
    ...
```

策略层不直接下单，只**吐信号**；下单由 `paper_trade.broker.execute_day()` 处理。这样策略可以在**回测**和**模拟盘**共用。

### swing_v1 逻辑

```
1. 排除已持仓的股票
2. 调 analysis.scorer.rank_universe() 打分
3. 过滤 total >= min_score（默认 65）
4. 取前 slots = max_positions - len(portfolio.positions) 只
5. 生成 BuySignal，target_pct = position_size
6. 不主动卖出，全交给风控（止损/止盈/到期）
```

---

## 七、模拟撮合 `paper_trade/`

### 数据类（`portfolio.py`）

```python
@dataclass
class Position:
    shares: int
    avg_cost: float
    open_date: str
    last_price: float

    @property
    def unrealized_pnl_pct(self) -> float: ...

@dataclass
class Portfolio:
    account_id: str
    cash: float
    positions: dict[str, Position]
    trades: list[Trade]
    daily_snapshots: list[Snapshot]

    def to_dict() / from_dict() / save(path) / load(path)  # JSON 持久化
```

### 费用模型（`broker.py::FeeConfig`）

```python
commission_rate = 0.0003      # 万分之三（双向）
commission_min = 5.0          # 每笔最低 5 元
stamp_tax = 0.001             # 印花税 0.1%（仅卖方）
transfer_fee = 0.00002        # 过户费（仅沪市）
slippage = 0.001              # 千分之一滑点
```

**滑点处理**：`_fill_price(close, side) = close * (1 ± slippage)`。买单成交价高于收盘价，卖单成交价低于收盘价。

### 每日撮合流程（`execute_day`）

```
1. mark_to_market(close_prices)           # 更新持仓最新价
2. risk_signals = risk.check(portfolio)   # 扫描止损/止盈/到期
3. 合并 risk_signals + 策略 sell_signals（风控优先）
4. 对每个 sell 信号：调 sell() 变现，更新账户
5. slots = max_positions - len(positions)
6. 处理 buy_signals[:slots]：调 buy() 建仓，扣现金
7. portfolio.take_snapshot(date)          # 保存当日快照
```

### 关键的整手处理

A 股买入必须 100 股整数倍：

```python
max_shares_raw = int(target_amount * 0.995 / price)  # 预留 0.5% 手续费
shares = (max_shares_raw // 100) * 100
if shares < 100: return None                          # 一手都买不起
```

---

## 八、回测层 `backtest/`

### 引擎（`engine.py`）

```python
def run(strategy_fn, universe, start, end, initial_cash, ...):
    trading_days = get_trading_days(start, end, ref_symbol="600519")
    port = Portfolio.new("backtest", initial_cash)
    for date in trading_days:
        buys, sells = strategy_fn(port, universe, as_of=date, **kwargs)
        prices = _load_close_prices(relevant_symbols, date)
        execute_day(port, date, prices, buys, sells, ...)
    return {"portfolio": port, "snapshots": df, "metrics": summarize(df)}
```

**注意**：
- 交易日历用一只主流股票（贵州茅台）的日线索引，非交易日自然跳过
- 回测里 `use_llm=False`，避免每股每天调 LLM 的巨额开销

### 指标（`metrics.py`）

| 指标 | 公式 |
|---|---|
| 累计收益 | `(1+r).prod() - 1` |
| 年化收益 | `(1+r).prod()^(252/n) - 1` |
| 最大回撤 | `-min((equity - equity.cummax()) / equity.cummax())` |
| 年化波动率 | `r.std() * sqrt(252)` |
| 夏普 | `(annualized_return - risk_free) / volatility` |

### 报告（`report.py`）

生成三份文件：
- `report.md` — Markdown 汇总
- `snapshots.csv` — 每日净值
- `trades.csv` — 全部成交
- `equity_curve.png` — 净值曲线（matplotlib 可选，缺则跳过）

保存到 `logs/backtests/{strategy}_{ts}/`。

---

## 九、通知层 `notify/`

### 统一入口 `dispatch.notify()`

```python
def notify(title: str, text: str) -> dict[str, bool | None]:
    return {
        "feishu": feishu.send(...) if feishu.is_configured() else None,
        "dingtalk": ...,
        "wechat": ...,
        "email": ...,
    }
```

`None` 表示未配置（未尝试发送），`True/False` 表示发送成功/失败。

### 各渠道实现

- **飞书/企微/钉钉** — HTTP POST webhook（`urllib.request`，无第三方依赖）
- **钉钉加签** — 用 HMAC-SHA256 签 timestamp+secret，拼到 URL 里
- **SMTP** — 用标准库 `smtplib`

设计原则：**不引入 requests 或第三方 SDK**，用标准库把网络调用成本降到最低。

### 用途

- `scripts/daily.sh` 会调 `dispatch.notify()` 推送每日报告摘要
- 用户在 Web 页面 `🔔 通知` 面板可以发测试消息

---

## 十、Web 层 `web/`

### 后端 `server.py` + `api/routes.py`

**FastAPI 结构**：
```python
app = FastAPI()
app.add_middleware(CORSMiddleware, ...)
app.include_router(routes.router, prefix="/api")
app.mount("/static", StaticFiles(directory=STATIC_DIR))

@app.get("/") → 返回 static/index.html
```

**25 个 endpoint** 分类：
- `/api/status` 系统状态
- `/api/portfolio/*` 账户 CRUD
- `/api/universe/{index}` 成分股
- `/api/market/daily` 拉日线
- `/api/score`、`/api/rank` 评分/排名
- `/api/report/*` 每日报告
- `/api/paper/run` 触发撮合
- `/api/backtest/run` 触发回测
- `/api/qbot/*` Qbot 策略/文档浏览
- `/api/notify/test` 测试通知

**Pydantic** 定义所有请求体（如 `ScoreRequest`, `BacktestRequest`），FastAPI 自动生成 OpenAPI 文档 `/docs`。

### 前端 `static/index.html` + `static/app.js`

**技术栈**：
- Tailwind CSS（CDN） — 无需 npm 构建
- Chart.js（CDN） — 画净值曲线
- marked（CDN） — 把 Markdown 渲染成 HTML

**为什么不用 React/Vue**：
1. 单页控制台，交互简单
2. 目标用户是个人，希望零 npm 门槛
3. 4000 行 JS 的 SPA 反而不好维护

**Tab 切换**：纯原生 `document.querySelectorAll` + `classList.toggle('hidden')`。

**API 调用封装**：
```javascript
const API = (path, opts = {}) =>
  fetch(`/api${path}`, { headers: {...}, ...opts })
    .then(r => r.json());
```

---

## 十一、Qbot 集成方式

**背景**：Qbot 是个 wxPython 桌面应用，有 GUI 但装 wxPython 麻烦；作者活跃度不稳定，可能停更。

**我们的做法**：
1. **不用 Qbot 的 GUI**（wxPython 麻烦）
2. **用 Qbot 的策略库和文档** — 保留在 `vendor/Qbot/qbot/strategies/`，一键在 Web 面板浏览源码
3. **用 Qbot 的一些工具类** — 如 `qbot/strategies/bigger_than_ema_bt.py`（backtrader 均线策略）在 `examples/hello_qbot.py` 里直接 import 复用

**Web 里的 Qbot 融合**：
- `/api/qbot/strategies` 列出所有 Python 策略文件
- `/api/qbot/strategy/{name}` 返回源码
- `/api/qbot/docs` + `/api/qbot/doc?path=` 列出/读文档 markdown

**未来 M7 计划**：`vendor/Qbot/qbot/engine/trade/` 里有掘金和 vnpy 模拟盘通道，可以在这个基础上接真实模拟盘。

**同步上游**：
```bash
rm -rf vendor/Qbot
git clone --depth 1 https://github.com/UFund-Me/Qbot.git vendor/Qbot
rm -rf vendor/Qbot/.git vendor/Qbot/dev/*.whl vendor/Qbot/docs/tutorials_code \
       vendor/Qbot/docs/notebook vendor/Qbot/qbot/plugins/investool vendor/Qbot/web
```

---

## 十二、扩展开发指南

### 加一个新的数据源

在 `data_layer/` 加个新文件，例如 `data_layer/options.py`（期权数据）：

```python
from data_layer.cache import cached

@cached("options", max_age_hours=6)
def option_chain(underlying: str) -> pd.DataFrame:
    import akshare as ak
    return ak.option_finance_board(...)
```

在 `data_layer/__init__.py` 的 `__all__` 里加上 `"options"`。

### 加一个新的评分维度

在 `analysis/` 加个新文件 `analysis/macro_score.py`：

```python
def score(symbol, as_of=None, with_detail=False) -> float | dict:
    # 拉宏观数据，输出 0-100
    ...
```

然后改 `analysis/scorer.py::score_one()`：加一列 `macro_total`，改综合分公式，加权重字段到 `configs/strategy.yaml`。

### 加一个新的策略

在 `my_strategies/` 加 `my_strategies/momentum_v1.py`：

```python
def generate_signals(portfolio, universe, as_of=None, **kwargs):
    # 你自己的逻辑，返回 (buys, sells)
    return [BuySignal(...), ...], []
```

`examples/paper_trade_demo.py` 里 `from my_strategies import momentum_v1 as swing_v1` 即可切换。

### 加一个新的通知渠道

在 `notify/` 加 `notify/telegram.py`：

```python
def is_configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN"))

def send(title: str, text: str) -> bool:
    if not is_configured(): return False
    # 调 Telegram Bot API
```

改 `notify/dispatch.py` 加进去；改 `.env.example` 加环境变量说明。

### 加一个新的 Web API

改 `web/api/routes.py`：

```python
@router.get("/my/endpoint")
def my_handler(param: str):
    return {"result": ...}
```

FastAPI 会自动更新 `/docs`。前端在 `web/static/app.js` 里加对应的调用。

---

## 十三、测试与 CI

### 单元测试布局

```
data_layer/tests/    test_cache.py                 4 用例
analysis/tests/      test_technical.py             3 用例
ai_analysis/tests/   test_llm_client.py            4 用例
paper_trade/tests/   test_broker.py                9 用例
backtest/tests/      test_metrics.py               6 用例
notify/tests/        test_dispatch.py              2 用例
                                                  ────
                                              总 28 用例
```

### pytest 配置（`pytest.ini`）

```ini
testpaths = data_layer/tests analysis/tests ai_analysis/tests paper_trade/tests backtest/tests notify/tests
norecursedirs = vendor .git .venv data logs
addopts = -v --tb=short
```

**为什么排除 vendor**：Qbot 的 tests 需要 tushare/joinquant token，跑不通。

### 测试设计原则

- **不依赖外部 API**：所有测试都用 mock 数据或环境变量控制
- **stub 覆盖**：LLM 测试全走 stub 分支；通知测试验证"未配置返回 None"
- **数值断言用容差**：涉及浮点的都用 `abs(a - b) < 1e-9`

### 跑测试

```bash
pytest                          # 全部
pytest paper_trade/tests -v     # 只跑撮合的
pytest -k "sharpe"              # 按名字过滤
```

---

## 十四、已知问题与设计取舍

### 已知问题

1. **AkShare 接口偶尔变动**：AkShare 是社区维护的开源库，某些接口的返回列名会变。数据层做了列名兼容（`_A_HIST_RENAME` 用 `.get()` 而非直接索引）。
2. **交易日历用茅台代替**：`get_trading_days()` 用 600519 的日线索引作为交易日历。不严谨但够用。
3. **单账户单策略**：一个 JSON 文件对应一个账户，没做多策略互相隔离。想跑两个策略就起两个账户名（`swing_v1.json`, `momentum_v1.json`）。
4. **回测里 LLM 关闭**：跑一年的回测如果每股每天调 LLM，成本上千美元。所以强制 `use_llm=False`。如果你要"含 LLM"的回测，自己开这个开关，并做好 token 预算。

### 主动做的取舍

| 我做的选择 | 替代方案 | 为什么这样选 |
|---|---|---|
| Python 3.9 | 3.10+/3.12 | Qbot 硬约束 |
| AkShare 免费源 | Tushare Pro | 零门槛，用户不用注册 |
| JSON 持久化 | SQLite/Postgres | 单机场景，肉眼可读，方便 git 追踪 |
| 装饰器缓存 | Redis | 单机不需要网络缓存 |
| 单页 HTML | React SPA | 目标用户是个人，避免 npm 构建 |
| 惰性 import | 顶部 import | pytest 不装 akshare 也能跑 |
| stub 兜底 | 抛异常 | LLM/通知失效不该 crash 主流程 |
| 相对分位打分 | 绝对阈值 | 因子失效时不至于全崩 |
| 不用 easytrader | 用它接实盘 | UI 自动化违反券商协议，风险高 |

### 未来可能改的地方

- 引入 Postgres 存历史快照（当账户数量变大时）
- Web 前端换 React（如果要做用户系统）
- 加个消息队列（celery / rq）解耦 LLM 调用与 Web 响应（现在同步等 LLM 慢）
- 加更严谨的交易日历（用 pandas-market-calendars 或 QuantLib）

---

## 附：环境变量完整清单

| 变量 | 必需 | 说明 |
|---|:---:|---|
| `ANTHROPIC_API_KEY` | ❌ | Claude API |
| `OPENAI_API_KEY` | ❌ | OpenAI API |
| `DEEPSEEK_API_KEY` | ❌ | DeepSeek API |
| `LLM_PROVIDER` | ❌ | 手动指定 `claude`/`openai`/`deepseek`/`stub` |
| `TUSHARE_TOKEN` | ❌ | Tushare Pro（可选） |
| `DATA_DIR` | ❌ | 缓存目录，默认 `./data` |
| `FEISHU_WEBHOOK` | ❌ | 飞书群机器人 URL |
| `DINGTALK_WEBHOOK` | ❌ | 钉钉群机器人 URL |
| `DINGTALK_SECRET` | ❌ | 钉钉加签 secret（可选） |
| `WECHAT_WEBHOOK` | ❌ | 企微群机器人 URL |
| `SMTP_HOST` | ❌ | 邮件服务器 |
| `SMTP_PORT` | ❌ | 默认 465（SSL） |
| `SMTP_USER` | ❌ | 发件邮箱 |
| `SMTP_PASS` | ❌ | SMTP 授权码 |
| `SMTP_TO` | ❌ | 收件人逗号分隔 |
| `WEB_HOST` | ❌ | Web 监听地址，默认 127.0.0.1 |
| `WEB_PORT` | ❌ | Web 端口，默认 8000 |

全部字段都可以留空，程序会自动降级到 stub / 静默跳过。

---

## 附：Python 依赖清单

**必装**（`requirements.txt`）：
- `akshare>=1.12.0` — A 股数据
- `backtrader>=1.9` — Qbot 回测（我们用少量）
- `pyyaml>=6.0` — 配置文件
- `pyarrow>=15.0` — parquet 缓存
- `pytest>=7.4` — 测试
- `fastapi>=0.110` — Web 后端
- `uvicorn[standard]>=0.27` — ASGI server
- `pydantic>=2.5` — 请求校验
- `anthropic>=0.34.0` — Claude SDK（可选，装了才能用）
- `openai>=1.40.0` — OpenAI/DeepSeek SDK（可选）

**Qbot 的依赖**（`vendor/Qbot/requirements.txt`）：pandas / numpy / tushare / joinquant-sdk / talib 等，一部分已经被我们的 requirements 覆盖。

**推荐但可选**：
- `matplotlib` — 画回测净值曲线（缺则跳过图）
- `python-dotenv` — 自动加载 .env（我们目前用 shell 手动 source）

---

## License

MIT. 详见 [LICENSE](./LICENSE)（如无则以本文件为准）。Qbot 源码副本按 Qbot 自己的 MIT 使用（见 [NOTICE.md](./NOTICE.md)）。
