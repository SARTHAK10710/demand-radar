"""Command-line entry point for Demand Radar.

    python -m demand_radar configs/shortform_video.yaml
    python -m demand_radar configs/shortform_video.yaml --live-ingest
    python -m demand_radar configs/shortform_video.yaml --offline
"""

from __future__ import annotations

import argparse
import os
import sys

from .config import Config
from .export import write_campaign, write_kami
from .pipeline import run
from .report import render_console


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="demand-radar",
        description="Derive a product's ICP from real demand signals, "
                    "instead of guessing it.",
    )
    p.add_argument("config", help="Path to a product config .yaml")
    p.add_argument("--live-ingest", action="store_true",
                   help="Also pull posts live from configured sources (best effort).")
    p.add_argument("--offline", action="store_true",
                   help="Force heuristic mode — never call the LLM (no key needed).")
    p.add_argument("--live", action="store_true",
                   help="Force LLM mode even if no key is auto-detected.")
    p.add_argument("--outdir", default="outputs", help="Where to write reports.")
    p.add_argument("--no-write", action="store_true", help="Don't write report files.")
    p.add_argument("--leads", type=int, default=None, help="Override number of leads.")
    p.add_argument("--max-posts", type=int, default=None,
                   help="Cap total posts analysed (useful for API rate/quota budgets).")
    p.add_argument("--export", action="store_true",
                   help="Also write a GTM handoff JSON (the brain->arms seam).")
    p.add_argument("--export-format", default="generic", choices=["generic", "kami"],
                   help="'generic' = executor-agnostic campaign; 'kami' = Kami-contract "
                        "demand signals + segment sizing. Default: generic.")
    p.add_argument("--export-objective", default="sales", choices=["sales", "marketing"],
                   help="Campaign objective for generic --export (default: sales).")
    p.add_argument("--model", default=None, help="Override the Claude model id.")
    p.add_argument("--quiet", action="store_true", help="Suppress step-by-step logging.")
    return p


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252 and choke on the report glyphs; make
    # stdout/stderr UTF-8 where the platform allows it.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    args = build_parser().parse_args(argv)

    try:
        config = Config.load(args.config)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.leads is not None:
        config.lead_count = args.leads
    if args.model is not None:
        config.model = args.model

    logger = (lambda *_: None) if args.quiet else print

    result = run(
        config,
        live_ingest=args.live_ingest,
        prefer_offline=args.offline,
        force_live=args.live,
        outdir=args.outdir,
        write=not args.no_write,
        max_posts=args.max_posts,
        logger=logger,
    )

    print(render_console(result.config, result.segments, result.leads, result.meta))

    export_path = None
    if args.export:
        slug = result.config.name or "run"
        if args.export_format == "kami":
            export_path = write_kami(
                os.path.join(args.outdir, f"{slug}_kami.json"), result.config, result)
            export_label = "kami"
        else:
            export_path = write_campaign(
                os.path.join(args.outdir, f"{slug}_campaign.json"),
                result.config, result, objective=args.export_objective)
            export_label = "campaign"

    if result.paths or export_path:
        print(f"\nWritten to: {args.outdir}/")
        for kind, path in (result.paths or {}).items():
            print(f"  {kind:<9} {path}")
        if export_path:
            note = ("Kami-contract demand signals + sizing" if args.export_format == "kami"
                    else "executor-agnostic GTM handoff")
            print(f"  {export_label:<9} {export_path}   ({note})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
