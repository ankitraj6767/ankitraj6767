#!/usr/bin/env python3
"""Generate a GitHub language snapshot SVG for a profile README.

Data source:
- Public repos: GitHub REST /users/{username}/repos + /repos/{owner}/{repo}/languages
- Private repos: set PROFILE_STATS_TOKEN with access to the repos you want counted.

This is intentionally generated into the repository so the README is stable, fast,
and not dependent on third-party language-card caching.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USERNAME = os.getenv("GITHUB_USERNAME", "ankitraj6767")
TOKEN = os.getenv("PROFILE_STATS_TOKEN") or ""
PUBLIC_ONLY = os.getenv("PUBLIC_ONLY", "false").lower() == "true"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "assets"))
SVG_PATH = OUTPUT_DIR / "language-snapshot.svg"
JSON_PATH = OUTPUT_DIR / "language-snapshot.json"
API_ROOT = "https://api.github.com"

LANG_COLORS = {
    "TypeScript": "#3178C6",
    "JavaScript": "#F1E05A",
    "Java": "#B07219",
    "Dart": "#00B4AB",
    "Python": "#3572A5",
    "C++": "#F34B7D",
    "C": "#555555",
    "HTML": "#E34C26",
    "CSS": "#563D7C",
    "SCSS": "#C6538C",
    "Shell": "#89E051",
    "PLpgSQL": "#336790",
    "SQL": "#E38C00",
    "Go": "#00ADD8",
    "Ruby": "#701516",
    "PHP": "#4F5D95",
    "Kotlin": "#A97BFF",
    "Swift": "#F05138",
    "Vue": "#41B883",
    "Jupyter Notebook": "#DA5B0B",
}

EXCLUDED_REPOS = {USERNAME.lower()}  # exclude profile repo from language totals by default
EXCLUDED_LANGUAGES = {"Profile"}


def request_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USERNAME}-profile-language-snapshot",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    req = Request(url, headers=headers)
    for attempt in range(3):
        try:
            with urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {403, 429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(2**attempt)
                continue
            raise
        except URLError:
            if attempt < 2:
                time.sleep(2**attempt)
                continue
            raise


def list_repos() -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    page = 1
    while True:
        if TOKEN and not PUBLIC_ONLY:
            params = urlencode({
                "affiliation": "owner",
                "visibility": "all",
                "per_page": 100,
                "page": page,
                "sort": "updated",
            })
            url = f"{API_ROOT}/user/repos?{params}"
        else:
            params = urlencode({"per_page": 100, "page": page, "sort": "updated"})
            url = f"{API_ROOT}/users/{USERNAME}/repos?{params}"

        chunk = request_json(url)
        if not chunk:
            break
        repos.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
    return repos


def aggregate_languages(repos: list[dict[str, Any]]) -> tuple[dict[str, int], list[dict[str, Any]]]:
    totals: dict[str, int] = {}
    counted_repos: list[dict[str, Any]] = []

    for repo in repos:
        name = repo.get("name", "")
        if name.lower() in EXCLUDED_REPOS:
            continue
        if repo.get("fork") or repo.get("archived"):
            continue

        full_name = repo.get("full_name")
        if not full_name:
            continue

        languages_url = f"{API_ROOT}/repos/{full_name}/languages"
        try:
            languages = request_json(languages_url)
        except Exception as exc:  # keep one bad/private repo from breaking the profile
            print(f"WARN: failed language fetch for {full_name}: {exc}", file=sys.stderr)
            continue

        repo_total = 0
        for language, byte_count in languages.items():
            if language in EXCLUDED_LANGUAGES:
                continue
            byte_count = int(byte_count)
            if byte_count <= 0:
                continue
            totals[language] = totals.get(language, 0) + byte_count
            repo_total += byte_count

        if repo_total > 0:
            counted_repos.append({
                "name": full_name,
                "private": bool(repo.get("private")),
                "pushed_at": repo.get("pushed_at"),
                "bytes": repo_total,
            })

    return totals, counted_repos


def escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def human_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    n = float(value)
    for unit in units:
        if n < 1024 or unit == units[-1]:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{value} B"


def color_for(language: str, index: int) -> str:
    fallback = ["#60A5FA", "#A78BFA", "#34D399", "#FBBF24", "#FB7185", "#22D3EE", "#F97316", "#84CC16"]
    return LANG_COLORS.get(language, fallback[index % len(fallback)])


def render_svg(totals: dict[str, int], counted_repos: list[dict[str, Any]], generated_at: str, includes_private: bool) -> str:
    total_bytes = sum(totals.values())
    width = 920
    height = 455

    if total_bytes <= 0:
        return f'''<svg width="{width}" height="260" viewBox="0 0 {width} 260" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">Live Language Snapshot</title>
  <desc id="desc">No repository language data could be generated.</desc>
  <rect width="{width}" height="260" rx="22" fill="#0B1120"/>
  <rect x="1" y="1" width="{width-2}" height="258" rx="21" stroke="#334155"/>
  <text x="36" y="58" fill="#E5E7EB" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="26" font-weight="800">Live Language Snapshot</text>
  <text x="36" y="102" fill="#94A3B8" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="16">No language data found yet. Run the workflow or add PROFILE_STATS_TOKEN for private repos.</text>
  <text x="36" y="220" fill="#64748B" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="13">Generated {escape(generated_at)}</text>
</svg>'''

    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    top = ranked[:10]
    other = sum(v for _, v in ranked[10:])
    if other:
        top.append(("Other", other))

    bar_x, bar_y, bar_w, bar_h = 36, 108, 848, 22
    x = bar_x
    segments: list[str] = []
    min_visible = 3
    for index, (language, byte_count) in enumerate(top):
        raw_w = (byte_count / total_bytes) * bar_w
        seg_w = max(min_visible, raw_w) if raw_w > 0 else 0
        if x + seg_w > bar_x + bar_w:
            seg_w = max(0, bar_x + bar_w - x)
        color = "#64748B" if language == "Other" else color_for(language, index)
        if seg_w > 0:
            segments.append(f'<rect x="{x:.2f}" y="{bar_y}" width="{seg_w:.2f}" height="{bar_h}" fill="{color}"/>')
            x += seg_w

    legend_items: list[str] = []
    for index, (language, byte_count) in enumerate(top[:10]):
        pct = (byte_count / total_bytes) * 100
        col = index % 2
        row = index // 2
        lx = 48 + col * 430
        ly = 170 + row * 43
        color = "#64748B" if language == "Other" else color_for(language, index)
        legend_items.append(f'<circle cx="{lx}" cy="{ly - 5}" r="6" fill="{color}"/>')
        legend_items.append(f'<text x="{lx + 16}" y="{ly}" fill="#E5E7EB" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="15" font-weight="700">{escape(language)}</text>')
        legend_items.append(f'<text x="{lx + 205}" y="{ly}" fill="#94A3B8" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="14">{pct:.2f}% • {human_bytes(byte_count)}</text>')

    latest_push = "No pushes found"
    pushed_values = [repo.get("pushed_at") for repo in counted_repos if repo.get("pushed_at")]
    if pushed_values:
        latest_push = max(pushed_values)

    repo_label = f"{len(counted_repos)} repos counted"
    visibility_label = "public + private token" if includes_private else "public repos only"

    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">Live Language Snapshot</title>
  <desc id="desc">Aggregated GitHub repository language usage for {escape(USERNAME)}.</desc>
  <defs>
    <linearGradient id="card" x1="0" y1="0" x2="920" y2="455" gradientUnits="userSpaceOnUse">
      <stop stop-color="#020617"/>
      <stop offset="0.45" stop-color="#0F172A"/>
      <stop offset="1" stop-color="#111827"/>
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="18" result="blur"/>
      <feColorMatrix in="blur" type="matrix" values="0 0 0 0 0.23 0 0 0 0 0.51 0 0 0 0 0.96 0 0 0 .28 0"/>
      <feBlend in="SourceGraphic"/>
    </filter>
    <clipPath id="barClip"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="11"/></clipPath>
  </defs>
  <rect width="{width}" height="{height}" rx="24" fill="url(#card)"/>
  <rect x="1" y="1" width="{width-2}" height="{height-2}" rx="23" stroke="#334155"/>
  <circle cx="820" cy="78" r="120" fill="#2563EB" opacity="0.12" filter="url(#glow)"/>
  <circle cx="110" cy="370" r="110" fill="#7C3AED" opacity="0.10" filter="url(#glow)"/>

  <text x="36" y="52" fill="#F8FAFC" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="26" font-weight="900">Live Language Snapshot</text>
  <text x="36" y="80" fill="#94A3B8" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="14">GitHub Languages API • {escape(repo_label)} • {escape(visibility_label)}</text>

  <g clip-path="url(#barClip)">
    <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" fill="#1E293B"/>
    {' '.join(segments)}
  </g>
  <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="11" stroke="#475569" opacity="0.7"/>

  {''.join(legend_items)}

  <rect x="36" y="385" width="848" height="42" rx="14" fill="#0F172A" stroke="#1E293B"/>
  <text x="56" y="411" fill="#CBD5E1" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="13">Updated: {escape(generated_at)} UTC</text>
  <text x="474" y="411" fill="#64748B" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="13">Latest repository push: {escape(latest_push)}</text>
</svg>'''


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    repos = list_repos()
    totals, counted_repos = aggregate_languages(repos)
    includes_private = bool(TOKEN and not PUBLIC_ONLY)

    SVG_PATH.write_text(render_svg(totals, counted_repos, generated_at, includes_private), encoding="utf-8")
    JSON_PATH.write_text(
        json.dumps(
            {
                "username": USERNAME,
                "generated_at_utc": generated_at,
                "source": "GitHub REST languages endpoint",
                "includes_private_token": includes_private,
                "counted_repositories": counted_repos,
                "total_bytes": sum(totals.values()),
                "languages": dict(sorted(totals.items(), key=lambda item: item[1], reverse=True)),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
