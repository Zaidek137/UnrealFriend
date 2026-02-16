#pragma once

#include "Agent/AgentAction.h"

class FAutomationCompositeAction final : public IAgentAction
{
public:
    FAutomationCompositeAction(const FString& InName, const FString& InDescription);

    virtual FString GetName() const override;
    virtual FString GetDescription() const override;
    virtual FAgentActionResult Execute(const FAgentActionRequest& Request) override;

private:
    FString Name;
    FString Description;
};
