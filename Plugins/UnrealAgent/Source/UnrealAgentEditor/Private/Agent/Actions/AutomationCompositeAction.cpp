#include "Agent/Actions/AutomationCompositeAction.h"

#include "Agent/AgentActionRegistry.h"
#include "Agent/AgentJsonUtils.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Editor.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/Level.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Actor.h"
#include "HAL/FileManager.h"
#include "Math/UnrealMathUtility.h"
#include "Misc/DateTime.h"
#include "Misc/Paths.h"
#include "ScopedTransaction.h"
#include "Serialization/JsonTypes.h"
#include "UnrealClient.h"

namespace UnrealAgentPrivate
{
static bool ParsePayloadObject(const FString& JsonString, TSharedPtr<FJsonObject>& OutPayload, FString& OutError)
{
    OutPayload = MakeShared<FJsonObject>();
    OutError.Reset();
    if (JsonString.IsEmpty())
    {
        return true;
    }
    if (!ParseJsonObject(JsonString, OutPayload, OutError))
    {
        return false;
    }
    return true;
}

static FAgentActionResult ExecuteNamedAction(const FString& ActionName, const TSharedRef<FJsonObject>& Payload, const bool bDryRun)
{
    FAgentActionRequest Nested;
    Nested.ActionName = ActionName;
    Nested.PayloadJson = SerializePayload(Payload);
    Nested.bDryRun = bDryRun;
    return FAgentActionRegistry::Get().Execute(Nested);
}

static FVector ReadVectorOrDefault(const TSharedPtr<FJsonObject>& Payload, const FString& Field, const FVector& DefaultValue)
{
    const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
    if (!Payload.IsValid() || !Payload->TryGetArrayField(Field, Arr) || Arr == nullptr || Arr->Num() != 3)
    {
        return DefaultValue;
    }

    double X = 0.0;
    double Y = 0.0;
    double Z = 0.0;
    if (!(*Arr)[0].IsValid() || !(*Arr)[1].IsValid() || !(*Arr)[2].IsValid())
    {
        return DefaultValue;
    }
    if (!(*Arr)[0]->TryGetNumber(X) || !(*Arr)[1]->TryGetNumber(Y) || !(*Arr)[2]->TryGetNumber(Z))
    {
        return DefaultValue;
    }
    return FVector(static_cast<float>(X), static_cast<float>(Y), static_cast<float>(Z));
}

static TArray<FString> ReadStringArray(const TSharedPtr<FJsonObject>& Payload, const FString& Field)
{
    TArray<FString> Out;
    const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
    if (!Payload.IsValid() || !Payload->TryGetArrayField(Field, Arr) || Arr == nullptr)
    {
        return Out;
    }

    for (const TSharedPtr<FJsonValue>& V : *Arr)
    {
        FString S;
        if (V.IsValid() && V->TryGetString(S) && !S.IsEmpty())
        {
            Out.Add(S);
        }
    }
    return Out;
}

static int32 ReadIntOrDefault(const TSharedPtr<FJsonObject>& Payload, const FString& Field, const int32 DefaultValue)
{
    if (!Payload.IsValid())
    {
        return DefaultValue;
    }
    double Number = static_cast<double>(DefaultValue);
    if (!Payload->TryGetNumberField(Field, Number))
    {
        return DefaultValue;
    }
    return static_cast<int32>(Number);
}

static float ReadFloatOrDefault(const TSharedPtr<FJsonObject>& Payload, const FString& Field, const float DefaultValue)
{
    if (!Payload.IsValid())
    {
        return DefaultValue;
    }
    double Number = static_cast<double>(DefaultValue);
    if (!Payload->TryGetNumberField(Field, Number))
    {
        return DefaultValue;
    }
    return static_cast<float>(Number);
}

static FAgentActionResult BuildPassThroughResult(const FString& Message, const TSharedRef<FJsonObject>& Payload)
{
    return {true, Message, SerializePayload(Payload), TEXT("OK")};
}

static FAgentActionResult BuildUnsupported(const FString& Message)
{
    return {false, Message, TEXT(""), TEXT("UNSUPPORTED")};
}

static FAgentActionResult HandleCreateWidgetBlueprint(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString AssetName = TEXT("WBP_AgentWidget");
    FString PackagePath = TEXT("/Game/AgentGenerated/UI");
    FString ParentClass = TEXT("/Script/UMG.UserWidget");
    Payload->TryGetStringField(TEXT("asset_name"), AssetName);
    Payload->TryGetStringField(TEXT("package_path"), PackagePath);
    Payload->TryGetStringField(TEXT("parent_class"), ParentClass);

    TSharedRef<FJsonObject> NestedPayload = MakeShared<FJsonObject>();
    NestedPayload->SetStringField(TEXT("asset_name"), AssetName);
    NestedPayload->SetStringField(TEXT("package_path"), PackagePath);
    NestedPayload->SetStringField(TEXT("parent_class"), ParentClass);
    return ExecuteNamedAction(TEXT("create_blueprint"), NestedPayload, Request.bDryRun);
}

static FAgentActionResult HandleModifyWidgetTree(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("implemented"), false);
    Result->SetStringField(TEXT("note"), TEXT("Widget tree mutation scaffolding is registered; use recipe-level widget generation in this release."));
    if (Payload.IsValid())
    {
        Result->SetObjectField(TEXT("requested"), Payload.ToSharedRef());
    }
    return BuildPassThroughResult(
        Request.bDryRun ? TEXT("Dry run: modify_widget_tree accepted (scaffold).") : TEXT("modify_widget_tree scaffold accepted."),
        Result);
}

static FAgentActionResult HandleBindWidgetEvents(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("implemented"), false);
    Result->SetStringField(TEXT("note"), TEXT("Widget event binding scaffold registered for deterministic recipes."));
    if (Payload.IsValid())
    {
        Result->SetObjectField(TEXT("requested"), Payload.ToSharedRef());
    }
    return BuildPassThroughResult(
        Request.bDryRun ? TEXT("Dry run: bind_widget_events accepted (scaffold).") : TEXT("bind_widget_events scaffold accepted."),
        Result);
}

static FAgentActionResult HandleCreateObjectiveActor(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString ActorLabel = TEXT("Objective_Item");
    FString FolderPath = TEXT("AgentGenerated/Objectives");
    FString ClassPath = TEXT("/Script/Engine.StaticMeshActor");
    FString StaticMeshPath;
    Payload->TryGetStringField(TEXT("actor_label"), ActorLabel);
    Payload->TryGetStringField(TEXT("folder_path"), FolderPath);
    Payload->TryGetStringField(TEXT("class_path"), ClassPath);
    Payload->TryGetStringField(TEXT("static_mesh_path"), StaticMeshPath);

    const FVector Location = ReadVectorOrDefault(Payload, TEXT("location"), FVector::ZeroVector);
    const FVector Rotation = ReadVectorOrDefault(Payload, TEXT("rotation"), FVector::ZeroVector);
    const FVector Scale = ReadVectorOrDefault(Payload, TEXT("scale"), FVector(1.0f, 1.0f, 1.0f));

    TArray<FString> Tags = ReadStringArray(Payload, TEXT("tags"));
    if (!Tags.Contains(TEXT("ObjectiveItem")))
    {
        Tags.Add(TEXT("ObjectiveItem"));
    }

    TSharedRef<FJsonObject> Spawn = MakeShared<FJsonObject>();
    Spawn->SetStringField(TEXT("class_path"), ClassPath);
    Spawn->SetStringField(TEXT("actor_label"), ActorLabel);
    Spawn->SetStringField(TEXT("folder_path"), FolderPath);
    Spawn->SetStringField(TEXT("static_mesh_path"), StaticMeshPath);
    Spawn->SetArrayField(
        TEXT("location"),
        {MakeShared<FJsonValueNumber>(Location.X), MakeShared<FJsonValueNumber>(Location.Y), MakeShared<FJsonValueNumber>(Location.Z)});
    Spawn->SetArrayField(
        TEXT("rotation"),
        {MakeShared<FJsonValueNumber>(Rotation.X), MakeShared<FJsonValueNumber>(Rotation.Y), MakeShared<FJsonValueNumber>(Rotation.Z)});
    Spawn->SetArrayField(
        TEXT("scale"),
        {MakeShared<FJsonValueNumber>(Scale.X), MakeShared<FJsonValueNumber>(Scale.Y), MakeShared<FJsonValueNumber>(Scale.Z)});

    TArray<TSharedPtr<FJsonValue>> TagValues;
    for (const FString& Tag : Tags)
    {
        TagValues.Add(MakeShared<FJsonValueString>(Tag));
    }
    Spawn->SetArrayField(TEXT("tags"), TagValues);

    return ExecuteNamedAction(TEXT("spawn_actor"), Spawn, Request.bDryRun);
}

static FAgentActionResult HandleVariableSystem(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload, const FString& VariableName, const FString& VariableType, const FString& DefaultValue, const FString& Category)
{
    FString BlueprintPath;
    Payload->TryGetStringField(TEXT("blueprint_path"), BlueprintPath);
    if (BlueprintPath.IsEmpty())
    {
        return {false, TEXT("Missing blueprint_path."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    TSharedRef<FJsonObject> AddVar = MakeShared<FJsonObject>();
    AddVar->SetStringField(TEXT("blueprint_path"), BlueprintPath);
    AddVar->SetStringField(TEXT("operation"), TEXT("add_variable"));
    AddVar->SetStringField(TEXT("variable_name"), VariableName);
    AddVar->SetStringField(TEXT("variable_type"), VariableType);
    AddVar->SetStringField(TEXT("default_value"), DefaultValue);
    AddVar->SetStringField(TEXT("category"), Category);
    AddVar->SetBoolField(TEXT("compile_after"), false);

    return ExecuteNamedAction(TEXT("modify_blueprint_graph"), AddVar, Request.bDryRun);
}

static FAgentActionResult HandleBatchSpawnActors(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    const TArray<TSharedPtr<FJsonValue>>* ActorsArray = nullptr;
    if (!Payload->TryGetArrayField(TEXT("actors"), ActorsArray) || ActorsArray == nullptr || ActorsArray->Num() == 0)
    {
        return {false, TEXT("batch_spawn_actors requires payload.actors[]"), TEXT(""), TEXT("MISSING_FIELD")};
    }

    int32 Succeeded = 0;
    int32 Failed = 0;
    TArray<TSharedPtr<FJsonValue>> Results;
    for (int32 i = 0; i < ActorsArray->Num(); ++i)
    {
        const TSharedPtr<FJsonObject> ActorObj = (*ActorsArray)[i].IsValid() ? (*ActorsArray)[i]->AsObject() : nullptr;
        if (!ActorObj.IsValid())
        {
            ++Failed;
            continue;
        }

        const FAgentActionResult SpawnResult = ExecuteNamedAction(TEXT("spawn_actor"), ActorObj.ToSharedRef(), Request.bDryRun);
        TSharedRef<FJsonObject> Step = MakeShared<FJsonObject>();
        Step->SetNumberField(TEXT("index"), i);
        Step->SetBoolField(TEXT("success"), SpawnResult.bSuccess);
        Step->SetStringField(TEXT("message"), SpawnResult.Message);
        Step->SetStringField(TEXT("error_code"), NormalizeErrorCode(SpawnResult));
        Results.Add(MakeShared<FJsonValueObject>(Step));

        if (SpawnResult.bSuccess)
        {
            ++Succeeded;
        }
        else
        {
            ++Failed;
        }
    }

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetNumberField(TEXT("requested"), ActorsArray->Num());
    Out->SetNumberField(TEXT("succeeded"), Succeeded);
    Out->SetNumberField(TEXT("failed"), Failed);
    Out->SetArrayField(TEXT("results"), Results);
    return {
        Failed == 0,
        Failed == 0 ? TEXT("batch_spawn_actors completed.") : TEXT("batch_spawn_actors completed with failures."),
        SerializePayload(Out),
        Failed == 0 ? TEXT("OK") : TEXT("PARTIAL_FAILURE")};
}

static FAgentActionResult HandleLayoutAlongSpline(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    const FVector Start = ReadVectorOrDefault(Payload, TEXT("start"), FVector::ZeroVector);
    const FVector End = ReadVectorOrDefault(Payload, TEXT("end"), FVector(1000.0f, 0.0f, 0.0f));
    int32 Count = ReadIntOrDefault(Payload, TEXT("count"), 10);
    Count = FMath::Clamp(Count, 1, 200);

    FString ClassPath = TEXT("/Script/Engine.StaticMeshActor");
    FString StaticMeshPath;
    FString FolderPath = TEXT("AgentGenerated/JumpLines");
    Payload->TryGetStringField(TEXT("class_path"), ClassPath);
    Payload->TryGetStringField(TEXT("static_mesh_path"), StaticMeshPath);
    Payload->TryGetStringField(TEXT("folder_path"), FolderPath);

    TArray<TSharedPtr<FJsonValue>> Actors;
    for (int32 i = 0; i < Count; ++i)
    {
        const float Alpha = Count == 1 ? 0.0f : static_cast<float>(i) / static_cast<float>(Count - 1);
        const FVector P = FMath::Lerp(Start, End, Alpha);
        TSharedRef<FJsonObject> Spawn = MakeShared<FJsonObject>();
        Spawn->SetStringField(TEXT("class_path"), ClassPath);
        Spawn->SetStringField(TEXT("static_mesh_path"), StaticMeshPath);
        Spawn->SetStringField(TEXT("folder_path"), FolderPath);
        Spawn->SetStringField(TEXT("actor_label"), FString::Printf(TEXT("JumpLine_%03d"), i + 1));
        Spawn->SetArrayField(
            TEXT("location"),
            {MakeShared<FJsonValueNumber>(P.X), MakeShared<FJsonValueNumber>(P.Y), MakeShared<FJsonValueNumber>(P.Z)});
        Spawn->SetArrayField(
            TEXT("tags"),
            {MakeShared<FJsonValueString>(TEXT("JumpLine"))});
        Actors.Add(MakeShared<FJsonValueObject>(Spawn));
    }

    TSharedRef<FJsonObject> Batch = MakeShared<FJsonObject>();
    Batch->SetArrayField(TEXT("actors"), Actors);
    return HandleBatchSpawnActors(Request, Batch);
}

static FAgentActionResult HandleCreateLevelChunk(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    int32 Rows = ReadIntOrDefault(Payload, TEXT("rows"), 6);
    int32 Cols = ReadIntOrDefault(Payload, TEXT("cols"), 6);
    float Spacing = ReadFloatOrDefault(Payload, TEXT("spacing"), 400.0f);
    Rows = FMath::Clamp(Rows, 1, 50);
    Cols = FMath::Clamp(Cols, 1, 50);

    const FVector Origin = ReadVectorOrDefault(Payload, TEXT("origin"), FVector::ZeroVector);

    FString ClassPath = TEXT("/Script/Engine.StaticMeshActor");
    FString StaticMeshPath;
    FString FolderPath = TEXT("AgentGenerated/CityChunks");
    Payload->TryGetStringField(TEXT("class_path"), ClassPath);
    Payload->TryGetStringField(TEXT("static_mesh_path"), StaticMeshPath);
    Payload->TryGetStringField(TEXT("folder_path"), FolderPath);

    TArray<TSharedPtr<FJsonValue>> Actors;
    Actors.Reserve(Rows * Cols);
    for (int32 r = 0; r < Rows; ++r)
    {
        for (int32 c = 0; c < Cols; ++c)
        {
            const FVector P(Origin.X + static_cast<float>(c) * Spacing, Origin.Y + static_cast<float>(r) * Spacing, Origin.Z);
            TSharedRef<FJsonObject> Spawn = MakeShared<FJsonObject>();
            Spawn->SetStringField(TEXT("class_path"), ClassPath);
            Spawn->SetStringField(TEXT("static_mesh_path"), StaticMeshPath);
            Spawn->SetStringField(TEXT("folder_path"), FolderPath);
            Spawn->SetStringField(TEXT("actor_label"), FString::Printf(TEXT("CityChunk_%02d_%02d"), r, c));
            Spawn->SetArrayField(
                TEXT("location"),
                {MakeShared<FJsonValueNumber>(P.X), MakeShared<FJsonValueNumber>(P.Y), MakeShared<FJsonValueNumber>(P.Z)});
            Spawn->SetArrayField(TEXT("tags"), {MakeShared<FJsonValueString>(TEXT("CityChunk"))});
            Actors.Add(MakeShared<FJsonValueObject>(Spawn));
        }
    }

    TSharedRef<FJsonObject> Batch = MakeShared<FJsonObject>();
    Batch->SetArrayField(TEXT("actors"), Actors);
    return HandleBatchSpawnActors(Request, Batch);
}

static FAgentActionResult HandleTagAndGroupActors(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    UWorld* EditorWorld = (GEditor != nullptr) ? GEditor->GetEditorWorldContext().World() : nullptr;
    if (EditorWorld == nullptr)
    {
        return {false, TEXT("No editor world found."), TEXT(""), TEXT("WORLD_NOT_FOUND")};
    }

    FString LabelContains;
    FString FolderPath;
    Payload->TryGetStringField(TEXT("label_contains"), LabelContains);
    Payload->TryGetStringField(TEXT("folder_path"), FolderPath);
    const TArray<FString> Tags = ReadStringArray(Payload, TEXT("tags"));

    int32 Matched = 0;
    int32 Updated = 0;
    for (TActorIterator<AActor> It(EditorWorld); It; ++It)
    {
        AActor* Actor = *It;
        if (Actor == nullptr)
        {
            continue;
        }
        const FString Label = Actor->GetActorLabel();
        if (!LabelContains.IsEmpty() && !Label.Contains(LabelContains))
        {
            continue;
        }
        ++Matched;
        if (!Request.bDryRun)
        {
            if (!FolderPath.IsEmpty())
            {
                Actor->SetFolderPath(*FolderPath);
            }
            for (const FString& Tag : Tags)
            {
                const FName TagName(*Tag);
                if (!Actor->Tags.Contains(TagName))
                {
                    Actor->Tags.Add(TagName);
                }
            }
            ++Updated;
        }
    }

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetNumberField(TEXT("matched"), Matched);
    Out->SetNumberField(TEXT("updated"), Request.bDryRun ? 0 : Updated);
    Out->SetBoolField(TEXT("dry_run"), Request.bDryRun);
    return BuildPassThroughResult(TEXT("tag_and_group_actors completed."), Out);
}

static bool ActorHasAnyTag(const AActor* Actor, const TArray<FString>& QueryTags)
{
    if (Actor == nullptr || QueryTags.Num() == 0)
    {
        return false;
    }
    for (const FString& Tag : QueryTags)
    {
        if (Actor->Tags.Contains(FName(*Tag)))
        {
            return true;
        }
    }
    return false;
}

static FAgentActionResult HandleDeleteActorsByFilter(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    UWorld* EditorWorld = (GEditor != nullptr) ? GEditor->GetEditorWorldContext().World() : nullptr;
    if (EditorWorld == nullptr)
    {
        return {false, TEXT("No editor world found."), TEXT(""), TEXT("WORLD_NOT_FOUND")};
    }

    const TArray<FString> Tags = ReadStringArray(Payload, TEXT("tags"));
    FString LabelContains;
    FString FolderContains;
    bool bOnlyGenerated = false;
    Payload->TryGetStringField(TEXT("label_contains"), LabelContains);
    Payload->TryGetStringField(TEXT("folder_contains"), FolderContains);
    Payload->TryGetBoolField(TEXT("only_generated"), bOnlyGenerated);

    TArray<AActor*> ToDelete;
    for (TActorIterator<AActor> It(EditorWorld); It; ++It)
    {
        AActor* Actor = *It;
        if (Actor == nullptr)
        {
            continue;
        }
        const FString Label = Actor->GetActorLabel();
        const FString Folder = Actor->GetFolderPath().ToString();

        bool bMatches = false;
        if (Tags.Num() > 0 && ActorHasAnyTag(Actor, Tags))
        {
            bMatches = true;
        }
        if (!LabelContains.IsEmpty() && Label.Contains(LabelContains))
        {
            bMatches = true;
        }
        if (!FolderContains.IsEmpty() && Folder.Contains(FolderContains))
        {
            bMatches = true;
        }

        if (bOnlyGenerated)
        {
            const bool bGeneratedByName = Label.StartsWith(TEXT("Objective_")) || Label.StartsWith(TEXT("JumpLine_")) || Label.StartsWith(TEXT("CityChunk_"));
            const bool bGeneratedByFolder = Folder.Contains(TEXT("AgentGenerated"));
            if (!bGeneratedByName && !bGeneratedByFolder)
            {
                bMatches = false;
            }
        }

        if (bMatches)
        {
            ToDelete.Add(Actor);
        }
    }

    int32 Deleted = 0;
    if (!Request.bDryRun && ToDelete.Num() > 0)
    {
        const FScopedTransaction Tx(NSLOCTEXT("UnrealAgent", "DeleteActorsByFilter", "Agent Delete Actors By Filter"));
        for (AActor* Actor : ToDelete)
        {
            if (IsValid(Actor))
            {
                EditorWorld->DestroyActor(Actor, true, true);
                ++Deleted;
            }
        }
        EditorWorld->MarkPackageDirty();
    }

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetBoolField(TEXT("dry_run"), Request.bDryRun);
    Out->SetNumberField(TEXT("matched"), ToDelete.Num());
    Out->SetNumberField(TEXT("deleted"), Request.bDryRun ? 0 : Deleted);
    return {
        true,
        Request.bDryRun ? TEXT("Dry run: delete_actors_by_filter matched actors.") : TEXT("delete_actors_by_filter completed."),
        SerializePayload(Out),
        TEXT("OK")};
}

static FAgentActionResult HandleClearMapLayout(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    TSharedRef<FJsonObject> Query = MakeShared<FJsonObject>();
    Query->SetBoolField(TEXT("only_generated"), true);
    Query->SetStringField(TEXT("folder_contains"), TEXT("AgentGenerated"));
    Query->SetArrayField(
        TEXT("tags"),
        {
            MakeShared<FJsonValueString>(TEXT("ObjectiveItem")),
            MakeShared<FJsonValueString>(TEXT("CityChunk")),
            MakeShared<FJsonValueString>(TEXT("JumpLine"))
        });
    if (Payload.IsValid())
    {
        if (Payload->HasField(TEXT("tags")))
        {
            const TArray<FString> OverrideTags = ReadStringArray(Payload, TEXT("tags"));
            if (OverrideTags.Num() > 0)
            {
                TArray<TSharedPtr<FJsonValue>> TagValues;
                for (const FString& Tag : OverrideTags)
                {
                    TagValues.Add(MakeShared<FJsonValueString>(Tag));
                }
                Query->SetArrayField(TEXT("tags"), TagValues);
            }
        }
        bool bOnlyGenerated = true;
        Payload->TryGetBoolField(TEXT("only_generated"), bOnlyGenerated);
        Query->SetBoolField(TEXT("only_generated"), bOnlyGenerated);
    }

    return HandleDeleteActorsByFilter(Request, Query);
}

static FAgentActionResult HandleCreateDataAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString AssetName = TEXT("DA_AgentData");
    FString PackagePath = TEXT("/Game/AgentGenerated/Data");
    FString ParentClass = TEXT("/Script/Engine.PrimaryDataAsset");
    Payload->TryGetStringField(TEXT("asset_name"), AssetName);
    Payload->TryGetStringField(TEXT("package_path"), PackagePath);
    Payload->TryGetStringField(TEXT("parent_class"), ParentClass);

    TSharedRef<FJsonObject> Nested = MakeShared<FJsonObject>();
    Nested->SetStringField(TEXT("asset_name"), AssetName);
    Nested->SetStringField(TEXT("package_path"), PackagePath);
    Nested->SetStringField(TEXT("parent_class"), ParentClass);
    return ExecuteNamedAction(TEXT("create_blueprint"), Nested, Request.bDryRun);
}

static FAgentActionResult HandleCreateDataTable(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetBoolField(TEXT("implemented"), false);
    Out->SetStringField(TEXT("note"), TEXT("DataTable creation scaffold is available; use create_data_asset as primary deterministic path in this release."));
    Out->SetBoolField(TEXT("dry_run"), Request.bDryRun);
    if (Payload.IsValid())
    {
        Out->SetObjectField(TEXT("requested"), Payload.ToSharedRef());
    }
    return BuildPassThroughResult(TEXT("create_data_table scaffold accepted."), Out);
}

static FAgentActionResult HandleEditDataTableRow(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetBoolField(TEXT("implemented"), false);
    Out->SetBoolField(TEXT("dry_run"), Request.bDryRun);
    if (Payload.IsValid())
    {
        Out->SetObjectField(TEXT("requested"), Payload.ToSharedRef());
    }
    return BuildPassThroughResult(TEXT("edit_data_table_row scaffold accepted."), Out);
}

static FAgentActionResult HandleValidateDataSchema(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    const TArray<TSharedPtr<FJsonValue>>* RequiredArray = nullptr;
    const TSharedPtr<FJsonObject>* RowObject = nullptr;
    const bool bHasRequired = Payload->TryGetArrayField(TEXT("required_fields"), RequiredArray) && RequiredArray != nullptr;
    const bool bHasRow = Payload->TryGetObjectField(TEXT("row"), RowObject) && RowObject != nullptr && RowObject->IsValid();

    TArray<FString> Missing;
    if (bHasRequired && bHasRow)
    {
        for (const TSharedPtr<FJsonValue>& V : *RequiredArray)
        {
            FString Key;
            if (!V.IsValid() || !V->TryGetString(Key) || Key.IsEmpty())
            {
                continue;
            }
            if (!(*RowObject)->HasField(Key))
            {
                Missing.Add(Key);
            }
        }
    }

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetBoolField(TEXT("dry_run"), Request.bDryRun);
    Out->SetBoolField(TEXT("valid"), Missing.Num() == 0);
    TArray<TSharedPtr<FJsonValue>> MissingValues;
    for (const FString& M : Missing)
    {
        MissingValues.Add(MakeShared<FJsonValueString>(M));
    }
    Out->SetArrayField(TEXT("missing_fields"), MissingValues);

    return {
        Missing.Num() == 0,
        Missing.Num() == 0 ? TEXT("Data schema validation passed.") : TEXT("Data schema validation failed."),
        SerializePayload(Out),
        Missing.Num() == 0 ? TEXT("OK") : TEXT("SCHEMA_INVALID")};
}

static FAgentActionResult HandleInspectCompileErrors(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString BlueprintPath;
    Payload->TryGetStringField(TEXT("blueprint_path"), BlueprintPath);
    if (BlueprintPath.IsEmpty())
    {
        return {false, TEXT("Missing blueprint_path."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    TSharedRef<FJsonObject> Compile = MakeShared<FJsonObject>();
    Compile->SetStringField(TEXT("blueprint_path"), BlueprintPath);
    const FAgentActionResult CompileResult = ExecuteNamedAction(TEXT("compile_blueprint"), Compile, Request.bDryRun);

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetStringField(TEXT("blueprint_path"), BlueprintPath);
    Out->SetBoolField(TEXT("compile_success"), CompileResult.bSuccess);
    Out->SetStringField(TEXT("compile_message"), CompileResult.Message);
    Out->SetStringField(TEXT("compile_error_code"), NormalizeErrorCode(CompileResult));
    return {
        CompileResult.bSuccess,
        CompileResult.bSuccess ? TEXT("Compile inspection passed.") : TEXT("Compile inspection found errors."),
        SerializePayload(Out),
        CompileResult.bSuccess ? TEXT("OK") : TEXT("COMPILE_FAILED")};
}

static FAgentActionResult HandleAssertWorldState(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    UWorld* EditorWorld = (GEditor != nullptr) ? GEditor->GetEditorWorldContext().World() : nullptr;
    if (EditorWorld == nullptr)
    {
        return {false, TEXT("No editor world found."), TEXT(""), TEXT("WORLD_NOT_FOUND")};
    }

    FString LabelContains;
    FString RequiredClassPath;
    int32 MinCount = 1;
    Payload->TryGetStringField(TEXT("label_contains"), LabelContains);
    Payload->TryGetStringField(TEXT("class_path"), RequiredClassPath);
    MinCount = ReadIntOrDefault(Payload, TEXT("min_count"), MinCount);
    MinCount = FMath::Max(0, MinCount);
    const TArray<FString> RequiredTags = ReadStringArray(Payload, TEXT("required_tags"));

    int32 Count = 0;
    int32 TagHits = 0;
    for (TActorIterator<AActor> It(EditorWorld); It; ++It)
    {
        AActor* Actor = *It;
        if (Actor == nullptr)
        {
            continue;
        }
        if (!LabelContains.IsEmpty() && !Actor->GetActorLabel().Contains(LabelContains))
        {
            continue;
        }
        if (!RequiredClassPath.IsEmpty() && Actor->GetClass()->GetPathName() != RequiredClassPath)
        {
            continue;
        }

        ++Count;
        bool bAllTags = true;
        for (const FString& Tag : RequiredTags)
        {
            if (!Actor->Tags.Contains(FName(*Tag)))
            {
                bAllTags = false;
                break;
            }
        }
        if (bAllTags)
        {
            ++TagHits;
        }
    }

    const bool bTagSatisfied = RequiredTags.Num() == 0 ? true : TagHits >= MinCount;
    const bool bCountSatisfied = Count >= MinCount;
    const bool bSuccess = bCountSatisfied && bTagSatisfied;

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetNumberField(TEXT("matched_count"), Count);
    Out->SetNumberField(TEXT("tag_satisfied_count"), TagHits);
    Out->SetNumberField(TEXT("min_count"), MinCount);
    Out->SetBoolField(TEXT("success"), bSuccess);
    return {bSuccess, bSuccess ? TEXT("World assertions passed.") : TEXT("World assertions failed."), SerializePayload(Out), bSuccess ? TEXT("OK") : TEXT("ASSERT_FAILED")};
}

static FAgentActionResult HandleRunPieScenario(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    const TArray<TSharedPtr<FJsonValue>>* Assertions = nullptr;
    if (!Payload->TryGetArrayField(TEXT("assertions"), Assertions) || Assertions == nullptr)
    {
        return {false, TEXT("run_pie_scenario requires assertions[]."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    int32 Passed = 0;
    int32 Failed = 0;
    TArray<TSharedPtr<FJsonValue>> Results;
    for (int32 i = 0; i < Assertions->Num(); ++i)
    {
        TSharedPtr<FJsonObject> AssertionObj = (*Assertions)[i].IsValid() ? (*Assertions)[i]->AsObject() : nullptr;
        if (!AssertionObj.IsValid())
        {
            ++Failed;
            continue;
        }

        FAgentActionRequest AssertReq;
        AssertReq.ActionName = TEXT("assert_world_state");
        AssertReq.PayloadJson = SerializePayload(AssertionObj.ToSharedRef());
        AssertReq.bDryRun = Request.bDryRun;
        const FAgentActionResult AssertResult = FAgentActionRegistry::Get().Execute(AssertReq);

        TSharedRef<FJsonObject> Step = MakeShared<FJsonObject>();
        Step->SetNumberField(TEXT("index"), i);
        Step->SetBoolField(TEXT("success"), AssertResult.bSuccess);
        Step->SetStringField(TEXT("message"), AssertResult.Message);
        Step->SetStringField(TEXT("error_code"), NormalizeErrorCode(AssertResult));
        Results.Add(MakeShared<FJsonValueObject>(Step));

        if (AssertResult.bSuccess)
        {
            ++Passed;
        }
        else
        {
            ++Failed;
        }
    }

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetNumberField(TEXT("assertions"), Assertions->Num());
    Out->SetNumberField(TEXT("passed"), Passed);
    Out->SetNumberField(TEXT("failed"), Failed);
    Out->SetArrayField(TEXT("results"), Results);
    const bool bSuccess = Failed == 0;
    return {bSuccess, bSuccess ? TEXT("Scenario assertions passed.") : TEXT("Scenario assertions failed."), SerializePayload(Out), bSuccess ? TEXT("OK") : TEXT("SCENARIO_FAILED")};
}

static FAgentActionResult HandleCaptureScreenshot(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString FileName;
    Payload->TryGetStringField(TEXT("file_name"), FileName);
    if (FileName.IsEmpty())
    {
        FileName = FString::Printf(TEXT("agent_capture_%s.png"), *FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S")));
    }
    const FString Directory = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("UnrealAgent"), TEXT("Screenshots"));
    IFileManager::Get().MakeDirectory(*Directory, true);
    const FString AbsolutePath = FPaths::Combine(Directory, FileName);

    if (!Request.bDryRun)
    {
        FScreenshotRequest::RequestScreenshot(AbsolutePath, false, false);
    }

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetStringField(TEXT("screenshot_path"), AbsolutePath);
    Out->SetBoolField(TEXT("requested"), !Request.bDryRun);
    return BuildPassThroughResult(Request.bDryRun ? TEXT("Dry run screenshot path generated.") : TEXT("Screenshot request queued."), Out);
}
} // namespace UnrealAgentPrivate

FAutomationCompositeAction::FAutomationCompositeAction(const FString& InName, const FString& InDescription)
    : Name(InName)
    , Description(InDescription)
{
}

FString FAutomationCompositeAction::GetName() const
{
    return Name;
}

FString FAutomationCompositeAction::GetDescription() const
{
    return Description;
}

FAgentActionResult FAutomationCompositeAction::Execute(const FAgentActionRequest& Request)
{
    TSharedPtr<FJsonObject> Payload;
    FString ParseError;
    if (!UnrealAgentPrivate::ParsePayloadObject(Request.PayloadJson, Payload, ParseError))
    {
        return {false, ParseError, TEXT(""), TEXT("INVALID_PAYLOAD")};
    }

    if (Name == TEXT("create_widget_blueprint"))
    {
        return UnrealAgentPrivate::HandleCreateWidgetBlueprint(Request, Payload);
    }
    if (Name == TEXT("modify_widget_tree"))
    {
        return UnrealAgentPrivate::HandleModifyWidgetTree(Request, Payload);
    }
    if (Name == TEXT("bind_widget_events"))
    {
        return UnrealAgentPrivate::HandleBindWidgetEvents(Request, Payload);
    }
    if (Name == TEXT("create_game_mode_logic"))
    {
        return UnrealAgentPrivate::HandleVariableSystem(Request, Payload, TEXT("GameModeState"), TEXT("string"), TEXT("Ready"), TEXT("AgentGameplay"));
    }
    if (Name == TEXT("create_objective_actor"))
    {
        return UnrealAgentPrivate::HandleCreateObjectiveActor(Request, Payload);
    }
    if (Name == TEXT("wire_objective_progress"))
    {
        return UnrealAgentPrivate::HandleVariableSystem(Request, Payload, TEXT("ObjectiveProgress"), TEXT("int"), TEXT("0"), TEXT("AgentGameplay"));
    }
    if (Name == TEXT("create_timer_system"))
    {
        return UnrealAgentPrivate::HandleVariableSystem(Request, Payload, TEXT("TimeRemaining"), TEXT("float"), TEXT("60.0"), TEXT("AgentGameplay"));
    }
    if (Name == TEXT("create_score_system"))
    {
        return UnrealAgentPrivate::HandleVariableSystem(Request, Payload, TEXT("Score"), TEXT("int"), TEXT("0"), TEXT("AgentGameplay"));
    }
    if (Name == TEXT("create_restart_flow"))
    {
        return UnrealAgentPrivate::HandleVariableSystem(Request, Payload, TEXT("CanRestart"), TEXT("bool"), TEXT("true"), TEXT("AgentGameplay"));
    }
    if (Name == TEXT("batch_spawn_actors"))
    {
        return UnrealAgentPrivate::HandleBatchSpawnActors(Request, Payload);
    }
    if (Name == TEXT("layout_along_spline"))
    {
        return UnrealAgentPrivate::HandleLayoutAlongSpline(Request, Payload);
    }
    if (Name == TEXT("create_level_chunk"))
    {
        return UnrealAgentPrivate::HandleCreateLevelChunk(Request, Payload);
    }
    if (Name == TEXT("tag_and_group_actors"))
    {
        return UnrealAgentPrivate::HandleTagAndGroupActors(Request, Payload);
    }
    if (Name == TEXT("delete_actors_by_filter"))
    {
        return UnrealAgentPrivate::HandleDeleteActorsByFilter(Request, Payload);
    }
    if (Name == TEXT("clear_map_layout"))
    {
        return UnrealAgentPrivate::HandleClearMapLayout(Request, Payload);
    }
    if (Name == TEXT("create_data_asset"))
    {
        return UnrealAgentPrivate::HandleCreateDataAsset(Request, Payload);
    }
    if (Name == TEXT("create_data_table"))
    {
        return UnrealAgentPrivate::HandleCreateDataTable(Request, Payload);
    }
    if (Name == TEXT("edit_data_table_row"))
    {
        return UnrealAgentPrivate::HandleEditDataTableRow(Request, Payload);
    }
    if (Name == TEXT("validate_data_schema"))
    {
        return UnrealAgentPrivate::HandleValidateDataSchema(Request, Payload);
    }
    if (Name == TEXT("inspect_compile_errors"))
    {
        return UnrealAgentPrivate::HandleInspectCompileErrors(Request, Payload);
    }
    if (Name == TEXT("run_pie_scenario"))
    {
        return UnrealAgentPrivate::HandleRunPieScenario(Request, Payload);
    }
    if (Name == TEXT("assert_world_state"))
    {
        return UnrealAgentPrivate::HandleAssertWorldState(Request, Payload);
    }
    if (Name == TEXT("capture_screenshot"))
    {
        return UnrealAgentPrivate::HandleCaptureScreenshot(Request, Payload);
    }

    return UnrealAgentPrivate::BuildUnsupported(FString::Printf(TEXT("Unsupported automation action: %s"), *Name));
}
