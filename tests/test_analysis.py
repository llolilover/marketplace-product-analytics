"""Run: python -m unittest discover -s tests -v"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from analysis import generate, build_db, proportions, srm_test, SQL, DATA, query


class TestStatistics(unittest.TestCase):
    def test_no_difference(self):
        self.assertEqual(proportions(100, 1000, 100, 1000)['p_value'], 1.0)

    def test_obvious_effect(self):
        stats = proportions(100, 1000, 200, 1000)
        self.assertGreater(stats['ci95_lower'], 0)
        self.assertLess(stats['p_value'], 0.05)

    def test_srm(self):
        self.assertFalse(srm_test(1000, 1000)['srm_flag_p_lt_0_001'])
        self.assertTrue(srm_test(100, 500)['srm_flag_p_lt_0_001'])

    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            proportions(10, 2, 3, 5)


class TestDatabase(unittest.TestCase):
    def test_generated_mart_and_deduplication(self):
        # Existing project's generated CSV is regenerated with a stable seed.
        generate(20000, 2026)
        with tempfile.TemporaryDirectory() as tmp:
            db = build_db(Path(tmp) / 'test.sqlite')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM user_funnel_mart').fetchone()[0], 20000)
            self.assertEqual(db.execute('SELECT SUM(exposed) FROM user_funnel_mart').fetchone()[0], 20000)
            self.assertEqual(db.execute('SELECT COUNT(*) - COUNT(DISTINCT event_id) FROM clean_events').fetchone()[0], 0)
            violations = db.execute('SELECT COUNT(*) FROM user_funnel_mart WHERE messaged > contacted OR contacted > viewed OR viewed > exposed').fetchone()[0]
            self.assertEqual(violations, 0)
            quality = {r['issue']: r['n'] for r in query(db, '06_quality.sql')}
            self.assertGreater(quality['duplicate_event_ids'], 0)
            self.assertGreater(quality['orphan_messages'], 0)
            db.close()


if __name__ == '__main__':
    unittest.main()
