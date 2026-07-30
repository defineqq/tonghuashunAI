# CHANGELOG

## 2026-07-30

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
