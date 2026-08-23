#!/usr/bin/env python3
"""Send the rendered image back to Telegram with its approve buttons.

The approval that matters happens here rather than on the text. Text reading
well is not the same as the post looking right — a long confession drops to a
smaller font and can end up cramped — so nothing is scheduled until someone has
seen this picture and tapped 👍.

The buttons carry the Apps Script key, which arrives in the dispatch payload,
so the taps route straight back to the pending confession.

Publishing is not done here. Apps Script owns that, through Composio, at the
minute the confession is due.

Runs with `if: always()`, so it has to report a failed render or staging step
too — a silent workflow failure would leave someone waiting for a picture that
is never coming.
"""
import os
import sys

import requests

TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHAT = os.environ["TELEGRAM_CHAT_ID"]
IMAGE_URL = os.environ.get("IMAGE_URL", "").strip()
KEY = os.environ.get("KEY", "").strip()
APPROVER = os.environ.get("APPROVER", "").strip()
EDITED = os.environ.get("EDITED", "") in ("true", "True", "1")
SIZE = os.environ.get("SIZE", "").strip()
LINES = os.environ.get("LINES", "").strip()
RENDER_RESULT = os.environ.get("RENDER_RESULT", "").strip()
STAGE_RESULT = os.environ.get("STAGE_RESULT", "").strip()


def telegram(method, data, files=None):
    return requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/{method}",
        data=data, files=files, timeout=120,
    ).json()


def fail(message):
    telegram("sendMessage", {"chat_id": TG_CHAT, "text": message[:4000]})
    sys.exit(1)


def tail_log(path, lines=12):
    """The last few lines of a captured log — where the traceback ends up."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return "".join(fh.readlines()[-lines:]).strip()
    except OSError:
        return ""


if RENDER_RESULT and RENDER_RESULT != "success":
    detail = tail_log("/tmp/render.log")
    fail(
        "⚠️ הרינדור נכשל — הוידוי לא תוזמן.\n\n"
        + (detail[-1200:] if detail else "אין פרטים; בדוק את לוג ה-Actions.")
    )

# Staging is what makes the picture reachable by Instagram. Without it the
# publish would fail later with nothing to point at, so refuse to offer the
# scheduling buttons at all rather than promising something that cannot work.
if STAGE_RESULT and STAGE_RESULT != "success":
    fail(
        "⚠️ העלאת התמונה לענף media נכשלה — אי אפשר לתזמן.\n"
        "אם המאגר פרטי, raw.githubusercontent.com לא יגיש את הקובץ. "
        "בדוק את לוג ה-Actions."
    )

bits = []
if EDITED:
    bits.append("נערך")
if APPROVER:
    bits.append(f"אושר: {APPROVER}")
if SIZE and LINES:
    bits.append(f"{SIZE}pt · {LINES} שורות")
caption = "👀 נראה טוב? " + (" · ".join(bits) if bits else "")

payload = {"chat_id": TG_CHAT, "caption": caption[:1000]}

# Without a key there is nothing to route a tap back to, so send the picture
# plain rather than buttons that would silently do nothing.
if KEY:
    import json

    payload["reply_markup"] = json.dumps({
        "inline_keyboard": [[
            {"text": "👍 תזמן", "callback_data": f"img:ok:{KEY}"},
            {"text": "✏️ ערוך", "callback_data": f"img:ed:{KEY}"},
            {"text": "❌ בטל", "callback_data": f"img:no:{KEY}"},
        ]]
    })

with open("post.jpg", "rb") as fh:
    res = telegram("sendPhoto", payload, files={"photo": ("post.jpg", fh, "image/jpeg")})

if not res.get("ok"):
    print("telegram sendPhoto failed:", res.get("description"), file=sys.stderr)
    sys.exit(1)

print("staged:", IMAGE_URL or "(none)")
