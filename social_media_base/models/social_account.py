# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import json
import logging

import psycopg2
from dateutil.relativedelta import relativedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.service.model import PG_CONCURRENCY_ERRORS_TO_RETRY
from odoo.tools import file_open

from ..exceptions import SocialCredentialsError
from ..social_utils import generate_timestamps, get_chart_periods

_logger = logging.getLogger(__name__)

CHART_GRANULARITIES = {
    "DAY": relativedelta(days=1),
    "WEEK": relativedelta(weeks=1),
    "MONTH": relativedelta(months=1),
}

# Statistics of a period the social media reported nothing for: clicks,
# likes, comments, shares, engagement and impressions.
EMPTY_CHART_STATISTICS = (0, 0, 0, 0, 0, 0)

# How long the initial sync waits before trying again an account another
# transaction was updating. Long enough for the update that took the row to
# be over, short enough for the dashboard not to announce an import that is
# not running.
INITIAL_SYNC_RETRY_DELAY_MINUTES = 5


class SocialAccount(models.Model):
    """Account associated with a social media."""

    _name = "social.account"
    _inherit = [
        "mail.thread",
        "mail.activity.mixin",
        "avatar.mixin",
        "social.media.base.mixin",
    ]
    _description = "Social Account"

    @api.model
    def _default_image(self):
        with file_open("base/static/img/avatar.png", "rb") as image_file:
            return base64.b64encode(image_file.read())

    name = fields.Char()
    active = fields.Boolean(default=True)
    username = fields.Char()
    media_id = fields.Many2one("social.media", ondelete="restrict")
    media_type = fields.Selection(related="media_id.media_type")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    user_id = fields.Many2one(
        "res.users",
        string="Responsible",
        required=True,
        index=True,
        default=lambda self: self.env.user,
        tracking=True,
        help="User this account belongs to. Only the responsible user and the "
        "social media administrators can see it.",
    )
    remote_ref = fields.Char(
        string="Remote Reference",
        copy=False,
        index=True,
        help="Identifier of this account on the social media. It is set by "
        "the connector module of each social media.",
    )
    last_update_account = fields.Datetime()
    post_account_ids = fields.One2many("social.post.account", "account_id")
    post_ids = fields.Many2many(
        "social.post",
        relation="social_account_social_post_rel",
        column1="social_account_id",
        column2="social_post_id",
        string="Posts",
        readonly=True,
        help="Posts that target this account. Inverse of the accounts of a "
        "post, it is what keeps the counter up to date.",
    )
    image_1920 = fields.Image(default=_default_image)

    comment_count = fields.Integer(default=0)
    like_count = fields.Integer(default=0)
    click_count = fields.Integer(default=0)
    share_count = fields.Integer(default=0)
    interactions_count = fields.Integer(
        compute="_compute_interactions_count",
        store=True,
        default=0,
        help="Interactions with the publication: clicks, likes, comments and "
        "shares.",
    )
    impression_count = fields.Integer(
        default=0,
        help="Total number of views, which may include multiple views by the "
        "same user.",
    )
    engagement = fields.Float(default=0, digits=(16, 2))

    account_url = fields.Char(compute="_compute_account_url")
    need_update = fields.Boolean(default=False)
    pending_initial_sync = fields.Boolean(
        default=False,
        copy=False,
        help="Technical field: the account was just associated and its posts "
        "still have to be imported by the initial sync cron.",
    )

    access_token = fields.Char(groups="base.group_system")
    refresh_access_token = fields.Char(groups="base.group_system")
    expire_access_token_date = fields.Date(string="Expire Access Token")
    is_property_account = fields.Boolean(
        default=False, compute="_compute_is_property_account"
    )
    can_manage_account = fields.Boolean(
        compute="_compute_can_manage_account",
        help="Whether the current user may update or archive this account: "
        "its responsible user and the social media administrators.",
    )
    post_count = fields.Integer(compute="_compute_post_count")
    utm_campaign_count = fields.Integer(compute="_compute_utm_campaign_count")

    @api.depends("post_ids")
    def _compute_post_count(self):
        counts = dict(
            self.env["social.post"]._read_group(
                domain=[("account_ids", "in", self.ids)],
                groupby=["account_ids"],
                aggregates=["__count"],
            )
        )
        for account in self:
            account.post_count = counts.get(account, 0)

    def action_open_posts(self):
        """Open the posts this account is one of the targets of."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Posts"),
            "res_model": "social.post",
            "view_mode": "kanban,tree,form",
            "domain": [("account_ids", "in", self.ids)],
            "context": {"default_account_ids": [Command.set(self.ids)]},
        }

    def _get_utm_campaigns(self):
        """Return the marketing campaigns of the posts of this account.

        Both sides have to be read. A publication imported from the social
        media has no parent post and its campaign is written on the imported
        publication itself, so the posts alone would leave it out; and a post
        that is still a draft has no publication yet, so the publications
        alone would leave its campaign out until it is sent.

        :rtype: recordset
        """
        campaigns = (
            self.env["social.post.account"]
            .search(
                [
                    ("account_id", "in", self.ids),
                    ("campaign_id", "!=", False),
                ]
            )
            .campaign_id
        )
        return (
            campaigns
            | self.env["social.post"]
            .search(
                [
                    ("account_ids", "in", self.ids),
                    ("campaign_id", "!=", False),
                ]
            )
            .campaign_id
        )

    @api.depends("post_account_ids.campaign_id", "post_ids.campaign_id")
    def _compute_utm_campaign_count(self):
        for account in self:
            account.utm_campaign_count = len(account._get_utm_campaigns())

    def action_open_utm_campaigns(self):
        """Open the marketing campaigns of the publications of this account."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Marketing Campaigns"),
            "res_model": "utm.campaign",
            "view_mode": "tree,form",
            "domain": [("id", "in", self._get_utm_campaigns().ids)],
        }

    @api.depends("user_id")
    @api.depends_context("uid")
    def _compute_is_property_account(self):
        for account in self:
            account.is_property_account = self.env.user == account.user_id

    @api.depends("user_id")
    @api.depends_context("uid")
    def _compute_can_manage_account(self):
        is_manager = self.env.user.has_group(
            "social_media_base.group_social_media_manager"
        )
        for account in self:
            account.can_manage_account = is_manager or account.user_id == self.env.user

    def action_update_account(self):
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

    def action_archive_account(self):
        """Archive the accounts and their whole footprint.

        Nothing is removed from the social media: relinking the account
        reactivates everything.
        """
        self.write(
            {
                "active": False,
            }
        )

    def action_unarchive_account(self):
        """Restore the accounts and everything archived with them.

        The scheduled posts whose date passed while the account was archived
        are sent back to draft instead of being published on the spot: that is
        handled by ``social.post.write`` for every way of reactivating a post,
        see :meth:`~odoo.addons.social_media_base.models.social_post.SocialPost.
        _reset_overdue_schedule`.
        """
        self.write(
            {
                "active": True,
            }
        )

    @api.model
    def _find_account_to_associate(self, media_type, remote_ref, username=None):
        """Return the account already linked to ``remote_ref`` on this media.

        The remote reference is the only immutable identifier: a user name
        can be renamed and reused by somebody else. ``username`` is a
        fallback for the accounts created before it was stored.
        """
        accounts = self.sudo().with_context(active_test=False)
        account = (
            accounts.search(
                [
                    ("media_type", "=", media_type),
                    ("remote_ref", "=", remote_ref),
                ],
                limit=1,
            )
            if remote_ref
            else self.browse()
        )
        if not account and username:
            account = accounts.search(
                [
                    ("media_type", "=", media_type),
                    ("username", "=", username),
                    ("remote_ref", "in", [False, ""]),
                ],
                limit=1,
            )
        return account

    def _check_can_associate(self):
        """Check the current user may relink this already existing account.

        Associating writes the credentials of whoever completes the OAuth
        flow, so it is restricted to the responsible user and to the
        managers to prevent taking over somebody else's account.
        """
        self.ensure_one()
        account_sudo = self.sudo()
        if (
            account_sudo.company_id
            and account_sudo.company_id not in self.env.companies
        ):
            raise AccessError(
                _(
                    "The account %(account)s belongs to another company.",
                    account=account_sudo.display_name,
                )
            )
        if self.env.user.has_group("social_media_base.group_social_media_manager"):
            return
        if account_sudo.user_id != self.env.user:
            raise AccessError(
                _(
                    "The account %(account)s is already associated with "
                    "another user. Ask its responsible user or a social "
                    "media administrator to relink it.",
                    account=account_sudo.display_name,
                )
            )

    def action_purge_account(self):
        """Delete the accounts and their publication history from Odoo only.

        The records of the other applications that reference an account lose
        the link instead of being deleted.

        :return: the accounts list action, the current record no longer exists.
        :rtype: dict
        """
        if not self.env.user.has_group("social_media_base.group_social_media_manager"):
            raise AccessError(
                _("Only a social media administrator can delete an account.")
            )
        accounts = self.with_context(active_test=False)
        post_accounts = accounts.post_account_ids
        linked_posts = (
            self.env["social.post"]
            .with_context(active_test=False)
            .search([("account_ids", "in", accounts.ids)])
        )
        posts = linked_posts.filtered(lambda post: not (post.account_ids - accounts))
        shared_posts = linked_posts - posts
        _logger.info(
            "%s permanently deletes the social media accounts %s",
            self.env.user.login,
            accounts.mapped("display_name"),
        )
        post_accounts.unlink()
        posts.unlink()
        if shared_posts:
            shared_posts.write(
                {"account_ids": [Command.unlink(account.id) for account in accounts]}
            )
        accounts._purge_linked_records()
        accounts.unlink()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "social_media_base.social_account_action"
        )
        action["target"] = "main"
        return action

    def _purge_linked_records(self):
        """Delete what these accounts own before they are deleted themselves.

        Extension point of :meth:`action_purge_account` for the modules
        adding records that mirror the social media of an account: the
        foreign keys only unlink them, which would leave behind records
        pointing at nothing. It runs while the accounts still exist, so the
        links can still be read.
        """

    @api.model
    def _get_removal_domain(self, media_type):
        return [("media_type", "=", media_type)]

    @api.model
    def _remove_social_media(self, media_type):
        """Drop the credentials and archive the accounts of an uninstalled media.

        ``remote_ref`` is kept, so reinstalling the connector and relinking
        the account restores its history instead of duplicating it.
        """
        accounts = (
            self.sudo()
            .with_context(active_test=False)
            .search(self._get_removal_domain(media_type))
        )
        if accounts:
            accounts.write(accounts._get_removal_values())

    def _get_removal_values(self):
        """Return the values written on an account when its module is uninstalled.

        Connector modules override it to complete these generic values.

        :rtype: dict
        """
        return {
            "access_token": False,
            "refresh_access_token": False,
            "expire_access_token_date": False,
            "active": False,
        }

    def write(self, vals):
        to_toggle = (
            self.filtered(lambda account: account.active != vals["active"])
            if "active" in vals
            else self.browse()
        )
        res = super().write(vals)
        if to_toggle:
            to_toggle._propagate_active_to_related(vals["active"])
        return res

    def _propagate_active_to_related(self, active):
        """Archive or unarchive the whole footprint of these accounts.

        Dashboard posts and the posts left without any active account. Other
        modules extend it with their own related records.
        """
        SocialPostAccount = self.env["social.post.account"].with_context(
            active_test=False
        )
        SocialPost = self.env["social.post"].with_context(active_test=False)
        SocialPostAccount.search(
            [("account_id", "in", self.ids), ("active", "!=", active)]
        ).write({"active": active})
        posts = SocialPost.search(
            [("account_ids", "in", self.ids), ("active", "!=", active)]
        )
        if not active:
            posts = posts.filtered(lambda post: not post.account_ids.filtered("active"))
        if not posts:
            return
        posts.write({"active": active})

    @api.depends("name", "media_type")
    def _compute_display_name(self):
        for account in self:
            account.display_name = (
                f"[{account.media_type.upper()}] {account.name}"
                if account.media_type
                else account.name
            )

    def _fields_account_url(self):
        """Return the account URLs as ``(media_type, url)`` tuples.

        Each connector module appends its own.

        :rtype: list
        """
        return []

    @api.depends("media_type", "remote_ref", "username")
    def _compute_account_url(self):
        for account in self:
            account.account_url = ""
            for val_url in account._fields_account_url():
                if len(val_url) < 2:
                    continue
                if account.media_type == val_url[0]:
                    account.account_url = val_url[1]
                    break

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
        """Add up the statistics a connector reports for several entities.

        The connector is the one building ``entity_statistics``, so the tuple
        is the contract between both sides: six numbers, always in the order
        ``(clicks, likes, comments, shares, engagement, impressions)``, the
        same one ``_map_chart_statistics`` walks on.

        :param dict entity_statistics: statistics tuple by entity key.
        :return: the totals, keyed by the field they feed.
        :rtype: dict
        """
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

    def _get_chart_account_statistics(
        self, start_date, end_date, granularity, with_totals=True
    ):
        """Return the account statistics formatted for the chart view.

        :param start_date: start of the period.
        :param end_date: end of the period.
        :param granularity: one of the keys of ``CHART_GRANULARITIES``.
        :param with_totals: also read the figures of the whole account, the
            ones the header shows next to the ones of the period. They do not
            depend on the range, so the chart view only asks for them when it
            is first loaded.
        :rtype: list
        """
        return []

    def _get_chart_granularities(self):
        """Granularities the chart view offers for these accounts.

        Every social media groups its statistics by its own units, so a
        connector narrows the list down to the ones its API supports.

        :rtype: list
        """
        return list(CHART_GRANULARITIES)

    @api.model
    def _check_chart_date_range(self, start_date, end_date, granularity):
        """Refuse a range that does not cover one unit of the granularity.

        The social media answer an error of their own when the range is
        shorter than the unit they group the statistics by, so the case is
        caught here to answer something the user can act on. The check is
        kept on the public method so it also covers the calls made through
        RPC by the chart view.

        :raises UserError: when the range is shorter than one unit.
        """
        unit = CHART_GRANULARITIES.get(granularity)
        if not (unit and start_date and end_date):
            return
        start = fields.Date.to_date(start_date)
        end = fields.Date.to_date(end_date)
        if start and end and end < start + unit:
            raise UserError(
                _(
                    "The statistics are grouped by %(granularity)s, so the "
                    "date range has to cover at least one of them. Widen the "
                    "range or pick a smaller granularity.",
                    granularity=granularity.lower(),
                )
            )

    def get_chart_account_statistics(
        self, start_date=None, end_date=None, granularity="DAY", with_totals=True
    ):
        self._check_chart_date_range(start_date, end_date, granularity)
        return self._get_chart_account_statistics(
            start_date, end_date, granularity, with_totals=with_totals
        )

    def _update_posts_statistics(self, post_id, domain):
        """Update the posts and their statistics.

        :param post_id: post to update, all of them when not set.
        :param domain: additional domain on the posts.
        :rtype: list
        """
        return []

    def update_posts_statistics(self, post_id=None, domain=None):
        """Refresh the posts and the statistics of the accounts.

        An account refreshed here does not need its initial sync any more:
        this is the very import the cron was going to run, so the flag is
        cleared and the dashboard stops announcing a background import. It is
        also what keeps the *Update* button able to unblock an account whose
        import failed.

        :param post_id: post to update, all of them when not set.
        :param domain: additional domain on the posts.
        :rtype: str
        """
        accounts = self or self.search([])
        statistics = self._update_posts_statistics(post_id, domain)
        pending = accounts.filtered("pending_initial_sync")
        if pending:
            pending.sudo().write({"pending_initial_sync": False})
        return json.dumps(statistics)

    def _full_resync(self):
        """Hook for the connectors to read everything again and reconcile it.

        The ordinary refresh is free to ask the social media only about what it
        needs, which on a large account is what keeps it affordable. What it
        cannot do that way is notice that a publication was **deleted** on the
        social media: nothing is left to ask about. This is the pass that reads
        the whole thing and reconciles it.

        The default is the ordinary refresh: a social media with no notion of a
        feed read whole has nothing extra to do here, and a connector that
        already imports incrementally keeps its own way of doing it.

        Nothing is done without accounts: a connector delegates here the
        accounts it does not handle, and :meth:`update_posts_statistics` takes
        an empty recordset as every account, which would refresh a second time
        the very accounts the connector already reconciled.
        """
        if not self:
            return None
        return self.update_posts_statistics()

    def action_full_resync(self):
        """Read everything again from the social media, from the account form."""
        self.ensure_one()
        self._full_resync()

    @api.model
    def _run_full_resync(self):
        """Reconcile every account against its social media.

        This is what notices the publications deleted on the social media, and
        the only thing that does: the ordinary refresh no longer reads whole
        feeds. It runs seldom on purpose, because reading everything costs one
        call per page of publications.

        Each account is reconciled in its own savepoint: the pass writes as it
        goes, so a failure on one account must not undo what the previous ones
        already imported nor stop the ones still to come.

        The cron record does not set a user, so the search needs ``sudo()`` to
        reach the accounts of every responsible, like :meth:`_run_full_resync`'s
        sibling crons do. The accounts waiting for their initial sync are left
        out: that import is this very pass, and the two would fight over the
        same rows.
        """
        for account in self.sudo().search([("pending_initial_sync", "=", False)]):
            try:
                with self.env.cr.savepoint():
                    account._full_resync()
            except psycopg2.OperationalError as error:
                if error.pgcode in PG_CONCURRENCY_ERRORS_TO_RETRY:
                    raise
                _logger.exception(
                    "Error on the full resync of the account %s", account.id
                )
            except Exception:  # noqa: BLE001 - one account must not stop the rest
                _logger.exception(
                    "Error on the full resync of the account %s", account.id
                )

    def validate_access_token(self):
        """Hook for the connector modules to refresh an expired token.

        Called before every operation on the social media, so connectors
        keep it cheap and answer from the stored expiry dates.
        """

    def action_validate_access_token(self):
        """Check the token against the social media, from the account form.

        The user asking whether the token works expects a real answer: the
        stored dates cannot tell a token that was revoked on the social media side.
        ``check_remote_token`` is what connectors use to tell this deliberate
        check from the guard that runs before every call.
        """
        self.ensure_one()
        return self.with_context(check_remote_token=True).validate_access_token()

    def _refresh_credentials(self):
        """Renew the credentials of this account without asking the user.

        Hook for the connector modules whose social media allows it. Called
        when a publication was refused because of the credentials, so it must
        answer whether the caller can try again.

        :return: whether the account can be used again.
        :rtype: bool
        """
        return False

    def _flag_credentials_expired(self, message):
        """Record that this account needs the user to authorize it again.

        The credentials cannot be renewed from Odoo anymore, and whoever
        notices is a cron or somebody publishing on another account: the flag
        is what puts the warning on the dashboard, and the note is what
        reaches the user in charge of the account.

        :param message: the reason the social media gave.
        """
        self.ensure_one()
        if not self.need_update:
            self.sudo().write({"need_update": True})
            self._need_update()
        self.message_post(
            body=_(
                "The credentials of the account are no longer valid and could "
                "not be renewed: %(error)s. Update the account to authorize "
                "it again.",
                error=message,
            ),
            partner_ids=self.user_id.partner_id.ids,
        )

    def _run_check_media_updates(self):
        """Check for new updates on the social media.

        Every run also renews the credentials that are about to expire, so a
        token does not run out between two publications: the connectors answer
        from their stored expiry dates, so an account whose token is still
        good costs nothing. Each account is checked in its own savepoint, and
        the one that cannot be renewed is flagged instead of dropping the run
        of the others.

        The cron record does not set a user, so the search needs ``sudo()`` to
        reach the accounts of every responsible, and the tokens themselves are
        restricted to the administrators.

        Only the credentials the social media refused, raised by the connectors
        as ``SocialCredentialsError``, flag the account: the flag is cleared by
        a new authorization and by nothing else, so a timeout or a bug in a
        connector must not ask the user to authorize an account again.

        The accounts waiting for their initial sync are left out: this check
        writes the same row the import writes its statistics on, and the two
        crons run in parallel threads, so a check landing on an account that
        is being imported is what aborts one of them with a serialization
        failure. Nothing is lost by waiting: the import brings in the very
        updates this check looks for.

        :return: whether new updates were found.
        :rtype: bool
        """
        for account in self.sudo().search([("pending_initial_sync", "=", False)]):
            try:
                with self.env.cr.savepoint():
                    account.with_context(not_notify=True).validate_access_token()
            except psycopg2.OperationalError as error:
                if error.pgcode in PG_CONCURRENCY_ERRORS_TO_RETRY:
                    raise
                _logger.exception(
                    "Error checking the credentials of the account %s", account.id
                )
            except SocialCredentialsError as error:
                _logger.warning(
                    "The credentials of the account %(account)s are no longer "
                    "valid: %(error)s",
                    {"account": account.id, "error": error},
                )
                account._flag_credentials_expired(str(error))
            except Exception:  # noqa: BLE001 - one account must not stop the rest
                _logger.exception(
                    "Error checking the credentials of the account %s", account.id
                )
        return False

    def _trigger_initial_sync(self):
        """Run the posts-statistics sync now so the dashboard is populated
        right after linking an account.

        Called on the accounts that were just associated: they are flagged so
        the cron only syncs them and not every account of every user.
        """
        if not self:
            return
        self.sudo().write({"pending_initial_sync": True})
        cron = self.env.ref(
            "social_media_base.initial_sync_account_job", raise_if_not_found=False
        )
        if cron:
            cron.sudo()._trigger()

    @api.model
    def _is_concurrency_error(self, error):
        """Whether the error is the one PostgreSQL raises on a lost race.

        :param error: the exception to look at.
        :rtype: bool
        """
        return (
            isinstance(error, psycopg2.OperationalError)
            and error.pgcode in PG_CONCURRENCY_ERRORS_TO_RETRY
        )

    def _reschedule_initial_sync(self):
        """Ask the cron to import these accounts again in a few minutes.

        The cron only runs once a month, and the retry Odoo does on a
        concurrency error covers the web requests, not the crons
        (:meth:`~odoo.addons.base.models.ir_cron.ir_cron._callback` only logs
        and rolls back): an account left pending because another transaction
        was writing its row would keep the dashboard waiting for an import
        nobody was going to run again.
        """
        if not self:
            return
        cron = self.env.ref(
            "social_media_base.initial_sync_account_job", raise_if_not_found=False
        )
        if not cron:
            return
        _logger.info(
            "The initial sync of the accounts %s is retried in %s minutes.",
            self.ids,
            INITIAL_SYNC_RETRY_DELAY_MINUTES,
        )
        cron.sudo()._trigger(
            at=fields.Datetime.now()
            + relativedelta(minutes=INITIAL_SYNC_RETRY_DELAY_MINUTES)
        )

    def _close_initial_sync(self, error=None):
        """Clear the pending flag and tell the user how the import went.

        The dashboard shows the account as syncing while the flag is set, so
        it is cleared whether the import worked or not, and the reason of a
        failure is left on the account: the bus notification of the connectors
        reaches nobody when the cron runs, and the user can import again with
        the *Update* button.

        :param error: the exception the import raised, if it did.
        """
        self.ensure_one()
        if error is not None:
            self._register_initial_sync_failure(error)
        self.pending_initial_sync = False
        self._notify_posts_updated()

    @api.model
    def _run_initial_sync(self):
        """Import the posts of the accounts that were just associated.

        Each account is synced in its own savepoint: a failure on one of them
        must not lose what the previous ones already imported.

        An account whose row another transaction wrote first is not fought
        over. Its flag is kept and the cron is asked to come back in a few
        minutes, because the write that lost the race is the whole import:
        clearing the flag would leave the dashboard announcing posts that were
        never brought in. Unlike a web request, a cron gets no retry of its
        own, so the concurrency error is handled here instead of raised.

        The cron record does not set a user, so the search needs ``sudo()``
        to reach the pending accounts of every responsible, like
        :meth:`_run_check_media_updates` does.
        """
        pending = self.sudo().search([("pending_initial_sync", "=", True)])
        postponed = self.browse()
        for account in pending:
            error = None
            try:
                with self.env.cr.savepoint():
                    account.update_posts_statistics()
            except Exception as sync_error:  # noqa: BLE001 - one account cannot stop the rest
                if self._is_concurrency_error(sync_error):
                    _logger.info(
                        "The initial sync of the account %s lost a race "
                        "against another update, it is retried later.",
                        account.id,
                    )
                    postponed |= account
                    continue
                _logger.exception(
                    "Error on the initial sync of the account %s", account.id
                )
                error = sync_error
            account._close_initial_sync(error)
        postponed._reschedule_initial_sync()

    def _register_initial_sync_failure(self, error):
        """Tell the responsible user that the first import did not go through.

        The flag is cleared whatever happens, so nothing on the dashboard
        recalls the failure afterwards, and the cron that runs the import has
        nobody connected to receive a bus notification: the note on the
        account is the only durable trace the user in charge can find.

        :param error: the exception the import raised.
        """
        self.ensure_one()
        self.message_post(
            body=_(
                "The posts of the account could not be imported: %(error)s. "
                "Press the Update button of the dashboard to import them "
                "again.",
                error=error,
            ),
            partner_ids=self.user_id.partner_id.ids,
        )

    def _notify_posts_updated(self):
        """Tell the responsible user that the posts of the account changed.

        The initial sync runs in a cron, so the dashboard the user is looking
        at knows nothing about it: this is what makes it reload itself. The
        message names the account because a user may be responsible for
        several of them.
        """
        for account in self:
            self.env["bus.bus"]._sendone(
                account.user_id.partner_id,
                "social_posts_updated",
                {
                    "account_id": account.id,
                    "message_type": "info",
                    "message": account._format_user_notification(
                        _("The posts of the account were updated."),
                        media=account.media_type or account.media_id.name,
                        account_name=account.name,
                        message_type="info",
                    ),
                },
            )

    def _need_update(self, need_update=True):
        """Flag pending updates on the dashboard of the responsible users.

        The check runs in a cron, whose user is not the one owning the
        account, so the message has to be addressed to each responsible user.
        """
        partners = self.user_id.partner_id or self.env.user.partner_id
        for partner in partners:
            self.env["bus.bus"]._sendone(
                partner,
                "social_need_update",
                {"need_update": need_update},
            )

    @api.model
    def _get_social_dashboard_url(self):
        """Return the URL of the Social Media dashboard.

        Used by the OAuth callbacks to land the user on the dashboard
        instead of the default app.
        """
        menu = self.env.ref(
            "social_media_base.social_dashboard_menu",
            raise_if_not_found=False,
        )
        if menu and menu.action:
            return f"/web#menu_id={menu.id}&action={menu.action.id}"
        return "/web"

    def _get_default_filter_date(self, start_date, end_date, time_date=False, months=1):
        start = start_date or (fields.Datetime.now() - relativedelta(months=months))
        end = end_date or fields.Datetime.now()
        if time_date:
            return generate_timestamps(date_start=start, date_end=end)
        return start, end

    def _map_chart_statistics(self, statistics_by_period, **values):
        """Format the statistics of one account for the chart view.

        :param statistics_by_period: statistics tuple by period key, as
            ``social_utils.get_chart_period_key`` builds them. Every series
            is read period by period, never by position: a period the social
            media has no bucket for is a zero, not a shift of the whole
            series.
        :param values: ``start_date``, ``end_date`` and ``freq`` of the
            range, plus the optional ``totals`` of the account, which are
            the figures of the whole account instead of the ones of the
            period.
        :rtype: list
        """
        data_chart = []
        if statistics_by_period and self.media_type:
            chart_periods = get_chart_periods(
                values.get("start_date"),
                values.get("end_date"),
                freq=values.get("freq", "W-MON"),
            )
            statistics_values = list(statistics_by_period.values())

            def map_chart_data(label, key_data=0):
                return {
                    "pointStyle": "circle",
                    "pointRadius": 10,
                    "pointHoverRadius": 15,
                    "label": label,
                    "data": [
                        statistics_by_period.get(key, EMPTY_CHART_STATISTICS)[key_data]
                        for key, _label in chart_periods
                    ],
                }

            def sum_statistics(*indexes):
                return sum(
                    sum(statistics[index] for index in indexes)
                    for statistics in statistics_values
                    if len(statistics) > max(indexes)
                )

            totals = values.get("totals") or {}
            data_chart.append(
                {
                    "id": self.id,
                    "name": f"[{self.media_type.upper()}] {self.name}",
                    "impressionCount": sum_statistics(5),
                    "commentCount": sum_statistics(2),
                    "reactionCount": sum_statistics(1, 3),
                    "impressionCountTotal": totals.get("impressionCount"),
                    "commentCountTotal": totals.get("commentCount"),
                    "reactionCountTotal": totals.get("reactionCount"),
                    "chartLabel": _("Statistics"),
                    "granularities": self._get_chart_granularities(),
                    "labels": [label for _key, label in chart_periods],
                    "datasets": [
                        map_chart_data(_("Clicks"), 0),
                        map_chart_data(_("Shares"), 3),
                        map_chart_data(_("Likes"), 1),
                        map_chart_data(_("Comments"), 2),
                        map_chart_data(_("Impressions"), 5),
                        map_chart_data(_("Engagement"), 4),
                    ],
                }
            )
        return data_chart
