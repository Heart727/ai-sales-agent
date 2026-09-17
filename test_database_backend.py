import sqlite3
import unittest
from unittest.mock import patch

import turso_serverless

import config
import database


class FakeConnection:
    def __init__(self):
        self.row_factory = None


class DatabaseBackendTests(unittest.TestCase):
    def test_get_conn_uses_turso_when_both_credentials_are_present(self):
        fake_connection = FakeConnection()
        with patch.object(config, "TURSO_DATABASE_URL", "turso://demo"), \
             patch.object(config, "TURSO_AUTH_TOKEN", "secret"), \
             patch("turso_serverless.connect", return_value=fake_connection) as connect:
            result = database.get_conn()

        connect.assert_called_once_with("turso://demo", auth_token="secret")
        self.assertIs(result, fake_connection)
        self.assertIs(result.row_factory, turso_serverless.Row)

    def test_get_conn_rejects_partial_turso_credentials(self):
        with patch.object(config, "TURSO_DATABASE_URL", "turso://demo"), \
             patch.object(config, "TURSO_AUTH_TOKEN", ""):
            with self.assertRaisesRegex(RuntimeError, "TURSO_DATABASE_URL.*TURSO_AUTH_TOKEN"):
                database.get_conn()

    def test_local_backend_still_returns_sqlite_connection(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(config, "TURSO_DATABASE_URL", ""), \
                 patch.object(config, "TURSO_AUTH_TOKEN", ""), \
                 patch.object(database, "DB_PATH", f"{temp_dir}/local.db"):
                conn = database.get_conn()
                try:
                    self.assertIsInstance(conn, sqlite3.Connection)
                    self.assertIs(conn.row_factory, sqlite3.Row)
                finally:
                    conn.close()
