#include "Agent/Actions/CompileBlueprintAction.h"

#include "Agent/AgentJsonUtils.h"
#include "Dom/JsonObject.h"
#include "Engine/Blueprint.h"
#include "Kismet2/KismetEditorUtilities.h"
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
        return BlueprintPathOrObjectPath;
    }

    const FString AssetName = FPackageName::GetLongPackageAssetName(BlueprintPathOrObjectPath);
    if (AssetName.IsEmpty())
    {
        return BlueprintPathOrObjectPath;
    }

    return FString::Printf(TEXT("%s.%s"), *BlueprintPathOrObjectPath, *AssetName);
}
} // namespace UnrealAgentPrivate

FString FCompileBlueprintAction::GetName() const
{
    return TEXT("compile_blueprint");
}

FString FCompileBlueprintAction::GetDescription() const
{
    return TEXT("Compiles a Blueprint asset and returns compile status.");
}

FAgentActionResult FCompileBlueprintAction::Execute(const FAgentActionRequest& Request)
{
    FString BlueprintPathOrObjectPath;
    if (!Request.PayloadJson.IsEmpty())
    {
        TSharedPtr<FJsonObject> Payload;
        FString ParseError;
        if (!UnrealAgentPrivate::ParseJsonObject(Request.PayloadJson, Payload, ParseError))
        {
            return {false, ParseError, TEXT("")};
        }
        Payload->TryGetStringField(TEXT("blueprint_path"), BlueprintPathOrObjectPath);
    }

    if (BlueprintPathOrObjectPath.IsEmpty())
    {
        return {
            false,
            TEXT("Missing required payload field: blueprint_path"),
            TEXT("")
        };
    }

    const FString ObjectPath = UnrealAgentPrivate::NormalizeBlueprintObjectPath(BlueprintPathOrObjectPath);
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
            TEXT("")
        };
    }

    if (!Request.bDryRun)
    {
        FKismetEditorUtilities::CompileBlueprint(Blueprint);
    }

    FString CompileStatus = TEXT("Unknown");
    if (const UEnum* StatusEnum = StaticEnum<EBlueprintStatus>())
    {
        CompileStatus = StatusEnum->GetNameStringByValue(static_cast<int64>(Blueprint->Status));
    }

    const bool bCompileSucceeded = Blueprint->Status != BS_Error;

    const TSharedRef<FJsonObject> Payload = MakeShared<FJsonObject>();
    Payload->SetStringField(TEXT("blueprint"), Blueprint->GetPathName());
    Payload->SetStringField(TEXT("compile_status"), CompileStatus);
    Payload->SetBoolField(TEXT("dry_run"), Request.bDryRun);

    return {
        bCompileSucceeded,
        Request.bDryRun ? TEXT("Dry run successful. Blueprint was not compiled.") :
                          (bCompileSucceeded ? TEXT("Blueprint compiled.") : TEXT("Blueprint compile reported errors.")),
        UnrealAgentPrivate::SerializePayload(Payload)
    };
}
