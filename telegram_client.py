# telegram_client.py
import os
from typing import Optional
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


class TelegramError(Exception):
    """自訂錯誤：Telegram 發送失敗"""
    pass


def _check_env():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise TelegramError("TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 未設定")


# ---------------------------------------------------------
# 1) 傳送文字訊息
# ---------------------------------------------------------
def send_telegram_message(text: str, parse_mode: Optional[str] = "Markdown") -> None:
    """
    傳送文字訊息到 Telegram
    """
    _check_env()

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    resp = requests.post(url, json=payload, timeout=20)
    if resp.status_code != 200:
        raise TelegramError(f"Telegram 發送失敗: {resp.status_code} {resp.text}")


# ---------------------------------------------------------
# 2) 傳送圖片（PNG / JPG）
# ---------------------------------------------------------
def send_telegram_photo(photo_path: str, caption: str = "", parse_mode: str = "Markdown") -> None:
    """
    傳送圖片到 Telegram
    """
    _check_env()

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    if not os.path.exists(photo_path):
        raise TelegramError(f"找不到圖片檔案: {photo_path}")

    with open(photo_path, "rb") as f:
        resp = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption,
                "parse_mode": parse_mode,
            },
            files={"photo": f},
            timeout=20,
        )

    if resp.status_code != 200:
        raise TelegramError(f"Telegram Photo 發送失敗: {resp.status_code} {resp.text}")


# ---------------------------------------------------------
# 3) 傳送一般檔案（PDF / CSV / ZIP / Excel）
# ---------------------------------------------------------
def send_telegram_document(file_path: str, caption: str = "", parse_mode: str = "Markdown") -> None:
    """
    傳送任意檔案到 Telegram（PDF / CSV / XLSX / ZIP）
    """
    _check_env()

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"

    if not os.path.exists(file_path):
        raise TelegramError(f"找不到檔案: {file_path}")

    with open(file_path, "rb") as f:
        resp = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption,
                "parse_mode": parse_mode,
            },
            files={"document": f},
            timeout=30,
        )

    if resp.status_code != 200:
        raise TelegramError(f"Telegram Document 發送失敗: {resp.status_code} {resp.text}")
