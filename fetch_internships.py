#!/usr/bin/env python3
"""Collect internship listings and update the job table in README.md."""

from __future__ import annotations

import json
import re
import sys
import html
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
CACHE_PATH = ROOT / "data" / "internships.json"
CONFIG_PATH = ROOT / "config" / "boards.json"

MAX_AGE_DAYS = 30
MAX_DISPLAY_PER_CATEGORY = 150
TIMEOUT_SECONDS = 25
USER_AGENT = "India-Internship-Tracker/1.0 (GitHub Actions; public job API client)"
START_MARKER = "<!-- JOBS:START -->"
END_MARKER = "<!-- JOBS:END -->"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def clean(value) -> str:
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]*>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_date(value) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            # Lever uses Unix milliseconds; tolerate seconds too.
            stamp = float(value)
            if stamp > 10_000_000_000:
                stamp /= 1000
            return datetime.fromtimestamp(stamp, tz=timezone.utc)
        text = str(value).strip()
        if text.isdigit():
            return parse_date(int(text))
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def canonical_url(url: str) -> str:
    url = clean(url)
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ""
        # Remove common tracking parameters and fragments.
        return urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            "",
            "",
        ))
    except ValueError:
        return ""


def is_internship(job: dict) -> bool:
    title = clean(job.get("title")).lower()
    kind = clean(job.get("job_type")).lower()
    if isinstance(job.get("job_types"), list):
        kind += " " + " ".join(map(str, job["job_types"])).lower()
    category = clean(job.get("category")).lower()
    text = f"{title} {kind} {category}"

    # Explicit title wording is the most reliable signal.
    if re.search(r"\b(intern|internship|internships)\b", title):
        return True
    # Some feeds label the job type instead of putting it in the title.
    if re.search(r"\b(intern|internship|internships)\b", kind):
        return True
    return False


def category_for(title: str, description: str = "") -> str:
    text = f"{title} {description}".lower()
    if re.search(r"\b(ai|artificial intelligence|machine learning|deep learning|llm|nlp|computer vision)\b", text):
        return "AI & Machine Learning"
    if re.search(r"\b(data science|data scientist|data analyst|analytics|business intelligence)\b", text):
        return "Data Science & Analytics"
    if re.search(r"\b(front.?end|back.?end|full.?stack|web developer|web development|react|angular|vue)\b", text):
        return "Web Development"
    if re.search(r"\b(software|software engineer|developer|programmer|java|python|backend|sde|qa engineer|quality assurance|devops|cloud engineer|cybersecurity|security engineer|mobile developer|android|ios)\b", text):
        return "Software Engineering"
    return "Other IT Internships"


def location_is_eligible(location: str, remote: bool = False, source: str = "") -> bool:
    loc = clean(location).lower()
    india_terms = ("india", "bengaluru", "bangalore", "hyderabad", "pune",
                   "mumbai", "delhi", "gurugram", "gurgaon", "noida",
                   "chennai", "kolkata", "kochi", "ahmedabad", "indore")
    worldwide_terms = ("worldwide", "anywhere", "global", "all countries",
                       "multiple locations", "remote - worldwide",
                       "remote worldwide", "india or remote", "remote (india)")
    if any(term in loc for term in india_terms):
        return True
    if any(term in loc for term in worldwide_terms):
        return True
    # Accept a clearly stated remote-only location when the source does not
    # specify a country restriction. Do not treat every remote job as global.
    if remote and (not loc or loc in ("remote", "remote, worldwide", "work from home")):
        return True
    return False


def make_job(*, title, company, location, url, posted_at=None, source,
             description="", remote=False, source_id="") -> dict | None:
    title = clean(title)
    company = clean(company)
    location = clean(location) or ("Remote" if remote else "Not specified")
    url = canonical_url(url)
    if not title or not company or not url:
        return None
    posted = parse_date(posted_at)
    return {
        "id": clean(source_id),
        "title": title,
        "company": company,
        "location": location,
        "url": url,
        "posted_at": posted.isoformat() if posted else None,
        "source": source,
        "category": category_for(title, clean(description)),
        "remote": bool(remote),
    }


def request_json(url: str):
    response = SESSION.get(url, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def fetch_remotive() -> list[dict]:
    # Public API. Remotive may delay publication and its API terms require
    # attribution and links back to the original listing/source.
    payload = request_json("https://remotive.com/api/remote-jobs?limit=500")
    output = []
    for raw in payload.get("jobs", []):
        if not is_internship({
            "title": raw.get("title"),
            "job_type": raw.get("job_type"),
            "job_types": raw.get("job_types", []),
        }):
            continue
        location = raw.get("candidate_required_location") or "Remote"
        if not location_is_eligible(location, remote=True, source="Remotive"):
            continue
        job = make_job(
            title=raw.get("title"),
            company=raw.get("company_name"),
            location=location,
            url=raw.get("url"),
            posted_at=raw.get("publication_date"),
            source="Remotive",
            description=raw.get("description"),
            remote=True,
            source_id=raw.get("id"),
        )
        if job:
            output.append(job)
    return output


def fetch_arbeitnow() -> list[dict]:
    # Public job-board API. The API is not India-focused; only matching roles
    # explicitly located in India or clearly worldwide remote are retained.
    payload = request_json("https://www.arbeitnow.com/api/job-board-api")
    output = []
    for raw in payload.get("data", []):
        title = raw.get("title", "")
        job_types = raw.get("job_types", [])
        if not is_internship({"title": title, "job_types": job_types}):
            continue
        location = raw.get("location", "")
        remote = raw.get("remote", False)
        if isinstance(remote, str):
            remote = remote.lower() in ("true", "yes", "1")
        if not location_is_eligible(location, remote=bool(remote), source="Arbeitnow"):
            continue
        job = make_job(
            title=title,
            company=raw.get("company_name"),
            location=location or ("Remote" if remote else ""),
            url=raw.get("url"),
            posted_at=raw.get("created_at"),
            source="Arbeitnow",
            description=raw.get("description"),
            remote=bool(remote),
            source_id=raw.get("slug"),
        )
        if job:
            output.append(job)
    return output


def fetch_greenhouse(board_token: str) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    payload = request_json(url)
    output = []
    for raw in payload.get("jobs", []):
        title = raw.get("title", "")
        location = (raw.get("location") or {}).get("name", "")
        content = raw.get("content", "")
        if not is_internship({"title": title}):
            continue
        if not location_is_eligible(location, remote=("remote" in location.lower()), source="Greenhouse"):
            continue
        job = make_job(
            title=title,
            company=board_token.replace("-", " ").title(),
            location=location,
            url=raw.get("absolute_url"),
            posted_at=raw.get("updated_at"),
            source="Greenhouse",
            description=content,
            remote=("remote" in location.lower()),
            source_id=raw.get("id"),
        )
        if job:
            output.append(job)
    return output


def fetch_lever(site: str) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{site}?mode=json"
    payload = request_json(url)
    output = []
    if not isinstance(payload, list):
        return output
    for raw in payload:
        title = raw.get("text", "")
        categories = raw.get("categories") or {}
        location = categories.get("location", "")
        workplace = raw.get("workplaceType", "")
        remote = "remote" in str(workplace).lower()
        if not is_internship({"title": title}):
            continue
        if not location_is_eligible(location, remote=remote, source="Lever"):
            continue
        lists = raw.get("lists") or []
        description = " ".join(
            clean(item.get("content", "")) for item in lists if isinstance(item, dict)
        )
        job = make_job(
            title=title,
            company=site.replace("-", " ").title(),
            location=location or ("Remote" if remote else ""),
            url=raw.get("hostedUrl"),
            posted_at=raw.get("createdAt"),
            source="Lever",
            description=description,
            remote=remote,
            source_id=raw.get("id"),
        )
        if job:
            output.append(job)
    return output


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {"greenhouse_boards": [], "lever_sites": []}
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        config = json.load(handle)
    return {
        "greenhouse_boards": config.get("greenhouse_boards", []),
        "lever_sites": config.get("lever_sites", []),
    }


def load_cache() -> list[dict]:
    if not CACHE_PATH.exists():
        return []
    try:
        with CACHE_PATH.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        jobs = payload.get("jobs", [])
        return jobs if isinstance(jobs, list) else []
    except (json.JSONDecodeError, OSError):
        print("WARNING: cache could not be read; starting without cached jobs.")
        return []


def deduplicate(jobs: list[dict]) -> list[dict]:
    by_url = {}
    by_content = set()
    for job in jobs:
        url_key = canonical_url(job.get("url", ""))
        content_key = "|".join([
            clean(job.get("company")).lower(),
            clean(job.get("title")).lower(),
            clean(job.get("location")).lower(),
        ])
        key = url_key or content_key
        if not key or content_key in by_content:
            continue
        by_content.add(content_key)
        if key not in by_url:
            by_url[key] = job
        else:
            # Prefer a record with a known posting date.
            old = by_url[key]
            if not old.get("posted_at") and job.get("posted_at"):
                by_url[key] = job
    return list(by_url.values())


def keep_recent(jobs: list[dict]) -> list[dict]:
    cutoff = now_utc() - timedelta(days=MAX_AGE_DAYS)
    kept = []
    for job in jobs:
        posted = parse_date(job.get("posted_at"))
        if posted is None or posted >= cutoff:
            kept.append(job)
    return kept


def merge_jobs(old_jobs: list[dict], new_jobs: list[dict]) -> list[dict]:
    # Retain cached jobs if one source is temporarily unavailable.
    # New data replaces the cached version for the same URL.
    merged = {}
    for job in old_jobs + new_jobs:
        url_key = canonical_url(job.get("url", ""))
        if not url_key:
            continue
        existing = merged.get(url_key)
        if existing is None:
            merged[url_key] = job
        elif job in new_jobs:
            merged[url_key] = job
    return keep_recent(deduplicate(list(merged.values())))


def md_cell(value: str) -> str:
    value = clean(value).replace("|", r"\|")
    return value or "Not specified"


def markdown_link(url: str) -> str:
    # Canonical URLs remove query strings/fragments; escape parentheses for Markdown.
    return canonical_url(url).replace("(", "%28").replace(")", "%29")


def format_age(posted_at) -> str:
    posted = parse_date(posted_at)
    if not posted:
        return "Unknown"
    days = max(0, (now_utc() - posted).days)
    if days == 0:
        return "Today"
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"


def build_job_section(jobs: list[dict]) -> str:
    categories = [
        "Software Engineering",
        "AI & Machine Learning",
        "Data Science & Analytics",
        "Web Development",
        "Other IT Internships",
    ]
    lines = [
        "## Latest internship listings",
        "",
        f"> Last refreshed: **{now_utc().strftime('%Y-%m-%d %H:%M UTC')}** · "
        f"**{len(jobs)} listings** · Automatically updated every six hours.",
        "",
        "Listings are collected from public sources. Verify eligibility and deadlines on the original application page.",
        "",
    ]
    if not jobs:
        lines.extend(["No matching internships were returned by the configured sources in this run.", ""])
    for category in categories:
        grouped = [j for j in jobs if j.get("category") == category]
        grouped.sort(key=lambda j: parse_date(j.get("posted_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        lines.extend([f"### {category}", ""])
        if not grouped:
            lines.extend(["_No matching listings currently available._", ""])
            continue
        lines.extend([
            "| Company | Internship role | Location | Age | Source | Apply |",
            "|---|---|---|---|---|---|",
        ])
        for job in grouped[:MAX_DISPLAY_PER_CATEGORY]:
            link = markdown_link(job.get("url", ""))
            lines.append(
                f"| {md_cell(job.get('company', ''))} "
                f"| {md_cell(job.get('title', ''))} "
                f"| {md_cell(job.get('location', ''))} "
                f"| {format_age(job.get('posted_at'))} "
                f"| {md_cell(job.get('source', ''))} "
                f"| [Apply]({link}) |"
            )
        lines.append("")
    lines.extend([
        "### Sources and attribution",
        "",
        "- [Remotive](https://remotive.com/remote-jobs) — remote job listings; see the [API terms](https://remotive.com/remote-jobs/api).",
        "- [Arbeitnow](https://www.arbeitnow.com/) — public job-board API.",
        "- Greenhouse and Lever listings link to the original employer job pages.",
        "",
        f"_Listings with known posting dates older than {MAX_AGE_DAYS} days are removed. Listings with unknown dates are retained._",
        "",
    ])
    return "\n".join(lines)


def update_readme(section: str) -> None:
    if not README_PATH.exists():
        raise RuntimeError("README.md not found. Restore the project README before running.")
    text = README_PATH.read_text(encoding="utf-8")
    if START_MARKER not in text or END_MARKER not in text:
        raise RuntimeError("README.md is missing JOBS:START / JOBS:END markers.")
    before, remainder = text.split(START_MARKER, 1)
    _, after = remainder.split(END_MARKER, 1)
    updated = before + START_MARKER + "\n" + section.rstrip() + "\n\n" + END_MARKER + after
    README_PATH.write_text(updated, encoding="utf-8")


def save_cache(jobs: list[dict]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_updated_utc": now_utc().isoformat(),
        "jobs": jobs,
    }
    CACHE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    config = load_config()
    old_jobs = load_cache()
    new_jobs: list[dict] = []
    successful_sources = 0
    errors: list[str] = []

    sources = [
        ("Remotive", fetch_remotive),
        ("Arbeitnow", fetch_arbeitnow),
    ]
    for token in config["greenhouse_boards"]:
        if token and not str(token).startswith("example-"):
            sources.append((f"Greenhouse:{token}", lambda token=token: fetch_greenhouse(str(token))))
    for site in config["lever_sites"]:
        if site and not str(site).startswith("example-"):
            sources.append((f"Lever:{site}", lambda site=site: fetch_lever(str(site))))

    for name, fetcher in sources:
        try:
            result = fetcher()
            new_jobs.extend(result)
            successful_sources += 1
            print(f"{name}: fetched {len(result)} matching internships.")
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            errors.append(f"{name}: {exc}")
            print(f"WARNING: {name} failed: {exc}", file=sys.stderr)

    if successful_sources == 0:
        print("ERROR: all sources failed; preserving README.md and cache.", file=sys.stderr)
        return 1

    jobs = merge_jobs(old_jobs, new_jobs)
    update_readme(build_job_section(jobs))
    save_cache(jobs)

    print(f"Updated README.md and cache with {len(jobs)} listings.")
    if errors:
        print(f"WARNING: {len(errors)} source(s) failed; cached listings were retained.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
