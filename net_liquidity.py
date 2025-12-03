# net_liquidity.py
import os
import datetime as dt
from typing import Dict, Any, List

import requests
from dotenv import load_dotenv

load_dotenv()

FRED_API_KEY = os.getenv("FRED_API_KEY")
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

SERIES_WALCL = "WALCL"
SERIES_TGA = "WTREGEN"
SERIES_RRP = "RRPONTSYD"


class NetLiqDataError(Exception):
    pass


def _fetch_series(
    series_id: str, start_date: str, end_date: str
) -> Dict[str, float]:
    """
    回傳 {date_str: value} dict
    """
    if not FRED_API_KEY:
        raise NetLiqDataError("FRED_API_KEY 未設定")

    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date,
        "observation_end": end_date,
    }
    resp = requests.get(FRED_BASE_URL, params=params, timeout=15)
    if resp.status_code != 200:
        raise NetLiqDataError(
            f"FRED API ({series_id}) 回應失敗: {resp.status_code} {resp.text}"
        )

    data = resp.json()
    observations = data.get("observations", [])
    if not observations:
        raise NetLiqDataError(f"{series_id} 資料為空")

    series = {}
    for obs in observations:
        val = obs.get("value")
        if val in (None, ".", ""):
            continue
        series[obs["date"]] = float(val)
    if not series:
        raise NetLiqDataError(f"{series_id} 無有效數值")
    return series


def _find_latest_common_date(series_dicts: List[Dict[str, float]]) -> str:
    common_dates = set(series_dicts[0].keys())
    for s in series_dicts[1:]:
        common_dates &= set(s.keys())
    if not common_dates:
        raise NetLiqDataError("找不到共同日期（最新）")
    return max(common_dates)


def _find_year_ago_common_date(series_dicts: List[Dict[str, float]], latest_date: str) -> str:
    latest_dt = dt.date.fromisoformat(latest_date)
    target = latest_dt - dt.timedelta(days=365)

    # 只保留 <= target 的日期再取最大
    common_dates = set(series_dicts[0].keys())
    for s in series_dicts[1:]:
        common_dates &= set(s.keys())
    candidates = [d for d in common_dates if dt.date.fromisoformat(d) <= target]
    if not candidates:
        raise NetLiqDataError("找不到共同日期（一年前附近）")
    return max(candidates)


def get_net_liquidity_status(lookback_days: int = 500) -> Dict[str, Any]:
    today = dt.date.today()
    start = today - dt.timedelta(days=lookback_days)
    start_str = start.isoformat()
    end_str = today.isoformat()

    walcl = _fetch_series(SERIES_WALCL, start_str, end_str)
    tga = _fetch_series(SERIES_TGA, start_str, end_str)
    rrp = _fetch_series(SERIES_RRP, start_str, end_str)

    series_list = [walcl, tga, rrp]

    latest_date = _find_latest_common_date(series_list)
    year_ago_date = _find_year_ago_common_date(series_list, latest_date)

    latest_val = walcl[latest_date] - tga[latest_date] - rrp[latest_date]
    prev_val = walcl[year_ago_date] - tga[year_ago_date] - rrp[year_ago_date]

    yoy = None
    if prev_val != 0:
        yoy = (latest_val - prev_val) / prev_val * 100.0

    return {
        "latest_date": latest_date,
        "latest_value": latest_val,
        "year_ago_date": year_ago_date,
        "year_ago_value": prev_val,
        "yoy": yoy,
    }


def build_net_liquidity_text(info: Dict[str, Any]) -> str:
    latest_date = info["latest_date"]
    latest_val = info["latest_value"]
    year_ago_date = info["year_ago_date"]
    year_ago_val = info["year_ago_value"]
    yoy = info["yoy"]

    if yoy is None:
        yoy_str = "N/A"
    else:
        yoy_str = f"{yoy:+.2f}%"

    if yoy is None:
        comment = "Net Liquidity 年增率無法計算。"
    elif yoy > 5:
        comment = "Net Liquidity 年增率轉正且明顯上升，代表整體流動性在回補，對風險資產偏多。"
    elif yoy > -5:
        comment = "Net Liquidity 約持平，流動性對市場影響中性。"
    else:
        comment = "Net Liquidity 年增率為負，代表政策仍在抽水階段，對風險資產偏空。"

    lines = []
    lines.append("🌊 *Net Liquidity（WALCL − TGA − RRP）*")
    lines.append(f"最新值：*{latest_val:,.1f}* 億美元（{latest_date}）")
    lines.append(f"一年前：`{year_ago_val:,.1f}` 億美元（{year_ago_date}）")
    lines.append(f"年增率 YoY：*{yoy_str}*")
    lines.append(f"總體解讀：{comment}")
    return "\n".join(lines)
