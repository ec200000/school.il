#!/usr/bin/env python3
"""Deliver the rendered image into the Telegram group with its scheduled time.

This used to publish to Instagram as well. It no longer does: Apps Script owns
publishing now, through Composio, at the minute the confession is due. All this
job does is render, stage the JPEG on the public media branch, and show it to
whoever approved it so a bad render is caught while someone is still watching.

Runs with `if: always()`, so it has to report a failed staging step too — a
silent workflow failure would mean the publish call later finds no image and
nobody knows why.
"""
import os
import sys

import requests

TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHAT = os.environ["TELEGRAM_CHAT_ID"]
IMAGE_URL = os.environ.get("IMAGE_URL", "").strip()
SCHEDULED = os.environ.get("SCHEDULED", "").strip()
APPROVER = os.environ.get("APPROVER", "").strip()
EDITED = os.environ.get("EDITED", "") in ("true", "True", "1")
SIZE = os.environ.get("SIZE", "").strip()
LINES = os.environ.get("LINES", "").strip()
STAGE_RESULT = os.environ.get("STAGE_RESULT", "").strip()


def telegram_photo(caption):
    with open("post.jpg", "rb") as fh:
        return requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
            data={"chat_id": TG_CHAT, "caption": caption[:1000]},
            files={"photo": ("post.jpg", fh, "image/jpeg")},
            timeout=120,
        ).json()


def telegram_text(text):
    return requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        data={"chat_id": TG_CHAT, "text": text[:4000]},
        timeout=60,
    ).json()


# Staging is what makes the picture reachable. Without it the scheduled publish
# will fail later with nothing to point at, so say so now and loudly.
if STAGE_RESULT and STAGE_RESULT != "success":
    telegram_text(
        "⚠️ העלאת התמונה לענף media נכשלה.\n"
        "הפוסט מתוזמן אבל אין תמונה — הפרסום ייכשל.\n"
        "בדוק את לוג ה-Actions."
    )
    sys.exit(1)

bits = []
if SCHEDULED:
    bits.append(f"📅 {SCHEDULED}")
if EDITED:
    bits.append("נערך")
if APPROVER:
    bits.append(f"אושר: {APPROVER}")
if SIZE and LINES:
    bits.append(f"{SIZE}pt · {LINES} שורות")

caption = " · ".join(bits) if bits else "מוכן"
if not IMAGE_URL:
    caption += "\n⚠️ לא נוצר קישור ציבורי — הפרסום ייכשל"

res = telegram_photo(caption)
if not res.get("ok"):
    print("telegram sendPhoto failed:", res.get("description"), file=sys.stderr)
    sys.exit(1)

print("staged:", IMAGE_URL or "(none)")
