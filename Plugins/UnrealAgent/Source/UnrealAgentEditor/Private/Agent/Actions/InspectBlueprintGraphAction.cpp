#include "Agent/Actions/InspectBlueprintGraphAction.h"

#include "Agent/AgentJsonUtils.h"
#include "Dom/JsonObject.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
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

    if (!GraphName.IsEmpty())
    {
        for (UEdGraph* Graph : Blueprint->UbergraphPages)
        {
            if (Graph != nullptr && Graph->GetName().Equals(GraphName, ESearchCase::IgnoreCase))
            {
                return Graph;
            }
        }
        for (UEdGraph* Graph : Blueprint->FunctionGraphs)
        {
            if (Graph != nullptr && Graph->GetName().Equals(GraphName, ESearchCase::IgnoreCase))
            {
                return Graph;
            }
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

    return nullptr;
}
} // namespace UnrealAgentPrivate

FString FInspectBlueprintGraphAction::GetName() const
{
    return TEXT("inspect_blueprint_graph");
}

FString FInspectBlueprintGraphAction::GetDescription() const
{
    return TEXT("Returns a node inventory for a Blueprint graph (Event Graph by default).");
}

FAgentActionResult FInspectBlueprintGraphAction::Execute(const FAgentActionRequest& Request)
{
    FString BlueprintPath;
    FString GraphName;
    int32 MaxNodes = 250;
    bool bIncludePins = false;

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
        Payload->TryGetNumberField(TEXT("max_nodes"), MaxNodes);
        Payload->TryGetBoolField(TEXT("include_pins"), bIncludePins);
    }

    if (BlueprintPath.IsEmpty())
    {
        return {false, TEXT("Missing required payload field: blueprint_path"), TEXT(""), TEXT("MISSING_FIELD")};
    }

    MaxNodes = FMath::Clamp(MaxNodes, 1, 2000);

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
            TEXT("Unable to resolve Blueprint graph. The blueprint has no event/function graphs."),
            TEXT(""),
            TEXT("GRAPH_NOT_FOUND")
        };
    }

    TArray<TSharedPtr<FJsonValue>> Nodes;
    Nodes.Reserve(FMath::Min(TargetGraph->Nodes.Num(), MaxNodes));

    int32 Count = 0;
    for (UEdGraphNode* Node : TargetGraph->Nodes)
    {
        if (Node == nullptr)
        {
            continue;
        }
        if (Count >= MaxNodes)
        {
            break;
        }

        TSharedRef<FJsonObject> NodeObject = MakeShared<FJsonObject>();
        NodeObject->SetStringField(TEXT("name"), Node->GetName());
        NodeObject->SetStringField(TEXT("title"), Node->GetNodeTitle(ENodeTitleType::ListView).ToString());
        NodeObject->SetStringField(TEXT("class"), Node->GetClass()->GetPathName());
        NodeObject->SetNumberField(TEXT("pos_x"), Node->NodePosX);
        NodeObject->SetNumberField(TEXT("pos_y"), Node->NodePosY);
        NodeObject->SetNumberField(TEXT("pin_count"), Node->Pins.Num());

        if (bIncludePins)
        {
            TArray<TSharedPtr<FJsonValue>> Pins;
            Pins.Reserve(Node->Pins.Num());

            for (const UEdGraphPin* Pin : Node->Pins)
            {
                if (Pin == nullptr)
                {
                    continue;
                }

                TSharedRef<FJsonObject> PinObject = MakeShared<FJsonObject>();
                PinObject->SetStringField(TEXT("name"), Pin->PinName.ToString());
                PinObject->SetStringField(TEXT("direction"), Pin->Direction == EGPD_Input ? TEXT("input") : TEXT("output"));
                PinObject->SetStringField(TEXT("category"), Pin->PinType.PinCategory.ToString());
                PinObject->SetNumberField(TEXT("links"), Pin->LinkedTo.Num());
                Pins.Add(MakeShared<FJsonValueObject>(PinObject));
            }

            NodeObject->SetArrayField(TEXT("pins"), Pins);
        }

        Nodes.Add(MakeShared<FJsonValueObject>(NodeObject));
        ++Count;
    }

    const TSharedRef<FJsonObject> ResultPayload = MakeShared<FJsonObject>();
    ResultPayload->SetStringField(TEXT("blueprint"), Blueprint->GetPathName());
    ResultPayload->SetStringField(TEXT("graph_name"), TargetGraph->GetName());
    ResultPayload->SetNumberField(TEXT("total_nodes"), TargetGraph->Nodes.Num());
    ResultPayload->SetNumberField(TEXT("returned_nodes"), Nodes.Num());
    ResultPayload->SetBoolField(TEXT("truncated"), TargetGraph->Nodes.Num() > Nodes.Num());
    ResultPayload->SetBoolField(TEXT("include_pins"), bIncludePins);
    ResultPayload->SetArrayField(TEXT("nodes"), Nodes);

    return {
        true,
        TEXT("Blueprint graph inventory generated."),
        UnrealAgentPrivate::SerializePayload(ResultPayload),
        TEXT("OK")
    };
}
