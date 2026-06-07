#!/bin/bash
# ============================================================
# 甲趣一键部署脚本 - 在 /opt/jiaqu 下运行
# 用法: ./deploy.sh
# 功能: 拉新代码 → 同步 skill → 重启 Flask → 健康检查
# ============================================================
set -e  # 任一步失败立刻停止

cd "$(dirname "$0")"
echo "==> [1/5] 解封 + 拉新代码"
git checkout -- nohup.out 2>/dev/null || true
git pull --rebase origin main
echo "    HEAD: $(git log --oneline -1)"

echo "==> [2/5] 同步 OpenClaw skill"
if [ -d skills ]; then
  mkdir -p /root/.openclaw/workspace/skills
  cp -r skills/* /root/.openclaw/workspace/skills/
  echo "    已同步 skills/ → /root/.openclaw/workspace/skills/"
fi

echo "==> [3/5] 杀掉旧 Flask"
pkill -9 -f "python3 app.py" 2>/dev/null || true
sleep 1

echo "==> [4/5] 启动新 Flask"
# shellcheck disable=SC1091
source venv/bin/activate
# shellcheck disable=SC1091
source .env
nohup python3 app.py > nohup.out 2>&1 &
sleep 2

echo "==> [5/5] 健康检查"
HEALTH=$(curl -s --max-time 3 http://localhost:5000/health || echo FAIL)
echo "    /health → $HEALTH"

if [[ "$HEALTH" == *"\"ok\""* ]]; then
  echo ""
  echo "✅ 部署成功"
  echo "   C 端:       http://124.221.15.86:5000/"
  echo "   运营端:     http://124.221.15.86:5000/admin"
  echo "   商家端:     http://124.221.15.86:5000/merchant"
  echo "   商家数据库: http://124.221.15.86:5000/merchant-dataset"
else
  echo ""
  echo "❌ 启动失败，看日志：tail -50 nohup.out"
  tail -20 nohup.out
  exit 1
fi
