"""Offline tests: synthetic SDK responses only; no API requests or secrets."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import tracker


class TrackerTests(unittest.TestCase):
    def test_cost(self):
        self.assertAlmostEqual(tracker.calculate_cost(1000, 2000, .25, 1.50), .00325)
        self.assertAlmostEqual(tracker.calculate_cost(1000, 2000, .075, .30), .000675)

    def test_missing_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "Missing GEMINI_API_KEY"):
                tracker.get_key("gemini")

    def test_prices(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(tracker.get_prices("groq", "openai/gpt-oss-20b"), (.075, .30))
            with self.assertRaisesRegex(ValueError, "No prices configured"):
                tracker.get_prices("groq", "new-model")
        with patch.dict(os.environ, {"GROQ_INPUT_PRICE_PER_M": "0.1", "GROQ_OUTPUT_PRICE_PER_M": "0.2"}, clear=True):
            self.assertEqual(tracker.get_prices("groq", "new-model"), (.1, .2))
        with patch.dict(os.environ, {"GROQ_INPUT_PRICE_PER_M": "nan", "GROQ_OUTPUT_PRICE_PER_M": "0.2"}, clear=True):
            with self.assertRaises(ValueError):
                tracker.get_prices("groq", "new-model")

    def test_missing_token_count(self):
        with self.assertRaises(RuntimeError):
            tracker.token_count(None)

    def test_full_run_with_mocked_sdks(self):
        google = ModuleType("google")
        google.genai = MagicMock()
        gemini_client = google.genai.Client.return_value
        gemini_client.models.generate_content.return_value = SimpleNamespace(
            text="Gemini example reply",
            usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=20, thoughts_token_count=5),
        )
        groq = ModuleType("groq")
        groq.Groq = MagicMock()
        groq_client = groq.Groq.return_value.__enter__.return_value
        groq_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Groq example reply"))],
            usage=SimpleNamespace(prompt_tokens=30, completion_tokens=40),
        )
        env = {"GEMINI_API_KEY": "test-placeholder", "GROQ_API_KEY": "test-placeholder"}
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as folder, patch.object(tracker, "ROOT", Path(folder)), \
                patch.dict(os.environ, env, clear=True), patch.dict(sys.modules, {"google": google, "groq": groq}), \
                contextlib.redirect_stdout(output):
            self.assertEqual(tracker.main(["Same prompt"]), 0)
            data = json.loads((Path(folder) / "results.json").read_text())
        self.assertEqual([row["provider"] for row in data], ["gemini", "groq"])
        fields = {"provider", "model", "reply", "input_tokens", "output_tokens", "input_price_per_m", "output_price_per_m", "cost_usd"}
        for row in data:
            self.assertEqual(set(row), fields)
        self.assertEqual((data[0]["input_tokens"], data[0]["output_tokens"]), (10, 25))
        self.assertEqual((data[1]["input_tokens"], data[1]["output_tokens"]), (30, 40))
        self.assertAlmostEqual(data[0]["cost_usd"], .00004)
        self.assertAlmostEqual(data[1]["cost_usd"], .00001425)
        gemini_client.models.generate_content.assert_called_once_with(model=tracker.DEFAULT_MODELS["gemini"], contents="Same prompt")
        groq_client.chat.completions.create.assert_called_once_with(model=tracker.DEFAULT_MODELS["groq"], messages=[{"role": "user", "content": "Same prompt"}])
        for text in ("Gemini example reply", "Groq example reply", "Seconds", "Cost (USD)"):
            self.assertIn(text, output.getvalue())

    def test_cli_missing_key_and_no_results(self):
        errors = io.StringIO()
        with tempfile.TemporaryDirectory() as folder, patch.object(tracker, "ROOT", Path(folder)), \
                patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(errors):
            self.assertEqual(tracker.main(["Hello"]), 1)
            self.assertFalse((Path(folder) / "results.json").exists())
        self.assertIn("Missing GEMINI_API_KEY", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
