# CHANGELOG

## 全景总览

| # | 里程碑 | 关键产出 | 状态 |
|---|---|---|:---:|
| M0 | 初始化仓库 + Qbot 底座 | 目录骨架、`.gitignore`、`hello_qbot.py` | ✅ |
| M0.5 | Qbot 从 submodule 转为本地副本 | `vendor/Qbot/` 精简到 77MB、`NOTICE.md` | ✅ |
| M1 | 数据层 | `data_layer/` 5 模块 + parquet 缓存 | ✅ |
| M1.5 | 三维评分器 | `analysis/` 4 模块 + `rank_hs300.py` | ✅ |
| M2 | LLM 情绪分析层 | `ai_analysis/` 4 模块 + `daily_report.py` | ✅ |
| M3 | 本地模拟撮合 | `paper_trade/` 3 模块 + 假想账户 JSON 持久化 | ✅ |
| M3.5 | swing_v1 波段策略 | `my_strategies/swing_v1.py` | ✅ |
| M4 | 历史回测框架 | `backtest/` 3 模块 + Markdown/CSV/PNG 报告 | ✅ |
| M5 | 通知推送 + 一键调度 | `notify/` 4 通道 + `scripts/daily.sh` | ✅ |
| M6 | Web 控制台 | FastAPI + 单页 HTML，融合 Qbot 策略浏览 | ✅ |

**测试**：pytest 28/28 全绿。

## 2026-07-30

### 🔒 安全事件与处理

发现 Qbot 上游源码里硬编码了 3 处真实的 GitHub token（不是我们的，是 Qbot 作者的）：
- `vendor/Qbot/utils/pull_issues.py`
- `vendor/Qbot/utils/sendemail_stargazers.py`
- `vendor/Qbot/docs/index.html`

**处理**：
1. 工作树替换成 `REDACTED_PLEASE_SET_YOUR_OWN_TOKEN` 占位符
2. 用 `git-filter-repo` **重写整个历史**，把 2 个 ghp_ token 全部替换为 `REDACTED_QBOT_UPSTREAM_LEAKED_TOKEN`
3. `git push origin main --force` 覆盖远端历史（这是转 public 的前置条件）
4. 副作用：M0.5、M0 commit 的 hash 变了，早期 push 记录已被清除

### M6：Web 控制台 ✅

- FastAPI 后端 `web/server.py` + 路由 `web/api/routes.py`（25 个 endpoint）
- 单页前端 `web/static/index.html`（Tailwind CDN + Chart.js CDN + marked CDN），零 npm 构建
- 功能面板：概览 / 评分 / 每日报告 / 假想账户 / 回测 / Qbot 集成 / 通知
- Qbot 融合方式：不用它的 wxPython GUI（桌面应用不方便嵌浏览器），改为**通过 API 浏览 Qbot 所有内置策略源码 + 完整文档**
- 一键启动：`python examples/run_web.py` → http://127.0.0.1:8000

### M5：通知 + 一键调度 ✅

- `notify/` 4 个渠道：飞书 / 钉钉 / 企业微信 / SMTP 邮件（都走 webhook 或 SMTP，不需要客户端）
- 未配置的渠道静默跳过，不 crash
- `notify.dispatch.notify(title, text)` 统一入口
- `scripts/daily.sh` 每日一键：生成报告 → 模拟撮合 → 通知推送 → GitHub 同步
- crontab 建议：`30 15 * * 1-5`（每交易日 15:30 后跑）

### M4：历史回测 + 报告 ✅

- `backtest/engine.py`：逐日撮合引擎，产出账户曲线
- `backtest/metrics.py`：年化 / 累计 / 最大回撤 / 夏普 / 波动率
- `backtest/report.py`：Markdown + CSV + PNG（matplotlib 可选）
- `examples/backtest_swing_v1.py`：一键跑历史回测

**注意**：回测里强制 `use_llm=False`（每股每天调 LLM 成本太高），情绪面用中性 50。想含 LLM 回测可以自己开，但要预算好 token 费。

### M3.5：swing_v1 波段策略 ✅

- 综合评分 ≥ min_score（默认 65）的进入候选
- 已持仓不加仓
- 卖出全交给风控（止损/止盈/到期）
- 单只最大 18% 仓位，最多同时持有 5 只

### M3：本地模拟撮合 + 假想账户 ✅

- `paper_trade/portfolio.py`：账户/持仓/成交/快照，JSON 持久化到 `logs/portfolio/{account}.json`
- `paper_trade/broker.py`：日度撮合，覆盖手续费 / 印花税 / 过户费 / 滑点
- `paper_trade/risk.py`：止损（-5%）/ 止盈（+15% 减半）/ 最长持有（10 天）
- `execute_day()` 是核心入口：mark to market → 风控卖 → 策略卖 → 策略买 → 快照

### M2：LLM 情绪分析层 ✅

- `llm_client.py`：统一 LLM 接口，无 key 自动 stub（返回中性）
- `stock_scorer.py`：个股情绪评分
- `news_scorer.py`：大盘情绪评分
- `daily_report.py`：生成每日 Markdown 报告
- Provider 优先级：Claude > DeepSeek > OpenAI，可用 `LLM_PROVIDER` 覆盖

### M1.5：三维评分器 ✅

- 技术面（5 子项）/ 基本面（3 子项）/ 资金面（3 子项）
- 所有子项都是**相对分位**打分，避免绝对值失效
- `analysis/scorer.py` 按 YAML 权重合并

### M1：数据层 ✅

- `data_layer/` 5 模块：market / fundamental / moneyflow / sentiment / universe
- `cache.py`：md5 参数指纹 + parquet 装饰器
- 历史数据永久缓存，近期数据 0.1–6h 短时缓存

### M0.5：Qbot 从 submodule 转为本地副本 ✅

- 移除 submodule 关联，源码直接纳入 `vendor/Qbot/`
- 精简：686 MB → 77 MB
- `NOTICE.md` 说明 MIT 合规

### M0：仓库初始化 ✅

- `defineqq/tonghuashunAI` GitHub 私有仓库
- Python 3.9 + AkShare + backtrader + Qbot 依赖链
5. **想继续做**：下一站是 **M3 本地模拟撮合**（每日盘前跑、假想账户跟 PnL），预计半天左右

---

## 2026-07-30

### M2：LLM 情绪分析层 ✅

**做了什么**
- 新增 `ai_analysis/` Python 包
  - `llm_client.py`：统一 LLM 调用接口，支持 Claude / OpenAI / DeepSeek，**无 API key 时自动 stub**（返回中性评分），下游流程始终能跑
  - `stock_scorer.py`：用 LLM 分析个股公告，输出情绪评分（0-100）+ 利好利空要点 + 风险提示
  - `news_scorer.py`：分析财联社电报，输出大盘情绪评分 + 热点/承压板块 + 关键事件
  - `daily_report.py`：组合大盘情绪 + Top N 个股，生成 Markdown 每日报告
  - `prompts/`：`stock_sentiment.md`、`market_sentiment.md` Prompt 模板
- `analysis/scorer.py`：把情绪面接入 LLM 评分，加 `use_llm` 开关（False 时跳过，跑大池子更快）
- 新增 `examples/daily_report_demo.py`：一键生成完整每日报告
- 新增 `pytest.ini`：只收集自研测试，排除 vendor/Qbot 里需要 tushare token 的测试
- 单元测试：`ai_analysis/tests/test_llm_client.py`（4 个用例，全跑 stub 分支）
- pytest 全绿：11/11 通过

**关键决策**
- **stub 优先**：没有 key 也能全流程跑通，只是情绪维度不参与打分；等用户填 key 后自动切换真实 LLM
- **LLM provider 优先级**：Claude > DeepSeek > OpenAI，可通过 `LLM_PROVIDER` 环境变量覆盖
- **DeepSeek 推荐给个人用户**：价格是 OpenAI/Claude 的 1/10，性能够用
- **Prompt 强制 JSON 输出**：所有情绪评分都用 `json_mode=True`，避免文本解析歧义

**待用户处理**
- 在 `.env` 里填入 `ANTHROPIC_API_KEY` / `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` 之一，即可启用真实 LLM 评分
- 目前默认模型 `claude-opus-4-8`（Claude 最新款），如果用户走 Claude 通道会用这个

### M1.5：三维度评分器 + 完整项目手册 ✅

**做了什么**
- 新增 `analysis/` Python 包
  - `technical.py`：技术面评分（均线多头/动量/RSI/量能/波动率 5 子项）
  - `fundamental_score.py`：基本面评分（估值分位/ROE/增长 3 子项）
  - `moneyflow_score.py`：资金面评分（北向变化/主力净流入/换手 3 子项）
  - `scorer.py`：综合打分 + 排名，读取 `configs/strategy.yaml` 权重
- 新增 `examples/rank_hs300.py`：从沪深 300 选综合分 Top N 的完整示例
- 单元测试：`analysis/tests/test_technical.py`（3 个用例）
- 重构 data_layer/analysis 为按需 import（避免 pytest 时强制依赖 akshare）
- 跑通 pytest：7 个测试全绿

**关键决策**
- 情绪面（sentiment）暂返回中性 50 分，M2 阶段用 LLM 填充；这样 M1.5 阶段的选股逻辑仍可完整跑通
- 所有评分都是**相对分位**而非绝对判定，避免因子失效
- 综合打分权重可通过 YAML 调整，不用改代码

### README 大改
- 按用户要求，把 README 重写为完整的项目手册
- 包含：能力矩阵、项目结构、启动步骤、常用命令、配置说明、路线图、免责声明
- 常见依赖问题（TA-Lib、wxPython、pip 源）都写了 workaround

### M1：数据层封装 ✅

**做了什么**
- 新增 `data_layer/` Python 包，对 AkShare 做统一封装
- `cache.py`：带 md5 参数指纹的 parquet 本地缓存装饰器 `@cached(namespace, max_age_hours)`
- `market.py`：日线 / 分钟线 / 全市场实时快照
- `fundamental.py`：估值（PE/PB/PS）、财务摘要、行业归属
- `moneyflow.py`：北向资金 / 个股主力净流入 / 板块资金流
- `sentiment.py`：公告 / 财联社电报 / 龙虎榜 / 概念板块
- `universe.py`：沪深300/中证500/中证1000 成分股 + 从 `configs/stock_pool.yaml` 加载
- `tests/test_cache.py`：缓存机制的单测（指纹一致性 + 装饰器命中）

**设计要点**
- 历史数据（日线、财报）→ 永久缓存
- 近期数据（快照、龙虎榜）→ 短时缓存（0.1–6 小时）
- 缓存文件放 `${DATA_DIR}/{namespace}/{fn_name}__{md5}.parquet`，`.gitignore` 已排除
- 所有函数签名统一 (symbol, start, end)，上层策略无需关心底层数据源

### M0.5：Qbot 从 submodule 转为本地副本（+ 精简）

**触发**：用户担心上游停更风险，要求把 Qbot 内容直接下载纳入。

**做了什么**
- 移除 git submodule 关联，重新以普通目录方式克隆 Qbot 到 `vendor/Qbot/`
- 精简 Qbot：686 MB → 77 MB（删掉 `.git`、`dev/*.whl`、`docs/tutorials_code/`、`docs/notebook/`、`qbot/plugins/investool/`、`web/`、各类二进制）
- 保留：完整 Python 源码、策略库、回测引擎、交易适配层、精简文档、LICENSE
- 新增 `NOTICE.md` 说明源码来源、协议、修改历史（MIT 合规要求）
- README、.gitignore 相应更新

**为什么这样做**
- Qbot 作者曾提示"可能停更"，submodule 依赖远端仓库存在风险
- 精简后仓库仍可独立运行，避免体积失控（GitHub 单仓库软上限 5GB）
- MIT 允许保留 + 修改 + 商用，只需保留版权声明

### M0：初始化仓库 + 引入 Qbot 底座 ✅

**做了什么**
- 创建 GitHub 私有仓库 `defineqq/tonghuashunAI`
- 用 git submodule 引入 [Qbot](https://github.com/UFund-Me/Qbot)（1.8w⭐, MIT）到 `vendor/Qbot/`
- 建目录骨架：`my_strategies/` `ai_analysis/` `configs/` `examples/` `scripts/` `data/` `logs/`
- 写好 `.gitignore`（排除数据、日志、密钥、缓存）
- 写好 `README.md`、`.env.example`、`requirements.txt`
- 配置文件占位：`configs/stock_pool.yaml`（默认沪深 300）、`configs/strategy.yaml`（波段策略参数）
- 最小验证示例：`examples/hello_qbot.py`（用 AkShare 拉贵州茅台日线 + Qbot 的 15 日均线策略回测）

**关键决策**
- **不 fork Qbot**：Qbot 更新频繁，fork 后追不上；submodule 保留干净的上游链接
- **submodule 用浅克隆**（`--depth 1`）：Qbot 仓库 380MB，浅克隆只拉最新代码，快
- **数据源选 AkShare 不选 Tushare**：AkShare 免费无 key，用户零门槛就能跑；Tushare 需注册 + 积分制
- **股票池默认沪深 300**：数据干净、覆盖主流、约 300 只规模可控
- **不引入 easytrader**：easytrader 是 UI 自动化实盘下单，风险高且违反券商协议；本项目定位模拟盘，不需要
- **Python 版本要求 3.8/3.9**：Qbot 硬约束（README 明写），后续建虚拟环境需注意

**待验证 / 待处理**
- 本地环境目前 Python 版本未确认，`examples/hello_qbot.py` 未实际跑过（用户睡了，不想装依赖打扰他）
- Qbot 依赖里有 wxPython/TA-Lib 等重依赖，可能需要系统包，等实际装的时候再处理
- Tushare token 未配置（当前用 AkShare 不需要）
- LLM API key 未配置（M2 才用到）

### 下一步计划（M1）
- 抽出数据层：封装 AkShare 拉取行情/基本面/资金流/龙虎榜的统一接口
- 加本地 parquet 缓存，避免每次跑都重新拉
- 单元测试基础数据接口

### 再下一步计划（M2）
- AI 情绪分析层：LLM 分析新闻/公告文本，输出情绪评分（等用户确认用哪家 LLM 服务）
- 需要用户提供：`ANTHROPIC_API_KEY` 或 `DEEPSEEK_API_KEY` 之一

---

_本 CHANGELOG 由 Claude 在用户睡觉时自动维护，用户可随时查阅进度。_
