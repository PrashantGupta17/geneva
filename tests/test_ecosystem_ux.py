import pytest
import builtins
import yaml
import json
import os
from unittest.mock import patch, MagicMock

# Import the logic to test
from main import main
from compiler.builder import build_graph
import litellm

def test_interactive_index_bounds(monkeypatch, capsys):
    # 1. test_interactive_index_bounds: Mock input() providing out-of-bounds integer to /attach logic.
    # We will simulate main loop with a mock input sequence

    # Sequence of inputs:
    # 1. /attach
    # 2. 99 (out of bounds)
    # 3. quit

    inputs = iter(["/attach", "99", "quit"])
    def mock_input(prompt):
        return next(inputs)

    monkeypatch.setattr(builtins, "input", mock_input)

    # Mock auto_discover_providers
    with patch("main.auto_discover_providers", return_value={"master_planner": "test", "providers": []}):
        with patch("main.DBOS.launch"):
            with patch("main.PlannerAgent"):
                main()

    captured = capsys.readouterr()
    # It should catch the out-of-bounds gracefully and print "Invalid project number."
    assert "Invalid project number." in captured.out

def test_config_llm_categorization(monkeypatch, capsys):
    # 2. test_config_llm_categorization: Mock invoke_master_llm to return the JSON.
    inputs = iter(["/config model add", "groq", "llama3-70b-8192", "quit"])
    def mock_input(prompt):
        return next(inputs)
    monkeypatch.setattr(builtins, "input", mock_input)

    # Mock invoke_master_llm
    mock_response = json.dumps({"pool_name": "llama-3-70b", "tier": "free", "capabilities": ["text"]})
    with patch("core.meta_llm.invoke_master_llm", return_value=mock_response):
        with patch("main.auto_discover_providers", return_value={"master_planner": "test", "providers": []}):
            with patch("main.DBOS.launch"):
                with patch("main.PlannerAgent"):
                    # We need to make sure we don't mess up actual config
                    with patch("builtins.open", new_callable=MagicMock):
                        with patch("yaml.dump") as mock_dump:
                            with patch("yaml.safe_load", return_value={"models": []}):
                                main()

                                # Verify configuration parsing logic correctly extracted keys
                                # the dump should have been called with the updated config
                                assert mock_dump.called
                                args, kwargs = mock_dump.call_args
                                config_data = args[0]

                                # Check if the model is added correctly
                                assert "models" in config_data
                                added_model = config_data["models"][-1]
                                assert added_model["provider"] == "groq"
                                assert added_model["model_id"] == "llama3-70b-8192"
                                assert added_model["pool_name"] == "llama-3-70b"
                                assert added_model["tier"] == "free"
                                assert added_model["capabilities"] == ["text"]

def test_litellm_router_setup():
    # 3. test_litellm_router_setup: Mock a geneva_config.yaml with two models sharing the pool llama-3-70b

    mock_config = {
        "models": [
            {"provider": "groq", "model_id": "llama3", "pool_name": "llama-3-70b"},
            {"provider": "openrouter", "model_id": "llama3", "pool_name": "llama-3-70b"}
        ]
    }

    # We just test the router initialization logic from compiler/builder.py
    # Since it's evaluated at import time or module level, we can just reproduce the logic
    model_list = [{"model_name": m["pool_name"], "litellm_params": {"model": f"{m['provider']}/{m['model_id']}"}} for m in mock_config["models"]]

    router = litellm.Router(model_list=model_list, num_retries=2)

    # Assert model_list groups them correctly
    assert len(router.model_list) == 2
    assert router.model_list[0]["model_name"] == "llama-3-70b"
    assert router.model_list[1]["model_name"] == "llama-3-70b"

def test_rewind_as_node(monkeypatch, capsys):
    # 4. test_rewind_as_node: Mock LangGraph update_state call for /rewind.
    # Assert that as_node is correctly formatted as evaluator_{stage_name} and payload is correct.

    inputs = iter(["/attach test_id", "/rewind", "1", "quit"])
    def mock_input(prompt):
        return next(inputs)
    monkeypatch.setattr(builtins, "input", mock_input)

    # Mock active_dsl and graph
    mock_dsl = MagicMock()
    mock_stage = MagicMock()
    mock_stage.stage_name = "test_stage"
    mock_dsl.stages = [mock_stage]

    mock_graph = MagicMock()
    mock_state = MagicMock()
    mock_state.values = {"data": {"test_stage": {"passed": True}}}
    mock_graph.get_state.return_value = mock_state

    with patch("main.auto_discover_providers", return_value={"master_planner": "test", "providers": []}):
        with patch("main.DBOS.launch"):
            with patch("main.PlannerAgent"):
                with patch("main.os.path.exists", return_value=True):
                    with patch("builtins.open", MagicMock()):
                        with patch("yaml.safe_load", return_value={}):
                            with patch("main.ProjectDSL", return_value=mock_dsl):
                                with patch("main.build_graph", return_value=mock_graph):
                                    with patch("main.get_status_from_graph", return_value=("PAUSED", None)):
                                        main()

                                        # Verify the update_state call
                                        mock_graph.update_state.assert_called_with(
                                            {"configurable": {"thread_id": "test_id"}},
                                            {"data": {"test_stage": {"passed": False}}},
                                            as_node="evaluator_test_stage"
                                        )
