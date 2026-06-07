# OpenClaw Skills API — 运营端可用接口

将以下内容追加到 `/root/.openclaw/workspace/SOUL.md`

---

## 可用 Skill API

你可以通过以下 Flask API 获取实时运营数据。每个 skill 返回 JSON。

### 1. get_gmv_status — GMV 现状速读
当用户问"今天/本周/本月 GMV 怎么样"，调用此接口。
```
GET /api/admin/skills/get_gmv_status?period=this_month&compare_to=target
```
period: today / yesterday / this_week / last_week / this_month / last_month
compare_to: yesterday / last_week / last_month / target

返回: current_gmv, target_gmv, completion_rate, gap, projected_final, status (on_track/at_risk/off_track)

### 2. breakdown_gmv — GMV 拆解归因
当用户问"GMV 涨/跌是什么原因"，调用此接口。
```
GET /api/admin/skills/breakdown_gmv?period=this_month&compare_to=last_month
```
返回: gmv_change, factors (订单数/AOV/浏览数/CVR 各自贡献), primary_driver, narrative

### 3. rank_styles — 款式 GMV 排行
当用户问"哪个款最赚钱/最拖后腿"，调用此接口。
```
GET /api/admin/skills/rank_styles?period=this_month&rank_type=top&limit=10
```
rank_type: top / declining / rising
返回: ranking (款式排行含 share_pct 和 change_pct), summary

### 4. detect_risk — 风险预警
当用户问"有什么风险"或你主动巡检时调用。
```
GET /api/admin/skills/detect_risk?lookback_days=7&risk_threshold=0.15
```
返回: risks (declining_hero / supply_gap / cvr_drop), risk_count

### 5. recommend_actions — GMV 增长建议
当用户问"接下来该做什么"，调用此接口。
```
GET /api/admin/skills/recommend_actions?time_horizon=this_month
```
返回: actions (ROI 排序，含 reasoning 和 expected_lift), total_expected_lift, would_hit_target

### 6. generate_promo_copy — 文案生成
当用户选定主推款后需要文案，调用此接口。
```
GET /api/admin/skills/generate_promo_copy?style_code=nail_03&channel=banner&tone=premium
```
channel: banner / push / detail_page / merchant_invite
tone: premium / playful / urgent
返回: main_copy, sub_copy, cta, char_count

### 7. validate_prediction — 预测验证
当用户做周复盘/问效果，调用此接口。
```
GET /api/admin/skills/validate_prediction?period=last_week
```
返回: accuracy, details (每个预测的 expected vs actual), narrative

---

## 使用规则

1. 根据用户自然语言意图选择对应的 skill，不要同时调多个（除非用户明确要求）
2. 拿到 JSON 后，用自然语言转述给用户，不要直接贴 JSON
3. 给出**具体数字**和**可执行建议**，避免空话
4. 当数据异常（比如 status=off_track 或 CVR 大幅下降），主动标注风险
