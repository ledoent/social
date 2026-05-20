# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import json
import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.tools import file_open

from ..social_utils import _generate_timestamps, get_weeks

_logger = logging.getLogger(__name__)

_HEALTH_SEVERITY = {
    "healthy": 0,
    "never_connected": 0,
    "warning": 1,
    "expired": 2,
    "disconnected": 2,
}
_HEALTH_DEGRADED = ("warning", "expired", "disconnected")
_FOLLOWER_HISTORY_WINDOW_DAYS = 7


class SocialAccount(models.Model):
    _name = "social.account"
    _inherit = ["avatar.mixin", "social.media.base.mixin"]
    _description = "Social Account"

    """
        This model defines the accounts associated with the different social networks.
    """

    name = fields.Char()
    active = fields.Boolean(default=True)
    username = fields.Char()
    media_id = fields.Many2one("social.media", ondelete="restrict")
    media_type = fields.Selection(related="media_id.media_type")
    company_id = fields.Many2one(
        "res.company", "Company", default=lambda self: self.env.company
    )
    advertising_account_id = fields.Char()
    last_update_account = fields.Datetime()
    post_account_ids = fields.One2many("social.post.account", "account_id")

    @api.model
    def _default_image(self):
        return base64.b64encode(file_open("base/static/img/avatar.png", "rb").read())

    image_1920 = fields.Image(default=_default_image)
    # Use media platform icon for kanban group headers
    # Override avatar_128 to show platform logo instead of account image
    avatar_128 = fields.Image(
        compute="_compute_avatar_128",
        store=False,
        help="Platform logo dynamically retrieved from social.media.image",
    )
    avatar_256 = fields.Image(
        compute="_compute_avatar_256",
        store=False,
        help="Platform logo in 256x256 for better quality",
    )

    @api.depends("media_id", "media_id.image")
    def _compute_avatar_128(self):
        """Use platform logo as avatar for group headers"""
        for account in self:
            if account.media_id and account.media_id.image:
                # Dynamically get platform logo from social.media
                account.avatar_128 = account.media_id.image
            else:
                # Fallback to account image if no media linked
                account.avatar_128 = account.image_128

    @api.depends("media_id", "media_id.image")
    def _compute_avatar_256(self):
        """Use platform logo for higher resolution displays"""
        for account in self:
            if account.media_id and account.media_id.image:
                # Dynamically get platform logo from social.media
                account.avatar_256 = account.media_id.image
            else:
                # Fallback to account image
                account.avatar_256 = account.image_256

    # STATISTICS
    comment_count = fields.Integer(default=0)
    like_count = fields.Integer(default=0)
    click_count = fields.Integer(default=0)
    share_count = fields.Integer(default=0)
    interactions_count = fields.Integer(
        compute="_compute_interactions_count",
        store=True,
        default=0,
        help="""
            Indicates the interactions with the
            publication (clicks, likes, comments,shares).
        """,
    )
    impression_count = fields.Integer(
        default=0,
        help="""
            Total number of views, which may include
            multiple views by the same user.
        """,
    )
    engagement = fields.Float(default=0)

    account_url = fields.Char(compute="_compute_account_url", store=True)
    environment = fields.Selection(
        [("test", "Test"), ("production", "Production")], default="test"
    )
    need_update = fields.Boolean(default=False)
    show_post_calendar = fields.Boolean(
        default=False, help="Defines whether to display upcoming posts in the calendar."
    )

    # SECURITY
    access_token = fields.Char()
    refresh_access_token = fields.Char()
    expire_access_token_date = fields.Date()
    is_property_account = fields.Boolean(
        default=False, compute="_compute_is_property_account"
    )

    @api.depends_context("uid")
    def _compute_is_property_account(self):
        """True when the current user is the creator of this account."""
        for account in self:
            account.is_property_account = self.env.user == account.create_uid

    def update_account(self):
        return {
            "res_model": "wizard.social.account",
            "views": [[False, "form"]],
            "target": "new",
            "type": "ir.actions.act_window",
            "context": {
                "default_account_id": self.id,
                "default_media_id": self.media_id.id,
                "social_update_account": True,
            },
        }

    def delete_account(self):
        """
        Archive social media account.

        This method is used to delete the social account,
        as well as all its associated posts and campaigns.
        It also marks all the associated posts and campaigns
        as inactive.
        """
        SocialPostAccount = self.env["social.post.account"]
        SocialPost = self.env["social.post"]
        UtmCampaign = self.env["utm.campaign"]
        for account in self:
            SocialPostAccount.search([("account_id", "=", account.id)]).write(
                {
                    "active": False,
                }
            )
            UtmCampaign.search([("account_id", "=", account.id)]).write(
                {
                    "active": False,
                }
            )
            post_ids = SocialPost.search([("account_ids", "in", account.id)])
            for post in post_ids:
                if len(post.account_ids) == 1:
                    post.write(
                        {
                            "active": False,
                        }
                    )
            account.write(
                {
                    "active": False,
                }
            )

    def _compute_display_name(self):
        """Display clean account name - platform icon shown via avatar widget"""
        for account in self:
            # Show just the account name - the platform logo/icon will be displayed
            # via the many2one_avatar widget which uses avatar_128/avatar_256 fields
            # that are computed to show media_id.image dynamically
            account.display_name = account.name or "Unnamed Account"

    def _fields_account_url(self):
        """Return list of (field_name, url_template) pairs for account_url computation.

        Override in platform modules to map media_type → profile URL.
        Each entry: (field_name_or_media_type, url_string).
        """
        return []

    @api.depends(lambda self: [val[0] for val in self._fields_account_url()])
    def _compute_account_url(self):
        for account in self:
            for val_url in account._fields_account_url():
                if len(val_url) < 2:
                    continue
                if account.media_id.media_type:
                    account.account_url = (
                        val_url[1] if account.media_id.media_type in val_url[0] else ""
                    )
                else:
                    continue

    @api.depends("click_count", "like_count", "share_count", "comment_count")
    def _compute_interactions_count(self):
        for account in self:
            account.interactions_count = (
                account.click_count
                + account.like_count
                + account.share_count
                + account.comment_count
            )

    def _filter_statistics(self, entity_statistics):
        post_statistics = {
            "click_count": 0,
            "like_count": 0,
            "comment_count": 0,
            "share_count": 0,
            "engagement": 0,
            "impression_count": 0,
        }
        for __, statistics in entity_statistics.items():
            post_statistics["click_count"] += statistics[0]
            post_statistics["like_count"] += statistics[1]
            post_statistics["comment_count"] += statistics[2]
            post_statistics["share_count"] += statistics[3]
            post_statistics["engagement"] += statistics[4]
            post_statistics["impression_count"] += statistics[5]
        return post_statistics

    def _get_chart_account_statistics(self, start_date, end_date, granularity):
        """
        Returns a list of dictionaries containing statistics
        for the specified social media account, formatted correctly
        for display in the chart view.

        :param start_date: Start date and time of the period
        :param end_date: End date and time of the period
        :param granularity: Level of granularity for the statistics
                            (e.g., WEEK, MONTH, YEAR)
        :return: List of dictionaries
        :rtype: dict
        """
        return []

    def get_chart_account_statistics(
        self, start_date=None, end_date=None, granularity="WEEK"
    ):
        return self._get_chart_account_statistics(start_date, end_date, granularity)

    def _update_posts_statistics(self, post_id, domain):
        """
        Update posts and statistics.

        :param post_id: ID of the post
        :param domain: Domain of the post
        :return: List of dictionaries
        :rtype: list
        """
        return []

    def update_posts_statistics(self, post_id=None, domain=None):
        """
        Update posts and  statistics
        """
        statistics = self._update_posts_statistics(post_id, domain)
        return json.dumps(statistics)

    def validate_access_token(self):
        """
        Validates the access token for the social media account.
        """
        pass

    def _load_ads_accounts(self):
        """
        Returns a dictionary containing the ads accounts of the social media account.

        :return: Dictionary containing ads accounts
        :rtype: dict
        """
        return {}

    def load_ads_accounts(self):
        return self._load_ads_accounts()

    def _run_check_media_updates(self):
        """
        Checks for social media updates.
        This method is used to check for any new social media updates.

        :return: True if new updates are found, otherwise False
        :rtype: bool
        """
        return False

    def _need_update(self, need_update=True):
        """Broadcast a bus notification to prompt the UI to refresh account data."""
        self.env["bus.bus"]._sendone(
            self.env.user.partner_id,
            "social_need_update",
            {"need_update": need_update},
        )

    def _get_default_filter_date(self, start_date, end_date, time_date=False, months=1):
        start = start_date or (fields.Datetime.now() - relativedelta(months=months))
        end = end_date or fields.Datetime.now()
        if time_date:
            return _generate_timestamps(date_start=start, date_end=end)
        return start, end

    def _map_chart_statistics(self, account_statistics, **values):
        data_chart = []
        statistics_values = (
            account_statistics.values()
            if isinstance(account_statistics, dict)
            else account_statistics
        )
        if statistics_values and self.media_type:
            chart_weeks = get_weeks(
                values.get(
                    "start_date",
                ),
                values.get(
                    "end_date",
                ),
                freq=values.get("freq", "W-MON"),
            )

            def map_chart_data(chart_statistics, label, key_data=0):
                dataset = {
                    "pointStyle": "circle",
                    "pointRadius": 10,
                    "pointHoverRadius": 15,
                    "label": self.env._(label),
                    "data": [
                        statistics[key_data]
                        for statistics in chart_statistics
                        if len(statistics) > key_data
                    ],
                }
                return dataset

            impression_count = sum(
                [
                    statistics[5]
                    for statistics in statistics_values
                    if len(statistics) > 5
                ]
            )
            comment_count = sum(
                [
                    statistics[2]
                    for statistics in statistics_values
                    if len(statistics) > 2
                ]
            )
            reaction_count = sum(
                [
                    statistics[1] + statistics[3]
                    for statistics in statistics_values
                    if len(statistics) > 1 and len(statistics) > 3
                ]
            )
            data_chart.append(
                {
                    "id": self.id,
                    "name": self.env._(f"[{self.media_type.upper()}] {self.name}"),
                    "impressionCount": impression_count,
                    "commentCount": comment_count,
                    "reactionCount": reaction_count,
                    "chartLabel": self.env._("Statistics"),
                    "labels": [week for week in chart_weeks],
                    "datasets": [
                        map_chart_data(statistics_values, "Clicks", 0),
                        map_chart_data(statistics_values, "Shares", 3),
                        map_chart_data(statistics_values, "Likes", 1),
                        map_chart_data(statistics_values, "Comments", 2),
                        map_chart_data(
                            statistics_values,
                            "Impressions",
                            5,
                        ),
                        map_chart_data(statistics_values, "Engagement", 4),
                    ],
                }
            )
        return data_chart

    # ─────────────────────────────────────────────────────────────────────
    # Tier 2 — Connection Health Board
    # Per-account health snapshot driven by the daily refresh cron. Channel
    # modules implement `_refresh_account_health` and the test-post pair;
    # base provides the cron orchestration + degradation hook (mail.activity).
    # ─────────────────────────────────────────────────────────────────────
    health_status = fields.Selection(
        [
            ("never_connected", "Never connected"),
            ("healthy", "Healthy"),
            ("warning", "Warning"),
            ("expired", "Expired"),
            ("disconnected", "Disconnected"),
        ],
        default="never_connected",
        readonly=True,
        tracking=True,
        help=(
            "Current connection health. Computed by the daily refresh cron "
            "(see `_cron_refresh_all_accounts`). Channel modules override "
            "`_refresh_account_health` to derive the value from platform "
            "API state."
        ),
    )
    health_message = fields.Char(
        readonly=True,
        translate=False,
        help="Human-readable label rendered on the kanban status pill.",
    )
    health_evaluated_at = fields.Datetime(
        readonly=True,
        help="Timestamp of the most recent health-refresh cron run.",
    )
    health_severity = fields.Integer(
        compute="_compute_health_severity",
        store=True,
        help=(
            "0=healthy/never, 1=warning, 2=expired/disconnected. Used as "
            "the kanban default sort so degraded accounts surface first."
        ),
    )
    media_brand_color = fields.Char(
        related="media_id.brand_color",
        store=False,
        help="Hex brand color for the kanban card's left band.",
    )

    follower_count = fields.Integer(default=0, readonly=True)
    follower_count_at = fields.Datetime(
        readonly=True,
        help="Timestamp of the most recent follower_count refresh.",
    )
    follower_count_prev = fields.Integer(
        default=0,
        readonly=True,
        help=(
            "Follower count from approximately 7 days ago. Rotated forward "
            "by the daily cron when the live snapshot ages past the window."
        ),
    )
    follower_count_delta = fields.Integer(
        compute="_compute_follower_count_delta",
        store=True,
        help="follower_count - follower_count_prev. Drives the trend arrow.",
    )

    last_post_at = fields.Datetime(
        compute="_compute_last_post",
        store=True,
        help="Published date of the most recent published post on this account.",
    )
    last_post_id = fields.Many2one(
        "social.post",
        compute="_compute_last_post",
        store=True,
        help="Most recent published post, for kanban click-through.",
    )

    @api.depends("health_status")
    def _compute_health_severity(self):
        for account in self:
            account.health_severity = _HEALTH_SEVERITY.get(account.health_status, 0)

    @api.depends("follower_count", "follower_count_prev")
    def _compute_follower_count_delta(self):
        for account in self:
            account.follower_count_delta = (
                account.follower_count - account.follower_count_prev
            )

    @api.depends(
        "post_account_ids.post_id.published_date",
        "post_account_ids.post_id.state",
    )
    def _compute_last_post(self):
        for account in self:
            published = account.post_account_ids.post_id.filtered(
                lambda p: p.state == "published" and p.published_date
            )
            latest = published.sorted("published_date", reverse=True)[:1]
            account.last_post_id = latest
            account.last_post_at = latest.published_date if latest else False

    # ── Template methods — channel modules override ────────────────────
    def _refresh_account_health(self):
        """Refresh follower_count and evaluate health_status for this account.

        Channel modules MUST override. The default implementation marks the
        account as `never_connected` so an unsupported platform never blocks
        the cron run for supported ones.

        Side effects: writes follower_count, follower_count_at,
        health_status, health_message, health_evaluated_at. Must NOT call
        `_post_health_warning` — the cron handles transition detection.
        """
        self.ensure_one()
        self.write(
            {
                "health_status": "never_connected",
                "health_message": _("No health refresh implemented for %s")
                % (self.media_id.name or "?"),
                "health_evaluated_at": fields.Datetime.now(),
            }
        )

    def _test_post_and_delete(self, message=None, delay_seconds=60):
        """Publish a test post to the live account, then schedule its
        deletion after `delay_seconds`. Returns the platform post id.

        Channel modules MUST override. Base raises NotImplementedError so
        misuse fails loudly rather than silently no-op'ing.

        Default copy is read from the `social_media_base.test_post_message`
        system parameter so admins can edit it without code changes.
        """
        raise NotImplementedError(
            _("Channel module must implement _test_post_and_delete()")
        )

    def _delete_test_post(self, platform_post_id):
        """Delete a previously-published test post by platform id.

        Channel modules MUST override. Called by the one-shot delete cron
        scheduled inside `_test_post_and_delete`.
        """
        raise NotImplementedError(
            _("Channel module must implement _delete_test_post()")
        )

    def _post_health_warning(self, prior_status):
        """Hook fired by the cron when health_status degrades.

        Default: schedules a `mail.activity` todo on `create_uid` (falling
        back to the current user) summarizing the change. Downstream and
        channel modules may override to add platform-specific recovery
        URLs, external notifications (ntfy/Slack), or escalation logic.

        `prior_status` is supplied so overrides can distinguish first-time
        degradation from a continued one if they want.
        """
        self.ensure_one()
        assignee = self.create_uid or self.env.user
        summary = _("Reconnect %s") % (self.media_id.name or _("social account"))
        note = _(
            "Account: %(name)s\nStatus: %(now)s (was %(prev)s)\nMessage: %(msg)s"
        ) % {
            "name": self.name or "?",
            "now": self.health_status,
            "prev": prior_status,
            "msg": self.health_message or "",
        }
        self.activity_schedule(
            "mail.mail_activity_data_todo",
            user_id=assignee.id,
            summary=summary,
            note=note,
            date_deadline=fields.Date.context_today(self),
        )

    # ── Cron orchestrator ───────────────────────────────────────────────
    @api.model
    def _cron_refresh_all_accounts(self):
        """Iterate active accounts; rotate follower history; refresh health;
        fire warning hooks on degradation. Errors per-account are swallowed
        and logged so one bad account doesn't block the rest of the run.

        Wired to `cron_refresh_account_health` in
        `data/ir_cron_data.xml` (daily, 06:00 UTC).
        """
        accounts = self.search([("active", "=", True)])
        now = fields.Datetime.now()
        window = now - timedelta(days=_FOLLOWER_HISTORY_WINDOW_DAYS)
        for account in accounts:
            prior = account.health_status
            # Rotate the follower history slot before refresh so the
            # delta arrow reflects week-over-week movement, not
            # measurement noise from the same day.
            if account.follower_count_at and account.follower_count_at <= window:
                account.follower_count_prev = account.follower_count
            try:
                account._refresh_account_health()
            except Exception as exc:  # noqa: BLE001 — log + continue
                _logger.exception(
                    "Health refresh failed for account %s (%s): %s",
                    account.id,
                    account.media_id.media_type,
                    exc,
                )
                account.write(
                    {
                        "health_status": "disconnected",
                        "health_message": _("Refresh failed: %s") % str(exc)[:120],
                        "health_evaluated_at": now,
                    }
                )
            if (
                account.health_status in _HEALTH_DEGRADED
                and prior != account.health_status
            ):
                try:
                    account._post_health_warning(prior)
                except Exception as exc:  # noqa: BLE001 — log + continue
                    _logger.exception(
                        "Health warning post failed for account %s: %s",
                        account.id,
                        exc,
                    )

    # ── Action methods — kanban button bindings ─────────────────────────
    def action_reconnect(self):
        """Re-open the connect wizard pre-filled with this account.

        The wizard's `social_update_account` context flag tells Scene 1 to
        skip the pre-flight and land directly on the credentials form.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "wizard.social.account",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_media_id": self.media_id.id,
                "default_account_id": self.id,
                "social_update_account": True,
            },
        }

    def action_test_post(self):
        """Publish a self-deleting test post to prove the connection works.

        Guarded on `health_status == healthy` so users can't post-spam a
        degraded account. Channel modules implement the actual post +
        schedule-delete path via `_test_post_and_delete`.
        """
        self.ensure_one()
        if self.health_status != "healthy":
            from odoo.exceptions import UserError

            raise UserError(
                _(
                    "Account must be Healthy before sending a test post "
                    "(current status: %s)."
                )
                % self.health_status
            )
        self._test_post_and_delete()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Test posted"),
                "message": _("Will auto-delete in about 60 seconds."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_disconnect(self):
        """Soft-disconnect this account — archives it and flags the status.

        Tokens are intentionally NOT cleared here so a later reconnect
        can re-use them via the wizard's update flow if the user changes
        their mind. Hard credential rotation should go through the
        reconnect wizard.
        """
        self.ensure_one()
        self.write(
            {
                "active": False,
                "health_status": "disconnected",
                "health_message": _("Disconnected by user"),
                "health_evaluated_at": fields.Datetime.now(),
            }
        )
        return True
