# repo_liquidity.py
import os
import datetime as dt
from typing import Dict, Any, List, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

FRED_API_KEY = os.getenv("FRED_API_KEY")
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
# 你現在看的指標：Overnight Repurchase Agreements: Amount of Treasury Securities Submitted
FRED_SERIES_ID = "RPONTSYSAD"


class RepoDataError(Exception):
    pass


def fetch_repo_observations(
    start_date: str, end_date: str
) -> List[Dict[str, Any]]:
    """
    從 FRED 抓 RPONTSYSAD 日資料。
    回傳 observation list，每筆含 date / value。
    """
    if not FRED_API_KEY:
        raise RepoDataError("FRED_API_KEY 未設定")

    params = {
        "series_id": FRED_SERIES_ID,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date,
        "observation_end": end_date,
    }
    resp = requests.get(FRED_BASE_URL, params=params, timeout=15)
    if resp.status_code != 200:
        raise RepoDataError(f"FRED API 回應失敗: {resp.status_code} {resp.text}")

    data = resp.json()
    observations = data.get("observations", [])
    # 過濾掉值為"." 的缺失值
    cleaned = [
        {"date": obs["date"], "value": float(obs["value"])}
        for obs in observations
        if obs.get("value") not in (None, ".", "")
    ]
    if not cleaned:
        raise RepoDataError("FRED 回傳的資料為空")
    return cleaned


def get_latest_repo_info(lookback_days: int = 120) -> Dict[str, Any]:
    """
    取得最近一筆 repo 數據 + 近7日平均等資訊。
    """
    today = dt.date.today()
    start = today - dt.timedelta(days=lookback_days)
    observations = fetch_repo_observations(
        start_date=start.isoformat(), end_date=today.isoformat()
    )

    # 依日期排序（保險起見）
    observations.sort(key=lambda x: x["date"])

    latest = observations[-1]
    latest_value = latest["value"]
    latest_date = latest["date"]

    # 最近 7 筆（不一定是 7 天，因為週末沒資料）
    last_7 = observations[-7:] if len(observations) >= 7 else observations
    avg_7 = sum(o["value"] for o in last_7) / len(last_7)

    # 找出過去一段期間內的最高值
    max_obs = max(observations, key=lambda x: x["value"])

    return {
        "latest_date": latest_date,
        "latest_value": latest_value,
        "avg_7": avg_7,
        "max_value": max_obs["value"],
        "max_date": max_obs["date"],
    }


def assess_repo_stress(value: float) -> Tuple[int, str, str]:
    """
    根據當日數值給壓力等級 0-5 + 等級標籤 + 簡短解讀。
    這裡的區間你之後可以自己微調。
    """
    if value < 5:
        level = 0
        label = "正常"
        comment = "銀行間資金充裕，尚未出現明顯流動性壓力。"
    elif value < 15:
        level = 1
        label = "輕微偏緊"
        comment = "短端美元略為吃緊，屬可控範圍，需持續觀察。"
    elif value < 30:
        level = 3
        label = "系統性壓力升溫"
        comment = "銀行體系明顯倚賴 Fed 提供流動性，類似 2019 年前期跡象。"
    elif value < 50:
        level = 4
        label = "高壓狀態"
        comment = "短端融資市場信用減弱，Fed 如持續忽略，QT 可能被迫提前結束。"
    else:
        level = 5
        label = "危險區"
        comment = "流動性已接近凍結狀態，極有可能觸發緊急操作或類 QE。"

    return level, label, comment


def build_report_text(info: Dict[str, Any]) -> str:
    """
    組合成要發到 Telegram 的文字報告。
    """
    latest_date = info["latest_date"]
    latest_value = info["latest_value"]
    avg_7 = info["avg_7"]
    max_value = info["max_value"]
    max_date = info["max_date"]

    level, label, comment = assess_repo_stress(latest_value)

    lines = []
    lines.append("📊 *美國 Repo 壓力雷達*（RPONTSYSAD）")
    lines.append(f"日期：`{latest_date}`")
    lines.append(f"當日國債提交額：*{latest_value:.1f}* 億美元")
    lines.append(f"近 7 筆平均值：`{avg_7:.2f}` 億美元")
    lines.append(f"最近波段高點：`{max_date}` = `{max_value:.1f}` 億美元")
    lines.append("")
    lines.append(f"壓力等級：*Level {level} – {label}*")
    lines.append(f"解讀：{comment}")
    lines.append("")
    # 給你策略性的簡短提示（之後你可以自己改）
    if level <= 1:
        hint = (
            "市場處於相對健康狀態，流動性尚未成為主導因子，"
            "風險資產走勢更多取決於情緒與基本面。"
        )
    elif level <= 3:
        hint = (
            "流動性開始約束銀行資產負債表，若壓力持續升高，"
            "通常會促使 Fed 放緩或終止 QT，對債券與黃金偏多。"
        )
    elif level <= 4:
        hint = (
            "短端美元市場已處於高壓狀態，任何政策轉向（結束 QT、溫和 QE）"
            "都可能帶來債券與黃金的劇烈反彈，同時為 BTC 創造中期利多。"
        )
    else:
        hint = (
            "壓力突破危險區，若搭配股市大幅回檔或信用利差擴大，"
            "通常意味著系統性風險事件逼近，隨後往往是強力寬鬆政策。"
        )

    lines.append(f"策略提示：{hint}")
    return "\n".join(lines)
