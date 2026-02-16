#pragma once

#include "CoreMinimal.h"
#include "EditorSubsystem.h"

#include "AgentEditorSubsystem.generated.h"

UCLASS()
class UNREALAGENTEDITOR_API UAgentEditorSubsystem : public UEditorSubsystem
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintCallable, Category = "UnrealAgent")
    FString ExecuteAction(const FString& ActionName, const FString& PayloadJson, bool bDryRun = false);

    UFUNCTION(BlueprintCallable, Category = "UnrealAgent")
    TArray<FString> ListActions() const;
};
