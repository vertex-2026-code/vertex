#!/bin/bash
# ============================================================
# 甲趣一键部署脚本 - 在 /opt/jiaqu 下运行
# 用法: ./deploy.sh
# 功能: 杀 Flask → 兜底 stash → 拉新代码 → 同步 skill → 起 Flask → 健康检查
# ============================================================
set -e

cd "$(dirname "$0")"

echo "==> [1/6] 杀掉旧 Flask（先杀，否则它会持续写 nohup.out 卡住 rebase）"
pkill -9 -f "python3 app.py" 2>/dev/null || true
sleep 1

echo "==> [2/6] 兜底 stash 任何 dirty 文件（nohup.out / VS Code 临时改的 wiki 等）"
if [ -n "$(git status --porcelain)" ]; then
  git stash push -u -m "deploy_auto_$(date +%Y%m%d_%H%M%S)" > /dev/null
  echo "    已 stash dirty 文件（git stash list 可见）"
fi

echo "==> [3/6] 拉新代码"
git pull --rebase origin main
echo "    HEAD: $(git log --oneline -1)"

echo "==> [4/6] 同步 OpenClaw skill"
if [ -d skills ]; then
  mkdir -p /root/.openclaw/workspace/skills
  cp -r skills/* /root/.openclaw/workspace/skills/
  echo "    已同步 skills/ → /root/.openclaw/workspace/skills/"
fi

echo "==> [5/6] 启动新 Flask"
# shellcheck disable=SC1091
source venv/bin/activate
# shellcheck disable=SC1091
source .env
# 优先用 gunicorn 4 worker：一个 AI 请求只阻塞 1/4 worker，其他 3 个继续服务
# 没装 gunicorn 时回退到 python3 app.py（开发模式）
if python3 -c "import gunicorn" 2>/dev/null; then
  echo "    使用 gunicorn 4 worker (timeout 600s)"
  nohup gunicorn -w 4 -b 0.0.0.0:5000 --timeout 600 --access-logfile - app:app > nohup.out 2>&1 &
else
  echo "    ⚠️  没装 gunicorn，回退到 python3 app.py 单进程（AI 请求会阻塞其他请求）"
  echo "    建议: pip install gunicorn 然后重跑 deploy.sh"
  nohup python3 app.py > nohup.out 2>&1 &
fi
sleep 3

echo "==> [6/6] 健康检查"
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

