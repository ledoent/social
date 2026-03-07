# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

from odoo import fields

from odoo.addons.social_media_base.tests.test_social_common import (
    TestSocialMediaBaseCommon,
)


class TestSocialMediaCalendar(TestSocialMediaBaseCommon):

    # ------------------------------------------------------------------
    # color computation
    # ------------------------------------------------------------------

    def test_compute_color(self):
        mapping = {
            "planned": 2,
            "publishing": 6,
            "published": 10,
            "cancelled": 0,
            "draft": 4,
        }
        for state, expected_color in mapping.items():
            post = self.SocialPost.create({"message": f"Post {state}", "state": state})
            self.assertEqual(
                post.color,
                expected_color,
                f"State {state!r} should map to color {expected_color}",
            )

    # ------------------------------------------------------------------
    # date_calendar — priority: published_date > send_post_date > create_date
    # ------------------------------------------------------------------

    def test_date_calendar_uses_published_date(self):
        """published_date takes precedence over send_post_date and create_date."""
        published = fields.Datetime.now() - timedelta(days=2)
        scheduled = fields.Datetime.now() + timedelta(days=1)
        post = self.SocialPost.create(
            {
                "message": "Published post",
                "published_date": published,
                "send_post_date": scheduled,
            }
        )
        self.assertEqual(post.date_calendar, published.date())

    def test_date_calendar_falls_back_to_send_post_date(self):
        """send_post_date is used when published_date is not set."""
        scheduled = fields.Datetime.now() + timedelta(days=3)
        post = self.SocialPost.create(
            {
                "message": "Scheduled post",
                "send_post_date": scheduled,
            }
        )
        self.assertEqual(post.date_calendar, scheduled.date())

    def test_date_calendar_falls_back_to_create_date(self):
        """create_date is used when neither published_date nor send_post_date is set."""
        post = self.SocialPost.create({"message": "Draft post"})
        self.assertEqual(post.date_calendar, post.create_date.date())

    def test_date_calendar_recomputes_on_publish(self):
        """date_calendar updates when published_date is written after creation."""
        post = self.SocialPost.create({"message": "Will be published"})
        original_date = post.date_calendar
        published = fields.Datetime.now() - timedelta(days=1)
        post.write({"published_date": published})
        self.assertEqual(post.date_calendar, published.date())
        self.assertNotEqual(post.date_calendar, original_date)

    # ------------------------------------------------------------------
    # action_open_post click-through
    # ------------------------------------------------------------------

    def test_action_open_post_returns_form_action(self):
        """action_open_post() returns a valid act_window action for the form view."""
        post = self.SocialPost.create({"message": "Click-through test"})
        action = post.action_open_post()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "social.post")
        self.assertEqual(action["res_id"], post.id)
        self.assertEqual(action["view_mode"], "form")
        self.assertEqual(action["target"], "current")

    def test_action_open_post_requires_single_record(self):
        """action_open_post() raises on multi-record set (ensure_one guard)."""
        p1 = self.SocialPost.create({"message": "Post 1"})
        p2 = self.SocialPost.create({"message": "Post 2"})
        with self.assertRaises(Exception):
            (p1 | p2).action_open_post()
