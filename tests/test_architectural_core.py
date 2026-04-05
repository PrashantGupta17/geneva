import pytest
import os
import json
import subprocess
from unittest import mock
import operator
from core.bootstrap import auto_discover_providers
from core.coercer import DataCoercer

# 1. test_key_inference
def test_key_inference(monkeypatch):
    # Mocking input to simulate user typing "sk-ant-api03-12345"
    inputs = iter(["sk-ant-api03-12345"])
    monkeypatch.setattr('builtins.input', lambda _: next(inputs))

    # Mock auto_discover_providers to not actually load the config
    monkeypatch.setattr('os.path.exists', lambda p: False)

    # Mock litellm completion to pass validation
    with mock.patch("litellm.completion") as mock_completion:
        mock_completion.return_value = True # Just mock it passes without exception

        # Test the inference logic inside auto_discover_providers
        # Note: We need to bypass the environ check or assume it's empty
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setattr("shutil.which", lambda _: None)

        # We need to mock open to avoid saving to file, but we can let it save to a temp file or just mock yaml.dump
        with mock.patch("yaml.dump"), mock.patch("builtins.open", mock.mock_open()):
            config = auto_discover_providers()

            assert config is not None
            assert "providers" in config
            assert len(config["providers"]) == 1
            assert config["providers"][0]["name"] == "anthropic"
            assert config["providers"][0]["type"] == "api"
            assert config["master_planner"] == "anthropic"

# 2. test_coercion_layer
def test_coercion_layer():
    # Mock the invoke_master_llm to return {"count": 42}
    with mock.patch("core.coercer.invoke_master_llm") as mock_invoke:
        mock_invoke.return_value = '{"count": 42}'

        coercer = DataCoercer(model="gpt-4-turbo")
        raw_text = "Analysis complete. The final count is 42."
        schema = {"type": "object", "properties": {"count": {"type": "integer"}}}

        result = coercer.sanitize_for_computation(raw_text, schema)

        assert result == {"count": 42}

from compiler.builder import execute_ephemeral_code

# 3. test_ephemeral_io
def test_ephemeral_io():
    # Dummy python script
    script = """
import sys
import json

data = json.load(sys.stdin)
data["modified"] = True
print(json.dumps(data))
"""
    input_data = {"test": "value"}

    # We test the wrapped execution function to bypass DBOS initialization check inside the test
    output_str, cost = execute_ephemeral_code.__wrapped__("test_stage", script, input_data)

    output_data = json.loads(output_str)
    assert output_data == {"test": "value", "modified": True}
    assert cost == 0.0

# 4. test_parallel_reducer
def test_parallel_reducer():
    # Simulate a state dictionary receiving three parallel updates to experiment_results
    # LangGraph uses operator.add for the reducer

    initial_results = []

    update1 = [{"provider": "openai", "output": "result1", "cost": 0.01}]
    update2 = [{"provider": "anthropic", "output": "result2", "cost": 0.02}]
    update3 = [{"provider": "gemini", "output": "result3", "cost": 0.03}]

    # Apply updates using operator.add
    state_results = operator.add(initial_results, update1)
    state_results = operator.add(state_results, update2)
    state_results = operator.add(state_results, update3)

    assert len(state_results) == 3
    assert state_results[0]["provider"] == "openai"
    assert state_results[1]["provider"] == "anthropic"
    assert state_results[2]["provider"] == "gemini"
