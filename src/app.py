"""Lambda entry point: collect, drop items already sent, summarize, email, remember."""

import html
import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import boto3

import fetch
import sources
from summarize import add_summaries

logging.getLogger().setLevel(logging.INFO)
log = logging.getLogger(__name__)

EMAIL = os.environ["EMAIL"]
TABLE = boto3.resource("dynamodb").Table(os.environ["SEEN_TABLE"])
SES = boto3.client("sesv2")
SEEN_TTL_DAYS = 60
TZ = ZoneInfo(os.environ.get("DIGEST_TZ", "America/Los_Angeles"))

SECTIONS = [
    ("blogs", "From the AI labs"),
    ("news", "News"),
    ("hn", "On Hacker News"),
    ("github", "Trending repos"),
]


def _unseen(items: list[dict]) -> list[dict]:
    seen = set()
    urls = [it["url"] for it in items]
    for start in range(0, len(urls), 100):
        request = {TABLE.name: {"Keys": [{"url": u} for u in urls[start:start + 100]],
                                "ProjectionExpression": "#u",
                                "ExpressionAttributeNames": {"#u": "url"}}}
        while request:
            resp = TABLE.meta.client.batch_get_item(RequestItems=request)
            seen.update(r["url"] for r in resp["Responses"].get(TABLE.name, []))
            request = resp.get("UnprocessedKeys") or None
    return [it for it in items if it["url"] not in seen]


def _mark_seen(items: list[dict]) -> None:
    expires = int(time.time()) + SEEN_TTL_DAYS * 86400
    with TABLE.batch_writer() as batch:
        for it in items:
            batch.put_item(Item={"url": it["url"], "expires": expires})


def _render(items: list[dict], today: str) -> str:
    esc = html.escape
    parts = [f'<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
             f'max-width:640px;color:#1a1a1a;line-height:1.45">'
             f'<h2 style="margin-bottom:4px">AI digest</h2>'
             f'<div style="color:#666;margin-bottom:20px">{esc(today)}</div>']
    for key, heading in SECTIONS:
        rows = [it for it in items if it["section"] == key]
        if not rows:
            continue
        parts.append(f'<h3 style="border-bottom:1px solid #ddd;padding-bottom:4px">{heading}</h3>')
        for it in rows:
            meta = esc(it["source"]) + (f" · {it['extra']}" if it["extra"] else "")
            parts.append(
                f'<p style="margin:0 0 14px"><a href="{esc(it["url"], quote=True)}" '
                f'style="font-weight:600;color:#0b57d0;text-decoration:none">{esc(it["title"])}</a>'
                f'<br><span style="color:#666;font-size:13px">{meta}</span>'
                + (f'<br>{esc(it["summary"])}' if it["summary"] else "") + "</p>")
    parts.append("</div>")
    return "".join(parts)


def handler(event, context):
    dry_run = bool((event or {}).get("dry_run"))
    items = _unseen(fetch.collect())
    if not items:
        return {"sent": False, "reason": "nothing new"}

    # Haiku scores every candidate; keep the count bounded so the call stays cheap.
    # Dates are UTC ISO strings, so they sort as text. Undated items (HN, GitHub) go last
    # and, since the sort is stable, keep their source order (points, stars).
    items.sort(key=lambda it: it["published"] or "", reverse=True)
    candidates = items[: sources.MAX_CANDIDATES]
    add_summaries(candidates)

    # Each section shows its top-scored items. Without scores (the call failed),
    # it falls back to newest first across all sources.
    capped = []
    for key, _ in SECTIONS:
        rows = [it for it in candidates if it["section"] == key
                and (it["score"] is None or it["score"] >= sources.MIN_SCORE)]
        rows.sort(key=lambda it: -(it["score"] or 0))  # stable: ties stay newest first
        capped += rows[: sources.MAX_PER_SECTION[key]]
    log.info("%d new items, %d scored, %d in email", len(items), len(candidates), len(capped))
    today = datetime.now(TZ).strftime("%A, %B %-d")
    body = _render(capped, today)
    if dry_run:
        return {"sent": False, "dry_run": True, "items": len(capped), "html": body,
                "scored": [{"section": it["section"], "score": it["score"], "source": it["source"],
                            "title": it["title"], "shown": it in capped} for it in candidates]}

    SES.send_email(
        FromEmailAddress=f"AI Digest <{EMAIL}>",
        Destination={"ToAddresses": [EMAIL]},
        Content={"Simple": {"Subject": {"Data": f"AI digest · {today}"},
                            "Body": {"Html": {"Data": body}}}},
    )
    _mark_seen(capped)
    return {"sent": True, "items": len(capped)}
