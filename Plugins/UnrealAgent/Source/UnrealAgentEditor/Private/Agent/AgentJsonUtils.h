#pragma once

#include "Agent/AgentTypes.h"
#include "CoreMinimal.h"

class FJsonObject;

namespace UnrealAgentPrivate
{
bool ParseJsonObject(const FString& JsonString, TSharedPtr<FJsonObject>& OutObject, FString& OutError);
FString SerializePayload(const TSharedRef<FJsonObject>& Payload);
FString SerializeActionResult(const FAgentActionResult& Result);
FString NormalizeErrorCode(const FAgentActionResult& Result);
} // namespace UnrealAgentPrivate
