#include "Agent/Actions/ListAssetsAction.h"

#include "Agent/AgentJsonUtils.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Misc/PackageName.h"
#include "Modules/ModuleManager.h"

FString FListAssetsAction::GetName() const
{
    return TEXT("list_assets");
}

FString FListAssetsAction::GetDescription() const
{
    return TEXT("Lists assets in a project package path deterministically.");
}

FAgentActionResult FListAssetsAction::Execute(const FAgentActionRequest& Request)
{
    FString PackagePath = TEXT("/Game");
    bool bRecursive = true;
    FString NameContains;
    int32 Limit = 5000;
    TSet<FString> ClassFilterSet;

    if (!Request.PayloadJson.IsEmpty())
    {
        TSharedPtr<FJsonObject> Payload;
        FString ParseError;
        if (!UnrealAgentPrivate::ParseJsonObject(Request.PayloadJson, Payload, ParseError))
        {
            return {false, ParseError, TEXT(""), TEXT("INVALID_PAYLOAD")};
        }

        Payload->TryGetStringField(TEXT("package_path"), PackagePath);
        Payload->TryGetBoolField(TEXT("recursive"), bRecursive);
        Payload->TryGetStringField(TEXT("name_contains"), NameContains);
        double LimitNumber = static_cast<double>(Limit);
        if (Payload->TryGetNumberField(TEXT("limit"), LimitNumber))
        {
            Limit = FMath::Clamp(static_cast<int32>(LimitNumber), 1, 50000);
        }

        const TArray<TSharedPtr<FJsonValue>>* ClassPathsArr = nullptr;
        if (Payload->TryGetArrayField(TEXT("class_paths"), ClassPathsArr) && ClassPathsArr != nullptr)
        {
            for (const TSharedPtr<FJsonValue>& Value : *ClassPathsArr)
            {
                FString ClassPath;
                if (Value.IsValid() && Value->TryGetString(ClassPath))
                {
                    const FString Normalized = ClassPath.TrimStartAndEnd().ToLower();
                    if (!Normalized.IsEmpty())
                    {
                        ClassFilterSet.Add(Normalized);
                    }
                }
            }
        }
    }

    if (!PackagePath.StartsWith(TEXT("/")))
    {
        return {
            false,
            FString::Printf(TEXT("Invalid package_path: %s"), *PackagePath),
            TEXT(""),
            TEXT("INVALID_PATH")
        };
    }

    FARFilter Filter;
    Filter.PackagePaths.Add(*PackagePath);
    Filter.bRecursivePaths = bRecursive;
    Filter.bRecursiveClasses = true;

    FAssetRegistryModule& AssetRegistryModule = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry"));
    IAssetRegistry& AssetRegistry = AssetRegistryModule.Get();
    TArray<FAssetData> Assets;
    AssetRegistry.GetAssets(Filter, Assets);

    const FString NameContainsLower = NameContains.TrimStartAndEnd().ToLower();
    const bool bHasNameFilter = !NameContainsLower.IsEmpty();

    int32 Matched = 0;
    bool bTruncated = false;
    TArray<TSharedPtr<FJsonValue>> AssetValues;
    AssetValues.Reserve(FMath::Min(Assets.Num(), Limit));

    for (const FAssetData& AssetData : Assets)
    {
        const FString AssetName = AssetData.AssetName.ToString();
        const FString ClassPath = AssetData.AssetClassPath.ToString();
        const FString ClassPathLower = ClassPath.ToLower();

        if (ClassFilterSet.Num() > 0 && !ClassFilterSet.Contains(ClassPathLower))
        {
            continue;
        }
        if (bHasNameFilter && !AssetName.ToLower().Contains(NameContainsLower))
        {
            continue;
        }

        ++Matched;
        if (AssetValues.Num() >= Limit)
        {
            bTruncated = true;
            continue;
        }

        const TSharedRef<FJsonObject> AssetObject = MakeShared<FJsonObject>();
        AssetObject->SetStringField(TEXT("asset_name"), AssetName);
        AssetObject->SetStringField(TEXT("package_name"), AssetData.PackageName.ToString());
        AssetObject->SetStringField(TEXT("object_path"), AssetData.GetObjectPathString());
        AssetObject->SetStringField(TEXT("class_path"), ClassPath);
        AssetValues.Add(MakeShared<FJsonValueObject>(AssetObject));
    }

    const TSharedRef<FJsonObject> ResultPayload = MakeShared<FJsonObject>();
    ResultPayload->SetStringField(TEXT("package_path"), PackagePath);
    ResultPayload->SetBoolField(TEXT("recursive"), bRecursive);
    ResultPayload->SetStringField(TEXT("name_contains"), NameContains);
    ResultPayload->SetNumberField(TEXT("limit"), Limit);
    ResultPayload->SetNumberField(TEXT("matched"), Matched);
    ResultPayload->SetNumberField(TEXT("returned"), AssetValues.Num());
    ResultPayload->SetBoolField(TEXT("truncated"), bTruncated);
    ResultPayload->SetArrayField(TEXT("assets"), AssetValues);

    return {
        true,
        TEXT("Asset listing generated."),
        UnrealAgentPrivate::SerializePayload(ResultPayload),
        TEXT("OK")
    };
}

