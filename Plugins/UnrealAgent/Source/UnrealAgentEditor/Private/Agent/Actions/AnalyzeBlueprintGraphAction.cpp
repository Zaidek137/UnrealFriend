#include "Agent/Actions/AnalyzeBlueprintGraphAction.h"

#include "Agent/Actions/BlueprintAnalysisShared.h"
#include "Agent/AgentJsonUtils.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "EdGraph/EdGraph.h"
#include "Engine/Blueprint.h"
#include "Misc/PackageName.h"

namespace UnrealAgentPrivate
{
static FString NormalizeBlueprintObjectPath(const FString& BlueprintPathOrObjectPath)
{
    if (BlueprintPathOrObjectPath.Contains(TEXT(".")))
    {
        return BlueprintPathOrObjectPath;
    }

    if (!BlueprintPathOrObjectPath.StartsWith(TEXT("/")))
    {
        return TEXT("");
    }

    const FString AssetName = FPackageName::GetLongPackageAssetName(BlueprintPathOrObjectPath);
    if (AssetName.IsEmpty())
    {
        return TEXT("");
    }

    return FString::Printf(TEXT("%s.%s"), *BlueprintPathOrObjectPath, *AssetName);
}

static UEdGraph* ResolveTargetGraph(UBlueprint* Blueprint, const FString& GraphName)
{
    if (Blueprint == nullptr)
    {
        return nullptr;
    }

    auto FindByName = [&](const TArray<UEdGraph*>& Graphs) -> UEdGraph*
    {
        for (UEdGraph* Graph : Graphs)
        {
            if (Graph != nullptr && Graph->GetName().Equals(GraphName, ESearchCase::IgnoreCase))
            {
                return Graph;
            }
        }
        return nullptr;
    };

    if (!GraphName.IsEmpty())
    {
        if (UEdGraph* Found = FindByName(Blueprint->UbergraphPages))
        {
            return Found;
        }
        if (UEdGraph* Found = FindByName(Blueprint->FunctionGraphs))
        {
            return Found;
        }
        if (UEdGraph* Found = FindByName(Blueprint->MacroGraphs))
        {
            return Found;
        }
    }

    if (Blueprint->UbergraphPages.Num() > 0 && Blueprint->UbergraphPages[0] != nullptr)
    {
        return Blueprint->UbergraphPages[0];
    }

    if (Blueprint->FunctionGraphs.Num() > 0 && Blueprint->FunctionGraphs[0] != nullptr)
    {
        return Blueprint->FunctionGraphs[0];
    }

    if (Blueprint->MacroGraphs.Num() > 0 && Blueprint->MacroGraphs[0] != nullptr)
    {
        return Blueprint->MacroGraphs[0];
    }

    return nullptr;
}
} // namespace UnrealAgentPrivate

FString FAnalyzeBlueprintGraphAction::GetName() const
{
    return TEXT("analyze_blueprint_graph");
}

FString FAnalyzeBlueprintGraphAction::GetDescription() const
{
    return TEXT("Deterministically analyzes execution flow, guards, calls, constants, and contradictions for a Blueprint graph.");
}

FAgentActionResult FAnalyzeBlueprintGraphAction::Execute(const FAgentActionRequest& Request)
{
    FString BlueprintPath;
    FString GraphName;
    UnrealAgentPrivate::FGraphAnalysisOptions Options;

    if (!Request.PayloadJson.IsEmpty())
    {
        TSharedPtr<FJsonObject> Payload;
        FString ParseError;
        if (!UnrealAgentPrivate::ParseJsonObject(Request.PayloadJson, Payload, ParseError))
        {
            return {false, ParseError, TEXT(""), TEXT("INVALID_PAYLOAD")};
        }

        Payload->TryGetStringField(TEXT("blueprint_path"), BlueprintPath);
        Payload->TryGetStringField(TEXT("graph_name"), GraphName);
        Payload->TryGetNumberField(TEXT("max_nodes"), Options.MaxNodes);
        Payload->TryGetNumberField(TEXT("max_trace_depth"), Options.MaxTraceDepth);
        Payload->TryGetBoolField(TEXT("include_pins"), Options.bIncludePins);
    }

    if (BlueprintPath.IsEmpty())
    {
        return {false, TEXT("Missing required payload field: blueprint_path"), TEXT(""), TEXT("MISSING_FIELD")};
    }

    const FString ObjectPath = UnrealAgentPrivate::NormalizeBlueprintObjectPath(BlueprintPath);
    if (ObjectPath.IsEmpty())
    {
        return {
            false,
            FString::Printf(TEXT("Invalid blueprint path: %s"), *BlueprintPath),
            TEXT(""),
            TEXT("INVALID_PATH")
        };
    }

    UBlueprint* Blueprint = FindObject<UBlueprint>(nullptr, *ObjectPath);
    if (Blueprint == nullptr)
    {
        Blueprint = LoadObject<UBlueprint>(nullptr, *ObjectPath);
    }

    if (Blueprint == nullptr)
    {
        return {
            false,
            FString::Printf(TEXT("Failed to load blueprint: %s"), *ObjectPath),
            TEXT(""),
            TEXT("ASSET_LOAD_FAILED")
        };
    }

    UEdGraph* TargetGraph = UnrealAgentPrivate::ResolveTargetGraph(Blueprint, GraphName);
    if (TargetGraph == nullptr)
    {
        return {
            false,
            TEXT("Unable to resolve Blueprint graph. The blueprint has no event/function/macro graphs."),
            TEXT(""),
            TEXT("GRAPH_NOT_FOUND")
        };
    }

    TSharedRef<FJsonObject> Analysis = MakeShared<FJsonObject>();
    FString AnalyzeError;
    if (!UnrealAgentPrivate::AnalyzeGraph(Blueprint, TargetGraph, Options, Analysis, AnalyzeError))
    {
        return {false, AnalyzeError, TEXT(""), TEXT("ANALYSIS_FAILED")};
    }

    const TArray<TSharedPtr<FJsonValue>>* Contradictions = nullptr;
    const bool bHasContradictions = Analysis->TryGetArrayField(TEXT("contradictions"), Contradictions)
        && Contradictions != nullptr
        && Contradictions->Num() > 0;

    return {
        !bHasContradictions,
        bHasContradictions ? TEXT("Graph analysis generated with contradictions detected.") : TEXT("Graph analysis generated."),
        UnrealAgentPrivate::SerializePayload(Analysis),
        bHasContradictions ? TEXT("ANALYSIS_CONTRADICTION") : TEXT("OK")
    };
}
