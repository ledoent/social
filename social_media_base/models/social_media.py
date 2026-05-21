# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

from ..social_utils import get_brand_color


class SocialMedia(models.Model):
    _name = "social.media"
    _inherit = "social.media.base.mixin"
    _description = "Social Media"

    """
        This model defines social networks.
    """

    name = fields.Char()
    description = fields.Text()
    media_type = fields.Selection(
        selection=[("other_social", "Other social")],
        readonly=True,
    )
    image = fields.Binary()
    brand_color = fields.Char(
        compute="_compute_brand_color",
        help=(
            "Hex brand color for status board tinting + pre-flight wizard. "
            "Sourced from social_utils.BRAND_COLORS so the value is "
            "consistent across the kanban band and the connect wizard."
        ),
    )

    @api.depends("media_type")
    def _compute_brand_color(self):
        for media in self:
            media.brand_color = get_brand_color(media.media_type)

    def open_action_account(self):
        """
        Show wizard for creating a new social media account.
        Override in platform-specific modules (social_media_facebook, etc.).
        """
        return False
