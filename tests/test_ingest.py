"""
Tests for parsing and ingesting. Run from the project root:

    python3 -m unittest discover -s tests
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from log_analyzer.analyzer import ingest_file  # noqa: E402
from log_analyzer.database import LogDatabase  # noqa: E402
from log_analyzer.log_parser import ParseStats, get_message_pattern, parse_log_file, parse_log_line  # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), '..', 'data', 'sample_logs.txt')


class ParserTests(unittest.TestCase):

    def test_parses_line_with_year(self):
        entry = parse_log_line('07 Sep 14:27:29 [info] Laser Range Finder | Sent stop', 2026)
        self.assertEqual(entry.timestamp, datetime(2026, 9, 7, 14, 27, 29))
        self.assertEqual(entry.level, 'INFO')
        self.assertEqual(entry.component, 'Laser Range Finder')
        self.assertEqual(entry.message, 'Sent stop')

    def test_rejects_garbage(self):
        self.assertIsNone(parse_log_line('Traceback (most recent call last):', 2026))
        self.assertIsNone(parse_log_line('07 Foo 14:27:29 [INFO] X | y', 2026))

    def test_year_rolls_over_at_new_year(self):
        stats = ParseStats()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'a.log')
            with open(path, 'w') as f:
                f.write('31 Dec 23:59:59 [INFO] A | before\n'
                        '01 Jan 00:00:01 [INFO] A | after\n')
            entries = list(parse_log_file(path, 2025, stats))
        self.assertEqual([e.timestamp.year for e in entries], [2025, 2026])

    def test_counts_unparsed_lines(self):
        stats = ParseStats()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'a.log')
            with open(path, 'w') as f:
                f.write('07 Sep 14:27:29 [INFO] A | ok\nnot a log line\n\n')
            entries = list(parse_log_file(path, 2026, stats))
        self.assertEqual(len(entries), 1)
        self.assertEqual(stats.unparsed, 1)
        self.assertEqual(stats.unparsed_samples, [(2, 'not a log line')])

    def test_pattern_masks_numbers(self):
        self.assertEqual(get_message_pattern('Battery voltage dropping: 11.2V'),
                         'Battery voltage dropping: NUMV')


class IngestTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = LogDatabase(os.path.join(self.tmp.name, 'test.db'))
        self.db.connect()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def write_log(self, name, text):
        path = os.path.join(self.tmp.name, name)
        with open(path, 'w') as f:
            f.write(text)
        return path

    def level_counts(self):
        return dict(self.db.get_total_by_level())

    def test_ingesting_twice_does_not_double_count(self):
        first = ingest_file(self.db, SAMPLE, 2026)
        second = ingest_file(self.db, SAMPLE, 2026)
        self.assertEqual(first.entry_count, 18)
        self.assertTrue(second.skipped_because)
        self.assertEqual(self.level_counts()['ERROR'], 5)

    def test_identical_copy_is_skipped(self):
        ingest_file(self.db, SAMPLE, 2026)
        with open(SAMPLE) as f:
            copy = self.write_log('copy.log', f.read())
        self.assertTrue(ingest_file(self.db, copy, 2026).skipped_because)

    def test_replace_reingests_changed_file(self):
        path = self.write_log('a.log', '07 Sep 14:00:00 [ERROR] A | boom\n')
        ingest_file(self.db, path, 2026)
        self.write_log('a.log', '07 Sep 14:00:00 [ERROR] A | boom\n07 Sep 14:00:01 [ERROR] A | boom\n')
        result = ingest_file(self.db, path, 2026, replace=True)
        self.assertEqual(result.replaced, [1])
        self.assertEqual(len(self.db.list_sources()), 1)
        self.assertEqual(self.level_counts(), {'ERROR': 2})

    def test_same_message_in_two_components_is_two_groups(self):
        path = self.write_log('a.log',
                              '07 Sep 14:00:00 [ERROR] Motor | Device not responding\n'
                              '07 Sep 14:00:01 [ERROR] Laser | Device not responding\n')
        ingest_file(self.db, path, 2026)
        components = sorted(row[2] for row in self.db.get_top_errors())
        self.assertEqual(components, ['Laser', 'Motor'])

    def test_time_span_sorts_across_months(self):
        path = self.write_log('a.log',
                              '30 Sep 23:00:00 [INFO] A | x\n'
                              '01 Oct 01:00:00 [INFO] A | y\n')
        ingest_file(self.db, path, 2026)
        self.assertEqual(self.db.get_time_span(), ('2026-09-30 23:00:00', '2026-10-01 01:00:00'))

    def test_summary_can_be_scoped_to_one_source(self):
        a = ingest_file(self.db, self.write_log('a.log', '07 Sep 14:00:00 [ERROR] A | x\n'), 2026)
        ingest_file(self.db, self.write_log('b.log', '07 Sep 14:00:00 [WARNING] B | y\n'), 2026)
        self.assertEqual(dict(self.db.get_total_by_level(a.source_id)), {'ERROR': 1})


if __name__ == '__main__':
    unittest.main()
