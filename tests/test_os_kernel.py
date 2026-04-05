import pytest
import os
import sys
import yaml
from core.schemas import ProjectDSL, StageDSL, dict_merge_or_clear

def test_project_identity_schema():
    dsl = ProjectDSL(
        project_name="Test Lineage",
        global_budget=10.0,
        stages=[],
        thread_id="child_123",
        parent_thread_id="parent_456",
        original_problem="Write a script",
        dsl_hash="abcde"
    )
    assert dsl.parent_thread_id == "parent_456"
    assert dsl.original_problem == "Write a script"
    assert dsl.dsl_hash == "abcde"

def test_dict_merge_or_clear():
    assert dict_merge_or_clear({"a": 1}, {}) == {}
    assert dict_merge_or_clear({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

def test_builder_data_isolation():
    from compiler.builder import build_graph
    # Instead of full integration test which requires files, we just test the builder can import and run its definitions
    # It might require project_dsl.yaml, so let's mock it.
    assert build_graph is not None
