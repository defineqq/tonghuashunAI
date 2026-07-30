# tonghuashunAI

> 面向 A 股的 AI 量化分析与自动化交易项目。
> **当前阶段：模拟盘 / 尚未接实盘。**
> 底座：开源项目 [Qbot](https://github.com/UFund-Me/Qbot)（1.8w⭐, MIT）源码副本 + 自研数据/分析/策略层。

## 💤 起床看这里（2026-07-30 夜里的进展）

- ✅ **M0 → M2 全部完成**：数据层、评分层、LLM 情绪分析层、每日报告生成器都能用
- ✅ **pytest 11/11 全绿**
- ✅ **6 次 commit 已 push** 到你的私有仓库 `defineqq/tonghuashunAI`
- ⏭️ **下一步**：M3 本地模拟撮合（每日跑策略 + 假想账户跟 PnL）
- 📖 **详细决策**：见 [CHANGELOG.md](./CHANGELOG.md)
- 🔑 **想启用 LLM 情绪评分**：把 `.env.example` 拷成 `.env`，填一个 API key（推荐 DeepSeek）

---


## 一、这个项目能做什么

### 已实现（M0 – M2）

| 能力 | 模块 | 说明 |
|---|---|---|
| **拉行情数据** | `data_layer/market.py` | A 股日线、分钟线、全市场实时快照，AkShare 免费源 |
| **拉基本面** | `data_layer/fundamental.py` | PE / PB / PS 估值、财务摘要（ROE、营收增长）、行业归属 |
| **拉资金流** | `data_layer/moneyflow.py` | 北向资金（大盘+个股）、主力净流入、板块资金流 |
| **拉情绪面数据** | `data_layer/sentiment.py` | 公司公告、财联社电报、龙虎榜、概念板块 |
| **本地缓存** | `data_layer/cache.py` | md5 参数指纹 + parquet 持久化，历史数据永久缓存，近期数据短时缓存 |
| **股票池管理** | `data_layer/universe.py` | 沪深 300 / 中证 500 / 中证 1000 成分股 + 自定义清单 |
| **技术面评分** | `analysis/technical.py` | 均线多头 / 动量 / RSI / 量能 / 波动率 五子项，0-100 |
| **基本面评分** | `analysis/fundamental_score.py` | 估值分位 / ROE / 增长三子项，0-100 |
| **资金面评分** | `analysis/moneyflow_score.py` | 北向变化 / 主力净流入天数 / 换手率三子项，0-100 |
| **情绪面 LLM 评分** | `ai_analysis/stock_scorer.py` | 用 Claude/DeepSeek/OpenAI 分析公告，输出 0-100 分（无 key 自动 stub） |
| **大盘情绪 LLM 评分** | `ai_analysis/news_scorer.py` | 分析财联社电报，输出大盘情绪 + 热点板块 |
| **每日报告生成** | `ai_analysis/daily_report.py` | 组合大盘情绪 + Top N 个股，输出 Markdown |
| **综合打分选股** | `analysis/scorer.py` | 按权重合并四维度，输出排名 DataFrame |
| **LLM 抽象层** | `ai_analysis/llm_client.py` | 统一接口封装 Claude/OpenAI/DeepSeek，无 key 自动降级到 stub |
| **回测引擎** | `vendor/Qbot/` | 基于 backtrader，20+ 现成策略（均线/MACD/KDJ/LightGBM/LSTM 等） |
| **模拟盘通道** | `vendor/Qbot/qbot/engine/trade/` | Qbot 提供的模拟撮合与掘金/vnpy 通道（M3/M4 阶段接入） |

### 未实现，计划中

| 阶段 | 能力 | 依赖 |
|---|---|---|
| **M3** | 本地模拟撮合（每日盘前跑策略、假想账户跟踪 PnL） | 现有代码基础上加 |
| **M4** | 接入 Qbot 模拟盘（真实模拟环境跑 3 个月） | Qbot GUI 或掘金模拟账号 |
| **M5** | 每日选股推送（邮件/微信/飞书） | Qbot 已提供通知模块 |

---

## 二、项目结构

```
tonghuashunAI/
│
├── data_layer/               # 【自研】数据层：屏蔽 AkShare 差异 + 本地缓存
│   ├── cache.py              #   缓存装饰器：md5 指纹 + parquet
│   ├── market.py             #   行情数据
│   ├── fundamental.py        #   基本面数据
│   ├── moneyflow.py          #   资金流数据
│   ├── sentiment.py          #   情绪面数据（新闻/公告/龙虎榜）
│   ├── universe.py           #   股票池：成分股 + 加载 stock_pool.yaml
│   └── tests/                #   单元测试
│
├── analysis/                 # 【自研】评分层：0-100 打分
│   ├── technical.py          #   技术面（均线/动量/RSI/量能/波动率）
│   ├── fundamental_score.py  #   基本面（估值分位/ROE/增长）
│   ├── moneyflow_score.py    #   资金面（北向/主力/换手）
│   ├── scorer.py             #   综合打分 + 排序
│   └── tests/                #   单元测试
│
├── my_strategies/            # 【自研】策略层（M2/M3 填充）
│   └── (待写)                #   短线波段策略 / 四维评分策略
│
├── ai_analysis/              # 【自研】LLM 层
│   ├── llm_client.py         #   统一 LLM 接口（Claude/OpenAI/DeepSeek，无 key 自动 stub）
│   ├── stock_scorer.py       #   个股 LLM 情绪评分
│   ├── news_scorer.py        #   大盘 LLM 情绪评分
│   ├── daily_report.py       #   每日选股 Markdown 报告
│   ├── prompts/              #   Prompt 模板（stock_sentiment.md, market_sentiment.md）
│   └── tests/                #   单元测试
│
├── configs/                  # 【自研】配置
│   ├── stock_pool.yaml       #   股票池：指数或自定义
│   └── strategy.yaml         #   策略参数：权重、止损止盈、仓位等
│
├── examples/                 # 【自研】示例脚本
│   ├── hello_qbot.py         #   最小示例：拉数据 + 跑 Qbot 均线策略回测
│   ├── rank_hs300.py         #   综合评分选股：从沪深300 选 Top N
│   └── daily_report_demo.py  #   生成每日选股 Markdown 报告
│
├── scripts/                  # 【自研】一键脚本（M3 填充）
│   └── (待写)                #   run_daily.sh / run_backtest.sh
│
├── vendor/Qbot/              # 【第三方】Qbot 源码副本（77MB，精简过）
│   ├── qbot/                 #   核心引擎、策略、GUI、通知
│   ├── pyfunds/              #   基金相关
│   ├── pytrader/             #   easytrader 集成（不推荐使用）
│   ├── pyfutures/            #   期货
│   ├── docs/                 #   Qbot 文档（策略说明、指标教程）
│   ├── requirements.txt      #   Qbot 的 Python 依赖清单
│   └── LICENSE               #   MIT
│
├── data/                     # 【运行时】本地缓存目录（.gitignore）
├── logs/                     # 【运行时】日志目录（.gitignore）
│
├── requirements.txt          # 本仓库自研代码的增量依赖
├── .env.example              # 环境变量模板（API keys 等）
├── .gitignore
├── README.md                 # 本文件
├── NOTICE.md                 # Qbot 源码来源与协议说明
└── CHANGELOG.md              # 变更历史（每个 milestone 有决策记录）
```

---

## 三、启动步骤

### 3.1 环境准备（首次）

```bash
# 1. 克隆仓库
git clone https://github.com/defineqq/tonghuashunAI.git
cd tonghuashunAI

# 2. 建 Python 虚拟环境
#    ⚠️ 强烈建议用 Python 3.9（Qbot 只测试过 3.8/3.9，3.10+ 部分依赖会失败）
python3.9 -m venv .venv
source .venv/bin/activate

# 3. 安装依赖（先装 Qbot 的重依赖，再装自研的增量依赖）
pip install -r vendor/Qbot/requirements.txt
pip install -r requirements.txt

# 4. 复制环境变量模板
cp .env.example .env
# 打开 .env 填入你的 API key（M2 阶段才需要 LLM key）
```

**Python 版本说明**：如果你机器上没有 3.9，可用 pyenv/miniconda 装一个：
```bash
# 用 miniconda
conda create -n thsai python=3.9 -y
conda activate thsai
```

**常见依赖问题**：
- `TA-Lib` 安装失败 → `sudo apt install ta-lib-dev` 或从源码编译（Qbot 用得不多，可以先跳过）
- `wxPython` 安装失败 → Qbot 的 GUI 才需要，命令行运行不用
- 中国大陆访问 PyPI 慢 → `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple ...`

### 3.2 跑第一个示例（验证环境 OK）

```bash
python examples/hello_qbot.py
```

预期输出：
```
拉取到 600519 486 条日线 (2023-01-01 → 2024-12-31)
期初资金: 100000.00
2023-01-03, Close, 1666.00
2023-01-03, 买入单, 1666.00
2023-01-04, 已买入, 价格: 1663.30, ...
...
期末资金: 108234.00
收益率:   8.23%
```

如果这一步过了，说明 AkShare + backtrader + Qbot 全通。

### 3.3 跑综合评分选股

```bash
# 从沪深 300 里选综合分最高的 10 只
python examples/rank_hs300.py

# 调试模式：只跑池子的前 20 只
python examples/rank_hs300.py --limit 20 --top 5

# 换用中证 500
python examples/rank_hs300.py --pool 000905 --top 15

# 指定截止日期（回测特定日期）
python examples/rank_hs300.py --as-of 2024-06-30
```

首次运行会下 300 只股票的行情+估值+资金流数据，比较慢（约 10–20 分钟，取决于网速）。**所有数据都会缓存到 `./data/` 目录**，之后再跑就是秒级。

### 3.4 生成每日选股分析报告（可选）

```bash
# 用配置里的股票池，跑前 50 只，输出 Top 10
python examples/daily_report_demo.py

# 只跑指定的几只股票（跳过股票池）
python examples/daily_report_demo.py --symbols 600519 000858 300750

# 保存到指定路径
python examples/daily_report_demo.py --save logs/reports/today.md
```

**LLM 说明**：
- 未在 `.env` 里配置任何 `*_API_KEY` → 自动 stub 模式，情绪评分统一 50，其他维度正常
- 配置了 `ANTHROPIC_API_KEY` → 用 Claude
- 配置了 `DEEPSEEK_API_KEY` → 用 DeepSeek（**便宜性价比高**，推荐个人使用）
- 配置了 `OPENAI_API_KEY` → 用 OpenAI
- 多个都配置时优先级：Claude > DeepSeek > OpenAI，可通过 `LLM_PROVIDER=deepseek` 手动指定

### 3.5 跑测试

```bash
# 装 pytest（只测本地逻辑，不需要 akshare）
pip install pytest

# 运行所有测试（用 pytest.ini 里的 testpaths 配置，只跑本仓库自研代码）
pytest
```

预期：
```
data_layer/tests/test_cache.py .... (4)
analysis/tests/test_technical.py ... (3)
ai_analysis/tests/test_llm_client.py .... (4)
11 passed
```

---

## 四、常用命令

| 目的 | 命令 |
|---|---|
| 拉一只股票的日线 | `python -c "from data_layer import market; print(market.daily('600519', '2024-01-01', '2024-12-31'))"` |
| 拉沪深 300 成分股 | `python -c "from data_layer.universe import hs300_constituents; print(hs300_constituents())"` |
| 给一只股票打分 | `python -c "from analysis.scorer import score_one; print(score_one('600519'))"` |
| 清空数据缓存 | `python -c "from data_layer.cache import clear_cache; print(clear_cache())"` |
| 查看 Qbot 现成策略 | `ls vendor/Qbot/qbot/strategies/` |
| 跑 Qbot 的 GUI | `cd vendor/Qbot && python main.py`（需要装 wxPython） |

---

## 五、配置说明

### 5.1 `configs/stock_pool.yaml` — 股票池

```yaml
use: index               # index=用成分股 / custom=用自定义清单
index: "000300"          # 000300=沪深300, 000905=中证500, 000852=中证1000

custom:                  # 自定义清单（use=custom 时生效）
  - "600519"
  - "300750"

filters:
  exclude_st: true       # 剔除 ST
  exclude_new_days: 60   # 剔除上市不足 N 天
  min_market_cap_yi: 50  # 最小总市值（亿元）
```

### 5.2 `configs/strategy.yaml` — 策略参数

```yaml
swing_v1:
  weights:                # 四维度评分权重（合计 = 1.0）
    technical: 0.35
    fundamental: 0.20
    sentiment: 0.20
    moneyflow: 0.25

  max_positions: 5        # 最多同时持有几只
  position_size: 0.18     # 单只最大仓位
  stop_loss_pct: 0.05     # 5% 止损
  take_profit_pct: 0.15   # 15% 止盈减半
```

### 5.3 `.env` — 密钥

```bash
ANTHROPIC_API_KEY=       # Claude（M2 用）
OPENAI_API_KEY=          # OpenAI（M2 备选）
DEEPSEEK_API_KEY=        # DeepSeek（M2 备选，性价比高）
TUSHARE_TOKEN=           # 可选，AkShare 用不到
DATA_DIR=./data          # 缓存路径
```

---

## 六、路线图

- [x] **M0**：初始化仓库、目录骨架、Qbot 源码副本
- [x] **M1**：数据层封装（行情/基本面/资金/情绪 + 缓存）
- [x] **M1.5**：三维度评分器（技术/基本/资金）+ 综合打分
- [x] **M2**：LLM 情绪分析层（个股/大盘情绪评分 + 每日报告，无 key 自动 stub）
- [ ] **M3**：本地模拟撮合（每日盘前跑、假想账户跟踪 PnL）
- [ ] **M4**：接入 Qbot 模拟盘
- [ ] **M5**：每日选股推送（邮件/微信/飞书）

变更历史见 [CHANGELOG.md](./CHANGELOG.md)。

---

## 七、免责声明

- 本项目仅用于**个人学习与研究**，不构成投资建议。
- 当前阶段**只涉及模拟盘**，未接入任何真实券商实盘。
- 股票市场有风险，任何策略回测的历史表现不代表未来收益。
- 使用本项目造成的任何直接或间接损失，由使用者自行承担。
- Qbot 源码副本按 MIT 协议使用，版权归原作者所有（见 [NOTICE.md](./NOTICE.md)）。

---

## 八、支持与反馈

有问题在私有仓库提 issue 即可。
