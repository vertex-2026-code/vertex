from __future__ import annotations

import hashlib
import json
import os
import random
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


BJT = timezone(timedelta(hours=8))
DEFAULT_PASSWORD = "demo123456"
DATASET_SUMMARY_FILENAME = "merchant_dataset_summary.json"
ARK_IMAGE_ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
DEFAULT_STYLE_IMAGE_MODEL = os.environ.get("MERCHANT_STYLE_IMAGE_MODEL", "doubao-seedream-4-5-251128")
DEFAULT_STYLE_IMAGE_SIZE = os.environ.get("MERCHANT_STYLE_IMAGE_SIZE", "2K")
STYLE_IMAGE_DIRNAME = "generated_styles"
LEGACY_STYLE_PERSONA_MAP = {
    "甜美可爱": "甜美少女",
    "闪耀华丽": "千金轻奢",
    "冷感暗黑": "御姐冷艳",
    "趋势实验": "拼色实验",
}

PRIMARY_STYLES = {
    "A": ["奶白法式", "冰透猫眼", "裸粉极简", "水晶点缀", "雾感奶咖"],
    "B": ["草莓奶冻", "腮红渐变", "蝴蝶结甜心", "樱花果冻", "奶油爱心"],
    "C": ["碎钻镜面", "极光闪片", "金属流光", "珍珠法式", "银河亮片"],
    "D": ["烟熏冷调", "黑银金属", "深酒红猫眼", "暗夜蓝灰", "冷感雾黑"],
    "E": ["多巴胺撞色", "异形拼贴", "雪花晶石", "未来感光疗", "解构拼色"],
}

CITY_DISTRICTS = {
    "北京": ["三里屯", "国贸", "五道口", "望京", "中关村", "朝阳大悦城"],
    "上海": ["静安寺", "徐家汇", "陆家嘴", "新天地", "五角场", "虹桥"],
    "深圳": ["南山", "福田", "后海", "万象天地", "车公庙", "海岸城"],
    "广州": ["天河", "珠江新城", "太古汇", "番禺", "北京路", "琶洲"],
    "杭州": ["湖滨", "钱江新城", "滨江", "城西银泰", "武林", "未来科技城"],
}

SHOP_PREFIX = ["云釉", "鹿屿", "慢糖", "光屿", "雾白", "朝露", "镜汐", "棠枝", "森屿", "星釉"]
SHOP_SUFFIX = ["美甲研究所", "Nail Studio", "美甲会所", "甲艺空间", "美学社", "设计所"]

TREND_KEYWORDS = {
    "colors": ["冰透蓝", "海盐蓝", "奶油白", "雾霾紫", "香槟金", "樱花粉"],
    "techniques": ["冰透猫眼", "果冻渐变", "细闪法式", "海盐贝壳", "镜面金属", "蝴蝶结点缀"],
    "elements": ["贝壳", "小蝴蝶结", "珍珠", "星月", "水滴", "小钻"],
    "occasions": ["春夏", "约会", "旅行", "拍照", "节日"],
}

STYLE_ARCHETYPES: dict[str, dict[str, Any]] = {
    "A": {
        "merchant_position": "韩系纯欲 / 简约清透 / 通勤显白",
        "primary_styles": {"简约清透": 0.28, "韩系纯欲": 0.26, "白月光": 0.2, "通勤显白": 0.16, "温柔奶系": 0.1},
        "secondary_styles": {"温柔": 0.3, "清透": 0.25, "通勤": 0.22, "约会": 0.13, "清冷": 0.1},
        "shapes": {"短方圆": 0.4, "短杏仁": 0.34, "自然椭圆": 0.18, "中短杏仁": 0.08},
        "lengths": {"超短": 0.1, "短": 0.52, "中短": 0.3, "中长": 0.08},
        "primary_colors": {"奶白": 0.24, "裸粉": 0.24, "豆沙": 0.16, "透明色": 0.14, "奶茶": 0.12, "浅紫": 0.1},
        "accent_colors": ["银色", "白色", "浅粉", "香槟金", "冰透蓝"],
        "transparencies": {"奶透": 0.34, "半透明": 0.28, "冰透": 0.22, "果冻透": 0.16},
        "finishes": {"亮面": 0.36, "果冻": 0.28, "水光": 0.22, "玻璃光": 0.14},
        "base_coats": ["奶透裸粉底", "透明冰透底", "奶白底", "裸粉底"],
        "core_technique_sets": [
            ["腮红", "冰透猫眼"],
            ["细边法式", "果冻渐变"],
            ["水光晕染", "裸透猫眼"],
            ["奶透法式", "微闪"],
        ],
        "support_techniques": ["细闪法式", "微闪", "珍珠法式", "局部贴钻", "极细金边"],
        "elements": ["小蝴蝶结", "小钻", "珍珠", "爱心", "贝壳"],
        "occasions": ["通勤", "约会", "春夏", "拍照"],
        "complexity": {"轻设计": 0.6, "中等": 0.32, "重工": 0.08},
        "forbidden": ["超长甲", "豹纹", "大面积金属链条", "暗黑哥特"],
    },
    "B": {
        "merchant_position": "甜美可爱 / 少女氛围 / 日系软萌",
        "primary_styles": {"甜美少女": 0.32, "蜜桃甜心": 0.24, "芭蕾公主": 0.16, "日系可爱": 0.16, "果冻奶系": 0.12},
        "secondary_styles": {"少女感": 0.3, "甜妹": 0.24, "约会": 0.2, "元气": 0.16, "节日": 0.1},
        "shapes": {"短方圆": 0.38, "短杏仁": 0.28, "自然圆": 0.22, "中短杏仁": 0.12},
        "lengths": {"超短": 0.08, "短": 0.44, "中短": 0.34, "中长": 0.14},
        "primary_colors": {"草莓粉": 0.24, "奶油白": 0.18, "樱花粉": 0.18, "蜜桃橘": 0.16, "奶黄": 0.12, "浅紫": 0.12},
        "accent_colors": ["奶白", "银色", "樱花粉", "蜜桃橘", "浅紫"],
        "transparencies": {"果冻透": 0.3, "半透明": 0.28, "奶透": 0.24, "冰透": 0.18},
        "finishes": {"亮面": 0.34, "果冻": 0.28, "水光": 0.22, "细闪": 0.16},
        "base_coats": ["草莓奶冻底", "奶油白底", "樱花粉底", "蜜桃果冻底"],
        "core_technique_sets": [
            ["腮红", "果冻渐变"],
            ["细边法式", "蝴蝶结贴饰"],
            ["爱心点缀", "微闪"],
            ["樱花晕染", "果冻水光"],
        ],
        "support_techniques": ["小钻点缀", "细闪", "奶油胶蝴蝶结", "花朵贴纸", "彩色法式"],
        "elements": ["蝴蝶结", "爱心", "小钻", "樱花", "草莓", "小珍珠"],
        "occasions": ["约会", "生日", "春夏", "拍照", "节日"],
        "complexity": {"轻设计": 0.44, "中等": 0.42, "重工": 0.14},
        "forbidden": ["大面积黑银金属", "超尖甲", "哥特元素"],
    },
    "C": {
        "merchant_position": "闪耀华丽 / 轻奢精致 / 宴会高光",
        "primary_styles": {"闪耀华丽": 0.26, "轻奢千金": 0.24, "高光宴会": 0.2, "珠宝法式": 0.16, "镜面贵气": 0.14},
        "secondary_styles": {"轻奢": 0.28, "贵气": 0.26, "拍照": 0.2, "聚会": 0.16, "节日": 0.1},
        "shapes": {"中短杏仁": 0.22, "长杏仁": 0.28, "窄方甲": 0.18, "中长棺材": 0.2, "短方圆": 0.12},
        "lengths": {"短": 0.12, "中短": 0.24, "中长": 0.38, "长": 0.26},
        "primary_colors": {"香槟金": 0.18, "酒红": 0.18, "银色": 0.16, "奶白": 0.16, "珍珠白": 0.16, "玫瑰金": 0.16},
        "accent_colors": ["银色", "金色", "珍珠白", "酒红", "奶白"],
        "transparencies": {"半透明": 0.18, "奶透": 0.18, "冰透": 0.16, "实色": 0.24, "果冻透": 0.24},
        "finishes": {"镜面": 0.26, "亮面": 0.24, "珠光": 0.24, "细闪": 0.16, "玻璃光": 0.1},
        "base_coats": ["珍珠奶白底", "香槟珠光底", "酒红亮面底", "奶透镜面底"],
        "core_technique_sets": [
            ["碎钻法式", "珠光"],
            ["镜面金属", "珍珠点缀"],
            ["银河猫眼", "液态金属"],
            ["闪粉渐变", "金边法式"],
        ],
        "support_techniques": ["局部排钻", "珍珠法式", "金边", "细闪", "微雕花"],
        "elements": ["珍珠", "碎钻", "金属蝴蝶", "星月", "金边"],
        "occasions": ["聚会", "婚礼", "晚宴", "节日", "拍照"],
        "complexity": {"轻设计": 0.18, "中等": 0.44, "重工": 0.38},
        "forbidden": ["过度儿童感卡通", "粗糙撞色"],
    },
    "D": {
        "merchant_position": "冷感暗黑 / 甜酷辣妹 / 夜店镜面",
        "primary_styles": {"冷感暗黑": 0.28, "甜酷辣妹": 0.24, "Y2K 夜色": 0.18, "哥特冷艳": 0.16, "金属烟熏": 0.14},
        "secondary_styles": {"酷飒": 0.3, "夜店": 0.24, "拍照": 0.2, "高反差": 0.16, "秋冬": 0.1},
        "shapes": {"长棺材": 0.28, "长尖甲": 0.22, "中长棺材": 0.22, "长杏仁": 0.18, "窄方甲": 0.1},
        "lengths": {"中短": 0.08, "中长": 0.34, "长": 0.38, "超长": 0.2},
        "primary_colors": {"黑色": 0.24, "冷灰": 0.18, "酒红": 0.18, "银色": 0.16, "深蓝": 0.12, "紫黑": 0.12},
        "accent_colors": ["银色", "酒红", "冰蓝", "紫色", "黑色"],
        "transparencies": {"实色": 0.36, "半透明": 0.18, "冰透": 0.16, "果冻透": 0.12, "奶透": 0.18},
        "finishes": {"镜面": 0.32, "亮面": 0.28, "金属": 0.2, "磨砂": 0.12, "细闪": 0.08},
        "base_coats": ["冷灰底", "黑镜面底", "酒红亮面底", "深蓝金属底"],
        "core_technique_sets": [
            ["镜面金属", "火焰法式"],
            ["烟熏晕染", "十字猫眼"],
            ["黑银撞色", "局部贴钻"],
            ["酒红猫眼", "液态金属"],
        ],
        "support_techniques": ["链条点缀", "十字架贴饰", "豹纹局部", "细闪", "金属边线"],
        "elements": ["十字架", "链条", "爱心", "豹纹", "金属蝴蝶", "铆钉"],
        "occasions": ["夜店", "拍照", "秋冬", "音乐节", "聚会"],
        "complexity": {"轻设计": 0.12, "中等": 0.34, "重工": 0.54},
        "forbidden": ["奶油可爱风", "大面积浅粉纯欲"],
    },
    "E": {
        "merchant_position": "趋势实验 / 小众设计 / 平台热点融合",
        "primary_styles": {"趋势实验": 0.28, "多巴胺撞色": 0.2, "未来感解构": 0.18, "艺术拼贴": 0.18, "热点融合": 0.16},
        "secondary_styles": {"平台爆款": 0.24, "拍照": 0.22, "夏季": 0.18, "艺术感": 0.18, "先锋": 0.18},
        "shapes": {"短方圆": 0.18, "中短杏仁": 0.22, "长杏仁": 0.2, "长棺材": 0.2, "异形甲": 0.2},
        "lengths": {"短": 0.12, "中短": 0.28, "中长": 0.28, "长": 0.2, "超长": 0.12},
        "primary_colors": {"冰透蓝": 0.18, "多巴胺橘": 0.16, "奶白": 0.14, "霓虹粉": 0.14, "牛油果绿": 0.14, "银色": 0.12, "透明色": 0.12},
        "accent_colors": ["海盐蓝", "霓虹粉", "银色", "牛油果绿", "奶白", "香槟金"],
        "transparencies": {"冰透": 0.28, "果冻透": 0.26, "半透明": 0.2, "实色": 0.14, "奶透": 0.12},
        "finishes": {"玻璃光": 0.24, "亮面": 0.22, "镜面": 0.18, "果冻": 0.18, "细闪": 0.18},
        "base_coats": ["冰透海盐底", "撞色渐变底", "透明果冻底", "奶白实验底"],
        "core_technique_sets": [
            ["海盐贝壳", "冰透猫眼"],
            ["撞色渐变", "异形拼贴"],
            ["镜面金属", "未来感线条"],
            ["果冻晕染", "多巴胺撞色"],
        ],
        "support_techniques": ["贝壳片", "小钻", "星月", "线条艺术", "液态金属"],
        "elements": ["贝壳", "星月", "水滴", "几何拼贴", "异形金属", "小蝴蝶"],
        "occasions": ["夏季", "旅行", "拍照", "节日", "内容种草"],
        "complexity": {"轻设计": 0.16, "中等": 0.42, "重工": 0.42},
        "forbidden": ["过度传统保守配色"],
    },
}

STYLE_PERSONAS: dict[str, dict[str, Any]] = {
    "minimal_commute": {
        "style_code": "A",
        "name": "简约通勤",
        "merchant_position": "简约通勤 / 低饱和显白 / 上班友好",
        "keywords": ["简约", "通勤", "显白", "低饱和", "干净", "职场友好"],
        "target_audiences": ["白领", "教师", "学生党", "宝妈"],
        "primary_styles": {"简约通勤": 0.34, "低饱和显白": 0.26, "干净利落": 0.2, "气质奶系": 0.12, "办公室友好": 0.08},
        "secondary_styles": {"通勤": 0.32, "知性": 0.24, "清透": 0.18, "显手白": 0.14, "日常": 0.12},
        "shapes": {"短方圆": 0.48, "自然椭圆": 0.24, "短杏仁": 0.2, "中短杏仁": 0.08},
        "lengths": {"超短": 0.16, "短": 0.54, "中短": 0.24, "中长": 0.06},
        "primary_colors": {"奶白": 0.26, "裸粉": 0.24, "豆沙": 0.18, "奶茶": 0.16, "透明色": 0.1, "雾灰": 0.06},
        "support_techniques": ["极细法式", "微闪", "裸透渐变", "局部点钻"],
        "elements": ["小钻", "珍珠", "爱心"],
        "occasions": ["通勤", "开会", "约会", "日常"],
        "forbidden": ["超长甲", "豹纹", "夸张拼色", "大面积金属链条"],
    },
    "pure_desire": {
        "style_code": "A",
        "name": "韩系纯欲",
        "merchant_position": "韩系纯欲 / 白月光氛围 / 约会显白",
        "keywords": ["纯欲", "韩系", "白月光", "显白", "约会", "清透"],
        "target_audiences": ["大学生", "白领女生", "约会人群", "内容博主"],
        "primary_styles": {"韩系纯欲": 0.36, "白月光": 0.24, "温柔奶系": 0.2, "约会氛围": 0.12, "清透高级": 0.08},
        "secondary_styles": {"温柔": 0.32, "约会": 0.24, "清透": 0.18, "少女感": 0.14, "拍照": 0.12},
        "primary_colors": {"裸粉": 0.28, "奶白": 0.22, "透明色": 0.18, "豆沙": 0.16, "浅紫": 0.08, "冰透蓝": 0.08},
        "support_techniques": ["细闪法式", "局部贴钻", "珍珠法式", "细银边"],
        "elements": ["小蝴蝶结", "小钻", "珍珠", "爱心"],
        "occasions": ["约会", "春夏", "拍照", "通勤"],
        "forbidden": ["暗黑哥特", "粗重金属", "超尖甲"],
    },
    "sweet_girl": {
        "style_code": "B",
        "name": "甜美少女",
        "merchant_position": "甜美少女 / 奶油果冻 / 可爱氛围",
        "keywords": ["甜美", "少女", "奶油", "果冻", "樱花", "蝴蝶结"],
        "target_audiences": ["学生党", "甜妹", "生日约会人群", "拍照人群"],
        "primary_styles": {"甜美少女": 0.34, "奶油果冻": 0.24, "蜜桃甜心": 0.18, "樱花公主": 0.14, "可爱拍照": 0.1},
        "secondary_styles": {"少女感": 0.3, "元气": 0.22, "约会": 0.2, "节日": 0.16, "可爱": 0.12},
        "elements": ["蝴蝶结", "爱心", "草莓", "小珍珠", "小钻"],
        "occasions": ["生日", "约会", "春夏", "拍照", "节日"],
        "forbidden": ["大面积黑银", "超长尖甲", "哥特元素"],
    },
    "pastoral_garden": {
        "style_code": "B",
        "name": "田园花卉",
        "merchant_position": "田园花卉 / 清新自然 / 轻法式甜美",
        "keywords": ["田园", "花卉", "雏菊", "清新", "自然", "草地"],
        "target_audiences": ["春夏出游人群", "文艺女生", "新客尝鲜人群", "轻婚礼人群"],
        "primary_styles": {"田园花卉": 0.34, "自然清新": 0.24, "法式花园": 0.18, "森系轻甜": 0.14, "度假感": 0.1},
        "secondary_styles": {"清新": 0.28, "春夏": 0.24, "文艺": 0.2, "约会": 0.16, "旅行": 0.12},
        "primary_colors": {"奶白": 0.2, "薄荷绿": 0.18, "樱花粉": 0.18, "奶黄": 0.16, "透明色": 0.14, "牛油果绿": 0.14},
        "support_techniques": ["花朵手绘", "细法式", "贝壳点缀", "局部小钻"],
        "elements": ["雏菊", "叶子", "蝴蝶", "樱花", "小珍珠"],
        "occasions": ["春夏", "旅行", "拍照", "约会"],
        "forbidden": ["重金属镜面", "夜店风", "大面积黑色"],
    },
    "rich_girl": {
        "style_code": "C",
        "name": "千金轻奢",
        "merchant_position": "千金轻奢 / 珠宝法式 / 精致贵气",
        "keywords": ["千金", "轻奢", "珍珠", "法式", "贵气", "精致"],
        "target_audiences": ["高客单白领", "聚会人群", "婚礼宾客", "内容拍照人群"],
        "primary_styles": {"千金轻奢": 0.34, "珠宝法式": 0.24, "精致贵气": 0.18, "香槟奶白": 0.14, "高光名媛": 0.1},
        "secondary_styles": {"贵气": 0.28, "拍照": 0.22, "聚会": 0.2, "婚礼": 0.18, "轻奢": 0.12},
        "primary_colors": {"奶白": 0.22, "珍珠白": 0.2, "香槟金": 0.18, "玫瑰金": 0.14, "酒红": 0.14, "银色": 0.12},
        "elements": ["珍珠", "碎钻", "金边", "金属蝴蝶"],
        "occasions": ["聚会", "婚礼", "拍照", "节日"],
        "forbidden": ["低幼卡通", "高饱和拼色"],
    },
    "old_money": {
        "style_code": "C",
        "name": "老钱贵气",
        "merchant_position": "老钱贵气 / 克制高级 / 酒红奶白",
        "keywords": ["老钱", "贵气", "克制", "奶白", "酒红", "高级感"],
        "target_audiences": ["成熟白领", "商务女性", "高净值客群", "晚宴人群"],
        "primary_styles": {"老钱贵气": 0.36, "克制高级": 0.22, "奶白酒红": 0.18, "冷静珠光": 0.14, "名媛晚宴": 0.1},
        "secondary_styles": {"高级": 0.28, "成熟": 0.24, "商务": 0.18, "晚宴": 0.16, "秋冬": 0.14},
        "primary_colors": {"酒红": 0.24, "奶白": 0.22, "香槟金": 0.18, "咖棕": 0.14, "黑色": 0.12, "银色": 0.1},
        "support_techniques": ["金边法式", "珠光", "细排钻", "液态金属"],
        "elements": ["珍珠", "金边", "碎钻", "链条"],
        "occasions": ["晚宴", "商务", "秋冬", "节日"],
        "forbidden": ["过于甜美的蝴蝶结", "多巴胺撞色", "低龄卡通"],
    },
    "queen_sister": {
        "style_code": "D",
        "name": "御姐冷艳",
        "merchant_position": "御姐冷艳 / 酒红冷灰 / 强气场",
        "keywords": ["御姐", "冷艳", "酒红", "冷灰", "强气场", "酷飒"],
        "target_audiences": ["都市白领", "拍照客群", "夜生活人群", "秋冬人群"],
        "primary_styles": {"御姐冷艳": 0.36, "酒红冷灰": 0.22, "强气场": 0.18, "酷飒成熟": 0.14, "夜色高级": 0.1},
        "secondary_styles": {"酷飒": 0.3, "成熟": 0.24, "秋冬": 0.18, "拍照": 0.16, "夜店": 0.12},
        "primary_colors": {"酒红": 0.24, "冷灰": 0.22, "黑色": 0.18, "银色": 0.14, "深蓝": 0.12, "紫黑": 0.1},
        "elements": ["链条", "金属蝴蝶", "小钻", "十字架"],
        "occasions": ["秋冬", "聚会", "夜店", "拍照"],
        "forbidden": ["奶油甜妹", "低龄蝴蝶结", "大面积果冻粉"],
    },
    "dark_goth": {
        "style_code": "D",
        "name": "暗黑甜酷",
        "merchant_position": "暗黑甜酷 / 哥特镜面 / Y2K 夜色",
        "keywords": ["暗黑", "甜酷", "哥特", "镜面", "Y2K", "夜色"],
        "target_audiences": ["辣妹客群", "夜店人群", "音乐节人群", "内容拍照人群"],
        "primary_styles": {"暗黑甜酷": 0.34, "哥特镜面": 0.24, "Y2K 夜色": 0.18, "黑银金属": 0.14, "火焰辣妹": 0.1},
        "secondary_styles": {"夜店": 0.28, "辣妹": 0.24, "拍照": 0.18, "高反差": 0.16, "节日": 0.14},
        "support_techniques": ["火焰法式", "金属边线", "链条点缀", "豹纹局部"],
        "elements": ["十字架", "链条", "豹纹", "铆钉", "爱心"],
        "occasions": ["夜店", "音乐节", "拍照", "聚会"],
        "forbidden": ["极简通勤", "田园花朵", "奶白纯欲"],
    },
    "color_block": {
        "style_code": "E",
        "name": "拼色实验",
        "merchant_position": "拼色实验 / 设计感强 / 色块表达",
        "keywords": ["拼色", "撞色", "设计感", "色块", "实验", "先锋"],
        "target_audiences": ["内容博主", "拍照客群", "设计师", "年轻潮流人群"],
        "primary_styles": {"拼色实验": 0.34, "设计感色块": 0.22, "先锋撞色": 0.18, "几何解构": 0.16, "潮流拍照": 0.1},
        "secondary_styles": {"艺术感": 0.26, "拍照": 0.22, "先锋": 0.2, "夏季": 0.16, "内容种草": 0.16},
        "primary_colors": {"多巴胺橘": 0.2, "冰透蓝": 0.18, "牛油果绿": 0.16, "霓虹粉": 0.16, "奶白": 0.16, "银色": 0.14},
        "support_techniques": ["线条艺术", "异形拼贴", "液态金属", "局部小钻"],
        "elements": ["几何拼贴", "异形金属", "星月", "水滴"],
        "occasions": ["拍照", "旅行", "节日", "内容种草"],
        "forbidden": ["过于保守单色", "传统婚礼款"],
    },
    "dopamine_pop": {
        "style_code": "E",
        "name": "多巴胺潮玩",
        "merchant_position": "多巴胺潮玩 / 高彩度 / 平台热点融合",
        "keywords": ["多巴胺", "潮玩", "高彩度", "夏日", "热点", "活力"],
        "target_audiences": ["学生党", "假日出游人群", "内容平台种草人群", "拍照客群"],
        "primary_styles": {"多巴胺潮玩": 0.34, "夏日热点": 0.22, "果冻撞色": 0.18, "平台同款": 0.16, "活力拍照": 0.1},
        "secondary_styles": {"夏季": 0.28, "活力": 0.24, "拍照": 0.18, "旅行": 0.16, "节日": 0.14},
        "primary_colors": {"霓虹粉": 0.18, "多巴胺橘": 0.18, "海盐蓝": 0.16, "牛油果绿": 0.16, "奶黄": 0.16, "透明色": 0.16},
        "elements": ["星月", "小蝴蝶", "贝壳", "水滴", "几何拼贴"],
        "occasions": ["夏季", "旅行", "拍照", "节日"],
        "forbidden": ["老钱克制风", "深秋暗黑主调"],
    },
    "minimal_clear": {
        "style_code": "A",
        "name": "简约清透",
        "merchant_position": "简约清透 / 透明水光 / 日常高级",
        "keywords": ["简约", "清透", "透明", "水光", "高级", "不挑人"],
        "target_audiences": ["新客尝鲜人群", "通勤人群", "极简审美人群", "短甲人群"],
        "primary_styles": {"简约清透": 0.36, "透明水光": 0.24, "日常高级": 0.18, "极简耐看": 0.14, "显手白": 0.08},
        "secondary_styles": {"清透": 0.3, "日常": 0.24, "高级": 0.18, "不挑人": 0.16, "通勤": 0.12},
        "primary_colors": {"透明色": 0.24, "奶白": 0.22, "裸粉": 0.2, "豆沙": 0.14, "冰透蓝": 0.1, "浅紫": 0.1},
        "support_techniques": ["微闪", "细法式", "局部珍珠", "裸透渐变"],
        "elements": ["珍珠", "小钻", "贝壳"],
        "occasions": ["日常", "通勤", "春夏", "拍照"],
        "forbidden": ["重工满钻", "大面积拼色", "超长甲"],
    },
    "bridal_french": {
        "style_code": "C",
        "name": "新娘法式",
        "merchant_position": "新娘法式 / 奶白珍珠 / 仪式感婚礼",
        "keywords": ["新娘", "法式", "婚礼", "珍珠", "奶白", "仪式感"],
        "target_audiences": ["新娘客群", "伴娘人群", "订婚拍摄人群", "婚礼试妆人群"],
        "primary_styles": {"新娘法式": 0.38, "婚礼奶白": 0.24, "珍珠仪式感": 0.18, "轻奢白纱": 0.12, "法式婚甲": 0.08},
        "secondary_styles": {"婚礼": 0.34, "仪式感": 0.22, "优雅": 0.18, "拍照": 0.14, "春夏": 0.12},
        "primary_colors": {"奶白": 0.32, "珍珠白": 0.26, "裸粉": 0.18, "香槟金": 0.14, "银色": 0.1},
        "support_techniques": ["珍珠法式", "细闪法式", "局部排钻", "薄纱晕染"],
        "elements": ["珍珠", "蝴蝶结", "小钻", "金边"],
        "occasions": ["婚礼", "订婚", "拍照", "春夏"],
        "forbidden": ["高饱和撞色", "夜店暗黑", "重金属链条"],
    },
    "chinese_chic": {
        "style_code": "C",
        "name": "新中式国风",
        "merchant_position": "新中式国风 / 玉石花窗 / 红金雅致",
        "keywords": ["国风", "新中式", "玉石", "青花", "红金", "山茶花"],
        "target_audiences": ["节日客群", "婚礼宾客", "国风拍照人群", "轻熟白领"],
        "primary_styles": {"新中式国风": 0.36, "玉石红金": 0.22, "东方雅致": 0.18, "青花雅韵": 0.14, "节日国风": 0.1},
        "secondary_styles": {"节日": 0.26, "东方": 0.24, "贵气": 0.18, "拍照": 0.16, "秋冬": 0.16},
        "primary_colors": {"酒红": 0.24, "奶白": 0.18, "墨绿": 0.16, "香槟金": 0.16, "青花蓝": 0.14, "黑色": 0.12},
        "support_techniques": ["金边法式", "水墨手绘", "玉石晕染", "局部排钻"],
        "elements": ["山茶花", "祥云", "玉石", "金边", "小珍珠"],
        "occasions": ["节日", "婚礼", "秋冬", "拍照"],
        "forbidden": ["霓虹多巴胺", "低幼卡通", "欧美豹纹"],
    },
    "japanese_editorial": {
        "style_code": "A",
        "name": "日杂轻熟",
        "merchant_position": "日杂轻熟 / 奶茶雾感 / 轻文艺通勤",
        "keywords": ["日杂", "轻熟", "奶茶", "雾感", "文艺", "耐看"],
        "target_audiences": ["轻熟白领", "文艺女生", "通勤客群", "摄影博主"],
        "primary_styles": {"日杂轻熟": 0.36, "奶茶雾感": 0.22, "轻文艺": 0.18, "温柔耐看": 0.14, "低调拍照": 0.1},
        "secondary_styles": {"轻熟": 0.28, "文艺": 0.24, "通勤": 0.18, "秋冬": 0.16, "日常": 0.14},
        "primary_colors": {"奶茶": 0.24, "豆沙": 0.2, "雾灰": 0.16, "奶白": 0.14, "咖棕": 0.14, "浅紫": 0.12},
        "support_techniques": ["雾面封层", "细法式", "裸透渐变", "局部贝壳"],
        "elements": ["小珍珠", "贝壳", "小钻", "叶子"],
        "occasions": ["通勤", "秋冬", "日常", "拍照"],
        "forbidden": ["高对比撞色", "哥特暗黑", "重工满钻"],
    },
    "french_vintage": {
        "style_code": "C",
        "name": "法式复古",
        "merchant_position": "法式复古 / 酒红奶油 / 轻宫廷感",
        "keywords": ["法式复古", "宫廷", "酒红", "奶油", "玫瑰", "复古感"],
        "target_audiences": ["成熟白领", "复古审美人群", "下午茶拍照人群", "秋冬客群"],
        "primary_styles": {"法式复古": 0.36, "酒红奶油": 0.22, "轻宫廷感": 0.18, "玫瑰复古": 0.14, "奶金法式": 0.1},
        "secondary_styles": {"复古": 0.3, "秋冬": 0.22, "优雅": 0.18, "拍照": 0.16, "约会": 0.14},
        "primary_colors": {"酒红": 0.26, "奶白": 0.18, "玫瑰金": 0.16, "咖棕": 0.14, "黑色": 0.14, "香槟金": 0.12},
        "support_techniques": ["玫瑰手绘", "金边法式", "珠光晕染", "细排钻"],
        "elements": ["玫瑰", "金边", "珍珠", "链条"],
        "occasions": ["秋冬", "约会", "拍照", "聚会"],
        "forbidden": ["多巴胺彩色", "极简透明", "低幼可爱风"],
    },
    "y2k_trend": {
        "style_code": "E",
        "name": "Y2K 潮酷",
        "merchant_position": "Y2K 潮酷 / 果冻镜面 / 平台同款",
        "keywords": ["Y2K", "潮酷", "镜面", "果冻", "平台同款", "辣妹"],
        "target_audiences": ["年轻潮流女生", "拍照客群", "内容平台种草人群", "派对人群"],
        "primary_styles": {"Y2K 潮酷": 0.36, "平台同款": 0.22, "果冻镜面": 0.18, "辣妹未来感": 0.14, "闪亮拍照": 0.1},
        "secondary_styles": {"拍照": 0.26, "辣妹": 0.22, "节日": 0.18, "夏季": 0.18, "先锋": 0.16},
        "primary_colors": {"银色": 0.18, "霓虹粉": 0.18, "冰透蓝": 0.16, "紫色": 0.16, "黑色": 0.16, "透明色": 0.16},
        "support_techniques": ["镜面金属", "果冻晕染", "星月贴饰", "液态金属"],
        "elements": ["星月", "金属蝴蝶", "水滴", "几何拼贴", "小钻"],
        "occasions": ["拍照", "节日", "派对", "夏季"],
        "forbidden": ["老钱克制风", "传统婚礼奶白"],
    },
    "sweet_cool": {
        "style_code": "D",
        "name": "甜酷辣妹",
        "merchant_position": "甜酷辣妹 / 黑粉银紫 / 高反差张力",
        "keywords": ["甜酷", "辣妹", "黑粉", "高反差", "张力", "酷感"],
        "target_audiences": ["辣妹客群", "夜生活女生", "拍照人群", "音乐节人群"],
        "primary_styles": {"甜酷辣妹": 0.38, "黑粉高反差": 0.22, "银紫酷感": 0.16, "夜色甜辣": 0.14, "派对焦点": 0.1},
        "secondary_styles": {"辣妹": 0.28, "拍照": 0.24, "派对": 0.18, "节日": 0.16, "夜店": 0.14},
        "primary_colors": {"黑色": 0.2, "霓虹粉": 0.18, "紫色": 0.16, "银色": 0.16, "酒红": 0.16, "冰蓝": 0.14},
        "support_techniques": ["火焰法式", "局部贴钻", "金属边线", "链条点缀"],
        "elements": ["爱心", "链条", "小钻", "金属蝴蝶", "豹纹"],
        "occasions": ["夜店", "拍照", "节日", "派对"],
        "forbidden": ["极简通勤", "田园花卉", "低饱和奶茶"],
    },
    "clean_girl": {
        "style_code": "A",
        "name": "Clean Girl",
        "merchant_position": "Clean Girl / 玻璃裸粉 / 清爽精致",
        "keywords": ["clean girl", "玻璃感", "裸粉", "清爽", "精致", "白开水风"],
        "target_audiences": ["都市白领", "健身博主", "新客尝鲜人群", "极简审美人群"],
        "primary_styles": {"Clean Girl": 0.38, "玻璃裸粉": 0.22, "白开水风": 0.18, "低调精致": 0.12, "清爽高级": 0.1},
        "secondary_styles": {"清爽": 0.28, "通勤": 0.22, "极简": 0.18, "拍照": 0.16, "不挑人": 0.16},
        "primary_colors": {"裸粉": 0.28, "透明色": 0.22, "奶白": 0.18, "豆沙": 0.14, "浅紫": 0.1, "香槟金": 0.08},
        "support_techniques": ["玻璃光封层", "裸透渐变", "局部珍珠", "细法式"],
        "elements": ["珍珠", "小钻", "贝壳"],
        "occasions": ["通勤", "健身", "拍照", "日常"],
        "forbidden": ["重工满钻", "夜店金属", "多巴胺撞色"],
    },
}


@dataclass
class MerchantAccount:
    username: str
    password_hash: str
    shop_id: str
    shop_name: str
    display_name: str
    role: str = "merchant"
    enabled_for_portal: int = 1


def _ensure_table_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def ensure_merchant_data_schema(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS merchant_accounts (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            shop_id TEXT NOT NULL,
            shop_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'merchant',
            enabled_for_portal INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS merchant_profiles (
            shop_id TEXT PRIMARY KEY,
            shop_name TEXT NOT NULL,
            city TEXT NOT NULL,
            district TEXT NOT NULL,
            style TEXT NOT NULL,
            style_name TEXT NOT NULL,
            style_persona_id TEXT NOT NULL DEFAULT '',
            style_persona_name TEXT NOT NULL DEFAULT '',
            style_keywords TEXT NOT NULL DEFAULT '[]',
            target_audiences TEXT NOT NULL DEFAULT '[]',
            rating REAL NOT NULL,
            review_count INTEGER NOT NULL,
            avg_ticket INTEGER NOT NULL,
            monthly_revenue INTEGER NOT NULL,
            repeat_customer_rate REAL NOT NULL,
            refund_rate REAL NOT NULL,
            complaint_rate REAL NOT NULL,
            store_status TEXT NOT NULL,
            hero_sku_id TEXT,
            hero_sku_name TEXT,
            owner_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS merchant_style_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id TEXT NOT NULL,
            style_id TEXT NOT NULL,
            style_name TEXT NOT NULL,
            category TEXT NOT NULL,
            price INTEGER NOT NULL,
            cost INTEGER NOT NULL,
            duration_minutes INTEGER NOT NULL,
            search_volume_30d INTEGER NOT NULL,
            click_volume_30d INTEGER NOT NULL,
            cart_volume_30d INTEGER NOT NULL,
            group_buy_orders_30d INTEGER NOT NULL,
            ctr REAL NOT NULL,
            conversion_rate REAL NOT NULL,
            refund_orders_30d INTEGER NOT NULL,
            favorite_count_30d INTEGER NOT NULL,
            share_count_30d INTEGER NOT NULL,
            impression_volume_30d INTEGER NOT NULL,
            cpc REAL NOT NULL,
            gmv_30d INTEGER NOT NULL,
            inventory_status TEXT NOT NULL,
            launch_stage TEXT NOT NULL,
            trend_signal TEXT NOT NULL,
            title_tags TEXT NOT NULL,
            style_persona_id TEXT NOT NULL DEFAULT '',
            style_persona_name TEXT NOT NULL DEFAULT '',
            primary_style TEXT NOT NULL DEFAULT '',
            secondary_style TEXT NOT NULL DEFAULT '',
            nail_shape TEXT NOT NULL DEFAULT '',
            nail_length TEXT NOT NULL DEFAULT '',
            primary_color TEXT NOT NULL DEFAULT '',
            accent_colors TEXT NOT NULL DEFAULT '[]',
            transparency TEXT NOT NULL DEFAULT '',
            texture_finish TEXT NOT NULL DEFAULT '',
            base_coat TEXT NOT NULL DEFAULT '',
            core_techniques TEXT NOT NULL DEFAULT '[]',
            support_techniques TEXT NOT NULL DEFAULT '[]',
            element_tags TEXT NOT NULL DEFAULT '[]',
            occasion_tags TEXT NOT NULL DEFAULT '[]',
            complexity_tier TEXT NOT NULL DEFAULT '',
            merchant_generation_mode TEXT NOT NULL DEFAULT 'safe',
            design_prompt TEXT NOT NULL DEFAULT '',
            style_image_url TEXT NOT NULL DEFAULT '',
            style_image_prompt TEXT NOT NULL DEFAULT '',
            style_image_status TEXT NOT NULL DEFAULT 'not_requested',
            style_image_error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_merchant_style_shop ON merchant_style_catalog(shop_id);

        CREATE TABLE IF NOT EXISTS merchant_shop_daily_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id TEXT NOT NULL,
            date TEXT NOT NULL,
            search_volume INTEGER NOT NULL,
            click_volume INTEGER NOT NULL,
            consultation_volume INTEGER NOT NULL,
            group_buy_orders INTEGER NOT NULL,
            revenue INTEGER NOT NULL,
            ad_spend INTEGER NOT NULL,
            repeat_orders INTEGER NOT NULL,
            refund_orders INTEGER NOT NULL,
            favorites_added INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_merchant_daily_shop_date ON merchant_shop_daily_metrics(shop_id, date DESC);

        CREATE TABLE IF NOT EXISTS merchant_style_daily_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id TEXT NOT NULL,
            style_id TEXT NOT NULL,
            date TEXT NOT NULL,
            search_volume INTEGER NOT NULL,
            click_volume INTEGER NOT NULL,
            group_buy_orders INTEGER NOT NULL,
            favorites_added INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_merchant_style_daily_shop_style_date ON merchant_style_daily_metrics(shop_id, style_id, date DESC);
        """
    )
    _ensure_table_columns(conn, "merchant_style_catalog", {
        "style_persona_id": "TEXT NOT NULL DEFAULT ''",
        "style_persona_name": "TEXT NOT NULL DEFAULT ''",
        "primary_style": "TEXT NOT NULL DEFAULT ''",
        "secondary_style": "TEXT NOT NULL DEFAULT ''",
        "nail_shape": "TEXT NOT NULL DEFAULT ''",
        "nail_length": "TEXT NOT NULL DEFAULT ''",
        "primary_color": "TEXT NOT NULL DEFAULT ''",
        "accent_colors": "TEXT NOT NULL DEFAULT '[]'",
        "transparency": "TEXT NOT NULL DEFAULT ''",
        "texture_finish": "TEXT NOT NULL DEFAULT ''",
        "base_coat": "TEXT NOT NULL DEFAULT ''",
        "core_techniques": "TEXT NOT NULL DEFAULT '[]'",
        "support_techniques": "TEXT NOT NULL DEFAULT '[]'",
        "element_tags": "TEXT NOT NULL DEFAULT '[]'",
        "occasion_tags": "TEXT NOT NULL DEFAULT '[]'",
        "complexity_tier": "TEXT NOT NULL DEFAULT ''",
        "merchant_generation_mode": "TEXT NOT NULL DEFAULT 'safe'",
        "design_prompt": "TEXT NOT NULL DEFAULT ''",
        "style_image_url": "TEXT NOT NULL DEFAULT ''",
        "style_image_prompt": "TEXT NOT NULL DEFAULT ''",
        "style_image_status": "TEXT NOT NULL DEFAULT 'not_requested'",
        "style_image_error": "TEXT NOT NULL DEFAULT ''",
    })
    _ensure_table_columns(conn, "merchant_profiles", {
        "style_persona_id": "TEXT NOT NULL DEFAULT ''",
        "style_persona_name": "TEXT NOT NULL DEFAULT ''",
        "style_keywords": "TEXT NOT NULL DEFAULT '[]'",
        "target_audiences": "TEXT NOT NULL DEFAULT '[]'",
    })
    conn.commit()
    conn.close()


def generate_merchant_dataset_skill(
    base_dir: str,
    merchant_count: int = 1000,
    min_styles_per_shop: int = 18,
    max_styles_per_shop: int = 36,
    days: int = 30,
    seed: int = 20260606,
    replace_existing: bool = True,
    enable_portal_accounts: bool = True,
    style_generation_mode: str = "mixed",
    generate_style_images: bool = False,
    style_image_limit: int = 0,
    style_images_per_shop: int = 1,
) -> dict[str, Any]:
    safe_count = max(1, min(int(merchant_count or 1000), 5000))
    min_styles = max(8, min(int(min_styles_per_shop or 18), 80))
    max_styles = max(min_styles, min(int(max_styles_per_shop or 36), 120))
    safe_days = max(7, min(int(days or 30), 180))
    safe_mode = str(style_generation_mode or "mixed").strip().lower()
    if safe_mode not in {"safe", "innovate", "trend", "mixed"}:
        safe_mode = "mixed"
    image_limit = max(0, min(int(style_image_limit or 0), 400))
    per_shop_image_limit = max(0, min(int(style_images_per_shop or 1), 6))
    image_generation_enabled = bool(generate_style_images and image_limit > 0 and per_shop_image_limit > 0)

    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "jiaqu.db")
    os.makedirs(os.path.join(base_dir, "static", STYLE_IMAGE_DIRNAME), exist_ok=True)
    ensure_merchant_data_schema(db_path)

    rng = random.Random(seed)
    now = datetime.now(BJT)
    created_at = now.isoformat()
    conn = sqlite3.connect(db_path)

    if replace_existing:
        conn.execute("DELETE FROM merchant_accounts")
        conn.execute("DELETE FROM merchant_profiles")
        conn.execute("DELETE FROM merchant_style_catalog")
        conn.execute("DELETE FROM merchant_shop_daily_metrics")
        conn.execute("DELETE FROM merchant_style_daily_metrics")

    profiles = []
    style_rows = []
    shop_daily_rows = []
    style_daily_rows = []
    accounts = []
    sample_accounts = []
    generated_style_images = 0
    style_image_failures = 0
    style_image_skipped = 0

    for index in range(1, safe_count + 1):
        shop_id = f"m_shop_{index:04d}"
        persona = _pick_style_persona(rng)
        style = str(persona["style_code"])
        city = rng.choice(list(CITY_DISTRICTS.keys()))
        district = rng.choice(CITY_DISTRICTS[city])
        shop_name = _build_shop_name(rng, district)
        rating = round(rng.uniform(4.1, 4.95), 1)
        review_count = rng.randint(60, 4200)
        avg_ticket = _category_ticket(style, rng)
        repeat_rate = round(rng.uniform(0.18, 0.62), 3)
        refund_rate = round(rng.uniform(0.01, 0.09), 3)
        complaint_rate = round(rng.uniform(0.002, 0.03), 3)
        owner_name = f"{district}店主"
        style_count = rng.randint(min_styles, max_styles)
        skus = _build_shop_styles(rng, shop_id, style, style_count, created_at, generation_mode=safe_mode, persona=persona)
        if image_generation_enabled:
            remaining = max(0, image_limit - generated_style_images)
            if remaining:
                image_stats = _attach_style_images_to_shop(
                    base_dir=base_dir,
                    rng=rng,
                    shop_name=shop_name,
                    shop_style_code=style,
                    styles=skus,
                    max_images=min(per_shop_image_limit, remaining),
                )
                generated_style_images += int(image_stats.get("generated", 0))
                style_image_failures += int(image_stats.get("failed", 0))
                style_image_skipped += int(image_stats.get("skipped", 0))

        total_revenue = sum(item["gmv_30d"] for item in skus)
        hero = max(skus, key=lambda item: (item["group_buy_orders_30d"], item["click_volume_30d"]))

        profiles.append((
            shop_id, shop_name, city, district, style, _style_name(style), persona["persona_id"], persona["name"],
            json.dumps(persona["keywords"], ensure_ascii=False), json.dumps(persona["target_audiences"], ensure_ascii=False), rating, review_count,
            avg_ticket, total_revenue, repeat_rate, refund_rate, complaint_rate, "active",
            hero["style_id"], hero["style_name"], owner_name, created_at, created_at,
        ))
        style_rows.extend([
            (
                item["shop_id"], item["style_id"], item["style_name"], item["category"], item["price"], item["cost"],
                item["duration_minutes"], item["search_volume_30d"], item["click_volume_30d"], item["cart_volume_30d"],
                item["group_buy_orders_30d"], item["ctr"], item["conversion_rate"], item["refund_orders_30d"],
                item["favorite_count_30d"], item["share_count_30d"], item["impression_volume_30d"], item["cpc"],
                item["gmv_30d"], item["inventory_status"], item["launch_stage"], item["trend_signal"],
                json.dumps(item["title_tags"], ensure_ascii=False),
                item["style_persona_id"],
                item["style_persona_name"],
                item["primary_style"],
                item["secondary_style"],
                item["nail_shape"],
                item["nail_length"],
                item["primary_color"],
                json.dumps(item["accent_colors"], ensure_ascii=False),
                item["transparency"],
                item["texture_finish"],
                item["base_coat"],
                json.dumps(item["core_techniques"], ensure_ascii=False),
                json.dumps(item["support_techniques"], ensure_ascii=False),
                json.dumps(item["element_tags"], ensure_ascii=False),
                json.dumps(item["occasion_tags"], ensure_ascii=False),
                item["complexity_tier"],
                item["merchant_generation_mode"],
                item["design_prompt"],
                item["style_image_url"],
                item["style_image_prompt"],
                item["style_image_status"],
                item["style_image_error"],
                created_at,
                created_at,
            )
            for item in skus
        ])

        shop_daily_rows.extend(_build_shop_daily_rows(rng, shop_id, total_revenue, safe_days, created_at))
        style_daily_rows.extend(_build_style_daily_rows(rng, skus, safe_days, created_at))

        username = f"merchant_{index:04d}"
        account = MerchantAccount(
            username=username,
            password_hash=_hash_password(DEFAULT_PASSWORD),
            shop_id=shop_id,
            shop_name=shop_name,
            display_name=f"{shop_name} 商家",
            enabled_for_portal=1 if enable_portal_accounts else 0,
        )
        accounts.append((account.username, account.password_hash, account.shop_id, account.shop_name, account.display_name, account.role, account.enabled_for_portal, created_at, created_at))
        if len(sample_accounts) < 12:
            sample_accounts.append({"username": username, "password": DEFAULT_PASSWORD, "shop_id": shop_id, "shop_name": shop_name})

    conn.executemany(
        """
        INSERT INTO merchant_profiles(
            shop_id, shop_name, city, district, style, style_name, style_persona_id, style_persona_name,
            style_keywords, target_audiences, rating, review_count, avg_ticket,
            monthly_revenue, repeat_customer_rate, refund_rate, complaint_rate, store_status,
            hero_sku_id, hero_sku_name, owner_name, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        profiles,
    )
    conn.executemany(
        """
        INSERT INTO merchant_style_catalog(
            shop_id, style_id, style_name, category, price, cost, duration_minutes, search_volume_30d,
            click_volume_30d, cart_volume_30d, group_buy_orders_30d, ctr, conversion_rate, refund_orders_30d,
            favorite_count_30d, share_count_30d, impression_volume_30d, cpc, gmv_30d, inventory_status,
            launch_stage, trend_signal, title_tags, style_persona_id, style_persona_name, primary_style, secondary_style, nail_shape, nail_length,
            primary_color, accent_colors, transparency, texture_finish, base_coat, core_techniques,
            support_techniques, element_tags, occasion_tags, complexity_tier, merchant_generation_mode,
            design_prompt, style_image_url, style_image_prompt, style_image_status, style_image_error,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        style_rows,
    )
    conn.executemany(
        """
        INSERT INTO merchant_shop_daily_metrics(
            shop_id, date, search_volume, click_volume, consultation_volume, group_buy_orders, revenue,
            ad_spend, repeat_orders, refund_orders, favorites_added, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        shop_daily_rows,
    )
    conn.executemany(
        """
        INSERT INTO merchant_style_daily_metrics(
            shop_id, style_id, date, search_volume, click_volume, group_buy_orders, favorites_added, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        style_daily_rows,
    )
    conn.executemany(
        """
        INSERT INTO merchant_accounts(
            username, password_hash, shop_id, shop_name, display_name, role, enabled_for_portal, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        accounts,
    )
    conn.commit()
    conn.close()

    summary = {
        "generated_at": created_at,
        "merchant_count": safe_count,
        "styles_total": len(style_rows),
        "style_daily_rows": len(style_daily_rows),
        "shop_daily_rows": len(shop_daily_rows),
        "portal_accounts_enabled": enable_portal_accounts,
        "style_generation_mode": safe_mode,
        "style_images_requested": image_generation_enabled,
        "style_image_limit": image_limit,
        "style_images_per_shop": per_shop_image_limit,
        "generated_style_images": generated_style_images,
        "style_image_failures": style_image_failures,
        "style_image_skipped": style_image_skipped,
        "default_password": DEFAULT_PASSWORD,
        "sample_accounts": sample_accounts,
        "tables": [
            "merchant_accounts",
            "merchant_profiles",
            "merchant_style_catalog",
            "merchant_shop_daily_metrics",
            "merchant_style_daily_metrics",
        ],
    }
    with open(os.path.join(data_dir, DATASET_SUMMARY_FILENAME), "w", encoding="utf-8") as fp:
        json.dump(summary, fp, ensure_ascii=False, indent=2)
    return summary


def get_dataset_summary(base_dir: str) -> dict[str, Any] | None:
    path = os.path.join(base_dir, "data", DATASET_SUMMARY_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def get_merchant_dataset_overview(base_dir: str) -> dict[str, Any]:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        return {
            "summary": get_dataset_summary(base_dir),
            "totals": {
                "merchants": 0,
                "styles": 0,
                "shop_daily_rows": 0,
                "style_daily_rows": 0,
                "portal_accounts": 0,
            },
            "cities": [],
            "styles": [],
        }
    ensure_merchant_data_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    style_rows = conn.execute("SELECT style_name, style_persona_name FROM merchant_profiles").fetchall()
    style_counter = Counter(
        _normalize_style_persona_name(row["style_persona_name"], row["style_name"])
        for row in style_rows
    )
    totals = {
        "merchants": conn.execute("SELECT COUNT(*) FROM merchant_profiles").fetchone()[0],
        "styles": conn.execute("SELECT COUNT(*) FROM merchant_style_catalog").fetchone()[0],
        "shop_daily_rows": conn.execute("SELECT COUNT(*) FROM merchant_shop_daily_metrics").fetchone()[0],
        "style_daily_rows": conn.execute("SELECT COUNT(*) FROM merchant_style_daily_metrics").fetchone()[0],
        "portal_accounts": conn.execute("SELECT COUNT(*) FROM merchant_accounts WHERE enabled_for_portal = 1").fetchone()[0],
        "style_personas": len(style_counter),
    }
    cities = [
        dict(row)
        for row in conn.execute(
            "SELECT city, COUNT(*) AS merchant_count FROM merchant_profiles GROUP BY city ORDER BY merchant_count DESC, city ASC"
        ).fetchall()
    ]
    styles = [
        {"style": key, "style_name": key, "merchant_count": count}
        for key, count in sorted(style_counter.items(), key=lambda item: (-item[1], item[0]))
    ]
    conn.close()
    return {
        "summary": get_dataset_summary(base_dir),
        "totals": totals,
        "cities": cities,
        "styles": styles,
    }


def list_generated_merchants(
    base_dir: str,
    page: int = 1,
    page_size: int = 24,
    query: str = "",
    city: str = "",
    style: str = "",
) -> dict[str, Any]:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        return {"items": [], "page": 1, "page_size": 24, "total": 0}
    ensure_merchant_data_schema(db_path)
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 24), 100))
    safe_query = str(query or "").strip()
    safe_city = str(city or "").strip()
    safe_style = str(style or "").strip()

    where = []
    params: list[Any] = []
    if safe_query:
        where.append("(p.shop_id LIKE ? OR p.shop_name LIKE ? OR COALESCE(a.username, '') LIKE ?)")
        keyword = f"%{safe_query}%"
        params.extend([keyword, keyword, keyword])
    if safe_city:
        where.append("p.city = ?")
        params.append(safe_city)
    if safe_style:
        legacy_aliases = [legacy for legacy, normalized in LEGACY_STYLE_PERSONA_MAP.items() if normalized == safe_style]
        style_clauses = ["p.style = ?", "p.style_name = ?", "p.style_persona_name = ?"]
        style_params: list[Any] = [safe_style, safe_style, safe_style]
        for legacy in legacy_aliases:
            style_clauses.append("p.style_name = ?")
            style_params.append(legacy)
        where.append(f"({' OR '.join(style_clauses)})")
        params.extend(style_params)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    total = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM merchant_profiles p
        LEFT JOIN (
            SELECT shop_id, MIN(username) AS username, MAX(enabled_for_portal) AS enabled_for_portal
            FROM merchant_accounts
            GROUP BY shop_id
        ) a ON a.shop_id = p.shop_id
        {where_sql}
        """,
        params,
    ).fetchone()[0]

    rows = conn.execute(
        f"""
        SELECT
            p.shop_id,
            p.shop_name,
            p.city,
            p.district,
            p.style,
            p.style_name,
            p.style_persona_name,
            p.rating,
            p.review_count,
            p.avg_ticket,
            p.monthly_revenue,
            p.repeat_customer_rate,
            p.refund_rate,
            p.complaint_rate,
            p.hero_sku_name,
            COALESCE(a.username, '') AS username,
            COALESCE(a.enabled_for_portal, 0) AS enabled_for_portal,
            COALESCE(stats.style_count, 0) AS style_count,
            COALESCE(stats.search_volume_30d, 0) AS search_volume_30d,
            COALESCE(stats.click_volume_30d, 0) AS click_volume_30d,
            COALESCE(stats.group_buy_orders_30d, 0) AS group_buy_orders_30d,
            COALESCE(stats.gmv_30d, 0) AS gmv_30d,
            COALESCE(stats.avg_ctr, 0) AS avg_ctr,
            COALESCE(stats.avg_conversion_rate, 0) AS avg_conversion_rate
        FROM merchant_profiles p
        LEFT JOIN (
            SELECT shop_id, MIN(username) AS username, MAX(enabled_for_portal) AS enabled_for_portal
            FROM merchant_accounts
            GROUP BY shop_id
        ) a ON a.shop_id = p.shop_id
        LEFT JOIN (
            SELECT
                shop_id,
                COUNT(*) AS style_count,
                SUM(search_volume_30d) AS search_volume_30d,
                SUM(click_volume_30d) AS click_volume_30d,
                SUM(group_buy_orders_30d) AS group_buy_orders_30d,
                SUM(gmv_30d) AS gmv_30d,
                AVG(ctr) AS avg_ctr,
                AVG(conversion_rate) AS avg_conversion_rate
            FROM merchant_style_catalog
            GROUP BY shop_id
        ) stats ON stats.shop_id = p.shop_id
        {where_sql}
        ORDER BY p.monthly_revenue DESC, p.rating DESC, p.shop_id ASC
        LIMIT ? OFFSET ?
        """,
        [*params, safe_page_size, (safe_page - 1) * safe_page_size],
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["style_persona_name"] = _normalize_style_persona_name(item.get("style_persona_name"), item.get("style_name"))
        items.append(item)
    conn.close()
    return {
        "items": items,
        "page": safe_page,
        "page_size": safe_page_size,
        "total": int(total),
    }


def get_generated_merchant_detail(
    base_dir: str,
    shop_id: str,
    style_limit: int = 16,
    daily_limit: int = 14,
) -> dict[str, Any] | None:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        return None
    ensure_merchant_data_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    profile = conn.execute(
        """
        SELECT shop_id, shop_name, city, district, style, style_name, rating, review_count, avg_ticket,
               style_persona_id, style_persona_name, style_keywords, target_audiences,
               monthly_revenue, repeat_customer_rate, refund_rate, complaint_rate, store_status,
               hero_sku_id, hero_sku_name, owner_name, created_at, updated_at
        FROM merchant_profiles
        WHERE shop_id = ?
        """,
        (str(shop_id or "").strip(),),
    ).fetchone()
    if not profile:
        conn.close()
        return None

    account = conn.execute(
        """
        SELECT username, shop_id, shop_name, display_name, enabled_for_portal
        FROM merchant_accounts
        WHERE shop_id = ?
        ORDER BY username ASC
        LIMIT 1
        """,
        (shop_id,),
    ).fetchone()
    totals = conn.execute(
        """
        SELECT
            COUNT(*) AS style_count,
            COALESCE(SUM(search_volume_30d), 0) AS search_volume_30d,
            COALESCE(SUM(click_volume_30d), 0) AS click_volume_30d,
            COALESCE(SUM(cart_volume_30d), 0) AS cart_volume_30d,
            COALESCE(SUM(group_buy_orders_30d), 0) AS group_buy_orders_30d,
            COALESCE(SUM(refund_orders_30d), 0) AS refund_orders_30d,
            COALESCE(SUM(gmv_30d), 0) AS gmv_30d,
            COALESCE(AVG(ctr), 0) AS avg_ctr,
            COALESCE(AVG(conversion_rate), 0) AS avg_conversion_rate
        FROM merchant_style_catalog
        WHERE shop_id = ?
        """,
        (shop_id,),
    ).fetchone()
    top_styles = conn.execute(
        """
        SELECT style_id, style_name, category, price, duration_minutes, search_volume_30d, click_volume_30d,
               cart_volume_30d, group_buy_orders_30d, ctr, conversion_rate, refund_orders_30d,
               favorite_count_30d, share_count_30d, gmv_30d, inventory_status, launch_stage, trend_signal, title_tags,
               primary_style, secondary_style, nail_shape, nail_length, primary_color, accent_colors, transparency,
               texture_finish, base_coat, core_techniques, support_techniques, element_tags, occasion_tags,
               complexity_tier, merchant_generation_mode, design_prompt, style_image_url, style_image_prompt,
               style_image_status, style_image_error
        FROM merchant_style_catalog
        WHERE shop_id = ?
        ORDER BY group_buy_orders_30d DESC, click_volume_30d DESC, search_volume_30d DESC
        LIMIT ?
        """,
        (shop_id, max(1, min(int(style_limit or 16), 40))),
    ).fetchall()
    low_conversion_styles = conn.execute(
        """
        SELECT style_id, style_name, category, price, search_volume_30d, click_volume_30d, group_buy_orders_30d,
               ctr, conversion_rate, refund_orders_30d, trend_signal, title_tags, primary_style, secondary_style,
               nail_shape, nail_length, primary_color, accent_colors, transparency, texture_finish, base_coat,
               core_techniques, support_techniques, element_tags, occasion_tags, complexity_tier,
               merchant_generation_mode, design_prompt, style_image_url, style_image_prompt, style_image_status,
               style_image_error
        FROM merchant_style_catalog
        WHERE shop_id = ?
        ORDER BY conversion_rate ASC, click_volume_30d DESC, search_volume_30d DESC
        LIMIT 8
        """,
        (shop_id,),
    ).fetchall()
    recent_daily_metrics = conn.execute(
        """
        SELECT date, search_volume, click_volume, consultation_volume, group_buy_orders, revenue,
               ad_spend, repeat_orders, refund_orders, favorites_added
        FROM merchant_shop_daily_metrics
        WHERE shop_id = ?
        ORDER BY date DESC
        LIMIT ?
        """,
        (shop_id, max(1, min(int(daily_limit or 14), 60))),
    ).fetchall()
    conn.close()

    profile_dict = dict(profile)
    profile_dict["style_persona_name"] = _normalize_style_persona_name(
        profile_dict.get("style_persona_name"),
        profile_dict.get("style_name"),
    )
    for key in ("style_keywords", "target_audiences"):
        raw = profile_dict.get(key)
        try:
            parsed = json.loads(raw) if isinstance(raw, str) and raw.strip() else []
        except json.JSONDecodeError:
            parsed = []
        profile_dict[key] = parsed if isinstance(parsed, list) else []

    return {
        "profile": profile_dict,
        "account": dict(account) if account else None,
        "totals": dict(totals) if totals else {},
        "top_styles": [_normalize_style_row(dict(row)) for row in top_styles],
        "low_conversion_styles": [_normalize_style_row(dict(row)) for row in low_conversion_styles],
        "recent_daily_metrics": [dict(row) for row in reversed(recent_daily_metrics)],
    }


def get_merchant_workbench(base_dir: str, shop_id: str, period_days: int = 14, style_limit: int = 80) -> dict[str, Any] | None:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        return None
    ensure_merchant_data_schema(db_path)
    safe_days = max(7, min(int(period_days or 14), 90))
    safe_limit = max(12, min(int(style_limit or 80), 160))
    detail = get_generated_merchant_detail(base_dir, shop_id=shop_id, style_limit=8, daily_limit=safe_days)
    if not detail:
        return None

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    styles = conn.execute(
        """
        SELECT style_id, style_name, category, price, cost, duration_minutes, search_volume_30d, click_volume_30d,
               cart_volume_30d, group_buy_orders_30d, ctr, conversion_rate, refund_orders_30d, favorite_count_30d,
               share_count_30d, impression_volume_30d, cpc, gmv_30d, inventory_status, launch_stage, trend_signal, title_tags,
               primary_style, secondary_style, nail_shape, nail_length, primary_color, accent_colors, transparency,
               texture_finish, base_coat, core_techniques, support_techniques, element_tags, occasion_tags,
               complexity_tier, merchant_generation_mode, design_prompt, style_image_url, style_image_prompt,
               style_image_status, style_image_error
        FROM merchant_style_catalog
        WHERE shop_id = ?
        ORDER BY group_buy_orders_30d DESC, click_volume_30d DESC, search_volume_30d DESC, style_id ASC
        LIMIT ?
        """,
        (shop_id, safe_limit),
    ).fetchall()
    daily_rows = conn.execute(
        """
        SELECT date, search_volume, click_volume, consultation_volume, group_buy_orders, revenue,
               ad_spend, repeat_orders, refund_orders, favorites_added
        FROM merchant_shop_daily_metrics
        WHERE shop_id = ?
        ORDER BY date DESC
        LIMIT ?
        """,
        (shop_id, safe_days),
    ).fetchall()
    peer_rows = conn.execute(
        """
        SELECT p.shop_id, p.shop_name, p.city, p.district, p.style, p.style_name, p.style_persona_name,
               p.rating, p.review_count, p.avg_ticket
        FROM merchant_profiles p
        WHERE p.style = (SELECT style FROM merchant_profiles WHERE shop_id = ? LIMIT 1)
          AND p.shop_id != ?
        ORDER BY p.rating DESC, p.review_count DESC, p.avg_ticket DESC, p.shop_id ASC
        LIMIT 8
        """,
        (shop_id, shop_id),
    ).fetchall()
    conn.close()

    style_rows = [_normalize_style_row(dict(row)) for row in styles]
    daily = [dict(row) for row in reversed(daily_rows)]
    public_competitors = _build_public_competitors(peer_rows, detail["profile"])
    hot_styles = _pick_hot_style_rows(style_rows, limit=7)
    hot_style_ids = {str(item.get("style_id") or "").strip() for item in hot_styles}
    cold_source_rows = [item for item in style_rows if str(item.get("style_id") or "").strip() not in hot_style_ids]
    cold_styles = _pick_cold_style_rows(cold_source_rows or style_rows, limit=3)
    image_targets = _select_style_image_targets(hot_styles, cold_styles)
    return {
        "profile": detail["profile"],
        "totals": detail["totals"],
        "hot_styles": hot_styles,
        "cold_styles": cold_styles,
        "styles": style_rows,
        "public_competitors": public_competitors,
        "funnels": _build_workbench_funnels(daily, detail["totals"]),
        "recent_daily_metrics": daily,
        "style_image_targets": image_targets,
        "today_advice": _build_today_ops_advice(
            detail["profile"],
            detail["totals"],
            hot_styles,
            cold_styles,
            style_rows,
            public_competitors,
        ),
    }


def apply_merchant_style_action(
    base_dir: str,
    shop_id: str,
    style_id: str,
    action: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        raise ValueError("merchant dataset not found")
    ensure_merchant_data_schema(db_path)
    safe_style_id = str(style_id or "").strip()
    if not safe_style_id:
        raise ValueError("style_id is required")
    safe_action = str(action or "").strip()
    if safe_action not in {"promote_traffic", "set_inventory_status", "apply_ai_update"}:
        raise ValueError(f"unsupported action: {safe_action}")
    extras = payload if isinstance(payload, dict) else {}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT *
        FROM merchant_style_catalog
        WHERE shop_id = ? AND style_id = ?
        LIMIT 1
        """,
        (shop_id, safe_style_id),
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError("style not found")

    style = _normalize_style_row(dict(row))
    message = ""
    if safe_action == "promote_traffic":
        delta = _build_promotion_delta(style, extras)
        _apply_style_delta(conn, shop_id, safe_style_id, style, delta)
        message = f"已为「{style['style_name']}」追加投流，预计会优先带动搜索、点击和成交。"
    elif safe_action == "set_inventory_status":
        requested = str(extras.get("status") or "").strip().lower()
        current_status = str(style.get("inventory_status") or "active").lower()
        next_status = requested if requested in {"active", "offline"} else ("offline" if current_status == "active" else "active")
        conn.execute(
            """
            UPDATE merchant_style_catalog
            SET inventory_status = ?, launch_stage = ?, updated_at = ?
            WHERE shop_id = ? AND style_id = ?
            """,
            (next_status, "on_shelf" if next_status == "active" else "paused", datetime.now(BJT).isoformat(), shop_id, safe_style_id),
        )
        message = f"已将「{style['style_name']}」调整为{'上架' if next_status == 'active' else '下架'}状态。"
    else:
        suggestion = _build_style_ai_update(style)
        if bool(extras.get("preview_only")):
            conn.close()
            return {
                "ok": True,
                "action": safe_action,
                "message": f"已为「{style['style_name']}」生成 AI 改款方案，请确认后再应用。",
                "style": style,
                "proposal": suggestion,
                "preview_only": True,
            }
        conn.execute(
            """
            UPDATE merchant_style_catalog
            SET price = ?, launch_stage = ?, title_tags = ?, design_prompt = ?, style_image_prompt = ?,
                style_image_status = ?, style_image_error = ?, updated_at = ?
            WHERE shop_id = ? AND style_id = ?
            """,
            (
                suggestion["price"],
                suggestion["launch_stage"],
                json.dumps(suggestion["title_tags"], ensure_ascii=False),
                suggestion["design_prompt"],
                suggestion["image_prompt"],
                "needs_regeneration",
                "",
                datetime.now(BJT).isoformat(),
                shop_id,
                safe_style_id,
            ),
        )
        message = suggestion["message"]

    conn.commit()
    updated = conn.execute(
        """
        SELECT *
        FROM merchant_style_catalog
        WHERE shop_id = ? AND style_id = ?
        LIMIT 1
        """,
        (shop_id, safe_style_id),
    ).fetchone()
    conn.close()
    return {
        "ok": True,
        "action": safe_action,
        "message": message,
        "style": _normalize_style_row(dict(updated)) if updated else style,
        "proposal": suggestion if safe_action == "apply_ai_update" else None,
    }


def authenticate_merchant(base_dir: str, username: str, password: str) -> dict[str, Any] | None:
    account = _load_account(base_dir, username=username)
    if not account:
        return None
    if account["password_hash"] != _hash_password(password):
        return None
    if not int(account.get("enabled_for_portal") or 0):
        return None
    return build_merchant_identity(base_dir, account["shop_id"], username=account["username"])


def build_merchant_identity(base_dir: str, shop_id: str, username: str | None = None) -> dict[str, Any] | None:
    profile = get_merchant_profile(base_dir, shop_id)
    if not profile:
        return None
    return {
        "username": username or f"{shop_id}_merchant",
        "shop_id": profile["shop_id"],
        "shop_name": profile["shop_name"],
        "style": profile["style"],
        "style_name": profile["style_name"],
        "style_persona_name": _normalize_style_persona_name(profile.get("style_persona_name"), profile["style_name"]),
        "target_audiences": profile.get("target_audiences", []),
        "city": profile["city"],
        "district": profile["district"],
        "rating": profile["rating"],
        "avg_ticket": profile["avg_ticket"],
        "source": profile.get("source") or "generated_dataset",
    }


def get_merchant_profile(base_dir: str, shop_id: str) -> dict[str, Any] | None:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        return None
    ensure_merchant_data_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT shop_id, shop_name, city, district, style, style_name, rating, review_count, avg_ticket,
               style_persona_id, style_persona_name, style_keywords, target_audiences,
               monthly_revenue, repeat_customer_rate, refund_rate, complaint_rate, store_status,
               hero_sku_id, hero_sku_name, owner_name
        FROM merchant_profiles
        WHERE shop_id = ?
        """,
        (shop_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    for key in ("style_keywords", "target_audiences"):
        raw = data.get(key)
        try:
            parsed = json.loads(raw) if isinstance(raw, str) and raw.strip() else []
        except json.JSONDecodeError:
            parsed = []
        data[key] = parsed if isinstance(parsed, list) else []
    data["style_persona_name"] = _normalize_style_persona_name(data.get("style_persona_name"), data.get("style_name"))
    data["source"] = "generated_dataset"
    return data


def list_portal_accounts(base_dir: str, limit: int = 20) -> list[dict[str, Any]]:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        return []
    ensure_merchant_data_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT username, shop_id, shop_name, display_name
        FROM merchant_accounts
        WHERE enabled_for_portal = 1
        ORDER BY username
        LIMIT ?
        """,
        (max(1, min(int(limit or 20), 100)),),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def seed_demo_portal_accounts(base_dir: str, shops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    ensure_merchant_data_schema(db_path)
    conn = sqlite3.connect(db_path)
    now = datetime.now(BJT).isoformat()
    seeded = []
    for index, shop in enumerate(shops, start=1):
        username = f"demo_merchant_{index:02d}"
        password_hash = _hash_password(DEFAULT_PASSWORD)
        style = str(shop.get("style") or "A")
        shop_name = str(shop.get("name") or shop["id"])
        conn.execute(
            """
            INSERT INTO merchant_accounts(
                username, password_hash, shop_id, shop_name, display_name, role, enabled_for_portal, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'merchant', 1, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                password_hash=excluded.password_hash,
                shop_id=excluded.shop_id,
                shop_name=excluded.shop_name,
                display_name=excluded.display_name,
                enabled_for_portal=1,
                updated_at=excluded.updated_at
            """,
            (username, password_hash, shop["id"], shop_name, f"{shop_name} 商家", now, now),
        )
        conn.execute(
            """
            INSERT INTO merchant_profiles(
                shop_id, shop_name, city, district, style, style_name, rating, review_count, avg_ticket,
                monthly_revenue, repeat_customer_rate, refund_rate, complaint_rate, store_status,
                hero_sku_id, hero_sku_name, owner_name, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(shop_id) DO UPDATE SET
                shop_name=excluded.shop_name,
                style=excluded.style,
                style_name=excluded.style_name,
                rating=excluded.rating,
                avg_ticket=excluded.avg_ticket,
                updated_at=excluded.updated_at
            """,
            (
                shop["id"],
                shop_name,
                "北京",
                _guess_demo_district(shop_name),
                style,
                _style_name(style),
                float(shop.get("rating") or 4.6),
                320,
                int(shop.get("price_avg") or 198),
                int((shop.get("price_avg") or 198) * 240),
                0.34,
                0.018,
                0.006,
                "active",
                None,
                None,
                f"{shop_name} 店主",
                now,
                now,
            ),
        )
        seeded.append({"username": username, "password": DEFAULT_PASSWORD, "shop_id": shop["id"], "shop_name": shop_name})
    conn.commit()
    conn.close()
    return seeded


def _load_account(base_dir: str, username: str) -> dict[str, Any] | None:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        return None
    ensure_merchant_data_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT username, password_hash, shop_id, shop_name, display_name, enabled_for_portal
        FROM merchant_accounts
        WHERE username = ?
        """,
        (str(username or "").strip(),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _hash_password(password: str) -> str:
    return hashlib.sha256(f"vertex-merchant::{password}".encode("utf-8")).hexdigest()


def _normalize_style_row(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("title_tags", "accent_colors", "core_techniques", "support_techniques", "element_tags", "occasion_tags"):
        value = row.get(key)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = []
            row[key] = parsed if isinstance(parsed, list) else []
    return row


def _normalize_style_persona_name(persona_name: Any, style_name: Any) -> str:
    persona = str(persona_name or "").strip()
    if persona:
        return persona
    fallback = str(style_name or "").strip()
    return LEGACY_STYLE_PERSONA_MAP.get(fallback, fallback)


def _pick_hot_style_rows(rows: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    def score(item: dict[str, Any]) -> float:
        return (
            float(item.get("group_buy_orders_30d") or 0) * 4.5
            + float(item.get("click_volume_30d") or 0) * 0.28
            + float(item.get("favorite_count_30d") or 0) * 0.35
            + float(item.get("ctr") or 0) * 120
            + float(item.get("conversion_rate") or 0) * 160
        )
    return sorted(rows, key=score, reverse=True)[:max(1, limit)]


def _pick_cold_style_rows(rows: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    def score(item: dict[str, Any]) -> float:
        return (
            (1 - float(item.get("conversion_rate") or 0)) * 120
            + max(0, 0.12 - float(item.get("ctr") or 0)) * 100
            + min(float(item.get("click_volume_30d") or 0), 200) * 0.16
            + float(item.get("refund_orders_30d") or 0) * 8
        )
    return sorted(rows, key=score, reverse=True)[:max(1, limit)]


def _build_public_competitors(rows: list[sqlite3.Row], profile: dict[str, Any]) -> list[dict[str, Any]]:
    current_template = str(profile.get("style_persona_name") or profile.get("style_name") or "")
    peers = []
    for index, row in enumerate(rows, start=1):
        item = dict(row)
        template = str(item.get("style_persona_name") or item.get("style_name") or "")
        rating = float(item.get("rating") or 0)
        reviews = int(item.get("review_count") or 0)
        style_match = 1.0 if template == current_template else 0.86
        public_score = round(rating * 18 + min(reviews, 2000) * 0.012 + style_match * 10, 1)
        peers.append({
            "rank": index,
            "shop_id": item["shop_id"],
            "shop_name": item["shop_name"],
            "city": item.get("city", ""),
            "district": item.get("district", ""),
            "style": item.get("style", ""),
            "style_name": template,
            "rating": rating,
            "review_count": reviews,
            "avg_ticket": int(item.get("avg_ticket") or 0),
            "style_match": round(style_match, 3),
            "public_score": public_score,
        })
    return peers


def _select_style_image_targets(
    hot_styles: list[dict[str, Any]],
    cold_styles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bucket, reason in ((hot_styles, "hot"), (cold_styles, "cold")):
        for item in bucket:
            style_id = str(item.get("style_id") or "").strip()
            if not style_id or style_id in seen:
                continue
            copied = dict(item)
            copied["image_reason"] = reason
            selected.append(copied)
            seen.add(style_id)
    return selected


def _build_today_ops_advice(
    profile: dict[str, Any],
    totals: dict[str, Any],
    hot_styles: list[dict[str, Any]],
    cold_styles: list[dict[str, Any]],
    all_styles: list[dict[str, Any]],
    public_competitors: list[dict[str, Any]],
) -> dict[str, Any]:
    hot_count = min(3, len(hot_styles))
    revise_candidates = [
        item for item in cold_styles
        if float(item.get("conversion_rate") or 0) < 0.08
    ]
    revise_count = min(2, len(revise_candidates) or len(cold_styles))
    offline_candidates = [
        item for item in cold_styles
        if float(item.get("conversion_rate") or 0) < 0.035
        or int(item.get("refund_orders_30d") or 0) >= 6
    ]
    offline_count = min(1, len(offline_candidates))
    total_orders = int(totals.get("group_buy_orders_30d") or 0)
    total_styles = int(totals.get("style_count") or len(all_styles) or 0)
    persona = str(profile.get("style_persona_name") or profile.get("style_name") or "当前门店风格")
    repeat_rate = float(profile.get("repeat_customer_rate") or 0)
    refund_rate = float(profile.get("refund_rate") or 0)
    avg_ticket = int(profile.get("avg_ticket") or 0)
    rating = float(profile.get("rating") or 0)
    competitor_count = len(public_competitors)

    notes = [
        f"今天先处理 {hot_count} 款待加码爆款，优先放大已经跑出成交的上新候选。",
        f"同时复查 {revise_count} 款高点击低成交款，先做款式图、卖点文案和价格带优化。",
    ]
    if offline_count:
        notes.append(f"其中有 {offline_count} 款建议直接进入下架或降权观察，避免继续吃掉曝光。")
    if repeat_rate < 0.28:
        notes.append("复购偏弱，今天适合补一轮老客提醒和二次到店话术。")
    if refund_rate >= 0.05:
        notes.append("退款压力偏高，记得优先回看差评和退款原因，避免继续放大问题款。")
    if competitor_count:
        notes.append(f"同风格公开竞店有 {competitor_count} 家可参考，后续可以按团购均价和风格包装补齐差距。")

    extra_suggestions = [
        f"围绕 {persona} 再补 1 组同审美变体，保持首页风格统一。",
        "把今天的投流预算优先给已经验证过点击承接能力的款，不要平均分散。",
        "晚间复盘点击高但未成交的款，优先检查主图、团购标题和首屏卖点。",
    ]
    if avg_ticket >= 220:
        extra_suggestions.append("客单已经不低，今天更适合放大高意向款，不建议盲目大降价。")
    else:
        extra_suggestions.append("当前客单仍有抬升空间，可同步测试一档高配版或加价换装饰。")
    if rating >= 4.7:
        extra_suggestions.append("店铺评分优势明显，记得把用户口碑和真实上手效果写进团购卖点。")

    headline = (
        f"今天建议先放大 {hot_count} 款有潜力的成交款，"
        f"再处理 {max(revise_count + offline_count, len(cold_styles))} 款低效款。"
    )
    return {
        "headline": headline,
        "summary": f"{persona} 门店当前共有 {total_styles} 款在运营，本周期累计成交 {total_orders} 单。",
        "promote_count": hot_count,
        "revise_count": revise_count,
        "offline_count": offline_count,
        "suggestions": notes,
        "extra_suggestions": extra_suggestions[:4],
        "actions": [
            {"label": f"{hot_count} 款待加强投流", "target": "hotStyleBoard", "type": "promote"},
            {"label": f"{revise_count} 款待改款优化", "target": "coldStyleBoard", "type": "revise"},
            {"label": f"{offline_count} 款待下架观察", "target": "coldStyleBoard", "type": "offline"},
        ],
    }


def generate_existing_style_images(
    base_dir: str,
    hot_count: int = 7,
    cold_count: int = 3,
    shop_limit: int = 0,
    only_missing: bool = True,
    shop_ids: list[str] | None = None,
) -> dict[str, Any]:
    db_path = os.path.join(base_dir, "data", "jiaqu.db")
    if not os.path.exists(db_path):
        raise ValueError("merchant dataset not found")
    ensure_merchant_data_schema(db_path)
    os.makedirs(os.path.join(base_dir, "static", STYLE_IMAGE_DIRNAME), exist_ok=True)

    safe_hot = max(1, min(int(hot_count or 7), 10))
    safe_cold = max(1, min(int(cold_count or 3), 10))
    safe_limit = max(0, min(int(shop_limit or 0), 5000))
    wanted_shop_ids = {str(item).strip() for item in (shop_ids or []) if str(item).strip()}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    params: list[Any] = []
    where_sql = ""
    if wanted_shop_ids:
        placeholders = ",".join("?" for _ in wanted_shop_ids)
        where_sql = f"WHERE shop_id IN ({placeholders})"
        params.extend(sorted(wanted_shop_ids))
    limit_sql = f"LIMIT {safe_limit}" if safe_limit else ""
    shops = conn.execute(
        f"""
        SELECT shop_id, shop_name, style
        FROM merchant_profiles
        {where_sql}
        ORDER BY shop_id ASC
        {limit_sql}
        """,
        params,
    ).fetchall()

    summary = {
        "generated_at": datetime.now(BJT).isoformat(),
        "shops_processed": 0,
        "styles_requested": 0,
        "generated": 0,
        "failed": 0,
        "skipped": 0,
        "shop_summaries": [],
        "hot_count": safe_hot,
        "cold_count": safe_cold,
        "only_missing": bool(only_missing),
    }
    for shop in shops:
        rows = conn.execute(
            """
            SELECT *
            FROM merchant_style_catalog
            WHERE shop_id = ?
            ORDER BY group_buy_orders_30d DESC, click_volume_30d DESC, search_volume_30d DESC, style_id ASC
            """,
            (shop["shop_id"],),
        ).fetchall()
        styles = [_normalize_style_row(dict(row)) for row in rows]
        hot_styles = _pick_hot_style_rows(styles, limit=safe_hot)
        hot_style_ids = {str(item.get("style_id") or "").strip() for item in hot_styles}
        cold_source_rows = [item for item in styles if str(item.get("style_id") or "").strip() not in hot_style_ids]
        cold_styles = _pick_cold_style_rows(cold_source_rows or styles, limit=safe_cold)
        targets = _select_style_image_targets(hot_styles, cold_styles)
        shop_stats = {"shop_id": shop["shop_id"], "shop_name": shop["shop_name"], "requested": 0, "generated": 0, "failed": 0, "skipped": 0}
        for item in targets:
            if only_missing and str(item.get("style_image_url") or "").strip() and str(item.get("style_image_status") or "").strip() == "generated":
                shop_stats["skipped"] += 1
                summary["skipped"] += 1
                continue
            asset = _generate_style_image_asset(
                base_dir=base_dir,
                shop_name=str(shop.get("shop_name") or shop["shop_id"]),
                shop_style_code=str(shop.get("style") or ""),
                style=item,
            )
            conn.execute(
                """
                UPDATE merchant_style_catalog
                SET style_image_url = ?, style_image_prompt = ?, style_image_status = ?, style_image_error = ?, updated_at = ?
                WHERE shop_id = ? AND style_id = ?
                """,
                (
                    asset["style_image_url"],
                    asset["style_image_prompt"],
                    asset["style_image_status"],
                    asset["style_image_error"],
                    datetime.now(BJT).isoformat(),
                    shop["shop_id"],
                    item["style_id"],
                ),
            )
            shop_stats["requested"] += 1
            summary["styles_requested"] += 1
            if asset["style_image_status"] == "generated":
                shop_stats["generated"] += 1
                summary["generated"] += 1
            elif str(asset["style_image_status"]).startswith("skipped"):
                shop_stats["skipped"] += 1
                summary["skipped"] += 1
            else:
                shop_stats["failed"] += 1
                summary["failed"] += 1
        summary["shops_processed"] += 1
        summary["shop_summaries"].append(shop_stats)
    conn.commit()
    conn.close()
    return summary


def _build_workbench_funnels(daily_rows: list[dict[str, Any]], totals: dict[str, Any]) -> dict[str, Any]:
    search_volume = sum(int(item.get("search_volume") or 0) for item in daily_rows) or int(totals.get("search_volume_30d") or 0)
    click_volume = sum(int(item.get("click_volume") or 0) for item in daily_rows) or int(totals.get("click_volume_30d") or 0)
    consultation_volume = sum(int(item.get("consultation_volume") or 0) for item in daily_rows)
    group_buy_orders = sum(int(item.get("group_buy_orders") or 0) for item in daily_rows) or int(totals.get("group_buy_orders_30d") or 0)
    favorites_added = sum(int(item.get("favorites_added") or 0) for item in daily_rows)
    tryon_volume = max(group_buy_orders, int(round(click_volume * 0.72 + favorites_added * 0.4)))
    store_click_volume = max(click_volume, int(round(search_volume * 0.34)))
    return {
        "search_click_group_buy": {
            "search_volume": search_volume,
            "store_click_volume": store_click_volume,
            "group_buy_orders": group_buy_orders,
            "click_rate": round(store_click_volume / search_volume, 3) if search_volume else 0.0,
            "group_buy_rate": round(group_buy_orders / store_click_volume, 3) if store_click_volume else 0.0,
        },
        "tryon_click_group_buy": {
            "tryon_volume": tryon_volume,
            "store_click_volume": store_click_volume,
            "group_buy_orders": group_buy_orders,
            "click_rate": round(store_click_volume / tryon_volume, 3) if tryon_volume else 0.0,
            "group_buy_rate": round(group_buy_orders / store_click_volume, 3) if store_click_volume else 0.0,
        },
        "consultation_group_buy": {
            "consultation_volume": consultation_volume,
            "group_buy_orders": group_buy_orders,
            "group_buy_rate": round(group_buy_orders / consultation_volume, 3) if consultation_volume else 0.0,
        },
    }


def _build_promotion_delta(style: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, int]:
    extras = payload if isinstance(payload, dict) else {}
    base_search = int(style.get("search_volume_30d") or 0)
    base_click = int(style.get("click_volume_30d") or 0)
    base_orders = int(style.get("group_buy_orders_30d") or 0)
    price = int(style.get("price") or 168)
    requested_budget = max(60, int(extras.get("budget") or 180))
    traffic_units = max(1, min(int(extras.get("traffic_units") or 1), 8))
    scale = max(0.7, min(3.5, requested_budget / 180)) * traffic_units
    inc_search = max(120, int((int(base_search * 0.18) + 48) * scale))
    inc_click = max(28, int((int(base_click * 0.16) + 14) * scale))
    inc_orders = max(2, int(round((max(base_orders, 3) * 0.12 + 2) * min(scale, 2.4))))
    inc_favorites = max(8, int(inc_click * 0.42))
    inc_share = max(3, int(inc_click * 0.18))
    return {
        "search_volume": inc_search,
        "click_volume": inc_click,
        "group_buy_orders": inc_orders,
        "favorite_count": inc_favorites,
        "share_count": inc_share,
        "revenue": inc_orders * price,
        "ad_spend": requested_budget,
        "consultation_volume": max(12, int(inc_click * 0.3)),
    }


def _apply_style_delta(
    conn: sqlite3.Connection,
    shop_id: str,
    style_id: str,
    style: dict[str, Any],
    delta: dict[str, int],
) -> None:
    now = datetime.now(BJT).isoformat()
    today = datetime.now(BJT).date().isoformat()
    conn.execute(
        """
        UPDATE merchant_style_catalog
        SET search_volume_30d = search_volume_30d + ?,
            click_volume_30d = click_volume_30d + ?,
            group_buy_orders_30d = group_buy_orders_30d + ?,
            favorite_count_30d = favorite_count_30d + ?,
            share_count_30d = share_count_30d + ?,
            gmv_30d = gmv_30d + ?,
            ctr = CASE
                WHEN (search_volume_30d + ?) > 0 THEN ROUND(CAST(click_volume_30d + ? AS REAL) / CAST(search_volume_30d + ? AS REAL), 4)
                ELSE 0
            END,
            conversion_rate = CASE
                WHEN (click_volume_30d + ?) > 0 THEN ROUND(CAST(group_buy_orders_30d + ? AS REAL) / CAST(click_volume_30d + ? AS REAL), 4)
                ELSE 0
            END,
            trend_signal = 'rising',
            launch_stage = 'traffic_boosted',
            updated_at = ?
        WHERE shop_id = ? AND style_id = ?
        """,
        (
            delta["search_volume"],
            delta["click_volume"],
            delta["group_buy_orders"],
            delta["favorite_count"],
            delta["share_count"],
            delta["revenue"],
            delta["search_volume"],
            delta["click_volume"],
            delta["search_volume"],
            delta["click_volume"],
            delta["group_buy_orders"],
            delta["click_volume"],
            now,
            shop_id,
            style_id,
        ),
    )
    existing_shop = conn.execute(
        "SELECT id FROM merchant_shop_daily_metrics WHERE shop_id = ? AND date = ? LIMIT 1",
        (shop_id, today),
    ).fetchone()
    if existing_shop:
        conn.execute(
            """
            UPDATE merchant_shop_daily_metrics
            SET search_volume = search_volume + ?,
                click_volume = click_volume + ?,
                consultation_volume = consultation_volume + ?,
                group_buy_orders = group_buy_orders + ?,
                revenue = revenue + ?,
                ad_spend = ad_spend + ?,
                favorites_added = favorites_added + ?
            WHERE shop_id = ? AND date = ?
            """,
            (
                delta["search_volume"],
                delta["click_volume"],
                delta["consultation_volume"],
                delta["group_buy_orders"],
                delta["revenue"],
                delta["ad_spend"],
                delta["favorite_count"],
                shop_id,
                today,
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO merchant_shop_daily_metrics(
                shop_id, date, search_volume, click_volume, consultation_volume, group_buy_orders,
                revenue, ad_spend, repeat_orders, refund_orders, favorites_added, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
            """,
            (
                shop_id,
                today,
                delta["search_volume"],
                delta["click_volume"],
                delta["consultation_volume"],
                delta["group_buy_orders"],
                delta["revenue"],
                delta["ad_spend"],
                delta["favorite_count"],
                now,
            ),
        )
    existing_style_day = conn.execute(
        "SELECT id FROM merchant_style_daily_metrics WHERE shop_id = ? AND style_id = ? AND date = ? LIMIT 1",
        (shop_id, style_id, today),
    ).fetchone()
    if existing_style_day:
        conn.execute(
            """
            UPDATE merchant_style_daily_metrics
            SET search_volume = search_volume + ?,
                click_volume = click_volume + ?,
                group_buy_orders = group_buy_orders + ?,
                favorites_added = favorites_added + ?
            WHERE shop_id = ? AND style_id = ? AND date = ?
            """,
            (
                delta["search_volume"],
                delta["click_volume"],
                delta["group_buy_orders"],
                delta["favorite_count"],
                shop_id,
                style_id,
                today,
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO merchant_style_daily_metrics(
                shop_id, style_id, date, search_volume, click_volume, group_buy_orders, favorites_added, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                shop_id,
                style_id,
                today,
                delta["search_volume"],
                delta["click_volume"],
                delta["group_buy_orders"],
                delta["favorite_count"],
                now,
            ),
        )


def _build_style_ai_update(style: dict[str, Any]) -> dict[str, Any]:
    price = int(style.get("price") or 168)
    click_volume = int(style.get("click_volume_30d") or 0)
    orders = int(style.get("group_buy_orders_30d") or 0)
    conversion = float(style.get("conversion_rate") or 0)
    search_volume = int(style.get("search_volume_30d") or 0)
    trend_signal = str(style.get("trend_signal") or "stable")
    tags = list(style.get("title_tags") or [])
    primary_style = str(style.get("primary_style") or style.get("style_persona_name") or "门店主风格")
    secondary_style = str(style.get("secondary_style") or "显白通勤")
    primary_color = str(style.get("primary_color") or "奶白")
    nail_shape = str(style.get("nail_shape") or "短方圆")
    nail_length = str(style.get("nail_length") or "短")
    finish = str(style.get("texture_finish") or "亮面")
    base_coat = str(style.get("base_coat") or f"{primary_color}底")
    core_techniques = list(style.get("core_techniques") or [])
    support_techniques = list(style.get("support_techniques") or [])
    element_tags = list(style.get("element_tags") or [])
    occasion_tags = list(style.get("occasion_tags") or [])
    hero_technique = core_techniques[0] if core_techniques else "细闪法式"
    support_technique = support_techniques[0] if support_techniques else "局部高光"
    hero_element = element_tags[0] if element_tags else "小钻"
    hero_occasion = occasion_tags[0] if occasion_tags else "通勤约会"

    if click_volume >= 140 and conversion < 0.06:
        next_price = max(88, price - 18)
        tags = list(dict.fromkeys([*tags, "AI改价", "引流款"]))
        strategy = "转化修复型改款"
        title_copy = f"{primary_color}{hero_technique}·{hero_element}{primary_style}"
        subtitle_copy = f"把主图重点放在 {primary_color} 显色和 {hero_technique} 细节上，先做新客引流测试。"
        offer_copy = f"适合 {hero_occasion} 的轻设计入门款，先用更低门槛团购价承接高点击人群。"
        selling_points = [
            f"封面图突出 {primary_color} 显白效果，弱化背景干扰。",
            f"把 {hero_technique} 和 {hero_element} 放到第一视觉层，减少“点进来但没记住”的情况。",
            f"团购文案先强调 {secondary_style}、好搭衣服和新客体验价。",
        ]
        image_direction = [
            f"重拍/重绘近景单手显色图，突出 {primary_color} + {hero_technique} 的质感。",
            f"保留 {nail_shape} / {nail_length} 的真实佩戴感，让用户更容易判断上手效果。",
            f"用 {base_coat} 做干净背景，局部补 {support_technique} 反光，让点击后的预期更稳定。",
        ]
        launch_stage = "ai_repriced"
        message = f"AI 已为「{style['style_name']}」生成转化修复方案，建议先下调到 ¥{next_price}，同时重做封面图和团购文案。"
    elif orders >= 16 and conversion >= 0.12:
        next_price = price + 12
        tags = list(dict.fromkeys([*tags, "AI主推", "稳定成交"]))
        strategy = "爆款放大型改款"
        title_copy = f"{primary_color}{finish}{primary_style}·{hero_technique}{hero_element}"
        subtitle_copy = f"保留原本高转化方向，把封面图改成更高级、更利于提客单的版本。"
        offer_copy = f"主打 {hero_occasion} 的精致升级款，可同步测试高配版或加价换装饰。"
        selling_points = [
            f"延续当前已经跑通的 {hero_technique} 卖点，避免大改风格导致流失。",
            f"把 {support_technique} 和 {hero_element} 作为“高级感细节”写进标题和首屏卖点。",
            f"团购文案增加“升级版”“进阶款”“主推款”表达，承接更高客单。",
        ]
        image_direction = [
            f"封面图切到更精致的近景质感图，强化 {finish} 光泽和 {hero_element} 细节。",
            f"增加一张细节图解释 {hero_technique}，让高意向用户更愿意为升级版下单。",
            f"整体画面保持 {primary_style} 审美，但加入更强的主推款陈列感。",
        ]
        launch_stage = "hero"
        message = f"AI 已为「{style['style_name']}」生成爆款放大方案，建议提价到 ¥{next_price}，并升级封面图与主推文案。"
    else:
        next_price = price
        tags = list(dict.fromkeys([*tags, "AI优化", "卖点重写"]))
        strategy = "内容焕新型改款"
        title_copy = f"{primary_color}{primary_style}·{hero_technique}{hero_element}"
        subtitle_copy = f"先不急着改价，优先把封面图、标题和团购卖点整理得更清楚。"
        offer_copy = f"更适合 {hero_occasion} 客群，强调 {secondary_style}、好驾驭和显白上手。"
        selling_points = [
            f"把 {primary_style} 说清楚，避免只看到颜色却不知道风格场景。",
            f"增加 {hero_technique} / {support_technique} 的细节说明，让用户知道这款值在哪里。",
            f"标题和团购首屏都补一句“适合 {hero_occasion}”的人群和场景。",
        ]
        image_direction = [
            f"封面图先改成更清晰的单手显色图，突出 {primary_color} 与 {hero_technique}。",
            f"增加一张佩戴场景图，强化 {secondary_style} 的穿搭联想。",
            f"减少无关装饰，把 {hero_element} 控制在点缀层，避免视觉太杂。",
        ]
        launch_stage = "ai_refined"
        message = f"AI 已为「{style['style_name']}」生成内容焕新方案，建议先重做款式图和标题文案，再决定是否加价或投流。"

    image_prompt = (
        f"真实美甲店作品图，{primary_style}风格，{nail_shape}{nail_length}，{primary_color}主色，"
        f"{finish}质感，{hero_technique}+{support_technique}，点缀{hero_element}，"
        f"突出{hero_occasion}场景，近景显色，封面构图干净，适合团购主图。"
    )
    design_prompt = (
        f"保留当前 {primary_style} 审美，强化 {primary_color} + {hero_technique} 卖点，"
        f"把 {secondary_style}、{hero_occasion}、{hero_element} 放进前两屏文案，"
        f"搜索 {search_volume} / 点击 {click_volume} / 成交 {orders} / 转化 {round(conversion * 100)}% / 趋势 {trend_signal}。"
    )
    apply_changes = [
        f"更新团购价格到 ¥{next_price}" if next_price != price else "本轮先保持当前价格不变",
        "重写封面图方向与出图提示词",
        f"把标题标签更新为：{'、'.join(tags[:4])}" if tags else "补充 AI 优化标签",
        f"把款式定位调整为 {strategy}",
    ]
    return {
        "strategy": strategy,
        "summary": message,
        "price": next_price,
        "current_price": price,
        "launch_stage": launch_stage,
        "title_tags": tags,
        "title_copy": title_copy,
        "subtitle_copy": subtitle_copy,
        "offer_copy": offer_copy,
        "selling_points": selling_points,
        "image_direction": image_direction,
        "image_prompt": image_prompt,
        "design_prompt": design_prompt,
        "apply_changes": apply_changes,
        "message": message,
    }


def _build_shop_name(rng: random.Random, district: str) -> str:
    return f"{rng.choice(SHOP_PREFIX)}{district}{rng.choice(SHOP_SUFFIX)}"


def _guess_demo_district(shop_name: str) -> str:
    for token in ("Sanlitun", "Wudaokou", "Guomao", "Wangjing", "Zhongguancun"):
        if token.lower() in shop_name.lower():
            return token
    return "北京"


def _style_name(style_code: str) -> str:
    return {
        "A": "简约清透",
        "B": "甜美可爱",
        "C": "闪耀华丽",
        "D": "冷感暗黑",
        "E": "趋势实验",
    }[style_code]


def _merge_weight_map(base: dict[str, float], override: dict[str, float] | None) -> dict[str, float]:
    merged = dict(base)
    if override:
        merged.update({str(key): float(value) for key, value in override.items()})
    return merged


def _merge_list_values(base: list[str], override: list[str] | None) -> list[str]:
    values = list(base)
    for item in override or []:
        if item not in values:
            values.append(item)
    return values


def _resolve_style_persona(persona_id: str) -> dict[str, Any]:
    raw = STYLE_PERSONAS[persona_id]
    base = STYLE_ARCHETYPES[str(raw["style_code"])]
    return {
        "persona_id": persona_id,
        "name": raw["name"],
        "style_code": raw["style_code"],
        "merchant_position": raw.get("merchant_position") or base["merchant_position"],
        "keywords": list(raw.get("keywords") or []),
        "target_audiences": list(raw.get("target_audiences") or []),
        "primary_styles": _merge_weight_map(base["primary_styles"], raw.get("primary_styles")),
        "secondary_styles": _merge_weight_map(base["secondary_styles"], raw.get("secondary_styles")),
        "shapes": _merge_weight_map(base["shapes"], raw.get("shapes")),
        "lengths": _merge_weight_map(base["lengths"], raw.get("lengths")),
        "primary_colors": _merge_weight_map(base["primary_colors"], raw.get("primary_colors")),
        "accent_colors": _merge_list_values(base["accent_colors"], raw.get("accent_colors")),
        "transparencies": _merge_weight_map(base["transparencies"], raw.get("transparencies")),
        "finishes": _merge_weight_map(base["finishes"], raw.get("finishes")),
        "base_coats": _merge_list_values(base["base_coats"], raw.get("base_coats")),
        "core_technique_sets": list(raw.get("core_technique_sets") or base["core_technique_sets"]),
        "support_techniques": _merge_list_values(base["support_techniques"], raw.get("support_techniques")),
        "elements": _merge_list_values(base["elements"], raw.get("elements")),
        "occasions": _merge_list_values(base["occasions"], raw.get("occasions")),
        "complexity": _merge_weight_map(base["complexity"], raw.get("complexity")),
        "forbidden": _merge_list_values(base["forbidden"], raw.get("forbidden")),
    }


def _pick_style_persona(rng: random.Random) -> dict[str, Any]:
    weights = {
        "minimal_commute": 0.07,
        "pure_desire": 0.09,
        "sweet_girl": 0.07,
        "pastoral_garden": 0.05,
        "rich_girl": 0.06,
        "old_money": 0.06,
        "queen_sister": 0.06,
        "dark_goth": 0.05,
        "color_block": 0.06,
        "dopamine_pop": 0.05,
        "minimal_clear": 0.07,
        "bridal_french": 0.05,
        "chinese_chic": 0.05,
        "japanese_editorial": 0.06,
        "french_vintage": 0.05,
        "y2k_trend": 0.05,
        "sweet_cool": 0.07,
        "clean_girl": 0.06,
    }
    persona_id = _weighted_choice(rng, weights)
    return _resolve_style_persona(persona_id)


def _category_ticket(style_code: str, rng: random.Random) -> int:
    ranges = {
        "A": (128, 228),
        "B": (138, 258),
        "C": (188, 368),
        "D": (168, 338),
        "E": (198, 398),
    }
    low, high = ranges[style_code]
    return rng.randint(low, high)


def _weighted_choice(rng: random.Random, pool: dict[str, float]) -> str:
    items = [(key, max(0.0, float(weight))) for key, weight in pool.items() if str(key)]
    total = sum(weight for _, weight in items)
    if total <= 0:
        return next(iter(pool))
    cursor = rng.uniform(0, total)
    running = 0.0
    for key, weight in items:
        running += weight
        if cursor <= running:
            return key
    return items[-1][0]


def _pick_unique_values(rng: random.Random, values: list[str], minimum: int = 1, maximum: int = 2) -> list[str]:
    choices = [str(value) for value in values if str(value)]
    if not choices:
        return []
    count = max(1, min(len(choices), rng.randint(minimum, max(maximum, minimum))))
    return rng.sample(choices, count)


def _choose_style_generation_mode(rng: random.Random, requested_mode: str) -> str:
    if requested_mode in {"safe", "innovate", "trend"}:
        return requested_mode
    weights = {"safe": 0.58, "innovate": 0.27, "trend": 0.15}
    return _weighted_choice(rng, weights)


def _adjacent_style_codes(style_code: str) -> list[str]:
    return {
        "A": ["B", "C"],
        "B": ["A", "E"],
        "C": ["A", "D"],
        "D": ["C", "E"],
        "E": ["B", "C"],
    }.get(style_code, ["A"])


def _build_style_fields(rng: random.Random, style_code: str, generation_mode: str, persona: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = persona or STYLE_ARCHETYPES.get(style_code, STYLE_ARCHETYPES["A"])
    actual_mode = _choose_style_generation_mode(rng, generation_mode)
    primary_style = _weighted_choice(rng, profile["primary_styles"])
    secondary_style = _weighted_choice(rng, profile["secondary_styles"])
    nail_shape = _weighted_choice(rng, profile["shapes"])
    nail_length = _weighted_choice(rng, profile["lengths"])
    primary_color = _weighted_choice(rng, profile["primary_colors"])
    accent_colors = _pick_unique_values(rng, profile["accent_colors"], minimum=1, maximum=2)
    transparency = _weighted_choice(rng, profile["transparencies"])
    texture_finish = _weighted_choice(rng, profile["finishes"])
    base_coat = rng.choice(profile["base_coats"])
    core_techniques = list(rng.choice(profile["core_technique_sets"]))
    support_techniques = _pick_unique_values(rng, profile["support_techniques"], minimum=1, maximum=2)
    element_tags = _pick_unique_values(rng, profile["elements"], minimum=1, maximum=2)
    occasion_tags = _pick_unique_values(rng, profile["occasions"], minimum=1, maximum=2)
    complexity_tier = _weighted_choice(rng, profile["complexity"])

    if actual_mode == "innovate":
        adjacent_profile = STYLE_ARCHETYPES[_adjacent_style_codes(style_code)[0]]
        innovation_pick = rng.choice(adjacent_profile["support_techniques"])
        if innovation_pick not in support_techniques:
            support_techniques.append(innovation_pick)
        accent_pick = rng.choice(adjacent_profile["accent_colors"])
        if accent_pick not in accent_colors:
            accent_colors.append(accent_pick)
    elif actual_mode == "trend":
        trend_technique = rng.choice(TREND_KEYWORDS["techniques"])
        if trend_technique not in core_techniques:
            core_techniques[-1] = trend_technique
        trend_element = rng.choice(TREND_KEYWORDS["elements"])
        if trend_element not in element_tags:
            element_tags.append(trend_element)
        trend_color = rng.choice(TREND_KEYWORDS["colors"])
        if trend_color not in accent_colors and trend_color != primary_color:
            accent_colors.append(trend_color)
        trend_occasion = rng.choice(TREND_KEYWORDS["occasions"])
        if trend_occasion not in occasion_tags:
            occasion_tags.append(trend_occasion)

    # Keep the card compact and internally consistent.
    accent_colors = accent_colors[:2]
    support_techniques = support_techniques[:2]
    element_tags = element_tags[:2]
    occasion_tags = occasion_tags[:2]

    return {
        "style_persona_id": str(profile.get("persona_id") or ""),
        "style_persona_name": str(profile.get("name") or _style_name(style_code)),
        "merchant_position": profile["merchant_position"],
        "keywords": list(profile.get("keywords") or []),
        "target_audiences": list(profile.get("target_audiences") or []),
        "primary_style": primary_style,
        "secondary_style": secondary_style,
        "nail_shape": nail_shape,
        "nail_length": nail_length,
        "primary_color": primary_color,
        "accent_colors": accent_colors,
        "transparency": transparency,
        "texture_finish": texture_finish,
        "base_coat": base_coat,
        "core_techniques": core_techniques,
        "support_techniques": support_techniques,
        "element_tags": element_tags,
        "occasion_tags": occasion_tags,
        "complexity_tier": complexity_tier,
        "merchant_generation_mode": actual_mode,
        "forbidden": list(profile["forbidden"]),
    }


def _build_style_name(fields: dict[str, Any], index: int) -> str:
    color = str(fields["primary_color"])
    lead_technique = str(fields["core_techniques"][0])
    secondary = str(fields["core_techniques"][1]) if len(fields["core_techniques"]) > 1 else str(fields["secondary_style"])
    element = str(fields["element_tags"][0]) if fields["element_tags"] else str(fields["secondary_style"])
    return f"{color}{lead_technique}·{secondary}{element}{index}"


def _complexity_level(label: str) -> int:
    return {"轻设计": 1, "中等": 2, "重工": 3}.get(str(label), 2)


def _daily_friendliness(fields: dict[str, Any]) -> float:
    length_score = {"超短": 1.0, "短": 0.95, "中短": 0.86, "中长": 0.72, "长": 0.58, "超长": 0.4}.get(str(fields["nail_length"]), 0.8)
    complexity_score = {1: 1.0, 2: 0.82, 3: 0.62}.get(_complexity_level(fields["complexity_tier"]), 0.8)
    return round(length_score * complexity_score, 3)


def _build_style_metrics(rng: random.Random, style_code: str, fields: dict[str, Any]) -> dict[str, Any]:
    complexity = _complexity_level(fields["complexity_tier"])
    trend_hits = sum(
        1
        for token in [fields["primary_color"], *fields["accent_colors"], *fields["core_techniques"], *fields["element_tags"], *fields["occasion_tags"]]
        if token in set(TREND_KEYWORDS["colors"] + TREND_KEYWORDS["techniques"] + TREND_KEYWORDS["elements"] + TREND_KEYWORDS["occasions"])
    )
    style_bias = {"A": 1.02, "B": 1.06, "C": 0.96, "D": 0.84, "E": 1.01}.get(style_code, 1.0)
    mode_bias = {"safe": 0.98, "innovate": 1.04, "trend": 1.14}.get(str(fields["merchant_generation_mode"]), 1.0)
    search_volume = max(160, int(rng.randint(220, 4200) * style_bias * mode_bias * (1 + trend_hits * 0.06)))
    ctr_base = {"A": 0.23, "B": 0.24, "C": 0.21, "D": 0.18, "E": 0.22}.get(style_code, 0.21)
    ctr = max(0.08, min(0.46, round(rng.uniform(ctr_base - 0.05, ctr_base + 0.07) + complexity * 0.008, 3)))
    click_volume = max(28, int(search_volume * ctr))
    cart_volume = max(4, int(click_volume * rng.uniform(0.1, 0.42)))

    ticket_anchor = _category_ticket(style_code, rng)
    price_adjust = (complexity - 2) * 28
    long_length_boost = {"中长": 18, "长": 34, "超长": 56}.get(str(fields["nail_length"]), 0)
    price = max(88, ticket_anchor + price_adjust + long_length_boost + rng.randint(-22, 34))
    cost = max(38, int(price * rng.uniform(0.28, 0.56)))
    duration_minutes = {
        1: rng.choice([45, 60, 75]),
        2: rng.choice([75, 90, 105]),
        3: rng.choice([105, 120, 135]),
    }[complexity]

    daily_score = _daily_friendliness(fields)
    conversion_base = {"A": 0.13, "B": 0.12, "C": 0.095, "D": 0.08, "E": 0.09}.get(style_code, 0.1)
    price_penalty = max(0.0, (price - ticket_anchor) / max(ticket_anchor, 1) * 0.03)
    conversion_rate = max(
        0.03,
        min(
            0.24,
            round(conversion_base + daily_score * 0.03 + trend_hits * 0.005 - price_penalty + rng.uniform(-0.018, 0.026), 3),
        ),
    )
    orders = max(0, int(click_volume * conversion_rate))
    refund_orders = min(orders, int(orders * rng.uniform(0.0, 0.08)))
    favorite_count = max(0, int(click_volume * rng.uniform(0.08, 0.28)))
    share_count = max(0, int(click_volume * rng.uniform(0.04, 0.18)))
    impression_volume = max(search_volume + rng.randint(120, 2600), int(search_volume * rng.uniform(1.15, 2.35)))
    gmv = price * max(orders - refund_orders, 0)

    if fields["merchant_generation_mode"] == "trend":
        launch_stage = rng.choice(["new", "growing", "growing"])
        trend_signal = rng.choice(["up", "up", "flat"])
    elif fields["merchant_generation_mode"] == "innovate":
        launch_stage = rng.choice(["new", "growing", "steady"])
        trend_signal = rng.choice(["up", "flat", "up"])
    else:
        launch_stage = rng.choice(["steady", "growing", "steady", "declining"])
        trend_signal = rng.choice(["flat", "up", "flat", "down"])

    inventory_status = "featured" if orders >= 26 or trend_signal == "up" else rng.choice(["normal", "limited", "normal"])

    return {
        "price": price,
        "cost": cost,
        "duration_minutes": duration_minutes,
        "search_volume_30d": search_volume,
        "click_volume_30d": click_volume,
        "cart_volume_30d": cart_volume,
        "group_buy_orders_30d": orders,
        "ctr": ctr,
        "conversion_rate": conversion_rate,
        "refund_orders_30d": refund_orders,
        "favorite_count_30d": favorite_count,
        "share_count_30d": share_count,
        "impression_volume_30d": impression_volume,
        "cpc": round(rng.uniform(0.4, 3.8), 2),
        "gmv_30d": gmv,
        "inventory_status": inventory_status,
        "launch_stage": launch_stage,
        "trend_signal": trend_signal,
    }


def _build_style_prompt(fields: dict[str, Any]) -> str:
    support_text = "、".join(fields["support_techniques"]) if fields["support_techniques"] else "无额外工艺"
    element_text = "、".join(fields["element_tags"]) if fields["element_tags"] else "低密度精致点缀"
    accent_text = "、".join(fields["accent_colors"]) if fields["accent_colors"] else "同色系细节"
    occasion_text = "、".join(fields["occasion_tags"]) if fields["occasion_tags"] else "日常拍照"
    audience_text = "、".join(fields["target_audiences"]) if fields["target_audiences"] else "门店主力客群"
    keyword_text = "、".join(fields["keywords"][:6]) if fields["keywords"] else fields["primary_style"]
    forbidden_text = "、".join(fields["forbidden"][:4])
    return (
        f"生成一张真实美甲店作品图，风格为{fields['merchant_position']}，主风格 {fields['primary_style']}，副风格 {fields['secondary_style']}。"
        f"甲型 {fields['nail_shape']}，长度 {fields['nail_length']}。"
        f"主色 {fields['primary_color']}，辅色 {accent_text}，底色 {fields['base_coat']}，透明度 {fields['transparency']}。"
        f"核心工艺 {fields['core_techniques'][0]}、{fields['core_techniques'][1] if len(fields['core_techniques']) > 1 else fields['secondary_style']}，"
        f"辅助工艺 {support_text}。元素点缀 {element_text}。"
        f"整体质感 {fields['texture_finish']}，复杂度 {fields['complexity_tier']}，适合 {occasion_text}，主推人群 {audience_text}。"
        f"关键词：{keyword_text}。"
        "画面要求单手近景，五指完整可见，指甲纹理清晰，真实高级的门店样板图质感，背景干净，颜色统一。"
        f"避免 {forbidden_text}，避免多余手指、手部畸形、模糊甲面、廉价塑料感和脏乱背景。"
    )


def _build_shop_styles(
    rng: random.Random,
    shop_id: str,
    style_code: str,
    count: int,
    created_at: str,
    generation_mode: str = "mixed",
    persona: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    catalog = []
    for index in range(1, count + 1):
        style_id = f"{shop_id}_sku_{index:03d}"
        fields = _build_style_fields(rng, style_code, generation_mode, persona=persona)
        metrics = _build_style_metrics(rng, style_code, fields)
        style_name = _build_style_name(fields, index)
        title_tags = list(dict.fromkeys([
            fields["primary_style"],
            fields["core_techniques"][0],
            fields["primary_color"],
            fields["style_persona_name"] or fields["secondary_style"],
            fields["occasion_tags"][0] if fields["occasion_tags"] else fields["secondary_style"],
            "门店招牌" if metrics["launch_stage"] in {"growing", "new"} else "高复购候选",
        ]))
        catalog.append({
            "shop_id": shop_id,
            "style_id": style_id,
            "style_name": style_name,
            "category": style_code,
            **metrics,
            "title_tags": title_tags,
            "style_persona_id": fields["style_persona_id"],
            "style_persona_name": fields["style_persona_name"],
            "primary_style": fields["primary_style"],
            "secondary_style": fields["secondary_style"],
            "nail_shape": fields["nail_shape"],
            "nail_length": fields["nail_length"],
            "primary_color": fields["primary_color"],
            "accent_colors": fields["accent_colors"],
            "transparency": fields["transparency"],
            "texture_finish": fields["texture_finish"],
            "base_coat": fields["base_coat"],
            "core_techniques": fields["core_techniques"],
            "support_techniques": fields["support_techniques"],
            "element_tags": fields["element_tags"],
            "occasion_tags": fields["occasion_tags"],
            "complexity_tier": fields["complexity_tier"],
            "merchant_generation_mode": fields["merchant_generation_mode"],
            "design_prompt": _build_style_prompt(fields),
            "style_image_url": "",
            "style_image_prompt": "",
            "style_image_status": "not_requested",
            "style_image_error": "",
            "created_at": created_at,
        })
    return catalog


def _attach_style_images_to_shop(
    base_dir: str,
    rng: random.Random,
    shop_name: str,
    shop_style_code: str,
    styles: list[dict[str, Any]],
    max_images: int,
) -> dict[str, int]:
    if max_images <= 0 or not styles:
        return {"generated": 0, "failed": 0, "skipped": 0}
    candidates = sorted(
        styles,
        key=lambda item: (
            int(item.get("group_buy_orders_30d") or 0) * 4
            + int(item.get("click_volume_30d") or 0)
            + (18 if item.get("merchant_generation_mode") == "trend" else 0)
        ),
        reverse=True,
    )[:max_images]
    stats = {"generated": 0, "failed": 0, "skipped": 0}
    for item in candidates:
        asset = _generate_style_image_asset(
            base_dir=base_dir,
            shop_name=shop_name,
            shop_style_code=shop_style_code,
            style=item,
        )
        item.update(asset)
        if item["style_image_status"] == "generated":
            stats["generated"] += 1
        elif item["style_image_status"].startswith("skipped"):
            stats["skipped"] += 1
        else:
            stats["failed"] += 1
    return stats


def _extract_generated_image_url(payload: dict[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("url"):
                return str(item["url"])
    return ""


def _generate_style_image_asset(
    base_dir: str,
    shop_name: str,
    shop_style_code: str,
    style: dict[str, Any],
) -> dict[str, str]:
    api_key = str(os.environ.get("ARK_API_KEY") or "").strip()
    prompt = str(style.get("style_image_prompt") or style.get("design_prompt") or "").strip()
    if not api_key:
        return {
            "style_image_url": "",
            "style_image_prompt": prompt,
            "style_image_status": "skipped_no_api_key",
            "style_image_error": "",
        }
    if not prompt:
        return {
            "style_image_url": "",
            "style_image_prompt": "",
            "style_image_status": "skipped_no_prompt",
            "style_image_error": "",
        }
    payload = {
        "model": DEFAULT_STYLE_IMAGE_MODEL,
        "prompt": prompt,
        "sequential_image_generation": "disabled",
        "response_format": "url",
        "size": DEFAULT_STYLE_IMAGE_SIZE,
        "stream": False,
        "watermark": True,
    }
    try:
        response = requests.post(
            ARK_IMAGE_ENDPOINT,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json=payload,
            timeout=180,
        )
        response.raise_for_status()
        data = response.json()
        image_url = _extract_generated_image_url(data)
        if not image_url:
            return {
                "style_image_url": "",
                "style_image_prompt": prompt,
                "style_image_status": "failed",
                "style_image_error": "ark_returned_empty_url",
            }
        image_bytes = requests.get(image_url, timeout=60).content
        local_dir = os.path.join(base_dir, "static", STYLE_IMAGE_DIRNAME)
        os.makedirs(local_dir, exist_ok=True)
        file_name = f"{style['style_id']}.png"
        with open(os.path.join(local_dir, file_name), "wb") as fp:
            fp.write(image_bytes)
        return {
            "style_image_url": f"/static/{STYLE_IMAGE_DIRNAME}/{file_name}",
            "style_image_prompt": prompt,
            "style_image_status": "generated",
            "style_image_error": "",
        }
    except (requests.RequestException, OSError, ValueError) as exc:
        return {
            "style_image_url": "",
            "style_image_prompt": prompt,
            "style_image_status": "failed",
            "style_image_error": str(exc)[:240],
        }


def _build_shop_daily_rows(rng: random.Random, shop_id: str, monthly_revenue: int, days: int, created_at: str) -> list[tuple[Any, ...]]:
    rows = []
    baseline = max(800, int(monthly_revenue / max(days, 1)))
    for offset in range(days):
        day = (datetime.now(BJT) - timedelta(days=offset)).date().isoformat()
        revenue = max(400, int(baseline * rng.uniform(0.65, 1.35)))
        search = max(80, int(revenue / rng.uniform(2.2, 4.8)))
        click = max(20, int(search * rng.uniform(0.12, 0.35)))
        orders = max(1, int(click * rng.uniform(0.04, 0.16)))
        rows.append((
            shop_id,
            day,
            search,
            click,
            max(4, int(click * rng.uniform(0.08, 0.26))),
            orders,
            revenue,
            max(50, int(revenue * rng.uniform(0.06, 0.2))),
            max(0, int(orders * rng.uniform(0.2, 0.55))),
            max(0, int(orders * rng.uniform(0.0, 0.08))),
            max(1, int(click * rng.uniform(0.03, 0.14))),
            created_at,
        ))
    return rows


def _build_style_daily_rows(rng: random.Random, styles: list[dict[str, Any]], days: int, created_at: str) -> list[tuple[Any, ...]]:
    rows = []
    tracked = styles[: min(12, len(styles))]
    for item in tracked:
        base_search = max(20, int(item["search_volume_30d"] / max(days, 1)))
        base_click = max(5, int(item["click_volume_30d"] / max(days, 1)))
        base_order = max(0, int(item["group_buy_orders_30d"] / max(days, 1)))
        for offset in range(days):
            day = (datetime.now(BJT) - timedelta(days=offset)).date().isoformat()
            search = max(0, int(base_search * rng.uniform(0.55, 1.45)))
            click = max(0, int(base_click * rng.uniform(0.55, 1.45)))
            orders = max(0, int(base_order * rng.uniform(0.35, 1.65)))
            rows.append((
                item["shop_id"],
                item["style_id"],
                day,
                search,
                click,
                orders,
                max(0, int(click * rng.uniform(0.03, 0.18))),
                created_at,
            ))
    return rows
