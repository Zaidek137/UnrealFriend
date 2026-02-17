#!/usr/bin/env python3
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "apps" / "unreal-agent-web" / "server.py"


def load_server_module():
    spec = importlib.util.spec_from_file_location("unreal_agent_web_server", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load server module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run() -> None:
    server = load_server_module()

    valid_plan = {
        "plan_id": "valid-plan",
        "dry_run": False,
        "steps": [
            {
                "id": "call_fn",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": "/Game/Test/BP_Example",
                    "operation": "call_function",
                    "class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                    "compile_after": False,
                },
            },
            {
                "id": "set_pin_default",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": "/Game/Test/BP_Example",
                    "operation": "set_default",
                    "class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                    "pin_name": "InString",
                    "default_value": "Hello",
                    "compile_after": False,
                },
            },
        ],
        "compile_blueprints": ["/Game/Test/BP_Example"],
    }
    valid_result = server.validate_plan_with_node_library(valid_plan)
    assert_true(valid_result.get("ok", False), f"Expected valid plan, got {valid_result}")

    missing_compile_plan = {
        "plan_id": "missing-compile",
        "dry_run": False,
        "steps": [
            {
                "id": "set_value",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": "/Game/Test/BP_CompileCheck",
                    "operation": "set_default",
                    "variable_name": "Score",
                    "default_value": "0",
                    "compile_after": False,
                },
            }
        ],
    }
    missing_compile_result = server.validate_plan_with_node_library(missing_compile_plan)
    assert_true(not missing_compile_result.get("ok", True), "Expected missing compile coverage to fail")
    compile_errors = " | ".join(missing_compile_result.get("errors", []))
    assert_true("compile_after=false" in compile_errors, f"Expected compile coverage error, got {compile_errors}")

    bad_variable_type_plan = {
        "plan_id": "bad-variable-type",
        "dry_run": True,
        "steps": [
            {
                "id": "add_bad_var",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": "/Game/Test/BP_Example",
                    "operation": "add_variable",
                    "variable_name": "BadVar",
                    "variable_type": "map",
                },
            }
        ],
    }
    bad_variable_type_result = server.validate_plan_with_node_library(bad_variable_type_plan)
    assert_true(not bad_variable_type_result.get("ok", True), "Expected unsupported variable type to fail")

    bad_set_default_plan = {
        "plan_id": "bad-set-default",
        "dry_run": True,
        "steps": [
            {
                "id": "set_missing_target",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": "/Game/Test/BP_Example",
                    "operation": "set_default",
                    "default_value": "true",
                },
            }
        ],
    }
    bad_set_default_result = server.validate_plan_with_node_library(bad_set_default_plan)
    assert_true(not bad_set_default_result.get("ok", True), "Expected incomplete set_default target to fail")

    remove_variable_plan = {
        "plan_id": "remove-variable-ok",
        "dry_run": True,
        "steps": [
            {
                "id": "remove_var",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": "/Game/Test/BP_Example",
                    "operation": "remove_variable",
                    "variable_name": "LegacyRollFlag",
                },
            }
        ],
    }
    remove_variable_result = server.validate_plan_with_node_library(remove_variable_plan)
    assert_true(remove_variable_result.get("ok", False), f"Expected remove_variable plan valid, got {remove_variable_result}")

    remove_function_plan = {
        "plan_id": "remove-function-ok",
        "dry_run": True,
        "steps": [
            {
                "id": "remove_fn",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": "/Game/Test/BP_Example",
                    "operation": "remove_function_call",
                    "class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                },
            }
        ],
    }
    remove_function_result = server.validate_plan_with_node_library(remove_function_plan)
    assert_true(remove_function_result.get("ok", False), f"Expected remove_function_call plan valid, got {remove_function_result}")

    remove_nodes_plan = {
        "plan_id": "remove-nodes-ok",
        "dry_run": True,
        "steps": [
            {
                "id": "remove_nodes",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": "/Game/Test/BP_Example",
                    "operation": "remove_nodes",
                    "node_title_contains": "Print String",
                },
            }
        ],
    }
    remove_nodes_result = server.validate_plan_with_node_library(remove_nodes_plan)
    assert_true(remove_nodes_result.get("ok", False), f"Expected remove_nodes plan valid, got {remove_nodes_result}")

    disconnect_pin_plan = {
        "plan_id": "disconnect-pin-ok",
        "dry_run": True,
        "steps": [
            {
                "id": "disconnect_pin",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": "/Game/Test/BP_Example",
                    "operation": "disconnect_pin",
                    "from_node_name": "K2Node_Event_0",
                    "from_pin_name": "then",
                    "to_node_name": "K2Node_CallFunction_1",
                    "to_pin_name": "execute",
                },
            }
        ],
    }
    disconnect_pin_result = server.validate_plan_with_node_library(disconnect_pin_plan)
    assert_true(disconnect_pin_result.get("ok", False), f"Expected disconnect_pin plan valid, got {disconnect_pin_result}")

    print("Plan validation tests passed.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"Plan validation tests failed: {exc}", file=sys.stderr)
        sys.exit(1)
