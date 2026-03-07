# Copyright 2025 Ledoent <https://www.ledoweb.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.addons.social_media_base.tests.test_social_common import (
    TestSocialMediaBaseCommon,
)

PATCH_ACCOUNT_FACEBOOK = (
    "odoo.addons.social_media_facebook.models.social_account.SocialAccount.{}"
)
PATCH_CONTROLLER_FACEBOOK = (
    "odoo.addons.social_media_facebook.controllers."
    "social_media_facebook.SocialMediaFacebookController.{}"
)
PATCH_WEBHOOK_CONTROLLER = (
    "odoo.addons.social_media_facebook.controllers."
    "webhook_controller.FacebookWebhookController.{}"
)
PATCH_WIZARD_FACEBOOK = (
    "odoo.addons.social_media_facebook.wizards."
    "wizard_social_account.WizardSocialAccount.{}"
)


class TestSocialCommonFacebook(TestSocialMediaBaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_facebook_id = cls.SocialMedia.create(
            {
                "name": "Facebook",
                "media_type": "facebook",
            }
        )
        cls.SocialAccountFacebook = cls.SocialAccount.create(
            {
                "name": "Test Facebook Page",
                "media_id": cls.media_facebook_id.id,
                "page_id": "123456789",
                "page_name": "Test Page",
                "page_access_token": "fake-page-token",
                "like_count": 10,
                "comment_count": 5,
                "share_count": 3,
                "click_count": 20,
                "engagement": 2.5,
                "impression_count": 1000,
            }
        )
        cls.IrConfigParameter = cls.env["ir.config_parameter"].sudo()
