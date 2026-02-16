#pragma once

#include "Agent/AgentTypes.h"
#include "CoreMinimal.h"

class UNREALAGENTRUNTIME_API IAgentAction
{
public:
    virtual ~IAgentAction() = default;

    virtual FString GetName() const = 0;
    virtual FString GetDescription() const = 0;
    virtual FAgentActionResult Execute(const FAgentActionRequest& Request) = 0;
};
