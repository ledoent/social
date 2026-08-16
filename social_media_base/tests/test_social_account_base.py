# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
from datetime import timedelta
from unittest.mock import patch

import psycopg2
from dateutil.relativedelta import relativedelta
from freezegun import freeze_time
from psycopg2 import errorcodes

from odoo import _, fields
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests.common import tagged
from odoo.tools import mute_logger

from odoo.addons.social_media_base.exceptions import SocialCredentialsError
from odoo.addons.social_media_base.hooks import remove_social_media
from odoo.addons.social_media_base.tests.test_social_common import (
    TestSocialMediaBaseCommon,
)

from .test_social_common import PATCH_ACCOUNT, PATCH_WIZARD_ACCOUNT

LOGGER_ACCOUNT = "odoo.addons.social_media_base.models.social_account"


class TestSocialAccountBase(TestSocialMediaBaseCommon):
    def test_compute_display_name(self):
        self.social_account_id._compute_display_name()
        self.assertEqual(self.social_account_id.display_name, "Linkedin")

    @patch(PATCH_ACCOUNT.format("_get_chart_account_statistics"))
    def test_get_chart_account_statistics(self, mock_get_chart_account_statistics):
        self.social_account_id.get_chart_account_statistics()
        mock_get_chart_account_statistics.assert_called_once()

    def test_chart_granularities_offers_every_unit(self):
        self.assertEqual(
            self.social_account_id._get_chart_granularities(),
            ["DAY", "WEEK", "MONTH"],
            msg="The base module is agnostic: narrowing the list down is up "
            "to the connector of each social media.",
        )

    @patch(PATCH_ACCOUNT.format("_get_chart_account_statistics"))
    def test_chart_range_shorter_than_the_granularity(self, mock_statistics):
        """A range that does not cover a whole unit never triggers a request.

        The social media answer an error of their own, so it is refused
        with a message the user can act on.
        """
        for granularity, start, end in [
            ("DAY", "2025-01-01", "2025-01-01"),
            ("WEEK", "2025-01-01", "2025-01-05"),
            ("MONTH", "2025-01-01", "2025-01-31"),
        ]:
            with self.subTest(granularity=granularity):
                with self.assertRaises(UserError):
                    self.social_account_id.get_chart_account_statistics(
                        start, end, granularity
                    )
        mock_statistics.assert_not_called()

    @patch(PATCH_ACCOUNT.format("_get_chart_account_statistics"))
    def test_chart_range_covering_the_granularity(self, mock_statistics):
        for granularity, start, end in [
            ("DAY", "2025-01-01", "2025-01-02"),
            ("WEEK", "2025-01-01", "2025-01-08"),
            ("MONTH", "2025-01-01", "2025-02-01"),
        ]:
            with self.subTest(granularity=granularity):
                self.social_account_id.get_chart_account_statistics(
                    start, end, granularity
                )
        self.assertEqual(mock_statistics.call_count, 3)

    @patch(PATCH_ACCOUNT.format("_get_chart_account_statistics"))
    def test_chart_range_is_not_checked_without_dates(self, mock_statistics):
        """The social medias answer their lifetime statistics without a range."""
        self.social_account_id.get_chart_account_statistics(granularity="MONTH")
        mock_statistics.assert_called_once()

    def test_get_default_filter_date_keeps_the_dates_it_receives(self):
        start, end = self.social_account_id._get_default_filter_date(
            self.start_datetime, self.end_datetime
        )
        self.assertEqual(start, self.start_datetime)
        self.assertEqual(end, self.end_datetime)

    @freeze_time("2025-03-15 10:00:00")
    def test_get_default_filter_date_defaults_to_the_last_month(self):
        start, end = self.social_account_id._get_default_filter_date(None, None)
        self.assertEqual(end, fields.Datetime.now())
        self.assertEqual(start, fields.Datetime.now() - relativedelta(months=1))
        start, __ = self.social_account_id._get_default_filter_date(
            None, None, months=3
        )
        self.assertEqual(start, fields.Datetime.now() - relativedelta(months=3))

    def test_get_default_filter_date_as_timestamps(self):
        """The social media that group by timestamp get milliseconds."""
        start, end = self.social_account_id._get_default_filter_date(
            self.start_datetime, self.end_datetime, time_date=True
        )
        self.assertEqual(start, self.start_timestamp)
        self.assertEqual(end, self.end_timestamp)

    def _map_chart_statistics(self, statistics_by_period, totals=None):
        field = self.social_media_id._fields["media_type"]
        with patch.object(field, "selection", new=[("other_social", "Other social")]):
            self.social_media_id.write({"media_type": "other_social"})
            return self.social_account_id._map_chart_statistics(
                statistics_by_period,
                start_date="2025-01-01",
                end_date="2025-01-02",
                freq="D",
                totals=totals,
            )

    def test_map_chart_statistics(self):
        """Every series is read period by period, never by position."""
        data_chart = self._map_chart_statistics(
            {
                "2025-01-01": (1, 2, 3, 4, 5.0, 6),
                "2025-01-02": (10, 20, 30, 40, 50.0, 60),
            }
        )
        self.assertEqual(len(data_chart), 1)
        chart = data_chart[0]
        self.assertEqual(chart["id"], self.social_account_id.id)
        self.assertEqual(chart["name"], "[OTHER_SOCIAL] Linkedin")
        self.assertEqual(chart["granularities"], ["DAY", "WEEK", "MONTH"])
        self.assertEqual(chart["labels"], ["01/01/2025", "02/01/2025"])
        self.assertEqual(chart["impressionCount"], 66)
        self.assertEqual(chart["commentCount"], 33)
        self.assertEqual(
            chart["reactionCount"],
            66,
            "A reaction is a like or a share",
        )
        self.assertEqual(
            [dataset["label"] for dataset in chart["datasets"]],
            ["Clicks", "Shares", "Likes", "Comments", "Impressions", "Engagement"],
        )
        self.assertEqual(
            [dataset["data"] for dataset in chart["datasets"]],
            [
                [1, 10],
                [4, 40],
                [2, 20],
                [3, 30],
                [6, 60],
                [5.0, 50.0],
            ],
        )

    def test_map_chart_statistics_fills_the_missing_periods(self):
        """A period the social media reported nothing for is a zero.

        The social media does not answer a bucket for the day in progress, so
        a missing period must not shift the rest of the series.
        """
        data_chart = self._map_chart_statistics({"2025-01-02": (1, 2, 3, 4, 5.0, 6)})
        chart = data_chart[0]
        self.assertEqual(chart["labels"], ["01/01/2025", "02/01/2025"])
        for dataset in chart["datasets"]:
            self.assertEqual(
                len(dataset["data"]),
                len(chart["labels"]),
                msg="A series always has one value per label.",
            )
        impressions = next(
            dataset
            for dataset in chart["datasets"]
            if dataset["label"] == "Impressions"
        )
        self.assertEqual(impressions["data"], [0, 6])

    def test_map_chart_statistics_totals(self):
        """The figures of the account travel next to the ones of the period."""
        data_chart = self._map_chart_statistics(
            {"2025-01-01": (1, 2, 3, 4, 5.0, 6)},
            totals={
                "impressionCount": 280,
                "commentCount": 3,
                "reactionCount": 8,
            },
        )
        chart = data_chart[0]
        self.assertEqual(chart["impressionCount"], 6)
        self.assertEqual(chart["impressionCountTotal"], 280)
        self.assertEqual(chart["commentCountTotal"], 3)
        self.assertEqual(chart["reactionCountTotal"], 8)

    def test_map_chart_statistics_without_totals(self):
        """Filtering does not read them again, so they travel empty."""
        chart = self._map_chart_statistics({"2025-01-01": (1, 2, 3, 4, 5.0, 6)})[0]
        self.assertIsNone(chart["impressionCountTotal"])
        self.assertIsNone(chart["commentCountTotal"])
        self.assertIsNone(chart["reactionCountTotal"])

    def test_map_chart_statistics_without_statistics(self):
        self.assertEqual(self._map_chart_statistics({}), [])

    def test_map_chart_statistics_without_media_type(self):
        """The base module has no media: nothing is charted."""
        self.assertEqual(
            self.social_account_id._map_chart_statistics(
                {"2025-01-01": (1, 2, 3, 4, 5.0, 6)},
                start_date="2025-01-01",
                end_date="2025-01-02",
                freq="D",
            ),
            [],
        )

    def test_archive_account(self):
        self.social_account_id.action_archive_account()
        self.assertFalse(self.social_post_id.active)
        self.assertFalse(self.social_post_account_id.active)
        self.assertFalse(self.social_account_id.active)

    def test_find_account_to_associate(self):
        media_type = self.social_account_id.media_type
        self.social_account_id.write(
            {"remote_ref": "urn:li:organization:1", "username": "the_account"}
        )
        found = self.SocialAccount._find_account_to_associate(
            media_type, "urn:li:organization:1"
        )
        self.assertEqual(found, self.social_account_id)
        self.assertFalse(
            self.SocialAccount._find_account_to_associate(
                media_type, "urn:li:organization:2"
            ),
            "An account of another organization must never be reused",
        )
        self.assertFalse(
            self.SocialAccount._find_account_to_associate(
                media_type, "urn:li:organization:2", username="the_account"
            ),
            "The user name is not a fallback for accounts that do have a "
            "remote reference",
        )

    def test_find_account_to_associate_without_remote_ref(self):
        media_type = self.social_account_id.media_type
        self.social_account_id.write({"remote_ref": False, "username": "legacy"})
        found = self.SocialAccount._find_account_to_associate(
            media_type, "urn:li:organization:1", username="legacy"
        )
        self.assertEqual(
            found,
            self.social_account_id,
            "Accounts stored before the remote reference existed are still "
            "relinked by their user name",
        )

    def test_check_can_associate_other_company(self):
        other_company = self.env["res.company"].create({"name": "Another company"})
        self.env.user.write({"company_ids": [(3, other_company.id)]})
        self.social_account_id.write({"company_id": other_company.id})
        with self.assertRaises(AccessError):
            self.social_account_id._check_can_associate()

    def test_purge_account(self):
        post = self.social_post_id
        post_account = self.social_post_account_id
        self.social_account_id.action_archive_account()
        action = self.social_account_id.action_purge_account()
        self.assertEqual(action.get("res_model"), "social.account")
        self.assertEqual(action.get("target"), "main")
        self.assertFalse(self.social_account_id.exists())
        self.assertFalse(post_account.exists())
        self.assertFalse(post.exists())

    def test_purge_account_keeps_shared_post(self):
        other_account = self.SocialAccount.create(
            {"name": "Other account", "media_id": self.social_media_id.id}
        )
        shared_post = self.SocialPost.create(
            {
                "message": "Shared message",
                "account_ids": [(6, 0, [self.social_account_id.id, other_account.id])],
            }
        )
        self.social_account_id.action_archive_account()
        self.social_account_id.action_purge_account()
        self.assertTrue(shared_post.exists())
        self.assertEqual(shared_post.account_ids, other_account)

    def test_action_full_resync(self):
        """The account form button delegates on the connector hook."""
        with patch(PATCH_ACCOUNT.format("_full_resync"), autospec=True) as mock:
            self.social_account_id.action_full_resync()
            mock.assert_called_once()

    def test_action_full_resync_needs_a_single_account(self):
        other_account = self.SocialAccount.create(
            {"name": "Other account", "media_id": self.social_media_id.id}
        )
        with self.assertRaises(ValueError):
            (self.social_account_id | other_account).action_full_resync()

    def test_remove_social_media(self):
        field = self.social_media_id._fields["media_type"]
        with patch.object(field, "selection", new=[("other_social", "Other social")]):
            self.social_media_id.write({"media_type": "other_social"})
            self.social_account_id.write(
                {
                    "remote_ref": "remote-account-1",
                    "access_token": "token",
                    "refresh_access_token": "refresh-token",
                }
            )
            self.SocialAccount._remove_social_media("other_social")
        account_sudo = self.social_account_id.sudo()
        self.assertFalse(account_sudo.access_token)
        self.assertFalse(account_sudo.refresh_access_token)
        self.assertFalse(self.social_account_id.active)
        self.assertFalse(self.social_post_account_id.active)
        self.assertEqual(self.social_account_id.remote_ref, "remote-account-1")

    def test_remove_social_media_other_media_untouched(self):
        field = self.social_media_id._fields["media_type"]
        with patch.object(field, "selection", new=[("other_social", "Other social")]):
            self.social_media_id.write({"media_type": "other_social"})
            self.social_account_id.write({"access_token": "token"})
            self.SocialAccount._remove_social_media("not_this_media")
        self.assertTrue(self.social_account_id.active)
        self.assertEqual(self.social_account_id.sudo().access_token, "token")

    def test_archive_account_cascade(self):
        self.social_account_id.write({"active": False})
        self.assertFalse(self.social_account_id.active)
        self.assertFalse(self.social_post_id.active)
        self.assertFalse(self.social_post_account_id.active)
        self.social_account_id.write({"active": True})
        self.assertTrue(self.social_account_id.active)
        self.assertTrue(self.social_post_id.active)
        self.assertTrue(self.social_post_account_id.active)

    def test_archive_cascade_with_several_accounts(self):
        """A post is archived once no active account is left, not before."""
        other_account = self.SocialAccount.create(
            {"name": "Other Linkedin", "media_id": self.social_media_id.id}
        )
        self.social_post_id.write({"account_ids": [Command.link(other_account.id)]})
        self.social_account_id.write({"active": False})
        self.assertTrue(self.social_post_id.active)
        self.assertFalse(self.social_post_account_id.active)
        other_account.write({"active": False})
        self.assertFalse(self.social_post_id.active)

    def test_archive_cascade_with_the_accounts_archived_at_once(self):
        other_account = self.SocialAccount.create(
            {"name": "Other Linkedin", "media_id": self.social_media_id.id}
        )
        self.social_post_id.write({"account_ids": [Command.link(other_account.id)]})
        (self.social_account_id + other_account).write({"active": False})
        self.assertFalse(self.social_post_id.active)

    def test_unarchive_sends_the_overdue_scheduled_posts_to_draft(self):
        """Reactivating must not hand an already due post to the cron."""
        post = self.social_post_id
        post.write({"send_post": "schedule"})
        post.send_post_date = fields.Datetime.now() + timedelta(minutes=5)
        self.assertEqual(post.state, "planned")
        self.social_account_id.write({"active": False})
        with freeze_time(fields.Datetime.now() + timedelta(minutes=10)):
            self.social_account_id.write({"active": True})
        self.assertTrue(post.active)
        self.assertEqual(post.state, "draft")
        self.assertTrue(
            post.message_ids.filtered(
                lambda message: "set back to draft" in (message.body or "")
            )
        )

    def test_unarchive_keeps_the_posts_scheduled_in_the_future(self):
        post = self.social_post_id
        post.write({"send_post": "schedule"})
        post.send_post_date = fields.Datetime.now() + timedelta(hours=2)
        self.social_account_id.write({"active": False})
        self.social_account_id.write({"active": True})
        self.assertEqual(post.state, "planned")

    def test_archive_post_cascades_to_its_publications(self):
        self.social_post_id.write({"active": False})
        self.assertFalse(self.social_post_account_id.active)
        self.social_post_id.write({"active": True})
        self.assertTrue(self.social_post_account_id.active)

    def test_unarchive_post_keeps_the_lines_of_an_archived_account(self):
        """The account is what hides those lines, not the post."""
        other_account = self.SocialAccount.create(
            {"name": "Other Linkedin", "media_id": self.social_media_id.id}
        )
        other_line = self.SocialPostAccount.create(
            {
                "post_id": self.social_post_id.id,
                "account_id": other_account.id,
                "message": "Test message",
            }
        )
        self.social_post_id.write({"account_ids": [Command.link(other_account.id)]})
        other_account.write({"active": False})
        self.assertFalse(other_line.active)
        self.social_post_id.write({"active": False})
        self.social_post_id.write({"active": True})
        self.assertTrue(self.social_post_account_id.active)
        self.assertFalse(other_line.active)

    def test_action_unarchive_account(self):
        self.social_account_id.action_archive_account()
        self.assertFalse(self.social_account_id.active)
        self.social_account_id.action_unarchive_account()
        self.assertTrue(self.social_account_id.active)
        self.assertTrue(self.social_post_id.active)
        self.assertTrue(self.social_post_account_id.active)

    def test_compute_account_url(self):
        fake_fields = [
            (
                "other_social",
                "https://www.failed.com/company/id1234account/admin",
            )
        ]
        field = self.social_media_id._fields["media_type"]
        with patch.object(
            type(self.social_account_id),
            "_fields_account_url",
            autospec=True,
            return_value=fake_fields,
        ), patch.object(
            field,
            "selection",
            new=[("other_social", "Other social")],
        ):
            self.social_media_id.write({"media_type": "other_social"})
            self.assertEqual(
                self.social_account_id.account_url,
                "https://www.failed.com/company/id1234account/admin",
            )

    def test_compute_account_url_failed(self):
        fake_failed_fields = [
            ("other_social", "https://www.failed.com/company/2333/admin")
        ]
        with patch.object(
            type(self.social_account_id),
            "_fields_account_url",
            autospec=True,
            return_value=fake_failed_fields,
        ):
            self.assertFalse(self.social_account_id.account_url)

    def test_compute_account_url_failed_continue(self):
        fake_failed_continue = ["Y"]
        with patch.object(
            type(self.social_account_id),
            "_fields_account_url",
            autospec=True,
            return_value=fake_failed_continue,
        ):
            self.assertFalse(self.social_account_id.account_url)

    def test_filter_statistics(self):
        fake_statistics = {"stats_fake": (5, 10, 15, 20, 25, 30)}
        statistics = self.social_account_id._filter_statistics(fake_statistics)
        self.assertEqual(statistics["click_count"], fake_statistics["stats_fake"][0])
        self.assertEqual(statistics["like_count"], fake_statistics["stats_fake"][1])
        self.assertEqual(statistics["comment_count"], fake_statistics["stats_fake"][2])
        self.assertEqual(statistics["share_count"], fake_statistics["stats_fake"][3])
        self.assertEqual(statistics["engagement"], fake_statistics["stats_fake"][4])
        self.assertEqual(
            statistics["impression_count"], fake_statistics["stats_fake"][5]
        )

    def test_update_posts_statistics(self):
        fake_statistics = [{"like_count": 5}]
        with patch.object(
            type(self.social_account_id),
            "_update_posts_statistics",
            autospec=True,
            return_value=fake_statistics,
        ):
            update_statistics = self.social_account_id.update_posts_statistics()
            load_update_statistics = json.loads(update_statistics)
            self.assertEqual(load_update_statistics[0]["like_count"], 5)

    def test_update_posts_statistics_clears_the_pending_initial_sync(self):
        """The manual update is the very import the cron was going to run.

        The dashboard announces a background import while the flag is set, so
        the button that does the import itself is what takes it down.
        """
        self.social_account_id.pending_initial_sync = True
        with patch.object(
            type(self.social_account_id),
            "_update_posts_statistics",
            autospec=True,
            return_value=[],
        ):
            self.social_account_id.update_posts_statistics()
        self.assertFalse(self.social_account_id.pending_initial_sync)

    def test_full_resync_falls_back_to_the_ordinary_refresh(self):
        """A media with no notion of a whole feed has nothing extra to do."""
        with patch.object(
            type(self.social_account_id),
            "update_posts_statistics",
            autospec=True,
            return_value="[]",
        ) as patch_update:
            self.social_account_id._full_resync()
        patch_update.assert_called_once()

    def test_full_resync_on_no_accounts_does_nothing(self):
        """No accounts is not every account.

        A connector delegates here the accounts it does not handle, and the
        ordinary refresh takes an empty recordset as every account: falling
        back on it would refresh a second time the very accounts the
        connector already reconciled.
        """
        with patch.object(
            type(self.social_account_id),
            "update_posts_statistics",
            autospec=True,
            return_value="[]",
        ) as patch_update:
            self.SocialAccount.browse()._full_resync()
        patch_update.assert_not_called()

    def test_run_full_resync_leaves_out_a_pending_initial_sync(self):
        """The initial sync is this very pass: the two must not fight."""
        self.social_account_id.pending_initial_sync = True
        with patch.object(
            type(self.social_account_id), "_full_resync", autospec=True
        ) as patch_resync:
            self.SocialAccount._run_full_resync()
        self.assertNotIn(
            self.social_account_id,
            [call[0][0] for call in patch_resync.call_args_list],
        )

    @mute_logger("odoo.addons.social_media_base.models.social_account")
    def test_run_full_resync_isolates_each_account(self):
        """The account that fails must not stop the ones still to come."""
        failing = self.social_account_id
        working = failing.copy({"name": "Other", "username": "other-account"})

        def resync(account):
            if account.id == failing.id:
                raise UserError(_("The social media refused the feed"))

        with patch.object(
            type(failing), "_full_resync", autospec=True, side_effect=resync
        ) as patch_resync:
            self.SocialAccount._run_full_resync()
        resynced = [call[0][0] for call in patch_resync.call_args_list]
        self.assertIn(working, resynced)

    @mute_logger("odoo.addons.social_media_base.models.social_account")
    def test_run_full_resync_reraises_a_concurrency_error(self):
        """A cron gets no retry of its own, so Odoo has to keep seeing it."""

        class ConcurrencyError(psycopg2.OperationalError):
            pgcode = errorcodes.SERIALIZATION_FAILURE

        with patch.object(
            type(self.social_account_id),
            "_full_resync",
            autospec=True,
            side_effect=ConcurrencyError("serialization conflict"),
        ):
            with self.assertRaises(psycopg2.OperationalError):
                self.SocialAccount._run_full_resync()

    def test_full_resync_cron_runs_weekly(self):
        """Reading every publication is the expensive pass, so it runs seldom."""
        cron = self.env.ref("social_media_base.full_resync_account_job")
        self.assertTrue(cron.active)
        self.assertEqual(cron.interval_number, 1)
        self.assertEqual(cron.interval_type, "weeks")
        self.assertEqual(cron.code, "model._run_full_resync()")

    def test_trigger_initial_sync(self):
        CronTrigger = self.env["ir.cron.trigger"]
        cron = self.env.ref("social_media_base.initial_sync_account_job")
        before = CronTrigger.search_count([("cron_id", "=", cron.id)])
        self.social_account_id._trigger_initial_sync()
        after = CronTrigger.search_count([("cron_id", "=", cron.id)])
        self.assertEqual(after, before + 1)
        self.assertTrue(self.social_account_id.pending_initial_sync)

    def test_trigger_initial_sync_without_accounts(self):
        CronTrigger = self.env["ir.cron.trigger"]
        cron = self.env.ref("social_media_base.initial_sync_account_job")
        before = CronTrigger.search_count([("cron_id", "=", cron.id)])
        self.SocialAccount._trigger_initial_sync()
        after = CronTrigger.search_count([("cron_id", "=", cron.id)])
        self.assertEqual(after, before)

    def test_run_initial_sync(self):
        self.social_account_id.pending_initial_sync = True
        with patch(
            PATCH_ACCOUNT.format("update_posts_statistics"), autospec=True
        ) as patch_update, patch(
            PATCH_ACCOUNT.format("_notify_posts_updated"), autospec=True
        ) as patch_notify:
            self.SocialAccount._run_initial_sync()
        patch_update.assert_called_once()
        patch_notify.assert_called_once()
        self.assertFalse(self.social_account_id.pending_initial_sync)

    @mute_logger(LOGGER_ACCOUNT)
    def test_run_initial_sync_clears_the_flag_on_error(self):
        """The dashboard waits on the flag, and nobody retries the sync.

        The cron only runs once a month, so keeping the flag after a failure
        would leave the view waiting forever. The reason is left on the
        account instead, because the cron has no user connected to receive the
        notification of the connectors.
        """
        self.social_account_id.pending_initial_sync = True
        before = len(self.social_account_id.message_ids)
        with patch(
            PATCH_ACCOUNT.format("update_posts_statistics"),
            autospec=True,
            side_effect=ValueError("boom"),
        ), patch(
            PATCH_ACCOUNT.format("_notify_posts_updated"), autospec=True
        ) as patch_notify:
            self.SocialAccount._run_initial_sync()
        patch_notify.assert_called_once()
        self.assertFalse(self.social_account_id.pending_initial_sync)
        messages = self.social_account_id.message_ids
        self.assertEqual(len(messages) - before, 1)
        self.assertIn("boom", messages[0].body)
        self.assertIn(
            self.social_account_id.user_id.partner_id,
            messages[0].partner_ids,
        )

    def test_run_initial_sync_retries_an_account_that_lost_a_race(self):
        """A concurrency error is retried, not recorded as a failure.

        The write that lost the race is the whole import, and the cron only
        runs once a month: clearing the flag would tell the dashboard about
        posts that were never brought in, and the retry Odoo does on a
        concurrency error covers the web requests, not the crons.
        """

        class ConcurrencyError(psycopg2.OperationalError):
            pgcode = errorcodes.SERIALIZATION_FAILURE

        self.social_account_id.pending_initial_sync = True
        with patch(
            PATCH_ACCOUNT.format("update_posts_statistics"),
            autospec=True,
            side_effect=ConcurrencyError("serialization conflict"),
        ), patch(
            PATCH_ACCOUNT.format("_close_initial_sync"), autospec=True
        ) as patch_close, patch(
            PATCH_ACCOUNT.format("_reschedule_initial_sync"), autospec=True
        ) as patch_reschedule:
            self.SocialAccount._run_initial_sync()
        patch_close.assert_not_called()
        patch_reschedule.assert_called_once()
        self.assertEqual(
            patch_reschedule.call_args[0][0],
            self.social_account_id,
            "The account that lost the race is the one to import again",
        )

    def test_run_initial_sync_does_not_reschedule_what_it_imported(self):
        self.social_account_id.pending_initial_sync = True
        with patch(
            PATCH_ACCOUNT.format("update_posts_statistics"), autospec=True
        ), patch(PATCH_ACCOUNT.format("_notify_posts_updated"), autospec=True), patch(
            PATCH_ACCOUNT.format("_reschedule_initial_sync"), autospec=True
        ) as patch_reschedule:
            self.SocialAccount._run_initial_sync()
        self.assertFalse(patch_reschedule.call_args[0][0])

    def test_reschedule_initial_sync_asks_the_cron_for_a_later_run(self):
        CronTrigger = self.env["ir.cron.trigger"]
        cron = self.env.ref("social_media_base.initial_sync_account_job")
        before = CronTrigger.search([("cron_id", "=", cron.id)])
        with freeze_time("2025-01-01 10:00:00"):
            self.social_account_id._reschedule_initial_sync()
        trigger = CronTrigger.search([("cron_id", "=", cron.id)]) - before
        self.assertEqual(len(trigger), 1)
        self.assertEqual(
            trigger.call_at,
            fields.Datetime.to_datetime("2025-01-01 10:05:00"),
            "An account is retried once the update that took it is over",
        )

    def test_reschedule_initial_sync_without_accounts(self):
        CronTrigger = self.env["ir.cron.trigger"]
        cron = self.env.ref("social_media_base.initial_sync_account_job")
        before = CronTrigger.search_count([("cron_id", "=", cron.id)])
        self.SocialAccount._reschedule_initial_sync()
        after = CronTrigger.search_count([("cron_id", "=", cron.id)])
        self.assertEqual(after, before)

    def test_notify_posts_updated(self):
        Bus = self.env["bus.bus"]
        with patch.object(type(Bus), "_sendone", autospec=True) as patch_sendone:
            self.social_account_id._notify_posts_updated()
        patch_sendone.assert_called_once()
        self.assertEqual(
            patch_sendone.call_args[0][1], self.social_account_id.user_id.partner_id
        )
        self.assertEqual(patch_sendone.call_args[0][2], "social_posts_updated")
        payload = patch_sendone.call_args[0][3]
        self.assertEqual(payload["account_id"], self.social_account_id.id)
        self.assertIn(
            self.social_account_id.name,
            payload["message"],
            "A user may be responsible for several accounts, so the message "
            "has to name the one that was updated",
        )

    def test_need_update(self):
        Bus = self.env["bus.bus"]
        with patch.object(type(Bus), "_sendone", autospec=True) as patch_sendone:
            self.social_account_id._need_update()
            patch_sendone.assert_called_once()

    def test_need_update_notifies_the_responsible_user(self):
        Bus = self.env["bus.bus"]
        self.social_account_id.user_id = self.env.ref("base.user_admin")
        with patch.object(type(Bus), "_sendone", autospec=True) as patch_sendone:
            self.social_account_id._need_update()
        self.assertEqual(
            patch_sendone.call_args[0][1], self.social_account_id.user_id.partner_id
        )

    def test_need_update_without_accounts(self):
        Bus = self.env["bus.bus"]
        with patch.object(type(Bus), "_sendone", autospec=True) as patch_sendone:
            self.SocialAccount._need_update()
        self.assertEqual(patch_sendone.call_args[0][1], self.env.user.partner_id)

    def test_refresh_credentials_is_not_available_by_default(self):
        self.assertFalse(self.social_account_id._refresh_credentials())

    def test_get_social_dashboard_url(self):
        url = self.SocialAccount._get_social_dashboard_url()
        menu = self.env.ref("social_media_base.social_dashboard_menu")
        self.assertEqual(url, f"/web#menu_id={menu.id}&action={menu.action.id}")

    def test_get_social_dashboard_url_without_action(self):
        menu = self.env.ref("social_media_base.social_dashboard_menu")
        menu.action = False
        self.assertEqual(self.SocialAccount._get_social_dashboard_url(), "/web")

    def test_remove_social_media_uninstall_hook(self):
        with patch(PATCH_ACCOUNT.format("_remove_social_media"), autospec=True) as mock:
            remove_social_media(self.env, "other_social")
        mock.assert_called_once()
        self.assertEqual(mock.call_args[0][1], "other_social")

    def test_the_wizard_hooks_do_nothing_in_the_base_module(self):
        """Every connector fills them in; the base module answers nothing."""
        self.assertIsNone(self.WizardAccount._get_url_redirect())
        self.assertIsNone(self.WizardAccount._action_add_account())
        self.assertIsNone(self.WizardAccount._update_account())
        self.assertIsNone(self.WizardAccount.action_update_account())

    def test_the_validation_hook_accepts_by_default(self):
        self.assertTrue(self.WizardAccount._action_valid_add_account())

    def test_wizard_update_account_wraps_unexpected_errors(self):
        wizard = self.WizardAccount.create(
            {
                "media_id": self.social_media_id.id,
                "account_id": self.social_account_id.id,
            }
        )
        with patch(
            PATCH_WIZARD_ACCOUNT.format("_update_account"),
            autospec=True,
            side_effect=ValueError("boom"),
        ), self.assertRaises(UserError) as capture:
            wizard.action_update_account()
        self.assertIn("boom", str(capture.exception))


@tagged("post_install", "-at_install")
class TestSocialAccountBaseCredentials(TestSocialMediaBaseCommon):
    """The cron walks over the accounts of every connector of the registry."""

    def test_run_check_media_updates_renews_the_credentials(self):
        """The updates cron is also what keeps the tokens from running out."""
        with patch.object(
            type(self.social_account_id),
            "validate_access_token",
            autospec=True,
        ) as mock_validate:
            self.SocialAccount._run_check_media_updates()
        self.assertTrue(mock_validate.called)
        self.assertTrue(
            mock_validate.call_args[0][0].env.context.get("not_notify"),
            "The cron must not notify a user who asked for nothing",
        )

    def test_run_check_media_updates_leaves_out_a_pending_initial_sync(self):
        """The two crons run in parallel threads and write the same row.

        An account whose posts are being imported is answered for by that
        import, so checking it here only buys a serialization failure.
        """
        self.social_account_id.pending_initial_sync = True
        with patch.object(
            type(self.social_account_id),
            "validate_access_token",
            autospec=True,
        ) as mock_validate:
            self.SocialAccount._run_check_media_updates()
        self.assertNotIn(
            self.social_account_id.id,
            [call[0][0].id for call in mock_validate.call_args_list],
        )

    def _run_check_media_updates_failing_on_the_account(self, error):
        """Run the cron with ``validate_access_token`` raising on one account.

        :return: the other account, which must be checked all the same.
        """
        other_account = self.SocialAccount.create(
            {
                "name": "Other account",
                "media_id": self.social_media_id.id,
                "username": "other_account_check",
            }
        )
        checked = []

        def _validate(account):
            checked.append(account.id)
            if account.id == self.social_account_id.id:
                raise error

        with patch.object(
            type(self.social_account_id),
            "validate_access_token",
            autospec=True,
            side_effect=_validate,
        ):
            self.SocialAccount._run_check_media_updates()
        self.assertIn(other_account.id, checked)
        self.assertFalse(other_account.need_update)
        return other_account

    @mute_logger(LOGGER_ACCOUNT)
    def test_run_check_media_updates_flags_the_account_it_cannot_renew(self):
        self._run_check_media_updates_failing_on_the_account(
            SocialCredentialsError(_("The token was revoked"))
        )
        self.assertTrue(self.social_account_id.need_update)
        self.assertTrue(
            self.social_account_id.message_ids.filtered(
                lambda message: "The token was revoked" in (message.body or "")
            )
        )

    @mute_logger(LOGGER_ACCOUNT)
    def test_run_check_media_updates_does_not_flag_a_transient_failure(self):
        """Only the credentials the social media refused ask for a new
        authorization: nothing clears the flag on its own.
        """
        self._run_check_media_updates_failing_on_the_account(
            ValueError("The social media did not answer")
        )
        self.assertFalse(self.social_account_id.need_update)
        self.assertFalse(
            self.social_account_id.message_ids.filtered(
                lambda message: "no longer valid" in (message.body or "")
            )
        )


@tagged("post_install", "-at_install")
class TestSocialAccountBaseUsers(TestSocialMediaBaseCommon):
    """Users are created here, so every module has to be in the registry."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.User = cls.env["res.users"]
        cls.any_user = cls.User.create(
            {
                "name": "User 1",
                "login": "user_1_test",
                "email": "user1@test.example.com",
                "password": "test1234",
                "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

    def _create_social_media_user(self):
        return self.User.create(
            {
                "name": "Social user",
                "login": "social_user_test",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref(
                                "social_media_base.group_social_media_user"
                            ).id,
                        ],
                    )
                ],
            }
        )

    def _create_social_media_manager(self):
        return self.User.create(
            {
                "name": "Social manager",
                "login": "social_manager_test",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref(
                                "social_media_base.group_social_media_manager"
                            ).id,
                        ],
                    )
                ],
            }
        )

    def test_the_record_rule_hides_the_accounts_of_other_users(self):
        """A user only sees the accounts they are responsible for."""
        social_user = self._create_social_media_user()
        self.social_account_id.write({"user_id": self.env.user.id})
        own_account = self.SocialAccount.create(
            {
                "name": "Own account",
                "media_id": self.social_media_id.id,
                "user_id": social_user.id,
            }
        )
        visible = self.SocialAccount.with_user(social_user).search([])
        self.assertIn(own_account, visible)
        self.assertNotIn(self.social_account_id, visible)

    def test_the_record_rule_hides_the_posts_of_other_users(self):
        social_user = self._create_social_media_user()
        self.social_post_id.write({"user_id": self.env.user.id})
        own_post = self.SocialPost.create(
            {
                "message": "Own message",
                "account_ids": [Command.set([self.social_account_id.id])],
                "user_id": social_user.id,
            }
        )
        visible = self.SocialPost.with_user(social_user).search([])
        self.assertIn(own_post, visible)
        self.assertNotIn(self.social_post_id, visible)

    def test_the_record_rule_hides_the_publications_of_other_users(self):
        social_user = self._create_social_media_user()
        self.social_account_id.write({"user_id": self.env.user.id})
        own_account = self.SocialAccount.create(
            {
                "name": "Own account",
                "media_id": self.social_media_id.id,
                "user_id": social_user.id,
            }
        )
        own_publication = self.SocialPostAccount.create(
            {"message": "Own publication", "account_id": own_account.id}
        )
        visible = self.SocialPostAccount.with_user(social_user).search([])
        self.assertIn(own_publication, visible)
        self.assertNotIn(self.social_post_account_id, visible)

    def test_a_manager_sees_the_records_of_every_user(self):
        manager = self._create_social_media_manager()
        self.social_account_id.write({"user_id": self.env.user.id})
        self.social_post_id.write({"user_id": self.env.user.id})
        self.assertIn(
            self.social_account_id, self.SocialAccount.with_user(manager).search([])
        )
        self.assertIn(
            self.social_post_id, self.SocialPost.with_user(manager).search([])
        )
        self.assertIn(
            self.social_post_account_id,
            self.SocialPostAccount.with_user(manager).search([]),
        )

    def test_compute_is_property_account(self):
        account_id = self.SocialAccount.create(
            {"name": "Account 1", "media_id": self.social_media_id.id}
        )
        account_not_property = account_id.with_user(self.any_user)
        self.assertNotEqual(account_not_property.env.user, self.env.user)
        self.assertFalse(account_not_property.is_property_account)

        account_id = self.SocialAccount.create(
            {"name": "Account 2", "media_id": self.social_media_id.id}
        )
        account_property = account_id.with_user(self.env.ref("base.user_root"))
        self.assertEqual(account_property.env.user, self.env.user)
        self.assertTrue(account_property.is_property_account)

    def test_check_can_associate(self):
        social_user = self._create_social_media_user()
        self.social_account_id.write({"user_id": self.env.user.id})
        self.social_account_id._check_can_associate()
        with self.assertRaises(AccessError):
            self.social_account_id.with_user(social_user)._check_can_associate()
        manager = self._create_social_media_manager()
        self.social_account_id.with_user(manager)._check_can_associate()

    def test_can_manage_account(self):
        social_user = self._create_social_media_user()
        manager = self._create_social_media_manager()
        self.social_account_id.write({"user_id": self.env.user.id})
        self.assertTrue(self.social_account_id.can_manage_account)
        self.assertFalse(
            self.social_account_id.with_user(social_user).can_manage_account,
            "A user who is not the responsible one cannot manage the account",
        )
        self.assertTrue(
            self.social_account_id.with_user(manager).can_manage_account,
            "A social media administrator can manage any account",
        )

    def test_wizard_cannot_touch_account_of_another_user(self):
        social_user = self._create_social_media_user()
        self.social_account_id.write({"user_id": self.env.user.id})
        wizard = self.WizardAccount.with_user(social_user).create(
            {
                "media_id": self.social_media_id.id,
                "account_id": self.social_account_id.id,
                "update_keys": True,
            }
        )
        with self.assertRaises(AccessError):
            wizard.action_update_account()
        with self.assertRaises(AccessError):
            wizard.action_associate_social_account()

    def test_wizard_allows_the_responsible_user(self):
        social_user = self._create_social_media_user()
        self.social_account_id.write({"user_id": social_user.id})
        wizard = self.WizardAccount.with_user(social_user).create(
            {
                "media_id": self.social_media_id.id,
                "account_id": self.social_account_id.id,
            }
        )
        wizard._check_account_access()

    def test_purge_account_requires_manager(self):
        social_user = self._create_social_media_user()
        with self.assertRaises(AccessError):
            self.social_account_id.with_user(social_user).action_purge_account()

    def test_user_cannot_unlink_account(self):
        social_user = self._create_social_media_user()
        account = self.SocialAccount.with_user(social_user).create(
            {"name": "Own account", "media_id": self.social_media_id.id}
        )
        with self.assertRaises(AccessError):
            account.unlink()

    def test_post_count(self):
        other_account = self.SocialAccount.create(
            {"name": "Other account", "media_id": self.social_media_id.id}
        )
        self.assertEqual(self.social_account_id.post_count, 1)
        self.assertEqual(other_account.post_count, 0)
        self.SocialPost.create(
            {
                "message": "Another message",
                "account_ids": [Command.set([self.social_account_id.id])],
            }
        )
        self.assertEqual(
            self.social_account_id.post_count,
            2,
            "A new post targeting the account has to invalidate the counter "
            "without waiting for the next request",
        )

    def test_action_open_posts(self):
        action = self.social_account_id.action_open_posts()
        self.assertEqual(action["res_model"], "social.post")
        self.assertEqual(
            action["domain"], [("account_ids", "in", self.social_account_id.ids)]
        )
        self.assertEqual(self.SocialPost.search(action["domain"]), self.social_post_id)


class TestSocialAccountUtmCampaigns(TestSocialMediaBaseCommon):
    """The marketing campaigns reachable from a social media account."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.UtmCampaign = cls.env["utm.campaign"]
        cls.utm_campaign_id = cls.UtmCampaign.create({"name": "Test Utm Campaign"})

    def test_utm_campaign_count_and_action(self):
        # The campaign is set on the post: a publication of a post always
        # carries the campaign of that post.
        self.social_post_id.write({"campaign_id": self.utm_campaign_id.id})
        self.social_account_id.invalidate_recordset()
        self.assertEqual(self.social_account_id.utm_campaign_count, 1)
        action = self.social_account_id.action_open_utm_campaigns()
        self.assertEqual(action["res_model"], "utm.campaign")
        self.assertEqual(
            self.UtmCampaign.search_count(action["domain"]),
            1,
        )

    def test_utm_campaign_count_covers_the_imported_publications(self):
        """A publication imported from the social media has no parent post."""
        imported = self.SocialPostAccount.create(
            {
                "message": "Imported publication",
                "account_id": self.social_account_id.id,
                "campaign_id": self.utm_campaign_id.id,
            }
        )
        self.assertFalse(imported.post_id)
        self.social_account_id.invalidate_recordset()
        self.assertEqual(self.social_account_id.utm_campaign_count, 1)

    def test_utm_campaign_count_covers_the_posts_not_sent_yet(self):
        """A draft post has no publication, but its campaign is already known."""
        draft = self.SocialPost.create(
            {
                "message": "Draft post",
                "account_ids": [Command.set(self.social_account_id.ids)],
                "campaign_id": self.utm_campaign_id.id,
            }
        )
        self.assertEqual(draft.state, "draft")
        self.assertFalse(draft.post_account_ids)
        self.social_account_id.invalidate_recordset()
        self.assertEqual(self.social_account_id.utm_campaign_count, 1)
        action = self.social_account_id.action_open_utm_campaigns()
        self.assertEqual(
            self.UtmCampaign.search(action["domain"]), self.utm_campaign_id
        )

    def test_utm_campaign_count_does_not_count_a_campaign_twice(self):
        """The same campaign on a post and on an imported publication is one."""
        self.social_post_id.write({"campaign_id": self.utm_campaign_id.id})
        self.SocialPostAccount.create(
            {
                "message": "Imported publication",
                "account_id": self.social_account_id.id,
                "campaign_id": self.utm_campaign_id.id,
            }
        )
        self.social_account_id.invalidate_recordset()
        self.assertEqual(self.social_account_id.utm_campaign_count, 1)

    def test_utm_campaign_count_without_campaigns(self):
        self.assertEqual(self.social_account_id.utm_campaign_count, 0)

    def test_utm_campaign_count_ignores_the_other_accounts(self):
        other_account = self.SocialAccount.create(
            {"name": "Other account", "media_id": self.social_media_id.id}
        )
        self.SocialPostAccount.create(
            {
                "message": "Other publication",
                "account_id": other_account.id,
                "campaign_id": self.utm_campaign_id.id,
            }
        )
        self.assertEqual(self.social_account_id.utm_campaign_count, 0)
