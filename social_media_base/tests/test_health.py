# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta
from unittest.mock import patch

from odoo import fields

from .test_social_common import PATCH_ACCOUNT, TestSocialMediaBaseCommon


class TestConnectionHealth(TestSocialMediaBaseCommon):
    """Tier 2 PR A — connection health computes, cron, and degradation hook."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.SocialMedia.create(
            {
                "name": "Facebook",
            }
        )

    # ── Computes ──────────────────────────────────────────────────────
    def test_severity_compute_maps_states(self):
        a = self.social_account_id
        for status, expected in [
            ("healthy", 0),
            ("never_connected", 0),
            ("warning", 1),
            ("rate_limited", 1),
            ("expired", 2),
            ("disconnected", 2),
        ]:
            a.health_status = status
            self.assertEqual(a.health_severity, expected, f"severity for {status}")

    def test_follower_delta_7d_from_history(self):
        a = self.social_account_id
        today = fields.Date.context_today(a)
        a.write(
            {
                "follower_count": 1247,
                "follower_history": [
                    {"d": (today - timedelta(days=30)).isoformat(), "n": 1100},
                    {"d": (today - timedelta(days=7)).isoformat(), "n": 1244},
                    {"d": (today - timedelta(days=1)).isoformat(), "n": 1246},
                ],
            }
        )
        a.invalidate_recordset()
        self.assertEqual(a.follower_count_delta_7d, 3)
        self.assertEqual(a.follower_count_delta_30d, 147)

    def test_follower_delta_falls_back_to_closest_older(self):
        # Sparse history (no entry exactly at 7 days ago) — should pick
        # the most recent snapshot at or before the target date.
        a = self.social_account_id
        today = fields.Date.context_today(a)
        a.write(
            {
                "follower_count": 500,
                "follower_history": [
                    {"d": (today - timedelta(days=14)).isoformat(), "n": 400},
                    {"d": (today - timedelta(days=2)).isoformat(), "n": 490},
                ],
            }
        )
        a.invalidate_recordset()
        # 7d window: closest at-or-before is the 14d-ago entry (400)
        self.assertEqual(a.follower_count_delta_7d, 100)

    def test_follower_delta_zero_when_no_history(self):
        a = self.social_account_id
        a.write({"follower_count": 1000, "follower_history": []})
        a.invalidate_recordset()
        self.assertEqual(a.follower_count_delta_7d, 0)
        self.assertEqual(a.follower_count_delta_30d, 0)

    def test_last_post_compute_picks_latest_published(self):
        a = self.social_account_id
        older = self._create_post_for_account(a, "older")
        newer = self._create_post_for_account(a, "newer")
        older.write(
            {
                "state": "published",
                "published_date": fields.Datetime.now() - timedelta(days=5),
            }
        )
        newer.write(
            {
                "state": "published",
                "published_date": fields.Datetime.now() - timedelta(days=1),
            }
        )
        a.invalidate_recordset()
        self.assertEqual(a.last_post_id, newer)
        self.assertEqual(a.last_post_at, newer.published_date)

    def test_last_post_compute_ignores_drafts(self):
        a = self.social_account_id
        published = self._create_post_for_account(a, "published")
        draft = self._create_post_for_account(a, "draft")
        published.write(
            {
                "state": "published",
                "published_date": fields.Datetime.now() - timedelta(days=2),
            }
        )
        # draft stays in default 'draft' state
        a.invalidate_recordset()
        self.assertEqual(a.last_post_id, published)
        self.assertNotEqual(a.last_post_id, draft)

    # ── Cron orchestrator ────────────────────────────────────────────
    def test_cron_calls_refresh_for_each_active_account(self):
        b = self.SocialAccount.create(
            {"name": "Second", "media_id": self.social_media_id.id}
        )
        with patch(
            PATCH_ACCOUNT.format("_refresh_account_health"), autospec=True
        ) as mocked:
            self.SocialAccount._cron_refresh_all_accounts()
        # Called at least once per active account
        called_ids = {call.args[0].id for call in mocked.call_args_list}
        self.assertIn(self.social_account_id.id, called_ids)
        self.assertIn(b.id, called_ids)

    def test_cron_appends_snapshot_to_history(self):
        a = self.social_account_id
        today = fields.Date.context_today(a)
        a.write(
            {
                "follower_count": 1234,
                "follower_history": [
                    {"d": (today - timedelta(days=2)).isoformat(), "n": 1200},
                ],
            }
        )
        with patch(PATCH_ACCOUNT.format("_refresh_account_health"), autospec=True):
            self.SocialAccount._cron_refresh_all_accounts()
        a.invalidate_recordset()
        history = a.follower_history or []
        self.assertEqual(len(history), 2, "cron should append today's snapshot")
        self.assertEqual(history[-1]["d"], today.isoformat())
        self.assertEqual(history[-1]["n"], 1234)

    def test_cron_overwrites_same_day_snapshot(self):
        a = self.social_account_id
        today = fields.Date.context_today(a)
        a.write(
            {
                "follower_count": 9999,
                "follower_history": [{"d": today.isoformat(), "n": 5000}],
            }
        )
        with patch(PATCH_ACCOUNT.format("_refresh_account_health"), autospec=True):
            self.SocialAccount._cron_refresh_all_accounts()
        a.invalidate_recordset()
        history = a.follower_history or []
        self.assertEqual(len(history), 1, "same-day call must not duplicate")
        self.assertEqual(history[0]["n"], 9999, "same-day call must overwrite")

    def test_cron_caps_history_length(self):
        from ..models.social_account import _FOLLOWER_HISTORY_MAX_ENTRIES

        a = self.social_account_id
        today = fields.Date.context_today(a)
        # Seed history past the cap with one entry per day
        a.follower_history = [
            {"d": (today - timedelta(days=i + 1)).isoformat(), "n": 100 + i}
            for i in range(_FOLLOWER_HISTORY_MAX_ENTRIES + 5)
        ][::-1]
        a.follower_count = 999
        with patch(PATCH_ACCOUNT.format("_refresh_account_health"), autospec=True):
            self.SocialAccount._cron_refresh_all_accounts()
        a.invalidate_recordset()
        self.assertEqual(
            len(a.follower_history),
            _FOLLOWER_HISTORY_MAX_ENTRIES,
            "history must be trimmed at the cap after appending",
        )
        self.assertEqual(a.follower_history[-1]["n"], 999)

    def test_cron_swallows_per_account_errors(self):
        b = self.SocialAccount.create(
            {"name": "Second", "media_id": self.social_media_id.id}
        )

        def selective_raise(self_arg):
            if self_arg.id == self.social_account_id.id:
                raise RuntimeError("boom")
            self_arg.write(
                {
                    "health_status": "healthy",
                    "health_message": "ok",
                    "health_evaluated_at": fields.Datetime.now(),
                }
            )

        with patch(
            PATCH_ACCOUNT.format("_refresh_account_health"),
            autospec=True,
            side_effect=selective_raise,
        ):
            self.SocialAccount._cron_refresh_all_accounts()
        b.invalidate_recordset()
        self.assertEqual(
            b.health_status, "healthy", "other accounts must still process"
        )

    def test_cron_marks_disconnected_on_unhandled_exception(self):
        a = self.social_account_id
        with patch(
            PATCH_ACCOUNT.format("_refresh_account_health"),
            autospec=True,
            side_effect=RuntimeError("api down"),
        ):
            self.SocialAccount._cron_refresh_all_accounts()
        a.invalidate_recordset()
        self.assertEqual(a.health_status, "disconnected")
        self.assertIn("api down", a.health_message or "")
        self.assertTrue(a.health_evaluated_at)

    # ── Degradation hook ─────────────────────────────────────────────
    def test_post_health_warning_fires_on_degradation(self):
        a = self.social_account_id
        a.health_status = "healthy"

        def degrade(self_arg):
            self_arg.write(
                {
                    "health_status": "warning",
                    "health_message": "Expires in 3d",
                    "health_evaluated_at": fields.Datetime.now(),
                }
            )

        with patch(
            PATCH_ACCOUNT.format("_refresh_account_health"),
            autospec=True,
            side_effect=degrade,
        ):
            self.SocialAccount._cron_refresh_all_accounts()
        activities = self.env["mail.activity"].search(
            [
                ("res_model", "=", "social.account"),
                ("res_id", "=", a.id),
            ]
        )
        self.assertTrue(
            activities,
            "degradation to warning should schedule a reconnect activity",
        )

    def test_post_health_warning_idempotent_when_unchanged(self):
        a = self.social_account_id
        a.health_status = "warning"
        a.health_message = "Expires in 3d"
        before = self.env["mail.activity"].search_count(
            [
                ("res_model", "=", "social.account"),
                ("res_id", "=", a.id),
            ]
        )

        def stay_warning(self_arg):
            self_arg.write(
                {
                    "health_status": "warning",
                    "health_message": "Expires in 3d",
                    "health_evaluated_at": fields.Datetime.now(),
                }
            )

        with patch(
            PATCH_ACCOUNT.format("_refresh_account_health"),
            autospec=True,
            side_effect=stay_warning,
        ):
            self.SocialAccount._cron_refresh_all_accounts()
        after = self.env["mail.activity"].search_count(
            [
                ("res_model", "=", "social.account"),
                ("res_id", "=", a.id),
            ]
        )
        self.assertEqual(
            before,
            after,
            "no transition → no new activity (warning → warning is steady)",
        )

    # ── Base contract ────────────────────────────────────────────────
    def test_base_refresh_marks_never_connected(self):
        a = self.social_account_id
        a._refresh_account_health()
        self.assertEqual(a.health_status, "never_connected")
        self.assertTrue(a.health_evaluated_at)

    def test_test_post_methods_raise_in_base(self):
        a = self.social_account_id
        with self.assertRaises(NotImplementedError):
            a._test_post_and_delete()
        with self.assertRaises(NotImplementedError):
            a._delete_test_post("any-id")

    # ── Helpers ──────────────────────────────────────────────────────
    def _create_post_for_account(self, account, message):
        post = self.SocialPost.create(
            {
                "message": message,
                "account_ids": [(6, 0, [account.id])],
            }
        )
        # Some posts auto-create a social.post.account row via constraint;
        # ensure the link exists for the compute path.
        if not self.SocialPostAccount.search_count(
            [("post_id", "=", post.id), ("account_id", "=", account.id)]
        ):
            self.SocialPostAccount.create(
                {
                    "post_id": post.id,
                    "account_id": account.id,
                    "message": message,
                }
            )
        return post
