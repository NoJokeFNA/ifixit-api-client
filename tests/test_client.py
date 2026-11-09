import os
import unittest
from unittest.mock import Mock, patch

import requests

from ifixit_client import IFixitAPIClient


class ClientTests(unittest.TestCase):
    def test_proxy_is_ignored_by_default_and_tls_stays_enabled(self):
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:9"}):
            client = IFixitAPIClient()
            self.assertFalse(client.session.trust_env)
            settings = client.session.merge_environment_settings(
                "https://www.ifixit.com", {}, None, None, None
            )
        self.assertFalse(settings["proxies"])
        self.assertIs(settings["verify"], True)

    def test_proxy_can_be_enabled_without_disabling_tls(self):
        with patch.dict(
            os.environ,
            {
                "HTTPS_PROXY": "http://127.0.0.1:9",
                "https_proxy": "http://127.0.0.1:9",
                "NO_PROXY": "",
                "no_proxy": "",
            },
        ):
            client = IFixitAPIClient(proxy=True)
            settings = client.session.merge_environment_settings(
                "https://www.ifixit.com", {}, None, None, None
            )
        self.assertTrue(client.session.trust_env)
        self.assertEqual(settings["proxies"]["https"], "http://127.0.0.1:9")
        self.assertIs(client.session.verify, True)

    def test_retries_are_configured_without_a_proxy(self):
        client = IFixitAPIClient(retries=4)
        retries = client.session.get_adapter("https://www.ifixit.com").max_retries
        self.assertEqual(retries.total, 4)
        self.assertIn("GET", retries.allowed_methods)
        self.assertNotIn("POST", retries.allowed_methods)

    def test_get_guides_accepts_documented_keywords_without_mutating_params(self):
        client = IFixitAPIClient()
        client._request = Mock(return_value=[])
        params = {"category": "Fairphone 5", "limit": 20}
        client.get_guides(params=params, limit=2, offset=3)
        client._request.assert_called_once_with(
            "GET",
            "/guides",
            params={
                "category": "Fairphone 5",
                "limit": 2,
                "offset": 3,
            },
        )
        self.assertEqual(params, {"category": "Fairphone 5", "limit": 20})

    def test_pagination_handles_server_page_caps(self):
        client = IFixitAPIClient()
        client._request = Mock(side_effect=[[{"guideid": 1}], [{"guideid": 2}], []])
        self.assertEqual(
            list(client.get_all_guides(page_size=100, raw=True)),
            [{"guideid": 1}, {"guideid": 2}],
        )
        offsets = [
            call.kwargs["params"]["offset"] for call in client._request.call_args_list
        ]
        self.assertEqual(offsets, [0, 1, 2])

    def test_invalid_page_size_fails_before_a_request(self):
        for value in [0, -1, True, 1.5]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                list(IFixitAPIClient().get_all_guides(page_size=value, raw=True))

    def test_stream_limit_is_enforced_within_a_page(self):
        client = IFixitAPIClient()
        client._request = Mock(return_value=[{"guideid": 1}, {"guideid": 2}])
        self.assertEqual(
            list(client.get_all_guides(page_size=100, limit=1, raw=True)),
            [{"guideid": 1}],
        )
        client._request.assert_called_once_with(
            "GET", "/guides", params={"limit": 1, "offset": 0}
        )

    def test_zero_stream_limit_makes_no_request(self):
        client = IFixitAPIClient()
        client._request = Mock()
        self.assertEqual(list(client.get_all_guides(limit=0, raw=True)), [])
        client._request.assert_not_called()

    def test_custom_guide_parser_is_preserved(self):
        client = IFixitAPIClient()
        client._request = Mock(side_effect=[[{"guideid": 7}], []])
        self.assertEqual(
            list(client.get_all_guides(parser=lambda guide: guide["guideid"])), [7]
        )

    def test_category_does_not_replace_explicit_empty_params(self):
        client = IFixitAPIClient()
        client._request = Mock()
        client.get_category("Fairphone_5", params={})
        client._request.assert_called_with(
            "GET", "/wikis/CATEGORY/Fairphone_5", params={}
        )
        client.get_category()
        client._request.assert_called_with(
            "GET", "/wikis/CATEGORY", params={"display": "hierarchy"}
        )

    def test_category_keeps_all_api_fields_unchanged(self):
        client = IFixitAPIClient()
        payload = {
            "info": [],
            "ancestors": [{"title": "Fairphone"}],
            "repairability_score": 10,
        }
        response = Mock()
        response.content = b"json"
        response.json.return_value = payload
        client.session.request = Mock(return_value=response)
        self.assertIs(client.get_category("Fairphone_5"), payload)

    def test_request_options_do_not_collide_with_defaults(self):
        client = IFixitAPIClient()
        response = Mock()
        response.content = b"json"
        client.session.request = Mock(return_value=response)
        client._request("GET", "/guides", timeout=7, verify=True)
        self.assertEqual(client.session.request.call_args.kwargs["timeout"], 7)
        self.assertIs(client.session.request.call_args.kwargs["verify"], True)

    def test_invalid_pin_is_rejected(self):
        for value in ["", "ab" * 20, "not a fingerprint", 7]:
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                IFixitAPIClient(certificate_fingerprint=value)

    def test_pinned_adapters_do_not_change_other_clients(self):
        original = (
            IFixitAPIClient()
            .session.get_adapter("https://")
            .poolmanager.pool_classes_by_scheme["https"]
        )
        pinned = IFixitAPIClient(certificate_fingerprint="ab" * 32)
        self.assertIsNot(
            pinned.session.get_adapter("https://").poolmanager.pool_classes_by_scheme[
                "https"
            ],
            original,
        )
        self.assertIs(
            IFixitAPIClient()
            .session.get_adapter("https://")
            .poolmanager.pool_classes_by_scheme["https"],
            original,
        )

    def test_pin_rejects_http_and_disabling_verification(self):
        client = IFixitAPIClient(certificate_fingerprint="ab" * 32)
        with self.assertRaises(requests.exceptions.SSLError):
            client.session.get("http://127.0.0.1:9", timeout=1)
        with self.assertRaises(ValueError):
            client.session.get("https://localhost:9", verify=False, timeout=1)
