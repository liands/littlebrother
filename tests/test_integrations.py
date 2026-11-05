"""Offline regression coverage for API adapters and failure semantics."""

import os
import unittest
from unittest.mock import patch

from core.bssidFinder import lookup_bssid
from core.facebookSearchTool import facebookSearchTool
from core.instagramSearchTool import instagramSearchTool
from core.ipFinder import lookup_ip
from core.leaked import leaked
from core.searchInfoNumero import searchInfoNumero
from core.twitterSearchTool import twitterSearchTool
from lib.http import IntegrationError


META_ENV = {"META_ACCESS_TOKEN": "test-token", "META_GRAPH_VERSION": "v26.0", "INSTAGRAM_USER_ID": "123"}
IG_PROFILE = {"id": "123", "username": "authorized", "name": "Authorized",
              "followers_count": 0, "follows_count": 1, "media_count": 2}
X_PROFILE = {"data": {"id": "123", "username": "example", "name": "Example",
                       "description": "Bio", "protected": False, "verified": False,
                       "public_metrics": {"followers_count": 0, "following_count": 2, "tweet_count": 3}}}


class CredentialTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    @patch("core.twitterSearchTool.get_json")
    def test_missing_x_token_never_requests_or_claims_absence(self, request):
        client = twitterSearchTool().getInfoProfile("example")
        self.assertFalse(client.success)
        self.assertEqual(client.status, "unavailable")
        self.assertIn("X_BEARER_TOKEN", client.error)
        self.assertEqual(client.manual_url, "https://x.com/example")
        self.assertIsNone(client.birth)
        request.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch("lib.integrations.get_json")
    def test_missing_meta_credentials_never_request(self, request):
        for client, call in ((instagramSearchTool(), lambda c: c.getInfo("example")),
                             (facebookSearchTool(), lambda c: c.getInfoProfile("123"))):
            with self.subTest(platform=type(client).__name__):
                call(client)
                self.assertEqual(client.status, "unavailable")
                self.assertIsNone(client.name)
                self.assertIsNotNone(client.manual_url)
        request.assert_not_called()

    @patch.dict(os.environ, {"META_ACCESS_TOKEN": "test", "META_GRAPH_VERSION": "v26.0/../me"}, clear=True)
    @patch("lib.integrations.get_json")
    def test_meta_version_path_injection_is_blocked(self, request):
        self.assertEqual(facebookSearchTool().getInfoProfile("me").status, "unavailable")
        request.assert_not_called()


class XTests(unittest.TestCase):
    @patch.dict(os.environ, {"X_BEARER_TOKEN": "test-token"}, clear=True)
    @patch("core.twitterSearchTool.get_json", return_value=X_PROFILE)
    def test_lookup_uses_official_api_and_header(self, request):
        client = twitterSearchTool().getInfoProfile("https://twitter.com/example/?ref=manual")
        self.assertTrue(client.success)
        self.assertEqual(client.status, "ok")
        self.assertEqual(client.posts, 3)
        self.assertEqual(client.followers, 0)
        self.assertEqual(client.urlAccount, "https://x.com/example")
        args, kwargs = request.call_args
        self.assertEqual(args[0], "https://api.x.com/2/users/by/username/example")
        self.assertEqual(kwargs["headers"], {"Authorization": "Bearer test-token"})
        self.assertNotIn("test-token", args[0])

    @patch.dict(os.environ, {"X_BEARER_TOKEN": "test-token"}, clear=True)
    @patch("core.twitterSearchTool.get_json", side_effect=[X_PROFILE, IntegrationError("Timeout", code="timeout")])
    def test_failure_resets_previous_profile(self, request):
        client = twitterSearchTool().getInfoProfile("example")
        self.assertTrue(client.success)
        client.getInfoProfile("different")
        self.assertFalse(client.success)
        self.assertEqual(client.status, "error")
        self.assertIsNone(client.name)
        self.assertIsNone(client.id)

    @patch.dict(os.environ, {"X_BEARER_TOKEN": "test-token"}, clear=True)
    @patch("core.twitterSearchTool.get_json", return_value={"data": {"id": "1", "username": "example", "name": "Example", "public_metrics": {"followers_count": -1}}})
    def test_bad_metrics_do_not_leave_partial_profile(self, request):
        client = twitterSearchTool().getInfoProfile("example")
        self.assertEqual(client.status, "error")
        self.assertIsNone(client.name)

    @patch("core.twitterSearchTool.get_json")
    def test_untrusted_profile_url_is_never_fetched(self, request):
        for value in ("https://localhost/example", "https://x.com@evil.test/example", "https://x.com/example/status/1", "https://x.com:8443/example", "../example"):
            with self.subTest(value=value):
                self.assertEqual(twitterSearchTool().getInfoProfile(value).status, "error")
        request.assert_not_called()

    @patch.dict(os.environ, {"X_BEARER_TOKEN": "test-token"}, clear=True)
    @patch("core.twitterSearchTool.get_json")
    def test_known_resource_error_is_distinct_from_api_failure(self, request):
        request.return_value = {"errors": [{"type": "https://api.x.com/2/problems/resource-not-found"}]}
        self.assertEqual(twitterSearchTool().getInfoProfile("example").status, "not_found")
        request.return_value = {"errors": [{"title": "Forbidden"}]}
        self.assertEqual(twitterSearchTool().getInfoProfile("example").status, "error")

    @patch.dict(os.environ, {"X_BEARER_TOKEN": "test-token"}, clear=True)
    @patch("core.twitterSearchTool.get_json", return_value={"meta": {"result_count": 0}})
    def test_search_empty_is_success_only_for_valid_response(self, request):
        client = twitterSearchTool()
        self.assertEqual(client.searchTwitter("some search"), [])
        self.assertTrue(client.success)
        request.return_value = {}
        self.assertEqual(client.searchTwitter("some search"), [])
        self.assertFalse(client.success)


class MetaTests(unittest.TestCase):
    @patch.dict(os.environ, META_ENV, clear=True)
    @patch("lib.integrations.get_json", return_value=IG_PROFILE)
    def test_authorized_instagram_maps_zero_counts(self, request):
        client = instagramSearchTool().getInfo("authorized")
        self.assertTrue(client.success)
        self.assertEqual(client.followers, 0)
        self.assertTrue(client._authorized_profile)
        self.assertEqual(client.urlAccount, "https://www.instagram.com/authorized/")
        self.assertIsNone(client.email)
        self.assertIsNone(client.private)
        self.assertEqual(request.call_args.kwargs["headers"]["Authorization"], "Bearer test-token")

    @patch.dict(os.environ, META_ENV, clear=True)
    @patch("lib.integrations.get_json", side_effect=[IG_PROFILE, {"business_discovery": {"id": "456", "username": "other", "name": "Other"}}])
    def test_instagram_business_discovery_is_explicit(self, request):
        client = instagramSearchTool().getInfo("other")
        self.assertTrue(client.success)
        self.assertFalse(client._authorized_profile)
        self.assertEqual(client.id, "456")
        self.assertIn("business_discovery.username(other)", request.call_args.kwargs["params"]["fields"])

    @patch.dict(os.environ, META_ENV, clear=True)
    @patch("lib.integrations.get_json", side_effect=[IG_PROFILE, {"id": "123"}])
    def test_instagram_inaccessible_profile_is_not_reported_missing(self, request):
        client = instagramSearchTool().getInfo("other")
        self.assertFalse(client.success)
        self.assertEqual(client.status, "unavailable")
        self.assertIsNone(client.name)

    @patch.dict(os.environ, META_ENV, clear=True)
    @patch("lib.integrations.get_json", side_effect=[IG_PROFILE, {"data": [{"id": "99", "media_type": "IMAGE", "media_url": "https://scontent.cdninstagram.com/image.jpg", "timestamp": "2026-01-01T00:00:00+0000"}, {"id": "100", "media_type": "VIDEO", "media_url": "https://scontent.cdninstagram.com/video.mp4"}]}])
    def test_authorized_media_returns_images_without_off_by_one(self, request):
        client = instagramSearchTool().getInfo("authorized")
        pictures = client.get_picturesInfo("authorized")
        self.assertTrue(client.success)
        self.assertEqual(len(pictures), 1)
        self.assertEqual(pictures[0]["type_media"], "Photo")
        self.assertIn("/123/media", request.call_args.args[0])
        self.assertEqual(request.call_args.kwargs["params"]["limit"], 12)

    @patch.dict(os.environ, META_ENV, clear=True)
    @patch("lib.integrations.get_json", side_effect=[IG_PROFILE, {"data": []}])
    def test_empty_authorized_media_is_valid(self, request):
        client = instagramSearchTool().getInfo("authorized")
        self.assertEqual(client.get_picturesInfo("authorized"), {})
        self.assertTrue(client.success)

    @patch("lib.integrations.get_json")
    def test_unsupported_meta_searches_remain_offline(self, request):
        client = instagramSearchTool()
        self.assertEqual(client.searchInsta("name"), [])
        self.assertEqual(client.searchByTag("tag"), {})
        self.assertEqual(client.getMediaWithLoc("city"), {})
        self.assertEqual(client.status, "unavailable")
        facebook = facebookSearchTool()
        self.assertEqual(facebook.searchFacebook("name"), [])
        self.assertEqual(facebook.getInfoProfile("username").status, "unavailable")
        request.assert_not_called()

    @patch.dict(os.environ, META_ENV, clear=True)
    @patch("lib.integrations.get_json", return_value={"id": "123", "name": "Authorized"})
    def test_facebook_profile_php_and_scoped_id(self, request):
        client = facebookSearchTool().getInfoProfile("https://www.facebook.com/profile.php?id=123")
        self.assertTrue(client.success)
        self.assertEqual(client.facebookId, "123")
        self.assertIsNone(client.username)
        self.assertIsNone(client.job)
        self.assertEqual(request.call_args.args[0], "https://graph.facebook.com/v26.0/123")

    @patch.dict(os.environ, META_ENV, clear=True)
    @patch("lib.integrations.get_json", return_value={"error": {"message": "reflected secret test-token"}})
    def test_meta_raw_error_body_is_not_disclosed(self, request):
        client = facebookSearchTool().getInfoProfile("me")
        self.assertEqual(client.status, "error")
        self.assertNotIn("test-token", client.error)


class BreachTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    @patch("core.leaked.get_json")
    def test_email_requires_key_and_does_not_claim_clear(self, request):
        client = leaked()
        with self.assertRaises(IntegrationError):
            client.email("example@example.com")
        self.assertEqual(client.status, "unavailable")
        request.assert_not_called()

    @patch.dict(os.environ, {"HIBP_API_KEY": "a" * 32}, clear=True)
    @patch("core.leaked.get_json", return_value=[{"Title": "Example", "Domain": "example.com", "BreachDate": "2024-01-01"}])
    def test_email_v3_encoding_and_schema(self, request):
        result = leaked().email("user+tag@example.com")
        self.assertEqual(result, [{"Title": "Example", "Domain": "example.com", "Date": "2024-01-01"}])
        self.assertIn("/api/v3/breachedaccount/user%2Btag%40example.com", request.call_args.args[0])
        self.assertEqual(request.call_args.kwargs["params"], {"truncateResponse": "false"})
        self.assertEqual(request.call_args.kwargs["headers"]["hibp-api-key"], "a" * 32)

    @patch.dict(os.environ, {"HIBP_API_KEY": "a" * 32}, clear=True)
    @patch("core.leaked.get_json")
    def test_only_hibp_404_represents_known_negative(self, request):
        request.side_effect = IntegrationError("Not found", code="http_404", status_code=404)
        client = leaked()
        self.assertEqual(client.email("user@example.com"), [])
        self.assertTrue(client.success)
        self.assertEqual(client.status, "not_found")
        for code in ("http_401", "http_403", "http_429", "http_503", "timeout"):
            with self.subTest(code=code):
                request.side_effect = IntegrationError("Unavailable", code=code)
                with self.assertRaises(IntegrationError):
                    client.email("user@example.com")
                self.assertFalse(client.success)

    @patch.dict(os.environ, {"HIBP_API_KEY": "a" * 32}, clear=True)
    @patch("core.leaked.get_json", return_value={"error": "unexpected"})
    def test_hibp_bad_json_schema_is_failure(self, request):
        with self.assertRaises(IntegrationError):
            leaked().email("user@example.com")

    @patch("core.leaked.get_text", return_value="A" * 35 + ":7\r\n" + "B" * 35 + ":0\r\n")
    def test_pwned_password_only_sends_prefix(self, request):
        digest = "12345" + "A" * 35
        self.assertEqual(leaked().check_password_hash(digest.lower()), 7)
        self.assertEqual(request.call_args.args[0], "https://api.pwnedpasswords.com/range/12345")
        self.assertNotIn(digest, str(request.call_args))
        self.assertEqual(request.call_args.kwargs["headers"]["Add-Padding"], "true")

    @patch("core.leaked.get_text", return_value="B" * 35 + ":7\n")
    def test_pwned_password_absence_is_zero(self, request):
        self.assertEqual(leaked().check_password_hash("A" * 40), 0)

    @patch("core.leaked.get_text", return_value="<html>Unavailable</html>")
    def test_bad_password_response_never_means_safe(self, request):
        with self.assertRaises(IntegrationError):
            leaked().check_password_hash("A" * 40)

    @patch("core.leaked.get_text")
    def test_old_hash_recovery_and_non_sha1_make_no_request(self, request):
        with self.assertRaises(IntegrationError):
            leaked().hash("A" * 32)
        for value in ("plaintext", "A" * 32, "G" * 40):
            with self.subTest(value=value), self.assertRaises(IntegrationError):
                leaked().check_password_hash(value)
        request.assert_not_called()


class NetworkMetadataTests(unittest.TestCase):
    @patch("core.ipFinder.get_json")
    def test_invalid_private_and_hostname_ip_are_not_sent(self, request):
        for address in ("127.0.0.1", "192.168.1.1", "::1", "example.com", "https://8.8.8.8", "224.0.0.1"):
            with self.subTest(address=address), self.assertRaises(IntegrationError):
                lookup_ip(address)
        request.assert_not_called()

    @patch("core.ipFinder.get_json", return_value={"success": True, "ip": "8.8.8.8", "country": "US", "latitude": 1, "longitude": 2, "connection": {"isp": "Example"}})
    def test_ip_https_and_expected_address(self, request):
        result = lookup_ip("8.8.8.8")
        self.assertEqual(result["isp"], "Example")
        request.assert_called_once_with("https://ipwho.is/8.8.8.8")
        request.return_value["ip"] = "1.1.1.1"
        with self.assertRaises(IntegrationError):
            lookup_ip("8.8.8.8")

    @patch("core.bssidFinder.get_json", return_value={"result": 200, "data": {"lat": "1.2", "lon": "2.3", "range": 140}})
    def test_bssid_uses_documented_path_and_open_dataset(self, request):
        result = lookup_bssid("00-11-22-33-44-55")
        self.assertEqual(result["bssid"], "00:11:22:33:44:55")
        self.assertEqual(result["accuracy_m"], 140)
        self.assertEqual(request.call_args.args[0], "https://api.mylnikov.org/geolocation/wifi")
        self.assertEqual(request.call_args.kwargs["params"]["data"], "open")

    @patch("core.bssidFinder.get_json")
    def test_bssid_no_result_differs_from_service_failure(self, request):
        request.return_value = {"result": 404}
        self.assertIsNone(lookup_bssid("001122334455"))
        for data in ({"result": 503}, {"result": []}, {"result": 200, "data": {"lat": "nan", "lon": 2}}):
            with self.subTest(data=data):
                request.return_value = data
                with self.assertRaises(IntegrationError):
                    lookup_bssid("001122334455")

    @patch("core.bssidFinder.get_json")
    def test_randomized_multicast_and_reserved_bssid_are_not_sent(self, request):
        for value in ("02:00:00:00:00:00", "01:00:00:00:00:00", "00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
            with self.subTest(value=value), self.assertRaises(IntegrationError):
                lookup_bssid(value)
        request.assert_not_called()

    @patch.dict(os.environ, {"X_BEARER_TOKEN": "test-token"}, clear=True)
    @patch("core.twitterSearchTool.get_json")
    def test_x_unsupported_query_uses_manual_search_without_request(self, request):
        client = twitterSearchTool()
        self.assertEqual(client.searchTwitter("João da Silva"), [])
        self.assertEqual(client.status, "unavailable")
        self.assertIn("q=Jo%C3%A3o", client.manual_url)
        request.assert_not_called()

    def test_brazil_number_is_local_metadata_without_carrier_claims(self):
        result = searchInfoNumero().search("+55 (85) 99999-1234")
        self.assertTrue(result.success)
        self.assertEqual(result.e164, "+5585999991234")
        self.assertIn("CE", result.location)
        self.assertIn("não é a localização atual", result.location)
        self.assertIsNone(result.city)
        self.assertIsNone(result.operator)

    def test_number_validation_and_fr_no_old_geographic_claim(self):
        client = searchInfoNumero().search("+33 1 23 45 67 89")
        self.assertTrue(client.success)
        self.assertIsNone(client.location)
        self.assertEqual(client.e164, "+33123456789")
        client.search("+1 202 555 0100")
        self.assertEqual(client.status, "unavailable")
        self.assertIsNone(client.e164)
        for value in ("not a number", "8599991234", "00999991234", ""):
            with self.subTest(value=value):
                self.assertEqual(searchInfoNumero().search(value).status, "error")


if __name__ == "__main__":
    unittest.main()
