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
#include "HAL/FileManager.h"
#include "HttpPath.h"
#include "HttpServerModule.h"
#include "IHttpRouter.h"
#include "Misc/CommandLine.h"
#include "Misc/EngineVersion.h"
#include "Misc/FileHelper.h"
#include "Misc/Guid.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Misc/ScopeLock.h"
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

static FAgentActionResult ExecuteNamedAction(const FString& ActionName, const TSharedRef<FJsonObject>& Payload, const bool bDryRun)
{
    FAgentActionRequest ActionRequest;
    ActionRequest.ActionName = ActionName;
    ActionRequest.PayloadJson = SerializePayload(Payload);
    ActionRequest.bDryRun = bDryRun;
    return FAgentActionRegistry::Get().Execute(ActionRequest);
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

static void AddStep(TArray<TSharedPtr<FJsonValue>>& Steps, const FString& Id, const FString& Action, const TSharedRef<FJsonObject>& Payload)
{
    TSharedRef<FJsonObject> Step = MakeShared<FJsonObject>();
    Step->SetStringField(TEXT("id"), Id);
    Step->SetStringField(TEXT("action"), Action);
    Step->SetObjectField(TEXT("payload"), Payload);
    Steps.Add(MakeShared<FJsonValueObject>(Step));
}

static TArray<TSharedPtr<FJsonValue>> BuildRecipeCatalog()
{
    TArray<TSharedPtr<FJsonValue>> Out;

    auto MakeInput = [](const TCHAR* Name, const TCHAR* Type, const TCHAR* Description, const bool bRequired, const TCHAR* DefaultValue = nullptr) -> TSharedPtr<FJsonValue>
    {
        TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
        Obj->SetStringField(TEXT("name"), Name);
        Obj->SetStringField(TEXT("type"), Type);
        Obj->SetStringField(TEXT("description"), Description);
        Obj->SetBoolField(TEXT("required"), bRequired);
        if (DefaultValue != nullptr)
        {
            Obj->SetStringField(TEXT("default"), DefaultValue);
        }
        return MakeShared<FJsonValueObject>(Obj);
    };

    auto MakeRecipe = [&Out](const TCHAR* Id, const TCHAR* Description, const TArray<TSharedPtr<FJsonValue>>& Inputs) -> void
    {
        TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
        Obj->SetStringField(TEXT("recipe_id"), Id);
        Obj->SetStringField(TEXT("version"), TEXT("1.0.0"));
        Obj->SetStringField(TEXT("description"), Description);
        Obj->SetArrayField(TEXT("inputs"), Inputs);
        Obj->SetArrayField(
            TEXT("outputs"),
            {
                MakeShared<FJsonValueString>(TEXT("execution.summary")),
                MakeShared<FJsonValueString>(TEXT("execution.steps"))
            });
        Out.Add(MakeShared<FJsonValueObject>(Obj));
    };

    MakeRecipe(
        TEXT("objective_loop_basic_sp"),
        TEXT("Builds a basic single-player objective loop scaffold."),
        {
            MakeInput(TEXT("namespace_root"), TEXT("string"), TEXT("Asset namespace root under /Game."), false, TEXT("/Game/AgentGenerated")),
            MakeInput(TEXT("controller_asset_name"), TEXT("string"), TEXT("Objective controller blueprint name."), false, TEXT("BP_AgentObjectiveController")),
            MakeInput(TEXT("widget_asset_name"), TEXT("string"), TEXT("HUD widget blueprint name."), false, TEXT("WBP_AgentObjectiveHUD")),
            MakeInput(TEXT("objective_count"), TEXT("integer"), TEXT("Number of objective actors to create."), false, TEXT("3"))
        });
    MakeRecipe(
        TEXT("objective_loop_basic_mp_safe"),
        TEXT("Builds an objective loop scaffold with multiplayer-safe variables."),
        {
            MakeInput(TEXT("namespace_root"), TEXT("string"), TEXT("Asset namespace root under /Game."), false, TEXT("/Game/AgentGenerated")),
            MakeInput(TEXT("controller_asset_name"), TEXT("string"), TEXT("Objective controller blueprint name."), false, TEXT("BP_AgentObjectiveController")),
            MakeInput(TEXT("widget_asset_name"), TEXT("string"), TEXT("HUD widget blueprint name."), false, TEXT("WBP_AgentObjectiveHUD")),
            MakeInput(TEXT("objective_count"), TEXT("integer"), TEXT("Number of objective actors to create."), false, TEXT("3"))
        });
    MakeRecipe(
        TEXT("objective_loop_timed_collection_sp"),
        TEXT("Builds a timed collection loop for single-player."),
        {
            MakeInput(TEXT("namespace_root"), TEXT("string"), TEXT("Asset namespace root under /Game."), false, TEXT("/Game/AgentGenerated")),
            MakeInput(TEXT("controller_asset_name"), TEXT("string"), TEXT("Objective controller blueprint name."), false, TEXT("BP_AgentObjectiveController")),
            MakeInput(TEXT("widget_asset_name"), TEXT("string"), TEXT("HUD widget blueprint name."), false, TEXT("WBP_AgentObjectiveHUD")),
            MakeInput(TEXT("objective_count"), TEXT("integer"), TEXT("Number of objective actors to create."), false, TEXT("3"))
        });
    MakeRecipe(
        TEXT("objective_loop_timed_collection_mp_safe"),
        TEXT("Builds a timed collection loop with multiplayer-safe variables."),
        {
            MakeInput(TEXT("namespace_root"), TEXT("string"), TEXT("Asset namespace root under /Game."), false, TEXT("/Game/AgentGenerated")),
            MakeInput(TEXT("controller_asset_name"), TEXT("string"), TEXT("Objective controller blueprint name."), false, TEXT("BP_AgentObjectiveController")),
            MakeInput(TEXT("widget_asset_name"), TEXT("string"), TEXT("HUD widget blueprint name."), false, TEXT("WBP_AgentObjectiveHUD")),
            MakeInput(TEXT("objective_count"), TEXT("integer"), TEXT("Number of objective actors to create."), false, TEXT("3"))
        });
    MakeRecipe(
        TEXT("world_city_block_layout"),
        TEXT("Builds a deterministic city block layout chunk."),
        {
            MakeInput(TEXT("rows"), TEXT("integer"), TEXT("Rows in the city block grid."), false, TEXT("12")),
            MakeInput(TEXT("cols"), TEXT("integer"), TEXT("Columns in the city block grid."), false, TEXT("12")),
            MakeInput(TEXT("spacing"), TEXT("number"), TEXT("World spacing between chunks."), false, TEXT("500.0"))
        });
    MakeRecipe(
        TEXT("world_jump_line_layout"),
        TEXT("Builds a deterministic jump line layout."),
        {
            MakeInput(TEXT("count"), TEXT("integer"), TEXT("Number of jump platforms."), false, TEXT("16")),
            MakeInput(TEXT("start"), TEXT("vector3"), TEXT("Start transform location."), false),
            MakeInput(TEXT("end"), TEXT("vector3"), TEXT("End transform location."), false)
        });
    MakeRecipe(
        TEXT("asset_import_materialize_pack"),
        TEXT("Scaffolded deterministic asset materialization workflow."),
        {
            MakeInput(TEXT("namespace_root"), TEXT("string"), TEXT("Asset namespace root under /Game."), false, TEXT("/Game/AgentGenerated"))
        });

    return Out;
}

static bool BuildPlanFromRecipeRequest(
    const TSharedPtr<FJsonObject>& RequestObject,
    TSharedPtr<FJsonObject>& OutPlanObject,
    FString& OutError
)
{
    OutPlanObject.Reset();
    OutError.Reset();
    if (!RequestObject.IsValid())
    {
        OutError = TEXT("Invalid recipe request object.");
        return false;
    }

    FString RecipeId;
    if (!RequestObject->TryGetStringField(TEXT("recipe_id"), RecipeId) || RecipeId.IsEmpty())
    {
        OutError = TEXT("Missing required field: recipe_id");
        return false;
    }

    bool bDryRun = false;
    bool bStopOnError = true;
    RequestObject->TryGetBoolField(TEXT("dry_run"), bDryRun);
    RequestObject->TryGetBoolField(TEXT("stop_on_error"), bStopOnError);

    FString Profile = TEXT("balanced");
    RequestObject->TryGetStringField(TEXT("profile"), Profile);

    const TSharedPtr<FJsonObject>* InputsPtr = nullptr;
    TSharedPtr<FJsonObject> Inputs = MakeShared<FJsonObject>();
    if (RequestObject->TryGetObjectField(TEXT("inputs"), InputsPtr) && InputsPtr != nullptr && InputsPtr->IsValid())
    {
        Inputs = *InputsPtr;
    }

    FString NamespaceRoot = TEXT("/Game/AgentGenerated");
    Inputs->TryGetStringField(TEXT("namespace_root"), NamespaceRoot);
    if (NamespaceRoot.IsEmpty())
    {
        NamespaceRoot = TEXT("/Game/AgentGenerated");
    }
    const FString GameplayPath = NamespaceRoot / TEXT("Gameplay");
    const FString UiPath = NamespaceRoot / TEXT("UI");
    const FString DataPath = NamespaceRoot / TEXT("Data");

    TArray<TSharedPtr<FJsonValue>> Steps;
    TArray<TSharedPtr<FJsonValue>> CompileBlueprints;

    if (RecipeId == TEXT("objective_loop_basic_sp") || RecipeId == TEXT("objective_loop_basic_mp_safe") ||
        RecipeId == TEXT("objective_loop_timed_collection_sp") || RecipeId == TEXT("objective_loop_timed_collection_mp_safe"))
    {
        FString ControllerAsset = TEXT("BP_AgentObjectiveController");
        Inputs->TryGetStringField(TEXT("controller_asset_name"), ControllerAsset);
        const FString ControllerPath = GameplayPath / ControllerAsset;

        TSharedRef<FJsonObject> CreateController = MakeShared<FJsonObject>();
        CreateController->SetStringField(TEXT("asset_name"), ControllerAsset);
        CreateController->SetStringField(TEXT("package_path"), GameplayPath);
        CreateController->SetStringField(TEXT("parent_class"), TEXT("/Script/Engine.Actor"));
        AddStep(Steps, TEXT("create_controller"), TEXT("create_blueprint"), CreateController);

        TSharedRef<FJsonObject> Progress = MakeShared<FJsonObject>();
        Progress->SetStringField(TEXT("blueprint_path"), ControllerPath);
        AddStep(Steps, TEXT("wire_progress"), TEXT("wire_objective_progress"), Progress);

        TSharedRef<FJsonObject> Score = MakeShared<FJsonObject>();
        Score->SetStringField(TEXT("blueprint_path"), ControllerPath);
        AddStep(Steps, TEXT("create_score"), TEXT("create_score_system"), Score);

        if (RecipeId.Contains(TEXT("timed")))
        {
            TSharedRef<FJsonObject> Timer = MakeShared<FJsonObject>();
            Timer->SetStringField(TEXT("blueprint_path"), ControllerPath);
            AddStep(Steps, TEXT("create_timer"), TEXT("create_timer_system"), Timer);
        }

        if (RecipeId.Contains(TEXT("mp_safe")))
        {
            TSharedRef<FJsonObject> GameModeLogic = MakeShared<FJsonObject>();
            GameModeLogic->SetStringField(TEXT("blueprint_path"), ControllerPath);
            AddStep(Steps, TEXT("game_mode_logic"), TEXT("create_game_mode_logic"), GameModeLogic);
        }

        FString WidgetAsset = TEXT("WBP_AgentObjectiveHUD");
        Inputs->TryGetStringField(TEXT("widget_asset_name"), WidgetAsset);
        TSharedRef<FJsonObject> CreateWidget = MakeShared<FJsonObject>();
        CreateWidget->SetStringField(TEXT("asset_name"), WidgetAsset);
        CreateWidget->SetStringField(TEXT("package_path"), UiPath);
        CreateWidget->SetStringField(TEXT("parent_class"), TEXT("/Script/UMG.UserWidget"));
        AddStep(Steps, TEXT("create_hud_widget"), TEXT("create_widget_blueprint"), CreateWidget);

        int32 ObjectiveCount = 3;
        double ObjectiveCountNumber = static_cast<double>(ObjectiveCount);
        if (Inputs->TryGetNumberField(TEXT("objective_count"), ObjectiveCountNumber))
        {
            ObjectiveCount = static_cast<int32>(ObjectiveCountNumber);
        }
        ObjectiveCount = FMath::Clamp(ObjectiveCount, 1, 50);
        FVector BaseLocation(0.0f, 0.0f, 80.0f);
        if (const TArray<TSharedPtr<FJsonValue>>* BaseLocationArr = nullptr;
            Inputs->TryGetArrayField(TEXT("objective_base_location"), BaseLocationArr) &&
            BaseLocationArr != nullptr && BaseLocationArr->Num() == 3)
        {
            double X = 0.0, Y = 0.0, Z = 0.0;
            if ((*BaseLocationArr)[0]->TryGetNumber(X) && (*BaseLocationArr)[1]->TryGetNumber(Y) && (*BaseLocationArr)[2]->TryGetNumber(Z))
            {
                BaseLocation = FVector(static_cast<float>(X), static_cast<float>(Y), static_cast<float>(Z));
            }
        }

        for (int32 i = 0; i < ObjectiveCount; ++i)
        {
            TSharedRef<FJsonObject> Objective = MakeShared<FJsonObject>();
            Objective->SetStringField(TEXT("actor_label"), FString::Printf(TEXT("Objective_%02d"), i + 1));
            Objective->SetStringField(TEXT("folder_path"), TEXT("AgentGenerated/Objectives"));
            Objective->SetStringField(TEXT("class_path"), TEXT("/Script/Engine.StaticMeshActor"));
            Objective->SetStringField(TEXT("static_mesh_path"), TEXT("/Engine/BasicShapes/Cube.Cube"));
            Objective->SetArrayField(
                TEXT("location"),
                {
                    MakeShared<FJsonValueNumber>(BaseLocation.X + static_cast<float>(i) * 250.0f),
                    MakeShared<FJsonValueNumber>(BaseLocation.Y),
                    MakeShared<FJsonValueNumber>(BaseLocation.Z)
                });
            Objective->SetArrayField(
                TEXT("scale"),
                {
                    MakeShared<FJsonValueNumber>(0.75f),
                    MakeShared<FJsonValueNumber>(0.75f),
                    MakeShared<FJsonValueNumber>(0.75f)
                });
            Objective->SetArrayField(TEXT("tags"), {MakeShared<FJsonValueString>(TEXT("ObjectiveItem"))});
            AddStep(Steps, FString::Printf(TEXT("create_objective_%d"), i + 1), TEXT("create_objective_actor"), Objective);
        }

        CompileBlueprints.Add(MakeShared<FJsonValueString>(ControllerPath));
    }
    else if (RecipeId == TEXT("world_city_block_layout"))
    {
        int32 Rows = 12;
        int32 Cols = 12;
        double Spacing = 500.0;
        double RowsNumber = static_cast<double>(Rows);
        double ColsNumber = static_cast<double>(Cols);
        Inputs->TryGetNumberField(TEXT("rows"), RowsNumber);
        Inputs->TryGetNumberField(TEXT("cols"), ColsNumber);
        Inputs->TryGetNumberField(TEXT("spacing"), Spacing);
        Rows = FMath::Clamp(static_cast<int32>(RowsNumber), 1, 100);
        Cols = FMath::Clamp(static_cast<int32>(ColsNumber), 1, 100);

        TSharedRef<FJsonObject> Chunk = MakeShared<FJsonObject>();
        Chunk->SetStringField(TEXT("folder_path"), TEXT("AgentGenerated/City"));
        Chunk->SetStringField(TEXT("class_path"), TEXT("/Script/Engine.StaticMeshActor"));
        Chunk->SetStringField(TEXT("static_mesh_path"), TEXT("/Engine/BasicShapes/Cube.Cube"));
        Chunk->SetNumberField(TEXT("rows"), Rows);
        Chunk->SetNumberField(TEXT("cols"), Cols);
        Chunk->SetNumberField(TEXT("spacing"), Spacing);
        AddStep(Steps, TEXT("create_city_chunk"), TEXT("create_level_chunk"), Chunk);
    }
    else if (RecipeId == TEXT("world_jump_line_layout"))
    {
        int32 Count = 16;
        double CountNumber = static_cast<double>(Count);
        Inputs->TryGetNumberField(TEXT("count"), CountNumber);
        Count = FMath::Clamp(static_cast<int32>(CountNumber), 1, 200);

        FVector Start(0.0f, 0.0f, 100.0f);
        FVector End(4000.0f, 1200.0f, 600.0f);
        if (const TArray<TSharedPtr<FJsonValue>>* StartArr = nullptr;
            Inputs->TryGetArrayField(TEXT("start"), StartArr) &&
            StartArr != nullptr && StartArr->Num() == 3)
        {
            double X = 0.0;
            double Y = 0.0;
            double Z = 0.0;
            if ((*StartArr)[0]->TryGetNumber(X) && (*StartArr)[1]->TryGetNumber(Y) && (*StartArr)[2]->TryGetNumber(Z))
            {
                Start = FVector(static_cast<float>(X), static_cast<float>(Y), static_cast<float>(Z));
            }
        }
        if (const TArray<TSharedPtr<FJsonValue>>* EndArr = nullptr;
            Inputs->TryGetArrayField(TEXT("end"), EndArr) &&
            EndArr != nullptr && EndArr->Num() == 3)
        {
            double X = 0.0;
            double Y = 0.0;
            double Z = 0.0;
            if ((*EndArr)[0]->TryGetNumber(X) && (*EndArr)[1]->TryGetNumber(Y) && (*EndArr)[2]->TryGetNumber(Z))
            {
                End = FVector(static_cast<float>(X), static_cast<float>(Y), static_cast<float>(Z));
            }
        }

        TSharedRef<FJsonObject> Layout = MakeShared<FJsonObject>();
        Layout->SetArrayField(TEXT("start"), {MakeShared<FJsonValueNumber>(Start.X), MakeShared<FJsonValueNumber>(Start.Y), MakeShared<FJsonValueNumber>(Start.Z)});
        Layout->SetArrayField(TEXT("end"), {MakeShared<FJsonValueNumber>(End.X), MakeShared<FJsonValueNumber>(End.Y), MakeShared<FJsonValueNumber>(End.Z)});
        Layout->SetNumberField(TEXT("count"), Count);
        Layout->SetStringField(TEXT("folder_path"), TEXT("AgentGenerated/JumpLines"));
        Layout->SetStringField(TEXT("class_path"), TEXT("/Script/Engine.StaticMeshActor"));
        Layout->SetStringField(TEXT("static_mesh_path"), TEXT("/Engine/BasicShapes/Cube.Cube"));
        AddStep(Steps, TEXT("create_jump_line"), TEXT("layout_along_spline"), Layout);
    }
    else if (RecipeId == TEXT("asset_import_materialize_pack"))
    {
        TSharedRef<FJsonObject> DataAsset = MakeShared<FJsonObject>();
        DataAsset->SetStringField(TEXT("asset_name"), TEXT("DA_AgentAssetPack"));
        DataAsset->SetStringField(TEXT("package_path"), DataPath);
        DataAsset->SetStringField(TEXT("parent_class"), TEXT("/Script/Engine.PrimaryDataAsset"));
        AddStep(Steps, TEXT("create_data_asset"), TEXT("create_data_asset"), DataAsset);

        TSharedRef<FJsonObject> ValidateSchema = MakeShared<FJsonObject>();
        ValidateSchema->SetArrayField(TEXT("required_fields"), {MakeShared<FJsonValueString>(TEXT("AssetId")), MakeShared<FJsonValueString>(TEXT("DisplayName"))});
        TSharedRef<FJsonObject> RowObject = MakeShared<FJsonObject>();
        RowObject->SetStringField(TEXT("AssetId"), TEXT("pack_001"));
        RowObject->SetStringField(TEXT("DisplayName"), TEXT("Agent Asset Pack"));
        ValidateSchema->SetObjectField(TEXT("row"), RowObject);
        AddStep(Steps, TEXT("validate_schema"), TEXT("validate_data_schema"), ValidateSchema);
    }
    else
    {
        OutError = FString::Printf(TEXT("Unknown recipe_id: %s"), *RecipeId);
        return false;
    }

    TSharedPtr<FJsonObject> Envelope = MakeShared<FJsonObject>();
    Envelope->SetStringField(TEXT("trace_id"), FGuid::NewGuid().ToString(EGuidFormats::DigitsWithHyphensLower));
    Envelope->SetStringField(TEXT("request_id"), FGuid::NewGuid().ToString(EGuidFormats::DigitsWithHyphensLower));
    Envelope->SetStringField(TEXT("profile"), Profile.IsEmpty() ? TEXT("balanced") : Profile);
    Envelope->SetStringField(TEXT("mode"), TEXT("recipe"));
    Envelope->SetStringField(TEXT("goal"), RecipeId);
    Envelope->SetObjectField(TEXT("goal_context"), Inputs.ToSharedRef());

    OutPlanObject = MakeShared<FJsonObject>();
    OutPlanObject->SetStringField(TEXT("plan_id"), FString::Printf(TEXT("recipe-%s-%s"), *RecipeId, *FGuid::NewGuid().ToString(EGuidFormats::Digits)));
    OutPlanObject->SetBoolField(TEXT("dry_run"), bDryRun);
    OutPlanObject->SetBoolField(TEXT("stop_on_error"), bStopOnError);
    OutPlanObject->SetObjectField(TEXT("envelope"), Envelope.ToSharedRef());
    OutPlanObject->SetArrayField(TEXT("steps"), Steps);
    if (CompileBlueprints.Num() > 0)
    {
        OutPlanObject->SetArrayField(TEXT("compile_blueprints"), CompileBlueprints);
    }
    return true;
}

static FString VerbToString(const EHttpServerRequestVerbs Verb)
{
    switch (Verb)
    {
    case EHttpServerRequestVerbs::VERB_GET:
        return TEXT("GET");
    case EHttpServerRequestVerbs::VERB_POST:
        return TEXT("POST");
    case EHttpServerRequestVerbs::VERB_PUT:
        return TEXT("PUT");
    case EHttpServerRequestVerbs::VERB_PATCH:
        return TEXT("PATCH");
    case EHttpServerRequestVerbs::VERB_DELETE:
        return TEXT("DELETE");
    case EHttpServerRequestVerbs::VERB_OPTIONS:
        return TEXT("OPTIONS");
    default:
        return TEXT("UNKNOWN");
    }
}

static FString TruncateForTrace(const FString& Input, const int32 MaxChars = 8192)
{
    if (Input.Len() <= MaxChars)
    {
        return Input;
    }
    return Input.Left(MaxChars) + TEXT("...(truncated)");
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
    DebugTraceFilePath = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("UnrealAgent"), TEXT("debug_trace.jsonl"));
    IFileManager::Get().MakeDirectory(*FPaths::GetPath(DebugTraceFilePath), true);

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

    RecipesRouteHandle = HttpRouter->BindRoute(
        FHttpPath(TEXT("/unreal-agent/v1/recipes")),
        EHttpServerRequestVerbs::VERB_GET,
        FHttpRequestHandler::CreateUObject(this, &UAgentHttpBridgeSubsystem::HandleRecipes)
    );

    RunRecipeRouteHandle = HttpRouter->BindRoute(
        FHttpPath(TEXT("/unreal-agent/v1/run-recipe")),
        EHttpServerRequestVerbs::VERB_POST,
        FHttpRequestHandler::CreateUObject(this, &UAgentHttpBridgeSubsystem::HandleRunRecipe)
    );

    ValidateRecipeRouteHandle = HttpRouter->BindRoute(
        FHttpPath(TEXT("/unreal-agent/v1/validate-recipe")),
        EHttpServerRequestVerbs::VERB_POST,
        FHttpRequestHandler::CreateUObject(this, &UAgentHttpBridgeSubsystem::HandleValidateRecipe)
    );

    RunScenarioRouteHandle = HttpRouter->BindRoute(
        FHttpPath(TEXT("/unreal-agent/v1/run-scenario")),
        EHttpServerRequestVerbs::VERB_POST,
        FHttpRequestHandler::CreateUObject(this, &UAgentHttpBridgeSubsystem::HandleRunScenario)
    );

    DebugTracesRouteHandle = HttpRouter->BindRoute(
        FHttpPath(TEXT("/unreal-agent/v1/debug/traces")),
        EHttpServerRequestVerbs::VERB_GET,
        FHttpRequestHandler::CreateUObject(this, &UAgentHttpBridgeSubsystem::HandleDebugTraces)
    );

    DebugClearRouteHandle = HttpRouter->BindRoute(
        FHttpPath(TEXT("/unreal-agent/v1/debug/clear")),
        EHttpServerRequestVerbs::VERB_POST,
        FHttpRequestHandler::CreateUObject(this, &UAgentHttpBridgeSubsystem::HandleDebugClear)
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
        HttpRouter->UnbindRoute(RecipesRouteHandle);
        HttpRouter->UnbindRoute(RunRecipeRouteHandle);
        HttpRouter->UnbindRoute(ValidateRecipeRouteHandle);
        HttpRouter->UnbindRoute(RunScenarioRouteHandle);
        HttpRouter->UnbindRoute(DebugTracesRouteHandle);
        HttpRouter->UnbindRoute(DebugClearRouteHandle);
    }

    HttpRouter.Reset();

    Super::Deinitialize();
}

bool UAgentHttpBridgeSubsystem::HandleExecute(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    const double StartedAt = FPlatformTime::Seconds();
    const FString BodyJson = ReadRequestBody(Request);

    if (!IsLoopbackRequest(Request))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Only loopback requests are allowed.\"}"),
            EHttpServerResponseCodes::Forbidden
        );
        RecordTrace(
            TEXT("/unreal-agent/v1/execute"),
            Request.Verb,
            BodyJson,
            false,
            TEXT("FORBIDDEN"),
            TEXT("Only loopback requests are allowed."),
            EHttpServerResponseCodes::Forbidden,
            (FPlatformTime::Seconds() - StartedAt) * 1000.0
        );
        return true;
    }

    TSharedPtr<FJsonObject> JsonRequest;
    FString ParseError;
    if (!UnrealAgentPrivate::ParseJsonObject(BodyJson, JsonRequest, ParseError))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Invalid JSON body. Expected object with action and payload.\"}"),
            EHttpServerResponseCodes::BadRequest
        );
        RecordTrace(
            TEXT("/unreal-agent/v1/execute"),
            Request.Verb,
            BodyJson,
            false,
            TEXT("INVALID_JSON"),
            ParseError,
            EHttpServerResponseCodes::BadRequest,
            (FPlatformTime::Seconds() - StartedAt) * 1000.0
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
        RecordTrace(
            TEXT("/unreal-agent/v1/execute"),
            Request.Verb,
            BodyJson,
            false,
            TEXT("INVALID_REQUEST"),
            ParseError,
            EHttpServerResponseCodes::BadRequest,
            (FPlatformTime::Seconds() - StartedAt) * 1000.0
        );
        return true;
    }

    const FAgentActionResult Result = FAgentActionRegistry::Get().Execute(ActionRequest);
    const FString ResponseJson = UnrealAgentPrivate::SerializeActionResult(Result);
    const EHttpServerResponseCodes StatusCode = Result.bSuccess ? EHttpServerResponseCodes::Ok : EHttpServerResponseCodes::BadRequest;
    SendJsonResponse(
        OnComplete,
        ResponseJson,
        StatusCode
    );
    TSharedPtr<FJsonObject> Extra = MakeShared<FJsonObject>();
    Extra->SetStringField(TEXT("action"), ActionRequest.ActionName);
    Extra->SetBoolField(TEXT("dry_run"), ActionRequest.bDryRun);
    RecordTrace(
        TEXT("/unreal-agent/v1/execute"),
        Request.Verb,
        BodyJson,
        Result.bSuccess,
        UnrealAgentPrivate::NormalizeErrorCode(Result),
        Result.Message,
        StatusCode,
        (FPlatformTime::Seconds() - StartedAt) * 1000.0,
        Extra
    );
    return true;
}

bool UAgentHttpBridgeSubsystem::HandleRunPlan(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    const double StartedAt = FPlatformTime::Seconds();
    const FString BodyJson = ReadRequestBody(Request);

    if (!IsLoopbackRequest(Request))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Only loopback requests are allowed.\"}"),
            EHttpServerResponseCodes::Forbidden
        );
        RecordTrace(
            TEXT("/unreal-agent/v1/run-plan"),
            Request.Verb,
            BodyJson,
            false,
            TEXT("FORBIDDEN"),
            TEXT("Only loopback requests are allowed."),
            EHttpServerResponseCodes::Forbidden,
            (FPlatformTime::Seconds() - StartedAt) * 1000.0
        );
        return true;
    }

    TSharedPtr<FJsonObject> JsonRequest;
    FString ParseError;
    if (!UnrealAgentPrivate::ParseJsonObject(BodyJson, JsonRequest, ParseError))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Invalid JSON body. Expected plan object.\"}"),
            EHttpServerResponseCodes::BadRequest
        );
        RecordTrace(
            TEXT("/unreal-agent/v1/run-plan"),
            Request.Verb,
            BodyJson,
            false,
            TEXT("INVALID_JSON"),
            ParseError,
            EHttpServerResponseCodes::BadRequest,
            (FPlatformTime::Seconds() - StartedAt) * 1000.0
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
    const bool bSuccess = ResponseObject->GetBoolField(TEXT("success"));
    const FString Message = ResponseObject->GetStringField(TEXT("message"));
    TSharedPtr<FJsonObject> Extra = MakeShared<FJsonObject>();
    const TSharedPtr<FJsonObject>* SummaryObject = nullptr;
    if (ResponseObject->TryGetObjectField(TEXT("summary"), SummaryObject) && SummaryObject != nullptr && SummaryObject->IsValid())
    {
        Extra->SetObjectField(TEXT("summary"), (*SummaryObject).ToSharedRef());
    }
    Extra->SetStringField(TEXT("plan_id"), ResponseObject->GetStringField(TEXT("plan_id")));
    RecordTrace(
        TEXT("/unreal-agent/v1/run-plan"),
        Request.Verb,
        BodyJson,
        bSuccess,
        bSuccess ? TEXT("OK") : TEXT("PLAN_FAILED"),
        Message,
        StatusCode,
        (FPlatformTime::Seconds() - StartedAt) * 1000.0,
        Extra
    );
    return true;
}

bool UAgentHttpBridgeSubsystem::HandleRunGoal(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    const double StartedAt = FPlatformTime::Seconds();
    const FString BodyJson = ReadRequestBody(Request);

    if (!IsLoopbackRequest(Request))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Only loopback requests are allowed.\"}"),
            EHttpServerResponseCodes::Forbidden
        );
        RecordTrace(
            TEXT("/unreal-agent/v1/run-goal"),
            Request.Verb,
            BodyJson,
            false,
            TEXT("FORBIDDEN"),
            TEXT("Only loopback requests are allowed."),
            EHttpServerResponseCodes::Forbidden,
            (FPlatformTime::Seconds() - StartedAt) * 1000.0
        );
        return true;
    }

    TSharedPtr<FJsonObject> GoalRequest;
    FString ParseError;
    if (!UnrealAgentPrivate::ParseJsonObject(BodyJson, GoalRequest, ParseError))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Invalid JSON body. Expected goal object.\"}"),
            EHttpServerResponseCodes::BadRequest
        );
        RecordTrace(
            TEXT("/unreal-agent/v1/run-goal"),
            Request.Verb,
            BodyJson,
            false,
            TEXT("INVALID_JSON"),
            ParseError,
            EHttpServerResponseCodes::BadRequest,
            (FPlatformTime::Seconds() - StartedAt) * 1000.0
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
        RecordTrace(
            TEXT("/unreal-agent/v1/run-goal"),
            Request.Verb,
            BodyJson,
            false,
            TEXT("GOAL_PLAN_ERROR"),
            PlanError,
            EHttpServerResponseCodes::BadRequest,
            (FPlatformTime::Seconds() - StartedAt) * 1000.0
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
    TSharedPtr<FJsonObject> Extra = MakeShared<FJsonObject>();
    Extra->SetStringField(TEXT("goal"), GoalText);
    const TSharedPtr<FJsonObject>* ExecSummary = nullptr;
    if (ExecutionResult->TryGetObjectField(TEXT("summary"), ExecSummary) && ExecSummary != nullptr && ExecSummary->IsValid())
    {
        Extra->SetObjectField(TEXT("execution_summary"), (*ExecSummary).ToSharedRef());
    }
    RecordTrace(
        TEXT("/unreal-agent/v1/run-goal"),
        Request.Verb,
        BodyJson,
        ResponseObject->GetBoolField(TEXT("success")),
        ResponseObject->GetBoolField(TEXT("success")) ? TEXT("OK") : TEXT("GOAL_FAILED"),
        ResponseObject->GetStringField(TEXT("message")),
        ExecutionStatusCode,
        (FPlatformTime::Seconds() - StartedAt) * 1000.0,
        Extra
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

bool UAgentHttpBridgeSubsystem::HandleRecipes(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
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

    TSharedRef<FJsonObject> Response = MakeShared<FJsonObject>();
    Response->SetBoolField(TEXT("success"), true);
    Response->SetArrayField(TEXT("recipes"), UnrealAgentPrivate::BuildRecipeCatalog());
    SendJsonResponse(OnComplete, UnrealAgentPrivate::SerializePayload(Response), EHttpServerResponseCodes::Ok);
    return true;
}

bool UAgentHttpBridgeSubsystem::HandleRunRecipe(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    const double StartedAt = FPlatformTime::Seconds();
    const FString BodyJson = ReadRequestBody(Request);

    if (!IsLoopbackRequest(Request))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Only loopback requests are allowed.\"}"),
            EHttpServerResponseCodes::Forbidden
        );
        RecordTrace(
            TEXT("/unreal-agent/v1/run-recipe"),
            Request.Verb,
            BodyJson,
            false,
            TEXT("FORBIDDEN"),
            TEXT("Only loopback requests are allowed."),
            EHttpServerResponseCodes::Forbidden,
            (FPlatformTime::Seconds() - StartedAt) * 1000.0
        );
        return true;
    }

    TSharedPtr<FJsonObject> JsonRequest;
    FString ParseError;
    if (!UnrealAgentPrivate::ParseJsonObject(BodyJson, JsonRequest, ParseError))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Invalid JSON body. Expected recipe request object.\"}"),
            EHttpServerResponseCodes::BadRequest
        );
        RecordTrace(
            TEXT("/unreal-agent/v1/run-recipe"),
            Request.Verb,
            BodyJson,
            false,
            TEXT("INVALID_JSON"),
            ParseError,
            EHttpServerResponseCodes::BadRequest,
            (FPlatformTime::Seconds() - StartedAt) * 1000.0
        );
        return true;
    }

    TSharedPtr<FJsonObject> PlanObject;
    FString PlanError;
    if (!UnrealAgentPrivate::BuildPlanFromRecipeRequest(JsonRequest, PlanObject, PlanError))
    {
        TSharedRef<FJsonObject> Error = MakeShared<FJsonObject>();
        Error->SetBoolField(TEXT("success"), false);
        Error->SetStringField(TEXT("message"), PlanError);
        SendJsonResponse(OnComplete, UnrealAgentPrivate::SerializePayload(Error), EHttpServerResponseCodes::BadRequest);
        RecordTrace(
            TEXT("/unreal-agent/v1/run-recipe"),
            Request.Verb,
            BodyJson,
            false,
            TEXT("RECIPE_BUILD_FAILED"),
            PlanError,
            EHttpServerResponseCodes::BadRequest,
            (FPlatformTime::Seconds() - StartedAt) * 1000.0
        );
        return true;
    }

    TSharedRef<FJsonObject> Execution = MakeShared<FJsonObject>();
    EHttpServerResponseCodes StatusCode = EHttpServerResponseCodes::Ok;
    UnrealAgentPrivate::ExecutePlanRequest(PlanObject, Execution, StatusCode);

    TSharedRef<FJsonObject> Response = MakeShared<FJsonObject>();
    Response->SetBoolField(TEXT("success"), Execution->GetBoolField(TEXT("success")));
    Response->SetStringField(TEXT("message"), Execution->GetStringField(TEXT("message")));
    Response->SetObjectField(TEXT("plan"), PlanObject.ToSharedRef());
    Response->SetObjectField(TEXT("execution"), Execution);

    SendJsonResponse(OnComplete, UnrealAgentPrivate::SerializePayload(Response), StatusCode);
    RecordTrace(
        TEXT("/unreal-agent/v1/run-recipe"),
        Request.Verb,
        BodyJson,
        Response->GetBoolField(TEXT("success")),
        Response->GetBoolField(TEXT("success")) ? TEXT("OK") : TEXT("RECIPE_FAILED"),
        Response->GetStringField(TEXT("message")),
        StatusCode,
        (FPlatformTime::Seconds() - StartedAt) * 1000.0
    );
    return true;
}

bool UAgentHttpBridgeSubsystem::HandleValidateRecipe(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    const double StartedAt = FPlatformTime::Seconds();
    const FString BodyJson = ReadRequestBody(Request);

    if (!IsLoopbackRequest(Request))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Only loopback requests are allowed.\"}"),
            EHttpServerResponseCodes::Forbidden
        );
        RecordTrace(
            TEXT("/unreal-agent/v1/validate-recipe"),
            Request.Verb,
            BodyJson,
            false,
            TEXT("FORBIDDEN"),
            TEXT("Only loopback requests are allowed."),
            EHttpServerResponseCodes::Forbidden,
            (FPlatformTime::Seconds() - StartedAt) * 1000.0
        );
        return true;
    }

    TSharedPtr<FJsonObject> JsonRequest;
    FString ParseError;
    if (!UnrealAgentPrivate::ParseJsonObject(BodyJson, JsonRequest, ParseError))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Invalid JSON body. Expected recipe request object.\"}"),
            EHttpServerResponseCodes::BadRequest
        );
        RecordTrace(
            TEXT("/unreal-agent/v1/validate-recipe"),
            Request.Verb,
            BodyJson,
            false,
            TEXT("INVALID_JSON"),
            ParseError,
            EHttpServerResponseCodes::BadRequest,
            (FPlatformTime::Seconds() - StartedAt) * 1000.0
        );
        return true;
    }

    JsonRequest->SetBoolField(TEXT("dry_run"), true);
    TSharedPtr<FJsonObject> PlanObject;
    FString PlanError;
    if (!UnrealAgentPrivate::BuildPlanFromRecipeRequest(JsonRequest, PlanObject, PlanError))
    {
        TSharedRef<FJsonObject> Error = MakeShared<FJsonObject>();
        Error->SetBoolField(TEXT("success"), false);
        Error->SetStringField(TEXT("message"), PlanError);
        SendJsonResponse(OnComplete, UnrealAgentPrivate::SerializePayload(Error), EHttpServerResponseCodes::BadRequest);
        RecordTrace(
            TEXT("/unreal-agent/v1/validate-recipe"),
            Request.Verb,
            BodyJson,
            false,
            TEXT("RECIPE_BUILD_FAILED"),
            PlanError,
            EHttpServerResponseCodes::BadRequest,
            (FPlatformTime::Seconds() - StartedAt) * 1000.0
        );
        return true;
    }

    TSharedRef<FJsonObject> Execution = MakeShared<FJsonObject>();
    EHttpServerResponseCodes StatusCode = EHttpServerResponseCodes::Ok;
    UnrealAgentPrivate::ExecutePlanRequest(PlanObject, Execution, StatusCode);

    TSharedRef<FJsonObject> Response = MakeShared<FJsonObject>();
    Response->SetBoolField(TEXT("success"), Execution->GetBoolField(TEXT("success")));
    Response->SetStringField(TEXT("message"), Execution->GetStringField(TEXT("message")));
    Response->SetBoolField(TEXT("validation_only"), true);
    Response->SetObjectField(TEXT("plan"), PlanObject.ToSharedRef());
    Response->SetObjectField(TEXT("execution"), Execution);
    SendJsonResponse(OnComplete, UnrealAgentPrivate::SerializePayload(Response), StatusCode);
    RecordTrace(
        TEXT("/unreal-agent/v1/validate-recipe"),
        Request.Verb,
        BodyJson,
        Response->GetBoolField(TEXT("success")),
        Response->GetBoolField(TEXT("success")) ? TEXT("OK") : TEXT("VALIDATION_FAILED"),
        Response->GetStringField(TEXT("message")),
        StatusCode,
        (FPlatformTime::Seconds() - StartedAt) * 1000.0
    );
    return true;
}

bool UAgentHttpBridgeSubsystem::HandleRunScenario(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    const double StartedAt = FPlatformTime::Seconds();
    const FString BodyJson = ReadRequestBody(Request);

    if (!IsLoopbackRequest(Request))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Only loopback requests are allowed.\"}"),
            EHttpServerResponseCodes::Forbidden
        );
        RecordTrace(
            TEXT("/unreal-agent/v1/run-scenario"),
            Request.Verb,
            BodyJson,
            false,
            TEXT("FORBIDDEN"),
            TEXT("Only loopback requests are allowed."),
            EHttpServerResponseCodes::Forbidden,
            (FPlatformTime::Seconds() - StartedAt) * 1000.0
        );
        return true;
    }

    TSharedPtr<FJsonObject> JsonRequest;
    FString ParseError;
    if (!UnrealAgentPrivate::ParseJsonObject(BodyJson, JsonRequest, ParseError))
    {
        SendJsonResponse(
            OnComplete,
            TEXT("{\"success\":false,\"message\":\"Invalid JSON body. Expected scenario request object.\"}"),
            EHttpServerResponseCodes::BadRequest
        );
        RecordTrace(
            TEXT("/unreal-agent/v1/run-scenario"),
            Request.Verb,
            BodyJson,
            false,
            TEXT("INVALID_JSON"),
            ParseError,
            EHttpServerResponseCodes::BadRequest,
            (FPlatformTime::Seconds() - StartedAt) * 1000.0
        );
        return true;
    }

    const TArray<TSharedPtr<FJsonValue>>* Assertions = nullptr;
    if (!JsonRequest->TryGetArrayField(TEXT("assertions"), Assertions) || Assertions == nullptr || Assertions->Num() == 0)
    {
        TSharedRef<FJsonObject> Error = MakeShared<FJsonObject>();
        Error->SetBoolField(TEXT("success"), false);
        Error->SetStringField(TEXT("message"), TEXT("run-scenario requires assertions[]"));
        SendJsonResponse(OnComplete, UnrealAgentPrivate::SerializePayload(Error), EHttpServerResponseCodes::BadRequest);
        RecordTrace(
            TEXT("/unreal-agent/v1/run-scenario"),
            Request.Verb,
            BodyJson,
            false,
            TEXT("MISSING_FIELD"),
            TEXT("run-scenario requires assertions[]"),
            EHttpServerResponseCodes::BadRequest,
            (FPlatformTime::Seconds() - StartedAt) * 1000.0
        );
        return true;
    }

    TSharedRef<FJsonObject> ScenarioPayload = MakeShared<FJsonObject>();
    ScenarioPayload->SetArrayField(TEXT("assertions"), *Assertions);
    bool bDryRun = false;
    JsonRequest->TryGetBoolField(TEXT("dry_run"), bDryRun);
    FAgentActionResult ScenarioResult = UnrealAgentPrivate::ExecuteNamedAction(TEXT("run_pie_scenario"), ScenarioPayload, bDryRun);

    const FString ResponseJson = UnrealAgentPrivate::SerializeActionResult(ScenarioResult);
    const EHttpServerResponseCodes StatusCode = ScenarioResult.bSuccess ? EHttpServerResponseCodes::Ok : EHttpServerResponseCodes::BadRequest;
    SendJsonResponse(
        OnComplete,
        ResponseJson,
        StatusCode
    );
    RecordTrace(
        TEXT("/unreal-agent/v1/run-scenario"),
        Request.Verb,
        BodyJson,
        ScenarioResult.bSuccess,
        UnrealAgentPrivate::NormalizeErrorCode(ScenarioResult),
        ScenarioResult.Message,
        StatusCode,
        (FPlatformTime::Seconds() - StartedAt) * 1000.0
    );
    return true;
}

bool UAgentHttpBridgeSubsystem::HandleDebugTraces(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
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

    int32 Limit = 50;
    if (const FString* LimitParam = Request.QueryParams.Find(TEXT("limit")))
    {
        Limit = FMath::Clamp(FCString::Atoi(**LimitParam), 1, 500);
    }

    FString Filter;
    if (const FString* FilterParam = Request.QueryParams.Find(TEXT("filter")))
    {
        Filter = FilterParam->ToLower();
    }

    TArray<TSharedPtr<FJsonValue>> Selected;
    {
        FScopeLock Lock(&DebugTraceMutex);
        for (int32 Index = DebugTraceEntries.Num() - 1; Index >= 0 && Selected.Num() < Limit; --Index)
        {
            const TSharedPtr<FJsonValue>& Value = DebugTraceEntries[Index];
            const TSharedPtr<FJsonObject> Obj = Value.IsValid() ? Value->AsObject() : nullptr;
            if (!Obj.IsValid())
            {
                continue;
            }

            if (!Filter.IsEmpty())
            {
                FString Route = Obj->GetStringField(TEXT("route")).ToLower();
                FString Message = Obj->GetStringField(TEXT("message")).ToLower();
                FString ErrorCode = Obj->GetStringField(TEXT("error_code")).ToLower();
                if (!Route.Contains(Filter) && !Message.Contains(Filter) && !ErrorCode.Contains(Filter))
                {
                    continue;
                }
            }

            Selected.Add(Value);
        }
    }

    TSharedRef<FJsonObject> Response = MakeShared<FJsonObject>();
    Response->SetBoolField(TEXT("success"), true);
    Response->SetNumberField(TEXT("count"), Selected.Num());
    Response->SetNumberField(TEXT("limit"), Limit);
    Response->SetStringField(TEXT("trace_file"), DebugTraceFilePath);
    Response->SetArrayField(TEXT("traces"), Selected);
    SendJsonResponse(
        OnComplete,
        UnrealAgentPrivate::SerializePayload(Response),
        EHttpServerResponseCodes::Ok
    );
    return true;
}

bool UAgentHttpBridgeSubsystem::HandleDebugClear(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
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

    {
        FScopeLock Lock(&DebugTraceMutex);
        DebugTraceEntries.Reset();
    }
    IFileManager::Get().Delete(*DebugTraceFilePath, false, true, true);

    SendJsonResponse(
        OnComplete,
        TEXT("{\"success\":true,\"message\":\"Debug traces cleared.\"}"),
        EHttpServerResponseCodes::Ok
    );
    return true;
}

void UAgentHttpBridgeSubsystem::RecordTrace(
    const FString& Route,
    const EHttpServerRequestVerbs Verb,
    const FString& RequestBody,
    const bool bSuccess,
    const FString& ErrorCode,
    const FString& Message,
    const EHttpServerResponseCodes StatusCode,
    const double DurationMs,
    const TSharedPtr<FJsonObject>& Extra
)
{
    TSharedRef<FJsonObject> Trace = MakeShared<FJsonObject>();
    Trace->SetStringField(TEXT("trace_id"), FGuid::NewGuid().ToString(EGuidFormats::DigitsWithHyphensLower));
    Trace->SetStringField(TEXT("timestamp_utc"), FDateTime::UtcNow().ToIso8601());
    Trace->SetStringField(TEXT("route"), Route);
    Trace->SetStringField(TEXT("verb"), UnrealAgentPrivate::VerbToString(Verb));
    Trace->SetBoolField(TEXT("success"), bSuccess);
    Trace->SetStringField(TEXT("error_code"), ErrorCode);
    Trace->SetStringField(TEXT("message"), Message);
    Trace->SetNumberField(TEXT("status_code"), static_cast<int32>(StatusCode));
    Trace->SetNumberField(TEXT("duration_ms"), DurationMs);
    Trace->SetStringField(TEXT("request_body"), UnrealAgentPrivate::TruncateForTrace(RequestBody));

    if (Extra.IsValid())
    {
        Trace->SetObjectField(TEXT("extra"), Extra.ToSharedRef());
    }

    {
        FScopeLock Lock(&DebugTraceMutex);
        DebugTraceEntries.Add(MakeShared<FJsonValueObject>(Trace));
        if (DebugTraceEntries.Num() > DebugTraceMaxEntries)
        {
            const int32 Overflow = DebugTraceEntries.Num() - DebugTraceMaxEntries;
            DebugTraceEntries.RemoveAt(0, Overflow);
        }
    }

    AppendTraceToFile(Trace);
}

void UAgentHttpBridgeSubsystem::AppendTraceToFile(const TSharedRef<FJsonObject>& TraceObject)
{
    const FString Line = UnrealAgentPrivate::SerializePayload(TraceObject) + TEXT("\n");
    FFileHelper::SaveStringToFile(Line, *DebugTraceFilePath, FFileHelper::EEncodingOptions::AutoDetect, &IFileManager::Get(), FILEWRITE_Append);
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
