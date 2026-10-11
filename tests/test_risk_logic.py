"""Small sanity checks for the project risk rules. Run: python -m unittest discover -s tests"""
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from climate_pipeline import classify_risk  # noqa: E402


class TestRiskLogic(unittest.TestCase):
    def test_normal_day_is_green(self):
        level, reason, score = classify_risk(31.0, 1.0, 45.0, "plains")
        self.assertEqual(level, "GREEN")
        self.assertTrue(reason)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_plains_hot_day_with_departure_is_orange(self):
        level, _, _ = classify_risk(42.0, 5.2, 40.0, "plains")
        self.assertEqual(level, "ORANGE")

    def test_plains_extreme_heat_is_red(self):
        level, _, _ = classify_risk(47.0, 2.0, 35.0, "plains")
        self.assertEqual(level, "RED")

    def test_coastal_heat_departure_triggers_alert(self):
        level, _, _ = classify_risk(38.0, 5.0, 80.0, "coastal")
        self.assertEqual(level, "ORANGE")


if __name__ == "__main__":
    unittest.main()
