#pragma once

#include "Agent/AgentAction.h"
#include "CoreMinimal.h"
#include "HAL/CriticalSection.h"

class UNREALAGENTRUNTIME_API FAgentActionRegistry
{
public:
    static FAgentActionRegistry& Get();

    void RegisterAction(TSharedRef<IAgentAction> Action);
    void UnregisterAction(const FString& ActionName);
    bool HasAction(const FString& ActionName) const;
    TArray<FString> GetActionNames() const;
    TArray<FAgentActionDescriptor> GetActionDescriptors() const;
    FAgentActionResult Execute(const FAgentActionRequest& Request) const;

private:
    mutable FCriticalSection Mutex;
    TMap<FString, TSharedRef<IAgentAction>> Actions;
};
