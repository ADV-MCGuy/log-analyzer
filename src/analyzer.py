"""
analyzer.py - Analyze logs and extract metrics
"""

from log_parser import parse_log_file, get_error_pattern
from database import LogDatabase


def analyze_logs(log_filepath, db_path='data/logs.db'):
    """
    Parse log file and analyze it.
    
    Args:
        log_filepath (str): Path to log file
        db_path (str): Path to database
    """
    # Parse logs
    print(f"Parsing log file: {log_filepath}")
    entries = parse_log_file(log_filepath)
    
    if not entries:
        print("No logs to analyze")
        return
    
    # Connect to database
    db = LogDatabase(db_path)
    db.connect()
    
    print(f"Analyzing {len(entries)} log entries...")
    
    # Store entries and build metrics
    for entry in entries:
        # Insert raw entry
        error_pattern = get_error_pattern(entry.message) if entry.level in ['ERROR', 'CRITICAL', 'WARNING'] else None
        db.insert_log_entry(entry, error_pattern)
        
        # Update metrics for errors/warnings
        if entry.level in ['ERROR', 'CRITICAL', 'WARNING']:
            db.insert_error_metric(error_pattern, entry.level, entry.component, entry.timestamp)
    
    # Print summary
    print_analysis_summary(db)
    
    db.close()
    return db_path


def print_analysis_summary(db):
    """Print a summary of the analysis."""
    print("\n" + "="*60)
    print("LOG ANALYSIS SUMMARY")
    print("="*60)
    
    # Total by level
    print("\nEntries by Level:")
    for level, count in db.get_total_by_level():
        print(f"  {level}: {count}")
    
    # Top errors
    print("\nTop Errors:")
    for i, (pattern, level, component, count, first, last) in enumerate(db.get_top_errors(5), 1):
        print(f"  {i}. [{component}] {count}x - {pattern[:60]}")
    
    # Errors by component
    print("\nErrors by Component:")
    for component, level, count in db.get_errors_by_component():
        print(f"  {component}: {count} {level}s")
    
    print("="*60 + "\n")