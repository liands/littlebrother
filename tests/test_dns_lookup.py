"""DNS tests use real dnspython records, with no external queries."""
import contextlib
from dataclasses import replace
import io
import os
import unittest
from unittest.mock import Mock, patch

import dns.exception
import dns.name
import dns.resolver
import dns.rrset

from core.dns_lookup import (DNSLookupError, DNSResult, check_email_dns, dns_lookup,
                             interactive_email_security, interactive_lookup,
                             render_lookup, validate_name, validate_selectors)


class Answer:
    def __init__(self, record_type, records, ttl=300, canonical='example.com.'):
        self.rrset = dns.rrset.from_text('example.com.', ttl, 'IN', record_type, *records)
        self.canonical_name = dns.name.from_text(canonical)

    def __iter__(self):
        return iter(self.rrset)


class NameTests(unittest.TestCase):
    def test_normalizes_case_trailing_dot_idna_and_dns_service_labels(self):
        self.assertEqual(validate_name('Example.COM.'), 'example.com')
        self.assertEqual(validate_name('café.example'), 'xn--caf-dma.example')
        self.assertEqual(validate_name('s1._domainkey.example.com'), 's1._domainkey.example.com')

    def test_rejects_urls_ips_controls_options_and_empty_labels(self):
        for name in ['', '.', ' example.com', 'example.com ', 'example.com..',
                     'https://example.com', 'example.com:53', 'user@example.com',
                     '127.0.0.1', '::1', '*.example.com', 'example.com/x',
                     'a\nb.example', 'x;whoami', '--help', 'a..com', 'x'*64+'.com']:
            with self.subTest(name=name), self.assertRaises(DNSLookupError):
                validate_name(name)

    def test_domain_check_does_not_accept_service_label(self):
        with self.assertRaises(DNSLookupError):
            check_email_dns('_dmarc.example.com')

    def test_selector_validation_and_deduplication(self):
        self.assertEqual(validate_selectors('s1, S2, s1', 'example.com'), ('s1', 's2'))
        self.assertEqual(validate_selectors('', 'example.com'), ())
        for selectors in ['s1,,s2', 'x;bad', 's1, s2, s3, s4, s5, s6', ['_bad']]:
            with self.subTest(selectors=selectors), self.assertRaises(DNSLookupError):
                validate_selectors(selectors, 'example.com')


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '0'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.resolver = Mock()

    def test_supported_types_have_real_dnspython_records(self):
        fixtures = {'A': ['1.1.1.1'], 'AAAA': ['2606:4700:4700::1111'],
                    'MX': ['10 mail.example.com.'], 'TXT': ['"hello world"'],
                    'NS': ['ns1.example.com.'], 'SOA': ['ns1.example.com. hostmaster.example.com. 1 7200 3600 1209600 300'],
                    'CNAME': ['target.example.com.']}
        for record_type, records in fixtures.items():
            self.resolver.resolve.return_value = Answer(record_type, records)
            result = dns_lookup('example.com', record_type, resolver=self.resolver)
            with self.subTest(record_type=record_type):
                self.assertEqual(result.status, 'ok')
                self.assertEqual(result.ttl, 300)
                self.assertEqual(result.canonical_name, 'example.com.')
                self.assertEqual(len(result.records), 1)

    def test_txt_fragments_join_into_one_record(self):
        self.resolver.resolve.return_value = Answer('TXT', ['"v=spf1 " "-all"', '"verification=example"'])
        result = dns_lookup('example.com', 'TXT', resolver=self.resolver)
        self.assertIn('v=spf1 -all', result.records)
        self.assertEqual(len(result.records), 2)

    def test_absolute_query_disables_search_suffix_and_sets_lifetime(self):
        self.resolver.resolve.return_value = Answer('A', ['1.1.1.1'])
        dns_lookup('Example.com.', 'a', 3, resolver=self.resolver)
        self.resolver.resolve.assert_called_once_with('example.com.', 'A', search=False, lifetime=3.0, raise_on_no_answer=True)

    def test_offline_never_constructs_or_uses_resolver(self):
        with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '1'}), patch('core.dns_lookup._resolver') as factory:
            result = dns_lookup('example.com')
            self.assertEqual(result.status, 'offline')
            factory.assert_not_called()
        self.resolver.resolve.assert_not_called()

    def test_dns_errors_are_distinct_without_raw_exception_text(self):
        for error, state in [(dns.resolver.NXDOMAIN(), 'nxdomain'), (dns.resolver.NoAnswer(), 'no_answer'),
                             (dns.exception.Timeout(), 'timeout'), (dns.resolver.NoNameservers(), 'resolver_error'),
                             (OSError('private resolver details'), 'resolver_error'),
                             (dns.exception.DNSException('private resolver details'), 'error')]:
            self.resolver.resolve.side_effect = error
            result = dns_lookup('example.com', resolver=self.resolver)
            with self.subTest(state=state):
                self.assertEqual(result.status, state)
                self.assertEqual(result.records, ())
                self.assertNotIn('private resolver details', result.message)

    def test_missing_system_configuration_is_treated(self):
        with patch('core.dns_lookup._resolver', side_effect=dns.resolver.NoResolverConfiguration()):
            self.assertEqual(dns_lookup('example.com').status, 'resolver_error')

    def test_configures_system_resolver_with_bounded_timeout(self):
        with patch('core.dns_lookup.dns.resolver.Resolver', return_value=self.resolver) as factory:
            self.resolver.resolve.return_value = Answer('A', ['1.1.1.1'])
            self.assertEqual(dns_lookup('example.com', timeout=4).status, 'ok')
            factory.assert_called_once_with(configure=True)
            self.assertEqual(self.resolver.timeout, 2.0)
            self.assertEqual(self.resolver.lifetime, 4.0)
            self.assertFalse(self.resolver.use_search_by_default)

    def test_invalid_type_and_timeout_do_not_query(self):
        for options in [{'record': 'AXFR'}, {'record': 'ANY'}, {'record': 'TXT;bad'},
                        {'timeout': True}, {'timeout': 0}, {'timeout': 16},
                        {'timeout': float('nan')}, {'timeout': float('inf')}]:
            with self.subTest(options=options), self.assertRaises(DNSLookupError):
                dns_lookup('example.com', resolver=self.resolver, **options)
        self.resolver.resolve.assert_not_called()

    def test_terminal_control_characters_are_escaped_at_display(self):
        self.resolver.resolve.return_value = Answer('TXT', ['"hello\\027[31m"'])
        result = dns_lookup('example.com', 'TXT', resolver=self.resolver)
        output = render_lookup(result)
        self.assertNotIn('\x1b', output)
        self.assertIn('\\x1b', output)


class PolicyTests(unittest.TestCase):
    def run_checks(self, records, selectors=()):
        def query(name, record, timeout):
            value = records.get(name, ())
            if isinstance(value, DNSResult):
                return value
            return DNSResult(name, record, 'ok' if value else 'no_answer', tuple(value))
        with patch('core.dns_lookup.dns_lookup', side_effect=query) as lookup:
            checks = check_email_dns('example.com', selectors)
        return checks, lookup

    def test_spf_and_dmarc_and_dkim_publication(self):
        checks, lookup = self.run_checks({'example.com': ['v=spf1 -all', 'unrelated=txt'],
                                         '_dmarc.example.com': ['v=DMARC1; p=reject'],
                                         's1._domainkey.example.com': ['v=DKIM1; k=rsa; p=abc']}, ['s1'])
        self.assertEqual([item.status for item in checks], ['present', 'present', 'present'])
        self.assertEqual([call.args[0] for call in lookup.call_args_list],
                         ['example.com', '_dmarc.example.com', 's1._domainkey.example.com'])

    def test_missing_selector_is_not_checked_and_not_absent(self):
        checks, lookup = self.run_checks({})
        self.assertEqual(checks[-1].status, 'not_checked')
        self.assertEqual(lookup.call_count, 2)

    def test_missing_records_are_scoped_absence(self):
        checks, _ = self.run_checks({}, ['s1'])
        self.assertEqual([item.status for item in checks], ['absent', 'absent', 'absent'])
        self.assertIn('neste nome', checks[1].message)

    def test_timeout_is_not_absence(self):
        failed = DNSResult('example.com', 'TXT', 'timeout', message='Timeout DNS')
        checks, _ = self.run_checks({'example.com': failed})
        self.assertEqual(checks[0].status, 'timeout')

    def test_multiple_spf_and_dmarc_are_flagged(self):
        checks, _ = self.run_checks({'example.com': ['v=spf1 -all', 'v=spf1 ~all'],
                                    '_dmarc.example.com': ['v=DMARC1; p=none', 'v=DMARC1; p=reject']})
        self.assertEqual([item.status for item in checks[:2]], ['multiple', 'multiple'])

    def test_dmarc_none_is_monitoring_and_missing_or_duplicate_policy_is_invalid(self):
        checks, _ = self.run_checks({'_dmarc.example.com': ['v=DMARC1; p=none']})
        self.assertIn('monitoramento', checks[1].message)
        for record in ['v=DMARC1; rua=mailto:reports@example.com', 'v=DMARC1; p=bad',
                       'v=DMARC1; p=none; p=reject', 'v=DMARC1 p=reject']:
            checks, _ = self.run_checks({'_dmarc.example.com': [record]})
            with self.subTest(record=record):
                self.assertEqual(checks[1].status, 'invalid')

    def test_dkim_version_optional_and_empty_key_revoked(self):
        checks, _ = self.run_checks({'s1._domainkey.example.com': ['k=rsa; p=abc']}, ['s1'])
        self.assertEqual(checks[-1].status, 'present')
        checks, _ = self.run_checks({'s1._domainkey.example.com': ['v=DKIM1; p=']}, ['s1'])
        self.assertEqual(checks[-1].status, 'revoked')

    def test_dkim_missing_key_and_duplicate_tags_are_invalid(self):
        for record in ['v=DKIM1; k=rsa', 'v=DKIM1; p=abc; p=def', 'v=DKIM2; p=abc']:
            checks, _ = self.run_checks({'s1._domainkey.example.com': [record]}, ['s1'])
            self.assertEqual(checks[-1].status, 'invalid')

    def test_control_characters_do_not_become_a_valid_policy(self):
        checks, _ = self.run_checks({'example.com': ['v=spf1\n-all']})
        self.assertEqual(checks[0].status, 'invalid')

    def test_all_selectors_are_validated_before_any_query(self):
        with patch('core.dns_lookup.dns_lookup') as lookup, self.assertRaises(DNSLookupError):
            check_email_dns('example.com', ['s1', 'bad;selector'])
        lookup.assert_not_called()

    def test_multiple_selectors_query_only_requested_names(self):
        checks, lookup = self.run_checks({}, 's1, s2, s1')
        self.assertEqual(len(checks), 4)
        self.assertEqual(lookup.call_count, 4)


class InteractiveTests(unittest.TestCase):
    def test_lookup_prompts_host_and_type(self):
        with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '0'}), patch('builtins.input', side_effect=['example.com', 'MX', '']), patch('core.dns_lookup.dns_lookup', return_value=DNSResult('example.com', 'MX', 'no_answer')) as lookup, contextlib.redirect_stdout(io.StringIO()):
            interactive_lookup()
        lookup.assert_called_once_with('example.com', 'MX', 5.0)

    def test_offline_actions_do_not_prompt_or_construct_resolver(self):
        with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '1'}), patch('builtins.input') as prompt, patch('core.dns_lookup._resolver') as resolver, contextlib.redirect_stdout(io.StringIO()):
            interactive_lookup()
            interactive_email_security()
        prompt.assert_not_called()
        resolver.assert_not_called()

    def test_email_check_output_has_scope_limits_and_selector_status(self):
        with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '0'}), patch('builtins.input', side_effect=['example.com', '', '']), patch('core.dns_lookup.dns_lookup', return_value=DNSResult('example.com', 'TXT', 'no_answer')), contextlib.redirect_stdout(io.StringIO()) as output:
            interactive_email_security()
        self.assertIn('não verificado', output.getvalue())
        self.assertIn('herança', output.getvalue())


if __name__ == '__main__':
    unittest.main()
