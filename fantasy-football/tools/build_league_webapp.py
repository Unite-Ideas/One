#!/usr/bin/env python3
"""Stamp a per-league Draft War Room from the shared template.

Takes the existing webapp/draft_room.html as the UI template and rewrites the
league-specific bits (board data, lineup constants, header defaults, storage
key, blurb) to produce a separate, self-contained war room for another league.
This is the "one template -> per-league builds" approach: the design lives in
one file; each league gets its own output + its own artifact link, and they
never share state (distinct localStorage KEY, fresh empty snapshot).

Usage: python3 tools/build_league_webapp.py lauren
(config below; add more as needed.)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from ffball import sources  # noqa: E402

TEMPLATE = ROOT / "webapp" / "draft_room.html"

# Per-league build configs. Superflex/no-K-DEF leagues can reuse the template
# defaults; standard leagues (like Lauren's) override lineup + keep K/DEF.
CONFIGS = {
    "lauren": {
        "out": "webapp/draft_room_lauren.html",
        "title": "Lauren's War Room",
        "superflex": False, "keep_kdef": True,
        "teams": 12, "slot": 7, "scoring_default": "ppr",
        "starters": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1},
        "flex": 1, "super_flex": 0, "bench": 7,
        "caps": {"QB": 2, "RB": 8, "WR": 8, "TE": 3, "K": 2, "DEF": 2},
        "mustfill": {"QB": 40, "RB": 60, "WR": 60, "TE": 28, "K": 200, "DEF": 200},
        "sf_weights": {},
        "key": "ffball_draft_lauren",
        "fmt": "`${TEAMS}-team · ${SCORING_LABEL[SCORING]} · "
               "1QB/2RB/2WR/1TE/1FLEX · K + D/ST · top-4 playoffs`",
        "slotdefs": '[["QB",1],["RB",2],["WR",2],["TE",1],["K",1],["DEF",1]]',
        # Miami/Havana pastel-tropical glassmorphism (overrides the cream
        # neumorphic look — appended last so it wins the cascade).
        # Lobster = a retro Havana-signage script for her header.
        "brand_html": 'La Reina del Draft \U0001F451'
                      '<span class="tagline">“I didn’t ask for a crown. I drafted one.” \U0001F336️</span>',
        "theme_head": '<link rel="stylesheet" href="https://fonts.googleapis.com/'
                      'css2?family=Lobster&family=Poppins:wght@500;600;700;800&display=swap">',
        "theme_css": """
  /* ===== Lauren's theme: Miami/Havana tropical glassmorphism ===== */
  body{background:linear-gradient(135deg,#ffdcc6 0%,#ffc6dc 27%,#e9c2fb 55%,#a9e7dd 100%) fixed !important;color:#3b2f39}
  :root{--ink:#3b2f39;--dim:#7c6b76;--faint:#a596a0;--line:rgba(120,90,110,.15);
    --turf:#ff5d8f;--turf-dim:#ffc2d6;--solid:#3f7be0;--value:#1fae72;--reach:#e08a00;
    --mine:rgba(255,255,255,.5);--mine-line:#ff8fb0}
  .brand,.card h2,.clock .big,.rec .nm{font-family:"Poppins","Archivo",sans-serif !important}
  .brand .b,.banner .lead,details.gloss summary{color:var(--turf)}
  header{background:rgba(255,255,255,.5) !important;backdrop-filter:blur(16px) saturate(1.5);
    -webkit-backdrop-filter:blur(16px) saturate(1.5);border-bottom:1px solid rgba(255,255,255,.6) !important;
    box-shadow:0 4px 24px rgba(180,120,150,.18) !important}
  .card,.banner,.term{background:rgba(255,255,255,.48) !important;backdrop-filter:blur(14px) saturate(1.4);
    -webkit-backdrop-filter:blur(14px) saturate(1.4);border:1px solid rgba(255,255,255,.65) !important;
    box-shadow:0 8px 30px rgba(150,110,140,.16) !important;border-radius:20px !important}
  .banner{border-left:4px solid var(--turf) !important}
  .vbtn{background:rgba(255,255,255,.5) !important;box-shadow:none !important;
    border:1px solid rgba(255,255,255,.6) !important;-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px)}
  .vbtn.active{background:var(--turf) !important;color:#fff !important;box-shadow:0 6px 16px rgba(255,93,143,.38) !important}
  input,select,.slotwrap{background:rgba(255,255,255,.6) !important;box-shadow:none !important;
    border:1px solid rgba(150,110,140,.22) !important;color:var(--ink)}
  .slotwrap input,.slotwrap select{color:var(--turf);border:none !important}
  button{background:rgba(255,255,255,.6) !important;box-shadow:none !important;
    border:1px solid rgba(150,110,140,.2) !important;color:var(--ink);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px)}
  .btn-me{background:linear-gradient(135deg,#ff7aa5,#ff5d8f) !important;color:#fff !important;
    border:none !important;box-shadow:0 6px 16px rgba(255,93,143,.4) !important}
  .btn-off{background:rgba(255,255,255,.55) !important;color:var(--dim)}
  .rec{background:rgba(255,255,255,.4) !important;box-shadow:none !important;
    border:1px solid rgba(255,255,255,.6) !important;border-radius:16px !important}
  .rec.top{box-shadow:inset 0 0 0 2px var(--turf-dim) !important}
  .pos{box-shadow:none !important}
  thead th{background:rgba(255,255,255,.72) !important}
  tbody tr:hover{background:rgba(255,255,255,.5) !important}
  tr.mine,tr.me-row{background:rgba(255,143,176,.2) !important}
  .toast{background:var(--turf) !important;color:#fff !important;box-shadow:0 8px 24px rgba(255,93,143,.5) !important}
  /* La Reina header — Havana-script brand + flirty tagline */
  .brand{font-family:"Lobster",cursive !important;font-weight:400 !important;font-size:31px !important;
    letter-spacing:.5px !important;text-transform:none !important;color:#ff4d86 !important;line-height:1.02;
    display:flex;flex-direction:column;text-shadow:0 1px 0 rgba(255,255,255,.6)}
  .brand .tagline{font-family:"Poppins",sans-serif !important;font-style:italic;font-weight:500;
    font-size:12px;letter-spacing:.2px;color:#7c6b76;text-transform:none;margin-top:10px}
""",
    },
}


def build_board(superflex: bool, keep_kdef: bool) -> list:
    merged: dict = {}
    order: list = []
    for sc in ("ppr", "half_ppr", "standard"):
        for r in sources.fetch_board_rows(scoring=sc, superflex=superflex):
            if not keep_kdef and r["position"] in ("K", "DEF"):
                continue
            pid = r["player_id"]
            if pid not in merged:
                merged[pid] = {"id": pid, "name": r["name"], "pos": r["position"],
                               "team": r["team"] or "", "bye": r["bye_week"], "adp": r["adp"]}
                order.append(pid)
            merged[pid]["pts_" + sc] = r["fpts"]
    return [merged[p] for p in order]


def sub_once(html: str, pattern: str, repl: str, label: str) -> str:
    new, n = re.subn(pattern, lambda m: repl, html, count=1)
    if n != 1:
        raise SystemExit(f"anchor not found/uniquely matched: {label}")
    return new


def main() -> None:
    key = sys.argv[1] if len(sys.argv) > 1 else "lauren"
    cfg = CONFIGS[key]
    html = TEMPLATE.read_text(encoding="utf-8")

    board = build_board(cfg["superflex"], cfg["keep_kdef"])
    data = json.dumps({"meta": {"scoring": cfg["scoring_default"], "teams": cfg["teams"]}, "board": board})

    # 1) board data blob
    html = re.sub(r'(<script id="data" type="application/json">).*?(</script>)',
                  lambda m: m.group(1) + data + m.group(2), html, count=1, flags=re.S)
    # 2) season blob stays empty for a fresh league
    html = re.sub(r'(<script id="season" type="application/json">).*?(</script>)',
                  lambda m: m.group(1) + "{}" + m.group(2), html, count=1, flags=re.S)
    # 3) keep or drop K/DEF from the working board
    if cfg["keep_kdef"]:
        html = sub_once(html, r'const BOARD = DATA\.board\.filter\([^;]*\);',
                        "const BOARD = DATA.board.slice();", "BOARD filter")
    # 4) fresh snapshot (never carry another league's roster) + new version
    html = sub_once(html, r'const SNAP_VER = "[^"]*";', f'const SNAP_VER = "{key}-fresh";', "SNAP_VER")
    html = sub_once(html, r'const SNAPSHOT = \{.*?\};',
                    'const SNAPSHOT = {"teams":%d,"mine":[],"drafted":[]};' % cfg["teams"], "SNAPSHOT")
    # 5) lineup constants
    html = sub_once(html, r'const STARTERS = \{[^}]*\};',
                    "const STARTERS = " + json.dumps(cfg["starters"]).replace('"', "") + ";", "STARTERS")
    html = sub_once(html, r'const FLEX = \d+, SUPER_FLEX = \d+, BENCH = \d+;',
                    f'const FLEX = {cfg["flex"]}, SUPER_FLEX = {cfg["super_flex"]}, BENCH = {cfg["bench"]};', "FLEX")
    html = sub_once(html, r'const CAPS = \{[^}]*\};[^\n]*',
                    "const CAPS = " + json.dumps(cfg["caps"]).replace('"', "") + ";", "CAPS")
    html = sub_once(html, r'const MUSTFILL_BONUS=\{[^}]*\};[^\n]*',
                    "const MUSTFILL_BONUS=" + json.dumps(cfg["mustfill"]).replace('"', "") + ";", "MUSTFILL")
    html = sub_once(html, r'const SUPER_FLEX_WEIGHTS = \{[^}]*\};',
                    "const SUPER_FLEX_WEIGHTS = " + json.dumps(cfg["sf_weights"]).replace('"', "") + ";", "SF_WEIGHTS")
    # 6) storage key (isolated per league)
    html = sub_once(html, r'const KEY = "[^"]*";[^\n]*', f'const KEY = "{cfg["key"]}";', "KEY")
    # 7) header defaults
    html = re.sub(r'(id="teams" type="number" min="4" max="20" value=")\d+(")',
                  rf'\g<1>{cfg["teams"]}\g<2>', html, count=1)
    html = re.sub(r'(id="slot" type="number" min="1" value=")\d+(")',
                  rf'\g<1>{cfg["slot"]}\g<2>', html, count=1)
    # 8) roster-slot display + format blurb + title
    html = sub_once(html, r'const slotDefs=\[.*?\];[^\n]*',
                    f'const slotDefs={cfg["slotdefs"]};', "slotDefs")
    html = sub_once(html, r'`\$\{TEAMS\}-team · \$\{SCORING_LABEL\[SCORING\]\}[^`]*`',
                    cfg["fmt"], "fmt blurb")
    html = sub_once(html, r'<title>[^<]*</title>', f'<title>{cfg["title"]}</title>', "title")

    # 9) optional custom brand/header + theme (font link into <head>, CSS before </style>)
    if cfg.get("brand_html"):
        html = sub_once(html, r'<div class="brand">.*?</div>',
                        '<div class="brand">' + cfg["brand_html"] + '</div>', "brand")
    if cfg.get("theme_head"):
        html = html.replace('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo',
                             cfg["theme_head"] + '\n<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo', 1)
    if cfg.get("theme_css"):
        html = html.replace("</style>", cfg["theme_css"] + "\n</style>", 1)

    out = ROOT / cfg["out"]
    out.write_text(html, encoding="utf-8")
    print(f"Built {cfg['out']} — {len(board)} players "
          f"({sum(1 for p in board if p['pos'] in ('K','DEF'))} K/DEF), "
          f"{cfg['teams']}-team, slot {cfg['slot']}, key {cfg['key']}")


if __name__ == "__main__":
    main()
