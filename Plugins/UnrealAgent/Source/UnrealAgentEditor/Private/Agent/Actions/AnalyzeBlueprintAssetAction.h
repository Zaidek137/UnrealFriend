#pragma once

#include "Agent/AgentAction.h"

class FAnalyzeBlueprintAssetAction final : public IAgentAction
{
public:
    virtual FString GetName() const override;
    virtual FString GetDescription() const override;
    virtual FAgentActionResult Execute(const FAgentActionRequest& Request) override;
};
