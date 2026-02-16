#include "Agent/AgentHttpBridgeSubsystem.h"

#include "Agent/AgentActionRegistry.h"
#include "Agent/AgentJsonUtils.h"
#include "Dom/JsonObject.h"
#include "Editor.h"
#include "Engine/Engine.h"
#include "Engine/Selection.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "HAL/PlatformTime.h"
#include "HttpPath.h"
#include "HttpServerModule.h"
#include "IHttpRouter.h"
#include "Misc/CommandLine.h"
#include "Misc/EngineVersion.h"
#include "Misc/FileHelper.h"
#include "Misc/Guid.h"
#include "Misc/Parse.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonTypes.h"

namespace UnrealAgentPrivate
{
static bool TryReadActionRequestFromJson(
    const TSharedPtr<FJsonObject>& JsonObject,
    const bool bDefaultDryRun,
    FAgentActionRequest& OutRequest,
    FString& OutError
)
{
    OutRequest = {};
    OutRequest.bDryRun = bDefaultDryRun;
    OutError.Reset();

    if (!JsonObject.IsValid())
    {
        OutError = TEXT("Invalid action object.");
        return false;
    }

    if (!JsonObject->TryGetStringField(TEXT("action"), OutRequest.ActionName) || OutRequest.ActionName.IsEmpty())
    {
        OutError = TEXT("Missing required field: action");
        return false;
    }

    JsonObject->TryGetBoolField(TEXT("dry_run"), OutRequest.bDryRun);

    OutRequest.PayloadJson = TEXT("{}");
    const TSharedPtr<FJsonObject>* PayloadObject = nullptr;
    if (JsonObject->TryGetObjectField(TEXT("payload"), PayloadObject) && PayloadObject != nullptr && PayloadObject->IsValid())
    {
        OutRequest.PayloadJson = SerializePayload((*PayloadObject).ToSharedRef());
    }
    else if (JsonObject->HasField(TEXT("payload")))
    {
        OutError = TEXT("Field payload must be a JSON object.");
        return false;
    }

    return true;
}

static TSharedRef<FJsonObject> BuildStepResultObject(
    const FString& StepId,
    const FAgentActionRequest& ActionRequest,
    const FAgentActionResult& ActionResult,
    const int32 DurationMs
)
{
    TSharedRef<FJsonObject> StepObject = MakeShared<FJsonObject>();
    StepObject->SetStringField(TEXT("id"), StepId);
    StepObject->SetStringField(TEXT("action"), ActionRequest.ActionName);
    StepObject->SetBoolField(TEXT("dry_run"), ActionRequest.bDryRun);
    StepObject->SetBoolField(TEXT("success"), ActionResult.bSuccess);
    StepObject->SetStringField(TEXT("error_code"), NormalizeErrorCode(ActionResult));
    StepObject->SetStringField(TEXT("message"), ActionResult.Message);
    StepObject->SetNumberField(TEXT("duration_ms"), DurationMs);

    if (!ActionResult.PayloadJson.IsEmpty())
    {
        TSharedPtr<FJsonObject> ParsedPayload;
        FString ParseError;
        if (ParseJsonObject(ActionResult.PayloadJson, ParsedPayload, ParseError) && ParsedPayload.IsValid())
        {
            StepObject->SetObjectField(TEXT("payload"), ParsedPayload.ToSharedRef());
        }
        else
        {
            StepObject->SetStringField(TEXT("payload_raw"), ActionResult.PayloadJson);
        }
    }

    return StepObject;
}

static TSharedRef<FJsonObject> CreateErrorResponseObject(const FString& Message)
{
    TSharedRef<FJsonObject> ErrorObject = MakeShared<FJsonObject>();
    ErrorObject->SetBoolField(TEXT("success"), false);
    ErrorObject->SetStringField(TEXT("message"), Message);
    return ErrorObject;
}

static bool ExecutePlanRequest(
    const TSharedPtr<FJsonObject>& JsonRequest,
    TSharedRef<FJsonObject>& OutResponse,
    EHttpServerResponseCodes& OutStatusCode
)
{
    if (!JsonRequest.IsValid())
    {
        OutResponse = CreateErrorResponseObject(TEXT("Invalid plan object."));
        OutStatusCode = EHttpServerResponseCodes::BadRequest;
        return false;
    }

    const TArray<TSharedPtr<FJsonValue>>* StepsArray = nullptr;
    if (!JsonRequest->TryGetArrayField(TEXT("steps"), StepsArray) || StepsArray == nullptr || StepsArray->Num() == 0)
    {
        OutResponse = CreateErrorResponseObject(TEXT("Missing required array field: steps"));
        OutStatusCode = EHttpServerResponseCodes::BadRequest;
        return false;
    }

    FString PlanId;
    JsonRequest->TryGetStringField(TEXT("plan_id"), PlanId);
    if (PlanId.IsEmpty())
    {
        PlanId = FGuid::NewGuid().ToString(EGuidFormats::DigitsWithHyphensLower);
    }

    bool bGlobalDryRun = false;
    bool bStopOnError = true;
    JsonRequest->TryGetBoolField(TEXT("dry_run"), bGlobalDryRun);
    JsonRequest->TryGetBoolField(TEXT("stop_on_error"), bStopOnError);

    bool bStoppedEarly = false;
    int32 SucceededSteps = 0;
    int32 FailedSteps = 0;
    int32 RequestedCompileSteps = 0;
    TArray<TSharedPtr<FJsonValue>> StepResults;
    StepResults.Reserve(StepsArray->Num());

    auto AppendFailureStep = [&StepResults, &FailedSteps](
        const FString& StepId,
        const FString& ActionName,
        const bool bDryRun,
        const FString& ErrorMessage
    )
    {
        TSharedRef<FJsonObject> StepObject = MakeShared<FJsonObject>();
        StepObject->SetStringField(TEXT("id"), StepId);
        StepObject->SetStringField(TEXT("action"), ActionName);
        StepObject->SetBoolField(TEXT("dry_run"), bDryRun);
        StepObject->SetBoolField(TEXT("success"), false);
        FAgentActionResult FailureResult;
        FailureResult.bSuccess = false;
        FailureResult.Message = ErrorMessage;
        StepObject->SetStringField(TEXT("error_code"), NormalizeErrorCode(FailureResult));
        StepObject->SetStringField(TEXT("message"), ErrorMessage);
        StepObject->SetNumberField(TEXT("duration_ms"), 0);
        StepResults.Add(MakeShared<FJsonValueObject>(StepObject));
        ++FailedSteps;
    };

    for (int32 Index = 0; Index < StepsArray->Num(); ++Index)
    {
        const TSharedPtr<FJsonObject> StepObject = (*StepsArray)[Index].IsValid() ? (*StepsArray)[Index]->AsObject() : nullptr;
        const FString DefaultStepId = FString::Printf(TEXT("step_%d"), Index + 1);
        if (!StepObject.IsValid())
        {
            AppendFailureStep(DefaultStepId, TEXT(""), bGlobalDryRun, TEXT("Each step must be a JSON object."));
            if (bStopOnError)
            {
                bStoppedEarly = true;
                break;
            }
            continue;
        }

        FString StepId;
        StepObject->TryGetStringField(TEXT("id"), StepId);
        if (StepId.IsEmpty())
        {
            StepId = DefaultStepId;
        }

        FAgentActionRequest ActionRequest;
        FString ActionParseError;
        if (!TryReadActionRequestFromJson(StepObject, bGlobalDryRun, ActionRequest, ActionParseError))
        {
            FString ActionName;
            StepObject->TryGetStringField(TEXT("action"), ActionName);
            AppendFailureStep(StepId, ActionName, bGlobalDryRun, ActionParseError);
            if (bStopOnError)
            {
                bStoppedEarly = true;
                break;
            }
            continue;
        }

        const double StartTime = FPlatformTime::Seconds();
        const FAgentActionResult ActionResult = FAgentActionRegistry::Get().Execute(ActionRequest);
        const int32 DurationMs = static_cast<int32>((FPlatformTime::Seconds() - StartTime) * 1000.0);

        StepResults.Add(MakeShared<FJsonValueObject>(
            BuildStepResultObject(StepId, ActionRequest, ActionResult, DurationMs)
        ));

        if (ActionResult.bSuccess)
        {
            ++SucceededSteps;
        }
        else
        {
            ++FailedSteps;
            if (bStopOnError)
            {
                bStoppedEarly = true;
                break;
            }
        }
    }

    const TArray<TSharedPtr<FJsonValue>>* CompileBlueprints = nullptr;
    if (!bStoppedEarly && JsonRequest->TryGetArrayField(TEXT("compile_blueprints"), CompileBlueprints) && CompileBlueprints != nullptr)
    {
        RequestedCompileSteps = CompileBlueprints->Num();
        for (int32 Index = 0; Index < CompileBlueprints->Num(); ++Index)
        {
            FString BlueprintPath;
            if (!(*CompileBlueprints)[Index].IsValid() || !(*CompileBlueprints)[Index]->TryGetString(BlueprintPath) || BlueprintPath.IsEmpty())
            {
                AppendFailureStep(
                    FString::Printf(TEXT("compile_%d"), Index + 1),
                    TEXT("compile_blueprint"),
                    bGlobalDryRun,
                    TEXT("compile_blueprints entries must be non-empty strings.")
                );
                if (bStopOnError)
                {
                    bStoppedEarly = true;
                    break;
                }
                continue;
            }

            TSharedRef<FJsonObject> CompilePayload = MakeShared<FJsonObject>();
            CompilePayload->SetStringField(TEXT("blueprint_path"), BlueprintPath);

            FAgentActionRequest CompileRequest;
            CompileRequest.ActionName = TEXT("compile_blueprint");
            CompileRequest.PayloadJson = SerializePayload(CompilePayload);
            CompileRequest.bDryRun = bGlobalDryRun;

            const double StartTime = FPlatformTime::Seconds();
            const FAgentActionResult CompileResult = FAgentActionRegistry::Get().Execute(CompileRequest);
            const int32 DurationMs = static_cast<int32>((FPlatformTime::Seconds() - StartTime) * 1000.0);

            StepResults.Add(MakeShared<FJsonValueObject>(
                BuildStepResultObject(
                    FString::Printf(TEXT("compile_%d"), Index + 1),
                    CompileRequest,
                    CompileResult,
                    DurationMs
                )
            ));

            if (CompileResult.bSuccess)
            {
                ++SucceededSteps;
            }
            else
            {
                ++FailedSteps;
                if (bStopOnError)
                {
                    bStoppedEarly = true;
                    break;
                }
            }
        }
    }

    const bool bPlanSucceeded = FailedSteps == 0;
    TSharedRef<FJsonObject> SummaryObject = MakeShared<FJsonObject>();
    SummaryObject->SetNumberField(TEXT("requested_action_steps"), StepsArray->Num());
    SummaryObject->SetNumberField(TEXT("requested_compile_steps"), RequestedCompileSteps);
    SummaryObject->SetNumberField(TEXT("requested_steps"), StepsArray->Num() + RequestedCompileSteps);
    SummaryObject->SetNumberField(TEXT("executed_steps"), StepResults.Num());
    SummaryObject->SetNumberField(TEXT("succeeded_steps"), SucceededSteps);
    SummaryObject->SetNumberField(TEXT("failed_steps"), FailedSteps);
    SummaryObject->SetBoolField(TEXT("stopped_early"), bStoppedEarly);
    SummaryObject->SetBoolField(TEXT("dry_run"), bGlobalDryRun);

    OutResponse = MakeShared<FJsonObject>();
    OutResponse->SetBoolField(TEXT("success"), bPlanSucceeded);
    OutResponse->SetStringField(
        TEXT("message"),
        bPlanSucceeded ? TEXT("Plan completed successfully.") : TEXT("Plan completed with failures.")
    );
    OutResponse->SetStringField(TEXT("plan_id"), PlanId);
    OutResponse->SetObjectField(TEXT("summary"), SummaryObject);
    OutResponse->SetArrayField(TEXT("steps"), StepResults);

    OutStatusCode = EHttpServerResponseCodes::Ok;
    return true;
}

static bool StringContainsAny(const FString& HaystackLower, const TArray<FString>& NeedlesLower)
{
    for (const FString& Needle : NeedlesLower)
    {
        if (HaystackLower.Contains(Needle))
        {
            return true;
        }
    }
    return false;
}

static bool BuildPlanFromGoalRequest(
    const TSharedPtr<FJsonObject>& GoalRequest,
    TSharedPtr<FJsonObject>& OutPlanObject,
    FString& OutError
)
{
    OutPlanObject.Reset();
    OutError.Reset();

    if (!GoalRequest.IsValid())
    {
        OutError = TEXT("Invalid goal request.");
        return false;
    }

    FString GoalText;
    if (!GoalRequest->TryGetStringField(TEXT("goal"), GoalText) || GoalText.IsEmpty())
    {
        OutError = TEXT("Missing required field: goal");
        return false;
    }

    const FString GoalLower = GoalText.ToLower();

    const TSharedPtr<FJsonObject>* ContextPtr = nullptr;
    TSharedPtr<FJsonObject> Context = MakeShared<FJsonObject>();
    if (GoalRequest->TryGetObjectField(TEXT("goal_context"), ContextPtr) && ContextPtr != nullptr && ContextPtr->IsValid())
    {
        Context = *ContextPtr;
    }
    else if (GoalRequest->TryGetObjectField(TEXT("context"), ContextPtr) && ContextPtr != nullptr && ContextPtr->IsValid())
    {
        Context = *ContextPtr;
    }

    bool bDryRun = false;
    bool bStopOnError = true;
    GoalRequest->TryGetBoolField(TEXT("dry_run"), bDryRun);
    GoalRequest->TryGetBoolField(TEXT("stop_on_error"), bStopOnError);

    FString PlanId;
    GoalRequest->TryGetStringField(TEXT("goal_id"), PlanId);
    if (PlanId.IsEmpty())
    {
        GoalRequest->TryGetStringField(TEXT("plan_id"), PlanId);
    }
    if (PlanId.IsEmpty())
    {
        PlanId = FString::Printf(TEXT("goal-%s"), *FGuid::NewGuid().ToString(EGuidFormats::DigitsWithHyphensLower));
    }

    FString BlueprintPath;
    FString AssetName;
    FString PackagePath;
    FString ParentClassPath = TEXT("/Script/Engine.Actor");
    FString Message;
    FString VariableName;
    FString VariableType = TEXT("bool");
    FString VariableDefault;
    FString VariableCategory = TEXT("Agent");
    FString FunctionClassPath;
    FString FunctionName;
    FString FunctionExecSource = TEXT("begin_play");

    Context->TryGetStringField(TEXT("blueprint_path"), BlueprintPath);
    Context->TryGetStringField(TEXT("asset_name"), AssetName);
    Context->TryGetStringField(TEXT("package_path"), PackagePath);
    Context->TryGetStringField(TEXT("parent_class"), ParentClassPath);
    Context->TryGetStringField(TEXT("message"), Message);
    Context->TryGetStringField(TEXT("variable_name"), VariableName);
    Context->TryGetStringField(TEXT("variable_type"), VariableType);
    Context->TryGetStringField(TEXT("default_value"), VariableDefault);
    Context->TryGetStringField(TEXT("variable_category"), VariableCategory);
    Context->TryGetStringField(TEXT("function_class_path"), FunctionClassPath);
    Context->TryGetStringField(TEXT("function_name"), FunctionName);
    Context->TryGetStringField(TEXT("exec_source"), FunctionExecSource);

    if (BlueprintPath.IsEmpty())
    {
        GoalRequest->TryGetStringField(TEXT("blueprint_path"), BlueprintPath);
    }
    if (AssetName.IsEmpty())
    {
        GoalRequest->TryGetStringField(TEXT("asset_name"), AssetName);
    }
    if (PackagePath.IsEmpty())
    {
        GoalRequest->TryGetStringField(TEXT("package_path"), PackagePath);
    }

    const bool bGoalMentionsBlueprint = GoalLower.Contains(TEXT("blueprint"));
    const bool bWantsCreate = bGoalMentionsBlueprint && StringContainsAny(
        GoalLower,
        TArray<FString>{TEXT("create"), TEXT("make"), TEXT("new")}
    );
    const bool bWantsPrint = StringContainsAny(
        GoalLower,
        TArray<FString>{TEXT("print"), TEXT("log"), TEXT("message"), TEXT("debug")}
    ) || !Message.IsEmpty();
    const bool bWantsBranch = StringContainsAny(
        GoalLower,
        TArray<FString>{TEXT("branch"), TEXT("if ")}
    );
    const bool bWantsVariable = GoalLower.Contains(TEXT("variable")) || !VariableName.IsEmpty();
    const bool bWantsSetDefault = StringContainsAny(
        GoalLower,
        TArray<FString>{TEXT("set default"), TEXT("default value")}
    ) || !VariableDefault.IsEmpty();
    const bool bWantsCall = StringContainsAny(
        GoalLower,
        TArray<FString>{TEXT("call function"), TEXT("invoke")}
    ) || !FunctionName.IsEmpty();

    const bool bNeedsBlueprintOps = bWantsPrint || bWantsBranch || bWantsVariable || bWantsSetDefault || bWantsCall;
    if (BlueprintPath.IsEmpty() && (bWantsCreate || bNeedsBlueprintOps))
    {
        if (AssetName.IsEmpty())
        {
            AssetName = TEXT("BP_AgentGenerated");
        }
        if (PackagePath.IsEmpty())
        {
            PackagePath = TEXT("/Game/AI/Blueprints");
        }
        const FString CleanPackagePath = PackagePath.EndsWith(TEXT("/")) ? PackagePath.LeftChop(1) : PackagePath;
        BlueprintPath = FString::Printf(TEXT("%s/%s"), *CleanPackagePath, *AssetName);
    }

    TArray<TSharedPtr<FJsonValue>> Steps;
    auto AddStep = [&Steps](const FString& StepId, const FString& Action, const TSharedRef<FJsonObject>& Payload)
    {
        TSharedRef<FJsonObject> Step = MakeShared<FJsonObject>();
        Step->SetStringField(TEXT("id"), StepId);
        Step->SetStringField(TEXT("action"), Action);
        Step->SetObjectField(TEXT("payload"), Payload);
        Steps.Add(MakeShared<FJsonValueObject>(Step));
    };

    if ((bWantsCreate || !AssetName.IsEmpty()) && !AssetName.IsEmpty() && !PackagePath.IsEmpty())
    {
        TSharedRef<FJsonObject> CreatePayload = MakeShared<FJsonObject>();
        CreatePayload->SetStringField(TEXT("asset_name"), AssetName);
        CreatePayload->SetStringField(TEXT("package_path"), PackagePath);
        CreatePayload->SetStringField(TEXT("parent_class"), ParentClassPath);
        AddStep(TEXT("create_blueprint"), TEXT("create_blueprint"), CreatePayload);
    }

    if (!BlueprintPath.IsEmpty() && bWantsVariable)
    {
        if (VariableName.IsEmpty())
        {
            VariableName = TEXT("AgentFlag");
        }
        TSharedRef<FJsonObject> VariablePayload = MakeShared<FJsonObject>();
        VariablePayload->SetStringField(TEXT("blueprint_path"), BlueprintPath);
        VariablePayload->SetStringField(TEXT("operation"), TEXT("add_variable"));
        VariablePayload->SetStringField(TEXT("variable_name"), VariableName);
        VariablePayload->SetStringField(TEXT("variable_type"), VariableType);
        VariablePayload->SetStringField(TEXT("default_value"), VariableDefault.IsEmpty() ? TEXT("false") : VariableDefault);
        VariablePayload->SetStringField(TEXT("category"), VariableCategory);
        VariablePayload->SetBoolField(TEXT("compile_after"), false);
        AddStep(TEXT("add_variable"), TEXT("modify_blueprint_graph"), VariablePayload);
    }

    if (!BlueprintPath.IsEmpty() && bWantsSetDefault && !VariableName.IsEmpty() && !VariableDefault.IsEmpty())
    {
        TSharedRef<FJsonObject> DefaultPayload = MakeShared<FJsonObject>();
        DefaultPayload->SetStringField(TEXT("blueprint_path"), BlueprintPath);
        DefaultPayload->SetStringField(TEXT("operation"), TEXT("set_default"));
        DefaultPayload->SetStringField(TEXT("variable_name"), VariableName);
        DefaultPayload->SetStringField(TEXT("default_value"), VariableDefault);
        DefaultPayload->SetBoolField(TEXT("compile_after"), false);
        AddStep(TEXT("set_default"), TEXT("modify_blueprint_graph"), DefaultPayload);
    }

    if (!BlueprintPath.IsEmpty() && bWantsBranch)
    {
        TSharedRef<FJsonObject> BranchPayload = MakeShared<FJsonObject>();
        BranchPayload->SetStringField(TEXT("blueprint_path"), BlueprintPath);
        BranchPayload->SetStringField(TEXT("operation"), TEXT("add_branch"));
        BranchPayload->SetBoolField(TEXT("compile_after"), false);
        AddStep(TEXT("add_branch"), TEXT("modify_blueprint_graph"), BranchPayload);
    }

    if (!BlueprintPath.IsEmpty() && bWantsCall)
    {
        if (FunctionClassPath.IsEmpty())
        {
            FunctionClassPath = TEXT("/Script/Engine.KismetSystemLibrary");
        }
        if (FunctionName.IsEmpty())
        {
            FunctionName = TEXT("PrintString");
        }

        TSharedRef<FJsonObject> CallPayload = MakeShared<FJsonObject>();
        CallPayload->SetStringField(TEXT("blueprint_path"), BlueprintPath);
        CallPayload->SetStringField(TEXT("operation"), TEXT("call_function"));
        CallPayload->SetStringField(TEXT("class_path"), FunctionClassPath);
        CallPayload->SetStringField(TEXT("function_name"), FunctionName);
        CallPayload->SetStringField(TEXT("exec_source"), FunctionExecSource);
        CallPayload->SetBoolField(TEXT("compile_after"), false);

        const TSharedPtr<FJsonObject>* InputObjectPtr = nullptr;
        if (Context->TryGetObjectField(TEXT("function_inputs"), InputObjectPtr) && InputObjectPtr != nullptr && InputObjectPtr->IsValid())
        {
            CallPayload->SetObjectField(TEXT("inputs"), (*InputObjectPtr).ToSharedRef());
        }
        else if (!Message.IsEmpty() && FunctionName == TEXT("PrintString"))
        {
            TSharedRef<FJsonObject> Inputs = MakeShared<FJsonObject>();
            Inputs->SetStringField(TEXT("InString"), Message);
            CallPayload->SetObjectField(TEXT("inputs"), Inputs);
        }

        AddStep(TEXT("call_function"), TEXT("modify_blueprint_graph"), CallPayload);
    }

    if (!BlueprintPath.IsEmpty() && bWantsPrint)
    {
        TSharedRef<FJsonObject> PrintPayload = MakeShared<FJsonObject>();
        PrintPayload->SetStringField(TEXT("blueprint_path"), BlueprintPath);
        PrintPayload->SetStringField(TEXT("operation"), TEXT("add_print_string_on_begin_play"));
        PrintPayload->SetStringField(TEXT("message"), Message.IsEmpty() ? TEXT("Generated by UnrealAgent") : Message);
        PrintPayload->SetBoolField(TEXT("compile_after"), false);
        AddStep(TEXT("add_begin_play_print"), TEXT("modify_blueprint_graph"), PrintPayload);
    }

    if (Steps.Num() == 0)
    {
        OutError = TEXT("Unable to infer a plan from goal and context. Provide blueprint details or explicit context hints.");
        return false;
    }

    OutPlanObject = MakeShared<FJsonObject>();
    OutPlanObject->SetStringField(TEXT("plan_id"), PlanId);
    OutPlanObject->SetBoolField(TEXT("dry_run"), bDryRun);
    OutPlanObject->SetBoolField(TEXT("stop_on_error"), bStopOnError);
    OutPlanObject->SetArrayField(TEXT("steps"), Steps);

    if (!BlueprintPath.IsEmpty())
    {
        TArray<TSharedPtr<FJsonValue>> CompileBlueprints;
        CompileBlueprints.Add(MakeShared<FJsonValueString>(BlueprintPath));
        OutPlanObject->SetArrayField(TEXT("compile_blueprints"), CompileBlueprints);
    }

    return true;
}
} // namespace UnrealAgentPrivate

void UAgentHttpBridgeSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);

    int32 PortFromCmd = static_cast<int32>(ListenPort);
    if (FParse::Value(FCommandLine::Get(), TEXT("UnrealAgentPort="), PortFromCmd) && PortFromCmd > 0)
    {
        ListenPort = static_cast<uint32>(PortFromCmd);
    }

    FHttpServerModule& HttpServerModule = FHttpServerModule::Get();
    HttpRouter = HttpServerModule.GetHttpRouter(ListenPort, false);
    if (!HttpRouter.IsValid())
    {
        UE_LOG(LogTemp, Error, TEXT("UnrealAgent: Failed to create HTTP router on port %u"), ListenPort);
        return;
    }

    ExecuteRouteHandle = HttpRouter->BindRoute(
        FHttpPath(TEXT("/unreal-agent/v1/execute")),
        EHttpServerRequestVerbs::VERB_POST,
        FHttpRequestHandler::CreateUObject(this, &UAgentHttpBridgeSubsystem::HandleExecute)
    );

    RunPlanRouteHandle = HttpRouter->BindRoute(
        FHttpPath(TEXT("/unreal-agent/v1/run-plan")),
        EHttpServerRequestVerbs::VERB_POST,
        FHttpRequestHandler::CreateUObject(this, &UAgentHttpBridgeSubsystem::HandleRunPlan)
    );

    RunGoalRouteHandle = HttpRouter->BindRoute(
        FHttpPath(TEXT("/unreal-agent/v1/run-goal")),
        EHttpServerRequestVerbs::VERB_POST,
        FHttpRequestHandler::CreateUObject(this, &UAgentHttpBridgeSubsystem::HandleRunGoal)
    );

    ActionsRouteHandle = HttpRouter->BindRoute(
        FHttpPath(TEXT("/unreal-agent/v1/actions")),
        EHttpServerRequestVerbs::VERB_GET,
        FHttpRequestHandler::CreateUObject(this, &UAgentHttpBridgeSubsystem::HandleListActions)
    );

    StateRouteHandle = HttpRouter->BindRoute(
        FHttpPath(TEXT("/unreal-agent/v1/state")),
        EHttpServerRequestVerbs::VERB_GET,
        FHttpRequestHandler::CreateUObject(this, &UAgentHttpBridgeSubsystem::HandleState)
    );

    InfoRouteHandle = HttpRouter->BindRoute(
        FHttpPath(TEXT("/unreal-agent/v1/info")),
        EHttpServerRequestVerbs::VERB_GET,
        FHttpRequestHandler::CreateUObject(this, &UAgentHttpBridgeSubsystem::HandleInfo)
    );

    HealthRouteHandle = HttpRouter->BindRoute(
        FHttpPath(TEXT("/unreal-agent/v1/health")),
        EHttpServerRequestVerbs::VERB_GET,
        FHttpRequestHandler::CreateUObject(this, &UAgentHttpBridgeSubsystem::HandleHealth)
    );

    HttpServerModule.StartAllListeners();

    UE_LOG(LogTemp, Log, TEXT("UnrealAgent HTTP bridge active: http://127.0.0.1:%u/unreal-agent/v1"), ListenPort);
}

void UAgentHttpBridgeSubsystem::Deinitialize()
{
    if (HttpRouter.IsValid())
    {
        HttpRouter->UnbindRoute(ExecuteRouteHandle);
        HttpRouter->UnbindRoute(RunPlanRouteHandle);
        HttpRouter->UnbindRoute(RunGoalRouteHandle);
        HttpRouter->UnbindRoute(ActionsRouteHandle);
        HttpRouter->UnbindRoute(StateRouteHandle);
        HttpRouter->UnbindRoute(InfoRouteHandle);
        HttpRouter->UnbindRoute(HealthRouteHandle);
    }

    HttpRouter.Reset();

    Super::Deinitialize();
}

bool UAgentHttpBridgeSubsystem::HandleExecute(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    if (!IsLoopbackRequest(Request))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Only loopback requests are allowed.\"}"),
            EHttpServerResponseCodes::Forbidden
        );
        return true;
    }

    const FString BodyJson = ReadRequestBody(Request);
    TSharedPtr<FJsonObject> JsonRequest;
    FString ParseError;
    if (!UnrealAgentPrivate::ParseJsonObject(BodyJson, JsonRequest, ParseError))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Invalid JSON body. Expected object with action and payload.\"}"),
            EHttpServerResponseCodes::BadRequest
        );
        return true;
    }

    FAgentActionRequest ActionRequest;
    if (!UnrealAgentPrivate::TryReadActionRequestFromJson(JsonRequest, false, ActionRequest, ParseError))
    {
        TSharedRef<FJsonObject> ErrorObject = MakeShared<FJsonObject>();
        ErrorObject->SetBoolField(TEXT("success"), false);
        ErrorObject->SetStringField(TEXT("message"), ParseError);
        SendJsonResponse(
            OnComplete,
            UnrealAgentPrivate::SerializePayload(ErrorObject),
            EHttpServerResponseCodes::BadRequest
        );
        return true;
    }

    const FAgentActionResult Result = FAgentActionRegistry::Get().Execute(ActionRequest);
    const FString ResponseJson = UnrealAgentPrivate::SerializeActionResult(Result);
    SendJsonResponse(
        OnComplete,
        ResponseJson,
        Result.bSuccess ? EHttpServerResponseCodes::Ok : EHttpServerResponseCodes::BadRequest
    );
    return true;
}

bool UAgentHttpBridgeSubsystem::HandleRunPlan(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    if (!IsLoopbackRequest(Request))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Only loopback requests are allowed.\"}"),
            EHttpServerResponseCodes::Forbidden
        );
        return true;
    }

    const FString BodyJson = ReadRequestBody(Request);
    TSharedPtr<FJsonObject> JsonRequest;
    FString ParseError;
    if (!UnrealAgentPrivate::ParseJsonObject(BodyJson, JsonRequest, ParseError))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Invalid JSON body. Expected plan object.\"}"),
            EHttpServerResponseCodes::BadRequest
        );
        return true;
    }

    TSharedRef<FJsonObject> ResponseObject = MakeShared<FJsonObject>();
    EHttpServerResponseCodes StatusCode = EHttpServerResponseCodes::Ok;
    UnrealAgentPrivate::ExecutePlanRequest(JsonRequest, ResponseObject, StatusCode);
    SendJsonResponse(
        OnComplete,
        UnrealAgentPrivate::SerializePayload(ResponseObject),
        StatusCode
    );
    return true;
}

bool UAgentHttpBridgeSubsystem::HandleRunGoal(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    if (!IsLoopbackRequest(Request))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Only loopback requests are allowed.\"}"),
            EHttpServerResponseCodes::Forbidden
        );
        return true;
    }

    const FString BodyJson = ReadRequestBody(Request);
    TSharedPtr<FJsonObject> GoalRequest;
    FString ParseError;
    if (!UnrealAgentPrivate::ParseJsonObject(BodyJson, GoalRequest, ParseError))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Invalid JSON body. Expected goal object.\"}"),
            EHttpServerResponseCodes::BadRequest
        );
        return true;
    }

    FString GoalText;
    GoalRequest->TryGetStringField(TEXT("goal"), GoalText);

    TSharedPtr<FJsonObject> GeneratedPlan;
    FString PlanError;
    if (!UnrealAgentPrivate::BuildPlanFromGoalRequest(GoalRequest, GeneratedPlan, PlanError))
    {
        TSharedRef<FJsonObject> ErrorObject = MakeShared<FJsonObject>();
        ErrorObject->SetBoolField(TEXT("success"), false);
        ErrorObject->SetStringField(TEXT("message"), PlanError);
        SendJsonResponse(
            OnComplete,
            UnrealAgentPrivate::SerializePayload(ErrorObject),
            EHttpServerResponseCodes::BadRequest
        );
        return true;
    }

    TSharedRef<FJsonObject> ExecutionResult = MakeShared<FJsonObject>();
    EHttpServerResponseCodes ExecutionStatusCode = EHttpServerResponseCodes::Ok;
    UnrealAgentPrivate::ExecutePlanRequest(GeneratedPlan, ExecutionResult, ExecutionStatusCode);

    TSharedRef<FJsonObject> ResponseObject = MakeShared<FJsonObject>();
    ResponseObject->SetBoolField(TEXT("success"), ExecutionResult->GetBoolField(TEXT("success")));
    ResponseObject->SetStringField(TEXT("message"), ExecutionResult->GetStringField(TEXT("message")));
    ResponseObject->SetStringField(TEXT("goal"), GoalText);
    ResponseObject->SetObjectField(TEXT("generated_plan"), GeneratedPlan.ToSharedRef());
    ResponseObject->SetObjectField(TEXT("execution"), ExecutionResult);

    SendJsonResponse(
        OnComplete,
        UnrealAgentPrivate::SerializePayload(ResponseObject),
        ExecutionStatusCode
    );
    return true;
}

bool UAgentHttpBridgeSubsystem::HandleListActions(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    if (!IsLoopbackRequest(Request))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Only loopback requests are allowed.\"}"),
            EHttpServerResponseCodes::Forbidden
        );
        return true;
    }

    const TArray<FAgentActionDescriptor> ActionDescriptors = FAgentActionRegistry::Get().GetActionDescriptors();
    TArray<TSharedPtr<FJsonValue>> ActionValues;
    ActionValues.Reserve(ActionDescriptors.Num());
    for (const FAgentActionDescriptor& Descriptor : ActionDescriptors)
    {
        TSharedRef<FJsonObject> ActionObject = MakeShared<FJsonObject>();
        ActionObject->SetStringField(TEXT("name"), Descriptor.Name);
        ActionObject->SetStringField(TEXT("description"), Descriptor.Description);
        ActionValues.Add(MakeShared<FJsonValueObject>(ActionObject));
    }

    TSharedRef<FJsonObject> ResponseObject = MakeShared<FJsonObject>();
    ResponseObject->SetBoolField(TEXT("success"), true);
    ResponseObject->SetArrayField(TEXT("actions"), ActionValues);

    SendJsonResponse(
        OnComplete,
        UnrealAgentPrivate::SerializePayload(ResponseObject),
        EHttpServerResponseCodes::Ok
    );
    return true;
}

bool UAgentHttpBridgeSubsystem::HandleState(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    if (!IsLoopbackRequest(Request))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Only loopback requests are allowed.\"}"),
            EHttpServerResponseCodes::Forbidden
        );
        return true;
    }

    TSharedRef<FJsonObject> ResponseObject = MakeShared<FJsonObject>();
    ResponseObject->SetBoolField(TEXT("success"), true);

    UWorld* EditorWorld = (GEditor != nullptr) ? GEditor->GetEditorWorldContext().World() : nullptr;
    ResponseObject->SetBoolField(TEXT("is_pie"), GEditor != nullptr && GEditor->PlayWorld != nullptr);
    ResponseObject->SetStringField(TEXT("editor_world"), EditorWorld != nullptr ? EditorWorld->GetPathName() : TEXT(""));
    ResponseObject->SetStringField(
        TEXT("current_level"),
        (EditorWorld != nullptr && EditorWorld->GetCurrentLevel() != nullptr) ? EditorWorld->GetCurrentLevel()->GetPathName() : TEXT("")
    );

    TArray<TSharedPtr<FJsonValue>> SelectedActors;
    if (GEditor != nullptr)
    {
        USelection* ActorSelection = GEditor->GetSelectedActors();
        if (ActorSelection != nullptr)
        {
            for (FSelectionIterator It(*ActorSelection); It; ++It)
            {
                const AActor* Actor = Cast<AActor>(*It);
                if (Actor == nullptr)
                {
                    continue;
                }

                TSharedRef<FJsonObject> ActorObject = MakeShared<FJsonObject>();
                ActorObject->SetStringField(TEXT("name"), Actor->GetName());
                ActorObject->SetStringField(TEXT("label"), Actor->GetActorLabel());
                ActorObject->SetStringField(TEXT("class"), Actor->GetClass()->GetPathName());
                ActorObject->SetStringField(TEXT("path"), Actor->GetPathName());
                SelectedActors.Add(MakeShared<FJsonValueObject>(ActorObject));
            }
        }
    }
    ResponseObject->SetArrayField(TEXT("selected_actors"), SelectedActors);

    SendJsonResponse(
        OnComplete,
        UnrealAgentPrivate::SerializePayload(ResponseObject),
        EHttpServerResponseCodes::Ok
    );
    return true;
}

bool UAgentHttpBridgeSubsystem::HandleInfo(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    if (!IsLoopbackRequest(Request))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Only loopback requests are allowed.\"}"),
            EHttpServerResponseCodes::Forbidden
        );
        return true;
    }

    TSharedRef<FJsonObject> ResponseObject = MakeShared<FJsonObject>();
    ResponseObject->SetBoolField(TEXT("success"), true);
    ResponseObject->SetStringField(TEXT("plugin_name"), TEXT("UnrealAgent"));
    ResponseObject->SetStringField(TEXT("plugin_version"), TEXT("0.1.0"));
    ResponseObject->SetStringField(TEXT("api_version"), TEXT("v1"));
    ResponseObject->SetStringField(TEXT("engine_version"), FEngineVersion::Current().ToString());
    ResponseObject->SetStringField(TEXT("engine_branch"), FEngineVersion::Current().GetBranch());

    SendJsonResponse(
        OnComplete,
        UnrealAgentPrivate::SerializePayload(ResponseObject),
        EHttpServerResponseCodes::Ok
    );
    return true;
}

bool UAgentHttpBridgeSubsystem::HandleHealth(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    if (!IsLoopbackRequest(Request))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Only loopback requests are allowed.\"}"),
            EHttpServerResponseCodes::Forbidden
        );
        return true;
    }

    SendJsonResponse(
        OnComplete,
        TEXT("{\"success\":true,\"message\":\"ok\"}"),
        EHttpServerResponseCodes::Ok
    );
    return true;
}

FString UAgentHttpBridgeSubsystem::ReadRequestBody(const FHttpServerRequest& Request) const
{
    FString BodyString;
    if (Request.Body.Num() > 0)
    {
        FFileHelper::BufferToString(BodyString, Request.Body.GetData(), Request.Body.Num());
    }
    return BodyString;
}

bool UAgentHttpBridgeSubsystem::IsLoopbackRequest(const FHttpServerRequest& Request) const
{
    if (!Request.PeerAddress.IsValid())
    {
        return false;
    }

    const FString Address = Request.PeerAddress->ToString(false);
    return Address == TEXT("127.0.0.1") ||
           Address == TEXT("::1") ||
           Address == TEXT("0:0:0:0:0:0:0:1") ||
           Address.StartsWith(TEXT("127."));
}

void UAgentHttpBridgeSubsystem::SendJsonResponse(
    const FHttpResultCallback& OnComplete,
    const FString& JsonString,
    const EHttpServerResponseCodes StatusCode
) const
{
    TUniquePtr<FHttpServerResponse> Response = FHttpServerResponse::Create(JsonString, TEXT("application/json"));
    Response->Code = StatusCode;
    OnComplete(MoveTemp(Response));
}
