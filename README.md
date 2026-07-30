# tonghuashunAI

A 股 AI 量化分析与自动化交易项目。**当前阶段：模拟盘 / 尚未接实盘。**

## 架构

以开源项目 [Qbot](https://github.com/UFund-Me/Qbot)（1.8w⭐, MIT）为底座，源码已作为**本地副本**纳入 `vendor/Qbot/`（详见 `NOTICE.md`）。本仓库同时维护自定义策略、AI 分析层、股票池、配置和运行脚本。

> **为什么直接纳入而不用 submodule？** 上游可能停更，直接纳入避免风险；同时精简了 600+MB 无关文件（预编译 wheel、教程代码、二进制工具），Qbot 部分只保留 77MB 的核心 Python 源码。

```
tonghuashunAI/
├── vendor/Qbot/         # Qbot 源码副本：数据/回测/模拟盘/通知（精简后 77MB）
├── data_layer/          # 数据层：统一封装 AkShare + 本地 parquet 缓存
├── my_strategies/       # 自定义策略
├── ai_analysis/         # LLM 情绪分析、每日报告
├── configs/             # 股票池、策略参数、密钥模板
├── examples/            # 最小可运行示例
├── scripts/             # 一键脚本：回测、模拟盘、每日报告
├── data/                # 本地缓存（.gitignore）
└── logs/                # 日志（.gitignore）
```

## 快速开始

```bash
# 1. 克隆（Qbot 已作为普通目录纳入，无需 --recurse-submodules）
git clone https://github.com/defineqq/tonghuashunAI.git
cd tonghuashunAI

# 2. 建虚拟环境（Qbot 要求 Python 3.8 / 3.9）
python3.9 -m venv .venv
source .venv/bin/activate

# 3. 装依赖
pip install -r vendor/Qbot/requirements.txt
pip install -r requirements.txt

# 4. 跑最小示例
python examples/hello_qbot.py
```

## 路线图

- [x] M0：初始化仓库、引入 Qbot 底座
- [ ] M1：数据+分析层（拉行情、四维度评分）
- [ ] M2：策略+回测（日级波段策略、历史回测）
- [ ] M3：本地模拟撮合（每日盘前跑策略、假想账户跟踪 PnL）
- [ ] M4：接入 Qbot 模拟盘（真实模拟环境跑 3 个月）

## 数据源

- **行情/资金流**：AkShare、Tushare（Qbot 内置）
- **基本面**：AkShare
- **新闻/公告/龙虎榜**：AkShare + 财联社 / 东财 抓取
- **LLM 分析**：待定（Claude / DeepSeek / 通义）

## 免责声明

本项目仅用于学习和研究目的。**当前只涉及模拟盘，不涉及真实交易。**任何策略回测结果不构成投资建议，实盘有风险，入市需谨慎。
