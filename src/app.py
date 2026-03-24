from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, render_template

from crawler import DB_PATH, init_db, run_crawler

app = Flask(__name__, template_folder="../templates")


def get_news():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT source, title, url, published_at, summary
            FROM news_items
            WHERE published_at >= datetime('now', '-30 day')
            ORDER BY published_at DESC
            LIMIT 200
            """
        ).fetchall()
    grouped: dict[str, list] = {}
    for row in rows:
        grouped.setdefault(row["source"], []).append(row)
    return grouped


@app.route("/")
def dashboard():
    grouped = get_news()
    total = sum(len(items) for items in grouped.values())
    return render_template(
        "dashboard.html",
        grouped=grouped,
        total=total,
        now=datetime.now(timezone.utc),
    )


def _scheduled_job():
    run_crawler()


def start_scheduler():
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(_scheduled_job, "cron", hour=1, minute=0)
    scheduler.start()


if __name__ == "__main__":
    init_db()
    run_crawler()
    start_scheduler()
    app.run(host="0.0.0.0", port=8080, debug=True)
