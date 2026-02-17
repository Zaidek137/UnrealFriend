#include "UnrealAgentEditorModule.h"

#include "Agent/Actions/CompileBlueprintAction.h"
#include "Agent/Actions/CreateBlueprintAction.h"
#include "Agent/Actions/AnalyzeBlueprintAssetAction.h"
#include "Agent/Actions/AnalyzeBlueprintGraphAction.h"
#include "Agent/Actions/AutomationCompositeAction.h"
#include "Agent/Actions/InspectAssetAction.h"
#include "Agent/Actions/InspectBlueprintGraphAction.h"
#include "Agent/Actions/ListAssetsAction.h"
#include "Agent/Actions/ModifyBlueprintGraphAction.h"
#include "Agent/Actions/SpawnActorAction.h"
#include "Agent/AgentActionRegistry.h"
#include "Modules/ModuleManager.h"

#define LOCTEXT_NAMESPACE "FUnrealAgentEditorModule"

void FUnrealAgentEditorModule::StartupModule()
{
    RegisteredActions.Reset();
    RegisteredActions.Add(MakeShared<FCreateBlueprintAction>());
    RegisteredActions.Add(MakeShared<FSpawnActorAction>());
    RegisteredActions.Add(MakeShared<FCompileBlueprintAction>());
    RegisteredActions.Add(MakeShared<FModifyBlueprintGraphAction>());
    RegisteredActions.Add(MakeShared<FInspectAssetAction>());
    RegisteredActions.Add(MakeShared<FListAssetsAction>());
    RegisteredActions.Add(MakeShared<FInspectBlueprintGraphAction>());
    RegisteredActions.Add(MakeShared<FAnalyzeBlueprintGraphAction>());
    RegisteredActions.Add(MakeShared<FAnalyzeBlueprintAssetAction>());
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_widget_blueprint"), TEXT("Creates a widget blueprint using deterministic defaults.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("modify_widget_tree"), TEXT("Deterministic widget tree mutation interface (root/add/remove/set_property).")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("bind_widget_events"), TEXT("Deterministic widget event binding (delegate event to callable node wiring).")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("generate_widget_template"), TEXT("Deterministic widget template generation with style presets and default bindings.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("analyze_widget_tree"), TEXT("Deterministic widget lint and binding completeness analysis.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("set_reflected_property"), TEXT("Sets a scalar reflected property on blueprint CDO/component templates/world actors.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_blueprint_function"), TEXT("Creates a blueprint function graph deterministically.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_blueprint_macro"), TEXT("Creates a blueprint macro graph deterministically.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("wire_blueprint_pins"), TEXT("Connects/disconnects graph pins deterministically by node and pin names.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("blueprint_node_authoring"), TEXT("Spawns/replaces K2 nodes (function call, custom event, branch) with deterministic payloads.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("blueprint_compile_diagnostics"), TEXT("Compiles a blueprint and returns graph inventory/analysis diagnostics.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("modify_blueprint_components"), TEXT("Adds/removes/configures blueprint component hierarchy nodes.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("edit_actor_transform"), TEXT("Sets actor transform fields deterministically in editor world.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_game_mode_logic"), TEXT("Creates baseline game mode logic variables and hooks.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_objective_actor"), TEXT("Creates an objective actor with objective tags.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("wire_objective_progress"), TEXT("Wires objective progress variables into blueprint logic.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_timer_system"), TEXT("Creates baseline timer system variables.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_score_system"), TEXT("Creates baseline score system variables.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_restart_flow"), TEXT("Creates baseline restart flow variables.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("batch_spawn_actors"), TEXT("Spawns actors in batch from deterministic payload.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("layout_along_spline"), TEXT("Lays out actors along a deterministic line/spline approximation.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_level_chunk"), TEXT("Creates a deterministic grid level chunk.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("generate_layout_from_template"), TEXT("Generates world layout from deterministic template parameters.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("scatter_assets_with_constraints"), TEXT("Scatters actors using deterministic seed and bounds constraints.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("clear_generated_layout_by_token"), TEXT("Clears generated actors by cleanup token tag.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("tag_and_group_actors"), TEXT("Tags and groups actors by label query.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("delete_actors_by_filter"), TEXT("Deletes actors matching tag/label/folder query.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("clear_map_layout"), TEXT("Clears agent-generated layout actors for a fresh test map.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_data_asset"), TEXT("Creates a primary data asset blueprint.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_behavior_tree_asset"), TEXT("Creates a native BehaviorTree asset with editor factory.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("edit_behavior_tree_asset"), TEXT("Edits BehaviorTree root and task-node topology deterministically.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_blackboard_data_asset"), TEXT("Creates a native BlackboardData asset with editor factory.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("edit_blackboard_data_asset"), TEXT("Edits Blackboard key schema deterministically.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_eqs_query_asset"), TEXT("Creates a native EnvQuery asset with editor factory.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("edit_eqs_query_asset"), TEXT("Edits EQS options/generator/tests deterministically.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_anim_blueprint_asset"), TEXT("Creates an AnimBlueprint scaffold using native blueprint creation path.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("edit_anim_blueprint_state_machine"), TEXT("Edits AnimBlueprint locomotion state-machine scaffold deterministically.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_material_asset"), TEXT("Creates a native Material asset.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("edit_material_asset"), TEXT("Edits deterministic material core properties.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_niagara_system_asset"), TEXT("Creates a native Niagara system asset.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("edit_niagara_system_graph"), TEXT("Applies deterministic Niagara system graph-level scaffolding edits.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_level_sequence_asset"), TEXT("Creates a native Level Sequence asset.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("edit_level_sequence_asset"), TEXT("Applies deterministic Level Sequence edit scaffolding.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_data_table"), TEXT("Scaffolded data table creation interface.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("edit_data_table_row"), TEXT("Scaffolded data table row editing interface.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("validate_data_schema"), TEXT("Validates data schema fields against a row object.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("inspect_compile_errors"), TEXT("Inspects compile status for a blueprint.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("run_pie_scenario"), TEXT("Runs deterministic scenario assertions.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("assert_world_state"), TEXT("Asserts editor world state with deterministic criteria.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("capture_screenshot"), TEXT("Captures a screenshot request into Saved/UnrealAgent/Screenshots.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("list_asset_dependencies"), TEXT("Lists transitive asset dependencies from Asset Registry.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("list_asset_referencers"), TEXT("Lists transitive asset referencers from Asset Registry.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("analyze_asset_impact"), TEXT("Builds deterministic impact view for an asset change.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("analyze_project_hotspots"), TEXT("Builds deterministic project hotspot report from registry connectivity.")));

    for (const TSharedPtr<IAgentAction>& Action : RegisteredActions)
    {
        if (Action.IsValid())
        {
            FAgentActionRegistry::Get().RegisterAction(Action.ToSharedRef());
        }
    }
}

void FUnrealAgentEditorModule::ShutdownModule()
{
    for (const TSharedPtr<IAgentAction>& Action : RegisteredActions)
    {
        if (Action.IsValid())
        {
            FAgentActionRegistry::Get().UnregisterAction(Action->GetName());
        }
    }

    RegisteredActions.Reset();
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FUnrealAgentEditorModule, UnrealAgentEditor)
