#!/usr/bin/env python3
"""Render every image of the profile README as static SVG, in dark and light.

  hero-{theme}.svg       name, role, impact numbers, load-test motif
  activity-{theme}.svg   contributions: streak numbers, weekly totals and the
                         familiar green calendar, all on one week axis
  appstore-{theme}.svg   "View on the App Store" pill

No animation anywhere: the README should read like a calm dashboard.
Data comes from the GitHub GraphQL contribution calendar, so private
contributions count when the profile shares them.

Usage: GITHUB_TOKEN=... python3 render_profile.py <login> <outdir>
       python3 render_profile.py --data <days.json> <outdir>   (offline preview;
       days.json is {"YYYY-MM-DD": count, ...})
"""
import datetime as dt
import json
import os
import random
import sys
import urllib.request
from xml.sax.saxutils import escape

THEMES = {
    "dark": {
        "panel": "#0D1117", "border": "#30363D", "hair": "#21262D",
        "ink": "#E6EDF3", "muted": "#8B949E", "faint": "#7D8590",
        "accent": "#FF7A1A", "wash": "#E6EDF3", "tile": "#161B22",
        "levels": ["#161B22", "#0E4429", "#006D32", "#26A641", "#39D353"],
    },
    "light": {
        "panel": "#FFFFFF", "border": "#D0D7DE", "hair": "#EAEEF2",
        "ink": "#1F2328", "muted": "#59636E", "faint": "#6E7781",
        "accent": "#E8590C", "wash": "#1F2328", "tile": "#F6F8FA",
        "levels": ["#EBEDF0", "#9BE9A8", "#40C463", "#30A14E", "#216E39"],
    },
}
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}
"""


# ---------- data ----------

def fetch(login, token):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise SystemExit(f"GraphQL error: {data['errors']}")
    cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    return {
        dt.date.fromisoformat(d["date"]): d["contributionCount"]
        for w in cal["weeks"] for d in w["contributionDays"]
    }


def load_json(path):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {dt.date.fromisoformat(k): int(v) for k, v in raw.items()}


def stats(days):
    dates = sorted(days)
    first, last = dates[0], dates[-1]
    series = [days.get(first + dt.timedelta(n), 0) for n in range((last - first).days + 1)]
    total = sum(series)

    longest = run = 0
    for v in series:
        run = run + 1 if v > 0 else 0
        longest = max(longest, run)
    # a streak is still alive if today has no contributions yet
    i = len(series) - 1
    if series[i] == 0:
        i -= 1
    current = 0
    while i >= 0 and series[i] > 0:
        current += 1
        i -= 1

    # GitHub-style columns: one per week, Sunday first; None pads outside the range
    start = first - dt.timedelta((first.weekday() + 1) % 7)
    weeks = []
    d = start
    while d <= last:
        weeks.append([(d + dt.timedelta(k), days.get(d + dt.timedelta(k)) if first <= d + dt.timedelta(k) <= last else None)
                      for k in range(7)])
        d += dt.timedelta(7)
    totals = [sum(v or 0 for _, v in w) for w in weeks]

    nz = sorted(v for v in series if v > 0) or [1]
    q = [nz[min(len(nz) - 1, int(len(nz) * f))] for f in (0.25, 0.5, 0.75)]
    return {
        "total": total, "current": current, "longest": longest,
        "weeks": weeks, "totals": totals, "quartiles": q,
    }


# ---------- helpers ----------

def monotone_path(pts):
    """Fritsch-Carlson monotone cubic: smooth, never overshoots below the baseline."""
    n = len(pts)
    if n < 2:
        return f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    dx = [pts[i + 1][0] - pts[i][0] for i in range(n - 1)]
    dy = [pts[i + 1][1] - pts[i][1] for i in range(n - 1)]
    m = [dy[i] / dx[i] for i in range(n - 1)]
    t = [m[0]] + [0.0] * (n - 2) + [m[-1]]
    for i in range(1, n - 1):
        if m[i - 1] * m[i] <= 0:
            t[i] = 0.0
        else:
            t[i] = 3 * (dx[i - 1] + dx[i]) / ((2 * dx[i] + dx[i - 1]) / m[i - 1] + (dx[i] + 2 * dx[i - 1]) / m[i])
    d = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
    for i in range(n - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        h = dx[i] / 3
        d.append(f"C{x0 + h:.1f},{y0 + t[i] * h:.1f} {x1 - h:.1f},{y1 - t[i + 1] * h:.1f} {x1:.1f},{y1:.1f}")
    return " ".join(d)


def text(x, y, s, size, fill, family=SANS, weight=400, anchor="start", spacing=0, opacity=1):
    extra = f' letter-spacing="{spacing}"' if spacing else ""
    op = f' fill-opacity="{opacity}"' if opacity != 1 else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}"{op} font-size="{size}" font-weight="{weight}" '
            f'font-family="{family}" text-anchor="{anchor}"{extra}>{escape(s)}</text>')


def svg(w, h, label, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{escape(label)}">\n<title>{escape(label)}</title>\n{body}\n</svg>\n')


def panel(w, h, c, r=14):
    return f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{r}" fill="{c["panel"]}" stroke="{c["border"]}"/>'


# ---------- hero ----------

def hero(c):
    W, H = 900, 300
    out = [panel(W, H, c)]

    # left: identity
    out.append(f'<rect x="44" y="53" width="8" height="8" rx="2" fill="{c["accent"]}"/>')
    out.append(text(62, 62, "DEVOPS · SRE · PERFORMANCE ENGINEERING", 12, c["muted"], MONO, 500, spacing=1.2))
    out.append(text(42, 116, "Dmitrii Ryazantsev", 44, c["ink"], SANS, 650, spacing=-0.8))
    out.append(text(44, 150, "Fast. Observable. Boring to operate.", 17, c["muted"]))

    # right: load-test motif as two stacked panels on a shared time axis
    x0, x1 = 586, 856
    lat_top, lat_bot = 44, 92
    rps_top, rps_bot = 112, 164
    rnd = random.Random(11)
    n = 60
    xs = [x0 + (x1 - x0) * i / (n - 1) for i in range(n)]

    def jitter(base, amp):
        return [base + rnd.uniform(-amp, amp) for _ in range(n)]

    p99 = jitter(lat_top + 14, 2.2)
    p50 = jitter(lat_top + 34, 1.2)
    for y in (lat_bot, rps_bot):
        out.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="{c["border"]}"/>')
    out.append(f'<path d="{monotone_path(list(zip(xs, p50)))}" fill="none" stroke="{c["faint"]}" stroke-width="1.5" stroke-linecap="round"/>')
    out.append(f'<path d="{monotone_path(list(zip(xs, p99)))}" fill="none" stroke="{c["accent"]}" stroke-width="2" stroke-linecap="round"/>')
    out.append(text(x0 - 10, lat_top + 18, "p99", 10, c["muted"], MONO, anchor="end"))
    out.append(text(x0 - 10, lat_top + 38, "p50", 10, c["faint"], MONO, anchor="end"))

    # stepped load profile: ramp, hold, ramp, hold...
    steps = [0.18, 0.38, 0.58, 0.78, 1.0]
    seg = (x1 - x0) / len(steps)
    ramp = seg * 0.18
    h = rps_bot - rps_top
    d = [f"M{x0},{rps_bot}"]
    prev = 0.0
    for k, s in enumerate(steps):
        xa = x0 + k * seg
        d.append(f"L{xa:.1f},{rps_bot - prev * h:.1f}")
        d.append(f"L{xa + ramp:.1f},{rps_bot - s * h:.1f}")
        prev = s
    d.append(f"L{x1},{rps_bot - prev * h:.1f} L{x1},{rps_bot} Z")
    out.append(f'<path d="{" ".join(d)}" fill="{c["wash"]}" fill-opacity="0.07" stroke="{c["muted"]}" stroke-opacity="0.55" stroke-width="1" stroke-linejoin="round"/>')
    out.append(text(x0 - 10, rps_bot - 6, "rps", 10, c["faint"], MONO, anchor="end"))
    out.append(text(x1, rps_bot + 22, "latency holds while load steps up", 10, c["faint"], MONO, anchor="end"))

    # bottom: impact numbers
    out.append(f'<line x1="32" y1="204" x2="{W - 32}" y2="204" stroke="{c["hair"]}"/>')
    cells = [
        ("~29", "production systems under load testing"),
        ("5", "App Store releases in under 4 weeks"),
        ("1,500+", "automated tests in my iOS app"),
    ]
    cw = (W - 88) / 3
    for k, (num, label) in enumerate(cells):
        x = 44 + k * cw
        if k:
            out.append(f'<line x1="{x - 18:.1f}" y1="224" x2="{x - 18:.1f}" y2="276" stroke="{c["hair"]}"/>')
        out.append(text(x, 254, num, 30, c["ink"], SANS, 650, spacing=-0.5))
        out.append(text(x, 276, label, 12, c["muted"]))

    return svg(W, H, "Dmitrii Ryazantsev - DevOps, SRE, performance engineering. "
               "~29 production systems under load testing, 5 App Store releases in under 4 weeks, "
               "1,500+ automated tests in my iOS app.", "\n".join(out))


# ---------- activity ----------

def level(v, q):
    if not v:
        return 0
    return 1 + sum(v > t for t in q)


def activity(c, s):
    W, H = 900, 384
    out = [panel(W, H, c)]
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%d %b %Y")
    weeks, totals = s["weeks"], s["totals"]
    lv = c["levels"]

    out.append(text(36, 46, "Contribution activity", 16, c["ink"], SANS, 600))
    out.append(text(864, 46, f"last 12 months · updated {stamp}", 11, c["faint"], MONO, anchor="end"))

    best = max(totals)
    kpis = [
        (f"{s['total']:,}", "contributions"),
        (f"{s['current']} {'day' if s['current'] == 1 else 'days'}", "current streak"),
        (f"{s['longest']} {'day' if s['longest'] == 1 else 'days'}", "longest streak"),
        (f"{best}", "best week"),
    ]
    kw = 828 / 4
    for k, (num, label) in enumerate(kpis):
        x = 36 + k * kw
        if k:
            out.append(f'<line x1="{x - 16:.1f}" y1="76" x2="{x - 16:.1f}" y2="126" stroke="{c["hair"]}"/>')
        out.append(text(x, 104, num, 24, c["ink"], SANS, 650, spacing=-0.4))
        lx = x
        if k == 1 and s["current"] > 0:
            out.append(f'<circle cx="{x + 3:.1f}" cy="122" r="3" fill="{lv[4]}"/>')
            lx = x + 12
        out.append(text(lx, 126, label, 12, c["muted"]))

    # one shared week axis: weekly totals on top, the daily calendar below
    pitch, cell = 15, 12
    x0 = 864 - (len(weeks) * pitch - (pitch - cell))
    bar_top, bar_base = 160, 206
    grid_top = 238

    out.append(f'<line x1="{x0}" y1="{bar_base + 0.5}" x2="864" y2="{bar_base + 0.5}" stroke="{c["border"]}"/>')
    peak_i = max(range(len(totals)), key=lambda i: totals[i])
    for i, t in enumerate(totals):
        if not t:
            continue
        h = max(2.0, t / best * (bar_base - bar_top))
        x, y, r = x0 + i * pitch, bar_base - h, min(2.0, h / 2)
        color = lv[4] if i == peak_i else lv[3]
        out.append(f'<path d="M{x},{bar_base} V{y + r:.1f} Q{x},{y:.1f} {x + r},{y:.1f} H{x + cell - r} '
                   f'Q{x + cell},{y:.1f} {x + cell},{y + r:.1f} V{bar_base} Z" fill="{color}"/>')

    last_m = None
    for i, w in enumerate(weeks):
        firsts = [d for d, v in w if v is not None and d.day == 1]
        if firsts and (last_m is None or i - last_m >= 3):
            out.append(text(x0 + i * pitch, grid_top - 10, firsts[0].strftime("%b"), 10, c["faint"], MONO))
            last_m = i

    for row, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        out.append(text(x0 - 8, grid_top + row * pitch + 9.5, name, 10, c["faint"], MONO, anchor="end"))

    for i, w in enumerate(weeks):
        for row, (d, v) in enumerate(w):
            if v is None:
                continue
            out.append(f'<rect x="{x0 + i * pitch}" y="{grid_top + row * pitch}" width="{cell}" height="{cell}" '
                       f'rx="2.5" fill="{lv[level(v, s["quartiles"])]}"/>')

    ly = grid_top + 7 * pitch + 14
    sq = [864 - 32 - (5 - k) * pitch + (pitch - cell) for k in range(5)]
    out.append(text(x0, ly + 9.5, "weekly totals above, daily contributions below", 10, c["faint"], MONO))
    out.append(text(sq[0] - 8, ly + 9.5, "Less", 10, c["faint"], MONO, anchor="end"))
    for k, x in enumerate(sq):
        out.append(f'<rect x="{x}" y="{ly}" width="{cell}" height="{cell}" rx="2.5" fill="{lv[k]}"/>')
    out.append(text(864, ly + 9.5, "More", 10, c["faint"], MONO, anchor="end"))

    label = (f"{s['total']:,} contributions in the last 12 months; current streak {s['current']} days; "
             f"longest streak {s['longest']} days; best week {best}.")
    return svg(W, H, label, "\n".join(out))


# ---------- small tiles ----------

def appstore(c):
    W, H = 196, 40
    out = [f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="8" fill="{c["tile"]}" stroke="{c["border"]}"/>']
    out.append(text(16, 25, "View on the App Store", 13, c["ink"], SANS, 600))
    out.append(f'<path d="M172 15 h9 v9 M181 15 l-10 10" fill="none" stroke="{c["accent"]}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')
    return svg(W, H, "View on the App Store", "\n".join(out))


# ---------- main ----------

def main():
    args = sys.argv[1:]
    if len(args) == 3 and args[0] == "--data":
        days, outdir = load_json(args[1]), args[2]
    elif len(args) == 2:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("GITHUB_TOKEN is not set")
        days, outdir = fetch(args[0], token), args[1]
    else:
        raise SystemExit(__doc__)
    s = stats(days)
    os.makedirs(outdir, exist_ok=True)
    for name, c in THEMES.items():
        for base, content in (
            ("hero", hero(c)), ("activity", activity(c, s)),
            ("appstore", appstore(c)),
        ):
            with open(os.path.join(outdir, f"{base}-{name}.svg"), "w", encoding="utf-8") as f:
                f.write(content)
    print(f"wrote {outdir}: total {s['total']}, streak {s['current']}/{s['longest']}, best week {max(s['totals'])}")


if __name__ == "__main__":
    main()
