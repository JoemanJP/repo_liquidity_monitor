# cds_monitor.py
import requests
from bs4 import BeautifulSoup


class CDSDataError(Exception):
    pass


def get_us_5y_cds() -> dict:
    """
    MacroMicro 美國 5Y CDS（免費公開頁面）
    自動加入 User-Agent，提升成功率
    """
    url = "https://www.macromicro.me/charts/33506/us-cds"
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    }

    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        raise CDSDataError(f"MacroMicro HTTP {resp.status_code} 無法讀取頁面")

    soup = BeautifulSoup(resp.text, "lxml")

    # 最新數值在 <span class="indicator-data"> 中
    value_tag = soup.find("span", class_="indicator-data")
    if not value_tag:
        raise CDSDataError("找不到 CDS 數據（indicator-data）")

    raw = value_tag.text.replace(",", "").strip()

    return {
        "value": float(raw),
        "comment": interpret_cds(float(raw)),
    }


def interpret_cds(value: float) -> str:
    if value > 80:
        return "⚠️ 美國主權違約風險升高（CDS 達危險區）。"
    elif value > 60:
        return "美國 CDS 高於歷史常態，需注意債務上限或財政壓力。"
    elif value > 40:
        return "CDS 稍高，市場對主權風險有輕微擔憂。"
    else:
        return "CDS 正常，主權風險可控。"


def build_cds_text(info: dict) -> str:
    return (
        "🛡️ *美國 5Y CDS（主權違約風險）*\n"
        f"最新數值：*{info['value']:.1f}* bps\n"
        f"解讀：{info['comment']}"
    )
