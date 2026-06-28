"""Demo 表数据生成器。"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from .common import DAY_STEPS, END_DATE, ROW_COUNT, SEGMENTS, bitmap, date_for, dim, game, if_filled, max_filled_day, traffic_metrics, ts_for

TABLES = [
    "ads_buy_channel_roi_daily", "ads_cohort_pivot", "ads_material_daily", "ads_op_game_overview_daily",
    "dws_v4_ad_cost_daily", "dws_v4_cohort_device", "dws_v4_cohort_user",
    "dws_v4_device_daily", "dws_v4_user_daily", "dws_v4_user_segment",
]


def ads_buy_channel_roi_daily() -> list[dict[str, Any]]:
    """生成买量渠道 ROI 日表。"""
    rows = []
    for i in range(ROW_COUNT):
        x, day, m = dim(i), date_for(i, 80), traffic_metrics(i)
        max_day = max_filled_day(day)
        row = {k: x[k] for k in ["papp_id", "app_id", "cch_id", "bus_company_id", "ptid", "rctid", "md_vid", "ad_pmedia", "tg_level_1", "tg_level_2", "tg_level_3"]}
        row.update(stat_date=day, spend=m["spend_yuan"], platform_new_user_cnt=int(m["base_new"] * 1.08), game_new_user_cnt=m["base_new"], new_device_cnt=m["new_device"], new_role_cnt=m["new_role"], pay_user_cnt=m["pay_user"], first_pay_user_cnt=m["first_pay_user"], pay_amt_sum=m["pay_amt"])
        add_retain_ltv(row, m, max_day)
        row.update(max_ltv_day_filled=max_day, is_spend_synced=1, last_update_ts=ts_for(day, 9))
        rows.append(row)
    return rows


def ads_cohort_pivot() -> list[dict[str, Any]]:
    """生成 cohort 宽表。"""
    rows = []
    for i in range(ROW_COUNT):
        x, day, m = dim(i, allow_organic=True), END_DATE - timedelta(days=i % 140), traffic_metrics(i, allow_organic=True)
        max_day = max_filled_day(day)
        row = {k: x[k] for k in ["papp_id", "app_id", "cch_id", "bus_company_id", "ad_pmedia", "ad_cch_id", "tg_level_1", "tg_level_2", "tg_level_3", "ad_material_id", "ad_material_type", "ad_position", "ad_link_id"]}
        row.update(enter_date=day, is_platform_new_user=0 if x["ad_pmedia"] == "organic" and i % 2 == 0 else 1, enter_user_cnt=m["base_new"], enter_device_cnt=m["new_device"], enter_pay_user_cnt=m["pay_user"], enter_pay_device_cnt=max(1, int(m["pay_user"] * .96)))
        add_retain_ltv(row, m, max_day)
        row.update(max_day_filled=max_day, is_finalized=1 if max_day >= 360 else 0, last_update_ts=ts_for(day, 11))
        rows.append(row)
    return rows


def ads_material_daily() -> list[dict[str, Any]]:
    """生成素材日报。"""
    rows = []
    for i in range(ROW_COUNT):
        x, day, m = dim(i), date_for(i, 80), traffic_metrics(i)
        row = {k: x[k] for k in ["papp_id", "app_id", "cch_id", "bus_company_id", "ad_pmedia", "ad_cch_id", "tg_level_1", "tg_level_2", "tg_level_3", "ad_material_id", "ad_material_type", "ad_position", "ad_link_id"]}
        row.update(stat_date=day, platform_new_user_cnt=int(m["base_new"] * 1.08), game_new_user_cnt=m["base_new"], pay_user_cnt=m["pay_user"], pay_order_cnt=m["pay_order"], pay_amt_sum=m["pay_amt"], statistical_pay_amt_sum=m["stat_pay_amt"])
        add_retain_ltv(row, m, max_filled_day(day))
        row.update(enter_pay_user_cnt=max(1, int(m["pay_user"] * .70)), is_finalized=0, last_update_ts=ts_for(day, 10))
        rows.append(row)
    return rows


def ads_op_game_overview_daily() -> list[dict[str, Any]]:
    """生成游戏运营总览日报。"""
    rows = []
    for i in range(ROW_COUNT):
        g, day, m = game(i), date_for(i, 70), traffic_metrics(i, allow_organic=True)
        max_day = max_filled_day(day)
        row = {"stat_date": day, "papp_id": g.papp_id, "app_id": g.app_id, "cch_id": g.cch_id, "bus_company_id": g.bus_company_id}
        row.update(dau=int(m["base_new"] * 3.2), dar=int(m["base_new"] * 3.5), login_cnt=int(m["base_new"] * 7.1), platform_new_user_cnt=int(m["base_new"] * 1.08), game_new_user_cnt=m["base_new"], ad_new_user_cnt=int(m["base_new"] * .68), organic_new_user_cnt=int(m["base_new"] * .32), new_role_cnt=m["new_role"], pay_user_cnt=m["pay_user"], first_pay_user_cnt=m["first_pay_user"], pay_amt_sum=m["pay_amt"], statistical_pay_amt_sum=m["stat_pay_amt"], refund_amt_sum=int(m["pay_amt"] * .01))
        for step in [1, 3, 7, 14, 30]:
            row[f"retain_d{step}_cnt"] = if_filled(max_day, step, m[f"retain_d{step}"])
        row.update(ltv_7d=if_filled(max_day, 7, m["ltv_7"]), ltv_30d=if_filled(max_day, 30, m["ltv_30"]), max_retain_day_filled=max_day, is_finalized=1, last_update_ts=ts_for(day, 12))
        rows.append(row)
    return rows


def dws_v4_ad_cost_daily() -> list[dict[str, Any]]:
    """生成广告成本日报。"""
    rows = []
    for i in range(ROW_COUNT):
        x, day, m = dim(i), date_for(i, 80), traffic_metrics(i)
        row = {k: x[k] for k in ["papp_id", "app_id", "cch_id", "md_traceid", "ad_pmedia", "ad_cch_id", "ad_account_id", "tg_level_1", "tg_level_2", "tg_level_3", "ad_material_id", "ad_position"]}
        impressions = max(1000, int(m["base_new"] * 120))
        clicks = max(1, int(impressions * .03))
        row.update(stat_date=day, currency="CNY", cost_amt=m["cost_cent"], impression_cnt=impressions, click_cnt=clicks, platform_convert_cnt=max(1, int(clicks * .1)), is_finalized=2, sync_ts=ts_for(day + timedelta(days=1), 5))
        rows.append(row)
    return rows


def cohort_row(i: int, *, device: bool) -> dict[str, Any]:
    """生成 cohort 用户/设备明细行。"""
    day_n = DAY_STEPS[i % len(DAY_STEPS)]
    enter = END_DATE - timedelta(days=(i % 50) + day_n)
    x, m = dim(i, allow_organic=True), traffic_metrics(i, allow_organic=True)
    base = m["new_device"] if device else m["base_new"]
    row = {k: x[k] for k in ["papp_id", "app_id", "cch_id", "app_type", "md_traceid", "ad_cch_id", "ad_account_id", "tg_level_1", "tg_level_2", "tg_level_3", "ad_material_id", "ad_position"]}
    row.update(enter_date=enter, enter_hour=i % 24, day_n=day_n, is_filled=1, d0_pay_amt=int(m["pay_amt"] * .7), day_n_pay_amt=int(m["pay_amt"] * max(.04, (day_n + 1) / 360)), day_n_pay_order_cnt=max(1, int(m["pay_order"] * .5)), cum_pay_amt=m["ltv_360"], cum_pay_order_cnt=m["pay_order"] + day_n, uid_cnt_on_device=1 if device else None)
    prefix = "device" if device else "user"
    row[f"d0_enter_{prefix}_cnt"] = base
    row[f"d0_pay_{prefix}_cnt"] = m["pay_user"]
    row[f"d0_enter_{prefix}_bitmap"] = bitmap(f"d0_enter_{prefix}", i)
    row[f"d0_pay_{prefix}_bitmap"] = bitmap(f"d0_pay_{prefix}", i)
    row[f"retain_{prefix}_cnt"] = int(base * .24)
    row[f"retain_{prefix}_bitmap"] = bitmap(f"retain_{prefix}", i)
    row[f"pay_retain_{prefix}_cnt"] = int(m["pay_user"] * .3)
    row[f"pay_retain_{prefix}_bitmap"] = bitmap(f"pay_retain_{prefix}", i)
    row[f"day_n_pay_{prefix}_cnt"] = max(1, int(m["pay_user"] * .2))
    row[f"day_n_pay_{prefix}_bitmap"] = bitmap(f"day_n_pay_{prefix}", i)
    row[f"cum_pay_{prefix}_cnt"] = m["pay_user"] + day_n
    row[f"cum_pay_{prefix}_bitmap"] = bitmap(f"cum_pay_{prefix}", i)
    if not device:
        row["d0_reg_user_cnt"] = int(base * .94)
    return {k: v for k, v in row.items() if v is not None}


def dws_v4_cohort_device() -> list[dict[str, Any]]:
    """生成设备 cohort 表。"""
    return [cohort_row(i, device=True) for i in range(ROW_COUNT)]


def dws_v4_cohort_user() -> list[dict[str, Any]]:
    """生成用户 cohort 表。"""
    return [cohort_row(i, device=False) for i in range(ROW_COUNT)]


def dws_v4_device_daily() -> list[dict[str, Any]]:
    """生成设备日报。"""
    return [device_or_user_daily(i, device=True) for i in range(ROW_COUNT)]


def dws_v4_user_daily() -> list[dict[str, Any]]:
    """生成用户日报。"""
    return [device_or_user_daily(i, device=False) for i in range(ROW_COUNT)]


def device_or_user_daily(i: int, *, device: bool) -> dict[str, Any]:
    """生成用户/设备日报行。"""
    x, day, m = dim(i, allow_organic=True), date_for(i, 50), traffic_metrics(i, allow_organic=True)
    row = {k: x[k] for k in ["papp_id", "app_id", "cch_id", "app_type", "md_traceid", "ad_cch_id", "ad_account_id", "tg_level_1", "tg_level_2", "tg_level_3", "ad_material_id", "ad_position"]}
    row.update(stat_date=day, stat_hour=i % 24, is_finalized=1)
    if device:
        row.update(activate_cnt=int(m["new_device"] * 1.12), new_device_cnt=m["new_device"], new_device_bitmap=bitmap("new_device", i), ad_new_device_cnt=int(m["new_device"] * .86), organic_new_device_cnt=int(m["new_device"] * .14))
    else:
        row.update(login_user_cnt=int(m["base_new"] * 1.8), login_device_cnt=int(m["base_new"] * 1.6), login_user_bitmap=bitmap("login_user", i), new_enter_user_cnt=m["base_new"], new_enter_device_cnt=m["new_device"], new_enter_user_bitmap=bitmap("new_enter_user", i), reg_user_cnt=int(m["base_new"] * .92), reg_device_cnt=int(m["new_device"] * .9), reg_user_bitmap=bitmap("reg_user", i), new_role_cnt=m["new_role"], new_enter_role_cnt=int(m["new_role"] * .96), trans_amt=m["pay_amt"], pay_user_cnt=m["pay_user"], pay_order_cnt=m["pay_order"], pay_user_bitmap=bitmap("pay_user", i), first_pay_amt=int(m["pay_amt"] * .38), first_pay_user_cnt=m["first_pay_user"], first_pay_user_bitmap=bitmap("first_pay_user", i))
    return row


def dws_v4_user_segment() -> list[dict[str, Any]]:
    """生成用户分群表。"""
    rows = []
    for i in range(ROW_COUNT):
        g, seg = game(i), SEGMENTS[i % len(SEGMENTS)]
        base = traffic_metrics(i, allow_organic=True)["base_new"]
        rows.append({"enter_date": END_DATE - timedelta(days=i % 100), "papp_id": g.papp_id, "app_id": g.app_id, "cch_id": g.cch_id, "segment_key": seg, "user_bitmap": bitmap(seg, i), "user_cnt": max(1, int(base * .12)), "computed_ts": ts_for(END_DATE, 3)})
    return rows


def add_retain_ltv(row: dict[str, Any], metrics: dict[str, Any], max_day: int) -> None:
    """向行内补充留存和 LTV 字段。"""
    for step in [1, 3, 7, 14, 30, 60, 90, 180, 360]:
        row[f"ltv_{step}d"] = if_filled(max_day, step, metrics[f"ltv_{step}"])
    for step in [1, 3, 7, 14, 30, 60, 90, 180, 360]:
        row[f"retain_d{step}_cnt"] = if_filled(max_day, step, metrics[f"retain_d{step}"])


GENERATORS = {name: globals()[name] for name in TABLES}
