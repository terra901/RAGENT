"""Demo 数据生成通用函数。"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

END_DATE = date(2026, 6, 2)
ROW_COUNT = 200
DAY_STEPS = [0, 1, 3, 7, 14, 30, 60, 90, 180, 360]
PAID_MEDIA = ["bytedance", "tencent", "meta", "google"]
ALL_MEDIA = PAID_MEDIA + ["organic"]
MATERIAL_TYPES = ["video", "image", "playable", "carousel"]
AD_POSITIONS = ["feed", "splash", "reward_video", "search"]
SEGMENTS = ["new_payer_d7", "high_value_user", "retained_d7", "organic_user", "risk_multi_uid_device"]


@dataclass(frozen=True)
class Game:
    """游戏基础维度。"""

    papp_id: int
    app_id: int
    cch_id: int
    bus_company_id: str
    app_type: int
    scale: float


GAMES = [
    Game(100101, 100101, 100, "t1", 1, 1.18),
    Game(100102, 100102, 100, "t1", 1, 0.96),
    Game(200201, 200201, 200, "t2", 1, 1.08),
]


def d(value: float | int) -> Decimal:
    """生成两位小数 Decimal。"""
    return Decimal(str(round(float(value), 2)))


def bitmap(label: str, i: int) -> bytes:
    """生成 demo bitmap 字段。"""
    return f"demo:{label}:{i:04d}".encode("utf-8")


def ts_for(day: date, hour: int = 10) -> int:
    """生成毫秒时间戳。"""
    return int(time.mktime((day.year, day.month, day.day, hour, 30, 0, 0, 0, -1)) * 1000)


def game(i: int) -> Game:
    """按序号选择游戏。"""
    return GAMES[i % len(GAMES)]


def media(i: int, *, allow_organic: bool = False) -> str:
    """按序号选择媒体。"""
    pool = ALL_MEDIA if allow_organic else PAID_MEDIA
    return pool[i % len(pool)]


def media_quality(name: str) -> float:
    """媒体质量系数。"""
    return {"bytedance": 1.00, "tencent": 0.94, "meta": 1.08, "google": 1.13, "organic": 1.22}[name]


def date_for(i: int, span: int = 50) -> date:
    """生成统计日期。"""
    return END_DATE - timedelta(days=i % span)


def dim(i: int, *, allow_organic: bool = False) -> dict[str, Any]:
    """生成通用广告维度。"""
    g = game(i)
    channel = media(i, allow_organic=allow_organic)
    paid = channel != "organic"
    return {
        "papp_id": g.papp_id,
        "app_id": g.app_id,
        "cch_id": g.cch_id,
        "bus_company_id": g.bus_company_id,
        "app_type": g.app_type,
        "ad_pmedia": channel,
        "ad_cch_id": 8000 + (i % 9) if paid else 0,
        "ad_account_id": f"acct_{channel}_{(i % 6) + 1:02d}" if paid else "",
        "md_traceid": f"trace_{channel}_{g.app_id}_{(i % 60) + 1:03d}" if paid else "",
        "tg_level_1": f"camp_{(i % 12) + 1:02d}" if paid else "organic",
        "tg_level_2": f"group_{(i % 18) + 1:02d}" if paid else "organic",
        "tg_level_3": f"creative_{(i % 24) + 1:02d}" if paid else "organic",
        "ad_material_id": f"mat_{(i % 40) + 1:03d}" if paid else "",
        "ad_material_type": MATERIAL_TYPES[i % len(MATERIAL_TYPES)] if paid else "organic",
        "ad_position": AD_POSITIONS[i % len(AD_POSITIONS)] if paid else "organic",
        "ad_link_id": f"link_{(i % 35) + 1:03d}" if paid else "",
        "ptid": f"pt_{(i % 4) + 1:02d}",
        "rctid": f"team_{(i % 10) + 1:02d}",
        "md_vid": f"buyer_{(i % 16) + 1:02d}" if paid else "",
    }


def max_filled_day(day: date) -> int:
    """根据日期计算最大可回填天数。"""
    age = max(0, (END_DATE - day).days)
    return max(step for step in DAY_STEPS if step <= age)


def if_filled(max_day: int, step: int, value: int) -> int:
    """未到回填天数时返回 0。"""
    return value if step <= max_day else 0


def traffic_metrics(i: int, *, allow_organic: bool = False) -> dict[str, int | Decimal]:
    """生成流量、付费、留存、LTV 指标。"""
    x = dim(i, allow_organic=allow_organic)
    q = media_quality(x["ad_pmedia"])
    base_new = int((80 + (i * 17) % 180) * game(i).scale * q * (1.0 + 0.12 * math.sin(i / 6.0)))
    spend_yuan = Decimal("0.00") if x["ad_pmedia"] == "organic" else d(base_new * (7.5 + (i % 9) * 0.9))
    pay_user = max(1, min(base_new, int(base_new * min(0.26, 0.075 + q * 0.035 + (i % 5) * 0.007))))
    pay_amt = pay_user * int((2600 + (i % 11) * 420) * q * game(i).scale)
    metrics = {
        "base_new": base_new,
        "new_device": int(base_new * (1.03 + (i % 3) * 0.04)),
        "new_role": int(base_new * (0.72 + (i % 4) * 0.035)),
        "pay_user": pay_user,
        "first_pay_user": max(1, int(pay_user * (0.42 + (i % 4) * 0.04))),
        "pay_order": max(pay_user, int(pay_user * (1.25 + (i % 5) * 0.12))),
        "pay_amt": pay_amt,
        "stat_pay_amt": int(pay_amt * 0.982),
        "spend_yuan": spend_yuan,
        "cost_cent": int(spend_yuan * 100),
    }
    for step, rate in [(1, .43), (3, .33), (7, .24), (14, .18), (30, .12), (60, .085), (90, .065), (180, .04), (360, .025)]:
        metrics[f"retain_d{step}"] = max(0, min(base_new, int(base_new * (rate + (q - 1.0) * 0.02))))
    ltv = int(pay_amt * 1.04)
    for step, mult in [(1, 1.0), (3, 1.32), (7, 1.78), (14, 2.24), (30, 3.05), (60, 3.66), (90, 4.13), (180, 5.04), (360, 5.94)]:
        metrics[f"ltv_{step}"] = int(ltv * mult)
    return metrics
