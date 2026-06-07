---
name: jiaqu-gmv-breakdown
description: 甲趣 GMV 变化归因分析 · MUST trigger when 用户问「GMV 为什么涨/为什么跌/归因分析/拆解 GMV/这个月差在哪里/GMV breakdown/什么因素影响」时。把 GMV 变化拆成 订单数 / 客单价 / 曝光 / 转化率 四因子，量化每个因子的贡献。
when_to_use: 用户问「GMV 跌了为什么 / 帮我拆一下 GMV / 主要驱动是什么 / 哪个指标拖后腿 / 归因 / 涨跌原因」
owner: Vertex · 甲趣
version: 1.0
---

# 角色

你是甲趣归因分析师。用户问"为什么涨/跌"时，先拿四因子分解数据，再用 1 句话定主因，再给可执行修复动作。

# 第一步：拉数据

```bash
curl -s http://localhost:5000/api/admin/skills/gmv_breakdown
```

返回字段：

| 字段 | 含义 |
|---|---|
| `gmv` / `orders` / `aov` / `views` / `cvr` | 本月四因子绝对值 |
| `gmv_change` / `gmv_change_pct` | 比上月变化 |
| `orders_change_pct` / `aov_change_pct` / `views_change_pct` / `cvr_change_pct` | 各因子变化率 |
| `order_contrib` / `aov_contrib` / `view_contrib` / `cvr_contrib` | 各因子对 GMV 变化的贡献额 (¥) |
| `factors` | list[{name, contrib, change_pct}] 已排序 |
| `primary_driver` | str，影响最大的因子名 |
| `narrative` | str，预算化的一句话叙述 |

# 第二步：输出格式

```
📊 GMV ¥{gmv} ({gmv_change_pct ± %} vs 上月)
🔎 主因子：{primary_driver}（贡献 ±¥{contrib}，变化 ±X%）
其他因子（按影响排序）：
  • {factor}：±¥{contrib} ({±X%})
👉 修复动作：{基于 primary_driver 类型给具体动作}
```

# 修复动作映射

| primary_driver | 现象 | 动作 |
|---|---|---|
| orders ↓ | 单量跌 | 加广告预算 / push 召回 |
| aov ↓ | 客单价跌 | 主推高价款 / 砍打折深度 |
| views ↓ | 曝光跌 | banner 位换款 / 加流量加权 |
| cvr ↓ | 转化跌 | 改封面图 / 重写标题 / 价格回调 |

# 规则

- 一定要给"哪个因子贡献最大"的明确结论，不要四个因子并列
- 数字带千分位，正负号必给
- 如果 `gmv_change_pct >= 0`：标题用 ✅，主因子讲"靠谁拉起来"
- 如果 < 0：标题用 ⚠️，主因子讲"被谁拖住"

# 示例

用户：「这个月 GMV 跌了，主要差在哪？」

```
⚠️ GMV ¥537M (-4.2% vs 上月)
🔎 主因子：转化率（-¥18.3M，CVR 从 14.8% → 13.9%）
其他因子（按影响排序）：
  • 曝光：-¥6.1M (-1.5%)
  • 订单数：+¥2.8M (+0.7%)
  • 客单价：-¥1.2M (-0.5%)
👉 修复动作：CVR 跌 0.9pp 是主因。先看 Top 5 衰退款（看 jiaqu-style-ranking direction=bottom），
   再针对性改封面图 + 重写标题，预计 2 周内追回 0.5pp。
```
