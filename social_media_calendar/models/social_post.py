# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class SocialPost(models.Model):
    _inherit = "social.post"

    date_calendar = fields.Date(
        compute="_compute_date_calendar", store=True, index=True
    )
    color = fields.Integer(compute="_compute_color")

    @api.depends("state")
    def _compute_color(self):
        for post in self:
            if post.state == "planned":
                post.color = 2
            elif post.state == "publishing":
                post.color = 6
            elif post.state == "published":
                post.color = 10
            elif post.state == "cancelled":
                post.color = 0
            else:
                post.color = 4

    @api.depends("create_date", "send_post_date", "published_date")
    def _compute_date_calendar(self):
        for post in self:
            post.date_calendar = (
                post.published_date or post.send_post_date or post.create_date
            )

    def action_open_post(self):
        """Click-through from calendar event to the social.post form view."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "social.post",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }
