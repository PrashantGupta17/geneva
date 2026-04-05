import pytest
import os
import tempfile
from unittest import mock
from core.meta_llm import invoke_master_llm
from utils.storage import resolve_payload
from compiler.builder import build_graph, OverallState
from core.schemas import ProjectDSL, StageDSL
from typing import Dict, Any

def test_meta_llm_cli_bridge():
    with mock.patch("core.meta_llm.get_master_provider") as mock_provider, \
         mock.patch("subprocess.run") as mock_run:

        mock_provider.return_value = {
            "name": "mock_cli",
            "type": "cli",
            "absolute_path": "/usr/bin/mock_cli"
        }

        mock_result = mock.Mock()
        mock_result.stdout = '{"mock": "response"}'
        mock_run.return_value = mock_result

        result = invoke_master_llm("test prompt", response_format={"type": "json_object"})

        assert result == '{"mock": "response"}'
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert "/usr/bin/mock_cli" in args[0]
        assert "<" in args[0] # Checks stdin redirection

def test_payload_resolution():
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("Actual file text")
        temp_path = f.name

    try:
        payload = {"gpt4": f"path://{temp_path}"}
        resolved = resolve_payload(payload)
        assert resolved == {"gpt4": "Actual file text"}
    finally:
        os.remove(temp_path)

def test_parallel_thread_pool():
    # Construct a dummy DSL for test
    dsl = ProjectDSL(
        project_name="test_parallel",
        global_budget=10.0,
        stages=[
            StageDSL(
                stage_name="parallel_test",
                assigned_model_tier="standard",
                stage_budget=5.0,
                success_criteria={"status": "ok"},
                stage_type="parallel_fanout",
                target_providers=["provider1", "provider2"]
            )
        ]
    )

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".yaml") as f:
        import yaml
        yaml.dump(dsl.model_dump(), f)
        dsl_path = f.name

    try:
        os.environ["DBOS_DISABLE"] = "1"
        graph = build_graph(dsl_path)

        # We simulate executing the node directly rather than full graph invocation to test specifically the node wrapper
        # The node is named `worker_parallel_fanout_parallel_test`
        for node_id, node_spec in graph.builder.nodes.items():
            if node_id == "worker_parallel_fanout_parallel_test":
                # In LangGraph, node_spec.runnable is the actual function wrapped
                # If it's a Runnable, we need to use invoke
                node_func = node_spec.runnable

                # We mock the executor to return deterministic dummy results
                with mock.patch("compiler.builder.execute_external_api.__wrapped__") as mock_exec:
                    mock_exec.return_value = ("mocked_output", 0.1)

                    state: OverallState = {
                        "project_name": "test_parallel",
                        "current_stage_index": 0,
                        "data": {},
                        "eval_loops": {},
                        "max_loops": 10,
                        "global_budget": 10.0,
                        "experiment_results": {},
                        "ingestion_path": None
                    }

                    # Direct invocation using invoke since it's a RunnableLambda
                    result = node_func.invoke(state, config={})

                    assert "experiment_results" in result
                    assert "provider1" in result["experiment_results"]
                    assert "provider2" in result["experiment_results"]
                    assert result["experiment_results"]["provider1"]["output"] == "mocked_output"
                    assert "data" in result
                    assert result["data"].get("parallel_test", {}).get("eval_cost") == 0.2 # 0.1 * 2
                break
    finally:
        os.remove(dsl_path)
        if "DBOS_DISABLE" in os.environ:
            del os.environ["DBOS_DISABLE"]
