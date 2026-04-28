from __future__ import annotations

import unittest

from armas_gadso.flows.notifications.graph_client import classify_graph_failure, extract_graph_error


class GraphClientTests(unittest.TestCase):
    def test_extract_graph_error_from_error_dict(self) -> None:
        detail = '{"error":{"code":"ErrorAccessDenied","message":"Access is denied."}}'
        self.assertEqual(extract_graph_error(detail), ("ErrorAccessDenied", "Access is denied."))

    def test_classify_invalid_client_secret(self) -> None:
        detail = '{"error":"invalid_client","error_description":"Invalid client secret is provided."}'
        tag, _message = classify_graph_failure(401, detail)
        self.assertEqual(tag, "AUTH_INVALID_CLIENT_SECRET")

    def test_classify_invalid_sender(self) -> None:
        detail = '{"error":{"code":"ErrorInvalidUser","message":"The requested user is invalid."}}'
        tag, _message = classify_graph_failure(404, detail)
        self.assertEqual(tag, "SENDER_INVALID_USER")

    def test_classify_access_denied(self) -> None:
        detail = '{"error":{"code":"ErrorAccessDenied","message":"Access is denied. Check credentials and try again."}}'
        tag, _message = classify_graph_failure(403, detail)
        self.assertEqual(tag, "SEND_ACCESS_DENIED")


if __name__ == "__main__":
    unittest.main()
