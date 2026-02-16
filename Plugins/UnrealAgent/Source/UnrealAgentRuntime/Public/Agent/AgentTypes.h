#pragma once

#include "CoreMinimal.h"

struct FAgentActionRequest
{
    FString ActionName;
    FString PayloadJson;
    bool bDryRun = false;
};

struct FAgentActionResult
{
    bool bSuccess = false;
    FString Message;
    FString PayloadJson;
    FString ErrorCode;
};

struct FAgentActionDescriptor
{
    FString Name;
    FString Description;
};
