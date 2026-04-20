# Copyright 2025 Ledoent <https://www.ledoweb.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

from odoo.tests.common import HttpCase, tagged

from odoo.addons.social_media_facebook.controllers.webhook_controller import (
    FacebookWebhookController,
)
from odoo.addons.social_media_facebook.tests.test_common_facebook import (
    TestSocialCommonFacebook,
)

APP_SECRET = "test_app_secret_abc123"


def _make_signature(payload: bytes, secret: str = APP_SECRET) -> str:
    """Helper: compute a valid X-Hub-Signature-256 header value."""
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@tagged("post_install", "-at_install")
class TestFacebookWebhook(HttpCase, TestSocialCommonFacebook):
    """Tests for FacebookWebhookController."""

    def setUp(self):
        super().setUp()
        self.controller = FacebookWebhookController()
        self.authenticate("admin", "admin")
        # Configure app secret for all tests
        self.IrConfigParameter.set_param(
            "social_media_base.facebook_app_secret", APP_SECRET
        )

    # ------------------------------------------------------------------
    # _verify_signature
    # ------------------------------------------------------------------

    def test_verify_signature_valid(self):
        """Valid HMAC-SHA256 signature is accepted."""
        payload = b'{"object":"page"}'
        sig = _make_signature(payload)
        self.assertTrue(self.controller._verify_signature(payload, sig))

    def test_verify_signature_wrong_secret(self):
        """Signature computed with wrong secret is rejected."""
        payload = b'{"object":"page"}'
        sig = _make_signature(payload, secret="wrong_secret")
        self.assertFalse(self.controller._verify_signature(payload, sig))

    def test_verify_signature_missing_prefix(self):
        """Header value without sha256= prefix is rejected."""
        payload = b'{"object":"page"}'
        raw_hmac = hmac.new(APP_SECRET.encode(), payload, hashlib.sha256).hexdigest()
        self.assertFalse(self.controller._verify_signature(payload, raw_hmac))

    def test_verify_signature_empty_header(self):
        """Empty signature header is rejected."""
        self.assertFalse(self.controller._verify_signature(b"data", ""))

    def test_verify_signature_fail_closed_no_secret(self):
        """When app_secret is not configured, webhook is rejected (fail-closed)."""
        self.IrConfigParameter.set_param("social_media_base.facebook_app_secret", "")
        payload = b'{"object":"page"}'
        # Signature irrelevant — no secret means reject
        sig = _make_signature(payload)
        self.assertFalse(self.controller._verify_signature(payload, sig))

    # ------------------------------------------------------------------
    # GET /facebook/webhook/leads — subscription verification
    # ------------------------------------------------------------------

    def test_webhook_verify_valid_token(self):
        """Correct verify_token returns hub.challenge."""
        verify_token = "my_verify_token"
        self.IrConfigParameter.set_param(
            "social_media_facebook.webhook_verify_token", verify_token
        )
        resp = self.url_open(
            "/facebook/webhook/leads"
            f"?hub.mode=subscribe"
            f"&hub.challenge=CHALLENGE_STRING"
            f"&hub.verify_token={verify_token}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("CHALLENGE_STRING", resp.text)

    def test_webhook_verify_wrong_token(self):
        """Wrong verify_token returns 403."""
        self.IrConfigParameter.set_param(
            "social_media_facebook.webhook_verify_token", "correct_token"
        )
        resp = self.url_open(
            "/facebook/webhook/leads"
            "?hub.mode=subscribe"
            "&hub.challenge=CHALLENGE"
            "&hub.verify_token=wrong_token"
        )
        self.assertEqual(resp.status_code, 403)

    # ------------------------------------------------------------------
    # POST /facebook/webhook/leads — lead webhook processing
    # ------------------------------------------------------------------

    def _build_lead_payload(
        self,
        page_id="123456789",
        leadgen_id="lead_001",
        form_id="form_001",
    ):
        return json.dumps(
            {
                "object": "page",
                "entry": [
                    {
                        "id": page_id,
                        "time": 1234567890,
                        "changes": [
                            {
                                "field": "leadgen",
                                "value": {
                                    "leadgen_id": leadgen_id,
                                    "form_id": form_id,
                                    "page_id": page_id,
                                    "created_time": 1234567890,
                                },
                            }
                        ],
                    }
                ],
            }
        ).encode()

    def test_webhook_receive_invalid_signature_returns_403(self):
        """POST with invalid signature returns 403."""
        payload = self._build_lead_payload()
        resp = self.url_open(
            "/facebook/webhook/leads",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=invalidsignature",
            },
        )
        self.assertEqual(resp.status_code, 403)

    def test_webhook_receive_non_page_object_ignored(self):
        """POST for non-page object returns OK without processing."""
        payload = json.dumps({"object": "user", "entry": []}).encode()
        sig = _make_signature(payload)
        resp = self.url_open(
            "/facebook/webhook/leads",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
            },
        )
        self.assertEqual(resp.status_code, 200)

    def test_webhook_receive_valid_leadgen_calls_process(self):
        """POST with valid signature triggers _process_leadgen_webhook."""
        payload = self._build_lead_payload()
        sig = _make_signature(payload)
        with patch.object(
            FacebookWebhookController,
            "_process_leadgen_webhook",
            autospec=True,
        ) as mock_process:
            resp = self.url_open(
                "/facebook/webhook/leads",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": sig,
                },
            )
            self.assertEqual(resp.status_code, 200)
            mock_process.assert_called_once()

    def test_process_leadgen_missing_fields_skips(self):
        """_process_leadgen_webhook with missing required fields does nothing."""
        # No exception should be raised
        self.controller._process_leadgen_webhook({})
        self.controller._process_leadgen_webhook(
            {"leadgen_id": "x", "form_id": "y"}  # missing page_id
        )

    def test_process_leadgen_unknown_form_skips(self):
        """_process_leadgen_webhook with unknown form_id does nothing."""
        # No social.lead.form with this id in the DB → should skip gracefully
        with patch(
            "odoo.http.request",
            new_callable=MagicMock,
        ) as mock_request:
            mock_request.env = self.env
            self.controller._process_leadgen_webhook(
                {
                    "leadgen_id": "lead_999",
                    "form_id": "nonexistent_form",
                    "page_id": "123",
                }
            )
            # No exception = pass
