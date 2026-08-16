# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo import api, fields, models

# Sort key of a media that has no database identifier yet, so that it is
# ordered after the stored ones instead of being compared with them.
UNSAVED_MEDIA_ORDER = float("inf")


class SocialPostMixin(models.AbstractModel):
    _name = "social.post.mixin"
    _description = "Social Media Post Mixin"

    image_urls = fields.Char(compute="_compute_image_urls", store=True)

    @staticmethod
    def _sorted_medias(attachments):
        """Return the attachments in the order the user added them.

        ``ir.attachment`` is ordered by ``id desc`` and a many2many is read
        with the order of its comodel, so a record re-read from database
        returns the attachments newest first. Everything that publishes or
        draws them goes through here, so what is previewed and what is
        published never disagree.

        A record that is not stored yet carries a ``NewId``, which cannot be
        compared with anything: those keep the order they were added in and
        stay last, which is where the user just put them. This happens on
        every onchange, before the post is saved.

        :param attachments: the ``ir.attachment`` recordset to order.
        :rtype: odoo.models.Model
        """
        return attachments.sorted(
            lambda attachment: attachment._origin.id or UNSAVED_MEDIA_ORDER
        )

    @api.depends(lambda self: ["image_ids", "image_ids.checksum"])
    def _compute_image_urls(self):
        """Build the image URLs of the post.

        The attachment checksum is embedded in the URL so that Odoo serves the
        image as immutable and the browser caches it instead of revalidating it
        on every page load. A new checksum yields a new URL, so an updated
        image is fetched again without any cache busting on the client side.

        The dependency is a lambda because ``image_ids`` is declared by the
        models inheriting this mixin, not by the mixin itself.

        The images are ordered by :meth:`_sorted_medias`: without it the
        gallery would draw them newest first, in another order than the one
        they are published in.
        """
        for post in self:
            post.image_urls = json.dumps(
                [
                    f"/web/image/{image.id}-{image.checksum}"
                    if image.checksum
                    else f"/web/image/{image.id}"
                    for image in self._sorted_medias(post.image_ids)
                ]
            )
