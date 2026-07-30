#!/usr/bin/env bash
# scripts/daily.sh — 每日盘后一键跑
# ============================================
# 用途：
#   1. 生成每日 A 股分析报告（大盘情绪 + Top N 个股）
#   2. 对 swing_v1 假想账户执行当日撮合
#   3. 把结果 push 到 GitHub 私仓
#   4. 通过飞书/钉钉/微信/邮件推送摘要（如已配置）
#
# 用法：
#   ./scripts/daily.sh
#
# 建议 crontab 每交易日 15:30 后跑一次：
#   30 15 * * 1-5 cd /home/gem/tonghuashunAI && ./scripts/daily.sh >> logs/daily.log 2>&1

set -euo pipefail
cd "$(dirname "$0")/.."

# 加载 .env（如果存在）
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

DATE=$(date +%Y-%m-%d)
mkdir -p logs/reports logs/portfolio

echo "===== $(date +%Y-%m-%d\ %H:%M:%S) 开始每日任务 ====="

# 1. 生成每日报告
echo "[1/4] 生成每日报告..."
python3 examples/daily_report_demo.py --limit 50 --top 10 --save "logs/reports/${DATE}.md" || {
  echo "  ⚠️  报告生成失败，继续"
}

# 2. 跑假想账户
echo "[2/4] 执行 swing_v1 撮合..."
python3 examples/paper_trade_demo.py --limit 50 --date "${DATE}" --no-llm || {
  echo "  ⚠️  撮合失败，继续"
}

# 3. 推送通知
echo "[3/4] 发送通知..."
python3 -c "
import sys
from pathlib import Path
from notify.dispatch import notify, summary_line

report_path = Path('logs/reports/${DATE}.md')
if not report_path.exists():
    sys.exit(0)

text = report_path.read_text(encoding='utf-8')
# 只发前 2000 字符（IM 有长度限制）
text = text[:2000]
result = notify(f'A股每日分析 ${DATE}', text)
print('  ' + summary_line(result))
"

# 4. 同步到 GitHub
echo "[4/4] 同步到 GitHub..."
git add logs/reports/${DATE}.md logs/portfolio/*.json 2>/dev/null || true
if ! git diff --cached --quiet; then
  git commit -m "daily: ${DATE} 报告 + 账户快照" || true
  git push || echo "  ⚠️  push 失败（可能是网络问题），下次自动重试"
else
  echo "  无新变更，跳过 push"
fi

echo "===== 完成 ====="
