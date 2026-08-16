# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import itertools
import logging
from urllib.parse import quote

import psycopg2

from odoo import Command, _, fields, models
from odoo.exceptions import UserError
from odoo.service.model import PG_CONCURRENCY_ERRORS_TO_RETRY
from odoo.tools import plaintext2html

from odoo.addons.social_media_base.social_utils import convert_date_in_time

from ..social_linkedin_utils import (
    _IMAGE_MIMETYPES_LINKEDIN,
    _URL_FEED_UPDATE_LINKEDIN,
    _URN_IMAGE_LINKEDIN,
    _VIDEO_MIMETYPES_LINKEDIN,
)

_logger = logging.getLogger(__name__)


class SocialPostAccount(models.Model):
    """Publication, comments and statistics of a post on a LinkedIn account."""

    _inherit = "social.post.account"

    def _get_linkedin_image_urns(self, content):
        """Return the image URNs carried by the content of a post.

        :param content: The ``content`` of the post answered by the Posts API.
        :rtype: list
        """
        media_id = str(content.get("media", {}).get("id", ""))
        image_urns = [media_id] if media_id.startswith(_URN_IMAGE_LINKEDIN) else []
        image_urns += [
            str(image.get("id", ""))
            for image in content.get("multiImage", {}).get("images", [])
            if str(image.get("id", "")).startswith(_URN_IMAGE_LINKEDIN)
        ]
        return image_urns

    def _remove_assets_deleted(self, content):
        """Drop the images that are no longer on the LinkedIn post.

        The publication mirrors what is online, so an image deleted on
        LinkedIn has to leave the dashboard card too. Only the attachments
        named after a LinkedIn URN are considered, so anything attached by
        hand in Odoo is never touched.

        The relation is unlinked before deleting the attachment: the field
        is declared with ``ondelete="restrict"``, so the database refuses to
        delete a media that a publication still points at.

        :param content: The ``content`` of the post answered by the Posts API.
        :return: The removed attachments.
        """
        self.ensure_one()
        remote_urns = self._get_linkedin_image_urns(content)
        removed = self.image_ids.filtered(
            lambda image: (image.name or "").startswith(_URN_IMAGE_LINKEDIN)
            and image.name not in remote_urns
        )
        if removed:
            self.image_ids = [Command.unlink(image.id) for image in removed]
            removed.sudo().unlink()
        return removed

    def _get_assets_save(self, content, account=None):
        """Download the images of a post that are not stored yet.

        :param content: The ``content`` of the post answered by the Posts API.
        :param account: The account to ask LinkedIn with, needed when the post
            does not exist in Odoo yet.
        :return: The commands creating the missing attachments.
        :rtype: list
        """
        image_urns = self._get_linkedin_image_urns(content)
        medias_exist = self._get_medias_account(image_urns)
        image_urns = [urn for urn in image_urns if urn not in medias_exist]
        if not image_urns:
            return []
        account = account or self.account_id
        download_urls = account._get_linkedin_images_download_url(image_urns)
        commands = [
            self._map_medias_account(**{"name": urn, "url": download_urls[urn]})
            for urn in image_urns
            if download_urls.get(urn)
        ]
        return [command for command in commands if command]

    def _check_linkedin_post_format(self):
        """Check that the post matches what LinkedIn publishes.

        Unlike the checks that extension modules add through
        :meth:`_check_linkedin_publishable`, this one runs for every post.

        :raise UserError: When the post cannot be published as it is.
        """
        self.ensure_one()
        if len(self.post_id.video_ids) > 1:
            raise UserError(
                _(
                    "LinkedIn publishes a single video per post, so this post "
                    "carrying %(videos)s videos cannot be published. Leave one "
                    "video or create a separate post for each of them.",
                    videos=len(self.post_id.video_ids),
                )
            )
        for video in self.post_id.video_ids:
            if (video.mimetype or "").lower() not in _VIDEO_MIMETYPES_LINKEDIN:
                raise UserError(
                    _(
                        "LinkedIn only publishes MP4 videos, so %(name)s "
                        "(%(mimetype)s) cannot be published. Convert it to MP4 "
                        "or remove it from the post.",
                        name=video.name,
                        mimetype=video.mimetype,
                    )
                )
        if self.post_id.video_ids:
            # A post carrying a video is published without its images, so
            # their format decides nothing. Checking them would fail a post
            # LinkedIn publishes just fine.
            return
        for image in self.post_id.image_ids:
            if (image.mimetype or "").lower() not in _IMAGE_MIMETYPES_LINKEDIN:
                raise UserError(
                    _(
                        "LinkedIn only publishes JPG, PNG and GIF images, so "
                        "%(name)s (%(mimetype)s) cannot be published. Convert "
                        "it or remove it from the post.",
                        name=image.name,
                        mimetype=image.mimetype,
                    )
                )

    def _check_linkedin_publishable(self):
        """Validate this publication before sending it to LinkedIn.

        Extension point: modules adding LinkedIn features override it to add
        their own pre-publish checks. It runs inside :meth:`_publish_guard`,
        so raising here fails this publication only.
        """
        self.ensure_one()
        self._check_linkedin_post_format()

    def _linkedin_published_values(self, post_entity):
        """Return the extra values to store once the post is online.

        Extension point. It runs after ``remote_ref`` has been written and
        inside :meth:`_publish_guard`, so an implementation must never let an
        error escape: rolling back here would drop the reference of a post
        that already exists on LinkedIn.
        """
        self.ensure_one()
        return {}

    def _action_post(self, post_id):
        res = super()._action_post(post_id)
        if any(account.media_type == "linkedin" for account in post_id.account_ids):
            post_accounts = post_id._filter_by_media_types(["linkedin"])
            images, videos = post_id._medias_for_publication()
            for post_account in post_accounts:
                with post_account._publish_guard():
                    post_account._check_linkedin_publishable()
                    (
                        post_entity,
                        image_urns,
                    ) = post_account._publish_attempt(
                        post_account.account_id._linkedin_create_post,
                        message=post_account.message,
                        image_ids=images,
                        video_ids=videos,
                    )
                    if post_entity:
                        post_account.write(
                            {
                                "remote_ref": post_entity,
                                "post_account_url": (
                                    f"{_URL_FEED_UPDATE_LINKEDIN}{post_entity}"
                                ),
                                "has_video": bool(videos),
                                "state": "posted",
                                "published_date": fields.Datetime.now(),
                                "failed_description": False,
                            }
                        )
                        post_account._linkedin_enrich_published_post(
                            post_entity, image_urns, images
                        )
                    else:
                        post_account.write(
                            {
                                "state": "failed",
                                "failed_description": plaintext2html(
                                    _(
                                        "The account has no LinkedIn access "
                                        "token. Update the account to "
                                        "authorize it again."
                                    )
                                ),
                            }
                        )
                        post_account.account_id._flag_credentials_expired(
                            _("the account has no access token")
                        )
        return res

    def _linkedin_enrich_published_post(
        self, post_entity, image_urns=None, images=None
    ):
        """Complete a publication that is already online on LinkedIn.

        Downloading the images is a best-effort step, and so are the extra
        values that extension modules add through
        :meth:`_linkedin_published_values`. The post exists on the social
        media, so a failure here must never revert its remote reference:
        errors are logged and reported on the post instead of being raised.

        LinkedIn does not always expose the images of a post right after
        creating it, so when the download brings nothing back the local
        attachments are copied instead: the dashboard card is never empty and
        the media does not have to wait for the next synchronization.

        :param post_entity: URN of the post created on LinkedIn.
        :param image_urns: URNs of the images attached to the post, in the
            same order as the local attachments that produced them.
        :param images: The attachments that produced ``image_urns``. They are
            received instead of read again so that both lists pair up by
            construction and not because two reads happen to agree on the
            order. Defaults to the images of the post.
        """
        self.ensure_one()
        values = {}
        attach_images = []
        try:
            ugc_post = self.account_id._get_posts(
                **{
                    "params_fields": ["ids"],
                    "params_values": {"ids": [post_entity]},
                }
            )
            if ugc_post and ugc_post[0].get("content", False):
                attach_images = self._get_assets_save(ugc_post[0].get("content", {}))
        except psycopg2.OperationalError as error:
            if error.pgcode in PG_CONCURRENCY_ERRORS_TO_RETRY:
                raise
            _logger.exception(
                "Error retrieving the medias of the LinkedIn post %s", post_entity
            )
        except Exception:  # noqa: BLE001 - the post is already published
            _logger.exception(
                "Error retrieving the medias of the LinkedIn post %s", post_entity
            )
        if not attach_images and image_urns:
            if images is None:
                images = self._sorted_medias(self.post_id.image_ids)
            attach_images = self._copy_medias_account(images, image_urns)
        if attach_images:
            values["image_ids"] = attach_images
        values.update(self._linkedin_published_values(post_entity))
        if values:
            self.write(values)

    def action_like_post(self, author_urn=None):
        res = super().action_like_post(author_urn)
        if self.media_id.media_type == "linkedin":
            like_ok = False
            response = self.account_id._request_linkedin(
                method="POST",
                endpoint="/reactions",
                headers=self.account_id.media_id._get_linkedin_headers(
                    self.account_id.sudo().access_token, content_type="application/json"
                ),
                token=True,
                return_json=False,
                linkedin_v2=True,
                params_fields=["actor"],
                params_values={"actor": author_urn},
                json_data={
                    "root": self.remote_ref,
                    "reactionType": "LIKE",
                },
            )
            message_like = ""
            if response.status_code == 201:
                like_ok = True
            elif response.status_code == 409:
                message_like = _("You have already reacted to this post.")
            elif response.status_code == 404:
                message_like = _("The post does not exist or has been deleted.")
            else:
                message_like = self.account_id._linkedin_error_message(response)
            return {"success": like_ok, "message": message_like}
        return res

    def action_like_comment(self, comment_id=None, author_urn=None):
        super().action_like_comment(comment_id, author_urn)
        return {"success": False, "message": ""}

    def get_comments(self):
        data = super().get_comments()
        comments = []
        if self.account_id.media_type == "linkedin" and self.remote_ref:
            response = self.account_id._request_linkedin(
                method="GET",
                endpoint=f"/socialActions/{quote(self.remote_ref)}/comments",
                headers=self.account_id.media_id._get_linkedin_headers(
                    self.account_id.sudo().access_token
                ),
                token=True,
                return_json=False,
                linkedin_v2=True,
            )
            if response.status_code == 200:
                response_comments = response.json().get("elements", [])
                comments = [
                    {
                        "id": comment.get("id"),
                        "text": comment.get("message", {}).get("text"),
                        "actor": comment.get("lastModified", {}).get("actor", {}),
                        "published_time": convert_date_in_time(
                            milliseconds=comment.get("lastModified", {}).get("time", 0),
                            timezone=self.env.user.tz,
                        ),
                        "images_url": [
                            val.get("url", {}) for val in comment.get("content", {})
                        ],
                    }
                    for comment in response_comments
                ]
            else:
                return_message = _(
                    "The comments could not be read from LinkedIn: %(error)s",
                    error=self.account_id._linkedin_error_message(response),
                )
                _logger.error(
                    "Error getting the comments of LinkedIn post %s: %s",
                    self.remote_ref,
                    response.status_code,
                )
                return {
                    "success": False,
                    "message": return_message,
                }
        return {
            "success": True,
            "data": list(itertools.chain(data.get("data", []), comments)),
        }

    def _create_linkedin_comment(self, post_data):
        if self.account_id.media_type == "linkedin":
            json_data = {
                "actor": self.account_id.remote_ref,
                "message": {"text": post_data.get("body", "")},
                "object": self.remote_ref,
            }
            response = self.account_id._request_linkedin(
                method="POST",
                endpoint=f"/socialActions/{quote(self.remote_ref)}/comments",
                headers=self.account_id.media_id._get_linkedin_headers(
                    self.account_id.sudo().access_token
                ),
                json_data=json_data,
                token=True,
                return_json=False,
                linkedin_v2=True,
            )
            if response.status_code != 201:
                return_message = _(
                    "The comment could not be published on LinkedIn: %(error)s",
                    error=self.account_id._linkedin_error_message(response),
                )
                _logger.error(
                    "Error replying to LinkedIn post %s: %s",
                    self.remote_ref,
                    response.status_code,
                )
                return {
                    "success": False,
                    "message": return_message,
                }
        return {
            "success": True,
        }

    def create_comment(self, post_data, context=None):
        if self.account_id.media_type == "linkedin":
            return self._create_linkedin_comment(post_data)
        else:
            return super().create_comment(post_data, context)

    def delete_linkedin_comment(self, comment_id, actor_urn):
        if self.account_id.media_type == "linkedin":
            response = self.account_id._request_linkedin(
                method="DELETE",
                endpoint=f"/socialActions/{quote(self.remote_ref)}/comments/{quote(comment_id)}",
                headers=self.account_id.media_id._get_linkedin_headers(
                    self.account_id.sudo().access_token
                ),
                params_fields=["actor"],
                params_values={"actor": actor_urn},
                token=True,
                return_json=False,
                linkedin_v2=True,
            )
            if response.status_code != 204:
                return {
                    "success": False,
                    "message": _(
                        "An error occurred while deleting the comment or it "
                        "no longer exists, please try again later."
                    ),
                }
        return {
            "success": True,
        }

    def _check_remote_post_exists(self):
        """Read the post on LinkedIn to know whether it is still online.

        Only a ``404`` is treated as a deletion. Any other answer means
        LinkedIn could not be asked, not that the publication is gone: a
        ``403`` is a lost page role, a ``429`` a throttled application, and
        acting on them would mark a live publication as deleted.
        """
        if self.account_id.media_type != "linkedin" or not self.remote_ref:
            return super()._check_remote_post_exists()
        try:
            response = self.account_id._request_linkedin(
                endpoint=f"/posts/{quote(self.remote_ref)}",
                headers=self.account_id.media_id._get_linkedin_headers(
                    self.account_id.sudo().access_token
                ),
                return_json=False,
            )
        except Exception:  # noqa: BLE001 - unreachable is not deleted
            _logger.exception(
                "Error checking the LinkedIn post %s, it is left untouched",
                self.remote_ref,
            )
            return True
        if response.status_code == 404:
            self._register_remote_post_gone()
            return False
        if response.status_code != 200:
            _logger.warning(
                "LinkedIn answered %(code)s while checking the post %(post)s, "
                "it is left untouched: %(error)s",
                {
                    "code": response.status_code,
                    "post": self.remote_ref,
                    "error": self.account_id._linkedin_error_message(response),
                },
            )
        return True

    def _delete_post_account(self):
        if self.media_id.media_type == "linkedin" and self.remote_ref:
            self.account_id.with_context(not_notify=True).validate_access_token()
            delete_post = self.account_id._request_linkedin(
                method="DELETE",
                endpoint=f"/posts/{quote(self.remote_ref)}",
                headers=self.media_id._get_linkedin_headers(
                    self.account_id.sudo().access_token
                ),
                return_json=False,
            )
            if delete_post.status_code != 204:
                error_message = self.account_id._linkedin_error_message(
                    delete_post
                ) or _("The post could not be deleted, please try again later.")
                raise UserError(
                    _("Error deleting LinkedIn post: %(error)s", error=error_message)
                )
        return super()._delete_post_account()
