#include "Agent/Actions/InspectAssetAction.h"

#include "Agent/AgentJsonUtils.h"
#include "Dom/JsonObject.h"
#include "Engine/Blueprint.h"
#include "Misc/PackageName.h"

namespace UnrealAgentPrivate
{
static FString NormalizeObjectPath(const FString& AssetPathOrObjectPath)
{
    if (AssetPathOrObjectPath.Contains(TEXT(".")))
    {
        return AssetPathOrObjectPath;
    }

    if (!AssetPathOrObjectPath.StartsWith(TEXT("/")))
    {
        return TEXT("");
    }

    const FString AssetName = FPackageName::GetLongPackageAssetName(AssetPathOrObjectPath);
    if (AssetName.IsEmpty())
    {
        return TEXT("");
    }

    return FString::Printf(TEXT("%s.%s"), *AssetPathOrObjectPath, *AssetName);
}
} // namespace UnrealAgentPrivate

FString FInspectAssetAction::GetName() const
{
    return TEXT("inspect_asset");
}

FString FInspectAssetAction::GetDescription() const
{
    return TEXT("Checks whether an asset exists and returns class/type metadata.");
}

FAgentActionResult FInspectAssetAction::Execute(const FAgentActionRequest& Request)
{
    FString AssetPath;
    if (!Request.PayloadJson.IsEmpty())
    {
        TSharedPtr<FJsonObject> Payload;
        FString ParseError;
        if (!UnrealAgentPrivate::ParseJsonObject(Request.PayloadJson, Payload, ParseError))
        {
            return {false, ParseError, TEXT(""), TEXT("INVALID_PAYLOAD")};
        }

        Payload->TryGetStringField(TEXT("asset_path"), AssetPath);
        if (AssetPath.IsEmpty())
        {
            Payload->TryGetStringField(TEXT("blueprint_path"), AssetPath);
        }
    }

    if (AssetPath.IsEmpty())
    {
        return {false, TEXT("Missing required payload field: asset_path"), TEXT(""), TEXT("MISSING_FIELD")};
    }

    const FString ObjectPath = UnrealAgentPrivate::NormalizeObjectPath(AssetPath);
    if (ObjectPath.IsEmpty())
    {
        return {
            false,
            FString::Printf(TEXT("Invalid asset path: %s"), *AssetPath),
            TEXT(""),
            TEXT("INVALID_PATH")
        };
    }

    UObject* Asset = FindObject<UObject>(nullptr, *ObjectPath);
    if (Asset == nullptr)
    {
        Asset = LoadObject<UObject>(nullptr, *ObjectPath);
    }

    const bool bExists = Asset != nullptr;

    const TSharedRef<FJsonObject> ResultPayload = MakeShared<FJsonObject>();
    ResultPayload->SetStringField(TEXT("input_path"), AssetPath);
    ResultPayload->SetStringField(TEXT("object_path"), ObjectPath);
    ResultPayload->SetBoolField(TEXT("exists"), bExists);
    ResultPayload->SetBoolField(TEXT("dry_run"), Request.bDryRun);

    if (bExists)
    {
        ResultPayload->SetStringField(TEXT("resolved_path"), Asset->GetPathName());
        ResultPayload->SetStringField(TEXT("class_path"), Asset->GetClass()->GetPathName());

        const UBlueprint* Blueprint = Cast<UBlueprint>(Asset);
        ResultPayload->SetBoolField(TEXT("is_blueprint"), Blueprint != nullptr);
        if (Blueprint != nullptr)
        {
            ResultPayload->SetStringField(
                TEXT("generated_class_path"),
                Blueprint->GeneratedClass != nullptr ? Blueprint->GeneratedClass->GetPathName() : TEXT("")
            );
            ResultPayload->SetNumberField(TEXT("ubergraph_count"), Blueprint->UbergraphPages.Num());
            ResultPayload->SetNumberField(TEXT("function_graph_count"), Blueprint->FunctionGraphs.Num());
        }
    }

    return {
        true,
        bExists ? TEXT("Asset located.") : TEXT("Asset does not exist."),
        UnrealAgentPrivate::SerializePayload(ResultPayload),
        TEXT("OK")
    };
}
