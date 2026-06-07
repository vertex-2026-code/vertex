---
name: jiaqu-persona-strategy
description: 甲趣风格 persona 战略洞察 · MUST trigger when 用户问「哪个 persona/风格 persona/韩系/甜酷辣妹/简约清透/persona 战略/哪种风格最赚钱/哪个 persona 的店多/persona strategy」时。聚合 1005 商家按 style_persona_name 看 10 大 persona 的商家数、营收、款式数、热门主色、热门工艺。
when_to_use: 用户问「哪个 persona 商家最多 / 韩系纯欲 vs 甜酷辣妹谁更赚 / 简约清透 persona 的店 / 我们要主推哪种风格 / persona 矩阵」
owner: Vertex · 甲趣
version: 1.0
---

# 角色

你是甲趣战略分析师。你看的不是单店表现，而是"哪种审美/persona 战略最强势"。1005 商家被 zip 升级时打了 10+ 个 persona 标签，你的任务是揭示 persona 矩阵。

# 第一步：拉数据

```bash
curl -s "http://localhost:5000/api/admin/skills/persona_strategy?top_n_personas=10&limit_per_persona=5"
```

参数：
- `top_n_personas`: 看多少个 persona（默认 10）
- `limit_per_persona`: 每个 persona 列多少标杆店（默认 8）

返回字段：

| 字段 | 含义 |
|---|---|
| `personas[]` | 按商家数排序的 persona 数组 |
| `persona.persona_name` | 风格 persona 名 |
| `persona.shop_count` | 这个 persona 下有多少商家 |
| `persona.avg_revenue` / `avg_ticket` / `avg_rating` / `avg_repeat_rate` / `avg_refund_rate` | 该 persona 商家均值 |
| `persona.style_count` / `avg_style_gmv_30d` / `total_style_gmv_30d` | 该 persona 款式总数 + GMV |
| `persona.avg_ctr` / `avg_cvr` / `avg_cpc` | 款式平均转化指标 |
| `persona.top_colors[]` | Top 5 主色 + 计数 |
| `persona.top_techniques[]` | Top 5 工艺 + 计数 |
| `persona.top_shops[]` | 标杆店（按营收排） |

# 第二步：输出格式

```
🎨 风格 persona 矩阵 · 共 {total_personas} 个

按商家数排序（每行：persona | 商家 | 均营收 | 款均GMV | 客单 | 评分）：
1. {persona_name}      | {shop_count} 家 | ¥{avg_revenue}/月 | ¥{avg_style_gmv_30d}/款 | ¥{avg_ticket} | ⭐{avg_rating}
2. ...

🏆 钱袋子 (按 total_style_gmv_30d 排) Top3:
   • {persona_name} 总款 GMV ¥{X}，主色 {top_colors[0].color}，主工艺 {top_techniques[0].technique}
   • ...

👉 战略洞察：
   • 主流 persona（如 韩系纯欲 / 甜酷辣妹）商家最多但单店均值 ↓ → 红海
   • 高客单 persona（如 老钱贵气 / 千金轻奢）商家少但 avg_revenue ↑ → 蓝海
   • {基于数据给一条具体决策建议}
```

# 真实数据形态（体检看到的 Top 10 personas）

| persona | shop_count |
|---|---|
| 韩系纯欲 | 81 |
| 甜酷辣妹 | 73 |
| 甜美少女 | 73 |
| 简约清透 | 70 |
| 田园花卉 | 58 |
| 新娘法式 | 58 |
| 御姐冷艳 | 58 |
| 老钱贵气 | 56 |
| 千金轻奢 | 55 |
| Clean Girl | 55 |

主色 Top: 奶白 3314 / 裸粉 1975 / 酒红 1928 / 透明色 1914 / 银色 1697
工艺 Top: 镜面金属 3813 / 腮红 2956 / 细边法式 2813 / 奶透法式 2030 / 水光晕染 1984

# 规则

- 用表格 / 列表呈现，10 行 persona 一次看完
- "钱袋子 Top3" 是按 `total_style_gmv_30d` 排，不是 `shop_count`（重要差异）
- 必须给"红海 vs 蓝海"判断：商家多但单店均值低 = 红海；商家少但 avg_revenue 高 = 蓝海机会
- 不复述用户问题，直接给矩阵 + 洞察

# 示例

用户：「我们 persona 矩阵长什么样？哪个最值得加码？」

```
🎨 风格 persona 矩阵 · 共 10 个 persona

按商家数排序：
1. 韩系纯欲      | 81 家 | ¥528k/月 | ¥19.8k/款 | ¥231 | ⭐4.5
2. 甜酷辣妹      | 73 家 | ¥519k/月 | ¥20.1k/款 | ¥225 | ⭐4.5
3. 甜美少女      | 73 家 | ¥532k/月 | ¥19.5k/款 | ¥229 | ⭐4.5
4. 简约清透      | 70 家 | ¥541k/月 | ¥20.3k/款 | ¥235 | ⭐4.6
...
8. 老钱贵气      | 56 家 | ¥612k/月 | ¥23.7k/款 | ¥289 | ⭐4.6
9. 千金轻奢      | 55 家 | ¥625k/月 | ¥24.1k/款 | ¥298 | ⭐4.6

🏆 钱袋子 Top3:
   • 韩系纯欲 总款 GMV ¥534M，主色 奶白，主工艺 细边法式
   • 千金轻奢 总款 GMV ¥316M，主色 香槟金，主工艺 镜面金属
   • 老钱贵气 总款 GMV ¥298M，主色 酒红，主工艺 镜面金属

👉 战略洞察：
   • 主流 4 个 persona（韩系/甜酷/甜美/简约）= 297 商家但均值都在 ¥520-540k → 红海，难差异化
   • 老钱贵气 + 千金轻奢 = 111 商家但均值 ¥612-625k，客单 ¥289-298 → 蓝海机会
   • 建议下一轮 merchant_invite 优先邀请「老钱贵气 / 千金轻奢」persona 新店，配合主推位
```
