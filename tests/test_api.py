import unittest

from fastapi.testclient import TestClient

import dashboard


class DashboardApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(dashboard.app)

    def test_index_serves_shell(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("DS4 Dwarfstar Dashboard", response.text)

    def test_config_defaults_match_ds4_context(self):
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["primary_port"], 8001)
        self.assertEqual(data["context_window"], 131072)
        self.assertEqual(data["kv_disk_cache"]["budget_mib"], 51200)

    def test_config_schema_is_dynamic_metadata(self):
        response = self.client.get("/api/config-schema")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertEqual(schema["context_window"]["type"], "int")
        self.assertEqual(schema["model"]["type"], "path")

    def test_status_includes_engine_and_system_metrics(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["engine"], "ds4")
        self.assertEqual(data["port"], 8001)
        self.assertIn("memory", data["system"])
        self.assertIn("cpu", data["system"])


if __name__ == "__main__":
    unittest.main()
