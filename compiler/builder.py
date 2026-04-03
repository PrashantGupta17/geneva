import yaml
import os
from typing import Dict, Any, List
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.memory import MemorySaver
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from core.schemas import ProjectDSL, StageDSL
from agents.evaluator import StageAwareRouter, EvaluatorNode
from dbos import DBOS

import subprocess
from litellm import completion, completion_cost
from typing import Tuple

from core.registry import ProviderRegistry
from utils.storage import StorageManager

registry = ProviderRegistry()
storage_manager = StorageManager()

def load_providers_from_config(config_path="geneva_config.yaml"):
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = yaml.safe_load(f) or {}
            providers = config.get("providers", [])
            for p in providers:
                if p.get("type") == "api":
                    registry.add_api_provider(p["name"], p["litellm_model_name"])
                elif p.get("type") == "cli":
                    registry.add_cli_provider(p["name"], p["absolute_path"], p["test_command"])

load_providers_from_config()

# External tool wrapped with DBOS.step for durability
@DBOS.step()
def execute_external_api(stage_name: str, provider_info: dict, prompt: str) -> Tuple[str, float]:
    print(f"[DBOS] Executing API LLM call for '{stage_name}'...")
    model_name = provider_info.get("litellm_model_name", "gpt-3.5-turbo")

    try:
        response = completion(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        output = response.choices[0].message.content
        try:
            cost = completion_cost(completion_response=response)
        except:
            cost = 0.0
        return output, cost
    except Exception as e:
        print(f"[DBOS] LLM API call failed: {e}")
        return f"Error: {e}", 0.0

@DBOS.step()
def execute_external_cli(stage_name: str, provider_info: dict, prompt: str) -> Tuple[str, float]:
    print(f"[DBOS] Executing CLI command for '{stage_name}'...")
    cli_path = provider_info.get("absolute_path", "")

    try:
        # Pass the prompt to the CLI using a standard approach (e.g., echo prompt | cli or pass as arg)
        # We will assume passing it via stdin or as an argument. Let's write it to a temp file and pass it.
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(prompt)
            temp_path = f.name

        result = subprocess.run(
            f"{cli_path} < \"{temp_path}\"",
            shell=True,
            capture_output=True,
            text=True
        )
        os.remove(temp_path)

        output = result.stdout
        if result.returncode != 0:
            output = f"CLI Error: {result.stderr}"

        # Mock cost for CLI
        return output, 0.0
    except Exception as e:
        print(f"[DBOS] CLI call failed: {e}")
        return f"Error: {e}", 0.0

@DBOS.step()
def persist_if_large_step(payload: str) -> str:
    # Use StorageManager to check and persist
    return storage_manager.persist_if_large(payload)

@DBOS.workflow()
def universal_step(stage_name: str, routed_tier: str, prompt: str, iteration_index: int, thread_id: str) -> Tuple[str, float]:
    """
    Universal executor that handles routing to either CLI or API provider.
    Wrapped in a single DBOS.workflow to guarantee atomicity.
    """
    # Since routed_tier determines model class, we'll map standard/premium to a mock provider logic.
    # In a real scenario, the stage config would specify the provider name.
    # We will fallback to "api" type if not specifically a CLI provider name.

    # We can check if `routed_tier` directly matches a registered CLI provider.
    # For now, let's treat "premium" as API gpt-4-turbo, and others as well,
    # unless the assigned_model_tier in the DSL was exactly a CLI provider name.
    provider_info = registry.get_provider(routed_tier)

    if provider_info and provider_info["type"] == "cli":
        output, cost = execute_external_cli(stage_name, provider_info, prompt)
    else:
        # Default to API
        model_name = "gpt-4-turbo" if routed_tier == "premium" else "gpt-3.5-turbo"
        mock_provider = {"type": "api", "litellm_model_name": model_name}
        output, cost = execute_external_api(stage_name, mock_provider, prompt)

    final_output = persist_if_large_step(output)
    return final_output, cost

router = StageAwareRouter()
evaluator_agent = EvaluatorNode(model="gpt-4-turbo")

# Define the State for the LangGraph
class OverallState(TypedDict):
    project_name: str
    current_stage_index: int
    data: Dict[str, Any]
    eval_loops: Dict[str, int]
    max_loops: int
    global_budget: float

def load_dsl(filepath: str) -> ProjectDSL:
    with open(filepath, "r") as f:
        data = yaml.safe_load(f)
    return ProjectDSL(**data)

def build_graph(dsl_filepath: str) -> CompiledStateGraph:
    """
    Dynamically compiles a LangGraph StateGraph based on the provided YAML DSL.
    """

    # Check if file exists, if not use a fallback/dummy for studio compilation
    if not os.path.exists(dsl_filepath):
        print(f"Warning: DSL file {dsl_filepath} not found. Creating a minimal fallback graph.")
        builder = StateGraph(OverallState)

        def dummy_node(state: OverallState):
            return {"data": {"status": "waiting for dsl"}}

        builder.add_node("waiting", dummy_node)
        builder.add_edge(START, "waiting")
        builder.add_edge("waiting", END)
        # We need a persistent checkpointer for the fallback as well if we are standardizing
        conn = sqlite3.connect("geneva_persistence.db", check_same_thread=False)
        checkpointer = SqliteSaver(conn)
        checkpointer.setup()
        return builder.compile(checkpointer=checkpointer)

    dsl = load_dsl(dsl_filepath)
    stages = dsl.stages

    builder = StateGraph(OverallState)

    # 1. Define Node Functions
    # We create factory functions to generate the actual node logic for each stage

    def create_worker_node(stage: StageDSL):
        def worker(state: OverallState):
            print(f"\n--- Executing Worker: {stage.stage_name} ---")

            # Phase 4: Budget-aware routing
            base_prompt = "Perform the required task based on project data."

            # Middleware check
            routed_tier, modified_prompt = router.prepare_routing(stage, base_prompt)
            print(f"Worker Routed Model Tier: {routed_tier}")

            # The evaluator cost is updated in state.
            # We track the evaluator cost here.
            eval_cost_spent = state.get("data", {}).get(f"{stage.stage_name}_eval_cost", 0.0)
            if eval_cost_spent > 0:
                router.update_budget(stage, cost=eval_cost_spent)

            # Using DBOS wrapped step to protect external calls
            # Must wrap the step inside a workflow for DBOS to track it natively within LangGraph
            iteration_index = state.get("eval_loops", {}).get(stage.stage_name, 0)

            # Since thread_id is available in runnable config when executed through invoke/stream,
            # we can inject it via state, but we don't have config here directly.
            # As a simpler approach, we'll pass project_name as part of thread identifier for now.
            thread_id = state.get("project_name", "unknown")

            # Use dbos Context or pass ID if natively supported.
            # In Python DBOS, SetWorkflowID does not exist as an attribute on DBOS class directly in the way used.
            # The simplest valid way is to invoke the workflow via handle or with context if supported,
            # or simply rely on DBOS auto-generating the UUID if we can't manually set it this way.
            # Since the requirement is that DBOS manages it durability natively, calling the workflow function normally is usually sufficient for standard restart-proof flows within an active DBOS runner.

            # Use DBOS workflow invocation directly (needs to be invoked via handle if already inside a thread or normally,
            # but usually DBOS requires starting from a top level if it's the root workflow.
            # To avoid "invoked before DBOS initialized" in LangGraph thread context which isn't registered,
            # we can execute it synchronously if DBOS.launch() was called.)
            # Wait, DBOS requires workflows to be invoked correctly. Let's make sure DBOS.launch() is actually effective.
            # Since DBOS launch runs, we can just call it. But maybe langgraph runs it in a background thread that DBOS doesn't recognize.
            # We'll invoke it synchronously.
            workflow_id = f"{thread_id}-{stage.stage_name}-{iteration_index}"
            if os.environ.get("DBOS_DISABLE") == "1":
                # Fallback directly for environment testing
                print(f"[DBOS Mock] Bypassing DBOS workflow invocation for test environment.")
                if registry.get_provider(routed_tier) and registry.get_provider(routed_tier)["type"] == "cli":
                    output, worker_cost = execute_external_cli.__wrapped__(stage.stage_name, registry.get_provider(routed_tier), modified_prompt)
                else:
                    output, worker_cost = execute_external_api.__wrapped__(stage.stage_name, {"type": "api", "litellm_model_name": "gpt-3.5-turbo"}, modified_prompt)
                worker_output = persist_if_large_step.__wrapped__(output)
            else:
                handle = DBOS.start_workflow(universal_step, workflow_id=workflow_id, stage_name=stage.stage_name, routed_tier=routed_tier, prompt=modified_prompt, iteration_index=iteration_index, thread_id=thread_id)
                worker_output, worker_cost = handle.get_result()

            router.update_budget(stage, cost=worker_cost)

            data_dict = state.get("data", {}).copy()
            data_dict[f"{stage.stage_name}_output"] = worker_output

            return {
                "data": data_dict
            }
        return worker

    def create_evaluator_node(stage: StageDSL):
        def evaluator(state: OverallState):
            print(f"\n--- Evaluating: {stage.stage_name} ---")

            # Phase 4: LLM-as-a-judge
            worker_output = state.get("data", {}).get(f"{stage.stage_name}_output", "")

            passes, cost = evaluator_agent.evaluate(stage, worker_output)

            current_loops = state.get("eval_loops", {}).copy()
            stage_loops = current_loops.get(stage.stage_name, 0)
            data = state.get("data", {}).copy()
            data[f"{stage.stage_name}_passed"] = passes
            data[f"{stage.stage_name}_eval_cost"] = cost

            if not passes:
                print(f"Evaluation FAILED. Incrementing loop counter to {stage_loops + 1}.")
                current_loops[stage.stage_name] = stage_loops + 1
                return {"eval_loops": current_loops, "data": data}

            print(f"Evaluation PASSED.")
            return {
                "current_stage_index": state.get("current_stage_index", 0) + 1,
                "data": data
            }
        return evaluator

    # 2. Add Nodes to Graph
    for i, stage in enumerate(stages):
        worker_name = f"worker_{stage.stage_name}"
        eval_name = f"evaluator_{stage.stage_name}"

        builder.add_node(worker_name, create_worker_node(stage))
        builder.add_node(eval_name, create_evaluator_node(stage))

    # 3. Add Edges
    if not stages:
        builder.add_edge(START, END)
        return builder.compile(checkpointer=MemorySaver())

    # START to first worker
    builder.add_edge(START, f"worker_{stages[0].stage_name}")

    for i, stage in enumerate(stages):
        worker_name = f"worker_{stage.stage_name}"
        eval_name = f"evaluator_{stage.stage_name}"

        # Worker goes to Evaluator
        builder.add_edge(worker_name, eval_name)

        # For a clearer logic flow, let's redefine check_eval:
        def create_routing_logic(current_stage, is_last: bool):
            def route(state: OverallState) -> str:
                loops_dict = state.get("eval_loops", {})

                total_loops = sum(loops_dict.values())
                if total_loops > state.get("max_loops", 10):
                    print(f"Global loop safety triggered: total_loops ({total_loops}) > max_loops ({state.get('max_loops', 10)}).")
                    return "end"

                stage_loops = loops_dict.get(current_stage.stage_name, 0)

                pass_flag = state.get("data", {}).get(f"{current_stage.stage_name}_passed", False)
                if not pass_flag:
                    if stage_loops <= current_stage.max_retries:
                        return "retry"
                    else:
                        print(f"WARNING: Max retries ({current_stage.max_retries}) reached for {current_stage.stage_name}. Moving to next node.")

                if is_last:
                    return "end"
                return "next"
            return route

        if i + 1 < len(stages):
            next_worker = f"worker_{stages[i+1].stage_name}"
            builder.add_conditional_edges(
                eval_name,
                create_routing_logic(stage, is_last=False),
                {"next": next_worker, "retry": worker_name}
            )
        else:
            builder.add_conditional_edges(
                eval_name,
                create_routing_logic(stage, is_last=True),
                {"end": END, "retry": worker_name}
            )

    # Optional HITL interrupts based on DSL
    interrupt_nodes = []
    for stage in stages:
        if stage.requires_human_approval:
            # We'll pause before the worker runs
            interrupt_nodes.append(f"worker_{stage.stage_name}")

    # 4. Compile Graph
    conn = sqlite3.connect("geneva_persistence.db", check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()
    graph = builder.compile(checkpointer=checkpointer, interrupt_before=interrupt_nodes)

    return graph

# This instance is what LangGraph Studio looks for
graph = build_graph("project_dsl.yaml")
