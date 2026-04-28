from __future__ import annotations

import unittest

from armas_gadso.flows.notifications.mail_config import split_addresses, validate_mail_config


class MailConfigTests(unittest.TestCase):
    def test_split_addresses_accepts_semicolon_and_comma(self) -> None:
        value = "a@demo.com; b@demo.com, c@demo.com"
        self.assertEqual(
            split_addresses(value),
            ["a@demo.com", "b@demo.com", "c@demo.com"],
        )

    def test_validate_mail_config_requires_sender_and_to(self) -> None:
        config = {
            "tenant_id": "tenant",
            "client_id": "client",
            "client_secret": "secret",
            "sender": "",
            "to": [],
            "cc": [],
            "subject_prefix": "ARMAS-GADSO",
        }
        self.assertEqual(validate_mail_config(config), "falta MS_GRAPH_SENDER")


if __name__ == "__main__":
    unittest.main()
