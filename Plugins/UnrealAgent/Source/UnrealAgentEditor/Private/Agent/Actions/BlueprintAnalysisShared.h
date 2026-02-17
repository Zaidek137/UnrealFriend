#pragma once

#include "CoreMinimal.h"

class UBlueprint;
class UEdGraph;
class FJsonObject;
class FJsonValue;

namespace UnrealAgentPrivate
{
struct FGraphAnalysisOptions
{
    int32 MaxNodes = 2000;
    int32 MaxTraceDepth = 64;
    bool bIncludePins = true;
};

bool AnalyzeGraph(
    const UBlueprint* Blueprint,
    const UEdGraph* Graph,
    const FGraphAnalysisOptions& Options,
    TSharedRef<FJsonObject>& OutAnalysis,
    FString& OutError
);

void AppendPinSnapshot(const UEdGraph* Graph, TArray<TSharedPtr<FJsonValue>>& OutPins);
} // namespace UnrealAgentPrivate
