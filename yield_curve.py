# yield_curve.py
import os
import datetime as dt
import requests
from typing import List, Dict, Any

from dotenv import load_dotenv
load_dotenv()

FRED_API_KEY = os.getenv("FRED_API_KEY")
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

SERIES_2Y = "DGS2"
SERIES_10Y = "DGS10"


class YieldCurveError(Exception):
    pass


def fetch_fred(series_id: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date,
        "observation_end": end_date,
    }
    resp = requests.get(FRED_BASE_URL, params=params, timeout=10)
    if resp.status_code != 200:
        raise YieldCurveError(f"FRED Error {series_id}: {resp.status_code}")

    data = resp.json()
    out = []
    for obs in data["observations"]:
        v = obs["value"]
        if v not in (None, ".", ""):
            out.append({"date": obs["date"], "value": float(v)})
    return out


def get_yield_curve(lookback_days: int = 60) -> Dict[str, Any]:
    today = dt.date.today()
    start = today - dt.timedelta(days=lookback_days)

    series_2y = fetch_fred(SERIES_2Y, start.isoformat(), today.isoformat())
    series_10y = fetch_fred(SERIES_10Y, start.isoformat(), today.isoformat())

    # 找共同日期
    dates_2y = {d["date"]: d["value"] for d in series_2y}
    dates_10y = {d["date"]: d["value"] for d in series_10y}
    common_dates = sorted(set(dates_2y.keys()) & set(dates_10y.keys()))

    if not common_dates:
        raise YieldCurveError("找不到共同日期")

    latest = common_dates[-1]

    val_2y = dates_2y[latest]
    val_10y = dates_10y[latest]
    spread = val_2y - val_10y  # 正常 > 0，倒掛 < 0

    # 判讀
    if spread < -0.75:
        comment = "殖利率深度倒掛，衰退機率偏高（歷史特徵）。"
    elif spread < 0:
        comment = "殖利率倒掛，市場仍有衰退疑慮。"
    elif spread < 0.4:
        comment = "殖利率曲線剛恢復正常化，市場開始反映經濟改善。"
    else:
        comment = "殖利率大幅正常化，市場偏向風險資產。"

    return {
        "date": latest,
        "value_2y": val_2y,
        "value_10y": val_10y,
        "spread": spread,
        "comment": comment,
    }


def build_yield_curve_text(info: Dict[str, Any]) -> str:
    lines = []
    lines.append("📉 *Yield Curve（2Y - 10Y 利差）*")
    lines.append(f"日期：`{info['date']}`")
    lines.append(f"2Y：{info['value_2y']:.2f}%")
    lines.append(f"10Y：{info['value_10y']:.2f}%")
    lines.append(f"利差（2Y–10Y）：*{info['spread']:+.2f}%*")
    lines.append(f"解讀：{info['comment']}")
    return "\n".join(lines)
