# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import itertools

from odoo import _, api, models

from ..social_linkedin_utils import (
    _IMAGE_MIMETYPES_LINKEDIN,
    _VIDEO_MIMETYPES_LINKEDIN,
)


class SocialPost(models.Model):
    """LinkedIn specific constraints on the posts to publish."""

    _inherit = "social.post"

    def _default_account_ids(self):
        """Preselect the LinkedIn accounts of the active company.

        The company is filtered in the domain on purpose: the record rule of
        ``social.account`` matches ``company_ids``, the companies the user is
        allowed to see, so without this an account of another activated
        company would be preselected as well.
        """
        res = super()._default_account_ids()
        account_ids = self.env["social.account"].search(
            [
                ("media_type", "=", "linkedin"),
                "|",
                ("company_id", "=", False),
                ("company_id", "=", self.env.company.id),
            ]
        )
        if account_ids:
            return list(itertools.chain(account_ids.ids, res))
        return res

    @api.depends("account_ids", "image_ids", "video_ids")
    def _compute_message_info(self):
        res = super()._compute_message_info()
        for post in self:
            if "linkedin" not in post.account_ids.mapped("media_type"):
                continue
            for message_info in post._linkedin_message_info():
                post.message_info = (
                    f"{post.message_info}\n{message_info}"
                    if post.message_info
                    else message_info
                )
        return res

    def _render_values_preview(self, media):
        """Drop the images LinkedIn will not publish from its preview.

        The Posts API holds a single media entry, so a post carrying a video
        is published without its images (see
        :meth:`~odoo.addons.social_media_linkedin.models.social_account.
        SocialAccount._linkedin_create_post`). Showing them would preview
        exactly what does not reach LinkedIn. Only the LinkedIn preview is
        touched: another media of the same post may well publish them.
        """
        values = super()._render_values_preview(media)
        if media.media_type == "linkedin" and self.video_ids:
            values = dict(values, image_ids=self.env["ir.attachment"])
        return values

    def _linkedin_message_info(self):
        """Return the LinkedIn warnings to show on the post.

        :rtype: list
        """
        self.ensure_one()
        messages = []
        if len(self.video_ids) > 1:
            messages.append(
                _(
                    "LinkedIn publishes a single video per post. Leave one "
                    "video or create a separate post for each of them."
                )
            )
        if self.image_ids and self.video_ids:
            messages.append(
                _(
                    "You have selected images and videos for this post. "
                    "However, the social media LinkedIn does not allow "
                    "combining both types of content in the same post. "
                    "Therefore, only the video will be published. If you wish "
                    "to publish the images, please remove the video from this "
                    "post or create a separate post."
                )
            )
        # The formats are refused when publishing; warning here saves the user
        # a publication that is bound to fail. Only the medias LinkedIn really
        # takes are looked at: with a video the images are not published.
        wrong_videos = self.video_ids.filtered(
            lambda video: (video.mimetype or "").lower()
            not in _VIDEO_MIMETYPES_LINKEDIN
        )
        if wrong_videos:
            messages.append(
                _(
                    "LinkedIn only publishes MP4 videos, so %(names)s will not "
                    "be published.",
                    names=", ".join(wrong_videos.mapped("name")),
                )
            )
        wrong_images = (
            self.env["ir.attachment"]
            if self.video_ids
            else self.image_ids.filtered(
                lambda image: (image.mimetype or "").lower()
                not in _IMAGE_MIMETYPES_LINKEDIN
            )
        )
        if wrong_images:
            messages.append(
                _(
                    "LinkedIn only publishes JPG, PNG and GIF images, so "
                    "%(names)s will not be published.",
                    names=", ".join(wrong_images.mapped("name")),
                )
            )
        return messages
