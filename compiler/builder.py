import yaml
import os
import sqlite3
from typing import Dict, Any, List, Annotated
import operator
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.memory import MemorySaver
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver
from core.schemas import ProjectDSL, StageDSL, dict_merge_or_clear
from agents.evaluator import StageAwareRouter, EvaluatorNode
from dbos import DBOS
from langgraph.types import Send

import subprocess
from litellm import completion, completion_cost
from typing import Tuple, Optional
import json
import hashlib

from core.registry import ProviderRegistry
from utils.storage import StorageManager, resolve_payload
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

from litellm import Router

# Initialize litellm.Router
model_list = []
if os.path.exists("geneva_config.yaml"):
    with open("geneva_config.yaml", "r") as f:
        config = yaml.safe_load(f) or {}
        models = config.get("models", [])
        model_list = [{"model_name": m["pool_name"], "litellm_params": {"model": f"{m['provider']}/{m['model_id']}"}} for m in models]

if model_list:
    litellm_router = Router(model_list=model_list, num_retries=2)
else:
    litellm_router = None


# External tool wrapped with DBOS.step for durability
@DBOS.step()
def execute_external_api(stage_name: str, provider_info: dict, prompt: str, tool_args: Dict = None) -> Tuple[str, float]:
    print(f"[DBOS] Executing API LLM call for '{stage_name}'...")
    model_name = provider_info.get("litellm_model_name", "gpt-3.5-turbo")

    tool_args = tool_args or {}

    # Filter for valid LiteLLM kwargs
    valid_kwargs = ["temperature", "max_tokens", "top_p", "frequency_penalty", "presence_penalty", "response_format", "seed", "tools", "tool_choice"]
    filtered_tool_args = {k: v for k, v in tool_args.items() if k in valid_kwargs}

    if "temperature" not in filtered_tool_args:
        filtered_tool_args["temperature"] = 0.0

    try:
        # Use litellm_router if available and we are using pool_name as model_name
        if litellm_router and any(m["model_name"] == model_name for m in model_list):
            response = litellm_router.completion(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                **filtered_tool_args
            )
        else:
            response = completion(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                **filtered_tool_args
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
def execute_external_cli(stage_name: str, provider_info: dict, prompt: str, tool_args: Dict = None) -> Tuple[str, float]:
    print(f"[DBOS] Executing CLI command for '{stage_name}'...")
    cli_path = provider_info.get("absolute_path", "")

    tool_args = tool_args or {}

    try:
        # Pass the prompt to the CLI using a standard approach (e.g., echo prompt | cli or pass as arg)
        # We will assume passing it via stdin or as an argument. Let's write it to a temp file and pass it.
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(prompt)
            temp_path = f.name

        cli_args_str = " ".join([f"{k} {v}" if v else f"{k}" for k, v in tool_args.items()])

        result = subprocess.run(
            f"{cli_path} {cli_args_str} < \"{temp_path}\"",
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

def get_content_hash(prompt: str, model: str, tool_args: Dict) -> str:
    """Creates a SHA256 hash of the prompt string, model tier, and serialized tool arguments."""
    # Phase 2: Ensure the model parameter used in the hash is the generic pool_name
    # to allow cache hits across providers.

    # Check if the model is actually a specific provider model and resolve it to pool_name if possible.
    pool_name = model
    if 'litellm_router' in globals() and litellm_router:
        for m in model_list:
            # If the model passed matches a pool name, use it
            if m["model_name"] == model:
                pool_name = model
                break
            # If it matches a specific provider/model, resolve to pool_name
            elif m["litellm_params"]["model"] == model:
                pool_name = m["model_name"]
                break

    payload = {
        "prompt": prompt,
        "model": pool_name,
        "tool_args": tool_args or {}
    }
    payload_str = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(payload_str.encode('utf-8')).hexdigest()

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
def universal_step(stage_name: str, routed_tier: str, prompt: str, iteration_index: int, tool_args: Optional[Dict] = None, provider_override: Optional[str] = None) -> Tuple[str, float]:
    """
    Universal executor that handles routing to either CLI or API provider.
    Wrapped in a single DBOS.workflow to guarantee atomicity.
    """
    provider_name = provider_override or routed_tier
    provider_info = registry.get_provider(provider_name)

    if provider_info and provider_info["type"] == "cli":
        output, cost = execute_external_cli(stage_name, provider_info, prompt, tool_args)
    else:
        model_name = "gpt-4-turbo" if routed_tier == "premium" else "gpt-3.5-turbo"
        if provider_info and provider_info["type"] == "api":
            model_name = provider_info.get("litellm_model_name", model_name)

        # In the context of pooled load balancing, routed_tier is often the pool_name
        # We should pass routed_tier as the model name to use the router properly
        if litellm_router and any(m["model_name"] == routed_tier for m in model_list):
            model_name = routed_tier

        mock_provider = {"type": "api", "litellm_model_name": model_name}
        output, cost = execute_external_api(stage_name, mock_provider, prompt, tool_args)

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
    experiment_results: Annotated[Dict[str, Any], dict_merge_or_clear]
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
        from langgraph.checkpoint.sqlite import SqliteSaver
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

                path = state.get("ingestion_path")
                content = ""
                if path:
                    if path.startswith("http"):
                        import requests
                        try:
                            content = requests.get(path).text
                        except Exception as e:
                            content = f"Error fetching URL: {e}"
                    elif os.path.isdir(path):
                        content = ""
                        for root, _, files in os.walk(path):
                            for f in files:
                                if f.endswith((".txt", ".md", ".py", ".csv", ".json")):
                                    try:
                                        with open(os.path.join(root, f), "r", encoding="utf-8") as file:
                                            content += f"--- File: {f} ---\n{file.read()}\n\n"
                                    except Exception:
                                        continue
                    else:
                        try:
                            with open(path, "r", encoding="utf-8") as f:
                                content = f.read()
                        except Exception as e:
                            content = f"Error reading file: {e}"

                data_dict = state.get("data", {}).copy()
                if stage.stage_name not in data_dict: data_dict[stage.stage_name] = {}
                data_dict[stage.stage_name]["output"] = storage_manager.persist_if_large(content)
                return {"data": data_dict}

            if stage.stage_type == "ephemeral_code":
                # Phase 6.2: ephemeral_code Execution
                print(f"Executing ephemeral code...")
                # Find previous stage output as data
                # Only pass the previous stage's output to keep the context window lean
                previous_output = ""
                if i > 0:
                    prev_stage_name = stages[i - 1].stage_name
                    previous_output = state.get("data", {}).get(prev_stage_name, {}).get("output", "")

                resolved_previous = resolve_payload(previous_output)
                raw_data = json.dumps(resolved_previous) if not isinstance(resolved_previous, str) else resolved_previous

                try:
                    coerced_data = coercer.sanitize_for_computation(raw_data, stage.input_schema or {})
                    coerced_data = resolve_payload(coerced_data)
                except Exception as e:
                    coerced_data = {"error": str(e)}

                if os.environ.get("DBOS_DISABLE") == "1":
                    worker_output, worker_cost = execute_ephemeral_code.__wrapped__(stage.stage_name, stage.ephemeral_script, coerced_data)
                else:
                    content_hash = get_content_hash(stage.ephemeral_script, "code", coerced_data)
                    workflow_id = f"{stage.stage_name}_{content_hash}_iter{iteration_index}"
                    handle = DBOS.start_workflow(execute_ephemeral_code, workflow_id=workflow_id, stage_name=stage.stage_name, script=stage.ephemeral_script, input_data=coerced_data)
                    worker_output, worker_cost = handle.get_result()

                data_dict = state.get("data", {}).copy()
                if stage.stage_name not in data_dict: data_dict[stage.stage_name] = {}
                data_dict[stage.stage_name]["output"] = storage_manager.persist_if_large(worker_output)
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
            current_spent = state.get("data", {}).get(stage.stage_name, {}).get("eval_cost", 0.0)

            base_prompt = "Perform the required task based on project data."
            routed_tier, modified_prompt = router.prepare_routing(stage, base_prompt, current_spent)
            print(f"Worker Routed Model Tier: {routed_tier}")

            content_hash = get_content_hash(modified_prompt, routed_tier, stage.tool_args)
            workflow_id = f"{stage.stage_name}_{content_hash}_iter{iteration_index}"

            if os.environ.get("DBOS_DISABLE") == "1":
                print(f"[DBOS Mock] Bypassing DBOS workflow invocation for test environment.")
                # Pass tool_args properly
                provider_info = registry.get_provider(routed_tier)
                if provider_info and provider_info["type"] == "cli":
                    output, worker_cost = execute_external_cli.__wrapped__(stage.stage_name, provider_info, modified_prompt, stage.tool_args)
                else:
                    output, worker_cost = execute_external_api.__wrapped__(stage.stage_name, {"type": "api", "litellm_model_name": "gpt-3.5-turbo"}, modified_prompt, stage.tool_args)
                worker_output = persist_if_large_step.__wrapped__(output)
            else:
                handle = DBOS.start_workflow(universal_step, workflow_id=workflow_id, stage_name=stage.stage_name, routed_tier=routed_tier, prompt=modified_prompt, iteration_index=iteration_index, tool_args=stage.tool_args)
                worker_output, worker_cost = handle.get_result()

            data_dict = state.get("data", {}).copy()
            current_cost = data_dict.get(stage.stage_name, {}).get("eval_cost", 0.0)
            if stage.stage_name not in data_dict: data_dict[stage.stage_name] = {}
            data_dict[stage.stage_name]["eval_cost"] = current_cost + worker_cost
            if stage.stage_name not in data_dict: data_dict[stage.stage_name] = {}
            data_dict[stage.stage_name]["output"] = worker_output

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
            data = state.get("data", {}).copy()
            current_loops = state.get("eval_loops", {}).copy()
            stage_loops = current_loops.get(stage.stage_name, 0)

            if stage.stage_type == "parallel_fanout":
                experiment_results = state.get("experiment_results", {})
                worker_output = json.dumps(resolve_payload(experiment_results))
            else:
                worker_output = data.get(stage.stage_name, {}).get("output", "")

            passes, eval_cost = evaluator_agent.evaluate(stage, worker_output)

            if stage.stage_name not in data: data[stage.stage_name] = {}
            data[stage.stage_name]["passed"] = passes
            current_cost = data.get(stage.stage_name, {}).get("eval_cost", 0.0)
            data[stage.stage_name]["eval_cost"] = current_cost + eval_cost

            if not passes:
                print(f"Evaluation FAILED. Incrementing loop counter to {stage_loops + 1}.")
                current_loops[stage.stage_name] = stage_loops + 1
                return {"eval_loops": current_loops, "data": data}

            print(f"Evaluation PASSED.")
            result_state = {
                "current_stage_index": state.get("current_stage_index", 0) + 1,
                "data": data
            }

            if stage.stage_type == "parallel_fanout":
                data[stage.stage_name]["output"] = worker_output
                result_state["experiment_results"] = {}
                result_state["data"] = data

            return result_state
        return evaluator

    # Phase 4: The Parallel Rewrite - Fanout helper node
    def create_fanout_worker_node(stage: StageDSL):
        def fanout_worker(state: OverallState):
            import concurrent.futures

            print(f"\n--- Executing Parallel Fanout Worker: {stage.stage_name} ---")
            thread_id = state.get("project_name", "unknown")
            iteration_index = state.get("eval_loops", {}).get(stage.stage_name, 0)

            current_spent = state.get("data", {}).get(stage.stage_name, {}).get("eval_cost", 0.0)

            base_prompt = "Perform the required task based on project data."
            routed_tier, modified_prompt = router.prepare_routing(stage, base_prompt, current_spent)

            def execute_for_provider(provider_name: str):
                content_hash = get_content_hash(modified_prompt, provider_name, stage.tool_args)
                workflow_id = f"{stage.stage_name}_{content_hash}_iter{iteration_index}"
                if os.environ.get("DBOS_DISABLE") == "1":
                    provider_info = registry.get_provider(provider_name)
                    if provider_info and provider_info.get("type") == "cli":
                        output, worker_cost = execute_external_cli.__wrapped__(stage.stage_name, provider_info, modified_prompt, stage.tool_args)
                    else:
                        output, worker_cost = execute_external_api.__wrapped__(stage.stage_name, {"type": "api", "litellm_model_name": "gpt-3.5-turbo"}, modified_prompt, stage.tool_args)
                    worker_output = persist_if_large_step.__wrapped__(output)
                    return provider_name, {"output": worker_output, "cost": worker_cost}
                else:
                    handle = DBOS.start_workflow(universal_step, workflow_id=workflow_id, stage_name=stage.stage_name, routed_tier=routed_tier, prompt=modified_prompt, iteration_index=iteration_index, tool_args=stage.tool_args, provider_override=provider_name)
                    worker_output, worker_cost = handle.get_result()
                    return provider_name, {"output": worker_output, "cost": worker_cost}

            experiment_results = {}
            total_worker_cost = 0.0
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = {executor.submit(execute_for_provider, p): p for p in (stage.target_providers or [])}
                for future in concurrent.futures.as_completed(futures):
                    p_name, res = future.result()
                    experiment_results[p_name] = res
                    total_worker_cost += res.get("cost", 0.0)

            data_dict = state.get("data", {}).copy()
            current_cost = data_dict.get(stage.stage_name, {}).get("eval_cost", 0.0)
            if stage.stage_name not in data_dict: data_dict[stage.stage_name] = {}
            data_dict[stage.stage_name]["eval_cost"] = current_cost + total_worker_cost

            return {
                "experiment_results": experiment_results,
                "data": data_dict
            }
        return fanout_worker

    # 2. Add Nodes to Graph
    for i, stage in enumerate(stages):
        if stage.stage_type == "parallel_fanout":
            node_name = f"worker_parallel_fanout_{stage.stage_name}"
            builder.add_node(node_name, create_fanout_worker_node(stage))
        else:
            worker_name = f"worker_{stage.stage_name}"
            builder.add_node(worker_name, create_worker_node(stage))

        eval_name = f"evaluator_{stage.stage_name}"
        builder.add_node(eval_name, create_evaluator_node(stage))

    # 3. Add Edges
    if not stages:
        builder.add_edge(START, END)
        return builder.compile(checkpointer=MemorySaver())

    # START to first worker
    if stages[0].stage_type == "parallel_fanout":
        builder.add_edge(START, f"worker_parallel_fanout_{stages[0].stage_name}")
    else:
        builder.add_edge(START, f"worker_{stages[0].stage_name}")

    for i, stage in enumerate(stages):
        eval_name = f"evaluator_{stage.stage_name}"

        # Worker goes to Evaluator
        if stage.stage_type == "parallel_fanout":
            node_name = f"worker_parallel_fanout_{stage.stage_name}"
            builder.add_edge(node_name, eval_name)
        else:
            worker_name = f"worker_{stage.stage_name}"
            builder.add_edge(worker_name, eval_name)

        # For a clearer logic flow, let's redefine check_eval:
        def create_routing_logic(current_stage, current_index: int):
            is_last = (current_index + 1 == len(stages))
            def route(state: OverallState):
                loops_dict = state.get("eval_loops", {})
                stage_loops = loops_dict.get(current_stage.stage_name, 0)

                pass_flag = state.get("data", {}).get(current_stage.stage_name, {}).get("passed", False)
                if not pass_flag:
                    if stage_loops <= current_stage.max_retries:
                        # Retry current stage
                        if current_stage.stage_type == "parallel_fanout":
                            return f"worker_parallel_fanout_{current_stage.stage_name}"
                        else:
                            return f"worker_{current_stage.stage_name}"
                    else:
                        print(f"WARNING: Max retries ({current_stage.max_retries}) reached for {current_stage.stage_name}. Moving to next node.")

                if is_last:
                    return END

                # Move to next
                next_stage = stages[current_index + 1]
                if next_stage.stage_type == "parallel_fanout":
                    return f"worker_parallel_fanout_{next_stage.stage_name}"
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
            # UX Interrupt Reversal: Pause before the evaluator runs so user can see output first
            interrupt_nodes.append(f"evaluator_{stage.stage_name}")

    # 4. Compile Graph
    # Database Unification: LangGraph + DBOS on Postgres
    dbos_url = os.environ.get("DBOS_DATABASE_URL")
    if not dbos_url:
        try:
            with open("dbos-config.yaml", "r") as f:
                dbos_cfg = yaml.safe_load(f)
                db_cfg = dbos_cfg.get("database", {})
                host = db_cfg.get("hostname", "localhost")
                port = db_cfg.get("port", 5432)
                user = db_cfg.get("username", "postgres")
                password = db_cfg.get("password", "password")
                dbname = db_cfg.get("app_db_name", "dbos")
                dbos_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
        except Exception:
            dbos_url = "postgresql://postgres:password@localhost:5432/dbos"

    if os.environ.get("DBOS_DISABLE") != "1":
        # Enable autocommit to allow CREATE INDEX CONCURRENTLY in migrations
        pool = ConnectionPool(conninfo=dbos_url, max_size=20, kwargs={"autocommit": True})
        checkpointer = PostgresSaver(pool)
        checkpointer.setup()
        graph = builder.compile(checkpointer=checkpointer, interrupt_before=interrupt_nodes)
    else:
        # Mock for tests
        checkpointer = MemorySaver()
        graph = builder.compile(checkpointer=checkpointer, interrupt_before=interrupt_nodes)

    return graph

# This instance is what LangGraph Studio looks for
if os.environ.get("DBOS_DISABLE") != "1":
    graph = build_graph("project_dsl.yaml")
else:
    graph = None
