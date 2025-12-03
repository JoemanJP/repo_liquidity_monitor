# tga_monitor.py
import os
import datetime as dt
from typing import Dict, Any, List, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

FRED_API_KEY = os.getenv("FRED_API_KEY")
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
# Treasury General Account (TGA)
FRED_SERIES_ID = "WTREGEN"


class TGADataError(Exception):
    pass


def _fetch_observations(
    series_id: str, start_date: str, end_date: str
) -> List[Dict[str, Any]]:
    if not FRED_API_KEY:
        raise TGADataError("FRED_API_KEY 未設定")

    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date,
        "observation_end": end_date,
    }
    resp = requests.get(FRED_BASE_URL, params=params, timeout=15)
    if resp.status_code != 200:
        raise TGADataError(f"FRED API 回應失敗: {resp.status_code} {resp.text}")

    data = resp.json()
    observations = data.get("observations", [])
    cleaned = [
        {"date": obs["date"], "value": float(obs["value"])}
        for obs in observations
        if obs.get("value") not in (None, ".", "")
    ]
    if not cleaned:
        raise TGADataError("TGA 資料為空")
    cleaned.sort(key=lambda x: x["date"])
    return cleaned


def _find_year_ago(observations: List[Dict[str, Any]], latest_date: str) -> Dict[str, Any]:
    latest_dt = dt.date.fromisoformat(latest_date)
    target = latest_dt - dt.timedelta(days=365)

    candidate = None
    for obs in observations:
        obs_dt = dt.date.fromisoformat(obs["date"])
        if obs_dt <= target:
            candidate = obs
        else:
            break

    if candidate is None:
        raise TGADataError("找不到一年前可用 TGA 資料點")
    return candidate


def get_tga_status(lookback_days: int = 400) -> Dict[str, Any]:
    today = dt.date.today()
    start = today - dt.timedelta(days=lookback_days)
    obs = _fetch_observations(FRED_SERIES_ID, start.isoformat(), today.isoformat())

    latest = obs[-1]
    year_ago = _find_year_ago(obs, latest["date"])

    latest_val = latest["value"]
    year_ago_val = year_ago["value"]
    yoy = None
    if year_ago_val != 0:
        yoy = (latest_val - year_ago_val) / year_ago_val * 100.0

    return {
        "latest_date": latest["date"],
        "latest_value": latest_val,
        "year_ago_date": year_ago["date"],
        "year_ago_value": year_ago_val,
        "yoy": yoy,
    }


def build_tga_text(info: Dict[str, Any]) -> str:
    latest_date = info["latest_date"]
    latest_val = info["latest_value"]
    year_ago_date = info["year_ago_date"]
    year_ago_val = info["year_ago_value"]
    yoy = info["yoy"]

    if yoy is None:
        yoy_str = "N/A"
    else:
        yoy_str = f"{yoy:+.2f}%"

    # 簡單解讀：TGA 上升 = 民間流動性被抽走
    if yoy is None:
        comment = "TGA 年增率無法計算，需搭配其他指標觀察。"
    elif yoy > 20:
        comment = "財政部大幅提高 TGA 餘額，等於從銀行體系抽走大量現金，對風險資產偏空。"
    elif yoy > 0:
        comment = "TGA 較去年溫和上升，對流動性略帶壓力。"
    elif yoy < -20:
        comment = "TGA 明顯下降，代表政府把現金重新打回民間，對流動性偏多。"
    else:
        comment = "TGA 變化有限，對整體流動性影響中性。"

    lines = []
    lines.append("🏛 *TGA（Treasury General Account）*")
    lines.append(f"最新餘額：*{latest_val:,.1f}* 億美元（{latest_date}）")
    lines.append(f"一年前：`{year_ago_val:,.1f}` 億美元（{year_ago_date}）")
    lines.append(f"年增率 YoY：*{yoy_str}*")
    lines.append(f"解讀：{comment}")
    return "\n".join(lines)
