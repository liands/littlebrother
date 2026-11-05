from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from core import checkleaked as service
from core import email_lookup as unified
from core.searchEmail import SearchEmail
from lib.email_config import load_email_config
from lib.http import IntegrationError

ROOT = Path(__file__).resolve().parents[1]
KEY = 'example-checkleaked-token'
EMAIL = 'user@example.com'


def response():
    return {'success': True, 'found': 1, 'result': [{'email': EMAIL, 'password': 'NEVER-PRINT-PASSWORD',
            'hash': 'NEVER-PRINT-HASH', 'username': 'NEVER-PRINT-USERNAME',
            'source': {'name': 'Example Breach', 'date': '2020-01-01'}}]}


def config():
    return {'keys': {'HIBP_API_KEY': '', 'HUNTER_API_KEY': '', 'KICKBOX_API_KEY': '', 'CHECKLEAKED_API_KEY': KEY},
            'hibp_enabled': False, 'hunter_enabled': False, 'kickbox_enabled': False,
            'checkleaked_enabled': True, 'hunter_max_attempts': 2, 'kickbox_timeout_ms': 6000}


class CheckLeakedTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '0'})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_response_whitelist_does_not_include_credentials_or_record_values(self):
        parsed = service.parse_results(response(), EMAIL, KEY)
        text = json.dumps(parsed)
        for secret in ('NEVER-PRINT-PASSWORD', 'NEVER-PRINT-HASH', 'NEVER-PRINT-USERNAME', KEY, EMAIL):
            self.assertNotIn(secret, text)
        self.assertEqual(parsed['count'], 1)
        self.assertEqual(parsed['sources'][0]['name'], 'Example Breach')
        self.assertIn('senha/credencial (conteúdo omitido)', parsed['fields'])

    def test_empty_success_and_positive_without_rows_are_distinct(self):
        parsed = service.parse_results({'success': True, 'found': 0, 'result': []}, EMAIL, KEY)
        self.assertEqual(parsed['count'], 0)
        self.assertFalse(parsed['partial'])
        parsed = service.parse_results({'success': True, 'found': 7, 'result': []}, EMAIL, KEY)
        self.assertEqual(parsed['count'], 7)
        self.assertTrue(parsed['partial'])

    def test_malformed_schema_never_becomes_absence(self):
        for data in ({'success': False, 'error': 'RAW-SECRET'}, {'success': True, 'found': False, 'result': []},
                     {'success': True, 'found': -1, 'result': []}, {'success': True, 'found': 0, 'result': [{}]},
                     {'success': True, 'found': 1, 'result': 'wrong'}, []):
            with self.subTest(data=data), self.assertRaises(IntegrationError):
                service.parse_results(data, EMAIL, KEY)

    def test_foreign_or_invalid_email_is_not_shown(self):
        for value in ('another@example.com', 'invalid-email'):
            data = response()
            data['result'][0]['email'] = value
            with self.subTest(value=value), self.assertRaises(IntegrationError):
                service.parse_results(data, EMAIL, KEY)

    def test_sources_are_deduplicated_and_large_results_marked_partial(self):
        data = response()
        data['result'] *= 4
        data['found'] = 10
        with patch.object(service, 'MAX_ROWS', 2):
            parsed = service.parse_results(data, EMAIL, KEY)
        self.assertTrue(parsed['partial'])
        self.assertEqual(len(parsed['sources']), 1)
        self.assertEqual(parsed['sources'][0]['records'], 2)

    def test_control_characters_and_reflected_key_are_sanitized(self):
        data = response()
        data['result'][0]['source']['name'] = '\x1b[2J' + KEY
        parsed = service.parse_results(data, EMAIL, KEY)
        self.assertNotIn(KEY, json.dumps(parsed))
        self.assertNotIn('\x1b', parsed['sources'][0]['name'])

    def test_one_exact_email_call_header_auth_no_optional_key_no_retry(self):
        with patch.object(service, '_reserve_attempt') as reserve, patch.object(service, 'get_json', return_value=response()) as request:
            parsed = service.check_email(EMAIL, KEY, config())
        reserve.assert_called_once_with(KEY)
        request.assert_called_once_with('https://api.checkleaked.cc/api/leak_check',
                params={'check': EMAIL, 'type': 'email'}, headers={'api-key': KEY})
        self.assertEqual(parsed['count'], 1)
        with patch.object(service, '_reserve_attempt'), patch.object(service, 'get_json', side_effect=IntegrationError('error', code='timeout')) as request:
            with self.assertRaises(IntegrationError):
                service.check_email(EMAIL, KEY, config())
            self.assertEqual(request.call_count, 1)

    def test_offline_and_invalid_input_never_reserve_quota_or_query(self):
        with patch.object(service, '_reserve_attempt') as reserve, patch.object(service, 'get_json') as request:
            with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '1'}), self.assertRaises(IntegrationError):
                service.check_email(EMAIL, KEY, config())
            with self.assertRaises(ValueError):
                service.check_email('bad-email', KEY, config())
            with self.assertRaises(IntegrationError):
                service.check_email(EMAIL, '', config())
        reserve.assert_not_called()
        request.assert_not_called()

    def test_local_budget_cooldown_two_per_rolling_24h_and_expiration(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.work') as folder:
            service._reserve_attempt(KEY, directory=folder, now=1000)
            with self.assertRaises(IntegrationError) as cooldown:
                service._reserve_attempt(KEY, directory=folder, now=1020)
            self.assertEqual(cooldown.exception.code, 'cooldown')
            service._reserve_attempt(KEY, directory=folder, now=1061)
            with self.assertRaises(IntegrationError) as limit:
                service._reserve_attempt(KEY, directory=folder, now=1200)
            self.assertEqual(limit.exception.code, 'local_limit')
            service._reserve_attempt(KEY, directory=folder, now=1000+86401)
            database = Path(folder)/'checkleaked_usage.sqlite3'
            self.assertNotIn(KEY.encode(), database.read_bytes())
            self.assertNotIn(EMAIL.encode(), database.read_bytes())
            with contextlib.closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 2)

    def test_budget_is_atomic_across_concurrent_connections(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.work') as folder:
            def reserve(_):
                try:
                    service._reserve_attempt(KEY, directory=folder, now=1000)
                    return True
                except IntegrationError:
                    return False
            with ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(reserve, range(6)))
            self.assertEqual(sum(results), 1)

    def test_budget_failure_or_cooldown_blocks_http(self):
        with patch.object(service, '_reserve_attempt', side_effect=IntegrationError('quota', code='local_limit')), patch.object(service, 'get_json') as request:
            result = unified._provider('CheckLeaked', EMAIL, KEY, config())
        self.assertEqual(result['state'], 'local_limit')
        request.assert_not_called()
        with tempfile.TemporaryDirectory(dir=ROOT/'.work') as folder, patch('core.checkleaked.Path.is_symlink', return_value=True):
            with self.assertRaises(IntegrationError) as error:
                service._reserve_attempt(KEY, directory=folder)
            self.assertEqual(error.exception.code, 'configuration')

    def test_enabled_and_key_does_not_automatically_spend_credit(self):
        with patch.object(unified, '_checkleaked') as query:
            report = unified.lookup_email(EMAIL, config=config())
        self.assertEqual(report['providers'][-1]['state'], 'not_requested')
        query.assert_not_called()

    def test_authorized_unified_lookup_and_render_exclude_credentials(self):
        parsed = service.parse_results(response(), EMAIL, KEY)
        with patch.object(unified, '_checkleaked', return_value=parsed) as query:
            report = unified.lookup_email(EMAIL, config=config(), consult_checkleaked=True)
        query.assert_called_once_with(EMAIL, KEY, config())
        text = unified.render_email_lookup(report)
        self.assertIn('Example Breach', text)
        self.assertIn('inconclusiva', unified.deliverability_summary(report))
        for secret in (KEY, 'NEVER-PRINT-PASSWORD', 'NEVER-PRINT-HASH', 'NEVER-PRINT-USERNAME'):
            self.assertNotIn(secret, text)

    def test_declining_or_accepting_cli_prompt_controls_the_query(self):
        parsed = service.parse_results(response(), EMAIL, KEY)
        for answer, expected in (('', False), ('n', False), ('s', True)):
            with patch('core.searchEmail.load_email_config', return_value=config()), \
                    patch('builtins.input', side_effect=[EMAIL, answer]), patch.object(unified, '_checkleaked', return_value=parsed) as query, \
                    contextlib.redirect_stdout(io.StringIO()):
                SearchEmail()
            self.assertEqual(query.called, expected)

    def test_cli_invalid_confirmation_does_not_start_any_lookup(self):
        with patch('core.searchEmail.load_email_config', return_value=config()), patch('builtins.input', side_effect=[EMAIL, 'maybe']), \
                patch('core.searchEmail.lookup_email') as query, self.assertRaises(ValueError):
            SearchEmail()
        query.assert_not_called()

    def test_server_errors_do_not_leak_key_or_claim_no_findings(self):
        for code, state in (('http_401', 'auth_error'), ('http_429', 'rate_limited'), ('timeout', 'error')):
            with patch.object(service, '_reserve_attempt'), patch.object(service, 'get_json', side_effect=IntegrationError(KEY, code=code)):
                result = unified._provider('CheckLeaked', EMAIL, KEY, config())
            self.assertEqual(result['state'], state)
            self.assertNotIn(KEY, json.dumps(result))
            self.assertNotIn('Nenhum registro', unified.render_email_lookup({'email': EMAIL, 'providers': [result]}))

    def test_template_adds_key_and_disables_costly_source_by_default(self):
        with patch.dict(os.environ, {'LITTLEBROTHER_CONFIG': str(ROOT/'configuracao.exemplo.ini')}, clear=True):
            settings = load_email_config()
        self.assertEqual(settings['keys']['CHECKLEAKED_API_KEY'], '')
        self.assertFalse(settings['checkleaked_enabled'])

    def test_official_sdk_results_without_success_are_supported(self):
        for status in ('missing', None, True):
            data = {'found': 1, 'results': [{'line': 'NEVER-PRINT-CREDENTIAL-LINE',
                    'lastBreach': {'Name': 'SDK Breach', 'BreachDate': '2021-01-01'}}]}
            if status != 'missing':
                data['success'] = status
            with self.subTest(status=status):
                parsed = service.parse_results(data, EMAIL, KEY)
                self.assertEqual(parsed['sources'][0]['name'], 'SDK Breach')
                self.assertNotIn('NEVER-PRINT-CREDENTIAL-LINE', json.dumps(parsed))

    def test_sdk_sources_uppercase_metadata_are_deduplicated_per_row(self):
        data = {'found': 1, 'results': [{'email': EMAIL, 'sources': [
                {'Name': 'SDK Source', 'BreachDate': '2021'}, {'Name': 'SDK Source', 'BreachDate': '2021'},
                {'Leak': 'Second Source', 'BreachDate': '2022'}]}]}
        parsed = service.parse_results(data, EMAIL, KEY)
        self.assertEqual(len(parsed['sources']), 2)
        self.assertEqual(parsed['sources'][0]['records'], 1)

    def test_positive_found_count_need_not_equal_sdk_result_row_count(self):
        data = {'found': 1, 'results': [{'source': {'name': 'one'}}, {'source': {'name': 'two'}}]}
        parsed = service.parse_results(data, EMAIL, KEY)
        self.assertEqual(parsed['rows_received'], 2)
        self.assertEqual(parsed['count'], 1)

    def test_ambiguous_or_incomplete_sdk_payload_is_not_empty_success(self):
        for data in ({'message': 'empty'}, {'success': 1, 'found': 0, 'results': []},
                     {'found': 0}, {'found': 1, 'result': [], 'results': [{}]},
                     {'found': 1, 'results': [{'sources': 'wrong'}]},
                     {'found': 1, 'results': [{'lastBreach': 'wrong'}]}):
            with self.subTest(data=data), self.assertRaises(IntegrationError):
                service.parse_results(data, EMAIL, KEY)

    def test_body_errors_are_classified_without_reflecting_secrets(self):
        cases = [('Invalid API key SECRET', 'checkleaked_auth'), ('Daily limit exceeded SECRET', 'checkleaked_quota'),
                 ('Cooldown: wait before searching SECRET', 'checkleaked_cooldown'),
                 ('Invalid query SECRET', 'checkleaked_params'), ('Upstream unavailable SECRET', 'checkleaked_upstream'),
                 ('Unexpected provider detail SECRET', 'checkleaked_error')]
        for message, code in cases:
            with self.subTest(code=code), self.assertRaises(IntegrationError) as error:
                service.parse_results({'success': False, 'error': message}, EMAIL, KEY)
            self.assertEqual(error.exception.code, code)
            self.assertNotIn('SECRET', str(error.exception))

    def test_explicit_failure_is_not_overridden_by_zero_results(self):
        with self.assertRaises(IntegrationError) as error:
            service.parse_results({'success': False, 'found': 0, 'results': [], 'error': 'No results found'}, EMAIL, KEY)
        self.assertEqual(error.exception.code, 'checkleaked_error')

    def test_provider_body_error_has_specific_ui_and_never_retries(self):
        with patch.object(service, '_reserve_attempt'), patch.object(service, 'get_json',
                return_value={'success': False, 'error': 'Daily limit exceeded ' + KEY}) as request:
            result = unified._provider('CheckLeaked', EMAIL, KEY, config())
        self.assertEqual(result['state'], 'rate_limited')
        self.assertEqual(request.call_count, 1)
        self.assertIn('limite diário', result['message'])
        self.assertNotIn(KEY, result['message'])


if __name__ == '__main__':
    unittest.main()
