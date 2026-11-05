import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from core import domain_registration as registration
from core.dns_lookup import DNSResult
from lib import http, rdap_registry
from test_http import FakeResponse

ROOT = Path(__file__).resolve().parents[1]


def vcard(**fields):
    return ['vcard', [[key, {}, 'text', value] for key, value in fields.items()]]


def fixture():
    return {'objectClassName': 'domain', 'ldhName': 'EXAMPLE.COM', 'handle': 'EXAMPLE-ID',
            'nameservers': [{'ldhName': 'NS1.EXAMPLE.NET.'}], 'status': ['active'],
            'secureDNS': {'delegationSigned': True},
            'events': [{'eventAction': 'registration', 'eventDate': '2000-01-01T00:00:00Z'}],
            'entities': [
                {'roles': ['registrar'], 'handle': '123', 'vcardArray': vcard(fn='Registrar Company'),
                 'publicIds': [{'type': 'IANA Registrar ID', 'identifier': '123'}],
                 'entities': [{'roles': ['abuse'], 'vcardArray': vcard(email='abuse@example.net')}]},
                {'roles': ['registrant'], 'vcardArray': vcard(fn='Published Owner', org=['Example Organization'],
                 adr=['', '', 'Published Street', 'City', 'State', '12345', 'BR'], email='owner@example.com')}],
            'notices': [{'title': 'Terms', 'description': ['Public data only.']}]}


class BootstrapTests(unittest.TestCase):
    def test_bundled_iana_selects_br_com_and_org(self):
        publication, services = rdap_registry.bootstrap()
        self.assertRegex(publication, r'^\d{4}-\d{2}-\d{2}T')
        self.assertGreater(len(services), 1000)
        self.assertEqual(rdap_registry.domain_url('empresa.com.br'), 'https://rdap.registro.br/domain/empresa.com.br')
        self.assertEqual(rdap_registry.domain_url('example.com'), 'https://rdap.verisign.com/com/v1/domain/example.com')
        self.assertEqual(rdap_registry.domain_url('example.org'), 'https://rdap.publicinterestregistry.org/rdap/domain/example.org')

    def test_longest_matching_suffix(self):
        with patch.object(rdap_registry, 'bootstrap', return_value=('date', {'test': ('https://rdap.example.net/',),
                'co.test': ('https://rdap.example.org/special/',)})):
            self.assertEqual(rdap_registry.domain_url('company.co.test'), 'https://rdap.example.org/special/domain/company.co.test')

    def test_unknown_and_insecure_only_services_are_explicit(self):
        with self.assertRaises(LookupError):
            rdap_registry.domain_url('example.invalid')
        with patch.object(rdap_registry, 'bootstrap', return_value=('date', {'test': ()})), self.assertRaises(LookupError):
            rdap_registry.domain_url('example.test')

    def test_only_https_bases_without_credentials_ips_or_queries(self):
        for url in ('http://rdap.example.com/', 'https://user:secret@rdap.example.com/',
                    'https://127.0.0.1/', 'https://rdap.example.com:444/', 'https://rdap.example.com/?x=1',
                    'https://rdap.example.com/#section', 'https://rdap.example.com/%2e%2e/',
                    'https://rdap.example.com/\n', 'https://rdap.example.com/not-a-directory'):
            with self.subTest(url=url):
                self.assertFalse(rdap_registry._safe_base(url))

    def test_queries_cannot_escape_iana_service_or_domain_path(self):
        self.assertTrue(rdap_registry.permitted_query('https://rdap.registro.br/domain/nic.br'))
        for url in ('https://127.0.0.1/domain/nic.br', 'https://rdap.registro.br.evil.invalid/domain/nic.br',
                    'https://rdap.registro.br/entity/123', 'https://rdap.registro.br/domain/nic.br?x=1',
                    'https://rdap.registro.br/domain/nic.br#fragment', 'https://rdap.registro.br/domain/../nic.br',
                    'https://rdap.registro.br/domain/%2e%2e', 'https://rdap.registro.br/domain/example.com',
                    'https://rdap.registro.br/domain/127.0.0.1'):
            with self.subTest(url=url):
                self.assertFalse(rdap_registry.permitted_query(url))


class RDAPHttpTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '0'})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.mock = patch('lib.http.requests.Session')
        self.session = self.mock.start().return_value.__enter__.return_value
        self.addCleanup(self.mock.stop)

    def test_separate_allowlist_does_not_expand_regular_api_access(self):
        with self.assertRaises(http.IntegrationError):
            http.get_json('https://rdap.registro.br/domain/nic.br')
        self.session.get.assert_not_called()
        self.session.get.return_value = FakeResponse(b'{"objectClassName":"domain"}')
        self.assertEqual(http.get_rdap_json('https://rdap.registro.br/domain/nic.br')['objectClassName'], 'domain')
        options = self.session.get.call_args.kwargs
        self.assertFalse(options['allow_redirects'])
        self.assertTrue(options['verify'])
        self.assertIn('application/rdap+json', options['headers']['Accept'])
        self.assertNotIn('Authorization', options['headers'])

    def test_rdap_does_not_follow_external_links_or_redirects(self):
        self.session.get.return_value = FakeResponse(status=302, headers={'Location': 'http://127.0.0.1/'})
        with self.assertRaises(http.IntegrationError) as error:
            http.get_rdap_json('https://rdap.registro.br/domain/nic.br')
        self.assertEqual(error.exception.code, 'redirect')
        self.assertEqual(self.session.get.call_count, 1)

    def test_offline_blocks_rdap_transport(self):
        with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '1'}), self.assertRaises(http.IntegrationError):
            http.get_rdap_json('https://rdap.registro.br/domain/nic.br')
        self.session.get.assert_not_called()

    def test_invalid_json_and_unexpected_shapes(self):
        for body in (b'<html>error</html>', b'null', b'[]', b'"text"', b'\xff'):
            self.session.get.return_value = FakeResponse(body)
            with self.subTest(body=body), self.assertRaises(http.IntegrationError):
                http.get_rdap_json('https://rdap.registro.br/domain/nic.br')


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '0'})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.dns_mock = patch.object(registration, 'dns_lookup', return_value=DNSResult('example.com', 'NS', 'ok', ('ns1.example.net.',)))
        self.dns = self.dns_mock.start()
        self.addCleanup(self.dns_mock.stop)
        self.api_mock = patch.object(registration, 'get_rdap_json', return_value=fixture())
        self.api = self.api_mock.start()
        self.addCleanup(self.api_mock.stop)

    def test_public_fields_roles_dates_dnssec_and_ns(self):
        report = registration.lookup_registration('EXAMPLE.COM.')
        rdap = report['rdap']
        self.assertEqual(rdap['status'], 'ok')
        self.assertEqual(rdap['nameservers'], ['ns1.example.net'])
        self.assertTrue(rdap['delegation_signed'])
        self.assertTrue(rdap['registrant_published'])
        self.assertEqual(len(rdap['contacts']), 3)
        registrar = rdap['contacts'][0]
        owner = rdap['contacts'][2]
        self.assertEqual(registrar['roles'], ['registrar'])
        self.assertEqual(owner['roles'], ['registrant'])
        self.assertEqual(owner['fields']['fn'], ['Published Owner'])
        self.assertIn('BR', owner['fields']['adr'][0])
        text = registration.render_registration(report)
        self.assertIn('listas coincidem', text)
        self.assertIn('Titular (registrant)', text)
        self.assertIn('Registrador (registrar)', text)
        self.assertIn('Registro/criação: 2000', text)

    def test_missing_owner_does_not_use_registrar_as_owner(self):
        data = fixture()
        data['entities'] = data['entities'][:1]
        self.api.return_value = data
        report = registration.lookup_registration('example.com')
        self.assertFalse(report['rdap']['registrant_published'])
        self.assertIn('Titular: dados não fornecidos', registration.render_registration(report))
        self.assertIn('Registrador (registrar)', registration.render_registration(report))

    def test_partial_redacted_contacts_are_preserved(self):
        data = fixture()
        data['redacted'] = [{'name': {'type': 'Registrant Email'}}]
        data['entities'][1]['vcardArray'] = vcard(fn='REDACTED FOR PRIVACY')
        parsed = registration.parse_registration(data, 'example.com')
        self.assertTrue(parsed['redaction_reported'])
        self.assertEqual(parsed['contacts'][2]['fields']['fn'], ['REDACTED FOR PRIVACY'])

    def test_http_failure_preserves_dns_nameservers(self):
        for code, status in (('http_404', 'not_found'), ('http_429', 'rate_limited'), ('timeout', 'error'), ('tls_error', 'error')):
            self.api.side_effect = http.IntegrationError('Consulta não concluída.', code=code)
            report = registration.lookup_registration('example.com')
            with self.subTest(code=code):
                self.assertEqual(report['rdap']['status'], status)
                self.assertEqual(report['dns']['records'], ('ns1.example.net.',))
                self.assertIn('ns1.example.net.', registration.render_registration(report))
        self.assertNotIn('disponível para registro', registration.render_registration(report))

    def test_dns_failure_does_not_hide_registry_response(self):
        self.dns.return_value = DNSResult('example.com', 'NS', 'timeout', message='Timeout DNS.')
        report = registration.lookup_registration('example.com')
        self.assertEqual(report['rdap']['status'], 'ok')
        self.assertEqual(report['dns']['status'], 'timeout')
        self.assertNotIn('listas coincidem', registration.render_registration(report))

    def test_different_ns_lists_are_reported(self):
        self.dns.return_value = DNSResult('example.com', 'NS', 'ok', ('other.example.net.',))
        self.assertIn('listas diferentes', registration.render_registration(registration.lookup_registration('example.com')))

    def test_offline_never_starts_dns_or_http(self):
        with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '1'}):
            report = registration.lookup_registration('example.com')
        self.assertEqual(report['rdap']['status'], 'offline')
        self.dns.assert_not_called()
        self.api.assert_not_called()

    def test_invalid_domains_and_options_do_not_start_queries(self):
        for domain in ('https://example.com', '127.0.0.1', 'localhost', 'example.com:443', '*.example.com', 'x.com;dir'):
            with self.subTest(domain=domain), self.assertRaises(ValueError):
                registration.lookup_registration(domain)
        for timeout in (0, 16, True, float('nan')):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                registration.lookup_registration('example.com', timeout)
        self.dns.assert_not_called()
        self.api.assert_not_called()

    def test_unsupported_extension_still_returns_dns(self):
        report = registration.lookup_registration('example.invalid')
        self.assertEqual(report['rdap']['status'], 'unsupported')
        self.api.assert_not_called()
        self.assertEqual(report['dns']['status'], 'ok')

    def test_invalid_record_or_different_domain_is_not_success(self):
        for data in ({'errorCode': 404}, {'objectClassName': 'entity'}, {'objectClassName': 'domain', 'ldhName': 'evil.example'}, []):
            self.api.return_value = data
            with self.subTest(data=data):
                self.assertEqual(registration.lookup_registration('example.com')['rdap']['status'], 'error')

    def test_empty_optional_fields_and_malformed_contacts(self):
        parsed = registration.parse_registration({'objectClassName': 'domain', 'ldhName': 'example.com',
            'entities': [None, {'vcardArray': 'bad'}, {'vcardArray': ['vcard', [['fn']]]}], 'secureDNS': {'delegationSigned': 'false'}}, 'example.com')
        self.assertIsNone(parsed['delegation_signed'])
        self.assertFalse(parsed['registrant_published'])
        self.assertEqual(parsed['nameservers'], [])

    def test_provider_control_characters_are_escaped_and_output_bounded(self):
        data = fixture()
        data['entities'][1]['vcardArray'] = vcard(fn='\x1b[2Jfake\n' + 'x' * 10000)
        self.api.return_value = data
        text = registration.render_registration(registration.lookup_registration('example.com'))
        self.assertNotIn('\x1b', text)
        self.assertIn('\\x1b', text)
        self.assertLess(len(text), 6000)

    def test_entity_limit_and_recursion_are_explicit(self):
        data = fixture()
        data['entities'] = [{'roles': ['technical']}] * 100
        parsed = registration.parse_registration(data, 'example.com')
        self.assertEqual(len(parsed['contacts']), registration.MAX_ENTITIES)
        self.assertTrue(parsed['contacts_truncated'])
        node = {'roles': ['technical']}
        data['entities'] = [node]
        for _ in range(10):
            child = {'roles': ['technical']}
            node['entities'] = [child]
            node = child
        self.assertTrue(registration.parse_registration(data, 'example.com')['contacts_truncated'])

    def test_progress_shows_dns_and_rdap_phases(self):
        events = []
        registration.lookup_registration('example.com', on_progress=events.append)
        self.assertEqual(len(events), 2)
        self.assertIn('nameservers', events[0])
        self.assertIn('RDAP oficial', events[1])

    def test_iana_catalog_failure_is_distinct_and_keeps_dns(self):
        with patch.object(registration, 'domain_url', side_effect=ValueError('invalid catalog')):
            report = registration.lookup_registration('example.com')
        self.assertEqual(report['rdap']['status'], 'error')
        self.assertIn('Catálogo IANA', report['rdap']['message'])
        self.assertEqual(report['dns']['status'], 'ok')

    def test_interactive_query_renders_results_and_source(self):
        with patch('builtins.input', side_effect=['example.com', '']), patch('sys.stdout', new_callable=io.StringIO) as output:
            registration.interactive_nameservers()
        self.assertIn('NS', output.getvalue())
        self.assertIn('Published Owner', output.getvalue())
        self.assertIn('https://rdap.verisign.com/com/v1/domain/example.com', output.getvalue())
        self.dns.assert_called_once_with('example.com', 'NS', 5.0)

    def test_interactive_offline_does_not_prompt(self):
        with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '1'}), patch('builtins.input') as prompt, patch('sys.stdout', new_callable=io.StringIO):
            registration.interactive_nameservers()
        prompt.assert_not_called()
        self.api.assert_not_called()
        self.dns.assert_not_called()

    def test_cli_dns_option_three_offline(self):
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'LittleBrother.py'), '--offline', '--data-dir', str(ROOT / '.work')],
            input='6\nh\nc\n3\nb\ne\n', capture_output=True, text=True, encoding='utf-8', timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('[3] Nameserver / domain registration', result.stdout)
        self.assertIn('nenhuma consulta DNS ou RDAP foi iniciada.', result.stdout)


if __name__ == '__main__':
    unittest.main()
