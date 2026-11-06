"""Collects items from feeds, Anthropic's sitemap, Hacker News, and GitHub."""

import gzip
import html
import json
import logging
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import sources

log = logging.getLogger(__name__)
USER_AGENT = "ai-digest/1.0"
ATOM = "{http://www.w3.org/2005/Atom}"
SITEMAP = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read()
    # Some servers (DeepMind) gzip the response even when it wasn't requested.
    return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body


def _clean(text: str | None, limit: int = 400) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)  # RSS (RFC 822)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))  # Atom (ISO 8601)
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _item(section, source, title, url, snippet="", published=None, extra=""):
    return {
        "section": section,
        "source": source,
        "title": _clean(title, 200),
        "url": url.strip(),
        "snippet": _clean(snippet),
        "published": published.isoformat() if published else None,
        "extra": extra,
    }


def _feed(section: str, source: str, url: str, since: datetime) -> list[dict]:
    root = ET.fromstring(_get(url))
    items = []
    for node in root.iter("item"):  # RSS 2.0
        published = _parse_date(node.findtext("pubDate"))
        if published and published < since:
            continue
        link = node.findtext("link") or ""
        if link:
            items.append(_item(section, source, node.findtext("title"), link,
                               node.findtext("description"), published))
    for node in root.iter(f"{ATOM}entry"):  # Atom
        published = _parse_date(node.findtext(f"{ATOM}published") or node.findtext(f"{ATOM}updated"))
        if published and published < since:
            continue
        link_el = node.find(f"{ATOM}link[@rel='alternate']")
        if link_el is None:
            link_el = node.find(f"{ATOM}link")
        link = link_el.get("href", "") if link_el is not None else ""
        if link:
            items.append(_item(section, source, node.findtext(f"{ATOM}title"), link,
                               node.findtext(f"{ATOM}summary") or node.findtext(f"{ATOM}content"),
                               published))
    return items


def _anthropic(since: datetime) -> list[dict]:
    root = ET.fromstring(_get(sources.ANTHROPIC_SITEMAP))
    items = []
    for node in root.iter(f"{SITEMAP}url"):
        loc = node.findtext(f"{SITEMAP}loc") or ""
        path = urllib.parse.urlparse(loc).path
        if not any(path.startswith(p) and len(path) > len(p) for p in sources.ANTHROPIC_PATHS):
            continue
        modified = _parse_date(node.findtext(f"{SITEMAP}lastmod"))
        if not modified or modified < since:
            continue
        title = path.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").capitalize()
        items.append(_item("blogs", "Anthropic", title, loc, "", modified))
    return items


def _hacker_news() -> list[dict]:
    data = json.loads(_get("https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=50"))
    pattern = re.compile(sources.HN_KEYWORDS, re.IGNORECASE)
    items = []
    for hit in sorted(data.get("hits", []), key=lambda h: h.get("points") or 0, reverse=True):
        title = hit.get("title") or ""
        if not pattern.search(title):
            continue
        discussion = f"https://news.ycombinator.com/item?id={hit['objectID']}"
        items.append(_item("hn", "Hacker News", title, hit.get("url") or discussion,
                           hit.get("story_text") or "", None,
                           f"{hit.get('points', 0)} points · <a href=\"{discussion}\">comments</a>"))
    return items


def _github() -> list[dict]:
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
    repos = {}
    for topic in sources.GITHUB_TOPICS:
        q = urllib.parse.quote(f"topic:{topic} created:>{week_ago}")
        data = json.loads(_get(
            f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=10"))
        for repo in data.get("items", []):
            repos[repo["full_name"]] = repo
    ranked = sorted(repos.values(), key=lambda r: r["stargazers_count"], reverse=True)
    return [
        _item("github", "GitHub", r["full_name"], r["html_url"], r.get("description") or "", None,
              f"★ {r['stargazers_count']:,}" + (f" · {r['language']}" if r.get("language") else ""))
        for r in ranked
    ]


def collect() -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(hours=sources.LOOKBACK_HOURS)
    jobs = {f"blog:{name}": (_feed, "blogs", name, url, since) for name, url in sources.BLOGS.items()}
    jobs |= {f"news:{name}": (_feed, "news", name, url, since) for name, url in sources.NEWS.items()}
    jobs |= {"blog:Anthropic": (_anthropic, since), "hn": (_hacker_news,), "github": (_github,)}

    items = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {name: pool.submit(fn, *args) for name, (fn, *args) in jobs.items()}
        for name, future in futures.items():
            try:
                items.extend(future.result())
            except Exception:
                log.exception("Source %s failed; skipping it", name)

    # Drop duplicate URLs within this run (the same story can appear in two feeds).
    unique = {}
    for item in items:
        unique.setdefault(item["url"], item)
    return list(unique.values())
