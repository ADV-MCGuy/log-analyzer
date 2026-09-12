"""
main.py - Entry point for log analyzer
"""

import sys
from analyzer import analyze_logs


def main():
    """Main function."""
    
    if len(sys.argv) > 1:
        log_file = sys.argv[1]
    else:
        log_file = input("Enter log file path: ")
    
    print(f"Starting log analysis...")
    analyze_logs(log_file)
    print("Analysis complete!")


if __name__ == '__main__':
    main()