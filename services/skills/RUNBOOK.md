# Skills RUNBOOK · GMV 运营端 OpenClaw

## 部署

```bash
# 1. 本仓库已含 skill 代码，git pull 即可
cd /opt/jiaqu && git pull

# 2. 追加到 OpenClaw workspace 配置
cat services/skills/SOUL_SNIPPET.md >> /root/.openclaw/workspace/SOUL.md

# 3. 重启 Flask
./deploy.sh
```

## 自然语言触发词 → API 映射

| 运营问（示例） | Skill | API Query |
|---|---|---|
| "今天 GMV 多少" | get_gmv_status | `?period=today` |
| "本月 GMV 完成怎么样了" | get_gmv_status | `?period=this_month&compare_to=target` |
| "和上周比涨了多少" | get_gmv_status | `?period=this_week&compare_to=last_week` |
| "为什么 GMV 跌了" | breakdown_gmv | `?period=this_month` |
| "哪个款卖得最好" | rank_styles | `?period=this_month&rank_type=top&limit=10` |
| "哪个款在跌" | rank_styles | `?period=this_month&rank_type=declining&limit=5` |
| "有什么风险吗" | detect_risk | 默认参数 |
| "接下来该推什么" | recommend_actions | `?time_horizon=this_month` |
| "要完成本月目标还能做什么" | recommend_actions | 同上 |
| "给 nail_03 写个 Banner 文案" | generate_promo_copy | `?style_code=nail_03&channel=banner&tone=premium` |
| "发个 Push 召回" | generate_promo_copy | `?channel=push&tone=urgent` |
| "上周的预测准不准" | validate_prediction | `?period=last_week` |

## 典型对话示例

### 示例 1: 快速问 GMV
```
User: "本月 GMV 怎么样"
API : GET /api/admin/skills/get_gmv_status?period=this_month&compare_to=target
AI  : "6 月至今 GMV ¥238k，月目标 ¥1.5M，完成率 15.9%，缺口 ¥1.26M。
       按当前日均 ¥40k 推算，月末约 ¥1.2M，状态: off_track，建议关注增长建议。"
```

### 示例 2: 归因分析
```
User: "GMV 为什么跌了"
API : GET /api/admin/skills/breakdown_gmv?period=this_month
AI  : "本期 GMV -¥195k，主要下降因子是浏览数（贡献 -¥227k）。
       AOV 和 CVR 基本持平，流量不足是核心瓶颈。建议推主推位提升曝光。"
```

### 示例 3: 选品决策
```
User: "哪个款最赚钱"
API : GET /api/admin/skills/rank_styles?period=this_month&rank_type=top&limit=5
AI  : "Top 1: nail_04（多巴胺撞色）¥58,813，占比 24.7%。多巴胺撞色连续上榜，
       建议继续主推。末位 nail_01（冰透）¥9,484，可考虑降权。"
```

### 示例 4: 增长建议
```
User: "接下来该做什么"
API : GET /api/admin/skills/recommend_actions?time_horizon=this_month
AI  : "3 条建议（按 ROI 排序）：
       1. [高ROI] 给 nail_04 加 Banner，预计 +¥379k
       2. [高ROI] 推高价款提 AOV，预计 +¥253k
       3. [中ROI] Push 通知召回用户，预计 +¥151k
       全部采纳预计月末 ¥1.02M，仍需追加动作才能达标。"
```

### 示例 5: 效果复盘
```
User: "上周的预测效果如何"
API : GET /api/admin/skills/validate_prediction?period=last_week
AI  : "上周 2 个运营动作，准确率 0%。actual_gmv_lift 尚未回填，
       建议补充实际数据后重跑。"
```

## 测试

```bash
# 在本地 Mac 运行（不依赖 Flask）
python3 -c "
import sqlite3
db = sqlite3.connect('data/jiaqu.db')
db.row_factory = sqlite3.Row
from services.skills import SKILL_MAP
import json
for name, fn in SKILL_MAP.items():
    try:
        result = fn(db)
        print(f'{name}: OK')
    except Exception as e:
        print(f'{name}: FAIL - {e}')
"

# pytest（需要安装 pytest）
pip install pytest
pytest tests/skills/ -v
```

## 故障排查

| 现象 | 原因 | 解决 |
|---|---|---|
| `ImportError: services` | Python path 不对 | `cd /opt/jiaqu` 后运行 |
| `sqlite3.OperationalError` | 表不存在 | 先跑 `python3 mock_operation_metrics.py` |
| 返回空数据 | 日期范围无数据 | 检查 `operation_metrics` 的 date 范围 |
| 预测准确率 0% | `actual_gmv_lift` 未回填 | 正常现象，等运营执行后 UPDATE |
