# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from markupsafe import Markup, escape

from odoo import api, fields, models

from ..social_utils import get_brand_color

# Pre-flight copy per platform. Channel modules can extend `_preflight_copy()`
# to swap any value or to add a new platform without touching the base.
# Brand color is sourced separately from social_utils.BRAND_COLORS so the
# wizard and the social.account kanban stay in sync from a single dict.
#
# `_PREFLIGHT_FALLBACK` is rendered when a wizard opens for a media_type
# without a registered entry — neutral copy so the user isn't shown
# LinkedIn branding for an unrelated platform.
_PREFLIGHT_FALLBACK = {
    "logo": "",
    "headline": "Connect your account",
    "subhead": (
        "Authorize this Odoo instance to draft and publish posts on your " "behalf."
    ),
    "time_estimate": (
        "Setup time depends on the platform — check its developer "
        "documentation for the OAuth steps."
    ),
    "permissions_grant": [
        "Read post statistics",
        "Draft posts",
        "Publish posts you've scheduled",
    ],
    "permissions_exclude": [
        "Direct messages",
        "Personal profile activity",
    ],
    "devportal_url": "",
}

_PREFLIGHT = {
    "linkedin": {
        "logo": "/social_media_base/static/src/img/linkedin-mark.svg",
        "headline": "Connect LinkedIn",
        "subhead": "Post drafts and scheduled posts to your organization page.",
        "time_estimate": (
            "About 5 minutes — 10 if you don't already have a LinkedIn "
            "Developer app."
        ),
        "permissions_grant": [
            "Read post statistics on your page",
            "Draft posts on your behalf",
            "Publish posts you've scheduled",
        ],
        "permissions_exclude": [
            "Comments and replies",
            "Direct messages",
            "Your personal profile activity",
        ],
        "devportal_url": "https://www.linkedin.com/developers/apps/new",
    },
    "facebook": {
        "logo": "/social_media_base/static/src/img/facebook-mark.svg",
        "headline": "Connect Facebook",
        "subhead": "Post drafts and scheduled posts to your Facebook page.",
        "time_estimate": (
            "About 7 minutes — 15 if you haven't created a Meta Business app " "yet."
        ),
        "permissions_grant": [
            "Read post statistics on your page",
            "Draft posts to your page",
            "Publish posts you've scheduled",
            "Read leadgen submissions",
        ],
        "permissions_exclude": [
            "Personal timeline posts",
            "Direct messages",
            "Friends and contacts",
        ],
        "devportal_url": "https://developers.facebook.com/apps/create/",
    },
}


class WizardSocialAccount(models.TransientModel):
    _name = "wizard.social.account"
    _inherit = ["social.media.base.mixin"]
    _description = "Associate Social Media Account"

    account_id = fields.Many2one("social.account")
    media_id = fields.Many2one("social.media", required=True)
    media_type = fields.Selection(
        string="Media Type",
        related="media_id.media_type",
    )
    update_keys = fields.Boolean(
        default=False, help="Only enable this field if your credentials have changed"
    )
    update_token = fields.Boolean(default=False, help="Update token")
    image = fields.Binary(related="media_id.image")

    # ── Pre-flight state machine ──────────────────────────────────────────
    # `preflight` shows the branded introduction + scope disclosure.
    # `credentials` reveals the platform credential fields (the original
    # form layout). Existing flows that pass `social_update_account=True`
    # in context skip pre-flight and land directly on the update form.
    step = fields.Selection(
        [("preflight", "Pre-flight"), ("credentials", "Credentials")],
        default="preflight",
        required=True,
    )
    preflight_html = fields.Html(
        compute="_compute_preflight_html",
        sanitize=False,
        readonly=True,
    )
    preflight_has_devportal = fields.Boolean(
        compute="_compute_preflight_has_devportal",
        help=(
            "True when the current media_type has a registered developer "
            "portal URL. Hides the 'Show me how to make one' button for "
            "fallback / unsupported platforms where we don't have a "
            "specific link to send the user to."
        ),
    )

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        # Skip pre-flight for update flows — they already have an account.
        if self.env.context.get("social_update_account"):
            vals["step"] = "credentials"
        return vals

    def _preflight_copy(self):
        """Return the pre-flight copy dict for this wizard's media_type.

        Channel modules override this to swap copy or to register a new
        platform. When the media_type has no registered entry, the neutral
        `_PREFLIGHT_FALLBACK` block is returned — the layout still renders
        but doesn't misrepresent the connection as a known platform.
        Brand color is injected from social_utils so wizard and kanban
        share one source of truth.
        """
        self.ensure_one()
        base = _PREFLIGHT.get(self.media_type or "", _PREFLIGHT_FALLBACK)
        return {**base, "brand_color": get_brand_color(self.media_type)}

    @api.depends("media_type")
    def _compute_preflight_html(self):
        for wizard in self:
            wizard.preflight_html = wizard._render_preflight_html()

    @api.depends("media_type")
    def _compute_preflight_has_devportal(self):
        for wizard in self:
            wizard.preflight_has_devportal = bool(
                wizard._preflight_copy().get("devportal_url")
            )

    def _render_preflight_html(self):
        """Return the full pre-flight panel as Markup-safe HTML.

        Rendering happens in Python rather than the form view because
        the brand color is per-platform inline CSS and the disclosure
        bullets are derived lists — both awkward to express in Odoo's
        view DSL.
        """
        self.ensure_one()
        copy = self._preflight_copy()

        def _bullet(item):
            return f"<li>{escape(self.env._(item))}</li>"

        grant_items = "".join(_bullet(i) for i in copy["permissions_grant"])
        exclude_items = "".join(_bullet(i) for i in copy["permissions_exclude"])
        logo_html = (
            f'<img src="{escape(copy["logo"])}" alt="" '
            'class="o-social-preflight-logo"/>'
            if copy.get("logo")
            else ""
        )
        return Markup(
            """
            <div class="o-social-preflight">
              <div class="o-social-preflight-band" style="background: {brand};">
                {logo_html}
                <div class="o-social-preflight-heading">
                  <h1>{headline}</h1>
                  <p>{subhead}</p>
                </div>
              </div>
              <div class="o-social-preflight-body">
                <div class="o-social-preflight-time">
                  <i class="fa fa-clock-o"></i>
                  <span>{time_estimate}</span>
                </div>
                <div class="o-social-preflight-disclosure">
                  <div class="o-social-preflight-card o-social-preflight-card--grant">
                    <h3>{grant_heading}</h3>
                    <ul class="o-social-preflight-list">{grant_items}</ul>
                  </div>
                  <div class="o-social-preflight-card o-social-preflight-card--exclude">
                    <h3>{exclude_heading}</h3>
                    <ul class="o-social-preflight-list">{exclude_items}</ul>
                  </div>
                </div>
              </div>
            </div>
            """.format(
                brand=escape(copy["brand_color"]),
                logo_html=logo_html,
                headline=escape(self.env._(copy["headline"])),
                subhead=escape(self.env._(copy["subhead"])),
                time_estimate=escape(self.env._(copy["time_estimate"])),
                grant_heading=escape(self.env._("We'll do")),
                exclude_heading=escape(self.env._("We won't touch")),
                grant_items=grant_items,
                exclude_items=exclude_items,
            )
        )

    # ── Pre-flight transitions ────────────────────────────────────────────
    def action_show_credentials(self):
        """Advance from pre-flight to the credentials entry step.

        Re-opens the wizard at the same record so the form re-renders
        with the credentials block visible and the pre-flight hidden.
        """
        self.ensure_one()
        self.step = "credentials"
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": self.env.context,
        }

    def action_open_devportal(self):
        """Open the platform developer portal in a new tab so the user
        can create or grab credentials without losing wizard state.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": self._preflight_copy()["devportal_url"],
            "target": "new",
        }

    # ── Existing OAuth glue (unchanged) ───────────────────────────────────
    def _get_csrf_state_token(self):
        """
        This method must be canceled if it is needed to exchange information
        during the verification and authorization process of a social media.
        """
        pass

    def _compute_csrf_state_token(self):
        """
        Generates a token state
        """
        for media in self:
            media.csrf_state_token = media._get_csrf_state_token()

    def _get_url_redirect(self):
        pass

    def _action_add_account(self):
        """
        Social media modules that inherit from this one should
        override this method as needed; the method is intended
        to redirect to the social network authorization.
        Call the method that generates a token state for use in the
        exchange of credentials and access token
        """
        pass

    def _action_valid_add_account(self):
        """
        It allows for validation before requesting access to the social network.
        """
        return True

    def action_associate_social_account(self):
        """
        This method links the account to the necessary data.
        """
        self._action_valid_add_account()
        return self._action_add_account()

    def _update_account(self):
        pass

    def update_account(self):
        return self._update_account()
