# main.py — 中文版 + 週期判斷 + 倉位建議 + 逃頂策略 + 市場風險分數 + 7&30天趨勢 + BTC/ETH 宏觀策略

import json
from pathlib import Path
from datetime import datetime, timedelta

from repo_liquidity import (
    get_latest_repo_info,
    build_report_text as build_repo_text,
    assess_repo_stress,
    RepoDataError,
)
from tga_monitor import get_tga_status, build_tga_text, TGADataError
from rrp_monitor import get_rrp_status, build_rrp_text, RRPDataError
from fed_bs_monitor import get_fed_bs_status, build_fed_bs_text, FedBSDataError
from net_liquidity import (
    get_net_liquidity_status,
    build_net_liquidity_text,
    NetLiqDataError,
)

from yield_curve import (
    get_yield_curve,
    build_yield_curve_text,
    YieldCurveError,
)
from cds_monitor import (
    get_us_5y_cds,
    build_cds_text,
    CDSDataError,
)
from generate_chart import generate_liquidity_chart

from telegram_client import (
    send_telegram_message,
    send_telegram_photo,
    TelegramError,
)

from crypto_integration import build_btc_eth_section  # 串接 BTC / ETH 宏觀策略區

# 是否同時發送短版與長版
SEND_BOTH_TEXTS = True  # True = 發短版摘要 + 完整報告；False = 只發完整報告

# 歷史紀錄檔案，用來算 7天 / 30天 趨勢與週期變化
HISTORY_FILE = Path(__file__).resolve().parent / "liquidity_history.json"


# ---------------------------------------------------------
# 工具：讀寫歷史資料
# ---------------------------------------------------------
def load_history() -> list:
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        return []


def save_history(history: list) -> None:
    # 只保留最近 400 筆，避免無限膨脹
    if len(history) > 400:
        # 按日期排序後保留最後 400
        def _parse_date(x):
            try:
                return datetime.strptime(x.get("date", "1900-01-01"), "%Y-%m-%d")
            except Exception:
                return datetime(1900, 1, 1)

        history = sorted(history, key=_parse_date)[-400:]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def find_reference_entry(history: list, today_date, lookback_days: int):
    """
    找一筆「距離 today_date - lookback_days 最近」的歷史資料
    沒有就回傳 None
    """
    if not history:
        return None

    target = today_date - timedelta(days=lookback_days)
    best = None
    best_diff = None

    for h in history:
        d_str = h.get("date")
        if not d_str:
            continue
        try:
            d = datetime.strptime(d_str, "%Y-%m-%d").date()
        except Exception:
            continue
        diff = abs((d - target).days)
        if best is None or diff < best_diff:
            best = h
            best_diff = diff

    return best


# ---------------------------------------------------------
# 動態 Summary：流動性 / 壓力 / 景氣（中文）
# ---------------------------------------------------------
def build_dynamic_summary(nl_yoy, repo_level, yc_spread) -> str:
    # 1) 流動性（看 Net Liquidity YoY）
    if nl_yoy is None:
        liq_phrase = "流動性訊號不明"
    else:
        if nl_yoy > 5:
            liq_phrase = "流動性偏多"
        elif nl_yoy > -5:
            liq_phrase = "流動性中性"
        else:
            liq_phrase = "流動性偏緊"

    # 2) Repo 壓力
    if repo_level is None:
        repo_phrase = "金融壓力不明"
    else:
        if repo_level <= 1:
            repo_phrase = "金融壓力低"
        elif repo_level == 2:
            repo_phrase = "金融壓力略升"
        elif repo_level == 3:
            repo_phrase = "金融壓力升溫"
        else:
            repo_phrase = "金融壓力偏高"

    # 3) 景氣循環（2Y–10Y 利差）
    if yc_spread is None:
        cycle_phrase = "景氣訊號不明"
    else:
        if yc_spread < -0.5:
            cycle_phrase = "景氣風險偏高（深度倒掛）"
        elif yc_spread < 0:
            cycle_phrase = "景氣偏弱（倒掛）"
        elif yc_spread < 0.5:
            cycle_phrase = "景氣修復中"
        else:
            cycle_phrase = "景氣偏強"

    return f"📌 *總結：{liq_phrase}、{repo_phrase}、{cycle_phrase}。*"


# ---------------------------------------------------------
# 加密週期判斷 + 倉位建議（中文）
# ---------------------------------------------------------
def classify_crypto_cycle(nl_yoy, repo_level, yc_spread):
    """
    回傳：
    {
        "stage": "Early Bull",
        "label": "早期牛市",
        "short": "...一句話說明",
        "position": "...倉位建議說明（文字）",
    }
    """
    if nl_yoy is None or repo_level is None or yc_spread is None:
        return {
            "stage": "Unknown",
            "label": "週期不明",
            "short": "關鍵指標不足，暫不對加密週期下結論。",
            "position": "倉位建議：維持中性曝險，重點放在風險控管與現金流，而非加槓桿博弈。",
        }

    # 1）熊市 / 崩盤式熊市
    if nl_yoy <= -5:
        if repo_level >= 3:
            return {
                "stage": "Capitulation Bear",
                "label": "崩盤式熊市",
                "short": "流動性急凍、金融壓力偏高，市場處於恐慌與被動砍倉階段。",
                "position": (
                    "倉位建議：總體加密曝險控制在 10–30%，以 BTC/ETH 為主，"
                    "避免槓桿與高風險山寨，現金與穩定幣應維持 70% 以上。"
                ),
            }
        else:
            return {
                "stage": "Early/Mid Bear",
                "label": "熊市階段",
                "short": "流動性持續收縮，反彈多為技術性，整體仍偏空。",
                "position": (
                    "倉位建議：總體加密曝險約 20–40%，核心持倉以 BTC/ETH 為主，"
                    "山寨僅少量試單，重心放在風險控制與資本保全。"
                ),
            }

    # 2）轉折期（熊轉牛、築底區）
    if -5 < nl_yoy <= 0:
        if repo_level <= 2:
            return {
                "stage": "Transition",
                "label": "轉折期（築底）",
                "short": "流動性收縮趨緩，市場進入築底與換手階段。",
                "position": (
                    "倉位建議：總體加密曝險 30–50%，分批買入 BTC/ETH，"
                    "採用『慢慢買、不要一次梭哈』的節奏，保留 50% 左右現金 / 穩定幣。"
                ),
            }
        else:
            return {
                "stage": "Stress Transition",
                "label": "壓力型轉折期",
                "short": "流動性接近谷底但金融壓力偏高，易出現最後一殺後 V 型反轉。",
                "position": (
                    "倉位建議：總體加密曝險 20–40%，耐心等待極端恐慌時分批進場，"
                    "避免追高反彈，優先鎖定 BTC/ETH 而非高風險題材幣。"
                ),
            }

    # 3）早期牛市
    if 0 < nl_yoy <= 5:
        if yc_spread < 0:
            return {
                "stage": "Early Bull",
                "label": "早期牛市",
                "short": "流動性由負轉正，景氣仍偏弱，但資金已開始回流風險資產。",
                "position": (
                    "倉位建議：總體加密曝險 50–70%，其中 BTC+ETH 佔 70–90%，"
                    "山寨幣控制在 10–30%，以主流與高品質題材為主。"
                ),
            }
        else:
            return {
                "stage": "Late Transition",
                "label": "轉牛前夕",
                "short": "流動性微增、景氣開始修復，牛市起跑線已接近。",
                "position": (
                    "倉位建議：總體加密曝險 40–60%，逐步提高 BTC/ETH 比重，"
                    "等確定放量與趨勢形成後，再增加山寨曝險。"
                ),
            }

    # 4）主升段牛市
    if 5 < nl_yoy <= 15:
        if repo_level <= 2:
            return {
                "stage": "Mid Bull",
                "label": "主升段牛市",
                "short": "流動性充沛、金融壓力低，風險資產處於順風期。",
                "position": (
                    "倉位建議：總體加密曝險 70–100%（視個人風險承受度），"
                    "BTC/ETH 約佔 50–70%，其餘配置於高品質主題幣（如 L2、AI、公鏈）。"
                ),
            }
        else:
            return {
                "stage": "Volatile Bull",
                "label": "震盪型牛市",
                "short": "流動性強但偶有壓力升溫，波動加大但中期仍偏多。",
                "position": (
                    "倉位建議：總體加密曝險 60–80%，搭配嚴格風險控管，"
                    "逢急漲減碼、急跌再接，避免滿倉硬扛全程震盪。"
                ),
            }

    # 5）末升段牛市（逃頂區）
    if nl_yoy > 15:
        return {
            "stage": "Late Bull",
            "label": "末升段牛市",
            "short": "流動性過熱且動能可能鈍化，市場易進入瘋狂與分配階段。",
            "position": (
                "倉位建議：總體加密曝險逐步降到 40–60%，"
                "提高穩定幣與現金比重，針對高估標的分批獲利了結，準備下一輪週期的子彈。"
            ),
        }

    return {
        "stage": "Unknown",
        "label": "週期不明",
        "short": "模型未覆蓋的區間，需搭配價格結構與鏈上指標綜合判斷。",
        "position": "倉位建議：維持中性到略低曝險，避免押注單一方向。",
    }


def build_crypto_cycle_line(info) -> str:
    return f"📊 *加密週期：{info['label']}* — {info['short']}"


def build_position_advice_line(info) -> str:
    return f"🧭 *倉位建議* — {info['position']}"


# ---------------------------------------------------------
# 逃頂策略 Top Risk 判斷（中文）
# ---------------------------------------------------------
def escape_top_signal(nl_yoy, repo_level, yc_spread) -> str:
    if nl_yoy is None or repo_level is None or yc_spread is None:
        return "🟨 *逃頂判斷：訊號不足* — 關鍵指標不完整，暫不啟動逃頂策略，只建議維持中性風險。"

    flags = 0

    # 1）流動性過熱
    if nl_yoy > 10:
        flags += 1

    # 2）Repo 壓力升溫
    if repo_level >= 3:
        flags += 1

    # 3）殖利率曲線接近轉正或已轉正（晚周期）
    if yc_spread is not None and yc_spread > -0.1:
        flags += 1

    # 4）流動性由高檔快速掉頭（這裡簡化成 YoY < 2，代表水龍頭關閉）
    if nl_yoy < 2:
        flags += 1

    if flags >= 2:
        return (
            "🟥 *逃頂判斷：建議啟動逃頂策略* — 流動性過熱或下彎、"
            "金融壓力升溫或景氣接近轉折，風險資產可能進入末升段與分配期。"
        )

    if flags == 1:
        return (
            "🟨 *逃頂判斷：觀察高峰風險* — 出現單一高風險訊號，建議收斂槓桿、"
            "提高嚴格停損與分批獲利，留意後續是否出現更多壓力訊號。"
        )

    return (
        "🟩 *逃頂判斷：不建議逃頂* — 流動性仍健康、金融壓力有限、"
        "景氣尚未進入明確晚周期，較適合順勢持有而非大幅撤退。"
    )


def build_escape_top_line(nl_yoy, repo_level, yc_spread) -> str:
    return escape_top_signal(nl_yoy, repo_level, yc_spread)


# ---------------------------------------------------------
# 市場風險分數 0–100（整合流動性 / 壓力 / 景氣）
# ---------------------------------------------------------
def compute_market_risk_score(nl_yoy, repo_level, yc_spread):
    if nl_yoy is None or repo_level is None or yc_spread is None:
        return None

    # 流動性風險
    if nl_yoy <= -10:
        risk_nl = 80
    elif nl_yoy <= -5:
        risk_nl = 65
    elif nl_yoy <= 0:
        risk_nl = 55
    elif nl_yoy <= 5:
        risk_nl = 40
    elif nl_yoy <= 15:
        risk_nl = 30
    else:  # 過熱
        risk_nl = 60

    # Repo 壓力
    if repo_level <= 0:
        risk_repo = 20
    elif repo_level == 1:
        risk_repo = 30
    elif repo_level == 2:
        risk_repo = 45
    elif repo_level == 3:
        risk_repo = 65
    else:
        risk_repo = 80

    # 景氣循環（倒掛／修復）
    if yc_spread < -0.5:
        risk_yc = 50
    elif yc_spread < 0:
        risk_yc = 55
    elif yc_spread < 0.5:
        risk_yc = 65
    else:
        risk_yc = 75

    score = int(round((risk_nl + risk_repo + risk_yc) / 3))
    score = max(0, min(100, score))
    return score


def build_risk_score_line(nl_yoy, repo_level, yc_spread) -> str:
    score = compute_market_risk_score(nl_yoy, repo_level, yc_spread)
    if score is None:
        return "⚠️ *市場風險分數：N/A* — 關鍵指標不足，暫不給定整體風險評級。"

    if score < 35:
        level = "低風險（偏安全）"
        comment = "流動性良好且壓力有限，市場整體風險偏低。"
    elif score < 60:
        level = "中性風險"
        comment = "部分指標出現雜訊，但尚未形成系統性壓力。"
    elif score < 80:
        level = "偏高風險"
        comment = "流動性或金融壓力指標有明顯緊縮跡象，需嚴控槓桿與倉位。"
    else:
        level = "極高風險"
        comment = "多項指標同時偏向緊縮或晚周期，需高度警戒可能的劇烈修正。"

    return f"⚠️ *市場風險分數：{score}/100（{level}）* — {comment}"


# ---------------------------------------------------------
# 週期等級排序，用來判斷「週期變化箭頭」
# ---------------------------------------------------------
_STAGE_ORDER = [
    "Capitulation Bear",
    "Early/Mid Bear",
    "Stress Transition",
    "Transition",
    "Late Transition",
    "Early Bull",
    "Mid Bull",
    "Volatile Bull",
    "Late Bull",
]


def get_stage_rank(stage: str):
    try:
        return _STAGE_ORDER.index(stage)
    except ValueError:
        return None


# ---------------------------------------------------------
# 7 天 / 30 天 趨勢 + 週期變化
# ---------------------------------------------------------
def build_trend_sections(today_snapshot: dict, history: list):
    """
    today_snapshot = {
        "date": "YYYY-MM-DD",
        "nl_yoy": float,
        "repo_level": int,
        "yc_spread": float,
        "stage": "Early Bull",
        "label": "早期牛市",
    }
    """
    lines_7 = []
    lines_30 = []
    cycle_shift_line = None

    today_date = datetime.strptime(today_snapshot["date"], "%Y-%m-%d").date()

    ref_7 = find_reference_entry(history, today_date, 7)
    ref_30 = find_reference_entry(history, today_date, 30)

    # --- 7 天趨勢 ---
    if ref_7 is None:
        lines_7.append("📉 *指標趨勢（過去 7 天）*：歷史資料不足。")
    else:
        lines_7.append("📉 *指標趨勢（過去 7 天）*")

        # 流動性
        d_nl = today_snapshot["nl_yoy"] - ref_7.get("nl_yoy", today_snapshot["nl_yoy"])
        if d_nl > 0.1:
            nl_text = "改善（↑）"
        elif d_nl < -0.1:
            nl_text = "惡化（↓）"
        else:
            nl_text = "持平（→）"

        # Repo
        d_repo = today_snapshot["repo_level"] - ref_7.get("repo_level", today_snapshot["repo_level"])
        if d_repo < 0:
            repo_text = "壓力下降（↓）"
        elif d_repo > 0:
            repo_text = "壓力上升（↑）"
        else:
            repo_text = "持平（→）"

        # Yield curve
        d_yc = today_snapshot["yc_spread"] - ref_7.get("yc_spread", today_snapshot["yc_spread"])
        if d_yc > 0.02:
            yc_text = "倒掛縮小（↑）"
        elif d_yc < -0.02:
            yc_text = "倒掛擴大（↓）"
        else:
            yc_text = "持平（→）"

        lines_7.append(f"• 流動性 YoY：{nl_text}")
        lines_7.append(f"• Repo 壓力：{repo_text}")
        lines_7.append(f"• 殖利率曲線：{yc_text}")

    # --- 30 天趨勢 ---
    if ref_30 is None:
        lines_30.append("📆 *指標趨勢（過去 30 天）*：歷史資料不足。")
    else:
        lines_30.append("📆 *指標趨勢（過去 30 天）*")

        # 流動性數值變化
        nl_from = ref_30.get("nl_yoy")
        nl_to = today_snapshot["nl_yoy"]
        if nl_from is not None and nl_to is not None:
            lines_30.append(
                f"• 流動性 YoY：由 {nl_from:.2f}% → {nl_to:.2f}%"
            )

        # Repo level
        repo_from = ref_30.get("repo_level")
        repo_to = today_snapshot["repo_level"]
        if repo_from is not None and repo_to is not None:
            lines_30.append(f"• Repo：Level {repo_from} → Level {repo_to}")

        # Yield curve
        yc_from = ref_30.get("yc_spread")
        yc_to = today_snapshot["yc_spread"]
        if yc_from is not None and yc_to is not None:
            lines_30.append(
                f"• 殖利率曲線：{yc_from:.2f}% → {yc_to:.2f}%"
            )

    # --- 週期變化（用 30 天，沒有就用 7 天） ---
    prev = ref_30 or ref_7
    curr_label = today_snapshot.get("label")
    curr_stage = today_snapshot.get("stage")

    if prev and curr_label:
        prev_label = prev.get("label", "未知")
        prev_stage = prev.get("stage", None)
        arrow = "➝"
        r_prev = get_stage_rank(prev_stage)
        r_curr = get_stage_rank(curr_stage)
        if r_prev is not None and r_curr is not None:
            if r_curr > r_prev:
                arrow = "🔼"
            elif r_curr < r_prev:
                arrow = "🔽"
            else:
                arrow = "➡️"

        cycle_shift_line = f"🔄 *週期變化* — 從「{prev_label}」{arrow}「{curr_label}」"
    else:
        cycle_shift_line = "🔄 *週期變化* — 歷史資料不足，尚無明確比較。"

    return lines_7, lines_30, cycle_shift_line


# ---------------------------------------------------------
# 短版摘要訊息組裝
# ---------------------------------------------------------
def build_brief_message(
    summary_line: str,
    cycle_line: str,
    escape_line: str,
    risk_line: str,
    position_line: str,
    trend_7_lines: list,
    trend_30_lines: list,
    cycle_shift_line: str,
) -> str:
    """
    建立發到 Telegram 的短版摘要訊息
    """
    brief_lines = []
    brief_lines.append("📌【短版摘要】")
    brief_lines.append("")
    brief_lines.append(summary_line)
    brief_lines.append(cycle_line)
    brief_lines.append(escape_line)
    brief_lines.append(risk_line)
    brief_lines.append(position_line)
    brief_lines.append("")
    brief_lines.extend(trend_7_lines)
    brief_lines.append("")
    brief_lines.extend(trend_30_lines)
    brief_lines.append("")
    brief_lines.append(cycle_shift_line)
    return "\n".join(brief_lines)


# ---------------------------------------------------------
# 主程式：組合所有文字 + 圖片
# ---------------------------------------------------------
def run_liquidity_dashboard() -> None:
    lines = []
    warnings = []

    nl_yoy = None
    repo_level = None
    yc_spread = None

    try:
        # 1) Net Liquidity
        nl_info = get_net_liquidity_status()
        nl_text = build_net_liquidity_text(nl_info)
        nl_yoy = nl_info.get("yoy")

        # 2) Repo 壓力
        repo_info = get_latest_repo_info(lookback_days=120)
        repo_text = build_repo_text(repo_info)
        repo_level, repo_label, _ = assess_repo_stress(repo_info["latest_value"])

        # 3) Yield Curve（2Y–10Y 利差）
        yc_info = None
        try:
            yc_info = get_yield_curve()
            yc_spread = yc_info.get("spread")
        except YieldCurveError:
            yc_spread = None

        # 4) 週期 + 倉位 + 逃頂 + 風險分數
        cycle_info = classify_crypto_cycle(nl_yoy, repo_level, yc_spread)

        summary_line = build_dynamic_summary(nl_yoy, repo_level, yc_spread)
        cycle_line = build_crypto_cycle_line(cycle_info)
        escape_line = build_escape_top_line(nl_yoy, repo_level, yc_spread)
        risk_line = build_risk_score_line(nl_yoy, repo_level, yc_spread)
        position_line = build_position_advice_line(cycle_info)

        # 5) 建立今日 snapshot 並載入歷史做 7/30 天趨勢
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        today_snapshot = {
            "date": today_str,
            "nl_yoy": nl_yoy,
            "repo_level": repo_level,
            "yc_spread": yc_spread,
            "stage": cycle_info.get("stage"),
            "label": cycle_info.get("label"),
        }
        history = load_history()
        trend_7_lines, trend_30_lines, cycle_shift_line = build_trend_sections(
            today_snapshot, history
        )

        # --- 頭部：Summary + 週期 + 逃頂 + 風險 + 倉位 ---
        lines.append(summary_line)
        lines.append(cycle_line)
        lines.append(escape_line)
        lines.append(risk_line)
        lines.append(position_line)
        lines.append("")

        # --- BTC / ETH 宏觀策略區（用 macro_context 丟給 crypto_integration） ---
        macro_context = {
            "nl_yoy": nl_yoy,
            "repo_level": repo_level,
            "yc_spread": yc_spread,
            "cycle_stage": cycle_info.get("stage"),
            "cycle_label": cycle_info.get("label"),
            "risk_score": compute_market_risk_score(nl_yoy, repo_level, yc_spread),
            "escape_comment": escape_top_signal(nl_yoy, repo_level, yc_spread),
        }
        btc_eth_lines = build_btc_eth_section(macro_context)
        lines.extend(btc_eth_lines)
        lines.append("")

        # --- 7 / 30 天趨勢 + 週期變化 ---
        lines.extend(trend_7_lines)
        lines.append("")
        lines.extend(trend_30_lines)
        lines.append("")
        lines.append(cycle_shift_line)
        lines.append("")

        # --- 規則型警報：Pivot & QT 終點 ---
        if repo_level is not None and repo_level >= 3 and nl_yoy is not None and nl_yoy > 0:
            warnings.append(
                "🔔 *流動性轉折訊號：Repo 壓力升溫 + Net Liquidity 年增率轉正* — "
                "通常意味著政策有停止 QT、甚至偏向寬鬆的壓力。"
            )
        if repo_level is not None and repo_level >= 4:
            warnings.append(
                "⚠️ *高機率：Fed QT 接近終點* — Repo 進入高壓區，"
                "若搭配金融市場明顯波動，歷史上常見劇本是停止縮表或啟動類 QE。"
            )

        if warnings:
            lines.append("🚨 *關鍵流動性訊號*")
            lines.extend(warnings)
            lines.append("")

        # --- 詳細指標內容 ---
        # Net Liquidity 詳細
        lines.append("📈 *美國流動性總覽 Dashboard*")
        lines.append("")
        lines.append(nl_text)
        lines.append("")

        # Repo 詳細
        lines.append(repo_text)
        lines.append("")

        # TGA
        tga_info = get_tga_status()
        tga_text = build_tga_text(tga_info)
        lines.append(tga_text)
        lines.append("")

        # RRP
        rrp_info = get_rrp_status()
        rrp_text = build_rrp_text(rrp_info)
        lines.append(rrp_text)
        lines.append("")

        # Fed 資產負債表
        fed_bs_info = get_fed_bs_status()
        fed_bs_text = build_fed_bs_text(fed_bs_info)
        lines.append(fed_bs_text)
        lines.append("")

        # Yield Curve 詳細
        if yc_info is not None:
            yc_text = build_yield_curve_text(yc_info)
            lines.append(yc_text)
            lines.append("")
        else:
            lines.append("📉 *Yield Curve（2Y–10Y）*：資料取得失敗")
            lines.append("")

        # CDS（成功才顯示）
        try:
            cds_info = get_us_5y_cds()
            cds_text = build_cds_text(cds_info)
            lines.append(cds_text)
            lines.append("")
        except CDSDataError:
            pass

        # --- 組裝完整長版文字 ---
        full_text = "\n".join(lines)

        # --- 組裝短版摘要 ---
        brief_text = build_brief_message(
            summary_line,
            cycle_line,
            escape_line,
            risk_line,
            position_line,
            trend_7_lines,
            trend_30_lines,
            cycle_shift_line,
        )

        # --- 發送 Telegram 文字 ---
        if SEND_BOTH_TEXTS:
            send_telegram_message(brief_text)
            send_telegram_message("📚【完整報告】\n\n" + full_text)
        else:
            # 如果之後只想要其中一種，可在這裡調整
            send_telegram_message(full_text)

        print("[ok] 流動性 Dashboard 文字報告已發送到 Telegram")

        # --- 發送圖表 ---
        try:
            chart_path = generate_liquidity_chart(filepath="liquidity_dashboard.png")
            send_telegram_photo(
                chart_path,
                caption="📊 US Liquidity Dashboard（NetLiq / Repo / Yield Curve）",
            )
            print("[ok] 流動性 Dashboard 圖表已發送到 Telegram")
        except Exception as e:
            print(f"[warn] 產生或發送圖表失敗：{e}")

        # --- 更新歷史紀錄 ---
        # 若當天已有紀錄，覆蓋；否則 append
        updated = False
        for h in history:
            if h.get("date") == today_str:
                h.update(today_snapshot)
                updated = True
                break
        if not updated:
            history.append(today_snapshot)
        save_history(history)

    except (
        RepoDataError,
        TGADataError,
        RRPDataError,
        FedBSDataError,
        NetLiqDataError,
        TelegramError,
    ) as e:
        print(f"[error] {e}")


if __name__ == "__main__":
    run_liquidity_dashboard()
