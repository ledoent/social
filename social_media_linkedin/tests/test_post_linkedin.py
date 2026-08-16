# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
from unittest.mock import MagicMock, patch

from odoo import Command
from odoo.exceptions import UserError
from odoo.tools import mute_logger

from odoo.addons.social_media_base.exceptions import SocialCredentialsError
from odoo.addons.social_media_base.tests.test_social_common import (
    PATCH_POST_ACCOUNT,
)
from odoo.addons.social_media_linkedin.tests.test_common_linkedin import (
    PATCH_ACCOUNT_LINKEDIN,
    PATCH_POST_ACCOUNT_LINKEDIN,
    TestSocialCommonLinkedin,
)

LOGGER_POST_ACCOUNT_LINKEDIN = (
    "odoo.addons.social_media_linkedin.models.social_post_account"
)
LOGGER_POST_ACCOUNT_BASE = "odoo.addons.social_media_base.models.social_post_account"


class TestSocialPostLinkedin(TestSocialCommonLinkedin):
    @patch("odoo.addons.social_media_base.models.social_post_account.requests.get")
    def test_get_assets_save(self, mock_get):
        """Only the images that are not stored yet are downloaded."""
        fake_content = b"fake image data"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = fake_content
        mock_get.return_value = mock_response
        self.create_attachment(attach_name="urn:li:image:exists")
        content = {
            "multiImage": {
                "images": [
                    {"id": "urn:li:image:new"},
                    {"id": "urn:li:image:exists"},
                ]
            }
        }
        images_response = MagicMock()
        images_response.status_code = 200
        images_response.json.return_value = {
            "results": {"urn:li:image:new": {"downloadUrl": "https://fake-url/new.jpg"}}
        }
        with patch.object(
            type(self.SocialAccountLinkedin),
            "_request_linkedin",
            return_value=images_response,
        ) as mock_request_linkedin:
            attachments = self.SocialPostAccountLinkedin._get_assets_save(content)
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0][2]["name"], "urn:li:image:new")
        self.assertEqual(attachments[0][2]["datas"], base64.b64encode(fake_content))
        self.assertEqual(
            mock_request_linkedin.call_args.kwargs["params_values"]["ids"],
            ["urn:li:image:new"],
        )

    def test_remove_assets_deleted_drops_the_images_gone_from_linkedin(self):
        """An image deleted on LinkedIn leaves the publication as well."""
        kept = self.create_attachment(attach_name="urn:li:image:kept")
        gone = self.create_attachment(attach_name="urn:li:image:gone")
        self.SocialPostAccountLinkedin.write(
            {"image_ids": [Command.set((kept | gone).ids)]}
        )
        content = {"multiImage": {"images": [{"id": "urn:li:image:kept"}]}}
        removed = self.SocialPostAccountLinkedin._remove_assets_deleted(content)
        self.assertEqual(self.SocialPostAccountLinkedin.image_ids, kept)
        self.assertEqual(len(removed), 1)
        self.assertFalse(gone.exists())

    def test_remove_assets_deleted_keeps_the_manual_attachments(self):
        """Only the medias named after a LinkedIn URN are managed here."""
        manual = self.create_attachment(attach_name="holidays.jpg")
        self.SocialPostAccountLinkedin.write({"image_ids": [Command.set(manual.ids)]})
        self.assertFalse(self.SocialPostAccountLinkedin._remove_assets_deleted({}))
        self.assertEqual(self.SocialPostAccountLinkedin.image_ids, manual)
        self.assertTrue(manual.exists())

    def test_remove_assets_deleted_drops_everything_without_remote_media(self):
        stored = self.create_attachment(attach_name="urn:li:image:stored")
        self.SocialPostAccountLinkedin.write({"image_ids": [Command.set(stored.ids)]})
        self.SocialPostAccountLinkedin._remove_assets_deleted({})
        self.assertFalse(self.SocialPostAccountLinkedin.image_ids)
        self.assertFalse(stored.exists())

    def test_remove_assets_deleted_keeps_the_images_still_online(self):
        stored = self.create_attachment(attach_name="urn:li:image:stored")
        self.SocialPostAccountLinkedin.write({"image_ids": [Command.set(stored.ids)]})
        content = {"media": {"id": "urn:li:image:stored"}}
        self.assertFalse(self.SocialPostAccountLinkedin._remove_assets_deleted(content))
        self.assertEqual(self.SocialPostAccountLinkedin.image_ids, stored)

    def test_get_assets_save_single_image(self):
        """The image of a post with a single media is resolved as well."""
        content = {"media": {"id": "urn:li:image:single"}}
        with patch.object(
            type(self.SocialAccountLinkedin),
            "_get_linkedin_images_download_url",
            return_value={},
        ) as mock_download_url:
            self.assertEqual(
                self.SocialPostAccountLinkedin._get_assets_save(content), []
            )
        mock_download_url.assert_called_once_with(["urn:li:image:single"])

    def test_get_assets_save_without_images(self):
        """A post with a video or without media does not ask for any image."""
        with patch.object(
            type(self.SocialAccountLinkedin),
            "_get_linkedin_images_download_url",
        ) as mock_download_url:
            self.assertEqual(
                self.SocialPostAccountLinkedin._get_assets_save(
                    {"media": {"id": "urn:li:video:1"}}
                ),
                [],
            )
            self.assertEqual(self.SocialPostAccountLinkedin._get_assets_save({}), [])
        mock_download_url.assert_not_called()

    @patch(PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"))
    def test_action_like_post(self, mock_request):
        author_urn = "urn:li:person:abc"
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_request.return_value = mock_response
        result = self.SocialPostAccountLinkedin.action_like_post(author_urn=author_urn)
        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "")

        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_request.return_value = mock_response
        result = self.SocialPostAccountLinkedin.action_like_post(author_urn=author_urn)
        self.assertFalse(result["success"])
        self.assertEqual(result["message"], "You have already reacted to this post.")

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_request.return_value = mock_response
        result = self.SocialPostAccountLinkedin.action_like_post(author_urn=author_urn)
        self.assertFalse(result["success"])
        self.assertEqual(
            result["message"], "The post does not exist or has been deleted."
        )

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = '{"message": "Internal error occurred."}'
        mock_request.return_value = mock_response

        result = self.SocialPostAccountLinkedin.action_like_post(author_urn=author_urn)
        self.assertFalse(result["success"])
        self.assertEqual(result["message"], "Internal error occurred.")

    def test_action_like_post_failed(self):
        with patch(PATCH_POST_ACCOUNT.format("action_like_post")) as mock_like_super:
            self.SocialPostAccount.action_like_post()
            mock_like_super.assert_called_once()

    @patch(PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"))
    def test_get_comments_success(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "elements": [
                {
                    "id": "comment1",
                    "message": {"text": "Great post!"},
                    "lastModified": {"actor": {"id": "actor1"}, "time": 1609459200000},
                    "content": [{"url": "http://example.com/image1.jpg"}],
                }
            ]
        }
        mock_request.return_value = mock_response
        result = self.SocialPostAccountLinkedin.get_comments()
        data = result["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "comment1")
        self.assertEqual(data[0]["text"], "Great post!")
        self.assertEqual(data[0]["actor"]["id"], "actor1")
        self.assertEqual(data[0]["images_url"], ["http://example.com/image1.jpg"])

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"elements": []}
        mock_request.return_value = mock_response
        result = self.SocialPostAccountLinkedin.get_comments()
        self.assertEqual(result["data"], [])

    @patch(PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"))
    def test_get_comments_without_last_modified(self, mock_request):
        """LinkedIn may answer a comment without its modification data."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "elements": [
                {
                    "id": "comment1",
                    "message": {"text": "Great post!"},
                    "content": [],
                }
            ]
        }
        mock_request.return_value = mock_response
        result = self.SocialPostAccountLinkedin.get_comments()
        self.assertTrue(result["success"])
        self.assertEqual(result["data"][0]["actor"], {})

    @mute_logger(LOGGER_POST_ACCOUNT_LINKEDIN)
    @patch(PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"))
    def test_get_comments_failed(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_request.return_value = mock_response
        result = self.SocialPostAccountLinkedin.get_comments()
        self.assertFalse(result["success"])
        self.assertIn("comments could not be read from LinkedIn", result["message"])

    @mute_logger(LOGGER_POST_ACCOUNT_LINKEDIN)
    @patch(PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"))
    @patch(PATCH_ACCOUNT_LINKEDIN.format("_linkedin_prepare_images_for_post"))
    def test_create_linkedin_comment_success(self, mock_prepare_images, mock_request):
        mock_prepare_images.return_value = [{"media": "asset_123"}]
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"message": "Comment created successfully"}
        mock_request.return_value = mock_response
        post_data = {
            "body": "Great post!",
            "attachment_ids": [1],
        }
        result = self.SocialPostAccountLinkedin._create_linkedin_comment(post_data)
        self.assertEqual(result["success"], True)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"message": "Comment created successfully"}
        mock_request.return_value = mock_response
        result = self.SocialPostAccountLinkedin._create_linkedin_comment(post_data)
        self.assertEqual(result["success"], True)

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_request.return_value = mock_response
        post_data.update({"attachment_ids": []})
        result = self.SocialPostAccountLinkedin._create_linkedin_comment(post_data)
        self.assertFalse(result["success"])
        self.assertIn("comment could not be published on LinkedIn", result["message"])

    @patch(PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"))
    def test_delete_linkedin_comment_success(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_request.return_value = mock_response
        comment_id = "123456"
        actor_urn = "urn:li:person:abc123"
        result = self.SocialPostAccountLinkedin.delete_linkedin_comment(
            comment_id, actor_urn
        )
        self.assertEqual(result["success"], True)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"message": "Internal Server Error"}
        mock_request.return_value = mock_response
        result = self.SocialPostAccountLinkedin.delete_linkedin_comment(
            comment_id, actor_urn
        )
        self.assertEqual(result["success"], False)

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"message": "Not Found"}
        mock_request.return_value = mock_response
        result = self.SocialPostAccountLinkedin.delete_linkedin_comment(
            comment_id, actor_urn
        )
        self.assertEqual(result["success"], False)

    @patch(PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"))
    def test_check_remote_post_exists(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response
        self.assertTrue(self.SocialPostAccountLinkedin.check_post_exists())

    @patch(PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"))
    def test_check_remote_post_exists_deleted(self, mock_request):
        """A 404 is the only answer that means the post is gone."""
        remote_ref = self.SocialPostAccountLinkedin.remote_ref
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_request.return_value = mock_response
        self.assertFalse(self.SocialPostAccountLinkedin.check_post_exists())
        self.assertEqual(self.SocialPostAccountLinkedin.state, "deleted")
        self.assertFalse(self.SocialPostAccountLinkedin.post_account_url)
        self.assertEqual(self.SocialPostAccountLinkedin.remote_ref, remote_ref)

    @patch(PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"))
    def test_check_remote_post_exists_forbidden(self, mock_request):
        """A lost permission is not a deletion: nothing may be written."""
        post_account = self.SocialPostAccountLinkedin
        post_account.write({"state": "posted"})
        remote_ref = post_account.remote_ref
        post_account_url = post_account.post_account_url
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_request.return_value = mock_response
        with mute_logger(LOGGER_POST_ACCOUNT_LINKEDIN):
            self.assertTrue(post_account.check_post_exists())
        self.assertEqual(post_account.state, "posted")
        self.assertEqual(post_account.remote_ref, remote_ref)
        self.assertEqual(post_account.post_account_url, post_account_url)

    @patch(PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"))
    def test_check_remote_post_exists_unreachable(self, mock_request):
        """LinkedIn out of reach leaves the publication untouched."""
        post_account = self.SocialPostAccountLinkedin
        post_account.write({"state": "posted"})
        mock_request.side_effect = UserError("boom")
        with mute_logger(LOGGER_POST_ACCOUNT_LINKEDIN):
            self.assertTrue(post_account.check_post_exists())
        self.assertEqual(post_account.state, "posted")

    def test_action_like_comment(self):
        result = self.SocialPostAccountLinkedin.action_like_comment()
        self.assertEqual(result, {"success": False, "message": ""})

    @patch(PATCH_POST_ACCOUNT_LINKEDIN.format("_create_linkedin_comment"))
    @patch(PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"))
    def test_create_comment(self, mock_request_linkedin, mock_create_linkedin_comment):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_request_linkedin.return_value = mock_response
        result = self.SocialPostAccountLinkedin.create_comment(
            {"body": "Test comment", "attachment_ids": [1]}
        )
        self.assertTrue(result["success"])
        mock_create_linkedin_comment.assert_called_once()

    def test_compute_message_info(self):
        post_message_info = self.SocialPost.create(
            {
                "message": self.test_message,
                "account_ids": [Command.set(self.SocialAccountLinkedin.ids)],
                "image_ids": [Command.set([self.create_attachment().id])],
                "video_ids": [
                    Command.set([self.create_attachment("test_video.mp4").id])
                ],
            }
        )
        self.assertTrue(post_message_info.message_info)
        self.assertIn(
            "You have selected images and videos for this post",
            post_message_info.message_info,
        )

        post = self.SocialPost.create(
            {
                "message": self.test_message,
                "account_ids": [Command.set(self.SocialAccountLinkedin.ids)],
                "image_ids": [Command.set([self.create_attachment().id])],
            }
        )
        self.assertFalse(post.message_info)

    def test_compute_message_info_recomputed_on_media_change(self):
        post = self.SocialPost.create(
            {
                "message": self.test_message,
                "account_ids": [Command.set(self.SocialAccountLinkedin.ids)],
                "image_ids": [Command.set([self.create_attachment().id])],
            }
        )
        self.assertFalse(post.message_info)

        post.video_ids = [Command.set([self.create_attachment("test_video.mp4").id])]
        self.assertIn(
            "You have selected images and videos for this post",
            post.message_info,
        )

        post.image_ids = [Command.clear()]
        self.assertFalse(post.message_info)

    def test_compute_message_info_video_wins_over_the_images(self):
        """The warning must say what the connector really publishes."""
        post = self.SocialPost.create(
            {
                "message": self.test_message,
                "account_ids": [Command.set(self.SocialAccountLinkedin.ids)],
                "image_ids": [Command.set([self.create_attachment().id])],
                "video_ids": [
                    Command.set([self.create_attachment("test_video.mp4").id])
                ],
            }
        )
        self.assertIn("only the video will be published", post.message_info)

    def test_post_preview_video_wins_over_the_images(self):
        """The preview must show what LinkedIn publishes, not the rest."""
        image = self.create_attachment("preview_image.jpg")
        video = self.create_attachment("preview_video.mp4")
        post = self.SocialPost.create(
            {
                "message": self.test_message,
                "account_ids": [Command.set(self.SocialAccountLinkedin.ids)],
                "image_ids": [Command.set([image.id])],
                "video_ids": [Command.set([video.id])],
            }
        )
        self.assertNotIn(f"/web/image/{image.id}", post.post_preview)
        self.assertIn("preview_video.mp4", post.post_preview)

    def test_post_preview_keeps_the_images_without_a_video(self):
        image = self.create_attachment("preview_image.jpg")
        post = self.SocialPost.create(
            {
                "message": self.test_message,
                "account_ids": [Command.set(self.SocialAccountLinkedin.ids)],
                "image_ids": [Command.set([image.id])],
            }
        )
        self.assertIn(f"/web/image/{image.id}", post.post_preview)

    def test_post_schedule(self):
        post_hide = self.SocialPost.create(
            {
                "message": self.test_message,
                "send_post": "schedule",
                "account_ids": [Command.set(self.SocialAccountLinkedin.ids)],
            }
        )
        self.assertEqual(post_hide.state, "planned")
        self.assertFalse(post_hide.hide_post)
        post_hide.action_draft()
        self.assertEqual(post_hide.state, "draft")
        self.assertFalse(post_hide.hide_post)
        post_hide.send_post = "schedule"
        post_hide.action_cancel()
        self.assertEqual(post_hide.state, "cancelled")

    @patch(PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"))
    def test_delete_post_account(self, mock_request_linkedin):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_request_linkedin.return_value = mock_response
        self.SocialPostAccountLinkedin._delete_post_account()

        mock_failed_response = MagicMock()
        mock_failed_response.status_code = 404
        mock_request_linkedin.return_value = mock_failed_response
        with self.assertRaises(UserError):
            self.SocialPostAccountLinkedin._delete_post_account()
        self.assertEqual(mock_request_linkedin.call_count, 2)

    @patch(PATCH_ACCOUNT_LINKEDIN.format("_request_linkedin"))
    def test_delete_post_account_refreshes_the_token_first(self, mock_request_linkedin):
        """A 401 here would be reported as an undeletable post."""
        mock_request_linkedin.return_value = MagicMock(status_code=204)
        with patch.object(
            type(self.SocialAccount), "validate_access_token", autospec=True
        ) as mock_validate:
            self.SocialPostAccountLinkedin._delete_post_account()
        mock_validate.assert_called_once()
        self.assertTrue(
            mock_validate.call_args.args[0].env.context.get("not_notify"),
            msg="Deleting a publication must not report that the token is valid.",
        )

    def test_action_post(self):
        self.SocialPostAccountLinkedin.write({"state": "ready"})
        post_account_urn = "urn:li:share:122809890045"
        attachment = self.env["ir.attachment"].create(
            {"name": "fake-asset.png", "datas": self.image_base64}
        )
        fake_response = [
            {
                "id": post_account_urn,
                "content": {"media": {"id": "urn:li:image:1"}},
            }
        ]
        with patch.object(
            type(self.SocialPostLinkedin),
            "_filter_by_media_types",
            autospec=True,
            return_value=self.SocialPostAccountLinkedin,
        ) as mock_filter_by_media_types, patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_linkedin_create_post",
            autospec=True,
            return_value=(post_account_urn, []),
        ) as mock_linkedin_create_post, patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_get_posts",
            autospec=True,
            return_value=fake_response,
        ) as mock_get_posts, patch.object(
            type(self.SocialPostAccountLinkedin),
            "_get_assets_save",
            autospec=True,
            return_value=[attachment.id],
        ) as mock_get_assets_save:
            self.SocialPostAccountLinkedin._action_post(self.SocialPostLinkedin)
            self.assertEqual(
                self.SocialPostAccountLinkedin.remote_ref,
                post_account_urn,
            )
            self.assertEqual(self.SocialPostAccountLinkedin.state, "posted")
            self.assertFalse(self.SocialPostAccountLinkedin.has_video)
            self.assertEqual(
                self.SocialPostAccountLinkedin.post_account_url,
                f"https://www.linkedin.com/feed/update/{post_account_urn}",
            )
            mock_filter_by_media_types.assert_called_once()
            mock_linkedin_create_post.assert_called_once()
            mock_get_posts.assert_called_once()
            mock_get_assets_save.assert_called_once()

    def test_action_post_video_sets_has_video(self):
        self.SocialPostAccountLinkedin.write({"state": "ready", "remote_ref": False})
        self.SocialPostLinkedin.write(
            {"video_ids": [Command.set([self.create_attachment("test_video.mp4").id])]}
        )
        post_account_urn = "urn:li:ugcPost:122809890045"
        fake_response = [
            {
                "id": post_account_urn,
                "content": {"media": {"id": "urn:li:image:1"}},
            }
        ]
        with patch.object(
            type(self.SocialPostLinkedin),
            "_filter_by_media_types",
            autospec=True,
            return_value=self.SocialPostAccountLinkedin,
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_linkedin_create_post",
            autospec=True,
            return_value=(post_account_urn, []),
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_get_posts",
            autospec=True,
            return_value=fake_response,
        ), patch.object(
            type(self.SocialPostAccountLinkedin),
            "_get_assets_save",
            autospec=True,
            return_value=[],
        ):
            self.SocialPostAccountLinkedin._action_post(self.SocialPostLinkedin)
        self.assertEqual(self.SocialPostAccountLinkedin.state, "posted")
        self.assertTrue(self.SocialPostAccountLinkedin.has_video)

    @mute_logger(LOGGER_POST_ACCOUNT_BASE)
    def test_action_post_with_several_videos_is_refused(self):
        """The check runs before uploading anything to LinkedIn."""
        self.SocialPostAccountLinkedin.write({"state": "ready", "remote_ref": False})
        self.SocialPostLinkedin.write(
            {
                "video_ids": [
                    Command.set(
                        [
                            self.create_attachment("one.mp4").id,
                            self.create_attachment("two.mp4").id,
                        ]
                    )
                ]
            }
        )
        with patch.object(
            type(self.SocialPostLinkedin),
            "_filter_by_media_types",
            autospec=True,
            return_value=self.SocialPostAccountLinkedin,
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_linkedin_prepare_videos_for_post",
            autospec=True,
        ) as mock_prepare_videos, patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_linkedin_create_post",
            autospec=True,
        ) as mock_linkedin_create_post:
            self.SocialPostAccountLinkedin._action_post(self.SocialPostLinkedin)
            mock_prepare_videos.assert_not_called()
            mock_linkedin_create_post.assert_not_called()
        self.assertEqual(self.SocialPostAccountLinkedin.state, "failed")
        self.assertIn(
            "single video per post", self.SocialPostAccountLinkedin.failed_description
        )

    def test_check_linkedin_post_format_accepts_a_gif(self):
        """The Images API takes GIF, so nothing may refuse it here."""
        self.SocialPostAccountLinkedin.write({"state": "ready", "remote_ref": False})
        self.SocialPostLinkedin.write(
            {"image_ids": [Command.set([self.create_attachment("animation.gif").id])]}
        )
        self.SocialPostAccountLinkedin._check_linkedin_post_format()
        self.assertNotIn("GIF", self.SocialPostLinkedin.message_info or "")

    def test_check_linkedin_post_format_rejects_a_mov_video(self):
        """The Videos API only takes MP4, whatever the file dialog let through."""
        self.SocialPostAccountLinkedin.write({"state": "ready", "remote_ref": False})
        self.SocialPostLinkedin.write(
            {"video_ids": [Command.set([self.create_attachment("holidays.mov").id])]}
        )
        with self.assertRaises(UserError):
            self.SocialPostAccountLinkedin._check_linkedin_post_format()
        self.assertIn("MP4 videos", self.SocialPostLinkedin.message_info)

    def test_check_linkedin_post_format_ignores_the_images_when_there_is_a_video(self):
        """A video drops the images, so their format decides nothing."""
        self.SocialPostAccountLinkedin.write({"state": "ready", "remote_ref": False})
        self.SocialPostLinkedin.write(
            {
                "image_ids": [Command.set([self.create_attachment("picture.webp").id])],
                "video_ids": [Command.set([self.create_attachment("clip.mp4").id])],
            }
        )
        self.SocialPostAccountLinkedin._check_linkedin_post_format()
        self.assertNotIn("JPG, PNG and GIF", self.SocialPostLinkedin.message_info)

    def test_check_linkedin_post_format_rejects_an_unsupported_image(self):
        self.SocialPostAccountLinkedin.write({"state": "ready", "remote_ref": False})
        self.SocialPostLinkedin.write(
            {"image_ids": [Command.set([self.create_attachment("picture.webp").id])]}
        )
        with self.assertRaises(UserError):
            self.SocialPostAccountLinkedin._check_linkedin_post_format()
        self.assertIn("JPG, PNG and GIF", self.SocialPostLinkedin.message_info)

    def test_action_post_fails_only_the_line_with_the_wrong_format(self):
        """The format is checked before anything is uploaded to LinkedIn."""
        self.SocialPostAccountLinkedin.write({"state": "ready", "remote_ref": False})
        self.SocialPostLinkedin.write(
            {"video_ids": [Command.set([self.create_attachment("holidays.mov").id])]}
        )
        with patch.object(
            type(self.SocialPostLinkedin),
            "_filter_by_media_types",
            autospec=True,
            return_value=self.SocialPostAccountLinkedin,
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_linkedin_create_post",
            autospec=True,
        ) as mock_linkedin_create_post:
            self.SocialPostAccountLinkedin._action_post(self.SocialPostLinkedin)
            mock_linkedin_create_post.assert_not_called()
        self.assertEqual(self.SocialPostAccountLinkedin.state, "failed")
        self.assertIn("MP4 videos", self.SocialPostAccountLinkedin.failed_description)

    def test_action_post_keeps_the_upload_order_of_the_images(self):
        """LinkedIn draws the images in the order it receives them."""
        self.SocialPostAccountLinkedin.write({"state": "ready", "remote_ref": False})
        images = self.env["ir.attachment"].create(
            [
                {
                    "name": f"image_{number}.jpg",
                    "type": "binary",
                    "datas": self.VALID_PNG_B64,
                }
                for number in range(3)
            ]
        )
        self.SocialPostLinkedin.write({"image_ids": [Command.set(images.ids)]})
        # Read back from database: a many2many follows the ``id desc`` order
        # of ``ir.attachment``, which is the order the cron would publish.
        self.SocialPostLinkedin.invalidate_recordset()
        with patch.object(
            type(self.SocialPostLinkedin),
            "_filter_by_media_types",
            autospec=True,
            return_value=self.SocialPostAccountLinkedin,
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_linkedin_create_post",
            autospec=True,
            return_value=("urn:li:share:1", []),
        ) as mock_linkedin_create_post, patch.object(
            type(self.SocialPostAccountLinkedin),
            "_linkedin_enrich_published_post",
            autospec=True,
        ):
            self.SocialPostAccountLinkedin._action_post(self.SocialPostLinkedin)
        self.assertEqual(
            list(mock_linkedin_create_post.call_args.kwargs["image_ids"].ids),
            images.ids,
        )

    def test_compute_message_info_several_videos(self):
        post = self.SocialPost.create(
            {
                "message": self.test_message,
                "account_ids": [Command.set(self.SocialAccountLinkedin.ids)],
                "video_ids": [
                    Command.set(
                        [
                            self.create_attachment("one.mp4").id,
                            self.create_attachment("two.mp4").id,
                        ]
                    )
                ],
            }
        )
        self.assertIn("single video per post", post.message_info)

    @mute_logger(LOGGER_POST_ACCOUNT_BASE)
    def test_action_post_isolates_the_failing_account(self):
        """One account failing must not undo the one that did publish."""
        post_account_urn = "urn:li:share:122809890046"
        second_account = self.SocialAccountLinkedin.copy(
            {"name": "Second LinkedIn account", "remote_ref": "urn:li:organization:2"}
        )
        second_post_account = self.SocialPostAccountLinkedin.copy(
            {"account_id": second_account.id, "state": "ready", "remote_ref": False}
        )
        self.SocialPostAccountLinkedin.write({"state": "ready", "remote_ref": False})
        post_accounts = self.SocialPostAccountLinkedin | second_post_account
        with patch.object(
            type(self.SocialPostLinkedin),
            "_filter_by_media_types",
            autospec=True,
            return_value=post_accounts,
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_linkedin_create_post",
            autospec=True,
            side_effect=[
                (post_account_urn, []),
                UserError("LinkedIn refused the post"),
            ],
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_get_posts",
            autospec=True,
            return_value=[],
        ):
            self.SocialPostAccountLinkedin._action_post(self.SocialPostLinkedin)
        self.assertEqual(self.SocialPostAccountLinkedin.state, "posted")
        self.assertEqual(self.SocialPostAccountLinkedin.remote_ref, post_account_urn)
        self.assertEqual(second_post_account.state, "failed")
        self.assertIn(
            "LinkedIn refused the post", second_post_account.failed_description
        )
        self.assertFalse(second_post_account.remote_ref)

    @mute_logger(LOGGER_POST_ACCOUNT_BASE)
    def test_check_linkedin_publishable_fails_only_its_own_line(self):
        """The extension point refusing a publication stops that one alone."""
        post_account_urn = "urn:li:share:122809890060"
        second_account = self.SocialAccountLinkedin.copy(
            {"name": "Second LinkedIn account", "remote_ref": "urn:li:organization:3"}
        )
        second_post_account = self.SocialPostAccountLinkedin.copy(
            {"account_id": second_account.id, "state": "ready", "remote_ref": False}
        )
        self.SocialPostAccountLinkedin.write({"state": "ready", "remote_ref": False})
        post_accounts = self.SocialPostAccountLinkedin | second_post_account
        refusal = "The extension refused this publication"

        def refuse_the_second(post_account):
            if post_account == second_post_account:
                raise UserError(refusal)

        with patch.object(
            type(self.SocialPostLinkedin),
            "_filter_by_media_types",
            autospec=True,
            return_value=post_accounts,
        ), patch.object(
            type(self.SocialPostAccountLinkedin),
            "_check_linkedin_publishable",
            autospec=True,
            side_effect=refuse_the_second,
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_linkedin_create_post",
            autospec=True,
            return_value=(post_account_urn, []),
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_get_posts",
            autospec=True,
            return_value=[],
        ):
            self.SocialPostAccountLinkedin._action_post(self.SocialPostLinkedin)
        self.assertEqual(self.SocialPostAccountLinkedin.state, "posted")
        self.assertEqual(self.SocialPostAccountLinkedin.remote_ref, post_account_urn)
        self.assertEqual(second_post_account.state, "failed")
        self.assertFalse(second_post_account.remote_ref)
        self.assertIn(refusal, second_post_account.failed_description)

    def test_linkedin_published_values_are_written(self):
        """What the extension point returns is stored with the publication."""
        post_account_urn = "urn:li:share:122809890061"
        self.SocialPostAccountLinkedin.write({"state": "ready", "remote_ref": False})
        with patch.object(
            type(self.SocialPostLinkedin),
            "_filter_by_media_types",
            autospec=True,
            return_value=self.SocialPostAccountLinkedin,
        ), patch.object(
            type(self.SocialPostAccountLinkedin),
            "_linkedin_published_values",
            autospec=True,
            return_value={"message": "Written by the extension"},
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_linkedin_create_post",
            autospec=True,
            return_value=(post_account_urn, []),
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_get_posts",
            autospec=True,
            return_value=[],
        ):
            self.SocialPostAccountLinkedin._action_post(self.SocialPostLinkedin)
        self.assertEqual(self.SocialPostAccountLinkedin.remote_ref, post_account_urn)
        self.assertEqual(
            self.SocialPostAccountLinkedin.message, "Written by the extension"
        )

    @mute_logger(LOGGER_POST_ACCOUNT_BASE)
    def test_linkedin_published_values_failing_loses_the_publication(self):
        """An error of the extension point undoes a post that is already online.

        This pins what the code does today, which is not what
        :meth:`_linkedin_enrich_published_post` documents: the call to
        _linkedin_published_values sits outside its try, so the error reaches
        _publish_guard and the savepoint takes the remote reference of a
        published post with it. Deferred as LNK-28 of the OCA review, since
        moving the call inside the try changes what is written.
        """
        post_account_urn = "urn:li:share:122809890062"
        self.SocialPostAccountLinkedin.write({"state": "ready", "remote_ref": False})
        with patch.object(
            type(self.SocialPostLinkedin),
            "_filter_by_media_types",
            autospec=True,
            return_value=self.SocialPostAccountLinkedin,
        ), patch.object(
            type(self.SocialPostAccountLinkedin),
            "_linkedin_published_values",
            autospec=True,
            side_effect=ValueError("The extension broke"),
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_linkedin_create_post",
            autospec=True,
            return_value=(post_account_urn, []),
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_get_posts",
            autospec=True,
            return_value=[],
        ):
            self.SocialPostAccountLinkedin._action_post(self.SocialPostLinkedin)
        self.assertEqual(self.SocialPostAccountLinkedin.state, "failed")
        self.assertFalse(self.SocialPostAccountLinkedin.remote_ref)

    def test_action_post_renews_the_token_and_publishes_again(self):
        """A token refused at the last moment is renewed and the post goes out."""
        post_account_urn = "urn:li:share:122809890050"
        self.SocialPostAccountLinkedin.write({"state": "ready", "remote_ref": False})
        with patch.object(
            type(self.SocialPostLinkedin),
            "_filter_by_media_types",
            autospec=True,
            return_value=self.SocialPostAccountLinkedin,
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_linkedin_create_post",
            autospec=True,
            side_effect=[
                SocialCredentialsError("The access token expired"),
                (post_account_urn, []),
            ],
        ) as mock_create_post, patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_refresh_credentials",
            autospec=True,
            return_value=True,
        ) as mock_refresh, patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_get_posts",
            autospec=True,
            return_value=[],
        ):
            self.SocialPostAccountLinkedin._action_post(self.SocialPostLinkedin)
        mock_refresh.assert_called_once()
        self.assertEqual(mock_create_post.call_count, 2)
        self.assertEqual(self.SocialPostAccountLinkedin.state, "posted")
        self.assertEqual(self.SocialPostAccountLinkedin.remote_ref, post_account_urn)

    @mute_logger(LOGGER_POST_ACCOUNT_BASE)
    def test_action_post_without_token_says_so_on_the_line(self):
        """A publication skipped for lack of token must explain itself."""
        self.SocialPostAccountLinkedin.write({"state": "ready", "remote_ref": False})
        self.SocialAccountLinkedin.sudo().access_token = False
        with patch.object(
            type(self.SocialPostLinkedin),
            "_filter_by_media_types",
            autospec=True,
            return_value=self.SocialPostAccountLinkedin,
        ):
            self.SocialPostAccountLinkedin._action_post(self.SocialPostLinkedin)
        self.assertEqual(self.SocialPostAccountLinkedin.state, "failed")
        self.assertIn(
            "no LinkedIn access token",
            self.SocialPostAccountLinkedin.failed_description,
        )
        self.assertTrue(self.SocialAccountLinkedin.need_update)

    def test_action_post_falls_back_to_the_local_images(self):
        """LinkedIn not exposing the images yet must not empty the card."""
        post_account_urn = "urn:li:share:122809890048"
        image = self.env["ir.attachment"].create(
            {
                "name": "local.jpg",
                "type": "binary",
                "datas": base64.b64encode(b"local image").decode(),
            }
        )
        self.SocialPostAccountLinkedin.write({"state": "ready", "remote_ref": False})
        self.SocialPostLinkedin.write({"image_ids": [Command.set(image.ids)]})
        with patch.object(
            type(self.SocialPostLinkedin),
            "_filter_by_media_types",
            autospec=True,
            return_value=self.SocialPostAccountLinkedin,
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_linkedin_create_post",
            autospec=True,
            return_value=(post_account_urn, ["urn:li:image:published"]),
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_get_posts",
            autospec=True,
            return_value=[],
        ):
            self.SocialPostAccountLinkedin._action_post(self.SocialPostLinkedin)
        self.assertEqual(self.SocialPostAccountLinkedin.state, "posted")
        copied = self.SocialPostAccountLinkedin.image_ids
        self.assertEqual(len(copied), 1)
        self.assertEqual(copied.name, "urn:li:image:published")
        self.assertEqual(copied.datas, image.datas)
        self.assertNotEqual(self.SocialPostAccountLinkedin.image_urls, "[]")

    def test_action_post_prefers_the_images_downloaded_from_linkedin(self):
        """The fallback only applies when the download brings nothing back."""
        post_account_urn = "urn:li:share:122809890049"
        image = self.env["ir.attachment"].create(
            {
                "name": "local.jpg",
                "type": "binary",
                "datas": base64.b64encode(b"local image").decode(),
            }
        )
        self.SocialPostAccountLinkedin.write({"state": "ready", "remote_ref": False})
        self.SocialPostLinkedin.write({"image_ids": [Command.set(image.ids)]})
        downloaded = self.create_attachment(attach_name="urn:li:image:downloaded")
        with patch.object(
            type(self.SocialPostLinkedin),
            "_filter_by_media_types",
            autospec=True,
            return_value=self.SocialPostAccountLinkedin,
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_linkedin_create_post",
            autospec=True,
            return_value=(post_account_urn, ["urn:li:image:published"]),
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_get_posts",
            autospec=True,
            return_value=[{"id": post_account_urn, "content": {"media": {"id": "x"}}}],
        ), patch.object(
            type(self.SocialPostAccountLinkedin),
            "_get_assets_save",
            autospec=True,
            return_value=[Command.link(downloaded.id)],
        ):
            self.SocialPostAccountLinkedin._action_post(self.SocialPostLinkedin)
        self.assertEqual(self.SocialPostAccountLinkedin.image_ids, downloaded)

    def test_action_post_does_not_empty_the_images_on_a_retry(self):
        """Republishing a failed line must not clear what it already had."""
        post_account_urn = "urn:li:share:122809890050"
        stored = self.create_attachment(attach_name="urn:li:image:stored")
        self.SocialPostAccountLinkedin.write(
            {
                "state": "failed",
                "remote_ref": False,
                "image_ids": [Command.set(stored.ids)],
            }
        )
        with patch.object(
            type(self.SocialPostLinkedin),
            "_filter_by_media_types",
            autospec=True,
            return_value=self.SocialPostAccountLinkedin,
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_linkedin_create_post",
            autospec=True,
            return_value=(post_account_urn, []),
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_get_posts",
            autospec=True,
            return_value=[],
        ):
            self.SocialPostAccountLinkedin._action_post(self.SocialPostLinkedin)
        self.assertEqual(self.SocialPostAccountLinkedin.state, "posted")
        self.assertEqual(self.SocialPostAccountLinkedin.image_ids, stored)

    @mute_logger(LOGGER_POST_ACCOUNT_LINKEDIN)
    def test_action_post_keeps_remote_ref_when_the_medias_fail(self):
        """The enrichment is best-effort: it never reverts a published post."""
        post_account_urn = "urn:li:share:122809890047"
        self.SocialPostAccountLinkedin.write({"state": "ready", "remote_ref": False})
        with patch.object(
            type(self.SocialPostLinkedin),
            "_filter_by_media_types",
            autospec=True,
            return_value=self.SocialPostAccountLinkedin,
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_linkedin_create_post",
            autospec=True,
            return_value=(post_account_urn, []),
        ), patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_get_posts",
            autospec=True,
            side_effect=UserError("LinkedIn is not available"),
        ):
            self.SocialPostAccountLinkedin._action_post(self.SocialPostLinkedin)
        self.assertEqual(self.SocialPostAccountLinkedin.state, "posted")
        self.assertEqual(self.SocialPostAccountLinkedin.remote_ref, post_account_urn)

    def test_action_post_failed(self):
        self.SocialPostAccountLinkedin.write({"state": "ready"})
        with patch.object(
            type(self.SocialPostLinkedin),
            "_filter_by_media_types",
            autospec=True,
            return_value=self.SocialPostAccountLinkedin,
        ) as mock_filter_by_media_types, patch.object(
            type(self.SocialPostAccountLinkedin.account_id),
            "_linkedin_create_post",
            autospec=True,
            return_value=(False, []),
        ) as mock_linkedin_create_post:
            self.SocialPostAccountLinkedin._action_post(self.SocialPostLinkedin)
            self.assertEqual(self.SocialPostAccountLinkedin.state, "failed")
            mock_filter_by_media_types.assert_called_once()
            mock_linkedin_create_post.assert_called_once()

    def test_default_account_ids_only_the_active_company(self):
        """An account of another allowed company is not preselected."""
        company = self.env["res.company"].create({"name": "Other Company"})
        other_account = self.SocialAccountLinkedin.copy({"company_id": company.id})
        self.assertNotIn(other_account.id, self.SocialPost._default_account_ids())
        self.assertIn(
            other_account.id,
            self.SocialPost.with_company(company)._default_account_ids(),
        )
