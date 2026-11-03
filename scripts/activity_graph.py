#!/usr/bin/env python3
"""Render a contribution activity chart (last 12 months) as an animated SVG.

Data comes from the GitHub GraphQL contribution calendar, so private
contributions are included when the profile shares their counts.

Usage: GITHUB_TOKEN=... python3 activity_graph.py <login> <out.svg>
       python3 activity_graph.py --sample <out.svg>   (offline preview)
"""
import datetime as dt
import json
import os
import random
import sys
import urllib.request

W, H = 900, 300
PAD_L, PAD_R = 36, 36
TOP, BOTTOM = 108, 244
ACCENT = "#FF7A1A"
BG = "#0D1117"
GRID = "#21262D"
MUTED = "#8B949E"
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


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
    weeks = []
    for w in cal["weeks"]:
        days = w["contributionDays"]
        weeks.append((dt.date.fromisoformat(days[0]["date"]), sum(d["contributionCount"] for d in days)))
    return cal["totalContributions"], weeks


def sample():
    start = dt.date.today() - dt.timedelta(weeks=52)
    weeks, rnd = [], random.Random(7)
    for i in range(53):
        base = 2 if i < 30 else 25 + 20 * ((i - 30) / 22)
        weeks.append((start + dt.timedelta(weeks=i), max(0, int(base + rnd.uniform(-8, 12)))))
    return sum(v for _, v in weeks), weeks


def monotone_path(pts):
    """Fritsch-Carlson monotone cubic through pts -> SVG path commands (no overshoot below 0)."""
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


def render(total, weeks):
    values = [v for _, v in weeks]
    vmax = max(max(values), 1)
    n = len(values)
    step = (W - PAD_L - PAD_R) / (n - 1)
    pts = [(PAD_L + i * step, BOTTOM - (v / vmax) * (BOTTOM - TOP)) for i, v in enumerate(values)]
    line = monotone_path(pts)
    area = f"{line} L{pts[-1][0]:.1f},{BOTTOM} L{pts[0][0]:.1f},{BOTTOM} Z"

    grid = "".join(
        f'<line x1="{PAD_L}" y1="{TOP + k * (BOTTOM - TOP) / 4:.1f}" x2="{W - PAD_R}" '
        f'y2="{TOP + k * (BOTTOM - TOP) / 4:.1f}" stroke="{GRID}" stroke-width="1" stroke-dasharray="3 5"/>'
        for k in range(4)
    )
    grid += f'<line x1="{PAD_L}" y1="{BOTTOM}" x2="{W - PAD_R}" y2="{BOTTOM}" stroke="#30363D" stroke-width="1"/>'

    months, last = [], None
    for i, (d, _) in enumerate(weeks):
        mid = d + dt.timedelta(days=3)
        if mid.month != last:
            if last is not None and (not months or i - months[-1][0] >= 3):
                months.append((i, mid.strftime("%b")))
            last = mid.month
    labels = "".join(
        f'<text x="{PAD_L + i * step:.1f}" y="{BOTTOM + 24}" fill="{MUTED}" font-size="11" '
        f'text-anchor="middle" font-family="{FONT}">{name}</text>'
        for i, name in months
    )

    pi = max(range(n), key=lambda i: values[i])
    px, py = pts[pi]
    anchor = "end" if px > W - 160 else "start"
    off = -10 if anchor == "end" else 10
    peak = (
        f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{px:.1f}" y2="{BOTTOM}" stroke="{ACCENT}" '
        f'stroke-opacity="0.35" stroke-dasharray="2 4"/>'
        f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{BG}" stroke="{ACCENT}" stroke-width="2.5"/>'
        f'<text x="{px + off:.1f}" y="{py - 10:.1f}" fill="#FFFFFF" font-size="12" font-weight="600" '
        f'text-anchor="{anchor}" font-family="{FONT}">peak {values[pi]} / week</text>'
    )
    lx, ly = pts[-1]
    live = (
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" fill="{ACCENT}" class="pulse"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="{ACCENT}"/>'
    )
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%d %b %Y")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{total:,} contributions in the last year">
<defs>
  <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="{ACCENT}" stop-opacity="0.45"/>
    <stop offset="100%" stop-color="{ACCENT}" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="stroke" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="#FFB37A"/>
    <stop offset="100%" stop-color="{ACCENT}"/>
  </linearGradient>
  <filter id="glow" x="-10%" y="-30%" width="120%" height="160%">
    <feGaussianBlur stdDeviation="4" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <clipPath id="reveal"><rect x="0" y="0" width="0" height="{H}"><animate attributeName="width" from="0" to="{W}" dur="2.2s" fill="freeze" calcMode="spline" keySplines="0.4 0 0.2 1" keyTimes="0;1"/></rect></clipPath>
</defs>
<style>
  .pulse {{ transform-box: fill-box; transform-origin: center; animation: pulse 2s ease-out 2.2s infinite; opacity: 0; }}
  @keyframes pulse {{ 0% {{ transform: scale(1); opacity: .8; }} 100% {{ transform: scale(4); opacity: 0; }} }}
</style>
<rect width="{W}" height="{H}" rx="12" fill="{BG}"/>
<text x="{PAD_L}" y="46" fill="#FFFFFF" font-size="18" font-weight="600" font-family="{FONT}">Contribution activity</text>
<text x="{PAD_L}" y="68" fill="{MUTED}" font-size="12" font-family="{FONT}">weekly contributions, last 12 months · updated {stamp}</text>
<text x="{W - PAD_R}" y="46" fill="{ACCENT}" font-size="26" font-weight="700" text-anchor="end" font-family="{FONT}">{total:,}</text>
<text x="{W - PAD_R}" y="68" fill="{MUTED}" font-size="12" text-anchor="end" font-family="{FONT}">contributions in the last year</text>
{grid}
<g clip-path="url(#reveal)">
  <path d="{area}" fill="url(#fill)"/>
  <path d="{line}" fill="none" stroke="url(#stroke)" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" filter="url(#glow)"/>
  {peak}
  {live}
</g>
{labels}
</svg>
"""


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--sample":
        total, weeks = sample()
        out = sys.argv[2]
    elif len(sys.argv) == 3:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("GITHUB_TOKEN is not set")
        total, weeks = fetch(sys.argv[1], token)
        out = sys.argv[2]
    else:
        raise SystemExit(__doc__)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(total, weeks))
    print(f"wrote {out}: {total} contributions, {len(weeks)} weeks")


if __name__ == "__main__":
    main()
