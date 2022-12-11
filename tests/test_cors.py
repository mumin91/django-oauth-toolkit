from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from oauth2_provider.models import get_application_model
from oauth2_provider.oauth2_validators import OAuth2Validator

from . import presets
from .utils import get_basic_auth_header


class CorsOAuth2Validator(OAuth2Validator):
    def is_origin_allowed(self, client_id, origin, request, *args, **kwargs):
        """Enable CORS in OAuthLib"""
        return True


Application = get_application_model()
UserModel = get_user_model()

CLEARTEXT_SECRET = "1234567890abcdefghijklmnopqrstuvwxyz"

# CORS is allowed for https only
CLIENT_URI = "https://example.org"


@pytest.mark.usefixtures("oauth2_settings")
@pytest.mark.oauth2_settings(presets.DEFAULT_SCOPES_RW)
class CorsTest(TestCase):
    """
    Test that CORS headers can be managed by OAuthLib.
    The objective is: http request 'Origin' header should be passed to OAuthLib
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.test_user = UserModel.objects.create_user("test_user", "test@example.com", "123456")
        self.dev_user = UserModel.objects.create_user("dev_user", "dev@example.com", "123456")

        self.oauth2_settings.ALLOWED_REDIRECT_URI_SCHEMES = ["https"]
        self.oauth2_settings.PKCE_REQUIRED = False

        self.application = Application.objects.create(
            name="Test Application",
            redirect_uris=(CLIENT_URI),
            user=self.dev_user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            client_secret=CLEARTEXT_SECRET,
        )

        self.oauth2_settings.ALLOWED_REDIRECT_URI_SCHEMES = ["https"]
        self.oauth2_settings.OAUTH2_VALIDATOR_CLASS = CorsOAuth2Validator

    def tearDown(self):
        self.application.delete()
        self.test_user.delete()
        self.dev_user.delete()

    def test_cors_header(self):
        """
        Test that /token endpoint has Access-Control-Allow-Origin
        """
        authorization_code = self._get_authorization_code()

        # exchange authorization code for a valid access token
        token_request_data = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": CLIENT_URI,
        }

        auth_headers = get_basic_auth_header(self.application.client_id, CLEARTEXT_SECRET)
        auth_headers["origin"] = CLIENT_URI

        response = self.client.post(reverse("oauth2_provider:token"), data=token_request_data, **auth_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], CLIENT_URI)

    def test_no_cors_header(self):
        """
        Test that /token endpoint does not have Access-Control-Allow-Origin
        """
        authorization_code = self._get_authorization_code()

        # exchange authorization code for a valid access token
        token_request_data = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": CLIENT_URI,
        }

        auth_headers = get_basic_auth_header(self.application.client_id, CLEARTEXT_SECRET)

        response = self.client.post(reverse("oauth2_provider:token"), data=token_request_data, **auth_headers)
        self.assertEqual(response.status_code, 200)
        # No CORS headers, because request did not have Origin
        self.assertFalse(response.has_header("Access-Control-Allow-Origin"))

    def _get_authorization_code(self):
        self.client.login(username="test_user", password="123456")

        # retrieve a valid authorization code
        authcode_data = {
            "client_id": self.application.client_id,
            "state": "random_state_string",
            "scope": "read write",
            "redirect_uri": "https://example.org",
            "response_type": "code",
            "allow": True,
        }
        response = self.client.post(reverse("oauth2_provider:authorize"), data=authcode_data)
        query_dict = parse_qs(urlparse(response["Location"]).query)
        return query_dict["code"].pop()
