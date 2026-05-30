import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient

import dashboard
from bridge.engine_client import DS4EngineClient, EngineClientConfig


class DashboardApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(dashboard.app)
        self._clear_config_overrides()

    def tearDown(self):
        self._clear_config_overrides()

    def _clear_config_overrides(self):
        for key in list(dashboard.config_manager.get_overrides()):
            dashboard.config_manager.clear_override(key)

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

    def test_config_profile_export_captures_current_overrides(self):
        dashboard.config_manager.set_override("poll_interval_ms", 1500)
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(dashboard, "CONFIG_PROFILES_DIR", Path(tmpdir)):
            response = self.client.post(
                "/api/config-profiles/export",
                json={"label": "Low Latency", "description": "Fast polling", "tags": ["latency"]},
            )

            self.assertEqual(response.status_code, 200)
            profile = response.json()["profile"]
            self.assertEqual(profile["id"], "low-latency")
            self.assertEqual(profile["override_count"], 1)
            saved = yaml.safe_load((Path(tmpdir) / "low-latency.yaml").read_text())
            self.assertEqual(saved["overrides"], {"poll_interval_ms": 1500})

    def test_config_profile_import_avoids_label_collisions(self):
        payload = b"label: Shared Profile\noverrides:\n  poll_interval_ms: 2500\n"
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(dashboard, "CONFIG_PROFILES_DIR", Path(tmpdir)):
            first = self.client.post(
                "/api/config-profiles/import",
                files={"file": ("shared.yaml", payload, "application/x-yaml")},
            )
            second = self.client.post(
                "/api/config-profiles/import",
                files={"file": ("shared.yaml", payload, "application/x-yaml")},
            )

            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(first.json()["profile"]["id"], "shared-profile")
            self.assertEqual(second.json()["profile"]["id"], "shared-profile-1")

    def test_config_profile_apply_replaces_current_overrides(self):
        dashboard.config_manager.set_override("poll_interval_ms", 3000)
        dashboard.config_manager.set_override("custom_test_key", "remove-me")
        profile = {
            "label": "Polling Profile",
            "description": "",
            "tags": [],
            "hardware_hint": "",
            "created": "2026-05-30T12:00:00Z",
            "updated": "2026-05-30T12:00:00Z",
            "overrides": {"poll_interval_ms": 1200},
        }
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(dashboard, "CONFIG_PROFILES_DIR", Path(tmpdir)):
            dashboard.save_profile("polling-profile", profile)
            response = self.client.post("/api/config-profiles/polling-profile/apply")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(dashboard.config_manager.get_overrides(), {"poll_interval_ms": 1200})

    def test_config_profile_metadata_update_preserves_overrides(self):
        profile = {
            "label": "Original",
            "description": "Before",
            "tags": ["old"],
            "overrides": {"poll_interval_ms": 900},
        }
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(dashboard, "CONFIG_PROFILES_DIR", Path(tmpdir)):
            dashboard.save_profile("original", profile)
            response = self.client.put(
                "/api/config-profiles/original",
                json={"label": "Renamed", "description": "After", "tags": ["new"]},
            )

            self.assertEqual(response.status_code, 200)
            saved = yaml.safe_load((Path(tmpdir) / "original.yaml").read_text())
            self.assertEqual(saved["label"], "Renamed")
            self.assertEqual(saved["description"], "After")
            self.assertEqual(saved["tags"], ["new"])
            self.assertEqual(saved["overrides"], {"poll_interval_ms": 900})

    def test_config_profile_download_returns_stored_yaml(self):
        profile = {
            "label": "Downloadable Test",
            "description": "Portable profile",
            "tags": ["portable"],
            "overrides": {"poll_interval_ms": 1100},
        }
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(dashboard, "CONFIG_PROFILES_DIR", Path(tmpdir)):
            dashboard.save_profile("downloadable-test", profile)
            response = self.client.get("/api/config-profiles/downloadable-test/download")

            self.assertEqual(response.status_code, 200)
            self.assertIn("downloadable-test.yaml", response.headers["content-disposition"])
            saved = yaml.safe_load(response.content.decode("utf-8"))
            self.assertEqual(saved["label"], "Downloadable Test")
            self.assertEqual(saved["overrides"], {"poll_interval_ms": 1100})


if __name__ == "__main__":
    unittest.main()
