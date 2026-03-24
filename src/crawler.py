from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

ONE_MONTH_AGO = datetime.now(timezone.utc) - timedelta(days=30)
DB_PATH = "data/news.db"


@dataclass
class SourceConfig:
    name: str
    start_url: str
    allowed_prefixes: tuple[str, ...]


SOURCES = [
    SourceConfig(
        name="Council of Europe",
        start_url="https://www.coe.int/en/web/portal/newsroom",
        allowed_prefixes=("https://www.coe.int/en/web/portal/-/",),
    ),
    SourceConfig(
        name="EDPB",
        start_url="https://www.edpb.europa.eu/news/news_en",
        allowed_prefixes=("https://www.edpb.europa.eu/news/",),
    ),
    SourceConfig(
        name="EDPS",
        start_url="https://www.edps.europa.eu/press-publications/press-news/press-releases_en",
        allowed_prefixes=("https://www.edps.europa.eu/press-publications/press-news/",),
    ),
    SourceConfig(
        name="noyb",
        start_url="https://noyb.eu/en/news",
        allowed_prefixes=("https://noyb.eu/en/",),
    ),
]


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                published_at TEXT NOT NULL,
                summary TEXT,
                fetched_at TEXT NOT NULL
            )
            """
        )


def _extract_candidate_links(html: str, base_url: str) -> Iterable[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()

    for a in soup.select("a[href]"):
        href = urljoin(base_url, a["href"].strip())
        title = " ".join(a.get_text(" ", strip=True).split())
        if not title or len(title) < 8:
            continue
        if href in seen:
            continue
        seen.add(href)
        yield href, title


def _find_date_in_text(text: str) -> datetime | None:
    snippets = re.findall(r"\b\d{1,2}[./\- ]\d{1,2}[./\- ]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b", text)
    for snippet in snippets[:5]:
        try:
            dt = date_parser.parse(snippet, dayfirst=True)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _fetch_article_date(client: httpx.Client, url: str) -> tuple[datetime | None, str]:
    try:
        resp = client.get(url, timeout=20)
        resp.raise_for_status()
    except Exception:
        return None, ""

    soup = BeautifulSoup(resp.text, "html.parser")
    summary_meta = soup.find("meta", attrs={"name": "description"})
    summary = summary_meta["content"].strip() if summary_meta and summary_meta.get("content") else ""

    for selector in [
        'meta[property="article:published_time"]',
        'meta[name="date"]',
        'meta[itemprop="datePublished"]',
        "time[datetime]",
    ]:
        tag = soup.select_one(selector)
        if not tag:
            continue
        value = tag.get("content") or tag.get("datetime") or tag.get_text(" ", strip=True)
        if not value:
            continue
        try:
            dt = date_parser.parse(value)
            return (dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc), summary)
        except Exception:
            continue

    dt = _find_date_in_text(soup.get_text(" ", strip=True)[:5000])
    return dt, summary


def _should_keep(url: str, title: str, source: SourceConfig) -> bool:
    return any(url.startswith(prefix) for prefix in source.allowed_prefixes) and len(title) >= 8


def crawl_source(source: SourceConfig, client: httpx.Client) -> list[dict]:
    resp = client.get(source.start_url, timeout=20)
    resp.raise_for_status()

    rows: list[dict] = []
    for url, title in _extract_candidate_links(resp.text, source.start_url):
        if not _should_keep(url, title, source):
            continue
        date, summary = _fetch_article_date(client, url)
        if not date or date < ONE_MONTH_AGO:
            continue
        rows.append(
            {
                "source": source.name,
                "title": title,
                "url": url,
                "published_at": date.isoformat(),
                "summary": summary[:320],
            }
        )
        if len(rows) >= 25:
            break
    return rows


def save_items(items: list[dict]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    with sqlite3.connect(DB_PATH) as conn:
        for item in items:
            try:
                conn.execute(
                    """
                    INSERT INTO news_items(source, title, url, published_at, summary, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (item["source"], item["title"], item["url"], item["published_at"], item["summary"], now),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                continue
    return inserted


def run_crawler() -> dict[str, int]:
    init_db()
    stats: dict[str, int] = {}
    with httpx.Client(follow_redirects=True, headers={"User-Agent": "psp-crawler/0.1"}) as client:
        for source in SOURCES:
            try:
                items = crawl_source(source, client)
                stats[source.name] = save_items(items)
            except Exception:
                stats[source.name] = 0
    return stats


if __name__ == "__main__":
    result = run_crawler()
    for k, v in result.items():
        print(f"{k}: inserted {v}")
