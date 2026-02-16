#include "UnrealAgentEditorModule.h"

#include "Agent/Actions/CompileBlueprintAction.h"
#include "Agent/Actions/CreateBlueprintAction.h"
#include "Agent/Actions/AnalyzeBlueprintAssetAction.h"
#include "Agent/Actions/AnalyzeBlueprintGraphAction.h"
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
