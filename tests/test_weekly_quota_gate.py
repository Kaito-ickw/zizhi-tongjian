import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.weekly_quota_gate import (
    Quota,
    begin,
    complete,
    evaluate,
    reset_state,
    rollover_state,
)


UTC = timezone.utc


class WeeklyQuotaGateTest(unittest.TestCase):
    def test_shadow_observes_but_does_not_block(self):
        now = datetime(2026, 8, 11, tzinfo=UTC)
        quota = Quota(80.0, now + timedelta(days=4))
        state = reset_state(quota.resets_at, now)
        decision = evaluate(state, quota, "drain", now)
        self.assertTrue(decision["shadow"])
        self.assertEqual("SKIP", decision["would_verdict"])
        self.assertEqual("RUN", decision["verdict"])

    def test_shadow_never_bypasses_absolute_ceiling(self):
        now = datetime(2026, 8, 11, tzinfo=UTC)
        quota = Quota(90.0, now + timedelta(days=4))
        state = reset_state(quota.resets_at, now)
        decision = evaluate(state, quota, "drain", now)
        self.assertTrue(decision["shadow"])
        self.assertEqual("SKIP", decision["verdict"])

    def test_high_other_project_rate_blocks_after_observation(self):
        now = datetime(2026, 8, 11, tzinfo=UTC)
        quota = Quota(60.0, now + timedelta(days=3))
        state = reset_state(quota.resets_at, now - timedelta(days=3))
        state["external_intervals"] = [
            {
                "start": (now - timedelta(days=2)).isoformat(),
                "end": now.isoformat(),
                "hours": 48,
                "points": 16,
            }
        ]
        decision = evaluate(state, quota, "drain", now)
        self.assertFalse(decision["shadow"])
        self.assertEqual("SKIP", decision["verdict"])

    def test_low_other_project_rate_allows_late_catch_up(self):
        now = datetime(2026, 8, 11, tzinfo=UTC)
        quota = Quota(60.0, now + timedelta(days=3))
        state = reset_state(quota.resets_at, now - timedelta(days=3))
        state["external_intervals"] = [
            {
                "start": (now - timedelta(days=2)).isoformat(),
                "end": now.isoformat(),
                "hours": 48,
                "points": 4,
            }
        ]
        decision = evaluate(state, quota, "drain", now)
        self.assertEqual("RUN", decision["verdict"])
        self.assertGreater(decision["available"], decision["estimated_cost"])

    def test_begin_complete_learns_job_cost(self):
        now = datetime(2026, 8, 11, tzinfo=UTC)
        reset = now + timedelta(days=5)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            started = begin(path, "drain", now, Quota(20.0, reset))
            result = complete(path, started["run_id"], now + timedelta(hours=1), Quota(26.0, reset))
            self.assertEqual(6.0, result["measured_cost"])

    def test_stale_active_run_is_conservatively_observed(self):
        now = datetime(2026, 8, 11, tzinfo=UTC)
        reset = now + timedelta(days=5)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            started = begin(path, "drain", now, Quota(20.0, reset))
            self.assertTrue(started["run_id"])
            begin(path, "image", now + timedelta(hours=2), Quota(25.0, reset))
            state = __import__("json").loads(path.read_text())
            self.assertEqual(5.0, state["external_intervals"][0]["points"])
            self.assertTrue(state["external_intervals"][0]["uncertain"])

    def test_weekly_rollover_preserves_learning(self):
        now = datetime(2026, 8, 11, tzinfo=UTC)
        state = reset_state(now + timedelta(hours=1), now - timedelta(days=4))
        state["external_intervals"] = [
            {
                "start": (now - timedelta(days=1)).isoformat(),
                "end": now.isoformat(),
                "hours": 24,
                "points": 3,
            }
        ]
        state["cost_estimates"]["drain"] = 5.5
        rolled = rollover_state(state, now + timedelta(days=7), now)
        self.assertEqual(state["observed_since"], rolled["observed_since"])
        self.assertEqual(3.0, rolled["external_intervals"][0]["points"])
        self.assertEqual(5.5, rolled["cost_estimates"]["drain"])


if __name__ == "__main__":
    unittest.main()
