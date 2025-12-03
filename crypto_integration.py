# crypto_integration.py
#
# 把「美國流動性 + 週期判斷」轉成 BTC / ETH 的策略建議區塊。
# 目前是純「宏觀規則版」，之後可以在這裡接你的 ma_analysis / LSTM 等技術模型。

from typing import Dict, List, Tuple


def _cycle_arrow(stage: str | None) -> str:
    """
    根據週期大致給一個箭頭：
      - 熊 → 轉折 → 早牛 → 主升 → 末牛
    """
    if stage is None:
        return "➡️"

    bear_stages = {"Capitulation Bear", "Early/Mid Bear"}
    trans_stages = {"Stress Transition", "Transition", "Late Transition"}
    bull_stages = {"Early Bull", "Mid Bull", "Volatile Bull", "Late Bull"}

    if stage in bear_stages:
        return "🔽"
    if stage in trans_stages:
        return "🔼"
    if stage in bull_stages:
        return "🔼"
    return "➡️"


def _macro_risk_label(risk_score: int | None) -> str:
    if risk_score is None:
        return "未知風險"
    if risk_score < 35:
        return "低風險"
    if risk_score < 60:
        return "中性風險"
    if risk_score < 80:
        return "偏高風險"
    return "極高風險"


def _btc_eth_weight_from_macro(stage: str | None, risk_score: int | None) -> Tuple[str, str]:
    """
    根據宏觀週期 + 市場風險分數，給出 BTC / ETH 的建議相對比重說明。
    不是精確%數，而是文字等級：
      - 「偏重 BTC」
      - 「BTC / ETH 均衡」
      - 「偏重 ETH」
    """

    if stage is None or risk_score is None:
        return ("BTC / ETH 均衡", "BTC / ETH 均衡")

    # 末升段、極高風險：優先 BTC 防禦，ETH 保守
    if stage == "Late Bull" or risk_score >= 80:
        return ("偏重 BTC（防禦）", "保守配置 ETH")

    # 主升段牛市：適度拉高 ETH 比重
    if stage in {"Mid Bull", "Volatile Bull"} and (risk_score is not None and risk_score < 70):
        return ("BTC / ETH 均衡略偏 BTC", "略偏重 ETH（進攻）")

    # 早期牛市 / 轉折期：以 BTC 打底，ETH 漸進
    if stage in {"Early Bull", "Transition", "Late Transition", "Stress Transition"}:
        return ("偏重 BTC（打底）", "中性配置 ETH")

    # 熊市：全部保守
    if stage in {"Capitulation Bear", "Early/Mid Bear"}:
        return ("低配 BTC（防守）", "更低配 ETH")

    # 其他未知：均衡處理
    return ("BTC / ETH 均衡", "BTC / ETH 均衡")


def _overall_exposure_advice(stage: str | None, risk_score: int | None) -> str:
    """
    根據週期 + 風險分數，給一個「整體加密曝險區間」建議。
    不替你做交易，只給區間：
      - 10–30%
      - 20–40%
      - 40–60%
      - 60–80%
      - 70–90%
    """
    if stage is None or risk_score is None:
        return "整體加密曝險建議維持在 30–50%，以 BTC / ETH 為主，避免高槓桿。"

    # 熊市
    if stage in {"Capitulation Bear", "Early/Mid Bear"}:
        return "整體加密曝險建議 10–30%，以 BTC / ETH 為核心，避免槓桿與高風險山寨。"

    # 壓力型轉折
    if stage == "Stress Transition":
        return "整體加密曝險建議 20–40%，逢極端恐慌再分批加碼 BTC / ETH。"

    # 一般轉折
    if stage in {"Transition", "Late Transition"}:
        return "整體加密曝險建議 30–50%，以分批佈局 BTC / ETH 為主，保留 50% 左右現金 / 穩定幣。"

    # 早牛
    if stage == "Early Bull":
        return "整體加密曝險建議 50–70%，BTC / ETH 為主體，山寨控制在 10–30%。"

    # 主升段牛市
    if stage in {"Mid Bull", "Volatile Bull"} and (risk_score is not None and risk_score < 70):
        return "整體加密曝險建議 70–90%，視個人風險偏好調整，但需搭配嚴格風險控管。"

    # 末升段：開始收槓桿
    if stage == "Late Bull" or (risk_score is not None and risk_score >= 70):
        return "整體加密曝險建議逐步降至 40–60%，以分批獲利了結、提高現金 / 穩定幣比重為主。"

    return "整體加密曝險建議維持在 40–60%，以 BTC / ETH 為主，視價格結構決定是否加減碼。"


def build_btc_eth_section(macro_context: Dict) -> List[str]:
    """
    接收 main.py 傳進來的 macro_context，輸出一段文字區塊（list[str]），
    會被插入在 Telegram 報告的「宏觀結論」後面。

    macro_context 期待包含：
      - nl_yoy: float | None
      - repo_level: int | None
      - yc_spread: float | None
      - cycle_stage: str | None
      - cycle_label: str | None
      - risk_score: int | None
      - escape_comment: str
    """
    nl_yoy = macro_context.get("nl_yoy")
    repo_level = macro_context.get("repo_level")
    yc_spread = macro_context.get("yc_spread")
    stage = macro_context.get("cycle_stage")
    label = macro_context.get("cycle_label")
    risk_score = macro_context.get("risk_score")
    escape_comment = macro_context.get("escape_comment")

    arrow = _cycle_arrow(stage)
    risk_label = _macro_risk_label(risk_score)
    btc_weight_text, eth_weight_text = _btc_eth_weight_from_macro(stage, risk_score)
    exposure_text = _overall_exposure_advice(stage, risk_score)

    lines: List[str] = []

    lines.append("——— 🪙 *BTC / ETH 策略區（結合宏觀流動性）* ———")

    # 1) 週期 + 宏觀箭頭
    if label:
        lines.append(f"📊 *加密大週期*：{label} {arrow}")
    else:
        lines.append("📊 *加密大週期*：資料不足，暫無法判斷。")

    # 2) 市場風險概況
    if risk_score is not None:
        lines.append(f"⚠️ *宏觀風險評級*：{risk_score}/100（{risk_label}）")
    else:
        lines.append("⚠️ *宏觀風險評級*：N/A（資料不足）")

    # 3) 逃頂提示（直接重用前面算好的 escape_comment）
    if escape_comment:
        lines.append(escape_comment)

    lines.append("")

    # 4) 整體曝險建議（鏈接整個幣圈倉位）
    lines.append(f"📦 *整體加密曝險建議* — {exposure_text}")

    # 5) BTC / ETH 相對配置（目前先純看宏觀，之後可再加技術面）
    lines.append("")
    lines.append("₿ *BTC 配置建議* — " + btc_weight_text)
    lines.append("Ξ *ETH 配置建議* — " + eth_weight_text)

    # 6) 說明
    lines.append("")
    lines.append("📌 *說明*：以上為「宏觀層級」給出的 BTC / ETH 大方向建議，")
    lines.append("後續可以在這一區塊下方，接上你 BTC / ETH 的技術指標與 LSTM 模型輸出，形成完整可交易訊號。")

    return lines
