#include "Agent/Actions/CreateBlueprintAction.h"

#include "Agent/AgentJsonUtils.h"
#include "AssetToolsModule.h"
#include "Dom/JsonObject.h"
#include "Engine/Blueprint.h"
#include "Factories/BlueprintFactory.h"
#include "Misc/PackageName.h"
#include "Modules/ModuleManager.h"
#include "ObjectTools.h"
#include "ScopedTransaction.h"

FString FCreateBlueprintAction::GetName() const
{
    return TEXT("create_blueprint");
}

FString FCreateBlueprintAction::GetDescription() const
{
    return TEXT("Creates a Blueprint Actor asset under /Game.");
}

FAgentActionResult FCreateBlueprintAction::Execute(const FAgentActionRequest& Request)
{
    FString AssetName = TEXT("BP_NewActor");
    FString PackagePath = TEXT("/Game");
    FString ParentClassPath = TEXT("/Script/Engine.Actor");

    if (!Request.PayloadJson.IsEmpty())
    {
        TSharedPtr<FJsonObject> Payload;
        FString ParseError;
        if (!UnrealAgentPrivate::ParseJsonObject(Request.PayloadJson, Payload, ParseError))
        {
            return {false, ParseError, TEXT("")};
        }

        Payload->TryGetStringField(TEXT("asset_name"), AssetName);
        Payload->TryGetStringField(TEXT("package_path"), PackagePath);
        Payload->TryGetStringField(TEXT("parent_class"), ParentClassPath);
    }

    AssetName = ObjectTools::SanitizeObjectName(AssetName);
    if (AssetName.IsEmpty())
    {
        return {false, TEXT("asset_name is empty after sanitization."), TEXT("")};
    }

    if (!PackagePath.StartsWith(TEXT("/Game")))
    {
        return {false, TEXT("package_path must start with /Game for safety."), TEXT("")};
    }

    if (!FPackageName::IsValidLongPackageName(PackagePath))
    {
        return {false, TEXT("package_path is not a valid Unreal package path."), TEXT("")};
    }

    UClass* ParentClass = UObject::StaticClass();
    if (!ParentClassPath.IsEmpty())
    {
        UClass* LoadedClass = FindObject<UClass>(nullptr, *ParentClassPath);
        if (LoadedClass == nullptr)
        {
            LoadedClass = LoadObject<UClass>(nullptr, *ParentClassPath);
        }

        if (LoadedClass == nullptr)
        {
            return {false, FString::Printf(TEXT("Failed to resolve parent class: %s"), *ParentClassPath), TEXT("")};
        }

        ParentClass = LoadedClass;
    }

    if (Request.bDryRun)
    {
        const TSharedRef<FJsonObject> DryRunPayload = MakeShared<FJsonObject>();
        DryRunPayload->SetStringField(TEXT("asset_name"), AssetName);
        DryRunPayload->SetStringField(TEXT("package_path"), PackagePath);
        DryRunPayload->SetStringField(TEXT("parent_class"), ParentClass->GetPathName());
        return {
            true,
            TEXT("Dry run successful. No asset created."),
            UnrealAgentPrivate::SerializePayload(DryRunPayload)
        };
    }

    const FScopedTransaction Transaction(NSLOCTEXT("UnrealAgent", "CreateBlueprintAction", "Agent Create Blueprint"));

    UBlueprintFactory* BlueprintFactory = NewObject<UBlueprintFactory>();
    BlueprintFactory->ParentClass = ParentClass;

    FAssetToolsModule& AssetToolsModule = FModuleManager::LoadModuleChecked<FAssetToolsModule>("AssetTools");
    UObject* CreatedAsset = AssetToolsModule.Get().CreateAsset(
        AssetName,
        PackagePath,
        UBlueprint::StaticClass(),
        BlueprintFactory
    );

    if (CreatedAsset == nullptr)
    {
        return {
            false,
            TEXT("Asset creation failed. Check package path and whether the asset already exists."),
            TEXT("")
        };
    }

    const TSharedRef<FJsonObject> SuccessPayload = MakeShared<FJsonObject>();
    SuccessPayload->SetStringField(TEXT("asset_name"), AssetName);
    SuccessPayload->SetStringField(TEXT("package_path"), PackagePath);
    SuccessPayload->SetStringField(TEXT("asset_path"), CreatedAsset->GetPathName());
    SuccessPayload->SetStringField(TEXT("parent_class"), ParentClass->GetPathName());

    return {
        true,
        TEXT("Blueprint created successfully."),
        UnrealAgentPrivate::SerializePayload(SuccessPayload)
    };
}
