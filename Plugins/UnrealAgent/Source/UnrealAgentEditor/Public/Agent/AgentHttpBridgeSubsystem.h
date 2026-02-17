#pragma once

#include "CoreMinimal.h"
#include "HttpServerRequest.h"
#include "HttpServerResponse.h"
#include "IHttpRouter.h"
#include "EditorSubsystem.h"
#include "HAL/CriticalSection.h"

#include "AgentHttpBridgeSubsystem.generated.h"

class FJsonObject;

UCLASS()
class UNREALAGENTEDITOR_API UAgentHttpBridgeSubsystem : public UEditorSubsystem
{
    GENERATED_BODY()

public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

private:
    bool HandleExecute(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    bool HandleRunPlan(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    bool HandleRunGoal(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    bool HandleListActions(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    bool HandleState(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    bool HandleInfo(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    bool HandleHealth(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    bool HandleRecipes(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    bool HandleRunRecipe(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    bool HandleValidateRecipe(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    bool HandleRunScenario(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    bool HandleDebugTraces(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    bool HandleDebugClear(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    bool IsLoopbackRequest(const FHttpServerRequest& Request) const;
    FString ReadRequestBody(const FHttpServerRequest& Request) const;
    void RecordTrace(
        const FString& Route,
        const EHttpServerRequestVerbs Verb,
        const FString& RequestBody,
        const bool bSuccess,
        const FString& ErrorCode,
        const FString& Message,
        const EHttpServerResponseCodes StatusCode,
        const double DurationMs,
        const TSharedPtr<FJsonObject>& Extra = nullptr
    );
    void AppendTraceToFile(const TSharedRef<FJsonObject>& TraceObject);
    void SendJsonResponse(
        const FHttpResultCallback& OnComplete,
        const FString& JsonString,
        EHttpServerResponseCodes StatusCode
    ) const;

    uint32 ListenPort = 47777;
    TSharedPtr<IHttpRouter> HttpRouter;
    FHttpRouteHandle ExecuteRouteHandle;
    FHttpRouteHandle RunPlanRouteHandle;
    FHttpRouteHandle RunGoalRouteHandle;
    FHttpRouteHandle ActionsRouteHandle;
    FHttpRouteHandle StateRouteHandle;
    FHttpRouteHandle InfoRouteHandle;
    FHttpRouteHandle HealthRouteHandle;
    FHttpRouteHandle RecipesRouteHandle;
    FHttpRouteHandle RunRecipeRouteHandle;
    FHttpRouteHandle ValidateRecipeRouteHandle;
    FHttpRouteHandle RunScenarioRouteHandle;
    FHttpRouteHandle DebugTracesRouteHandle;
    FHttpRouteHandle DebugClearRouteHandle;
    FCriticalSection DebugTraceMutex;
    TArray<TSharedPtr<FJsonValue>> DebugTraceEntries;
    int32 DebugTraceMaxEntries = 300;
    FString DebugTraceFilePath;
};
