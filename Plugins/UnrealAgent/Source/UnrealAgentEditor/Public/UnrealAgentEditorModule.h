#pragma once

#include "Agent/AgentAction.h"
#include "Containers/Array.h"
#include "Modules/ModuleManager.h"

class FUnrealAgentEditorModule final : public IModuleInterface
{
public:
    virtual void StartupModule() override;
    virtual void ShutdownModule() override;

private:
    TArray<TSharedPtr<IAgentAction>> RegisteredActions;
};
