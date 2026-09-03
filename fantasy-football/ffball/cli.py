"""Command-line interface for ffball.

Usage:
    python3 -m ffball init [--scoring ppr] [--roster standard_12] [--league-id <id>]
    python3 -m ffball board [--pos RB] [--limit 30]
    python3 -m ffball tiers [--pos RB]
    python3 -m ffball draft --slot 5        # interactive draft-day assistant
    python3 -m ffball roster
    python3 -m ffball sync --league-id <id> [--draft-id <id>]   # pull from Sleeper

Everything works offline against the bundled sample data; ``sync`` needs network
access to api.sleeper.app.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .db import Database
from .draft import DraftState, recommend
from .league import LeagueConfig
from .models import POSITIONS, Player
from .namematch import find
from .projections import load_players
from .scoring import ScoringSystem
from .valuation import build_board


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _load_config(db: Database) -> tuple[ScoringSystem, LeagueConfig]:
    scoring_name = db.get_meta("scoring", "ppr")
    roster_name = db.get_meta("roster", "standard_12")
    scoring = ScoringSystem.from_preset(scoring_name)
    league = LeagueConfig.from_preset(roster_name)
    teams_override = db.get_meta("teams", None)
    if teams_override:
        league.teams = int(teams_override)
    return scoring, league


def _fmt_player(p: Player, show_score: Optional[float] = None) -> str:
    tag = f"{p.position}{p.pos_rank or '?'}"
    inj = f" [{p.injury_status}]" if p.injury_status else ""
    bye = f" bye{p.bye_week}" if p.bye_week else ""
    adp = f" adp{p.adp:.0f}" if p.adp is not None else ""
    score = f"  score {show_score:.1f}" if show_score is not None else ""
    return (
        f"{(p.overall_rank or 0):>3}. {p.name:<24} {tag:<5} "
        f"pts {p.proj_points:>6.1f}  VBD {p.vbd:>+6.1f}  T{p.tier or '-'}"
        f"{adp}{bye}{inj}{score}"
    )


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def cmd_init(args) -> int:
    db = Database(args.db)
    league: LeagueConfig
    scoring: ScoringSystem

    if args.league_id:
        # Pull real league settings from Sleeper.
        from .sleeper import Sleeper
        sl = Sleeper()
        lg = sl.league(args.league_id)
        if not lg:
            print(f"Could not load league {args.league_id} from Sleeper.", file=sys.stderr)
            return 1
        scoring = ScoringSystem.from_sleeper_league(lg)
        league = LeagueConfig.from_sleeper_league(lg)
        db.set_meta("league_id", args.league_id)
        db.set_meta("scoring", "ppr")   # preset name unknown; settings stored below
        db.set_meta("scoring_settings", scoring.settings)
        print(f"Loaded league '{league.name}': {league.summary()} | PPR={scoring.is_ppr()}")
    else:
        scoring = ScoringSystem.from_preset(args.scoring)
        league = LeagueConfig.from_preset(args.roster)
        if args.teams:
            league.teams = args.teams
            db.set_meta("teams", args.teams)
        else:
            db.set_meta("teams", None)
        db.set_meta("scoring", args.scoring)
        db.set_meta("roster", args.roster)
        print(f"Config: scoring={args.scoring}, roster={league.summary()}")

    players = load_players()
    if not players:
        print("No projections found. Add CSVs to data/projections/ or keep the sample.",
              file=sys.stderr)
        return 1
    board = build_board(players, scoring, league)
    db.save_board(board)
    print(f"Built value board for {len(board)} players. Saved to {db.path}")
    print("\nTop 10 overall:")
    for p in board[:10]:
        print("  " + _fmt_player(p))
    db.close()
    return 0


def cmd_board(args) -> int:
    db = Database(args.db)
    board = db.load_board()
    if not board:
        print("No board yet. Run: python3 -m ffball init", file=sys.stderr)
        return 1
    if args.pos:
        board = [p for p in board if p.position == args.pos.upper()]
    for p in board[: args.limit]:
        print(_fmt_player(p))
    db.close()
    return 0


def cmd_tiers(args) -> int:
    db = Database(args.db)
    board = db.load_board()
    if not board:
        print("No board yet. Run: python3 -m ffball init", file=sys.stderr)
        return 1
    positions = [args.pos.upper()] if args.pos else POSITIONS
    for pos in positions:
        pos_players = [p for p in board if p.position == pos]
        if not pos_players:
            continue
        print(f"\n=== {pos} ===")
        last_tier = None
        for p in sorted(pos_players, key=lambda x: x.vbd, reverse=True)[: args.limit]:
            if p.tier != last_tier:
                print(f"  -- Tier {p.tier} --")
                last_tier = p.tier
            print("   " + _fmt_player(p))
    db.close()
    return 0


def cmd_roster(args) -> int:
    db = Database(args.db)
    board = {p.player_id: p for p in db.load_board()}
    mine = db.my_player_ids()
    if not mine:
        print("You haven't drafted anyone yet.")
        return 0
    print("Your team:")
    total = 0.0
    for pid in mine:
        p = board.get(pid)
        if p:
            print("  " + _fmt_player(p))
            total += p.proj_points
    print(f"\nProjected starting-pool points (raw sum): {total:.1f}")
    db.close()
    return 0


def _resolve_one(query: str, board: List[Player], drafted: set) -> Optional[Player]:
    matches = [p for p in find(query, board) if p.player_id not in drafted]
    if not matches:
        print(f"  ? no available match for '{query}'")
        return None
    if len(matches) > 1 and _norm_len(matches, query):
        print(f"  ? ambiguous '{query}':")
        for p in matches[:6]:
            print("     - " + _fmt_player(p))
        print("    (type more of the name)")
        return None
    return matches[0]


def _norm_len(matches, query) -> bool:
    # Treat as ambiguous only if the top match isn't an obvious exact/prefix win.
    return not (len(query) >= 3 and matches[0].name.lower().startswith(query.lower()))


def _print_recs(state: DraftState, board: List[Player]) -> None:
    recs = recommend(state, board)
    if not recs:
        print("  (no recommendations — board exhausted?)")
        return
    nxt = state.picks_until_next()
    hdr = f"  On the clock — pick {state.current_overall}"
    if nxt:
        hdr += f" (your next pick in {nxt} picks)"
    print(hdr + ". Recommended:")
    for i, s in enumerate(recs, 1):
        print(f"   {i}. {s.player.name:<22} {s.player.position:<3} "
              f"[{s.reason}]")


def cmd_draft(args) -> int:
    db = Database(args.db)
    board = db.load_board()
    if not board:
        print("No board yet. Run: python3 -m ffball init", file=sys.stderr)
        return 1
    scoring, league = _load_config(db)
    state = DraftState(league=league, my_slot=args.slot,
                       drafted_ids=db.drafted_ids(), my_player_ids=db.my_player_ids())

    print(f"Draft assistant — {league.summary()} | you are slot {args.slot}")
    print("Commands: 'me <player>' (you pick), '<player>' or 'x <player>' (someone else),")
    print("          'rec', 'board [POS]', 'roster', 'undo', 'help', 'quit'\n")
    if state.is_my_turn():
        _print_recs(state, board)

    board_by_id = {p.player_id: p for p in board}
    drafted = set(state.drafted_ids)

    while True:
        try:
            line = input("draft> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            if state.is_my_turn():
                _print_recs(state, board)
            continue
        cmd, _, rest = line.partition(" ")
        cmd = cmd.lower()

        if cmd in ("quit", "q", "exit"):
            break
        elif cmd == "help":
            print("  me <player> | x <player> | <player> | rec | board [POS] | roster | undo | quit")
        elif cmd == "rec":
            _print_recs(state, board)
        elif cmd == "roster":
            for pid in state.my_player_ids:
                p = board_by_id.get(pid)
                if p:
                    print("   " + _fmt_player(p))
        elif cmd == "board":
            pos = rest.strip().upper() or None
            shown = [p for p in board if p.player_id not in drafted
                     and (pos is None or p.position == pos)]
            for p in shown[:15]:
                print("   " + _fmt_player(p))
        elif cmd == "undo":
            if not state.drafted_ids:
                print("  nothing to undo")
                continue
            last = state.drafted_ids.pop()
            drafted.discard(last)
            if state.my_player_ids and state.my_player_ids[-1] == last:
                state.my_player_ids.pop()
            db.reset_draft()
            for i, pid in enumerate(state.drafted_ids, 1):
                db.record_pick(i, pid, state.overall_to_slot(i), pid in state.my_player_ids)
            print(f"  undid {board_by_id.get(last, Player(last, last, '?')).name}")
            if state.is_my_turn():
                _print_recs(state, board)
        else:
            # A pick. 'me X' = my pick; 'x X' or bare 'X' = someone else's.
            mine = False
            query = line
            if cmd == "me":
                mine, query = True, rest
            elif cmd == "x":
                query = rest
            player = _resolve_one(query.strip(), board, drafted)
            if not player:
                continue
            overall = state.current_overall
            slot = state.overall_to_slot(overall)
            state.drafted_ids.append(player.player_id)
            drafted.add(player.player_id)
            if mine:
                state.my_player_ids.append(player.player_id)
            db.record_pick(overall, player.player_id, slot, mine)
            who = "YOU" if mine else f"slot {slot}"
            print(f"  pick {overall} ({who}): {player.name} {player.position}")
            if state.is_my_turn():
                _print_recs(state, board)

    db.close()
    return 0


def cmd_sync(args) -> int:
    """Pull live data from Sleeper: league settings and/or an in-progress draft."""
    from .sleeper import Sleeper
    db = Database(args.db)
    sl = Sleeper()

    if args.league_id:
        lg = sl.league(args.league_id)
        if lg:
            scoring = ScoringSystem.from_sleeper_league(lg)
            league = LeagueConfig.from_sleeper_league(lg)
            db.set_meta("scoring_settings", scoring.settings)
            db.set_meta("league_id", args.league_id)
            players = load_players()
            board = build_board(players, scoring, league)
            db.save_board(board)
            print(f"Synced league '{league.name}' and rebuilt board ({len(board)} players).")

    if args.draft_id:
        players_map = sl.players()  # cached daily
        picks = sl.draft_picks(args.draft_id)
        db.reset_draft()
        board_by_id = {p.player_id: p for p in db.load_board()}
        for pick in picks:
            pid = pick.get("player_id")
            overall = pick.get("pick_no")
            slot = pick.get("draft_slot")
            # Map Sleeper player_id -> our board id via name when needed.
            local = board_by_id.get(pid)
            if not local:
                meta = players_map.get(pid) or {}
                from .sleeper import player_display
                cand = find(player_display(meta), list(board_by_id.values()))
                local = cand[0] if cand else None
            if local and overall:
                is_mine = (slot == args.slot) if args.slot else False
                db.record_pick(overall, local.player_id, slot or 0, is_mine)
        print(f"Synced {len(picks)} draft picks from Sleeper draft {args.draft_id}.")

    db.close()
    return 0


# --------------------------------------------------------------------------
# argparse wiring
# --------------------------------------------------------------------------
def cmd_doctor(args) -> int:
    """Connectivity self-check: what can this environment actually reach?"""
    import os
    import urllib.request
    import urllib.error

    def probe(url: str, timeout: int = 15):
        req = urllib.request.Request(url, headers={"User-Agent": "ffball/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp.read(200)
                return True, f"HTTP {resp.status}"
        except urllib.error.HTTPError as exc:
            # A 4xx still proves we reached the host.
            return True, f"HTTP {exc.code} (reachable)"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc).splitlines()[0][:80]

    print("ffball doctor — connectivity self-check\n")
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    print(f"HTTPS proxy: {proxy or '(none)'}\n")

    targets = [
        ("Sleeper API        (live league sync)", "https://api.sleeper.app/v1/state/nfl"),
        ("GitHub raw         (fetch fallback)  ", "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values-players.csv"),
    ]
    results = {}
    for label, url in targets:
        ok, detail = probe(url)
        results[label.strip()] = ok
        mark = "OK  ✓" if ok else "BLOCKED ✗"
        print(f"  [{mark:>10}]  {label}  {detail}")

    sleeper_ok = results.get("Sleeper API        (live league sync)".strip(), False)
    print()
    if sleeper_ok:
        print("Sleeper is reachable — live league sync is available.")
        if args.league_id:
            from .sleeper import Sleeper
            from .league import LeagueConfig
            from .scoring import ScoringSystem
            lg = Sleeper().league(args.league_id)
            if lg:
                scoring = ScoringSystem.from_sleeper_league(lg)
                league = LeagueConfig.from_sleeper_league(lg)
                print(f"\nLeague '{league.name}':")
                print(f"  format : {league.summary()}")
                print(f"  PPR    : {scoring.is_ppr()} pt/reception")
                print("  Run: python3 -m ffball init --league-id " + args.league_id)
            else:
                print(f"Could not load league {args.league_id}.")
    else:
        print("Sleeper is BLOCKED by this environment's network policy.")
        print("Fix: set the environment's Network access to 'Custom', add")
        print("     api.sleeper.app, keep the default package list checked,")
        print("     then start a NEW session. Meanwhile `ffball fetch` still")
        print("     works via GitHub for real rankings.")
    return 0


def cmd_fetch(args) -> int:
    """Pull real, current FantasyPros redraft ECR + byes + Sleeper crosswalk."""
    from . import sources
    print("Fetching live data from GitHub-hosted nflverse/dynastyprocess ...")
    try:
        path, total, mapped = sources.fetch(scoring=args.scoring, superflex=args.superflex)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Wrote {total} players ({mapped} mapped to a real Sleeper id) -> {path}")
    print(f"Points modeled for '{args.scoring}' scoring. Now run: python3 -m ffball init")
    return 0


def cmd_serve(args) -> int:
    from .web import serve
    serve(db_path=args.db, host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ffball", description="Sleeper fantasy draft assistant")
    p.add_argument("--db", default=None, help="path to the SQLite DB (default: data/ffball.db)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="build the value board")
    pi.add_argument("--scoring", default="ppr", help="scoring preset: ppr|half_ppr|standard")
    pi.add_argument("--roster", default="standard_12", help="roster preset")
    pi.add_argument("--teams", type=int, default=None,
                    help="override team count for any roster preset (e.g. 14, 15, 16)")
    pi.add_argument("--league-id", default=None, help="Sleeper league id (overrides presets)")
    pi.set_defaults(func=cmd_init)

    pb = sub.add_parser("board", help="print the value board")
    pb.add_argument("--pos", default=None)
    pb.add_argument("--limit", type=int, default=30)
    pb.set_defaults(func=cmd_board)

    pt = sub.add_parser("tiers", help="print tiers by position")
    pt.add_argument("--pos", default=None)
    pt.add_argument("--limit", type=int, default=40)
    pt.set_defaults(func=cmd_tiers)

    pd = sub.add_parser("draft", help="interactive draft-day assistant")
    pd.add_argument("--slot", type=int, required=True, help="your draft slot (1..teams)")
    pd.set_defaults(func=cmd_draft)

    pr = sub.add_parser("roster", help="show your drafted team")
    pr.set_defaults(func=cmd_roster)

    ps = sub.add_parser("sync", help="pull league/draft data from Sleeper")
    ps.add_argument("--league-id", default=None)
    ps.add_argument("--draft-id", default=None)
    ps.add_argument("--slot", type=int, default=None)
    ps.set_defaults(func=cmd_sync)

    pdoc = sub.add_parser("doctor", help="connectivity self-check (is Sleeper reachable?)")
    pdoc.add_argument("--league-id", default=None, help="also print league config if Sleeper is up")
    pdoc.set_defaults(func=cmd_doctor)

    pf = sub.add_parser("fetch", help="pull real FantasyPros ECR + Sleeper ids from GitHub")
    pf.add_argument("--scoring", default="ppr", help="points model: ppr|half_ppr|standard")
    pf.add_argument("--superflex", action="store_true",
                    help="use superflex consensus ranking (QBs valued correctly)")
    pf.set_defaults(func=cmd_fetch)

    pw = sub.add_parser("serve", help="run the web dashboard")
    pw.add_argument("--host", default="127.0.0.1")
    pw.add_argument("--port", type=int, default=8787)
    pw.set_defaults(func=cmd_serve)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
