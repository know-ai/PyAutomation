import unittest

import asyncua
from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256


def _version_at_least(version: str, minimum: str) -> bool:
    left = [int(part) for part in version.split(".")[:3]]
    right = [int(part) for part in minimum.split(".")[:3]]
    return left >= right


class TestSecurityCve(unittest.TestCase):
    def test_asyncua_closes_cve_2022_25304(self):
        self.assertTrue(_version_at_least(asyncua.__version__, "0.9.96"))
        self.assertTrue(_version_at_least(asyncua.__version__, "2.0.1"))

    def test_basic256sha256_symbol_imports(self):
        self.assertTrue(callable(SecurityPolicyBasic256Sha256))
