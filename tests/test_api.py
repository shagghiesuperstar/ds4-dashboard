import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import dashboard
from bridge.engine_client import DS4EngineClient, EngineClientConfig


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
        self.assertEqual(data["primary_host"], "127.0.0.1")
        self.assertEqual(data["primary_port"], 8001)
        self.assertEqual(data["context_window"], 131072)
        self.assertEqual(data["kv_disk_cache"]["path"], "/Volumes/OWC_MODELS_TB5/DS4/cache")
        self.assertEqual(data["kv_disk_cache"]["budget_mib"], 51200)

    def test_config_schema_is_dynamic_metadata(self):
        response = self.client.get("/api/config-schema")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertEqual(schema["context_window"]["type"], "int")
        self.assertEqual(schema["model"]["type"], "path")
        self.assertEqual(schema["primary_host"]["type"], "string")

    def test_agentic_full_suite_is_registered(self):
        response = self.client.get("/api/benchmarks")
        self.assertEqual(response.status_code, 200)
        suite_ids = {suite["id"] for suite in response.json()["suites"]}
        self.assertIn("agentic_full", suite_ids)

    def test_benchmark_run_accepts_suite_query_param(self):
        expected = {"run_id": "test", "suite_id": "agentic_full", "tasks": []}
        with patch.object(dashboard.benchmark_runner, "run_suite", return_value=expected) as run_suite:
            response = self.client.post("/api/benchmarks/run?suite=agentic_full")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        run_suite.assert_called_once()
        self.assertEqual(run_suite.call_args.args[0], "agentic_full")

    def test_status_includes_engine_and_system_metrics(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["engine"], "ds4")
        self.assertEqual(data["port"], 8001)
        self.assertIn("memory", data["system"])
        self.assertIn("cpu", data["system"])

    def test_engine_uses_model_average_when_telemetry_has_no_tok_s(self):
        client = DS4EngineClient(
            EngineClientConfig(
                host="127.0.0.1",
                port=1,
                telem_url="http://127.0.0.1:1/telem",
                binary_path=Path("/tmp/ds4-server"),
            )
        )
        client.set_model_averages_provider(lambda: {"tok_s": {"avg": 42.5}})

        telemetry = client._normalize_telemetry({})

        self.assertEqual(telemetry["tok_s"], 42.5)

    @patch("dashboard.fetch_model_card_description", return_value="HF description")
    @patch("dashboard.discover_models", return_value=[{"path": "/models/a.gguf", "repo": "org/repo"}])
    def test_model_descriptions_endpoint(self, _discover_models, _fetch_description):
        response = self.client.get("/api/model-descriptions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"/models/a.gguf": "HF description"})


if __name__ == "__main__":
    unittest.main()
