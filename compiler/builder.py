import yaml
import os
from typing import Dict, Any, List, Annotated
import operator
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.memory import MemorySaver
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from core.schemas import ProjectDSL, StageDSL
from agents.evaluator import StageAwareRouter, EvaluatorNode
from dbos import DBOS
from langgraph.types import Send

import subprocess
from litellm import completion, completion_cost
from typing import Tuple, Optional
import json

from core.registry import ProviderRegistry
from utils.storage import StorageManager
from core.coercer import DataCoercer

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

@DBOS.step()
def execute_ephemeral_code(stage_name: str, script: str, input_data: dict) -> Tuple[str, float]:
    print(f"[DBOS] Executing Ephemeral Code for '{stage_name}'...")
    try:
        result = subprocess.run(
            ["python3", "-c", script],
            input=json.dumps(input_data),
            capture_output=True,
            text=True
        )
        output = result.stdout
        if result.returncode != 0:
            output = f"Code Error: {result.stderr}"
        return output, 0.0
    except Exception as e:
        print(f"[DBOS] Code execution failed: {e}")
        return f"Error: {e}", 0.0

@DBOS.workflow()
def universal_step(stage_name: str, routed_tier: str, prompt: str, iteration_index: int, thread_id: str, tool_args: Optional[Dict] = None, provider_override: Optional[str] = None) -> Tuple[str, float]:
    """
    Universal executor that handles routing to either CLI or API provider.
    Wrapped in a single DBOS.workflow to guarantee atomicity.
    """
    provider_name = provider_override or routed_tier
    provider_info = registry.get_provider(provider_name)

    if provider_info and provider_info["type"] == "cli":
        cli_args = ""
        if tool_args:
            cli_args = " " + " ".join([f"--{k} {v}" for k, v in tool_args.items()])

        modified_prompt = prompt + cli_args
        output, cost = execute_external_cli(stage_name, provider_info, modified_prompt)
    else:
        model_name = "gpt-4-turbo" if routed_tier == "premium" else "gpt-3.5-turbo"
        if provider_info and provider_info["type"] == "api":
            model_name = provider_info.get("litellm_model_name", model_name)

        mock_provider = {"type": "api", "litellm_model_name": model_name}
        output, cost = execute_external_api(stage_name, mock_provider, prompt)

    final_output = persist_if_large_step(output)
    return final_output, cost

router = StageAwareRouter()
evaluator_agent = EvaluatorNode(model="gpt-4-turbo")
coercer = DataCoercer()

# Define the State for the LangGraph
class OverallState(TypedDict):
    project_name: str
    current_stage_index: int
    data: Dict[str, Any]
    eval_loops: Dict[str, int]
    max_loops: int
    global_budget: float
    experiment_results: Annotated[list, operator.add]
    ingestion_path: Optional[str]

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

            thread_id = state.get("project_name", "unknown")
            iteration_index = state.get("eval_loops", {}).get(stage.stage_name, 0)

            # 1. Routing by Stage Type
            if stage.stage_type == "data_ingestion":
                if not state.get("ingestion_path"):
                    print(f"Data ingestion path is empty. Interrupting...")
                    return {} # In a real interrupt, this would trigger langgraph interrupt_before. We just return state for now, main.py loop will handle it. Wait, the instructions say: "If so, return a state update that triggers an interrupt_before."
                    # We'll return an empty update, which just relies on the interrupt_before configured during graph compilation. Wait, the actual node runs AFTER interrupt if it's in interrupt_before.
                    # If it's empty, we might raise an exception or just return, but if it runs, we should just read it if it's there.
                    # The instructions say: "Check if state.get('ingestion_path') is empty. If so, return a state update that triggers an interrupt_before." Wait, LangGraph interrupt_before is defined on compile.
                    # But if we need to return an update, maybe we just return state. We can raise an error or just return empty. We will read it if available.
                    # Actually, if it's empty, we return a state update that triggers something? Let's just return to wait, but LangGraph needs to be interrupted.
                    # The simplest way to interrupt from a node in LangGraph is to raise NodeInterrupt or similar, but the instruction specifically says "return a state update that triggers an interrupt_before".
                    # However, if we're in the node, `interrupt_before` already happened. We'll check if path is available.

                path = state.get("ingestion_path")
                content = ""
                if path and os.path.exists(path):
                    with open(path, "r") as f:
                        content = f.read()

                data_dict = state.get("data", {}).copy()
                data_dict[f"{stage.stage_name}_output"] = content
                return {"data": data_dict}

            if stage.stage_type == "ephemeral_code":
                # Phase 6.2: ephemeral_code Execution
                print(f"Executing ephemeral code...")
                # Find previous stage output as data
                # We can just pass the entire state data dictionary to coercer
                raw_data = json.dumps(state.get("data", {}))

                try:
                    coerced_data = coercer.sanitize_for_computation(raw_data, stage.input_schema or {})
                except Exception as e:
                    coerced_data = {"error": str(e)}

                if os.environ.get("DBOS_DISABLE") == "1":
                    worker_output, worker_cost = execute_ephemeral_code.__wrapped__(stage.stage_name, stage.ephemeral_script, coerced_data)
                else:
                    workflow_id = f"{thread_id}_{stage.stage_name}_code_{iteration_index}"
                    handle = DBOS.start_workflow(execute_ephemeral_code, workflow_id=workflow_id, stage_name=stage.stage_name, script=stage.ephemeral_script, input_data=coerced_data)
                    worker_output, worker_cost = handle.get_result()

                data_dict = state.get("data", {}).copy()
                data_dict[f"{stage.stage_name}_output"] = worker_output
                return {"data": data_dict}

            if stage.stage_type == "parallel_fanout":
                # Send API for parallel execution
                sends = []
                for provider in (stage.target_providers or []):
                    # In LangGraph, .Send is returned from a conditional edge or we can return a list of Sends if this node is routing.
                    # However, the instructions say "Use LangGraph's .Send(node_name, state_update) API in the edge routing to spawn parallel executions"
                    # If this is the node, it shouldn't return Send directly if it's not an edge.
                    # Let me re-read: "Use LangGraph's .Send(node_name, state_update) API in the edge routing to spawn parallel executions for each provider in stage.target_providers."
                    # This means we need a conditional edge from the previous node or from start, not returning Send from the worker node itself.
                    # Wait, if this node is the worker, maybe this worker DOES the parallel fanout. But Send is used in edge routing.
                    # Let's adjust the worker to do the fanout internally using DBOS workflows if not using Send.
                    # BUT instruction specifically says: "Use LangGraph's .Send(node_name, state_update) API in the edge routing..."
                    # We will add an edge routing function for this later. For now, if the node itself executes, it might be the target of the Send.
                    # Wait, if `create_worker_node` is meant to route, let's look at the instruction again:
                    # "Refactor create_worker_node: It must now inspect stage.stage_type and route accordingly."
                    # If it's a fanout, we can just execute parallel DBOS workflows here, OR if we MUST use Send, this node needs to return Send.
                    # Actually, LangGraph node can return a Send object. Let's return Sends.
                    pass

            # Standard LLM (or fallback)
            base_prompt = "Perform the required task based on project data."
            routed_tier, modified_prompt = router.prepare_routing(stage, base_prompt)
            print(f"Worker Routed Model Tier: {routed_tier}")

            eval_cost_spent = state.get("data", {}).get(f"{stage.stage_name}_eval_cost", 0.0)
            if eval_cost_spent > 0:
                router.update_budget(stage, cost=eval_cost_spent)

            workflow_id = f"{thread_id}_{stage.stage_name}_{routed_tier}_{iteration_index}"

            if os.environ.get("DBOS_DISABLE") == "1":
                print(f"[DBOS Mock] Bypassing DBOS workflow invocation for test environment.")
                # Pass tool_args properly
                provider_info = registry.get_provider(routed_tier)
                if provider_info and provider_info["type"] == "cli":
                    cli_args = ""
                    if stage.tool_args:
                        cli_args = " " + " ".join([f"--{k} {v}" for k, v in stage.tool_args.items()])
                    output, worker_cost = execute_external_cli.__wrapped__(stage.stage_name, provider_info, modified_prompt + cli_args)
                else:
                    output, worker_cost = execute_external_api.__wrapped__(stage.stage_name, {"type": "api", "litellm_model_name": "gpt-3.5-turbo"}, modified_prompt)
                worker_output = persist_if_large_step.__wrapped__(output)
            else:
                handle = DBOS.start_workflow(universal_step, workflow_id=workflow_id, stage_name=stage.stage_name, routed_tier=routed_tier, prompt=modified_prompt, iteration_index=iteration_index, thread_id=thread_id, tool_args=stage.tool_args)
                worker_output, worker_cost = handle.get_result()

            router.update_budget(stage, cost=worker_cost)

            data_dict = state.get("data", {}).copy()
            data_dict[f"{stage.stage_name}_output"] = worker_output

            # If it's a parallel fanout that was sent to this node, we should append to experiment_results
            # But wait, if this IS the fanout, and the router sends here...

            # If this is standard execution, just return data
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

    # Fanout helper node
    def create_fanout_worker_node(stage: StageDSL, provider_name: str):
        def fanout_worker(state: OverallState):
            print(f"\n--- Executing Parallel Fanout Worker: {stage.stage_name} on {provider_name} ---")
            thread_id = state.get("project_name", "unknown")
            iteration_index = state.get("eval_loops", {}).get(stage.stage_name, 0)

            base_prompt = "Perform the required task based on project data."
            routed_tier, modified_prompt = router.prepare_routing(stage, base_prompt)
            workflow_id = f"{thread_id}_{stage.stage_name}_{provider_name}_{iteration_index}"

            if os.environ.get("DBOS_DISABLE") == "1":
                print(f"[DBOS Mock] Bypassing DBOS workflow invocation for test environment.")
                provider_info = registry.get_provider(provider_name)
                if provider_info and provider_info["type"] == "cli":
                    cli_args = ""
                    if stage.tool_args:
                        cli_args = " " + " ".join([f"--{k} {v}" for k, v in stage.tool_args.items()])
                    output, worker_cost = execute_external_cli.__wrapped__(stage.stage_name, provider_info, modified_prompt + cli_args)
                else:
                    output, worker_cost = execute_external_api.__wrapped__(stage.stage_name, {"type": "api", "litellm_model_name": "gpt-3.5-turbo"}, modified_prompt)
                worker_output = persist_if_large_step.__wrapped__(output)
            else:
                handle = DBOS.start_workflow(universal_step, workflow_id=workflow_id, stage_name=stage.stage_name, routed_tier=routed_tier, prompt=modified_prompt, iteration_index=iteration_index, thread_id=thread_id, tool_args=stage.tool_args, provider_override=provider_name)
                worker_output, worker_cost = handle.get_result()

            return {
                "experiment_results": [{"provider": provider_name, "output": worker_output, "cost": worker_cost}]
            }
        return fanout_worker

    # Fanout routing edge
    def create_fanout_router(stage: StageDSL):
        def route_fanout(state: OverallState):
            sends = []
            for provider in (stage.target_providers or []):
                # Send to a dynamically generated node or mapped node
                node_name = f"worker_{stage.stage_name}_{provider}"
                sends.append(Send(node_name, state))
            return sends
        return route_fanout

    # 2. Add Nodes to Graph
    for i, stage in enumerate(stages):
        if stage.stage_type == "parallel_fanout":
            for provider in (stage.target_providers or []):
                node_name = f"worker_{stage.stage_name}_{provider}"
                builder.add_node(node_name, create_fanout_worker_node(stage, provider))
        else:
            worker_name = f"worker_{stage.stage_name}"
            builder.add_node(worker_name, create_worker_node(stage))

        eval_name = f"evaluator_{stage.stage_name}"
        builder.add_node(eval_name, create_evaluator_node(stage))

    # 3. Add Edges
    if not stages:
        builder.add_edge(START, END)
        return builder.compile(checkpointer=MemorySaver())

    # START to first worker (or router if fanout)
    if stages[0].stage_type == "parallel_fanout":
        builder.add_conditional_edges(START, create_fanout_router(stages[0]))
    else:
        builder.add_edge(START, f"worker_{stages[0].stage_name}")

    for i, stage in enumerate(stages):
        eval_name = f"evaluator_{stage.stage_name}"

        # Worker goes to Evaluator
        if stage.stage_type == "parallel_fanout":
            # All parallel branches go to the evaluator
            for provider in (stage.target_providers or []):
                node_name = f"worker_{stage.stage_name}_{provider}"
                builder.add_edge(node_name, eval_name)
        else:
            worker_name = f"worker_{stage.stage_name}"
            builder.add_edge(worker_name, eval_name)

        # For a clearer logic flow, let's redefine check_eval:
        def create_routing_logic(current_stage, current_index: int):
            is_last = (current_index + 1 == len(stages))
            def route(state: OverallState):
                loops_dict = state.get("eval_loops", {})

                total_loops = sum(loops_dict.values())
                if total_loops > state.get("max_loops", 10):
                    print(f"Global loop safety triggered: total_loops ({total_loops}) > max_loops ({state.get('max_loops', 10)}).")
                    return END

                stage_loops = loops_dict.get(current_stage.stage_name, 0)

                pass_flag = state.get("data", {}).get(f"{current_stage.stage_name}_passed", False)
                if not pass_flag:
                    if stage_loops <= current_stage.max_retries:
                        # Retry current stage
                        if current_stage.stage_type == "parallel_fanout":
                            sends = []
                            for p in (current_stage.target_providers or []):
                                sends.append(Send(f"worker_{current_stage.stage_name}_{p}", state))
                            return sends
                        else:
                            return f"worker_{current_stage.stage_name}"
                    else:
                        print(f"WARNING: Max retries ({current_stage.max_retries}) reached for {current_stage.stage_name}. Moving to next node.")

                if is_last:
                    return END

                # Move to next
                next_stage = stages[current_index + 1]
                if next_stage.stage_type == "parallel_fanout":
                    sends = []
                    for p in (next_stage.target_providers or []):
                        sends.append(Send(f"worker_{next_stage.stage_name}_{p}", state))
                    return sends
                else:
                    return f"worker_{next_stage.stage_name}"
            return route

        builder.add_conditional_edges(
            eval_name,
            create_routing_logic(stage, i)
        )

    # Optional HITL interrupts based on DSL
    interrupt_nodes = []
    for stage in stages:
        if stage.requires_human_approval or stage.stage_type == "data_ingestion":
            # We'll pause before the worker runs
            if stage.stage_type == "parallel_fanout":
                for p in (stage.target_providers or []):
                    interrupt_nodes.append(f"worker_{stage.stage_name}_{p}")
            else:
                interrupt_nodes.append(f"worker_{stage.stage_name}")

    # 4. Compile Graph
    conn = sqlite3.connect("geneva_persistence.db", check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()
    graph = builder.compile(checkpointer=checkpointer, interrupt_before=interrupt_nodes)

    return graph

# This instance is what LangGraph Studio looks for
graph = build_graph("project_dsl.yaml")
