#!/usr/bin/env python3
"""Generate a premium technology snapshot SVG for a GitHub profile README.

What it measures:
- Language bytes from GitHub's official Languages API.
- Framework / stack signals from known dependency files such as package.json,
  pubspec.yaml, pom.xml, Gradle files, and Supabase folders.

Important:
- Dart/Flutter-heavy private repos are counted only when PROFILE_STATS_TOKEN has
  access to those repos.
- Spring Boot is a framework, not a GitHub language, so it is shown under Stack
  Signals, not Language Bytes.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

USERNAME = os.getenv("GITHUB_USERNAME", "ankitraj6767")
TOKEN = os.getenv("PROFILE_STATS_TOKEN") or ""
PUBLIC_ONLY = os.getenv("PUBLIC_ONLY", "false").lower() == "true"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "assets"))
SVG_PATH = OUTPUT_DIR / "language-snapshot.svg"
JSON_PATH = OUTPUT_DIR / "language-snapshot.json"
API_ROOT = "https://api.github.com"

LANG_COLORS = {
    "TypeScript": "#2563EB",
    "JavaScript": "#F59E0B",
    "Java": "#B45309",
    "Dart": "#0891B2",
    "Python": "#2563EB",
    "C++": "#DB2777",
    "C": "#525252",
    "HTML": "#EA580C",
    "CSS": "#7C3AED",
    "SCSS": "#BE185D",
    "Less": "#1D4ED8",
    "Shell": "#16A34A",
    "PLpgSQL": "#0F766E",
    "SQL": "#CA8A04",
    "Vue": "#059669",
}

STACK_COLORS = {
    "Spring Boot": "#16A34A",
    "Flutter": "#0891B2",
    "React": "#2563EB",
    "Next.js": "#111827",
    "Node.js / Express": "#65A30D",
    "NestJS": "#E11D48",
    "Supabase": "#059669",
    "PostgreSQL": "#1D4ED8",
    "MongoDB": "#16A34A",
    "Kafka": "#292524",
    "Razorpay": "#1E40AF",
    "Tailwind CSS": "#0D9488",
    "Redux": "#7C3AED",
    "Docker": "#0284C7",
}

EXCLUDED_REPOS = {USERNAME.lower()}
EXCLUDED_LANGUAGES = {"Profile"}
STACK_FILES = [
    "package.json",
    "pubspec.yaml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "docker-compose.yml",
    "Dockerfile",
    "supabase/config.toml",
    "supabase/schema.sql",
]


def request_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USERNAME}-profile-technology-snapshot",
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


def fetch_text_file(full_name: str, path: str) -> str:
    url = f"{API_ROOT}/repos/{full_name}/contents/{quote(path)}"
    try:
        item = request_json(url)
    except HTTPError as exc:
        if exc.code == 404:
            return ""
        raise
    except Exception:
        return ""

    if not isinstance(item, dict):
        return ""
    content = item.get("content") or ""
    encoding = item.get("encoding")
    if encoding != "base64" or not content:
        return ""
    try:
        return base64.b64decode(content).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def detect_stack(repo: dict[str, Any], languages: dict[str, int]) -> set[str]:
    full_name = repo.get("full_name", "")
    repo_name = repo.get("name", "")
    signals: set[str] = set()
    combined_parts = [repo_name.lower(), " ".join(languages.keys()).lower()]

    for path in STACK_FILES:
        content = fetch_text_file(full_name, path)
        if content:
            combined_parts.append(content.lower())

    combined = "\n".join(combined_parts)

    if "dart" in languages or "flutter:" in combined or "sdk: flutter" in combined:
        signals.add("Flutter")
    if "spring-boot" in combined or "org.springframework.boot" in combined:
        signals.add("Spring Boot")
    if "react" in combined or "typescript" in {k.lower() for k in languages.keys()}:
        signals.add("React")
    if "next" in combined or "next.js" in combined or "nextjs" in combined:
        signals.add("Next.js")
    if "express" in combined or "node.js" in combined or "nodejs" in combined:
        signals.add("Node.js / Express")
    if "nestjs" in combined or "@nestjs" in combined:
        signals.add("NestJS")
    if "supabase" in combined:
        signals.add("Supabase")
    if "postgres" in combined or "postgresql" in combined or "plpgsql" in {k.lower() for k in languages.keys()}:
        signals.add("PostgreSQL")
    if "mongodb" in combined or "mongoose" in combined:
        signals.add("MongoDB")
    if "kafka" in combined:
        signals.add("Kafka")
    if "razorpay" in combined:
        signals.add("Razorpay")
    if "tailwind" in combined:
        signals.add("Tailwind CSS")
    if "redux" in combined or "@reduxjs" in combined:
        signals.add("Redux")
    if "dockerfile" in combined or "docker-compose" in combined:
        signals.add("Docker")

    return signals


def aggregate(repos: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, int], list[dict[str, Any]]]:
    language_totals: dict[str, int] = {}
    stack_totals: dict[str, int] = {}
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

        try:
            languages = request_json(f"{API_ROOT}/repos/{full_name}/languages")
        except Exception as exc:
            print(f"WARN: failed language fetch for {full_name}: {exc}", file=sys.stderr)
            continue

        repo_bytes = 0
        for language, byte_count in languages.items():
            if language in EXCLUDED_LANGUAGES:
                continue
            byte_count = int(byte_count)
            if byte_count <= 0:
                continue
            language_totals[language] = language_totals.get(language, 0) + byte_count
            repo_bytes += byte_count

        stack_signals = detect_stack(repo, languages)
        for signal in stack_signals:
            stack_totals[signal] = stack_totals.get(signal, 0) + 1

        if repo_bytes > 0 or stack_signals:
            counted_repos.append({
                "name": full_name,
                "private": bool(repo.get("private")),
                "pushed_at": repo.get("pushed_at"),
                "bytes": repo_bytes,
                "languages": languages,
                "stack_signals": sorted(stack_signals),
            })

    return language_totals, stack_totals, counted_repos


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


def color_for_language(language: str, index: int) -> str:
    fallback = ["#F97316", "#14B8A6", "#84CC16", "#F43F5E", "#A16207", "#0EA5E9", "#9333EA"]
    return LANG_COLORS.get(language, fallback[index % len(fallback)])


def color_for_stack(stack: str, index: int) -> str:
    fallback = ["#D97706", "#059669", "#B91C1C", "#0F766E", "#C2410C", "#4338CA"]
    return STACK_COLORS.get(stack, fallback[index % len(fallback)])


def render_svg(language_totals: dict[str, int], stack_totals: dict[str, int], counted_repos: list[dict[str, Any]], generated_at: str, includes_private: bool) -> str:
    width, height = 980, 560
    total_bytes = sum(language_totals.values())
    language_ranked = sorted(language_totals.items(), key=lambda item: item[1], reverse=True)[:8]
    stack_ranked = sorted(stack_totals.items(), key=lambda item: (-item[1], item[0]))[:10]

    latest_push = "No pushes found"
    pushed_values = [repo.get("pushed_at") for repo in counted_repos if repo.get("pushed_at")]
    if pushed_values:
        latest_push = max(pushed_values)

    visibility = "public + private repos" if includes_private else "public repos only"
    private_warning = "Private Flutter/Spring Boot repos require PROFILE_STATS_TOKEN" if not includes_private else "Private repositories included"

    # Language segmented bar.
    bar_x, bar_y, bar_w, bar_h = 46, 145, 888, 20
    x = bar_x
    segments: list[str] = []
    for index, (language, byte_count) in enumerate(language_ranked):
        if total_bytes <= 0:
            continue
        seg_w = max(4, (byte_count / total_bytes) * bar_w)
        if x + seg_w > bar_x + bar_w:
            seg_w = max(0, bar_x + bar_w - x)
        if seg_w <= 0:
            break
        segments.append(f'<rect x="{x:.2f}" y="{bar_y}" width="{seg_w:.2f}" height="{bar_h}" fill="{color_for_language(language, index)}"/>')
        x += seg_w

    language_rows: list[str] = []
    for index, (language, byte_count) in enumerate(language_ranked):
        pct = (byte_count / total_bytes) * 100 if total_bytes else 0
        col = index % 2
        row = index // 2
        lx = 60 + col * 430
        ly = 210 + row * 42
        color = color_for_language(language, index)
        language_rows.append(f'<circle cx="{lx}" cy="{ly - 5}" r="6" fill="{color}"/>')
        language_rows.append(f'<text x="{lx + 16}" y="{ly}" fill="#292524" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="15" font-weight="800">{escape(language)}</text>')
        language_rows.append(f'<text x="{lx + 185}" y="{ly}" fill="#78716C" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="13">{pct:.2f}% • {human_bytes(byte_count)}</text>')

    max_stack = max(stack_totals.values()) if stack_totals else 1
    stack_rows: list[str] = []
    for index, (stack, count) in enumerate(stack_ranked[:8]):
        sx = 60 + (index % 2) * 430
        sy = 395 + (index // 2) * 36
        sw = 180 * (count / max_stack)
        color = color_for_stack(stack, index)
        stack_rows.append(f'<text x="{sx}" y="{sy}" fill="#292524" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="14" font-weight="800">{escape(stack)}</text>')
        stack_rows.append(f'<rect x="{sx + 170}" y="{sy - 12}" width="190" height="10" rx="5" fill="#E7E5E4"/>')
        stack_rows.append(f'<rect x="{sx + 170}" y="{sy - 12}" width="{sw:.2f}" height="10" rx="5" fill="{color}"/>')
        stack_rows.append(f'<text x="{sx + 372}" y="{sy}" fill="#78716C" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="12">{count} repos</text>')

    if not stack_rows:
        stack_rows.append('<text x="60" y="405" fill="#78716C" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="14">No framework signals detected yet. Add PROFILE_STATS_TOKEN for private repos.</text>')

    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">Technology Intelligence Snapshot</title>
  <desc id="desc">Language bytes and framework signals generated from GitHub repositories for {escape(USERNAME)}.</desc>
  <defs>
    <linearGradient id="paper" x1="0" y1="0" x2="980" y2="560" gradientUnits="userSpaceOnUse">
      <stop stop-color="#FFF7ED"/>
      <stop offset="0.46" stop-color="#FEF3C7"/>
      <stop offset="1" stop-color="#ECFDF5"/>
    </linearGradient>
    <linearGradient id="header" x1="46" y1="36" x2="934" y2="108" gradientUnits="userSpaceOnUse">
      <stop stop-color="#431407"/>
      <stop offset="0.48" stop-color="#92400E"/>
      <stop offset="1" stop-color="#065F46"/>
    </linearGradient>
    <filter id="softShadow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="14" stdDeviation="18" flood-color="#78350F" flood-opacity="0.18"/>
    </filter>
    <clipPath id="barClip"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="10"/></clipPath>
  </defs>

  <rect width="980" height="560" rx="30" fill="url(#paper)"/>
  <rect x="1" y="1" width="978" height="558" rx="29" stroke="#D6A94F" stroke-width="1.5"/>

  <rect x="46" y="34" width="888" height="76" rx="24" fill="url(#header)" filter="url(#softShadow)"/>
  <text x="72" y="67" fill="#FFF7ED" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="25" font-weight="950">Technology Intelligence Snapshot</text>
  <text x="72" y="93" fill="#FED7AA" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="13">Languages = GitHub byte totals • Stack signals = dependency/file detection • {escape(visibility)}</text>
  <text x="704" y="79" fill="#FEF3C7" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="13" font-weight="800">{len(counted_repos)} repos scanned</text>

  <text x="46" y="132" fill="#431407" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="17" font-weight="950">Language Byte Mix</text>
  <g clip-path="url(#barClip)">
    <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" fill="#E7E5E4"/>
    {' '.join(segments)}
  </g>
  <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="10" stroke="#A16207" opacity="0.55"/>

  {''.join(language_rows)}

  <rect x="46" y="350" width="888" height="1" fill="#D6A94F" opacity="0.7"/>
  <text x="46" y="377" fill="#431407" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="17" font-weight="950">Framework / Product Stack Signals</text>
  <text x="332" y="377" fill="#78716C" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="12">Spring Boot appears here because it is a framework, not a language.</text>

  {''.join(stack_rows)}

  <rect x="46" y="515" width="888" height="1" fill="#D6A94F" opacity="0.7"/>
  <text x="56" y="540" fill="#57534E" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="12">Updated {escape(generated_at)} UTC • Latest push: {escape(latest_push)}</text>
  <text x="662" y="540" fill="#92400E" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="12" font-weight="800">{escape(private_warning)}</text>
</svg>'''


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    repos = list_repos()
    language_totals, stack_totals, counted_repos = aggregate(repos)
    includes_private = bool(TOKEN and not PUBLIC_ONLY)

    SVG_PATH.write_text(render_svg(language_totals, stack_totals, counted_repos, generated_at, includes_private), encoding="utf-8")
    JSON_PATH.write_text(
        json.dumps(
            {
                "username": USERNAME,
                "generated_at_utc": generated_at,
                "source": {
                    "languages": "GitHub REST languages endpoint",
                    "stack_signals": "Detected from package.json, pubspec.yaml, pom.xml, Gradle, Docker, and Supabase files",
                },
                "includes_private_token": includes_private,
                "note": "Dart/Flutter private repos require PROFILE_STATS_TOKEN. Spring Boot is a framework signal, not a language byte category.",
                "counted_repositories": counted_repos,
                "total_language_bytes": sum(language_totals.values()),
                "languages": dict(sorted(language_totals.items(), key=lambda item: item[1], reverse=True)),
                "stack_signals": dict(sorted(stack_totals.items(), key=lambda item: (-item[1], item[0]))),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
