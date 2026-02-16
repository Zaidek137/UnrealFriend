#include "Agent/Actions/AnalyzeBlueprintAssetAction.h"

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

static void AddGraphGroup(const TArray<UEdGraph*>& Graphs, const FString& GroupName, TArray<TTuple<const UEdGraph*, FString>>& OutGraphs)
{
    for (const UEdGraph* Graph : Graphs)
    {
        if (Graph == nullptr)
        {
            continue;
        }
        OutGraphs.Add(MakeTuple(Graph, GroupName));
    }
}
} // namespace UnrealAgentPrivate

FString FAnalyzeBlueprintAssetAction::GetName() const
{
    return TEXT("analyze_blueprint_asset");
}

FString FAnalyzeBlueprintAssetAction::GetDescription() const
{
    return TEXT("Deterministically analyzes all graphs in a Blueprint asset (ubergraph, function graphs, macro graphs).");
}

FAgentActionResult FAnalyzeBlueprintAssetAction::Execute(const FAgentActionRequest& Request)
{
    FString BlueprintPath;
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
        Payload->TryGetNumberField(TEXT("max_nodes_per_graph"), Options.MaxNodes);
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

    TArray<TTuple<const UEdGraph*, FString>> Graphs;
    UnrealAgentPrivate::AddGraphGroup(Blueprint->UbergraphPages, TEXT("ubergraph"), Graphs);
    UnrealAgentPrivate::AddGraphGroup(Blueprint->FunctionGraphs, TEXT("function"), Graphs);
    UnrealAgentPrivate::AddGraphGroup(Blueprint->MacroGraphs, TEXT("macro"), Graphs);

    if (Graphs.Num() == 0)
    {
        return {
            false,
            TEXT("Blueprint has no analyzable graphs."),
            TEXT(""),
            TEXT("GRAPH_NOT_FOUND")
        };
    }

    TArray<TSharedPtr<FJsonValue>> GraphAnalyses;
    int32 TotalNodes = 0;
    int32 TotalEntryNodes = 0;
    int32 TotalContradictions = 0;

    for (const TTuple<const UEdGraph*, FString>& GraphRef : Graphs)
    {
        const UEdGraph* Graph = GraphRef.Key;
        if (Graph == nullptr)
        {
            continue;
        }

        TSharedRef<FJsonObject> GraphAnalysis = MakeShared<FJsonObject>();
        FString AnalyzeError;
        if (!UnrealAgentPrivate::AnalyzeGraph(Blueprint, Graph, Options, GraphAnalysis, AnalyzeError))
        {
            return {false, AnalyzeError, TEXT(""), TEXT("ANALYSIS_FAILED")};
        }

        GraphAnalysis->SetStringField(TEXT("graph_type"), GraphRef.Value);
        GraphAnalyses.Add(MakeShared<FJsonValueObject>(GraphAnalysis));

        TotalNodes += Graph->Nodes.Num();

        const TArray<TSharedPtr<FJsonValue>>* EntryNodes = nullptr;
        if (GraphAnalysis->TryGetArrayField(TEXT("entry_nodes"), EntryNodes) && EntryNodes != nullptr)
        {
            TotalEntryNodes += EntryNodes->Num();
        }

        const TArray<TSharedPtr<FJsonValue>>* Contradictions = nullptr;
        if (GraphAnalysis->TryGetArrayField(TEXT("contradictions"), Contradictions) && Contradictions != nullptr)
        {
            TotalContradictions += Contradictions->Num();
        }
    }

    TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetStringField(TEXT("blueprint"), Blueprint->GetPathName());
    Result->SetStringField(TEXT("parent_class"), Blueprint->ParentClass != nullptr ? Blueprint->ParentClass->GetPathName() : TEXT(""));
    Result->SetNumberField(TEXT("total_graphs"), GraphAnalyses.Num());
    Result->SetNumberField(TEXT("total_nodes"), TotalNodes);
    Result->SetNumberField(TEXT("total_entry_nodes"), TotalEntryNodes);
    Result->SetNumberField(TEXT("total_contradictions"), TotalContradictions);
    Result->SetArrayField(TEXT("graphs"), GraphAnalyses);
    Result->SetBoolField(TEXT("analysis_ok"), TotalContradictions == 0);

    return {
        TotalContradictions == 0,
        TotalContradictions == 0 ? TEXT("Blueprint asset analysis generated.") : TEXT("Blueprint asset analysis generated with contradictions."),
        UnrealAgentPrivate::SerializePayload(Result),
        TotalContradictions == 0 ? TEXT("OK") : TEXT("ANALYSIS_CONTRADICTION")
    };
}
