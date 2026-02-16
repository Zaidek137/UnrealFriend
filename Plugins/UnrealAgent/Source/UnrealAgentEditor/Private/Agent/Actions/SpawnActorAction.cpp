#include "Agent/Actions/SpawnActorAction.h"

#include "Agent/AgentJsonUtils.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Editor.h"
#include "Engine/Level.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "Components/StaticMeshComponent.h"
#include "ScopedTransaction.h"
#include "Serialization/JsonTypes.h"

namespace UnrealAgentPrivate
{
static bool ReadVectorField(const TSharedPtr<FJsonObject>& JsonObject, const FString& FieldName, FVector& OutVector)
{
    const TArray<TSharedPtr<FJsonValue>>* Values;
    if (!JsonObject->TryGetArrayField(FieldName, Values) || Values->Num() != 3)
    {
        return false;
    }

    double X = 0.0;
    double Y = 0.0;
    double Z = 0.0;
    if (!(*Values)[0].IsValid() || !(*Values)[1].IsValid() || !(*Values)[2].IsValid())
    {
        return false;
    }

    if (!(*Values)[0]->TryGetNumber(X) || !(*Values)[1]->TryGetNumber(Y) || !(*Values)[2]->TryGetNumber(Z))
    {
        return false;
    }

    OutVector = FVector(static_cast<float>(X), static_cast<float>(Y), static_cast<float>(Z));
    return true;
}
} // namespace UnrealAgentPrivate

FString FSpawnActorAction::GetName() const
{
    return TEXT("spawn_actor");
}

FString FSpawnActorAction::GetDescription() const
{
    return TEXT("Spawns an actor in the current editor world.");
}

FAgentActionResult FSpawnActorAction::Execute(const FAgentActionRequest& Request)
{
    FString ClassPath = TEXT("/Script/Engine.StaticMeshActor");
    FString ActorLabel = TEXT("AgentActor");
    FVector Location = FVector::ZeroVector;
    FVector RotationEuler = FVector::ZeroVector;
    FVector Scale = FVector(1.0f, 1.0f, 1.0f);
    FString FolderPath;
    FString StaticMeshPath;
    bool bSelectAfterSpawn = true;
    TArray<FName> Tags;

    if (!Request.PayloadJson.IsEmpty())
    {
        TSharedPtr<FJsonObject> Payload;
        FString ParseError;
        if (!UnrealAgentPrivate::ParseJsonObject(Request.PayloadJson, Payload, ParseError))
        {
            return {false, ParseError, TEXT("")};
        }

        Payload->TryGetStringField(TEXT("class_path"), ClassPath);
        Payload->TryGetStringField(TEXT("actor_label"), ActorLabel);
        Payload->TryGetStringField(TEXT("folder_path"), FolderPath);
        Payload->TryGetStringField(TEXT("static_mesh_path"), StaticMeshPath);
        Payload->TryGetBoolField(TEXT("select_actor"), bSelectAfterSpawn);
        const TArray<TSharedPtr<FJsonValue>>* TagArray = nullptr;
        if (Payload->TryGetArrayField(TEXT("tags"), TagArray) && TagArray != nullptr)
        {
            for (const TSharedPtr<FJsonValue>& TagValue : *TagArray)
            {
                FString TagString;
                if (TagValue.IsValid() && TagValue->TryGetString(TagString) && !TagString.IsEmpty())
                {
                    Tags.Add(FName(*TagString));
                }
            }
        }

        FVector ParsedVector;
        if (UnrealAgentPrivate::ReadVectorField(Payload, TEXT("location"), ParsedVector))
        {
            Location = ParsedVector;
        }
        if (UnrealAgentPrivate::ReadVectorField(Payload, TEXT("rotation"), ParsedVector))
        {
            RotationEuler = ParsedVector;
        }
        if (UnrealAgentPrivate::ReadVectorField(Payload, TEXT("scale"), ParsedVector))
        {
            Scale = ParsedVector;
        }
    }

    UClass* ActorClass = FindObject<UClass>(nullptr, *ClassPath);
    if (ActorClass == nullptr)
    {
        ActorClass = LoadObject<UClass>(nullptr, *ClassPath);
    }

    if (ActorClass == nullptr || !ActorClass->IsChildOf(AActor::StaticClass()))
    {
        return {false, FString::Printf(TEXT("Invalid actor class_path: %s"), *ClassPath), TEXT("")};
    }

    UWorld* EditorWorld = nullptr;
    if (GEditor != nullptr)
    {
        EditorWorld = GEditor->GetEditorWorldContext().World();
    }

    if (EditorWorld == nullptr)
    {
        return {false, TEXT("No editor world found."), TEXT("")};
    }

    if (GEditor != nullptr && GEditor->PlayWorld != nullptr)
    {
        return {false, TEXT("Cannot spawn_actor while PIE is active."), TEXT("")};
    }

    const FTransform SpawnTransform(FRotator::MakeFromEuler(RotationEuler), Location, Scale);

    if (Request.bDryRun)
    {
        const TSharedRef<FJsonObject> DryRunPayload = MakeShared<FJsonObject>();
        DryRunPayload->SetStringField(TEXT("class_path"), ActorClass->GetPathName());
        DryRunPayload->SetStringField(TEXT("actor_label"), ActorLabel);
        DryRunPayload->SetStringField(TEXT("static_mesh_path"), StaticMeshPath);
        if (Tags.Num() > 0)
        {
            TArray<TSharedPtr<FJsonValue>> TagValues;
            for (const FName& Tag : Tags)
            {
                TagValues.Add(MakeShared<FJsonValueString>(Tag.ToString()));
            }
            DryRunPayload->SetArrayField(TEXT("tags"), TagValues);
        }
        DryRunPayload->SetArrayField(
            TEXT("location"),
            {
                MakeShared<FJsonValueNumber>(Location.X),
                MakeShared<FJsonValueNumber>(Location.Y),
                MakeShared<FJsonValueNumber>(Location.Z)
            }
        );
        return {
            true,
            TEXT("Dry run successful. No actor spawned."),
            UnrealAgentPrivate::SerializePayload(DryRunPayload)
        };
    }

    const FScopedTransaction Transaction(NSLOCTEXT("UnrealAgent", "SpawnActorAction", "Agent Spawn Actor"));

    FActorSpawnParameters SpawnParams;
    SpawnParams.Name = NAME_None;
    AActor* SpawnedActor = EditorWorld->SpawnActor<AActor>(ActorClass, SpawnTransform, SpawnParams);
    if (SpawnedActor == nullptr)
    {
        return {false, TEXT("Failed to spawn actor."), TEXT("")};
    }

    if (!ActorLabel.IsEmpty())
    {
        SpawnedActor->SetActorLabel(ActorLabel);
    }

    if (!FolderPath.IsEmpty())
    {
        SpawnedActor->SetFolderPath(*FolderPath);
    }
    for (const FName& Tag : Tags)
    {
        if (!SpawnedActor->Tags.Contains(Tag))
        {
            SpawnedActor->Tags.Add(Tag);
        }
    }

    if (!StaticMeshPath.IsEmpty())
    {
        AStaticMeshActor* StaticMeshActor = Cast<AStaticMeshActor>(SpawnedActor);
        if (StaticMeshActor == nullptr || StaticMeshActor->GetStaticMeshComponent() == nullptr)
        {
            return {
                false,
                TEXT("static_mesh_path provided, but spawned actor is not a StaticMeshActor."),
                TEXT("")
            };
        }

        UStaticMesh* StaticMesh = LoadObject<UStaticMesh>(nullptr, *StaticMeshPath);
        if (StaticMesh == nullptr)
        {
            return {
                false,
                FString::Printf(TEXT("Failed to load static mesh: %s"), *StaticMeshPath),
                TEXT("")
            };
        }

        StaticMeshActor->GetStaticMeshComponent()->SetStaticMesh(StaticMesh);
    }

    if (bSelectAfterSpawn && GEditor != nullptr)
    {
        GEditor->SelectNone(false, true);
        GEditor->SelectActor(SpawnedActor, true, true);
    }

    EditorWorld->MarkPackageDirty();

    const TSharedRef<FJsonObject> SuccessPayload = MakeShared<FJsonObject>();
    SuccessPayload->SetStringField(TEXT("actor_name"), SpawnedActor->GetName());
    SuccessPayload->SetStringField(TEXT("actor_label"), SpawnedActor->GetActorLabel());
    SuccessPayload->SetStringField(TEXT("class_path"), ActorClass->GetPathName());
    SuccessPayload->SetStringField(TEXT("static_mesh_path"), StaticMeshPath);
    if (Tags.Num() > 0)
    {
        TArray<TSharedPtr<FJsonValue>> TagValues;
        for (const FName& Tag : Tags)
        {
            TagValues.Add(MakeShared<FJsonValueString>(Tag.ToString()));
        }
        SuccessPayload->SetArrayField(TEXT("tags"), TagValues);
    }
    SuccessPayload->SetStringField(TEXT("world"), EditorWorld->GetPathName());
    SuccessPayload->SetStringField(TEXT("level"), SpawnedActor->GetLevel()->GetPathName());

    return {
        true,
        TEXT("Actor spawned successfully."),
        UnrealAgentPrivate::SerializePayload(SuccessPayload)
    };
}
