"""Regressions from the official OpenAPI snapshot and public API responses."""

import unittest
from unittest.mock import Mock
import requests
from ifixit_client import IFixitAPIClient
from ifixit_client.client import Namespace
from ifixit_client.models import Guide, User, Wiki


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.client = IFixitAPIClient(api_key="example-key")
        self.client.session.request = Mock(
            return_value=Mock(
                content=b"{}",
                headers={"Content-Type": "application/json"},
                json=Mock(return_value={}),
            )
        )

    def request(self):
        return self.client.session.request.call_args.kwargs

    def test_key_and_legacy_token_use_different_schemes(self):
        self.assertEqual(
            self.client._build_headers()["Authorization"], "Bearer example-key"
        )
        self.assertEqual(
            IFixitAPIClient(auth_token="legacy")._build_headers()["Authorization"],
            "api legacy",
        )
        self.assertEqual(
            IFixitAPIClient(auth_token="oidc", auth_scheme="Bearer")._build_headers()[
                "Authorization"
            ],
            "Bearer oidc",
        )
        with self.assertRaises(ValueError):
            IFixitAPIClient(auth_token="legacy", api_key="key")
        with self.assertRaises(ValueError):
            IFixitAPIClient(auth_scheme="Basic")

    def test_login_bootstraps_without_token_and_does_not_log_credentials(self):
        self.client = IFixitAPIClient()
        self.client.session.request = Mock(
            return_value=Mock(content=b"{}", headers={}, json=Mock(return_value={}))
        )
        with self.assertLogs("ifixit_client.client", level="DEBUG") as logs:
            self.client.create_user_token(
                {"email": "private@example.org", "password": "secret-password"}
            )
        self.assertNotIn("Authorization", self.request()["headers"])
        self.assertNotIn("secret-password", str(logs.output))
        self.assertNotIn("private@example.org", str(logs.output))

    def test_legacy_deprecation_warns_without_rewriting_the_request(self):
        with self.assertWarnsRegex(DeprecationWarning, "get_user_badges"):
            self.client.get_badges()
        self.assertTrue(self.request()["url"].endswith("/badges"))
        self.assertIn("not confirmed removed", self.client.get_badges.__deprecated__)

    def test_document_uses_media_route(self):
        with self.assertWarns(UserWarning):
            self.client.get_document("123")
        self.assertTrue(self.request()["url"].endswith("/media/documents/123"))

    def test_revision_queries_for_existing_writers(self):
        calls = [
            lambda: self.client.make_guide_public(1, revisionid=23),
            lambda: self.client.make_guide_private(1, revisionid=23),
            lambda: self.client.update_guide_step(
                1, 2, {"title": "Step"}, revisionid=23
            ),
            lambda: self.client.delete_guide_step(1, 2, revisionid=23),
            lambda: self.client.update_guide_step_order(
                1, {"order": [2]}, revisionid=23
            ),
            lambda: self.client.update_wiki(
                Namespace.CATEGORY, "Phone", {}, revisionid=23
            ),
            lambda: self.client.delete_wiki(Namespace.CATEGORY, "Phone", revisionid=23),
        ]
        for call in calls:
            with self.subTest(call=call):
                call()
                self.assertEqual(self.request()["params"], {"revisionid": 23})
        self.client.session.request.reset_mock()
        with self.assertRaisesRegex(ValueError, "revisionid"):
            self.client.make_guide_public(1)
        self.client.session.request.assert_not_called()

    def test_wiki_revert_uses_queries_and_does_not_mutate_input(self):
        data = {"revisionid": 12, "to_revisionid": 8}
        self.client.revert_wiki(Namespace.CATEGORY, "Phone", data)
        self.assertEqual(self.request()["params"], data)
        self.assertIsNone(self.request()["json"])
        self.assertEqual(data, {"revisionid": 12, "to_revisionid": 8})

    def test_guide_supports_language_and_revision(self):
        self.client.get_guide(1, params={"langid": "de", "revisionid": 2})
        self.assertEqual(self.request()["params"], {"langid": "de", "revisionid": 2})

    def test_call_encodes_path_segments(self):
        self.client.call(
            "getWiki", path_params={"namespace": "CATEGORY", "title": "A/B?x#y"}
        )
        self.assertTrue(self.request()["url"].endswith("/wikis/CATEGORY/A%2FB%3Fx%23y"))

    def test_call_rejects_missing_parameters_before_network(self):
        for operation, kwargs in [
            ("notAnOperation", {}),
            ("getWiki", {}),
            ("login", {"json": {"email": "x"}}),
            ("login", {}),
        ]:
            with (
                self.subTest(operation=operation, kwargs=kwargs),
                self.assertRaises(ValueError),
            ):
                self.client.call(operation, **kwargs)
        self.client.session.request.assert_not_called()

    def test_chat_streams_from_documented_server_without_reading_content(self):
        response = Mock(spec=requests.Response)
        self.client.session.request.return_value = response
        result = self.client.call(
            "chat", json={"chatId": "example", "messages": [], "persona": "fixbot"}
        )
        self.assertIs(result, response)
        self.assertEqual(
            self.request()["url"], "https://fixbot.ifixit.com/api/2.0/chat"
        )
        self.assertTrue(self.request()["stream"])
        self.assertEqual(self.request()["headers"]["Content-Type"], "application/json")

    def test_binary_media_upload_and_required_filename(self):
        payload = b"example-document"
        self.client.call("uploadMedia", params={"file": "example.pdf"}, body=payload)
        options = self.request()
        self.assertEqual(options["data"], payload)
        self.assertIsNone(options["json"])
        self.assertEqual(options["headers"]["Content-Type"], "application/octet-stream")
        self.client.session.request.reset_mock()
        with self.assertRaisesRegex(ValueError, "file"):
            self.client.call("uploadMedia", body=payload)
        self.client.session.request.assert_not_called()

    def test_image_upload_uses_binary_body_with_concrete_type(self):
        self.client.upload_user_image(
            b"png-example", file="example.png", content_type="image/png"
        )
        self.assertEqual(self.request()["data"], b"png-example")
        self.assertEqual(self.request()["params"], {"file": "example.png"})
        self.assertEqual(self.request()["headers"]["Content-Type"], "image/png")
        with self.assertRaisesRegex(ValueError, "raw bytes"):
            self.client.upload_user_image({"file": "bad-json"})
        with self.assertRaisesRegex(ValueError, "content_type"):
            self.client.call("uploadImage", params={"file": "example.png"}, body=b"png")

    def test_non_json_response_and_empty_body(self):
        response = self.client.session.request.return_value
        response.headers = {"Content-Type": "application/xml"}
        response.text = "<guide />"
        self.assertEqual(self.client.get_guide(1, params={"type": "XML"}), "<guide />")
        response.content = b""
        self.assertIsNone(self.client.get_guide(1))

    def test_models_accept_current_payloads_and_preserve_new_fields(self):
        user = User.model_validate(
            {
                "userid": 1,
                "username": "user",
                "join_date": 0,
                "reputation": 0,
                "teams": [],
                "new_field": True,
            }
        )
        self.assertIsNone(user.url)
        self.assertTrue(user.model_dump()["new_field"])
        wiki = Wiki.model_validate(
            {
                "wikiid": 1,
                "title": "Phone",
                "namespace": "CATEGORY",
                "revisionid": 2,
                "modified_date": 0,
                "contents_raw": "",
                "contents_rendered": "",
                "children": ["Phone 2"],
            }
        )
        self.assertIsNone(wiki.url)
        self.assertEqual(wiki.model_dump()["children"], ["Phone 2"])
        guide = Guide.model_validate(
            {
                "guideid": 1,
                "title": "Phone",
                "category": "Phone",
                "difficulty": "Easy",
                "revisionid": 2,
                "modified_date": 0,
                "prereq_modified_date": 0,
                "public": True,
                "url": "https://www.ifixit.com/Guide/1",
                "userid": 1,
                "username": "user",
                "flags": [{"flagid": "featured"}],
                "locale": "de",
                "summary": "summary",
                "time_required_max": 60,
            }
        )
        for field in ("flags", "locale", "summary", "time_required_max"):
            self.assertIn(field, guide.model_dump())
