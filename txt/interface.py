"""Original menu layout and numbering, wired to the revised implementation."""

MAIN = """
 [1] Lookup
 [2] Other tool
 [3] Profiler
 [4] Change country
 [5] Tracert / Pathtrace
 [6] DNS lookup
 [7] Sub-domains

 [e] Exit script    [h] Help Message    [c] Clear Screen"""

LOOKUP = """
 [1] Personne lookup          [8] Mail tracer
 [2] Username lookup          [9] Employee search
 [3] Adresse lookup           [10] Google search
 [4] Phone lookup             [11] Facebook info
 [5] IP lookup                [12] Twitter / X info
 [6] BSSID locator            [13] Instagram info
 [7] Email lookup             [14] EXIF read

 [b] back main menu    [e] Exit script    [h] Help Message    [c] Clear Screen"""

OTHER = """
 [1] SHA-1 exposure check
 [2] SHA-1 hash generator

 [b] back main menu    [e] Exit script    [h] Help Message    [c] Clear Screen"""

PROFILER = """
 [1] Profiler
 [2] Show all Profiles
 [3] Create profile
 [4] Export profile
 [5] Restore backup
 [6] Edit accounts

 [b] back main menu    [e] Exit script    [h] Help Message    [c] Clear Screen"""

COUNTRY = """
 [1] FR (France)     [4] LU (Luxembourg)
 [2] BE (Belgique)   [5] All
 [3] CH (Suisse)     [6] BR (Brasil)

 [b] back main menu    [e] Exit script    [h] Help Message    [c] Clear Screen"""

COUNTRY_CODES = {"1": "FR", "2": "BE", "3": "CH", "4": "LU", "5": "XX", "6": "BR"}

TRACERT = """
 [1] Lookup host

 [b] back main menu    [e] Exit script    [h] Help Message    [c] Clear Screen"""

DNS = """
 [1] Lookup host / record type
 [2] SPF / DKIM / DMARC
 [3] Nameserver / domain registration

 [b] back main menu    [e] Exit script    [h] Help Message    [c] Clear Screen"""

SUBDOMAINS = """
 [1] Discover domain
 [2] Sources / tools status

 [b] back main menu    [e] Exit script    [h] Help Message    [c] Clear Screen"""
