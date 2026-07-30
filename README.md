# tonghuashunAI

> 面向 A 股的 AI 量化分析与自动化交易平台。
> **模拟盘 / 尚未接实盘。** 底座：[Qbot](https://github.com/UFund-Me/Qbot)（1.8w⭐ MIT）源码副本 + 自研数据/分析/策略/回测/交易/通知/Web 层。

## 项目进展

| # | 里程碑 | 状态 |
|---|---|:---:|
| M0 | 初始化仓库 + Qbot 底座 | ✅ |
| M1 | 数据层（AkShare + parquet 缓存） | ✅ |
| M1.5 | 技术/基本/资金 三维评分器 | ✅ |
| M2 | LLM 情绪分析层（Claude/DeepSeek/OpenAI） | ✅ |
| M3 | 本地模拟撮合 + 假想账户 | ✅ |
| M3.5 | swing_v1 波段策略 | ✅ |
| M4 | 历史回测引擎 + 报告输出 | ✅ |
| M5 | 通知推送（飞书/钉钉/企微/邮件） + 一键调度 | ✅ |
| M6 | Web 控制台（FastAPI + 单页 HTML） | ✅ |

**pytest 全绿：28/28。**

---

## 一、能力矩阵

### 数据（`data_layer/`）
- 日线 / 分钟线 / 实时快照（AkShare）
- 估值分位（PE/PB/PS）、财报摘要、行业归属
- 北向资金（大盘+个股）、主力净流入、板块资金流
- 公司公告、财联社电报、龙虎榜、概念板块
- 沪深300 / 中证500 / 中证1000 成分股 + 自定义股票池
- **本地 parquet 缓存**，历史数据永久缓存，近期数据短时缓存

### 分析（`analysis/` + `ai_analysis/`）
- 技术面评分：均线多头 / 动量 / RSI / 量能 / 波动率（5 子项）
- 基本面评分：估值分位 / ROE / 增长（3 子项）
- 资金面评分：北向变化 / 主力净流入天数 / 换手率（3 子项）
- 情绪面 LLM 评分：读近期公告输出 0–100 分 + 利好利空 + 风险点
- 大盘情绪 LLM 评分：读财联社电报输出大盘评分 + 热点板块
- 综合打分：按 YAML 权重合并，输出排名
- 每日 Markdown 报告

### 策略（`my_strategies/`）
- `swing_v1`：日级波段策略（综合评分选股 + 止损止盈 + 到期强平）

### 交易（`paper_trade/`）
- 假想账户：现金 / 持仓 / 成交历史 / 每日快照，JSON 持久化
- 模拟撮合器：日度粒度，覆盖手续费 / 印花税 / 过户费 / 滑点
- 风控：止损 / 止盈减半或全平 / 最长持有天数

### 回测（`backtest/`）
- 引擎：逐日调用策略 + 撮合，生成净值曲线
- 绩效指标：累计收益 / 年化 / 最大回撤 / 夏普 / 波动率
- 报告：Markdown + CSV + 净值曲线 PNG（若装了 matplotlib）

### 通知（`notify/`）
- 飞书 / 钉钉 / 企业微信 群机器人 webhook
- SMTP 邮件
- 统一分发器 `notify.dispatch.notify(title, text)`

### Web 控制台（`web/`） 🆕
- FastAPI 后端 + 单页 HTML 前端（Tailwind + Chart.js CDN）
- **在浏览器执行所有能力**：评分、排名、每日报告、假想撮合、历史回测
- **融合 Qbot**：浏览 Qbot 20+ 内置策略源码 + 完整文档

### 底座（`vendor/Qbot/`）
- 精简后 77 MB，20+ 现成策略（均线/MACD/KDJ/LightGBM/LSTM 等）
- 完整策略文档

---

## 二、项目结构

```
tonghuashunAI/
├── data_layer/           # 数据层（akshare 封装 + 缓存）
├── analysis/             # 三维规则评分（技术/基本/资金）
├── ai_analysis/          # LLM 情绪评分 + 每日报告
├── my_strategies/        # 自定义策略：swing_v1
├── paper_trade/          # 假想账户 + 模拟撮合 + 风控
├── backtest/             # 回测引擎 + 绩效指标 + 报告
├── notify/               # 飞书/钉钉/企微/邮件推送
├── web/                  # FastAPI + 前端
│   ├── server.py         # 服务入口
│   ├── api/routes.py     # REST API
│   └── static/           # index.html + app.js
├── configs/              # stock_pool.yaml, strategy.yaml
├── examples/             # 各功能示例脚本
├── scripts/              # daily.sh 一键脚本
├── vendor/Qbot/          # Qbot 源码副本（77MB）
├── data/                 # 缓存（.gitignore）
├── logs/                 # 日志（.gitignore）
├── requirements.txt
├── .env.example
├── pytest.ini
├── NOTICE.md             # Qbot MIT 协议说明
├── CHANGELOG.md
└── README.md
```

---

## 三、启动步骤

### 3.1 安装

```bash
git clone https://github.com/defineqq/tonghuashunAI.git
cd tonghuashunAI

# Qbot 要求 Python 3.9（3.10+ 部分依赖有兼容问题）
python3.9 -m venv .venv
source .venv/bin/activate

pip install -r vendor/Qbot/requirements.txt
pip install -r requirements.txt

cp .env.example .env
# 打开 .env 填 LLM API key（可选，不填自动 stub）和通知 webhook（可选）
```

**常见问题**：`TA-Lib` / `wxPython` 装不上时可跳过（我们不用）；PyPI 慢用 `-i https://pypi.tuna.tsinghua.edu.cn/simple`。

### 3.2 命令行示例

```bash
# 1) 最小验证：拉数据 + 跑一个 Qbot 内置策略回测
python examples/hello_qbot.py

# 2) 从沪深300 选综合分 Top N
python examples/rank_hs300.py --limit 30 --top 10

# 3) 生成今日选股 Markdown 报告
python examples/daily_report_demo.py --symbols 600519 000858 300750

# 4) 跑一次假想撮合
python examples/paper_trade_demo.py --limit 30

# 5) 跑一段历史回测
python examples/backtest_swing_v1.py --start 2024-06-01 --end 2024-12-31 --limit 30

# 6) 启动 Web 控制台
python examples/run_web.py
# 浏览器打开 http://127.0.0.1:8000
```

### 3.3 每日一键（含通知 + 推送到 GitHub）

```bash
./scripts/daily.sh
# 建议 crontab：30 15 * * 1-5 cd /path/to/tonghuashunAI && ./scripts/daily.sh
```

### 3.4 测试

```bash
pytest   # 28/28 全绿（本地逻辑测试，不需要外部 API）
```

### 3.5 Web 控制台 🆕

启动后打开 http://127.0.0.1:8000，可以在页面里：
- **📊 概览**：系统状态（LLM 是否配置、通知渠道是否启用）
- **🎯 评分**：单只股票四维打分 / 批量排名
- **📰 每日报告**：一键生成 Markdown 报告 / 浏览历史报告
- **💼 假想账户**：查看/新建账户、跑撮合、查持仓和成交
- **📈 回测**：填时间和股票池，一键跑，展示净值曲线和绩效指标
- **🧰 Qbot 集成**：浏览 Qbot 20+ 内置策略源码 + 文档
- **🔔 通知**：测试推送渠道

API 交互式文档：http://127.0.0.1:8000/docs （FastAPI 自动生成）。

---

## 四、评分系统设计

**核心思路**：4 个独立维度 → 每个 0–100 分 → 按权重加权成一个综合分。所有排名基于**相对分位**，避免单因子失效导致整体崩塌。

### 四个维度（12 个子项）

| 维度 | 默认权重 | 子项 |
|---|---:|---|
| 技术面 | 35% | 趋势多头 / 20日动量 / RSI 健康区 / 量能放量 / 波动率适中 |
| 基本面 | 20% | 估值 3 年分位（越低越好） / ROE / 营收增长 |
| 资金面 | 25% | 北向 5 日增持 / 主力净流入天数 / 换手率适中 |
| 情绪面 | 20% | LLM 读公告输出情绪评分 + 利好利空 + 风险点 |

权重在 `configs/strategy.yaml` 里，改配置不用改代码。

### 综合分 = 加权平均

```python
total = tech * 0.35 + fund * 0.20 + sentiment * 0.20 + moneyflow * 0.25
```

### LLM 情绪评分打分标准

- **80–100**：明显利好（重大合同、业绩超预期、政策利好、机构增持）
- **60–79**：偏正面
- **40–59**：中性
- **20–39**：偏负面
- **0–19**：明显利空（重大诉讼、财务造假、退市风险、立案调查）

无 LLM API key 时自动返回中性 50，不阻塞流程。

---

## 五、配置

### `configs/stock_pool.yaml`
```yaml
use: index                # index=用成分股 / custom=自定义
index: "000300"           # 000300=沪深300 / 000905=中证500 / 000852=中证1000
custom:
  - "600519"
filters:
  exclude_st: true
  exclude_new_days: 60
  min_market_cap_yi: 50
```

### `configs/strategy.yaml`
```yaml
swing_v1:
  weights: {technical: 0.35, fundamental: 0.20, sentiment: 0.20, moneyflow: 0.25}
  max_positions: 5
  position_size: 0.18
  stop_loss_pct: 0.05
  take_profit_pct: 0.15
  max_hold_days: 10
```

### `.env`
```
ANTHROPIC_API_KEY=       # 或 DEEPSEEK / OPENAI，任填一个启用 LLM
FEISHU_WEBHOOK=          # 通知渠道，任填一个即可
DINGTALK_WEBHOOK=
WECHAT_WEBHOOK=
SMTP_HOST=               # 4 项都填才启用邮件
SMTP_USER=
SMTP_PASS=
SMTP_TO=
```

---

## 六、路线图

- [x] M0–M6：数据、分析、策略、交易、回测、通知、Web 全链路完成
- [ ] M7：接入 Qbot 官方模拟盘通道（掘金 / vnpy）
- [ ] M8：日内高频（分钟级）支持
- [ ] M9：多策略组合 + 强化学习实验

---

## 七、免责声明

- 本项目仅用于**个人学习与研究**，不构成投资建议。
- 当前阶段**只涉及模拟盘**，未接入任何真实券商实盘。
- 股票市场有风险，任何策略回测的历史表现不代表未来收益。
- 使用本项目造成的任何直接或间接损失，由使用者自行承担。
- Qbot 源码副本按 MIT 协议使用，版权归原作者所有（见 [NOTICE.md](./NOTICE.md)）。
