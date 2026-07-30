# NOTICE

本仓库 `vendor/Qbot/` 目录下包含开源项目 [Qbot](https://github.com/UFund-Me/Qbot) 的源代码副本。

## 来源

- **上游项目**：https://github.com/UFund-Me/Qbot
- **克隆版本**：2026-07-30 主分支最新快照
- **协议**：MIT License（见 `vendor/Qbot/LICENSE`）
- **版权**：Copyright (c) 2022 UFund-Me
- **原作者**：Charmve 等（详见 vendor/Qbot/README.md）

## 说明

- 出于**上游可能停更**的风险考量，我们没有采用 git submodule，而是把 Qbot 源码直接纳入本仓库，作为一份快照独立维护。
- 已从上游删除的内容（为控制仓库体积）：
  - `.git/` submodule 元数据
  - `dev/*.whl` 预编译 wheel 包（wxPython、TA-Lib，pip 装依赖时会自动下载）
  - `docs/tutorials_code/`、`docs/notebook/` 教程代码与大 notebook（323 MB）
  - `qbot/plugins/investool/` Go 语言二进制工具（86 MB）
  - `web/` 前端 GUI 资源（暂不使用）
  - 各类 `*.exe` `*.dll` `*.dylib` 二进制可执行文件
- 保留 Qbot 完整的 Python 源码、策略库、回测引擎、交易适配层、精简的文档。
- 未来如果需要同步上游更新，可执行：
  ```bash
  # 备份自己的修改，然后：
  rm -rf vendor/Qbot
  git clone --depth 1 https://github.com/UFund-Me/Qbot.git vendor/Qbot
  rm -rf vendor/Qbot/.git vendor/Qbot/dev/*.whl vendor/Qbot/docs/tutorials_code \
         vendor/Qbot/docs/notebook vendor/Qbot/qbot/plugins/investool vendor/Qbot/web
  ```

## 我们的修改

本仓库根目录下的其他内容（`data_layer/`、`my_strategies/`、`ai_analysis/`、`configs/`、`examples/`、`scripts/` 等）为本项目原创，采用与上游一致的 MIT 协议。

## 致谢

感谢 Qbot 团队开源了这样一个优秀的量化投研平台。
