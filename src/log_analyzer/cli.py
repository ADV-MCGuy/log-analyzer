"""
cli.py - Command line interface for log analyzer

Usage:
    logan ingest FILE [FILE ...] [--year YEAR] [--replace]
    logan summary [--source ID] [--top N]
    logan sources
    logan remove ID
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime

from . import __version__
from .analyzer import ingest_file, print_analysis_summary
from .database import DatabaseError, LogDatabase

DEFAULT_DB = 'logan.db'


def cmd_ingest(db, args):
    status = 0
    for path in args.files:
        try:
            result = ingest_file(db, path, args.year, replace=args.replace)
        except OSError as e:
            print(f"{path}: {e.strerror or e}", file=sys.stderr)
            status = 1
            continue

        if result.skipped_because:
            ids = ', '.join(f"#{s[0]}" for s in result.skipped_because)
            print(f"{path}: skipped, already ingested as source {ids} (use --replace to re-ingest)")
            continue

        replaced = f", replaced #{', #'.join(map(str, result.replaced))}" if result.replaced else ''
        print(f"{path}: {result.entry_count} entries, {result.stats.unparsed} unparsed lines "
              f"(source #{result.source_id}{replaced})")

        if result.stats.unparsed and args.verbose:
            for line_no, text in result.stats.unparsed_samples:
                print(f"    line {line_no}: {text[:100]}")
            if result.stats.unparsed > len(result.stats.unparsed_samples):
                print(f"    ... and {result.stats.unparsed - len(result.stats.unparsed_samples)} more")
    return status


def cmd_summary(db, args):
    if args.source is not None and db.get_source(args.source) is None:
        print(f"No source #{args.source}. Run 'logan sources' to list them.", file=sys.stderr)
        return 1
    print_analysis_summary(db, args.source, args.top)
    return 0


def cmd_sources(db, args):
    sources = db.list_sources()
    if not sources:
        print("No sources ingested yet.")
        return 0
    print(f"{'ID':>4}  {'ENTRIES':>8}  {'UNPARSED':>8}  {'INGESTED':<19}  PATH")
    for source_id, path, _sha, ingested_at, entry_count, unparsed_count in sources:
        print(f"{source_id:>4}  {entry_count:>8}  {unparsed_count:>8}  {ingested_at:<19}  {path}")
    return 0


def cmd_remove(db, args):
    with db.transaction():
        removed = db.remove_source(args.source)
    if not removed:
        print(f"No source #{args.source}.", file=sys.stderr)
        return 1
    print(f"Removed source #{args.source}.")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog='logan',
        description='Offline log analyzer: ingest log files into SQLite and pull them apart.')
    parser.add_argument('--db', default=os.environ.get('LOGAN_DB', DEFAULT_DB),
                        help=f'database file (default: $LOGAN_DB or ./{DEFAULT_DB})')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    sub = parser.add_subparsers(dest='command', metavar='COMMAND')
    sub.required = True

    p = sub.add_parser('ingest', help='parse log files into the database')
    p.add_argument('files', nargs='+', metavar='FILE')
    p.add_argument('--year', type=int, default=datetime.now().year,
                   help='year of the first entry, since the log format has none (default: current year)')
    p.add_argument('--replace', action='store_true',
                   help='re-ingest files that were already ingested, replacing the old copy')
    p.add_argument('-v', '--verbose', action='store_true', help='show lines that failed to parse')
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser('summary', help='summarize levels, top errors and warnings')
    p.add_argument('--source', type=int, metavar='ID', help='only this source (default: all)')
    p.add_argument('--top', type=int, default=5, metavar='N', help='how many patterns to show (default: 5)')
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser('sources', help='list ingested files')
    p.set_defaults(func=cmd_sources)

    p = sub.add_parser('remove', help='remove an ingested file and its entries')
    p.add_argument('source', type=int, metavar='ID')
    p.set_defaults(func=cmd_remove)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    db = LogDatabase(args.db)
    try:
        db.connect()
        return args.func(db, args)
    except (DatabaseError, sqlite3.Error) as e:
        print(f"logan: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        db.close()
