#!/usr/bin/env python3
"""Render one approved confession and send it to the Telegram group.

Invoked by the render workflow, which passes the approved text through the
environment rather than the command line so newlines and quotes survive intact.
"""
import os
import sys

import requests

from make_post import render

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TEXT = os.environ.get("CONFESSION_TEXT", "").strip()
APPROVER = os.environ.get("APPROVER", "?")
EDITED = os.environ.get("EDITED", "") in ("true", "True", "1")

if not TEXT:
    sys.exit("CONFESSION_TEXT is empty — nothing to render")

path, size, lines = render(TEXT, "post.png")
caption = f"אושר על ידי {APPROVER}{' (נערך)' if EDITED else ''} · {size}pt, {lines} שורות"

with open(path, "rb") as fh:
    res = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendPhoto",
        data={"chat_id": CHAT_ID, "caption": caption},
        files={"photo": ("post.png", fh, "image/png")},
        timeout=120,
    ).json()

if not res.get("ok"):
    sys.exit(f"sendPhoto failed: {res.get('description')}")
print(f"sent · {size}pt, {lines} lines")
