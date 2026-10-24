#!/usr/bin/env python3
"""Generate profile charts and the repo table from real public data.

Writes:
  assets/commits-per-year.svg   public commits per year
  README.md                     the repo table between the REPOS markers

Python 3 standard library only.  Reads GITHUB_TOKEN from the environment if
present (needed for commit search).  Fails loudly, without overwriting any
file, if the data is missing or looks wrong.

Usage:  GITHUB_TOKEN=$(gh auth token) python3 scripts/generate_charts.py
"""
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

USER = "StevenTCramer"
ORG = "TimeWarpEngineering"
FIRST_YEAR = 2017
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = os.environ.get("GITHUB_TOKEN", "")
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

OCEAN, CYAN = "#004F78", "#00CCFF"
INK, MUTED, BORDER = "#1F2D33", "#5B6B73", "#D8E2E6"

# Overrides for repos whose GitHub About text is blank or not yet approved.
REPOS = [
    ("timewarp-state", None),
    ("timewarp-nuru", None),
    ("timewarp-architecture", None),
    ("timewarp-amuru",
     "Fluent C# process execution with pipeline support, a replacement for System.Diagnostics.Process."),
    ("timewarp-terminal",
     "A testable console and output layer for any .NET CLI: IConsole, ITerminal, panels, tables, rules and ANSI color."),
    ("timewarp-mediator", None),
    ("timewarp-jaribu", None),
]


class DataError(Exception):
    pass


def http(url, accept=None, retries=4, ok_404=False):
    headers = {"User-Agent": "profile-chart-generator"}
    if accept:
        headers["Accept"] = accept
    if TOKEN and "api.github.com" in url:
        headers["Authorization"] = "Bearer " + TOKEN
    delay = 5
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404 and ok_404:
                return None
            if e.code in (403, 429, 502, 503) and attempt < retries - 1:
                wait = int(e.headers.get("Retry-After", delay))
                print("  http %d, waiting %ds" % (e.code, wait), file=sys.stderr)
                time.sleep(wait)
                delay *= 2
                continue
            raise DataError("HTTP %d for %s" % (e.code, url))
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(delay)
                continue
            raise DataError("network error for %s: %s" % (url, e))
    raise DataError("failed: " + url)


def api(path, ok_404=False):
    body = http("https://api.github.com/" + path, "application/vnd.github+json", ok_404=ok_404)
    return None if body is None else json.loads(body)


def clean(text):
    """Keep generated prose free of dash punctuation that reads badly."""
    return text.replace("\u2014", ",").replace("\u2013", "-").strip()


# --------------------------------------------------------------------- commits
def fetch_commits_per_year(this_year):
    result = []
    for year in range(FIRST_YEAR, this_year + 1):
        q = "author:%s is:public author-date:%d-01-01..%d-12-31" % (USER, year, year)
        data = api("search/commits?per_page=1&q=" + urllib.parse.quote(q, safe=":"))
        if not data or "total_count" not in data:
            raise DataError("no total_count for %d" % year)
        result.append((year, int(data["total_count"])))
        print("  %d: %d" % (year, data["total_count"]), file=sys.stderr)
        time.sleep(3)  # search API allows 30 requests per minute
    if sum(c for _, c in result) < 1000 or max(c for _, c in result) == 0:
        raise DataError("commit totals look wrong: %r" % (result,))
    return result


def commits_svg(rows, this_year, updated):
    width, height = 860, 340
    left, right, top, bottom = 64, 24, 70, 62
    pw, ph = width - left - right, height - top - bottom
    peak = max(c for _, c in rows)
    step = 1
    for s in (100, 200, 250, 500, 1000, 2000, 2500, 5000):
        step = s
        if peak / s <= 5:
            break
    ymax = ((peak + step - 1) // step) * step
    out = []
    a = out.append
    a('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" role="img" aria-labelledby="t d">'
      % (width, height, width, height))
    a('<title id="t">Public commits per year</title>')
    a('<desc id="d">Bar chart of public commits per year from %d to %d.</desc>' % (rows[0][0], rows[-1][0]))
    a('<rect x="0.5" y="0.5" width="%d" height="%d" rx="10" fill="#FFFFFF" stroke="%s"/>' % (width - 1, height - 1, BORDER))
    a('<text x="24" y="34" font-family="%s" font-size="17" font-weight="600" fill="%s">Public commits per year</text>' % (FONT, INK))
    v = 0
    while v <= ymax:
        y = top + ph - ph * v / ymax
        a('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#E9EEF0"/>' % (left, y, left + pw, y))
        a('<text x="%d" y="%.1f" text-anchor="end" font-family="%s" font-size="11" fill="%s">%s</text>'
          % (left - 8, y + 4, FONT, MUTED, format(v, ",")))
        v += step
    slot = pw / len(rows)
    bw = slot * 0.6
    for i, (year, count) in enumerate(rows):
        x = left + i * slot + (slot - bw) / 2
        h = ph * count / ymax
        y = top + ph - h
        color = CYAN if year == this_year else OCEAN
        a('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="%s"><title>%d: %d commits</title></rect>'
          % (x, y, bw, h, color, year, count))
        a('<text x="%.1f" y="%.1f" text-anchor="middle" font-family="%s" font-size="12" fill="%s">%s</text>'
          % (x + bw / 2, y - 6, FONT, INK, format(count, ",")))
        label = "%d so far" % year if year == this_year else str(year)
        a('<text x="%.1f" y="%d" text-anchor="middle" font-family="%s" font-size="12" fill="%s">%s</text>'
          % (x + bw / 2, top + ph + 20, FONT, MUTED, label))
    a('<text x="24" y="%d" font-family="%s" font-size="11" fill="%s">Counts commits under this GitHub identity on public repos.  Updated %s.</text>'
      % (height - 16, FONT, MUTED, updated))
    a('</svg>')
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ repo table
def md_escape(s):
    return s.replace("|", "\\|")


def repo_table(updated):
    lines = ["| Repo | What it is | Stars | Latest release |", "| --- | --- | ---: | --- |"]
    for name, override in REPOS:
        info = api("repos/%s/%s" % (ORG, name))
        if info.get("private"):
            raise DataError(name + " is private")
        desc = clean(override or info.get("description") or "")
        if not desc:
            raise DataError("no description for " + name)
        rels = api("repos/%s/%s/releases?per_page=30" % (ORG, name)) or []
        published = [r for r in rels if not r.get("draft") and (r.get("published_at") or r.get("created_at"))]
        if published:
            newest = max(published, key=lambda r: r.get("published_at") or r["created_at"])
            release = newest["tag_name"]
        else:
            release = "none yet"
        lines.append("| [%s](%s) | %s | %d | %s |"
                     % (name, info["html_url"], md_escape(desc), info["stargazers_count"], md_escape(release)))
    lines.append("")
    lines.append("<sub>Snapshot from the GitHub API on %s, refreshed weekly.</sub>" % updated)
    return "\n".join(lines)


def main():
    now = dt.datetime.now(dt.timezone.utc)
    updated = now.date().isoformat()
    print("commits per year...", file=sys.stderr)
    rows = fetch_commits_per_year(now.year)
    print("repo table...", file=sys.stderr)
    table = repo_table(updated)

    readme_path = os.path.join(ROOT, "README.md")
    with open(readme_path, encoding="utf-8") as f:
        readme = f.read()
    pat = re.compile(r"(<!-- REPOS:START -->\n).*?(<!-- REPOS:END -->)", re.S)
    if not pat.search(readme):
        raise DataError("README.md is missing the REPOS markers")
    new_readme = pat.sub(lambda m: m.group(1) + table + "\n" + m.group(2), readme)

    outputs = {
        os.path.join(ROOT, "assets", "commits-per-year.svg"): commits_svg(rows, now.year, updated),
        readme_path: new_readme,
    }
    # everything was generated; only now touch files
    for path, content in outputs.items():
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        os.replace(tmp, path)
    print("commits per year: %r" % (rows,), file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except DataError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        sys.exit(1)
