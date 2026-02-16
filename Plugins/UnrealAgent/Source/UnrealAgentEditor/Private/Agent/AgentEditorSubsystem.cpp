#include "Agent/AgentEditorSubsystem.h"

#include "Agent/AgentActionRegistry.h"
#include "Agent/AgentJsonUtils.h"

FString UAgentEditorSubsystem::ExecuteAction(const FString& ActionName, const FString& PayloadJson, const bool bDryRun)
{
    FAgentActionRequest Request;
    Request.ActionName = ActionName;
    Request.PayloadJson = PayloadJson;
    Request.bDryRun = bDryRun;

    const FAgentActionResult Result = FAgentActionRegistry::Get().Execute(Request);
    return UnrealAgentPrivate::SerializeActionResult(Result);
}

TArray<FString> UAgentEditorSubsystem::ListActions() const
{
    return FAgentActionRegistry::Get().GetActionNames();
}
