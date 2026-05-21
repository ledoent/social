# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import random
import string
from datetime import date, datetime, timedelta

from werkzeug.urls import url_encode, url_join

from odoo import fields, models
from odoo.tools import hmac

from ..social_linkedin_utils import (
    _SCOPE_LINKEDIN_DEFAULT,
    _URL_AUTH_V2_LINKEDIN,
)


class WizardSocialAccount(models.TransientModel):
    _inherit = "wizard.social.account"

    linkedin_client = fields.Char(string="Client ID")
    linkedin_secret = fields.Char(string="Client Secret")
    linkedin_scopes = fields.Char(
        string="OAuth Scopes",
        default=lambda self: " ".join(_SCOPE_LINKEDIN_DEFAULT),
        help=(
            "Space-separated LinkedIn OAuth scopes to request. Defaults "
            "cover Sign In + Marketing Developer Platform org-posting. "
            "Add more only when the matching LinkedIn Product is approved "
            "on your dev app — extra unapproved scopes cause OAuth to "
            "fail with 'Bummer, something went wrong'."
        ),
    )
    csrf_state_token = fields.Char()

    def _get_url_redirect(self):
        if self.media_type == "linkedin":
            return url_join(self.get_base_url(), "/linkedin/callback")
        else:
            return super()._get_url_redirect()

    def _generate_code(self, length=10):
        caracteres = string.ascii_letters + string.digits
        return "".join(random.choices(caracteres, k=length))

    def _get_csrf_state_token(self):
        if self.media_type == "linkedin":
            return hmac(
                self.env(su=True),
                f"{self.media_type}-account-{self._generate_code()}-csrf-token",
                self.media_id.id,
            )
        else:
            return super()._get_csrf_state_token()

    def _get_linkedin_scopes(self):
        """Return the scope string requested in the OAuth authorize call.

        Priority: wizard's `linkedin_scopes` field (so the user can edit
        before clicking Connect) → linked account's stored scopes
        (re-auth flow) → module default. Always emit a space-separated
        token list with duplicates removed and preserving order.
        """
        self.ensure_one()
        raw = (
            self.linkedin_scopes
            or (self.account_id and self.account_id.linkedin_scopes)
            or " ".join(_SCOPE_LINKEDIN_DEFAULT)
        )
        seen, ordered = set(), []
        for tok in raw.split():
            if tok and tok not in seen:
                seen.add(tok)
                ordered.append(tok)
        return " ".join(ordered)

    def _action_add_account(self):
        result = super()._action_add_account()
        context = dict(self.env.context)
        if self.media_type == "linkedin":
            params = {
                "response_type": "code",
                "client_id": self.linkedin_client,
                "redirect_uri": self._get_url_redirect(),
                "state": self.csrf_state_token,
                "scope": self._get_linkedin_scopes(),
            }
            url_aut = f"{_URL_AUTH_V2_LINKEDIN}/authorization?{url_encode(params)}"
            if not context.get("only_url", False):
                return {
                    "type": "ir.actions.act_url",
                    "url": url_aut,
                    "target": "self",
                }
            return url_aut
        else:
            return result

    def _action_valid_add_account(self):
        result = super()._action_valid_add_account()
        if self.media_type == "linkedin":
            self.env["social.account"].sudo().unique_account(
                self.linkedin_client, self.linkedin_secret
            )
        return result

    def _update_account(self):
        if self.media_type == "linkedin":
            if self.update_keys or self.update_token:
                if self.update_keys:
                    self.account_id.write(
                        {
                            "linkedin_client_id": self.linkedin_client,
                            "linkedin_secret": self.linkedin_secret,
                        }
                    )
                    return {
                        "type": "ir.actions.act_url",
                        "url": self.with_context(only_url=True)._action_add_account(),
                        "target": "self",
                    }
                if self.update_token:
                    token = self.account_id._refresh_token()
                    self.account_id.write(
                        {
                            "access_token": token.get("access_token", False),
                            "refresh_access_token": token.get("refresh_token", False),
                            "expire_access_token_date": date.today()
                            + timedelta(days=token.get("expires_in", 0) / 86400),
                            "refresh_token_expires_in": date.today()
                            + timedelta(
                                days=token.get("refresh_token_expires_in", 0) / 86400
                            ),
                        }
                    )
                    # Notifying the user
                    if not self.env.context.get("not_notify", False):
                        self._notify_user_client(
                            notif_type="social_form_success",
                            notif_message=self.env._(
                                "The token was updated successfully"
                            ),
                            media="linkedin",
                            account_name=self.account_id.name,
                        )
            else:
                organizations = self.account_id.get_account_linkedin(
                    self.account_id.access_token
                )

                for organization in organizations:
                    self.account_id.write(
                        {
                            "name": organization.get("localizedName", False),
                            "username": organization.get("vanityName", False),
                            "image_1920": organization.get("logo", False),
                        }
                    )
            self.account_id.write(
                {
                    "last_update_account": datetime.now(),
                }
            )
        else:
            return super()._update_account()
