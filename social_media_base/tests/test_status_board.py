# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from .test_social_common import TestSocialMediaBaseCommon


class TestStatusBoardView(TestSocialMediaBaseCommon):
    """Tier 2 PR A — smoke tests for the connection-health kanban view.

    These don't render pixels; they verify the view loads and references
    only fields that actually exist on social.account. The real visual QA
    happens on staging via the Odoo client.
    """

    def test_kanban_view_arch_loads(self):
        view = self.env.ref("social_media_base.social_account_kanban_view")
        self.assertEqual(view.model, "social.account")
        # _check_xml renders the arch against the model — any unknown
        # field, malformed t-att, or broken xpath blows up here.
        view._check_xml()

    def test_kanban_get_view_with_seeded_account(self):
        # social_account_id is created in setUpClass with no platform
        # override; this exercises the "never_connected" branch of the
        # pill selector so the kanban renders for fresh installs.
        result = self.SocialAccount.with_context(studio=False).get_view(
            view_type="kanban"
        )
        self.assertEqual(result["type"], "kanban")
        self.assertIn("o-social-status-card", result["arch"])
        self.assertIn("o-social-status-pill", result["arch"])

    def test_search_view_filters_present(self):
        view = self.env.ref("social_media_base.social_account_search_view")
        self.assertEqual(view.model, "social.account")
        arch = view.arch
        self.assertIn("filter_degraded", arch)
        self.assertIn("filter_healthy", arch)
        self.assertIn("group_status", arch)
