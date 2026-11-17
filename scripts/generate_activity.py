#!/usr/bin/env python3
"""Render a self-hosted GitHub profile activity SVG from public repository commits.

This is intentionally a public-repository metric, not GitHub's official
contribution count. Private repositories and employer work are excluded.
"""
from __future__ import annotations

import collections
import datetime as dt
import html
import json
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request

USER = "mmmakskl"
OUTPUT = pathlib.Path("assets/activity.svg")
TOKEN = os.environ.get("GH_TOKEN", "")
NOW = dt.datetime.now(dt.timezone.utc)
SINCE = NOW - dt.timedelta(days=365)


def fetch(url: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-activity-generator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def public_commits():
    repositories = []
    for page in range(1, 5):
        url = ("https://api.github.com/users/" + USER
               + "/repos?per_page=100&type=owner&sort=updated&page=" + str(page))
        batch = fetch(url)
        repositories.extend(r for r in batch if not r.get("fork") and not r.get("private"))
        if len(batch) < 100:
            break

    dates = collections.Counter()
    scanned = 0
    # Search by GitHub author identity across non-fork public repositories.
    # GitHub's contributions calendar uses additional rules and may differ.
    for repo in repositories:
        full_name = repo["full_name"]
        page = 1
        while page <= 20:
            params = urllib.parse.urlencode({
                "author": USER,
                "since": SINCE.isoformat().replace("+00:00", "Z"),
                "until": NOW.isoformat().replace("+00:00", "Z"),
                "per_page": 100,
                "page": page,
            })
            url = "https://api.github.com/repos/" + full_name + "/commits?" + params
            try:
                batch = fetch(url)
            except urllib.error.HTTPError as err:
                if err.code == 409:  # An empty repository has no history.
                    break
                raise
            for commit in batch:
                timestamp = (commit.get("commit", {}).get("author") or {}).get("date")
                if timestamp:
                    day = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date()
                    if SINCE.date() <= day <= NOW.date():
                        dates[day] += 1
            scanned += len(batch)
            if len(batch) < 100:
                break
            page += 1
    return repositories, dates, scanned


def render(repositories, dates, scanned):
    total = sum(dates.values())
    active_days = len(dates)
    max_day = max(dates.values(), default=0)
    month_labels = []
    bars = []
    week_start = (SINCE.date() - dt.timedelta(days=SINCE.date().weekday()))
    weekly = []
    for w in range(53):
        start = week_start + dt.timedelta(weeks=w)
        count = sum(dates[start + dt.timedelta(days=j)] for j in range(7))
        weekly.append(count)
        if start.day <= 7:
            month_labels.append((w, start.strftime("%b")))
    maximum = max(weekly, default=1) or 1
    for i, count in enumerate(weekly):
        x = 38 + i * 17.25
        height = 5 + (count / maximum) * 47 if count else 5
        y = 283 - height
        color = "#67E8F9" if count else "#27364C"
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="11.5" height="{height:.1f}" rx="3" fill="{color}"/>')
    months = "".join(f'<text x="{38 + w*17.25:.1f}" y="308" fill="#93A6C3" font-size="11" font-family="Arial,sans-serif">{html.escape(label)}</text>' for w,label in month_labels)
    stamp = NOW.strftime("%Y-%m-%d %H:%M UTC")
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="345" viewBox="0 0 1000 345" role="img" aria-label="Public GitHub activity over the past 365 days">
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0D1424"/><stop offset="1" stop-color="#191C39"/></linearGradient></defs>
<rect width="1000" height="345" rx="18" fill="url(#bg)"/>
<rect x="1" y="1" width="998" height="343" rx="17" fill="none" stroke="#445273" stroke-opacity=".6"/>
<text x="37" y="41" font-family="Arial,sans-serif" font-size="20" font-weight="700" fill="#67E8F9">PUBLIC GITHUB ACTIVITY</text>
<text x="37" y="68" font-family="Arial,sans-serif" font-size="13" fill="#9EAFCA">Last 365 days · public owned non-fork repositories · authored commits</text>
<g font-family="Arial,sans-serif">
<text x="38" y="131" font-size="43" font-weight="700" fill="#F5F7FF">{total}</text>
<text x="38" y="155" font-size="14" fill="#B6C4DA">Authored commits</text>
<text x="355" y="131" font-size="43" font-weight="700" fill="#F5F7FF">{active_days}</text>
<text x="355" y="155" font-size="14" fill="#B6C4DA">Active days</text>
<text x="651" y="131" font-size="43" font-weight="700" fill="#F5F7FF">{len(repositories)}</text>
<text x="651" y="155" font-size="14" fill="#B6C4DA">Public repositories scanned</text>
<path d="M38 187H963" stroke="#35445D"/>
<text x="38" y="213" font-size="14" font-weight="700" fill="#DDE6F6">Weekly commit activity</text>
{''.join(bars)}
{months}
<text x="38" y="332" font-size="11" fill="#8D9CB8">Updated {stamp} · Not the official GitHub contributions count · Excludes private and employer work</text>
</g></svg>"""
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(svg + "\n", encoding="utf-8")


if __name__ == "__main__":
    repos, dates, scanned = public_commits()
    if not repos:
        raise SystemExit("No public owned repositories fetched; keeping the previous card")
    render(repos, dates, scanned)
    print(f"Rendered {OUTPUT}: {len(repos)} repositories, {sum(dates.values())} authored commits")
