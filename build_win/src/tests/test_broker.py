"""
broker 套件的單元測試（不依賴真實 fubon_neo SDK）。

執行：
    cd build_win/src
    python -m unittest tests.test_broker -v
"""
import os
import sys
import tempfile
import unittest

# 把 src 加入 path（與 main.py 同樣方式）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from broker import (  # noqa: E402
    AccountRef,
    BrokerError,
    ConnectionState,
    FubonAdapter,
    FubonAuthError,
    FubonConfigError,
    MockAdapter,
)
from config import BrokerSettings  # noqa: E402


class TestAccountRef(unittest.TestCase):
    def test_display_with_name(self):
        a = AccountRef(branch_no="6460", account_no="1234567",
                       account_name="王小明")
        self.assertEqual(a.display, "6460-1234567 (王小明)")

    def test_display_without_name(self):
        a = AccountRef(branch_no="6460", account_no="1234567")
        self.assertEqual(a.display, "6460-1234567")


class TestMockAdapter(unittest.TestCase):
    def test_login_success(self):
        m = MockAdapter()
        self.assertEqual(m.state, ConnectionState.DISCONNECTED)
        result = m.login()
        self.assertTrue(result.success)
        self.assertEqual(m.state, ConnectionState.CONNECTED)
        self.assertIsNotNone(m.account)
        self.assertEqual(len(result.accounts), 1)

    def test_logout(self):
        m = MockAdapter()
        m.login()
        m.logout()
        self.assertEqual(m.state, ConnectionState.DISCONNECTED)
        self.assertIsNone(m.account)


class TestFubonAdapterConfig(unittest.TestCase):
    def test_missing_required_field_raises(self):
        with self.assertRaises(FubonConfigError):
            FubonAdapter(
                personal_id="",        # 缺
                password="x",
                cert_path="x",
                cert_password="x",
                branch_no="6460",
                account_no="1234567",
            )

    def test_login_without_sdk_installed(self):
        adapter = FubonAdapter(
            personal_id="A123456789",
            password="pw",
            cert_path="/tmp/none.pfx",
            cert_password="cp",
            branch_no="6460",
            account_no="1234567",
        )
        # fubon_neo 不在測試環境 → 應拋 FubonAuthError
        with self.assertRaises(FubonAuthError):
            adapter.login()
        self.assertEqual(adapter.state, ConnectionState.LOGIN_FAILED)


class TestBrokerSettings(unittest.TestCase):
    def test_is_complete_false_when_empty(self):
        s = BrokerSettings()
        self.assertFalse(s.is_complete())

    def test_is_complete_true_when_filled(self):
        s = BrokerSettings(
            personal_id="A123",
            password="x",
            cert_path="/tmp/a.pfx",
            cert_password="x",
            branch_no="6460",
            account_no="1234567",
        )
        self.assertTrue(s.is_complete())

    def test_json_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "broker_settings.json")
            s = BrokerSettings(
                personal_id="A123456789",
                password="pw",
                cert_path="/tmp/demo.pfx",
                cert_password="cp",
                branch_no="6460",
                account_no="1234567",
                api_key="key",
                api_secret="secret",
                dry_run=False,
            )

            s.save(path)
            loaded = BrokerSettings.load_strict(path)

            self.assertEqual(loaded.personal_id, "A123456789")
            self.assertEqual(loaded.cert_path, "/tmp/demo.pfx")
            self.assertEqual(loaded.api_key, "key")
            self.assertFalse(loaded.dry_run)

    def test_from_dict_rejects_non_object_root(self):
        with self.assertRaises(ValueError):
            BrokerSettings.from_dict(["not", "object"])


class TestBrokerErrorHierarchy(unittest.TestCase):
    def test_subclasses(self):
        self.assertTrue(issubclass(FubonAuthError, BrokerError))
        self.assertTrue(issubclass(FubonConfigError, BrokerError))


if __name__ == "__main__":
    unittest.main()
