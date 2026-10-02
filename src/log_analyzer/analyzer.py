"""
analyzer.py - Ingest log files and summarize them
"""

import hashlib
import os

from .log_parser import ParseStats, parse_log_file, get_message_pattern


class IngestResult:
    """Outcome of ingesting one file."""

    def __init__(self, path, source_id=None, entry_count=0, stats=None, skipped_because=None, replaced=None):
        self.path = path
        self.source_id = source_id
        self.entry_count = entry_count
        self.stats = stats or ParseStats()
        self.skipped_because = skipped_because  # existing source rows, if skipped
        self.replaced = replaced or []          # ids of sources that were replaced


def file_sha256(path):
    """Hash a file's contents without reading it all into memory."""
    digest = hashlib.sha256()
    with open(path, 'rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def ingest_file(db, path, year, replace=False):
    """
    Parse a log file and store it as a new source.

    A file is skipped if the same path or identical contents were already
    ingested, so running twice doesn't double-count. With replace=True the
    earlier source is removed and the file is ingested again.

    Args:
        db (LogDatabase): Connected database
        path (str): Path to log file
        year (int): Year of the first entry (the log format has no year)
        replace (bool): Replace an existing source instead of skipping

    Returns:
        IngestResult
    """
    path = os.path.abspath(path)
    sha256 = file_sha256(path)

    existing = db.find_sources(path, sha256)
    if existing and not replace:
        return IngestResult(path, skipped_because=existing)

    stats = ParseStats()
    rows = (
        (e.line_no, e.timestamp, e.level, e.component, e.message, get_message_pattern(e.message))
        for e in parse_log_file(path, year, stats)
    )

    # One transaction per file: an error part-way through leaves the database unchanged
    with db.transaction():
        for source in existing:
            db.remove_source(source[0])
        source_id = db.insert_source(path, sha256)
        entry_count = db.insert_entries(source_id, rows)
        db.finish_source(source_id, entry_count, stats.unparsed)

    return IngestResult(path, source_id, entry_count, stats, replaced=[s[0] for s in existing])


def print_analysis_summary(db, source_id=None, limit=5):
    """Print a summary of the analysis."""
    first, last = db.get_time_span(source_id)
    if first is None:
        print("No log entries found. Run 'logan ingest FILE' first.")
        return

    print("\n" + "=" * 60)
    print("LOG ANALYSIS SUMMARY")
    if source_id is not None:
        print(f"Source #{source_id}: {db.get_source(source_id)[1]}")
    print("=" * 60)

    print(f"\nTime span: {first} -> {last}")

    # Total by level
    print("\nEntries by Level:")
    for level, count in db.get_total_by_level(source_id):
        print(f"  {level}: {count}")

    _print_patterns("Top Errors", db.get_top_errors(limit, source_id))
    _print_patterns("Top Warnings", db.get_top_warnings(limit, source_id))

    # Errors by component
    print("\nErrors by Component:")
    rows = db.get_errors_by_component(source_id)
    if not rows:
        print("  (none)")
    for component, level, count in rows:
        print(f"  {component}: {count} {level}")

    print("=" * 60 + "\n")


def _print_patterns(title, rows):
    print(f"\n{title}:")
    if not rows:
        print("  (none)")
    for i, (pattern, level, component, count, first, last) in enumerate(rows, 1):
        print(f"  {i}. [{component}] {count}x - {pattern[:80]}")
        print(f"     first {first}   last {last}")
