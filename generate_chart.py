# generate_chart.py
import matplotlib.pyplot as plt

from net_liquidity import get_net_liquidity_status
from repo_liquidity import get_latest_repo_info
from yield_curve import get_yield_curve


def generate_liquidity_chart(filepath: str = "liquidity_dashboard.png") -> str:
    """
    產生一張簡潔的美國流動性圖表：
    - Net Liquidity (bn USD)
    - Repo Submitted (bn USD)
    - 2Y-10Y Yield Spread (%)
    """

    # 抓數據
    nl = get_net_liquidity_status()
    repo = get_latest_repo_info()
    yc = get_yield_curve()

    netliq_val = nl["latest_value"]
    repo_val = repo["latest_value"]
    yc_spread = yc["spread"]

    labels = [
        "Net Liquidity\n(bn USD)",
        "Repo Submitted\n(bn USD)",
        "2Y-10Y Spread\n(%)",
    ]
    values = [netliq_val, repo_val, yc_spread]

    plt.figure(figsize=(9, 6))
    bars = plt.bar(range(len(labels)), values)

    # 在柱子上標數值
    for bar in bars:
        height = bar.get_height()
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            height,
            f"{height:,.1f}",
            ha="center",
            va="bottom",
            fontsize=10,
        )

    plt.xticks(range(len(labels)), labels, fontsize=10)
    plt.title("US Liquidity Snapshot – NetLiq / Repo / Yield Curve", fontsize=14)
    plt.grid(axis="y", linestyle="--", alpha=0.3)

    plt.tight_layout()
    plt.savefig(filepath, dpi=150)
    plt.close()

    return filepath
