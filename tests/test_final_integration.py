import pytest
import os
import yaml
from unittest.mock import patch, mock_open
from agents.planner import PlannerAgent
from compiler.builder import build_graph, OverallState
from core.schemas import StageDSL

def test_planner_model_awareness():
    mock_config = {
        "providers": [
            {
                "name": "mock-openai",
                "type": "api",
                "litellm_model_name": "gpt-4"
            }
        ],
        "models": [
            {
                "pool_name": "mock-pool-model",
                "provider": "mock-openai",
                "model_id": "gpt-4",
                "tier": "premium",
                "capabilities": ["text", "reasoning"]
            }
        ]
    }

    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config))):
            planner = PlannerAgent(model="gpt-4-turbo")
            loaded_config = planner._load_providers()
            assert "models" in loaded_config
            assert loaded_config["models"][0]["pool_name"] == "mock-pool-model"


@patch("compiler.builder.resolve_payload")
@patch("compiler.builder.json.dumps")
@patch("compiler.builder.DBOS")
def test_safe_serialization(mock_dbos, mock_json_dumps, mock_resolve_payload):
    # This is a bit tricky since we're testing inner logic of create_worker_node
    # Let's import the builder logic and simulate a state.

    # We want to test that if `previous_output` is "path://dummy.txt",
    # `resolve_payload` is called, and `json.dumps` gets the resolved text.

    # Let's mock resolve_payload to return "actual content"
    mock_resolve_payload.return_value = "actual content"
    mock_json_dumps.return_value = '"actual content"'

    # Instead of running the whole graph, let's just create the worker node function
    # and call it with a mock state.

    from compiler.builder import StateGraph, START, END

    # We need to construct a graph manually or use the logic
    # Since builder.py uses local functions, we can compile a dummy graph
    # Let's create a minimal DSL
    from core.schemas import ProjectDSL, StageDSL

    dummy_dsl = ProjectDSL(
        project_name="test",
        global_budget=1.0,
        max_loops=1,
        stages=[
            StageDSL(stage_name="stage1", assigned_model_tier="standard", stage_budget=0.1, success_criteria={}),
            StageDSL(
                stage_name="stage2",
                stage_type="ephemeral_code",
                assigned_model_tier="standard",
                stage_budget=0.1,
                success_criteria={},
                ephemeral_script="print('hello')"
            )
        ]
    )

    with patch("compiler.builder.load_dsl", return_value=dummy_dsl):
        with patch("os.path.exists", return_value=True):
            graph = build_graph("dummy.yaml")

            # The state would normally have "path://dummy.txt" as output of stage1
            state = {
                "project_name": "test",
                "current_stage_index": 1,
                "data": {
                    "stage1": {
                        "output": "path://dummy.txt"
                    }
                },
                "eval_loops": {},
                "max_loops": 1,
                "global_budget": 1.0,
                "experiment_results": {}
            }

            # We can't directly call the inner function easily, but we can see the effect
            # Actually, `resolve_payload` is used in `ephemeral_code` worker.
            # Let's just run it via the graph node directly.

            # The node function is stored in graph.nodes
            worker_node = graph.nodes["worker_stage2"]

            # Call the node function
            # State needs to be a proper dict for LangGraph node
            result = worker_node.invoke(state, config={})

            # Verify resolve_payload was called
            mock_resolve_payload.assert_any_call("path://dummy.txt")
