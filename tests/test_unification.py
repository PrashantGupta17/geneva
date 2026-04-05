import pytest
import os
import json
from unittest.mock import patch, MagicMock

os.environ["DBOS_DISABLE"] = "1"

from core.schemas import StageDSL, ProjectDSL
from compiler.builder import build_graph, execute_external_api, execute_external_cli
from core.bootstrap import auto_discover_providers
from litellm import completion

def test_parallel_retry_idempotency():
    """
    Test 1: test_parallel_retry_idempotency
    Mock a state update where a provider writes to experiment_results twice (simulating a retry).
    Assert the length of the dictionary remains 1 and the value is updated.
    """
    from core.schemas import dict_merge_or_clear

    # We are testing dict_merge_or_clear functionality manually and in a mock state context
    state1 = {"experiment_results": {}}

    update1 = {"experiment_results": {"openai": {"output": "result1", "cost": 0.1}}}
    state1["experiment_results"] = dict_merge_or_clear(state1["experiment_results"], update1["experiment_results"])

    # Retry update
    update2 = {"experiment_results": {"openai": {"output": "result2", "cost": 0.2}}}
    state1["experiment_results"] = dict_merge_or_clear(state1["experiment_results"], update2["experiment_results"])

    assert len(state1["experiment_results"]) == 1
    assert state1["experiment_results"]["openai"]["output"] == "result2"
    assert state1["experiment_results"]["openai"]["cost"] == 0.2

    # Test clearing
    state1["experiment_results"] = dict_merge_or_clear(state1["experiment_results"], {})
    assert state1["experiment_results"] == {}

@patch("agents.evaluator.EvaluatorNode.evaluate")
def test_evaluator_fanout_routing(mock_eval):
    """
    Test 2: test_evaluator_fanout_routing
    Mock a state where experiment_results has data but data_dict is empty.
    Assert the Evaluator correctly grades the experiment_results payload.
    """
    from compiler.builder import build_graph

    stage = StageDSL(
        stage_name="test_fanout",
        assigned_model_tier="standard",
        stage_budget=1.0,
        success_criteria={},
        stage_type="parallel_fanout"
    )

    # To get create_evaluator_node, we can inspect builder locals or just re-define the logic here to test the node logic itself, or since it's nested in build_graph, we can use the graph directly, but for simplicity of unit testing the inner logic, we can just extract it or mock it.
    # Since create_evaluator_node is inside build_graph, let's just make a dummy graph and execute the evaluator node.
    # Or, we can grab it from a mock run, but we can't easily extract it. Let's just redefine the node logic exactly as it is in builder.py or test it via the graph.
    # Actually, we can just write a dummy ProjectDSL, build_graph with it, and call the evaluator node directly from the graph.
    import yaml
    with open("test_dsl.yaml", "w") as f:
        yaml.dump(ProjectDSL(project_name="test", global_budget=1.0, stages=[stage]).model_dump(), f)

    try:
        os.environ["DBOS_DISABLE"] = "1"
        graph = build_graph("test_dsl.yaml")
    finally:
        os.remove("test_dsl.yaml")
        if "DBOS_DISABLE" in os.environ:
            del os.environ["DBOS_DISABLE"]

    # The evaluator node is named "evaluator_test_fanout"
    evaluator_runnable = graph.builder.nodes["evaluator_test_fanout"].runnable

    mock_eval.return_value = (True, 0.05)

    state = {
        "data": {},
        "eval_loops": {},
        "experiment_results": {"openai": {"output": "fanout1", "cost": 0.1}},
        "current_stage_index": 0
    }

    # In langgraph a node runnable takes config as well, or we can just invoke it.
    new_state = evaluator_runnable.invoke(state, config={})

    # Assert evaluator evaluated the serialized json
    expected_output = json.dumps({"openai": {"output": "fanout1", "cost": 0.1}})
    mock_eval.assert_called_once_with(stage, expected_output)

    # Assert state cleared correctly and mapped to output
    assert new_state["experiment_results"] == {}
    assert new_state["data"].get("test_fanout", {}).get("output") == expected_output
    assert new_state["data"].get("test_fanout", {}).get("passed") is True

@patch("compiler.builder.completion")
def test_api_kwargs_passing(mock_completion):
    """
    Test 3: test_api_kwargs_passing
    Mock execute_external_api with tool_args={"temperature": 0.5, "max_tokens": 100, "invalid": "dropme"}.
    Assert these arguments are correctly unpacked into the internal litellm.completion call.
    """
    # mock completion return
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="api_response"))]
    mock_completion.return_value = mock_resp

    provider_info = {"litellm_model_name": "gpt-4"}
    tool_args = {"temperature": 0.5, "max_tokens": 100, "invalid_arg": "dropme"}

    # call unwrapped to avoid dbos
    output, cost = execute_external_api.__wrapped__("test_api", provider_info, "hello", tool_args)

    mock_completion.assert_called_once()
    kwargs = mock_completion.call_args.kwargs
    assert kwargs["temperature"] == 0.5
    assert kwargs["max_tokens"] == 100
    assert "invalid_arg" not in kwargs

@patch("subprocess.run")
@patch("litellm.completion")
@patch("os.path.exists")
def test_cli_help_parsing(mock_exists, mock_completion, mock_run):
    """
    Test 4: test_cli_help_parsing
    Pass a dummy --help string to the bootstrap help-parser.
    Assert the Master LLM extracts {"--depth": "integer"}.
    """
    # Force it to think no config exists
    mock_exists.return_value = False

    # Ensure environment variables are not set for discovery so that local CLI is the only thing
    import os
    with patch.dict(os.environ, clear=True):
        # Mock discovering an ollama cli
        import shutil
        with patch("shutil.which", return_value="/usr/bin/ollama") as mock_which, \
             patch("builtins.input", side_effect=["1"]): # Select option 1 (ollama)

            # We need to mock subprocess.run correctly:
            # First call is test_command (ollama --version)
            # Second call is ollama --help
            mock_run.side_effect = [
                MagicMock(stdout="ollama version 1.0", stderr="", returncode=0), # test_command
                MagicMock(stdout="Usage: ollama run <model> --depth <int>", stderr="", returncode=0) # --help
            ]

            # Mock litellm completion to return {"--depth": "integer"}
            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock(message=MagicMock(content='{"--depth": "integer"}'))]
            mock_completion.return_value = mock_resp

            config = auto_discover_providers()

            # Assertions
            assert len(config["providers"]) == 1
            provider = config["providers"][0]
            assert provider["name"] == "ollama"
            assert "supported_args" in provider
            assert provider["supported_args"] == {"--depth": "integer"}
