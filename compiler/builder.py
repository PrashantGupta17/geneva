import yaml
import os
from typing import Dict, Any, List
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.memory import MemorySaver
from core.schemas import ProjectDSL, StageDSL
from agents.evaluator import StageAwareRouter, EvaluatorNode
from dbos import DBOS

from litellm import completion, completion_cost
from typing import Tuple

# External tool wrapped with DBOS.step for durability
@DBOS.step()
def execute_external_api(stage_name: str, routed_tier: str, prompt: str) -> Tuple[str, float]:
    """
    Demonstrates how individual node operations are made crash-proof.
    If the system crashes during this DBOS step, it won't be re-executed upon restart.
    Actually calls LiteLLM to perform the task and return real cost.
    """
    print(f"[DBOS] Executing actual LLM call for '{stage_name}' using tier '{routed_tier}'...")
    model_name = "gpt-4-turbo" if routed_tier == "premium" else "gpt-3.5-turbo"

    try:
        response = completion(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        output = response.choices[0].message.content
        cost = completion_cost(completion_response=response)
        return output, cost
    except Exception as e:
        print(f"[DBOS] LLM call failed: {e}")
        return f"Error: {e}", 0.0

@DBOS.workflow()
def execute_external_api_workflow(stage_name: str, routed_tier: str, prompt: str) -> Tuple[str, float]:
    return execute_external_api(stage_name, routed_tier, prompt)

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
        return builder.compile(checkpointer=MemorySaver())

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
            worker_output, worker_cost = execute_external_api_workflow(stage.stage_name, routed_tier, modified_prompt)

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
            return {"current_stage_index": state.get("current_stage_index", 0) + 1, "data": data}
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
                stage_loops = loops_dict.get(current_stage.stage_name, 0)

                # Global safety loop counter
                total_loops = sum(loops_dict.values())
                if total_loops >= state.get("max_loops", 10):
                    print(f"CRITICAL: Global max evaluation loops ({total_loops}) reached. Forcing END.")
                    return "end"

                pass_flag = state.get("data", {}).get(f"{current_stage.stage_name}_passed", False)
                if not pass_flag:
                    if stage_loops <= current_stage.max_retries:
                        return "retry"
                    else:
                        print(f"WARNING: Stage '{current_stage.stage_name}' failed after reaching max retries ({current_stage.max_retries}). Moving to next node.")

                if is_last:
                    return "end"
                return "next"
            return route

        if i + 1 < len(stages):
            next_worker = f"worker_{stages[i+1].stage_name}"
            builder.add_conditional_edges(
                eval_name,
                create_routing_logic(stage, is_last=False),
                {"next": next_worker, "retry": worker_name, "end": END}
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
    checkpointer = MemorySaver()
    graph = builder.compile(checkpointer=checkpointer, interrupt_before=interrupt_nodes)

    return graph

# This instance is what LangGraph Studio looks for
graph = build_graph("project_dsl.yaml")
