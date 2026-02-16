#include "UnrealAgentEditorModule.h"

#include "Agent/Actions/CompileBlueprintAction.h"
#include "Agent/Actions/CreateBlueprintAction.h"
#include "Agent/Actions/AnalyzeBlueprintAssetAction.h"
#include "Agent/Actions/AnalyzeBlueprintGraphAction.h"
#include "Agent/Actions/AutomationCompositeAction.h"
#include "Agent/Actions/InspectAssetAction.h"
#include "Agent/Actions/InspectBlueprintGraphAction.h"
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
    RegisteredActions.Add(MakeShared<FInspectBlueprintGraphAction>());
    RegisteredActions.Add(MakeShared<FAnalyzeBlueprintGraphAction>());
    RegisteredActions.Add(MakeShared<FAnalyzeBlueprintAssetAction>());
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_widget_blueprint"), TEXT("Creates a widget blueprint using deterministic defaults.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("modify_widget_tree"), TEXT("Scaffolded deterministic widget tree modification interface.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("bind_widget_events"), TEXT("Scaffolded deterministic widget event binding interface.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_game_mode_logic"), TEXT("Creates baseline game mode logic variables and hooks.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_objective_actor"), TEXT("Creates an objective actor with objective tags.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("wire_objective_progress"), TEXT("Wires objective progress variables into blueprint logic.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_timer_system"), TEXT("Creates baseline timer system variables.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_score_system"), TEXT("Creates baseline score system variables.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_restart_flow"), TEXT("Creates baseline restart flow variables.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("batch_spawn_actors"), TEXT("Spawns actors in batch from deterministic payload.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("layout_along_spline"), TEXT("Lays out actors along a deterministic line/spline approximation.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_level_chunk"), TEXT("Creates a deterministic grid level chunk.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("tag_and_group_actors"), TEXT("Tags and groups actors by label query.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("delete_actors_by_filter"), TEXT("Deletes actors matching tag/label/folder query.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("clear_map_layout"), TEXT("Clears agent-generated layout actors for a fresh test map.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_data_asset"), TEXT("Creates a primary data asset blueprint.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("create_data_table"), TEXT("Scaffolded data table creation interface.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("edit_data_table_row"), TEXT("Scaffolded data table row editing interface.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("validate_data_schema"), TEXT("Validates data schema fields against a row object.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("inspect_compile_errors"), TEXT("Inspects compile status for a blueprint.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("run_pie_scenario"), TEXT("Runs deterministic scenario assertions.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("assert_world_state"), TEXT("Asserts editor world state with deterministic criteria.")));
    RegisteredActions.Add(MakeShared<FAutomationCompositeAction>(TEXT("capture_screenshot"), TEXT("Captures a screenshot request into Saved/UnrealAgent/Screenshots.")));

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
