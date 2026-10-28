"""Command-line entry point: ``fantasy <command>``."""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import report

COMMANDS = ("report", "lineup", "waivers", "available", "matchup", "playoffs")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="fantasy", description="Yahoo Fantasy Sports optimizer: lineups, "
        "waiver pickups, matchup win odds and playoff odds.")
    ap.add_argument("--league", default=os.environ.get("YAHOO_LEAGUE_KEY"),
                    help="League key, e.g. 461.l.12345 (or set YAHOO_LEAGUE_KEY)")
    ap.add_argument("--oauth", default=os.environ.get("YAHOO_OAUTH_FILE", "oauth2.json"),
                    help="Path to the yahoo_oauth credentials file")
    ap.add_argument("--demo", choices=["nfl", "nba"],
                    help="Use a synthetic demo league instead of Yahoo")
    ap.add_argument("--cache-ttl", type=float, default=1800,
                    help="Seconds to cache API responses (0 disables)")
    ap.add_argument("--recent-weight", type=float, default=0.5,
                    help="Weight on last-month form vs. full season (0-1)")
    ap.add_argument("--pool", type=int, default=75,
                    help="How many top available players to evaluate")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("auth", help="Set up Yahoo OAuth credentials")
    sub.add_parser("leagues", help="List your leagues for the current season")
    for name, help_ in [
        ("report", "Full weekly report (matchup, lineup, pickups, playoff odds)"),
        ("lineup", "Optimal start/sit for this week"),
        ("waivers", "Best add/drop moves"),
        ("available", "Top available players"),
        ("matchup", "This week's win probability"),
        ("playoffs", "Playoff odds from a season simulation"),
    ]:
        p = sub.add_parser(name, help=help_)
        p.add_argument("--top", type=int, default=10, help="Rows to show")
        p.add_argument("--sims", type=int, default=3000, help="Season simulations")
        p.add_argument("--week-weight", type=float, default=0.35,
                       help="Waivers: weight on this week vs rest of season (0-1)")
    return ap


def cmd_auth(args):
    from yahoo_oauth import OAuth2
    if not os.path.exists(args.oauth):
        print("Create an app at https://developer.yahoo.com/apps/create/ "
              "(API permissions: Fantasy Sports - Read/Write, redirect URI: "
              "https://localhost:8080 or oob).")
        key = input("Client ID (consumer key): ").strip()
        secret = input("Client secret (consumer secret): ").strip()
        with open(args.oauth, "w") as f:
            json.dump({"consumer_key": key, "consumer_secret": secret}, f, indent=2)
        os.chmod(args.oauth, 0o600)
    sc = OAuth2(None, None, from_file=args.oauth)
    if not sc.token_is_valid():
        sc.refresh_access_token()
    print(f"Authenticated. Tokens stored in {args.oauth}. Next: `fantasy leagues`.")


def make_source(args):
    if args.demo:
        from .demo import DemoSource
        return DemoSource(args.demo)
    from .yahoo_source import YahooSource
    return YahooSource(args.oauth, args.league, cache_ttl=args.cache_ttl)


def cmd_leagues(args):
    src = make_source(args)
    if args.demo:
        info = src.league_info()
        rows = [[info.league_key, info.name, info.game_code, info.season, info.scoring_type]]
    else:
        rows = [[l["league_key"], l["name"], l["game_code"], l["season"], l["scoring_type"]]
                for l in src.list_leagues()]
    print(report.table(rows, ["League key", "Name", "Sport", "Season", "Scoring"],
                       ["<"] * 5))
    print("\nUse one with --league <key> or export YAHOO_LEAGUE_KEY=<key>.")


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "auth":
        return cmd_auth(args)
    if args.command == "leagues":
        return cmd_leagues(args)

    from .analysis import Analysis
    from .matchup import my_outlook
    analysis = Analysis.load(make_source(args), args.recent_weight, args.pool)
    print(report.render_header(analysis))
    if args.command == "report":
        print(report.render_report(analysis, args.top, args.sims, args.week_weight)
              .split("\n", 2)[2])
    elif args.command == "lineup":
        print(report.render_lineup(analysis))
    elif args.command == "waivers":
        print(report.render_waivers(analysis, my_outlook(analysis), args.top, args.week_weight))
    elif args.command == "available":
        print(report.render_available(analysis, args.top))
    elif args.command == "matchup":
        print(report.render_matchup(analysis, my_outlook(analysis)))
    elif args.command == "playoffs":
        print(report.render_playoffs(analysis, args.sims))


if __name__ == "__main__":
    sys.exit(main())
