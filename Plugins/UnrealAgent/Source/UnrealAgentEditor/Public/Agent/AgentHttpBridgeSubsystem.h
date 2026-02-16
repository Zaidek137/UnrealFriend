#pragma once

#include "CoreMinimal.h"
#include "HttpServerRequest.h"
#include "HttpServerResponse.h"
#include "IHttpRouter.h"
#include "EditorSubsystem.h"

#include "AgentHttpBridgeSubsystem.generated.h"

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
    bool IsLoopbackRequest(const FHttpServerRequest& Request) const;
    FString ReadRequestBody(const FHttpServerRequest& Request) const;
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
};
