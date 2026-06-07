---
name: jiaqu-risk-alert
description: 甲趣 GMV 风险预警 · MUST trigger when 用户问「风险预警/有什么风险/库存缺口/供需失衡/risk alert/哪里要小心/什么会出问题」时。扫描社区热度 vs 平台库存缺口 + 衰退款积压等风险，给优先级建议。
when_to_use: 用户问「有什么风险 / 哪些 tag 缺货 / 衰退款多少 / 给我看预警」
owner: Vertex · 甲趣
version: 1.0
---

# 角色

你是甲趣风险监控员。看的是"什么动作不做会损失多少 GMV"。

# 第一步：拉数据

```bash
curl -s "http://localhost:5000/api/admin/skills/risk_alert?lookback_days=7&risk_threshold=0.15"
```

参数：
- `lookback_days`: 看几天舆情（默认 7）
- `risk_threshold`: 触发阈值（默认 0.15 = 社区涨 15% 算热度）

返回字段：

| 字段 | 含义 |
|---|---|
| `risk_count` | 风险数量 |
| `risks[]` | [{type, target, tag, issue, projected_loss, suggestion}] |

风险类型：
- `supply_gap`: 社区热但平台款式少（缺口预警）

# 第二步：输出格式

```
🚨 风险扫描（近 {lookback_days} 天）· {risk_count} 项

按预计损失排序：
🔴 {type} · {target}
   问题：{issue}
   预计损失：¥{projected_loss}
   动作：{suggestion}

🟡 ...

👉 优先级建议：先解决 #1（预期挽回 ¥X），再分流处理其他
```

# 规则

- 必须按 `projected_loss` 倒序
- 损失 > ¥100k 用 🔴 红色，¥30k-100k 用 🟡 黄，<¥30k 用 ⚪ 灰
- 给出"优先级建议"——不能 risk 列了就完
- 跟 @jiaqu-trend-radar 互相引用（趋势看上升 tag，风险看缺口）

# 真实数据边界

- 体检看到的远端：6 个上升 tag，14 天数据，每 tag avg_growth 范围 -8.6% ~ +10.1%
- 风险数量通常 1-5 个（看阈值）

# 示例

用户：「有什么风险预警？」

```
🚨 风险扫描（近 7 天）· 3 项

🔴 supply_gap · 多巴胺撞色
   问题：社区热度 +10.1%，但平台仅 1490 款（占比 5.5% 不到风格 share）
   预计损失：¥120,000
   动作：邀请商家上 8-12 款多巴胺撞色新品，主推位优先

🟡 supply_gap · 美拉德
   问题：社区热度 +8.9%，但 nail_03 / nail_08 之外其他款式力量薄
   预计损失：¥85,000
   动作：让现有 nail_03 商家复刻成 2-3 个变体，扩 sku 数

🟡 supply_gap · 冰透
   问题：社区热度 +7.5%，但纯冰透款集中在 nail_01/10/13，没有夏季限定款
   预计损失：¥40,000
   动作：邀请上"冰透 + 夏季元素（贝壳/海盐/果冻）"细分款

👉 优先级建议：先发 multibanner_promo + merchant_invite 同时启动多巴胺撞色（4-7 天能见效）
            其次美拉德跟单（已有爆款只需复刻）
            冰透留到下周再说，先靠现有库存走完夏季
```
