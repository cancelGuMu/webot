"""趣味功能模块 — 群聊小玩法。"""

import json
import logging
import random
from pathlib import Path

from src.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# ── 默认签文数据（用户未自定义时使用）──────────────────────────────

_DEFAULT_LEVELS = [
    ("大吉", "🟢", [
        "福星在线，连外卖都能准点到",
        "好运爆棚，随手一抽全是惊喜",
        "今日开挂，困难见了都绕路走",
        "钱包回暖，心情直接原地起飞",
        "贵人冒头，关键时刻有人搭把手",
        "灵感喷涌，脑子比咖啡还提神",
        "状态满格，干啥都像顺风局",
        "喜气上头，小目标今天能推进",
        "效率拉满，摸鱼都不耽误正事",
        "万事顺滑，连红灯都像在放假",
        "好运排队，惊喜可能正在路上",
        "气场全开，今天适合大胆冲一把",
        "心想事成，连拖延症都被治好",
        "财运冒泡，奶茶钱有望自己来",
        "人品爆发，抽卡都像开了会员",
        "顺风顺水，麻烦暂时自动静音",
        "快乐加倍，今天笑点格外密集",
        "机会敲门，记得把门开大一点",
        "元气满满，整个人像刚充满电",
        "锦鲤附体，好消息可能连发三条",
    ]),
    ("中吉", "🔵", [
        "稳稳当当，小惊喜藏在日常里",
        "节奏不错，慢慢来反而更顺",
        "好运不吵，悄悄把路铺平了",
        "心态在线，小麻烦基本能搞定",
        "平平安安，今天适合稳步推进",
        "云淡风轻，事情会比想象简单",
        "手感回升，做完一件是一件",
        "靠谱发挥，普通日子也有盼头",
        "小有收获，努力没有白白浪费",
        "气氛不错，聊天办事都挺顺",
        "稳中带甜，生活给了颗小糖",
        "进展缓慢，但方向看起来没跑偏",
        "人缘尚可，关键消息来得刚好",
        "状态回正，适合把欠账慢慢清",
        "风浪不大，今天能平稳靠岸",
        "好运轻敲，别急着把门关上",
        "计划能动，虽然不快但很扎实",
        "小确幸在线，晚饭可能特别香",
        "心里有谱，事情基本不会失控",
        "普通但顺，今天适合安静变好",
    ]),
    ("小吉", "🟡", [
        "勉强能行，别把难度开太高",
        "小风小浪，问题不大但挺烦",
        "运气微亮，像手机还剩百分二十",
        "凑合不错，至少没有突然翻车",
        "缓慢回血，先把今天糊过去",
        "好运摸鱼，偶尔出来打个卡",
        "状态一般，但还能靠意志硬撑",
        "小赚一点，快乐像试用版会员",
        "别太激动，惊喜可能只有半份",
        "能过就行，细节先别太较真",
        "轻微顺利，像电梯刚好没关门",
        "运势及格，主打一个差不多",
        "脑子慢热，下午可能突然上线",
        "事情能成，就是过程有点磨叽",
        "快乐有限，但也不是完全没有",
        "小小转机，别嫌它来得低调",
        "今天不差，适合低成本开心",
        "能量半格，省着点用也够了",
        "小吉小吉，主打一个没白抽",
        "运气路过，顺手留下点零食",
    ]),
    ("末吉", "🟠", [
        "今天适合躺平，少折腾少背锅",
        "运势偏弱，先把基本盘守住",
        "别硬刚了，能拖一拖也是智慧",
        "心累预警，建议降低人生期待",
        "事情有点卡，先喝口水再说",
        "别太上头，今天适合保守操作",
        "能不加戏，就别给生活递剧本",
        "状态掉线，早点休息比硬撑强",
        "小坑不少，走路都建议看脚下",
        "计划缩水，能完成一半也算赢",
        "情绪别炸，世界暂时有点卡顿",
        "今日低电量，社交能省则省",
        "别追求完美，别翻车就算发挥",
        "风向一般，安静待机更划算",
        "灵感请假，脑子暂时不接单",
        "适合装忙，不适合主动揽活",
        "进度随缘，别跟自己死磕",
        "钱包别动，冲动消费容易后悔",
        "先别立旗，今天旗子容易倒",
        "保持低调，熬过今天就是胜利",
    ]),
    ("凶", "🔴", [
        "诸事不宜，早点下班最有性价比",
        "今天别赌，连硬币都可能叛逆",
        "运气休假，重要决定改天再议",
        "水逆感很强，先别挑战高难度",
        "别硬冲了，生活正在加载补丁",
        "脑子罢工，先别写长篇大论",
        "今日易翻车，安全带先系紧",
        "手气很迷，抽卡前请冷静三秒",
        "钱包告急，购物车先别清空",
        "情绪易燃，建议远离无效争论",
        "事情不顺，但至少还能笑一笑",
        "运势掉线，刷新也未必有用",
        "今日不宜嘴快，沉默能省麻烦",
        "麻烦冒头，先装作信号不好",
        "计划易碎，别把希望全压上",
        "状态离谱，适合早点洗洗睡",
        "别立大志，今天先活着就很棒",
        "运气堵车，好消息可能迟到",
        "别碰玄学，连抽签都在叹气",
        "今日主打避险，能苟住就是赢",
    ]),
]

_DEFAULT_WEIGHTS = [12, 23, 30, 20, 15]

# ── JSON 文件路径 ──────────────────────────────────────────────────

_LOTS_PATH = Path("data/lots.json")

# ── 缓存 ────────────────────────────────────────────────────────────

_lots_cache: tuple[list, list] | None = None


def _build_default_lots() -> tuple[list, list]:
    """将硬编码的默认数据转为标准化格式（levels 列表 + weights 列表）。"""
    levels = [
        {"name": name, "emoji": emoji, "phrases": list(phrases)}
        for name, emoji, phrases in _DEFAULT_LEVELS
    ]
    return levels, list(_DEFAULT_WEIGHTS)


def load_lots_config() -> dict:
    """读取当前抽签配置，返回标准化 dict。

    加载顺序：JSON 文件 → 代码默认值。

    Returns:
        {"weights": [...], "levels": [{"name": str, "emoji": str, "phrases": [...]}, ...]}
    """
    levels, weights = _get_lots()
    return {"weights": weights, "levels": levels}


def save_lots_config(data: dict) -> None:
    """保存抽签配置到 JSON 文件并清除缓存。

    Args:
        data: {"weights": [...], "levels": [...]}

    Raises:
        ValueError: 格式校验失败时抛出。
    """
    weights = data.get("weights", [])
    levels = data.get("levels", [])

    # ── 恢复默认：空数据 → 删除 JSON 文件 ──────────────────────
    if (not weights or len(weights) == 0) and (not levels or len(levels) == 0):
        if _LOTS_PATH.exists():
            _LOTS_PATH.unlink()
        reset_lots_cache()
        logger.info("抽签配置已恢复为默认值（删除了 lots.json）")
        return

    # ── 校验 ──────────────────────────────────────────────────────
    if not isinstance(weights, list) or not isinstance(levels, list):
        raise ValueError("weights 和 levels 必须是数组")
    if len(weights) != len(levels):
        raise ValueError(
            f"weights 长度 ({len(weights)}) 与 levels 长度 ({len(levels)}) 不一致"
        )
    if len(levels) == 0:
        raise ValueError("至少需要一个等级")
    for w in weights:
        if not isinstance(w, (int, float)) or w <= 0:
            raise ValueError(f"权重必须是正数，得到: {w}")
    for i, level in enumerate(levels):
        if not isinstance(level, dict):
            raise ValueError(f"levels[{i}] 必须是对象")
        if not level.get("name", "").strip():
            raise ValueError(f"levels[{i}] 缺少名称")
        phrases = level.get("phrases", [])
        if not isinstance(phrases, list) or len(phrases) == 0:
            raise ValueError(f"「{level.get('name', i)}」至少需要一条签文")

    # ── 写入 ──────────────────────────────────────────────────────
    _LOTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _LOTS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_LOTS_PATH)

    # 清除缓存
    reset_lots_cache()
    logger.info("抽签配置已保存到 %s", _LOTS_PATH)


def reset_lots_cache() -> None:
    """清除抽签缓存，下次调用 _get_lots() 时重新加载。"""
    global _lots_cache
    _lots_cache = None


def _load_lots_from_json() -> tuple[list, list] | None:
    """从 JSON 文件加载抽签配置。失败返回 None。"""
    if not _LOTS_PATH.exists():
        return None
    try:
        data = json.loads(_LOTS_PATH.read_text(encoding="utf-8"))
        weights = data.get("weights", [])
        levels = data.get("levels", [])

        # 快速校验（不做完整校验——save 时已经校验过；这里只防文件被手动损坏）
        if not weights or not levels or len(weights) != len(levels):
            logger.warning("lots.json 格式无效，使用默认签文")
            return None
        for level in levels:
            if not level.get("phrases"):
                logger.warning("lots.json 存在空签文等级，使用默认签文")
                return None

        return levels, weights
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("无法读取 lots.json (%s)，使用默认签文", e)
        return None


def _get_lots() -> tuple[list, list]:
    """获取当前抽签数据（带缓存）。

    Returns:
        (levels, weights) — levels 是 list[dict]，weights 是 list[float]。
    """
    global _lots_cache
    if _lots_cache is not None:
        return _lots_cache

    loaded = _load_lots_from_json()
    if loaded is not None:
        _lots_cache = loaded
    else:
        _lots_cache = _build_default_lots()

    return _lots_cache


# ── 抽签 ────────────────────────────────────────────────────────


def draw_lots(requester_name: str) -> str:
    """抽签 — 返回带解读的运势结果。

    优先使用 data/lots.json 中的自定义配置，文件不存在时使用默认签文。
    """
    levels_data, weights = _get_lots()

    # 构建 (label, emoji, phrases) 元组列表，兼容 random.choices
    lots = [
        (level["name"], level.get("emoji", ""), level["phrases"])
        for level in levels_data
    ]

    (label, emoji, phrases), = random.choices(lots, weights=weights, k=1)
    phrase = random.choice(phrases)
    return (
        f"@{requester_name} 抽签结果：{emoji} {label}\n"
        f"{phrase}"
    )
