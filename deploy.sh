#!/bin/bash
# ============================================================
# 甲趣一键部署脚本 - 在 /opt/jiaqu 下运行
# 用法: ./deploy.sh
# 功能: 杀 Flask → 兜底 stash → 拉新代码 → 同步 skill → 起 Flask → 健康检查
# ============================================================
set -e

cd "$(dirname "$0")"

echo "==> [1/6] 杀掉旧 Flask / gunicorn（先杀，否则它会持续写 nohup.out 卡住 rebase）"
# 必须三连杀：gunicorn master+worker、python3 app.py（dev 模式回退）、任何占着 5000 的兜底
pkill -9 -f "gunicorn.*app:app" 2>/dev/null || true
pkill -9 -f "python3 app.py" 2>/dev/null || true
fuser -k 5000/tcp 2>/dev/null || true
sleep 2
# 验证：端口必须为空，否则后面 gunicorn 还是会 Address already in use
if ss -tln 2>/dev/null | grep -q ":5000 "; then
  echo "    ❌ 端口 5000 仍被占用，强制退出。手动: lsof -i:5000 看是谁"
  ss -tlnp 2>/dev/null | grep ":5000 "
  exit 1
fi
echo "    端口 5000 已清空"

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

echo "==> [5/7] 同步 Python 依赖（gunicorn / Pillow 等新加的包）"
# shellcheck disable=SC1091
source venv/bin/activate
# shellcheck disable=SC1091
source .env
pip install -q -r requirements.txt 2>&1 | tail -3 || echo "    ⚠️ pip install 有问题，继续"

echo "==> [6/7] 启动新 Flask"
# 优先用 gunicorn 4 worker：一个 AI 请求只阻塞 1/4 worker，其他 3 个继续服务
# 没装 gunicorn 时回退到 python3 app.py（开发模式）
if python3 -c "import gunicorn" 2>/dev/null; then
  # 4 worker × 8 thread = 32 并发请求（同时处理图片 + API + AI）
  # 4G RAM 4 core，每 worker ~150-250MB → 总 ~1GB，给 AI/openclaw 留余地
  echo "    使用 gunicorn 4 worker × 8 thread = 32 并发 (timeout 600s)"
  nohup gunicorn -w 4 --threads 8 -k gthread \
    -b 0.0.0.0:5000 --timeout 600 \
    --access-logfile - app:app > nohup.out 2>&1 &
else
  echo "    ⚠️  没装 gunicorn，回退到 python3 app.py 单进程（AI 请求会阻塞其他请求）"
  echo "    建议: pip install gunicorn 然后重跑 deploy.sh"
  nohup python3 app.py > nohup.out 2>&1 &
fi
sleep 3

echo "==> [7/7] 健康检查"
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

