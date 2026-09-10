"""Tests for ServiceNow client auth modes."""

from unittest.mock import patch

from servicenow_bootstrap.servicenow_client import ServiceNowClient


@patch.dict("os.environ", {"SERVICENOW_INSTANCE_URL": "https://example.service-now.com"}, clear=False)
class TestServiceNowClientAuth:
    def test_api_key_sets_header_not_basic_auth(self):
        client = ServiceNowClient(api_key="token-123")
        assert client.session.headers["x-sn-apikey"] == "token-123"
        assert client.session.auth is None

    @patch.dict(
        "os.environ",
        {
            "SERVICENOW_USERNAME": "admin",
            "SERVICENOW_PASSWORD": "secret",
        },
        clear=False,
    )
    def test_basic_auth_when_no_api_key(self):
        client = ServiceNowClient()
        assert client.session.auth == ("admin", "secret")
        assert "x-sn-apikey" not in client.session.headers
