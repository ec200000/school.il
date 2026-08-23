#!/usr/bin/env python3
"""Render one confession to post.jpg.

Instagram only accepts JPEG, and displays square posts at 1080px, so that is
what we hand it. The rendering itself is the same measured layout used for every
post on the account.
"""
import os
import sys

from make_post import render

text = os.environ.get("CONFESSION_TEXT", "").strip()
if not text:
    sys.exit("CONFESSION_TEXT is empty — nothing to render")

path, size, lines = render(text, "post.jpg", export_px=1080)
print(f"rendered {path} at {size}pt across {lines} lines")

out = os.environ.get("GITHUB_OUTPUT")
if out:
    with open(out, "a", encoding="utf-8") as fh:
        fh.write(f"size={size}\nlines={lines}\n")
