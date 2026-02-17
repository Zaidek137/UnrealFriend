#include "Agent/Actions/AutomationCompositeAction.h"

#include "Agent/AgentActionRegistry.h"
#include "Agent/AgentJsonUtils.h"
#include "AssetToolsModule.h"
#include "AssetRegistry/IAssetRegistry.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Animation/AnimBlueprint.h"
#include "AnimStateEntryNode.h"
#include "AnimStateNode.h"
#include "AnimStateTransitionNode.h"
#include "AnimationStateMachineGraph.h"
#include "BehaviorTree/BehaviorTree.h"
#include "BehaviorTree/BTCompositeNode.h"
#include "WidgetBlueprint.h"
#include "Blueprint/WidgetTree.h"
#include "Components/ActorComponent.h"
#include "Components/Border.h"
#include "Components/Button.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/HorizontalBox.h"
#include "Components/HorizontalBoxSlot.h"
#include "Components/Image.h"
#include "Components/Overlay.h"
#include "Components/OverlaySlot.h"
#include "Components/PanelWidget.h"
#include "Components/ProgressBar.h"
#include "Components/RichTextBlock.h"
#include "Components/ScrollBox.h"
#include "Components/SizeBox.h"
#include "Components/TextBlock.h"
#include "Components/UniformGridPanel.h"
#include "Components/UniformGridSlot.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"
#include "Components/WrapBox.h"
#include "Components/WrapBoxSlot.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraphSchema_K2.h"
#include "EdGraphSchema_K2_Actions.h"
#include "Editor.h"
#include "Engine/Engine.h"
#include "Engine/SCS_Node.h"
#include "Engine/SimpleConstructionScript.h"
#include "Engine/GameViewportClient.h"
#include "Engine/Level.h"
#include "Engine/Blueprint.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "EnvironmentQuery/EnvQuery.h"
#include "EnvironmentQuery/EnvQueryOption.h"
#include "GameFramework/Actor.h"
#include "HAL/FileManager.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "K2Node_CallFunction.h"
#include "K2Node_ComponentBoundEvent.h"
#include "K2Node_CustomEvent.h"
#include "K2Node_IfThenElse.h"
#include "Kismet/KismetSystemLibrary.h"
#include "LevelSequence.h"
#include "Materials/Material.h"
#include "Materials/MaterialExpression.h"
#include "MaterialExpressionIO.h"
#include "Materials/MaterialExpressionConstant.h"
#include "Materials/MaterialExpressionConstant2Vector.h"
#include "Materials/MaterialExpressionConstant3Vector.h"
#include "Materials/MaterialExpressionConstant4Vector.h"
#include "Materials/MaterialExpressionTextureSample.h"
#include "Math/UnrealMathUtility.h"
#include "MovieScene.h"
#include "Tracks/MovieSceneFloatTrack.h"
#include "Sections/MovieSceneFloatSection.h"
#include "Channels/MovieSceneFloatChannel.h"
#include "Curves/RichCurve.h"
#include "Misc/DateTime.h"
#include "ObjectTools.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "NiagaraEmitter.h"
#include "NiagaraEmitterHandle.h"
#include "NiagaraSystem.h"
#include "NiagaraSystemEditorData.h"
#include "NiagaraUserRedirectionParameterStore.h"
#include "ScopedTransaction.h"
#include "Serialization/JsonTypes.h"
#include "Styling/SlateColor.h"
#include "UnrealClient.h"
#include "UObject/Field.h"
#include "UObject/Package.h"
#include "UObject/UnrealType.h"
#include "Factories/Factory.h"

namespace UnrealAgentPrivate
{
static FAgentActionResult HandleBatchSpawnActors(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);
static FAgentActionResult HandleLayoutAlongSpline(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);
static FAgentActionResult HandleCreateLevelChunk(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);
static FAgentActionResult HandleClearMapLayout(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);
static FAgentActionResult HandleCreateBehaviorTreeAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);
static FAgentActionResult HandleEditBehaviorTreeAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);
static FAgentActionResult HandleCreateBlackboardDataAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);
static FAgentActionResult HandleEditBlackboardDataAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);
static FAgentActionResult HandleCreateEQSQueryAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);
static FAgentActionResult HandleEditEQSQueryAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);
static FAgentActionResult HandleCreateAnimBlueprintAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);
static FAgentActionResult HandleEditAnimBlueprintStateMachine(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);
static FAgentActionResult HandleCreateMaterialAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);
static FAgentActionResult HandleEditMaterialAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);
static FAgentActionResult HandleCreateNiagaraSystemAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);
static FAgentActionResult HandleEditNiagaraSystemGraph(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);
static FAgentActionResult HandleCreateLevelSequenceAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);
static FAgentActionResult HandleEditLevelSequenceAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload);

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

static bool ReadVector2Field(const TSharedPtr<FJsonObject>& Payload, const FString& Field, FVector2D& OutVector)
{
    const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
    if (!Payload.IsValid() || !Payload->TryGetArrayField(Field, Arr) || Arr == nullptr || Arr->Num() != 2)
    {
        return false;
    }
    double X = 0.0;
    double Y = 0.0;
    if (!(*Arr)[0].IsValid() || !(*Arr)[1].IsValid())
    {
        return false;
    }
    if (!(*Arr)[0]->TryGetNumber(X) || !(*Arr)[1]->TryGetNumber(Y))
    {
        return false;
    }
    OutVector = FVector2D(static_cast<float>(X), static_cast<float>(Y));
    return true;
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

static UClass* ResolveClassByPath(const FString& ClassPath)
{
    if (ClassPath.IsEmpty())
    {
        return nullptr;
    }
    UClass* LoadedClass = FindObject<UClass>(nullptr, *ClassPath);
    if (LoadedClass == nullptr)
    {
        LoadedClass = LoadObject<UClass>(nullptr, *ClassPath);
    }
    return LoadedClass;
}

static UObject* ResolveAssetObject(const FString& AssetPath)
{
    if (AssetPath.IsEmpty())
    {
        return nullptr;
    }
    UObject* Obj = FindObject<UObject>(nullptr, *AssetPath);
    if (Obj == nullptr)
    {
        Obj = LoadObject<UObject>(nullptr, *AssetPath);
    }
    return Obj;
}

static FAgentActionResult CreateNativeAssetByClassPath(
    const FAgentActionRequest& Request,
    const FString& InAssetName,
    const FString& InPackagePath,
    const FString& AssetClassPath,
    const FString& FactoryClassPath,
    const FString& FactoryModuleName)
{
    FString AssetName = ObjectTools::SanitizeObjectName(InAssetName);
    FString PackagePath = InPackagePath;

    if (AssetName.IsEmpty())
    {
        return {false, TEXT("asset_name is empty after sanitization."), TEXT(""), TEXT("INVALID_FIELD")};
    }
    if (!PackagePath.StartsWith(TEXT("/Game")))
    {
        return {false, TEXT("package_path must start with /Game."), TEXT(""), TEXT("INVALID_PATH")};
    }
    if (!FPackageName::IsValidLongPackageName(PackagePath))
    {
        return {false, TEXT("package_path is not a valid long package name."), TEXT(""), TEXT("INVALID_PATH")};
    }

    UClass* AssetClass = ResolveClassByPath(AssetClassPath);
    if (AssetClass == nullptr)
    {
        return {false, FString::Printf(TEXT("Failed to resolve asset class: %s"), *AssetClassPath), TEXT(""), TEXT("ASSET_CLASS_NOT_FOUND")};
    }

    UFactory* Factory = nullptr;
    if (!FactoryClassPath.IsEmpty())
    {
        if (!FactoryModuleName.IsEmpty() && !FModuleManager::Get().IsModuleLoaded(*FactoryModuleName))
        {
            FModuleManager::Get().LoadModule(*FactoryModuleName);
        }
        UClass* FactoryClass = ResolveClassByPath(FactoryClassPath);
        if (FactoryClass == nullptr)
        {
            return {false, FString::Printf(TEXT("Failed to resolve factory class: %s"), *FactoryClassPath), TEXT(""), TEXT("FACTORY_CLASS_NOT_FOUND")};
        }
        UObject* FactoryObj = NewObject<UObject>(GetTransientPackage(), FactoryClass);
        Factory = Cast<UFactory>(FactoryObj);
        if (Factory == nullptr)
        {
            return {false, FString::Printf(TEXT("Factory class is not a UFactory: %s"), *FactoryClassPath), TEXT(""), TEXT("INVALID_FACTORY_CLASS")};
        }
    }

    if (Request.bDryRun)
    {
        TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
        Out->SetBoolField(TEXT("native"), true);
        Out->SetBoolField(TEXT("dry_run"), true);
        Out->SetStringField(TEXT("asset_name"), AssetName);
        Out->SetStringField(TEXT("package_path"), PackagePath);
        Out->SetStringField(TEXT("asset_class_path"), AssetClassPath);
        Out->SetStringField(TEXT("factory_class_path"), FactoryClassPath);
        return {true, TEXT("Dry run native asset creation succeeded."), SerializePayload(Out), TEXT("OK")};
    }

    FAssetToolsModule& AssetToolsModule = FModuleManager::LoadModuleChecked<FAssetToolsModule>("AssetTools");
    UObject* Created = AssetToolsModule.Get().CreateAsset(AssetName, PackagePath, AssetClass, Factory);
    if (Created == nullptr)
    {
        return {false, TEXT("Native asset creation failed. Asset may already exist or factory configuration is invalid."), TEXT(""), TEXT("CREATE_ASSET_FAILED")};
    }

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetBoolField(TEXT("native"), true);
    Out->SetBoolField(TEXT("dry_run"), false);
    Out->SetStringField(TEXT("asset_name"), AssetName);
    Out->SetStringField(TEXT("package_path"), PackagePath);
    Out->SetStringField(TEXT("asset_path"), Created->GetPathName());
    Out->SetStringField(TEXT("asset_class_path"), AssetClassPath);
    Out->SetStringField(TEXT("factory_class_path"), FactoryClassPath);
    return {true, TEXT("Native asset created."), SerializePayload(Out), TEXT("OK")};
}

static FAgentActionResult HandleCreateNativeAssetTyped(
    const FAgentActionRequest& Request,
    const TSharedPtr<FJsonObject>& Payload,
    const FString& DefaultAssetName,
    const FString& DefaultPackagePath,
    const FString& DefaultAssetClassPath,
    const FString& DefaultFactoryClassPath,
    const FString& DefaultFactoryModuleName)
{
    FString AssetName = DefaultAssetName;
    FString PackagePath = DefaultPackagePath;
    FString AssetClassPath = DefaultAssetClassPath;
    FString FactoryClassPath = DefaultFactoryClassPath;
    FString FactoryModuleName = DefaultFactoryModuleName;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("asset_name"), AssetName);
        Payload->TryGetStringField(TEXT("package_path"), PackagePath);
        Payload->TryGetStringField(TEXT("asset_class_path"), AssetClassPath);
        Payload->TryGetStringField(TEXT("factory_class_path"), FactoryClassPath);
        Payload->TryGetStringField(TEXT("factory_module_name"), FactoryModuleName);
    }
    return CreateNativeAssetByClassPath(Request, AssetName, PackagePath, AssetClassPath, FactoryClassPath, FactoryModuleName);
}

static bool SetStructNameField(void* StructValue, UStruct* StructType, const FName& FieldName, const FName& Value)
{
    if (StructValue == nullptr || StructType == nullptr)
    {
        return false;
    }
    if (FNameProperty* NameProp = CastField<FNameProperty>(StructType->FindPropertyByName(FieldName)))
    {
        void* ValuePtr = NameProp->ContainerPtrToValuePtr<void>(StructValue);
        NameProp->SetPropertyValue(ValuePtr, Value);
        return true;
    }
    return false;
}

static bool SetStructBoolField(void* StructValue, UStruct* StructType, const FName& FieldName, const bool bValue)
{
    if (StructValue == nullptr || StructType == nullptr)
    {
        return false;
    }
    if (FBoolProperty* BoolProp = CastField<FBoolProperty>(StructType->FindPropertyByName(FieldName)))
    {
        void* ValuePtr = BoolProp->ContainerPtrToValuePtr<void>(StructValue);
        BoolProp->SetPropertyValue(ValuePtr, bValue);
        return true;
    }
    return false;
}

static bool SetStructObjectField(void* StructValue, UStruct* StructType, const FName& FieldName, UObject* ObjectValue)
{
    if (StructValue == nullptr || StructType == nullptr)
    {
        return false;
    }
    if (FObjectPropertyBase* ObjProp = CastField<FObjectPropertyBase>(StructType->FindPropertyByName(FieldName)))
    {
        void* ValuePtr = ObjProp->ContainerPtrToValuePtr<void>(StructValue);
        ObjProp->SetObjectPropertyValue(ValuePtr, ObjectValue);
        return true;
    }
    return false;
}

static bool ReadLinearColorField(const TSharedPtr<FJsonObject>& Operation, const FString& Field, FLinearColor& OutColor)
{
    const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
    if (!Operation.IsValid() || !Operation->TryGetArrayField(Field, Values) || Values == nullptr || Values->Num() != 4)
    {
        return false;
    }

    double R = 1.0;
    double G = 1.0;
    double B = 1.0;
    double A = 1.0;
    if (!(*Values)[0].IsValid() || !(*Values)[1].IsValid() || !(*Values)[2].IsValid() || !(*Values)[3].IsValid()
        || !(*Values)[0]->TryGetNumber(R)
        || !(*Values)[1]->TryGetNumber(G)
        || !(*Values)[2]->TryGetNumber(B)
        || !(*Values)[3]->TryGetNumber(A))
    {
        return false;
    }
    OutColor = FLinearColor(static_cast<float>(R), static_cast<float>(G), static_cast<float>(B), static_cast<float>(A));
    return true;
}

static bool ReadMarginField(const TSharedPtr<FJsonObject>& Operation, const FString& Field, FMargin& OutMargin)
{
    if (!Operation.IsValid())
    {
        return false;
    }

    const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
    if (Operation->TryGetArrayField(Field, Values) && Values != nullptr && Values->Num() == 4)
    {
        double L = 0.0;
        double T = 0.0;
        double R = 0.0;
        double B = 0.0;
        if ((*Values)[0].IsValid() && (*Values)[1].IsValid() && (*Values)[2].IsValid() && (*Values)[3].IsValid()
            && (*Values)[0]->TryGetNumber(L)
            && (*Values)[1]->TryGetNumber(T)
            && (*Values)[2]->TryGetNumber(R)
            && (*Values)[3]->TryGetNumber(B))
        {
            OutMargin = FMargin(static_cast<float>(L), static_cast<float>(T), static_cast<float>(R), static_cast<float>(B));
            return true;
        }
        return false;
    }

    double Uniform = 0.0;
    if (Operation->TryGetNumberField(Field, Uniform))
    {
        OutMargin = FMargin(static_cast<float>(Uniform));
        return true;
    }
    return false;
}

static bool ParseHorizontalAlignment(const FString& Value, EHorizontalAlignment& Out)
{
    if (Value.Equals(TEXT("left"), ESearchCase::IgnoreCase) || Value.Equals(TEXT("fill"), ESearchCase::IgnoreCase))
    {
        Out = Value.Equals(TEXT("fill"), ESearchCase::IgnoreCase) ? HAlign_Fill : HAlign_Left;
        return true;
    }
    if (Value.Equals(TEXT("center"), ESearchCase::IgnoreCase))
    {
        Out = HAlign_Center;
        return true;
    }
    if (Value.Equals(TEXT("right"), ESearchCase::IgnoreCase))
    {
        Out = HAlign_Right;
        return true;
    }
    return false;
}

static bool ParseVerticalAlignment(const FString& Value, EVerticalAlignment& Out)
{
    if (Value.Equals(TEXT("top"), ESearchCase::IgnoreCase) || Value.Equals(TEXT("fill"), ESearchCase::IgnoreCase))
    {
        Out = Value.Equals(TEXT("fill"), ESearchCase::IgnoreCase) ? VAlign_Fill : VAlign_Top;
        return true;
    }
    if (Value.Equals(TEXT("center"), ESearchCase::IgnoreCase))
    {
        Out = VAlign_Center;
        return true;
    }
    if (Value.Equals(TEXT("bottom"), ESearchCase::IgnoreCase))
    {
        Out = VAlign_Bottom;
        return true;
    }
    return false;
}

static void ParseAlignmentPreset(const FString& Preset, EHorizontalAlignment& OutH, EVerticalAlignment& OutV)
{
    OutH = HAlign_Left;
    OutV = VAlign_Top;

    if (Preset.Equals(TEXT("center"), ESearchCase::IgnoreCase))
    {
        OutH = HAlign_Center;
        OutV = VAlign_Center;
    }
    else if (Preset.Equals(TEXT("top_right"), ESearchCase::IgnoreCase))
    {
        OutH = HAlign_Right;
        OutV = VAlign_Top;
    }
    else if (Preset.Equals(TEXT("bottom_left"), ESearchCase::IgnoreCase))
    {
        OutH = HAlign_Left;
        OutV = VAlign_Bottom;
    }
    else if (Preset.Equals(TEXT("bottom_right"), ESearchCase::IgnoreCase))
    {
        OutH = HAlign_Right;
        OutV = VAlign_Bottom;
    }
    else if (Preset.Equals(TEXT("fill"), ESearchCase::IgnoreCase))
    {
        OutH = HAlign_Fill;
        OutV = VAlign_Fill;
    }
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
    FString WidgetBlueprintPath;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("widget_blueprint"), WidgetBlueprintPath);
        if (WidgetBlueprintPath.IsEmpty())
        {
            Payload->TryGetStringField(TEXT("blueprint_path"), WidgetBlueprintPath);
        }
    }
    if (WidgetBlueprintPath.IsEmpty())
    {
        return {false, TEXT("Missing widget_blueprint (or blueprint_path)."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    UWidgetBlueprint* WidgetBlueprint = LoadObject<UWidgetBlueprint>(nullptr, *WidgetBlueprintPath);
    if (WidgetBlueprint == nullptr || WidgetBlueprint->WidgetTree == nullptr)
    {
        return {false, FString::Printf(TEXT("Widget blueprint not found: %s"), *WidgetBlueprintPath), TEXT(""), TEXT("ASSET_NOT_FOUND")};
    }

    bool bCompileAfter = true;
    if (Payload.IsValid())
    {
        Payload->TryGetBoolField(TEXT("compile_after"), bCompileAfter);
    }

    const TArray<TSharedPtr<FJsonValue>>* OperationsArray = nullptr;
    TArray<TSharedPtr<FJsonValue>> SingleOperationArray;
    if (!Payload->TryGetArrayField(TEXT("operations"), OperationsArray) || OperationsArray == nullptr)
    {
        FString OpName;
        if (!Payload->TryGetStringField(TEXT("op"), OpName) && !Payload->TryGetStringField(TEXT("operation"), OpName))
        {
            return {false, TEXT("modify_widget_tree requires operations[] or operation/op."), TEXT(""), TEXT("MISSING_FIELD")};
        }
        TSharedRef<FJsonObject> Synthetic = MakeShared<FJsonObject>(*Payload);
        Synthetic->SetStringField(TEXT("op"), OpName);
        SingleOperationArray.Add(MakeShared<FJsonValueObject>(Synthetic));
        OperationsArray = &SingleOperationArray;
    }

    auto ResolveWidgetClass = [](const FString& WidgetClassName) -> UClass*
    {
        const FString Name = WidgetClassName.TrimStartAndEnd();
        if (Name.IsEmpty() || Name.Equals(TEXT("CanvasPanel"), ESearchCase::IgnoreCase))
        {
            return UCanvasPanel::StaticClass();
        }
        if (Name.Equals(TEXT("TextBlock"), ESearchCase::IgnoreCase))
        {
            return UTextBlock::StaticClass();
        }
        if (Name.Equals(TEXT("Button"), ESearchCase::IgnoreCase))
        {
            return UButton::StaticClass();
        }
        if (Name.Equals(TEXT("Image"), ESearchCase::IgnoreCase))
        {
            return UImage::StaticClass();
        }
        if (Name.Equals(TEXT("ProgressBar"), ESearchCase::IgnoreCase))
        {
            return UProgressBar::StaticClass();
        }
        if (Name.Equals(TEXT("ScrollBox"), ESearchCase::IgnoreCase))
        {
            return UScrollBox::StaticClass();
        }
        if (Name.Equals(TEXT("VerticalBox"), ESearchCase::IgnoreCase))
        {
            return UVerticalBox::StaticClass();
        }
        if (Name.Equals(TEXT("HorizontalBox"), ESearchCase::IgnoreCase))
        {
            return UHorizontalBox::StaticClass();
        }
        if (Name.Equals(TEXT("Overlay"), ESearchCase::IgnoreCase))
        {
            return UOverlay::StaticClass();
        }
        if (Name.Equals(TEXT("UniformGridPanel"), ESearchCase::IgnoreCase))
        {
            return UUniformGridPanel::StaticClass();
        }
        if (Name.Equals(TEXT("WrapBox"), ESearchCase::IgnoreCase))
        {
            return UWrapBox::StaticClass();
        }
        if (Name.Equals(TEXT("Border"), ESearchCase::IgnoreCase))
        {
            return UBorder::StaticClass();
        }
        if (Name.Equals(TEXT("SizeBox"), ESearchCase::IgnoreCase))
        {
            return USizeBox::StaticClass();
        }
        if (Name.Equals(TEXT("RichTextBlock"), ESearchCase::IgnoreCase))
        {
            return URichTextBlock::StaticClass();
        }
        UClass* DynamicClass = FindObject<UClass>(nullptr, *Name);
        return (DynamicClass != nullptr && DynamicClass->IsChildOf(UWidget::StaticClass())) ? DynamicClass : nullptr;
    };

    auto FindWidgetByName = [&](const FString& WidgetName) -> UWidget*
    {
        if (WidgetName.IsEmpty())
        {
            return nullptr;
        }
        if (WidgetBlueprint->WidgetTree->RootWidget != nullptr && WidgetBlueprint->WidgetTree->RootWidget->GetName() == WidgetName)
        {
            return WidgetBlueprint->WidgetTree->RootWidget;
        }
        TArray<UWidget*> AllWidgets;
        WidgetBlueprint->WidgetTree->GetAllWidgets(AllWidgets);
        for (UWidget* Widget : AllWidgets)
        {
            if (Widget != nullptr && Widget->GetName() == WidgetName)
            {
                return Widget;
            }
        }
        return nullptr;
    };

    auto ApplySlotLayout = [](UWidget* Widget, const TSharedPtr<FJsonObject>& Operation)
    {
        if (Widget == nullptr || !Operation.IsValid())
        {
            return;
        }

        auto ReadAlignments = [&](EHorizontalAlignment& OutH, EVerticalAlignment& OutV) -> bool
        {
            bool bUpdated = false;
            FString Preset;
            if (Operation->TryGetStringField(TEXT("alignment_preset"), Preset) && !Preset.IsEmpty())
            {
                ParseAlignmentPreset(Preset, OutH, OutV);
                bUpdated = true;
            }
            FString Horizontal;
            if (Operation->TryGetStringField(TEXT("horizontal_alignment"), Horizontal))
            {
                EHorizontalAlignment Parsed = OutH;
                if (ParseHorizontalAlignment(Horizontal, Parsed))
                {
                    OutH = Parsed;
                    bUpdated = true;
                }
            }
            FString Vertical;
            if (Operation->TryGetStringField(TEXT("vertical_alignment"), Vertical))
            {
                EVerticalAlignment Parsed = OutV;
                if (ParseVerticalAlignment(Vertical, Parsed))
                {
                    OutV = Parsed;
                    bUpdated = true;
                }
            }
            return bUpdated;
        };

        if (UCanvasPanelSlot* CanvasSlot = Cast<UCanvasPanelSlot>(Widget->Slot))
        {
            const TArray<TSharedPtr<FJsonValue>>* PositionValues = nullptr;
            if (Operation->TryGetArrayField(TEXT("position"), PositionValues) && PositionValues != nullptr && PositionValues->Num() == 2)
            {
                double X = 0.0;
                double Y = 0.0;
                if ((*PositionValues)[0].IsValid() && (*PositionValues)[1].IsValid() && (*PositionValues)[0]->TryGetNumber(X) && (*PositionValues)[1]->TryGetNumber(Y))
                {
                    CanvasSlot->SetPosition(FVector2D(static_cast<float>(X), static_cast<float>(Y)));
                }
            }

            const TArray<TSharedPtr<FJsonValue>>* SizeValues = nullptr;
            if (Operation->TryGetArrayField(TEXT("size"), SizeValues) && SizeValues != nullptr && SizeValues->Num() == 2)
            {
                double X = 0.0;
                double Y = 0.0;
                if ((*SizeValues)[0].IsValid() && (*SizeValues)[1].IsValid() && (*SizeValues)[0]->TryGetNumber(X) && (*SizeValues)[1]->TryGetNumber(Y))
                {
                    CanvasSlot->SetSize(FVector2D(static_cast<float>(X), static_cast<float>(Y)));
                }
            }

            const TArray<TSharedPtr<FJsonValue>>* AlignValues = nullptr;
            if (Operation->TryGetArrayField(TEXT("alignment"), AlignValues) && AlignValues != nullptr && AlignValues->Num() == 2)
            {
                double X = 0.0;
                double Y = 0.0;
                if ((*AlignValues)[0].IsValid() && (*AlignValues)[1].IsValid() && (*AlignValues)[0]->TryGetNumber(X) && (*AlignValues)[1]->TryGetNumber(Y))
                {
                    CanvasSlot->SetAlignment(FVector2D(static_cast<float>(X), static_cast<float>(Y)));
                }
            }

            const TArray<TSharedPtr<FJsonValue>>* AnchorMinValues = nullptr;
            const TArray<TSharedPtr<FJsonValue>>* AnchorMaxValues = nullptr;
            if (Operation->TryGetArrayField(TEXT("anchors_min"), AnchorMinValues)
                && Operation->TryGetArrayField(TEXT("anchors_max"), AnchorMaxValues)
                && AnchorMinValues != nullptr
                && AnchorMaxValues != nullptr
                && AnchorMinValues->Num() == 2
                && AnchorMaxValues->Num() == 2)
            {
                double MinX = 0.0;
                double MinY = 0.0;
                double MaxX = 0.0;
                double MaxY = 0.0;
                if ((*AnchorMinValues)[0].IsValid() && (*AnchorMinValues)[1].IsValid() && (*AnchorMaxValues)[0].IsValid() && (*AnchorMaxValues)[1].IsValid()
                    && (*AnchorMinValues)[0]->TryGetNumber(MinX)
                    && (*AnchorMinValues)[1]->TryGetNumber(MinY)
                    && (*AnchorMaxValues)[0]->TryGetNumber(MaxX)
                    && (*AnchorMaxValues)[1]->TryGetNumber(MaxY))
                {
                    CanvasSlot->SetAnchors(FAnchors(
                        static_cast<float>(MinX),
                        static_cast<float>(MinY),
                        static_cast<float>(MaxX),
                        static_cast<float>(MaxY)));
                }
            }

            double ZOrder = 0.0;
            if (Operation->TryGetNumberField(TEXT("z_order"), ZOrder))
            {
                CanvasSlot->SetZOrder(static_cast<int32>(ZOrder));
            }
            return;
        }

        FMargin Margin(0.0f);
        const bool bHasPadding = ReadMarginField(Operation, TEXT("padding"), Margin) || ReadMarginField(Operation, TEXT("margins"), Margin);

        if (UVerticalBoxSlot* VerticalSlot = Cast<UVerticalBoxSlot>(Widget->Slot))
        {
            if (bHasPadding)
            {
                VerticalSlot->SetPadding(Margin);
            }
            EHorizontalAlignment H = VerticalSlot->GetHorizontalAlignment();
            EVerticalAlignment V = VerticalSlot->GetVerticalAlignment();
            if (ReadAlignments(H, V))
            {
                VerticalSlot->SetHorizontalAlignment(H);
                VerticalSlot->SetVerticalAlignment(V);
            }
            return;
        }

        if (UHorizontalBoxSlot* HorizontalSlot = Cast<UHorizontalBoxSlot>(Widget->Slot))
        {
            if (bHasPadding)
            {
                HorizontalSlot->SetPadding(Margin);
            }
            EHorizontalAlignment H = HorizontalSlot->GetHorizontalAlignment();
            EVerticalAlignment V = HorizontalSlot->GetVerticalAlignment();
            if (ReadAlignments(H, V))
            {
                HorizontalSlot->SetHorizontalAlignment(H);
                HorizontalSlot->SetVerticalAlignment(V);
            }
            return;
        }

        if (UOverlaySlot* OverlaySlot = Cast<UOverlaySlot>(Widget->Slot))
        {
            if (bHasPadding)
            {
                OverlaySlot->SetPadding(Margin);
            }
            EHorizontalAlignment H = OverlaySlot->GetHorizontalAlignment();
            EVerticalAlignment V = OverlaySlot->GetVerticalAlignment();
            if (ReadAlignments(H, V))
            {
                OverlaySlot->SetHorizontalAlignment(H);
                OverlaySlot->SetVerticalAlignment(V);
            }
            return;
        }

        if (UUniformGridSlot* UniformSlot = Cast<UUniformGridSlot>(Widget->Slot))
        {
            double NumberValue = 0.0;
            if (Operation->TryGetNumberField(TEXT("row"), NumberValue))
            {
                UniformSlot->SetRow(FMath::Max(0, static_cast<int32>(NumberValue)));
            }
            if (Operation->TryGetNumberField(TEXT("column"), NumberValue))
            {
                UniformSlot->SetColumn(FMath::Max(0, static_cast<int32>(NumberValue)));
            }
            // UE5.7 UniformGridSlot does not expose row/column span or padding mutators.
            EHorizontalAlignment H = UniformSlot->GetHorizontalAlignment();
            EVerticalAlignment V = UniformSlot->GetVerticalAlignment();
            if (ReadAlignments(H, V))
            {
                UniformSlot->SetHorizontalAlignment(H);
                UniformSlot->SetVerticalAlignment(V);
            }
            return;
        }

        if (UWrapBoxSlot* WrapSlot = Cast<UWrapBoxSlot>(Widget->Slot))
        {
            if (bHasPadding)
            {
                WrapSlot->SetPadding(Margin);
            }
        }
    };

    auto SetWidgetProperty = [&](UWidget* Widget, const TSharedPtr<FJsonObject>& Operation, FString& OutError) -> bool
    {
        OutError.Reset();
        if (Widget == nullptr || !Operation.IsValid())
        {
            OutError = TEXT("Invalid widget/property operation.");
            return false;
        }

        FString PropertyName;
        if (!Operation->TryGetStringField(TEXT("property"), PropertyName) || PropertyName.IsEmpty())
        {
            OutError = TEXT("set_property requires property.");
            return false;
        }

        if (PropertyName.Equals(TEXT("text"), ESearchCase::IgnoreCase))
        {
            UTextBlock* TextBlock = Cast<UTextBlock>(Widget);
            if (TextBlock == nullptr)
            {
                OutError = TEXT("Property 'text' is only supported for TextBlock.");
                return false;
            }
            FString TextValue;
            if (!Operation->TryGetStringField(TEXT("value"), TextValue))
            {
                Operation->TryGetStringField(TEXT("text"), TextValue);
            }
            TextBlock->SetText(FText::FromString(TextValue));
            return true;
        }

        if (PropertyName.Equals(TEXT("visibility"), ESearchCase::IgnoreCase))
        {
            FString VisibilityValue;
            if (!Operation->TryGetStringField(TEXT("value"), VisibilityValue) || VisibilityValue.IsEmpty())
            {
                OutError = TEXT("visibility requires string value.");
                return false;
            }
            ESlateVisibility Visibility = ESlateVisibility::Visible;
            if (VisibilityValue.Equals(TEXT("Collapsed"), ESearchCase::IgnoreCase))
            {
                Visibility = ESlateVisibility::Collapsed;
            }
            else if (VisibilityValue.Equals(TEXT("Hidden"), ESearchCase::IgnoreCase))
            {
                Visibility = ESlateVisibility::Hidden;
            }
            else if (VisibilityValue.Equals(TEXT("HitTestInvisible"), ESearchCase::IgnoreCase))
            {
                Visibility = ESlateVisibility::HitTestInvisible;
            }
            else if (VisibilityValue.Equals(TEXT("SelfHitTestInvisible"), ESearchCase::IgnoreCase))
            {
                Visibility = ESlateVisibility::SelfHitTestInvisible;
            }
            Widget->SetVisibility(Visibility);
            return true;
        }

        if (PropertyName.Equals(TEXT("render_opacity"), ESearchCase::IgnoreCase))
        {
            double Opacity = 1.0;
            if (!Operation->TryGetNumberField(TEXT("value"), Opacity))
            {
                OutError = TEXT("render_opacity requires numeric value.");
                return false;
            }
            Widget->SetRenderOpacity(static_cast<float>(Opacity));
            return true;
        }

        if (PropertyName.Equals(TEXT("text_color"), ESearchCase::IgnoreCase))
        {
            UTextBlock* TextBlock = Cast<UTextBlock>(Widget);
            if (TextBlock == nullptr)
            {
                OutError = TEXT("Property 'text_color' is only supported for TextBlock.");
                return false;
            }
            FLinearColor Color = FLinearColor::White;
            if (!ReadLinearColorField(Operation, TEXT("value"), Color))
            {
                OutError = TEXT("text_color requires value=[r,g,b,a].");
                return false;
            }
            TextBlock->SetColorAndOpacity(FSlateColor(Color));
            return true;
        }

        if (PropertyName.Equals(TEXT("font_size"), ESearchCase::IgnoreCase))
        {
            UTextBlock* TextBlock = Cast<UTextBlock>(Widget);
            if (TextBlock == nullptr)
            {
                OutError = TEXT("Property 'font_size' is only supported for TextBlock.");
                return false;
            }
            double FontSize = 12.0;
            if (!Operation->TryGetNumberField(TEXT("value"), FontSize))
            {
                OutError = TEXT("font_size requires numeric value.");
                return false;
            }
            FSlateFontInfo FontInfo = TextBlock->GetFont();
            FontInfo.Size = FMath::Clamp(static_cast<int32>(FontSize), 1, 512);
            TextBlock->SetFont(FontInfo);
            return true;
        }

        if (PropertyName.Equals(TEXT("font_family"), ESearchCase::IgnoreCase))
        {
            UTextBlock* TextBlock = Cast<UTextBlock>(Widget);
            if (TextBlock == nullptr)
            {
                OutError = TEXT("Property 'font_family' is only supported for TextBlock.");
                return false;
            }
            FString Family;
            if (!Operation->TryGetStringField(TEXT("value"), Family) || Family.IsEmpty())
            {
                OutError = TEXT("font_family requires string value.");
                return false;
            }
            FSlateFontInfo FontInfo = TextBlock->GetFont();
            FontInfo.TypefaceFontName = FName(*Family);
            TextBlock->SetFont(FontInfo);
            return true;
        }

        if (PropertyName.Equals(TEXT("font_weight"), ESearchCase::IgnoreCase))
        {
            UTextBlock* TextBlock = Cast<UTextBlock>(Widget);
            if (TextBlock == nullptr)
            {
                OutError = TEXT("Property 'font_weight' is only supported for TextBlock.");
                return false;
            }
            FString Weight;
            if (!Operation->TryGetStringField(TEXT("value"), Weight) || Weight.IsEmpty())
            {
                OutError = TEXT("font_weight requires string value (e.g. Regular, Bold).");
                return false;
            }
            FSlateFontInfo FontInfo = TextBlock->GetFont();
            FontInfo.TypefaceFontName = FName(*Weight);
            TextBlock->SetFont(FontInfo);
            return true;
        }

        if (PropertyName.Equals(TEXT("brush_tint"), ESearchCase::IgnoreCase))
        {
            FLinearColor Color = FLinearColor::White;
            if (!ReadLinearColorField(Operation, TEXT("value"), Color))
            {
                OutError = TEXT("brush_tint requires value=[r,g,b,a].");
                return false;
            }
            if (UImage* Image = Cast<UImage>(Widget))
            {
                Image->SetColorAndOpacity(Color);
                return true;
            }
            if (UBorder* Border = Cast<UBorder>(Widget))
            {
                Border->SetBrushColor(Color);
                return true;
            }
            if (UProgressBar* ProgressBar = Cast<UProgressBar>(Widget))
            {
                ProgressBar->SetFillColorAndOpacity(Color);
                return true;
            }
            OutError = TEXT("Property 'brush_tint' is supported for Image, Border, or ProgressBar.");
            return false;
        }

        if (PropertyName.Equals(TEXT("padding"), ESearchCase::IgnoreCase) || PropertyName.Equals(TEXT("margins"), ESearchCase::IgnoreCase))
        {
            FMargin Margin(0.0f);
            if (!ReadMarginField(Operation, TEXT("value"), Margin))
            {
                if (!ReadMarginField(Operation, TEXT("padding"), Margin) && !ReadMarginField(Operation, TEXT("margins"), Margin))
                {
                    OutError = TEXT("padding requires value as [l,t,r,b] or number.");
                    return false;
                }
            }

            if (UVerticalBoxSlot* Slot = Cast<UVerticalBoxSlot>(Widget->Slot))
            {
                Slot->SetPadding(Margin);
                return true;
            }
            if (UHorizontalBoxSlot* Slot = Cast<UHorizontalBoxSlot>(Widget->Slot))
            {
                Slot->SetPadding(Margin);
                return true;
            }
            if (UOverlaySlot* Slot = Cast<UOverlaySlot>(Widget->Slot))
            {
                Slot->SetPadding(Margin);
                return true;
            }
            if (UUniformGridSlot* Slot = Cast<UUniformGridSlot>(Widget->Slot))
            {
                OutError = TEXT("padding is not supported for UniformGridSlot in UE5.7.");
                return false;
            }
            if (UWrapBoxSlot* Slot = Cast<UWrapBoxSlot>(Widget->Slot))
            {
                Slot->SetPadding(Margin);
                return true;
            }
            OutError = TEXT("padding is supported on Vertical/Horizontal/Overlay/UniformGrid/Wrap slots.");
            return false;
        }

        if (PropertyName.Equals(TEXT("alignment_preset"), ESearchCase::IgnoreCase))
        {
            FString Preset;
            if (!Operation->TryGetStringField(TEXT("value"), Preset) || Preset.IsEmpty())
            {
                OutError = TEXT("alignment_preset requires string value.");
                return false;
            }
            EHorizontalAlignment H = HAlign_Left;
            EVerticalAlignment V = VAlign_Top;
            ParseAlignmentPreset(Preset, H, V);
            if (UVerticalBoxSlot* Slot = Cast<UVerticalBoxSlot>(Widget->Slot))
            {
                Slot->SetHorizontalAlignment(H);
                Slot->SetVerticalAlignment(V);
                return true;
            }
            if (UHorizontalBoxSlot* Slot = Cast<UHorizontalBoxSlot>(Widget->Slot))
            {
                Slot->SetHorizontalAlignment(H);
                Slot->SetVerticalAlignment(V);
                return true;
            }
            if (UOverlaySlot* Slot = Cast<UOverlaySlot>(Widget->Slot))
            {
                Slot->SetHorizontalAlignment(H);
                Slot->SetVerticalAlignment(V);
                return true;
            }
            if (UUniformGridSlot* Slot = Cast<UUniformGridSlot>(Widget->Slot))
            {
                Slot->SetHorizontalAlignment(H);
                Slot->SetVerticalAlignment(V);
                return true;
            }
            OutError = TEXT("alignment_preset is supported on Vertical/Horizontal/Overlay/UniformGrid slots.");
            return false;
        }

        if (PropertyName.Equals(TEXT("is_enabled"), ESearchCase::IgnoreCase))
        {
            bool bEnabled = true;
            if (!Operation->TryGetBoolField(TEXT("value"), bEnabled))
            {
                OutError = TEXT("is_enabled requires boolean value.");
                return false;
            }
            Widget->SetIsEnabled(bEnabled);
            return true;
        }

        OutError = FString::Printf(TEXT("Unsupported widget property: %s"), *PropertyName);
        return false;
    };

    int32 Applied = 0;
    int32 Failed = 0;
    bool bChanged = false;
    TArray<TSharedPtr<FJsonValue>> OpResults;
    OpResults.Reserve(OperationsArray->Num());
    TUniquePtr<FScopedTransaction> Transaction;
    if (!Request.bDryRun)
    {
        Transaction = MakeUnique<FScopedTransaction>(NSLOCTEXT("UnrealAgent", "ModifyWidgetTree", "Agent Modify Widget Tree"));
        WidgetBlueprint->Modify();
        WidgetBlueprint->WidgetTree->Modify();
    }

    for (int32 i = 0; i < OperationsArray->Num(); ++i)
    {
        const TSharedPtr<FJsonObject> Operation = (*OperationsArray)[i].IsValid() ? (*OperationsArray)[i]->AsObject() : nullptr;
        FString OpName;
        bool bOpSuccess = false;
        FString OpMessage;
        if (!Operation.IsValid() || (!Operation->TryGetStringField(TEXT("op"), OpName) && !Operation->TryGetStringField(TEXT("operation"), OpName)))
        {
            bOpSuccess = false;
            OpMessage = TEXT("Invalid operation entry.");
        }
        else if (OpName.Equals(TEXT("ensure_root"), ESearchCase::IgnoreCase))
        {
            FString RootClassName = TEXT("CanvasPanel");
            FString RootName = TEXT("Root");
            Operation->TryGetStringField(TEXT("widget_class"), RootClassName);
            Operation->TryGetStringField(TEXT("name"), RootName);
            UClass* RootClass = ResolveWidgetClass(RootClassName);
            if (RootClass == nullptr || !RootClass->IsChildOf(UPanelWidget::StaticClass()))
            {
                bOpSuccess = false;
                OpMessage = FString::Printf(TEXT("Unsupported root widget_class: %s"), *RootClassName);
            }
            else if (WidgetBlueprint->WidgetTree->RootWidget == nullptr)
            {
                if (!Request.bDryRun)
                {
                    UWidget* RootWidget = WidgetBlueprint->WidgetTree->ConstructWidget<UWidget>(RootClass, FName(*RootName));
                    WidgetBlueprint->WidgetTree->RootWidget = RootWidget;
                    bChanged = true;
                }
                bOpSuccess = true;
                OpMessage = TEXT("Root widget ensured.");
            }
            else
            {
                bOpSuccess = true;
                OpMessage = TEXT("Root widget already exists.");
            }
        }
        else if (OpName.Equals(TEXT("add_widget"), ESearchCase::IgnoreCase))
        {
            FString WidgetClassName;
            FString WidgetName;
            FString ParentName;
            FString InitialText;
            Operation->TryGetStringField(TEXT("widget_class"), WidgetClassName);
            Operation->TryGetStringField(TEXT("name"), WidgetName);
            Operation->TryGetStringField(TEXT("parent"), ParentName);
            Operation->TryGetStringField(TEXT("text"), InitialText);
            if (WidgetName.IsEmpty() || WidgetClassName.IsEmpty())
            {
                bOpSuccess = false;
                OpMessage = TEXT("add_widget requires name and widget_class.");
            }
            else
            {
                UClass* WidgetClass = ResolveWidgetClass(WidgetClassName);
                if (WidgetClass == nullptr)
                {
                    bOpSuccess = false;
                    OpMessage = FString::Printf(TEXT("Unsupported widget_class: %s"), *WidgetClassName);
                }
                else
                {
                    UWidget* RootWidget = WidgetBlueprint->WidgetTree->RootWidget.Get();
                    UWidget* ParentWidget = ParentName.IsEmpty() ? RootWidget : FindWidgetByName(ParentName);
                    UPanelWidget* ParentPanel = Cast<UPanelWidget>(ParentWidget);
                    if (ParentPanel == nullptr)
                    {
                        bOpSuccess = false;
                        OpMessage = TEXT("add_widget parent must resolve to a panel widget.");
                    }
                    else if (FindWidgetByName(WidgetName) != nullptr)
                    {
                        bOpSuccess = false;
                        OpMessage = TEXT("Widget with that name already exists.");
                    }
                    else
                    {
                        if (!Request.bDryRun)
                        {
                            UWidget* NewWidget = WidgetBlueprint->WidgetTree->ConstructWidget<UWidget>(WidgetClass, FName(*WidgetName));
                            ParentPanel->AddChild(NewWidget);
                            if (!InitialText.IsEmpty())
                            {
                                if (UTextBlock* TextBlock = Cast<UTextBlock>(NewWidget))
                                {
                                    TextBlock->SetText(FText::FromString(InitialText));
                                }
                            }
                            ApplySlotLayout(NewWidget, Operation);
                            bChanged = true;
                        }
                        bOpSuccess = true;
                        OpMessage = TEXT("Widget added.");
                    }
                }
            }
        }
        else if (OpName.Equals(TEXT("remove_widget"), ESearchCase::IgnoreCase))
        {
            FString WidgetName;
            Operation->TryGetStringField(TEXT("name"), WidgetName);
            if (WidgetName.IsEmpty())
            {
                bOpSuccess = false;
                OpMessage = TEXT("remove_widget requires name.");
            }
            else
            {
                UWidget* TargetWidget = FindWidgetByName(WidgetName);
                if (TargetWidget == nullptr)
                {
                    bOpSuccess = false;
                    OpMessage = TEXT("Widget not found.");
                }
                else
                {
                    if (!Request.bDryRun)
                    {
                        if (WidgetBlueprint->WidgetTree->RootWidget == TargetWidget)
                        {
                            WidgetBlueprint->WidgetTree->RootWidget = nullptr;
                            bChanged = true;
                        }
                        else if (UPanelWidget* ParentPanel = Cast<UPanelWidget>(TargetWidget->GetParent()))
                        {
                            bChanged = ParentPanel->RemoveChild(TargetWidget) || bChanged;
                        }
                    }
                    bOpSuccess = true;
                    OpMessage = TEXT("Widget removed.");
                }
            }
        }
        else if (OpName.Equals(TEXT("set_property"), ESearchCase::IgnoreCase))
        {
            FString WidgetName;
            Operation->TryGetStringField(TEXT("widget"), WidgetName);
            if (WidgetName.IsEmpty())
            {
                bOpSuccess = false;
                OpMessage = TEXT("set_property requires widget.");
            }
            else
            {
                UWidget* TargetWidget = FindWidgetByName(WidgetName);
                if (TargetWidget == nullptr)
                {
                    bOpSuccess = false;
                    OpMessage = TEXT("Target widget not found.");
                }
                else
                {
                    FString PropertyError;
                    if (Request.bDryRun)
                    {
                        FString PropertyName;
                        Operation->TryGetStringField(TEXT("property"), PropertyName);
                        if (PropertyName.Equals(TEXT("text"), ESearchCase::IgnoreCase))
                        {
                            bOpSuccess = Cast<UTextBlock>(TargetWidget) != nullptr;
                            OpMessage = bOpSuccess ? TEXT("Property update validated.") : TEXT("Property 'text' is only supported for TextBlock.");
                        }
                        else if (PropertyName.Equals(TEXT("visibility"), ESearchCase::IgnoreCase)
                            || PropertyName.Equals(TEXT("render_opacity"), ESearchCase::IgnoreCase)
                            || PropertyName.Equals(TEXT("text_color"), ESearchCase::IgnoreCase)
                            || PropertyName.Equals(TEXT("font_size"), ESearchCase::IgnoreCase)
                            || PropertyName.Equals(TEXT("font_family"), ESearchCase::IgnoreCase)
                            || PropertyName.Equals(TEXT("font_weight"), ESearchCase::IgnoreCase)
                            || PropertyName.Equals(TEXT("brush_tint"), ESearchCase::IgnoreCase)
                            || PropertyName.Equals(TEXT("padding"), ESearchCase::IgnoreCase)
                            || PropertyName.Equals(TEXT("margins"), ESearchCase::IgnoreCase)
                            || PropertyName.Equals(TEXT("alignment_preset"), ESearchCase::IgnoreCase)
                            || PropertyName.Equals(TEXT("is_enabled"), ESearchCase::IgnoreCase))
                        {
                            bOpSuccess = true;
                            OpMessage = TEXT("Property update validated.");
                        }
                        else
                        {
                            bOpSuccess = false;
                            OpMessage = FString::Printf(TEXT("Unsupported widget property: %s"), *PropertyName);
                        }
                    }
                    else
                    {
                        bOpSuccess = SetWidgetProperty(TargetWidget, Operation, PropertyError);
                        OpMessage = bOpSuccess ? TEXT("Property updated.") : PropertyError;
                        bChanged = bChanged || bOpSuccess;
                    }
                }
            }
        }
        else if (OpName.Equals(TEXT("set_slot"), ESearchCase::IgnoreCase))
        {
            FString WidgetName;
            Operation->TryGetStringField(TEXT("widget"), WidgetName);
            if (WidgetName.IsEmpty())
            {
                bOpSuccess = false;
                OpMessage = TEXT("set_slot requires widget.");
            }
            else
            {
                UWidget* TargetWidget = FindWidgetByName(WidgetName);
                if (TargetWidget == nullptr)
                {
                    bOpSuccess = false;
                    OpMessage = TEXT("Target widget not found.");
                }
                else
                {
                    if (!Request.bDryRun)
                    {
                        ApplySlotLayout(TargetWidget, Operation);
                        bChanged = true;
                    }
                    bOpSuccess = true;
                    OpMessage = TEXT("Slot layout updated.");
                }
            }
        }
        else
        {
            bOpSuccess = false;
            OpMessage = FString::Printf(TEXT("Unsupported widget operation: %s"), *OpName);
        }

        TSharedRef<FJsonObject> OpResult = MakeShared<FJsonObject>();
        OpResult->SetNumberField(TEXT("index"), i);
        OpResult->SetStringField(TEXT("op"), OpName);
        OpResult->SetBoolField(TEXT("success"), bOpSuccess);
        OpResult->SetStringField(TEXT("message"), OpMessage);
        OpResults.Add(MakeShared<FJsonValueObject>(OpResult));

        if (bOpSuccess)
        {
            ++Applied;
        }
        else
        {
            ++Failed;
        }
    }

    if (!Request.bDryRun && bChanged)
    {
        FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(WidgetBlueprint);
        WidgetBlueprint->MarkPackageDirty();
        if (bCompileAfter)
        {
            FKismetEditorUtilities::CompileBlueprint(WidgetBlueprint);
        }
    }

    TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetStringField(TEXT("widget_blueprint"), WidgetBlueprintPath);
    Result->SetBoolField(TEXT("dry_run"), Request.bDryRun);
    Result->SetBoolField(TEXT("changed"), Request.bDryRun ? false : bChanged);
    Result->SetNumberField(TEXT("operations_requested"), OperationsArray->Num());
    Result->SetNumberField(TEXT("operations_applied"), Applied);
    Result->SetNumberField(TEXT("operations_failed"), Failed);
    Result->SetBoolField(TEXT("compiled"), !Request.bDryRun && bChanged && bCompileAfter);
    Result->SetArrayField(TEXT("operation_results"), OpResults);

    const bool bSuccess = Failed == 0;
    return {
        bSuccess,
        bSuccess ? TEXT("modify_widget_tree completed.") : TEXT("modify_widget_tree completed with failures."),
        SerializePayload(Result),
        bSuccess ? TEXT("OK") : TEXT("PARTIAL_FAILURE")};
}

static FAgentActionResult HandleBindWidgetEvents(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString WidgetBlueprintPath;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("widget_blueprint"), WidgetBlueprintPath);
        if (WidgetBlueprintPath.IsEmpty())
        {
            Payload->TryGetStringField(TEXT("blueprint_path"), WidgetBlueprintPath);
        }
    }
    if (WidgetBlueprintPath.IsEmpty())
    {
        return {false, TEXT("Missing widget_blueprint (or blueprint_path)."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    UWidgetBlueprint* WidgetBlueprint = LoadObject<UWidgetBlueprint>(nullptr, *WidgetBlueprintPath);
    if (WidgetBlueprint == nullptr || WidgetBlueprint->WidgetTree == nullptr)
    {
        return {false, FString::Printf(TEXT("Widget blueprint not found: %s"), *WidgetBlueprintPath), TEXT(""), TEXT("ASSET_NOT_FOUND")};
    }

    bool bCompileAfter = true;
    if (Payload.IsValid())
    {
        Payload->TryGetBoolField(TEXT("compile_after"), bCompileAfter);
    }

    const TArray<TSharedPtr<FJsonValue>>* BindingsArray = nullptr;
    TArray<TSharedPtr<FJsonValue>> SingleBindingArray;
    if (!Payload->TryGetArrayField(TEXT("bindings"), BindingsArray) || BindingsArray == nullptr)
    {
        FString WidgetName;
        if (!Payload->TryGetStringField(TEXT("widget"), WidgetName))
        {
            return {false, TEXT("bind_widget_events requires bindings[] or widget+event fields."), TEXT(""), TEXT("MISSING_FIELD")};
        }
        TSharedRef<FJsonObject> Synthetic = MakeShared<FJsonObject>(*Payload);
        SingleBindingArray.Add(MakeShared<FJsonValueObject>(Synthetic));
        BindingsArray = &SingleBindingArray;
    }

    UEdGraph* EventGraph = nullptr;
    if (WidgetBlueprint->UbergraphPages.Num() > 0)
    {
        EventGraph = WidgetBlueprint->UbergraphPages[0];
    }
    if (EventGraph == nullptr && !Request.bDryRun)
    {
        EventGraph = FBlueprintEditorUtils::CreateNewGraph(
            WidgetBlueprint,
            NAME_None,
            UEdGraph::StaticClass(),
            UEdGraphSchema_K2::StaticClass());
        FBlueprintEditorUtils::AddUbergraphPage(WidgetBlueprint, EventGraph);
    }
    if (EventGraph == nullptr)
    {
        return {false, TEXT("Unable to resolve event graph for widget blueprint."), TEXT(""), TEXT("GRAPH_NOT_FOUND")};
    }

    auto FindWidgetByName = [&](const FString& WidgetName) -> UWidget*
    {
        if (WidgetName.IsEmpty())
        {
            return nullptr;
        }
        if (WidgetBlueprint->WidgetTree->RootWidget != nullptr && WidgetBlueprint->WidgetTree->RootWidget->GetName() == WidgetName)
        {
            return WidgetBlueprint->WidgetTree->RootWidget;
        }
        TArray<UWidget*> AllWidgets;
        WidgetBlueprint->WidgetTree->GetAllWidgets(AllWidgets);
        for (UWidget* Widget : AllWidgets)
        {
            if (Widget != nullptr && Widget->GetName() == WidgetName)
            {
                return Widget;
            }
        }
        return nullptr;
    };

    int32 Applied = 0;
    int32 Failed = 0;
    bool bChanged = false;
    int32 BaseY = 0;
    TArray<TSharedPtr<FJsonValue>> BindingResults;
    BindingResults.Reserve(BindingsArray->Num());
    TUniquePtr<FScopedTransaction> Transaction;
    if (!Request.bDryRun)
    {
        Transaction = MakeUnique<FScopedTransaction>(NSLOCTEXT("UnrealAgent", "BindWidgetEvents", "Agent Bind Widget Events"));
        WidgetBlueprint->Modify();
        EventGraph->Modify();
    }

    const UEdGraphSchema_K2* Schema = GetDefault<UEdGraphSchema_K2>();
    for (int32 i = 0; i < BindingsArray->Num(); ++i)
    {
        const TSharedPtr<FJsonObject> Binding = (*BindingsArray)[i].IsValid() ? (*BindingsArray)[i]->AsObject() : nullptr;
        bool bBindingSuccess = false;
        FString BindingMessage;
        FString WidgetName;
        FString EventName;
        if (!Binding.IsValid())
        {
            BindingMessage = TEXT("Invalid binding object.");
        }
        else if (!Binding->TryGetStringField(TEXT("widget"), WidgetName) || WidgetName.IsEmpty())
        {
            BindingMessage = TEXT("Binding requires widget.");
        }
        else if (!Binding->TryGetStringField(TEXT("event"), EventName) || EventName.IsEmpty())
        {
            BindingMessage = TEXT("Binding requires event.");
        }
        else
        {
            UWidget* TargetWidget = FindWidgetByName(WidgetName);
            if (TargetWidget == nullptr)
            {
                BindingMessage = TEXT("Target widget not found in widget tree.");
            }
            else
            {
                const UClass* WidgetClass = TargetWidget->GetClass();
                const FMulticastDelegateProperty* DelegateProperty = CastField<FMulticastDelegateProperty>(WidgetClass->FindPropertyByName(*EventName));
                if (DelegateProperty == nullptr || DelegateProperty->SignatureFunction == nullptr)
                {
                    BindingMessage = FString::Printf(TEXT("Widget event '%s' is not a multicast delegate on %s."), *EventName, *WidgetClass->GetName());
                }
                else if (Request.bDryRun)
                {
                    bBindingSuccess = true;
                    BindingMessage = TEXT("Binding validated.");
                }
                else
                {
                    UK2Node_ComponentBoundEvent* EventNode = FEdGraphSchemaAction_K2NewNode::SpawnNode<UK2Node_ComponentBoundEvent>(
                        EventGraph,
                        FVector2D(-1100.0f, static_cast<float>(BaseY)),
                        EK2NewNodeFlags::SelectNewNode,
                        [&](UK2Node_ComponentBoundEvent* NewNode)
                        {
                            NewNode->DelegatePropertyName = DelegateProperty->GetFName();
                            NewNode->ComponentPropertyName = FName(*WidgetName);
                            NewNode->EventReference.SetExternalMember(
                                DelegateProperty->SignatureFunction->GetFName(),
                                const_cast<UClass*>(WidgetClass));
                            NewNode->bInternalEvent = true;
                            NewNode->CustomFunctionName = FName(*FString::Printf(
                                TEXT("BndEvt__%s_%s_%d"),
                                *WidgetName,
                                *EventName,
                                i));
                        });

                    if (EventNode == nullptr)
                    {
                        BindingMessage = TEXT("Failed to create component bound event node.");
                    }
                    else
                    {
                        FString ActionMode = TEXT("print_string");
                        Binding->TryGetStringField(TEXT("action"), ActionMode);
                        bool bHandledDirectAction = false;

                        if (ActionMode.Equals(TEXT("toggle_visibility"), ESearchCase::IgnoreCase)
                            || ActionMode.Equals(TEXT("set_text"), ESearchCase::IgnoreCase)
                            || ActionMode.Equals(TEXT("set_progress"), ESearchCase::IgnoreCase))
                        {
                            bool bModeApplied = false;
                            if (ActionMode.Equals(TEXT("toggle_visibility"), ESearchCase::IgnoreCase))
                            {
                                bool bVisible = false;
                                if (!Binding->TryGetBoolField(TEXT("visible"), bVisible))
                                {
                                    FString VisibilityString;
                                    if (Binding->TryGetStringField(TEXT("visibility"), VisibilityString))
                                    {
                                        bVisible = VisibilityString.Equals(TEXT("Visible"), ESearchCase::IgnoreCase);
                                    }
                                }
                                TargetWidget->SetVisibility(bVisible ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
                                bModeApplied = true;
                            }
                            else if (ActionMode.Equals(TEXT("set_text"), ESearchCase::IgnoreCase))
                            {
                                FString TextValue = FString::Printf(TEXT("%s.%s"), *WidgetName, *EventName);
                                Binding->TryGetStringField(TEXT("text"), TextValue);
                                if (UTextBlock* TextBlock = Cast<UTextBlock>(TargetWidget))
                                {
                                    TextBlock->SetText(FText::FromString(TextValue));
                                    bModeApplied = true;
                                }
                                else if (URichTextBlock* RichText = Cast<URichTextBlock>(TargetWidget))
                                {
                                    RichText->SetText(FText::FromString(TextValue));
                                    bModeApplied = true;
                                }
                            }
                            else if (ActionMode.Equals(TEXT("set_progress"), ESearchCase::IgnoreCase))
                            {
                                double PercentValue = 1.0;
                                Binding->TryGetNumberField(TEXT("percent"), PercentValue);
                                if (UProgressBar* ProgressBar = Cast<UProgressBar>(TargetWidget))
                                {
                                    ProgressBar->SetPercent(FMath::Clamp(static_cast<float>(PercentValue), 0.0f, 1.0f));
                                    bModeApplied = true;
                                }
                            }

                            if (bModeApplied)
                            {
                                bBindingSuccess = true;
                                bChanged = true;
                                BindingMessage = TEXT("Widget event bound with direct widget action.");
                            }
                            else
                            {
                                BindingMessage = TEXT("Direct widget action was not applicable to target widget.");
                            }
                            bHandledDirectAction = true;
                        }

                        if (!bHandledDirectAction)
                        {
                            UFunction* Function = nullptr;
                            if (ActionMode.Equals(TEXT("print_string"), ESearchCase::IgnoreCase))
                            {
                                Function = UKismetSystemLibrary::StaticClass()->FindFunctionByName(TEXT("PrintString"));
                            }
                            else
                            {
                                FString ClassPath;
                                FString FunctionName;
                                Binding->TryGetStringField(TEXT("class_path"), ClassPath);
                                Binding->TryGetStringField(TEXT("function_name"), FunctionName);
                                if ((ActionMode.Equals(TEXT("call_function"), ESearchCase::IgnoreCase)
                                        || ActionMode.Equals(TEXT("dispatch_event"), ESearchCase::IgnoreCase))
                                    && (ClassPath.IsEmpty() || FunctionName.IsEmpty()))
                                {
                                    Function = UKismetSystemLibrary::StaticClass()->FindFunctionByName(TEXT("PrintString"));
                                    FunctionName = TEXT("PrintString");
                                }
                                if (!ClassPath.IsEmpty() && !FunctionName.IsEmpty())
                                {
                                    UClass* FunctionClass = LoadObject<UClass>(nullptr, *ClassPath);
                                    if (FunctionClass == nullptr)
                                    {
                                        FunctionClass = FindObject<UClass>(nullptr, *ClassPath);
                                    }
                                    if (FunctionClass != nullptr)
                                    {
                                        Function = FunctionClass->FindFunctionByName(*FunctionName);
                                    }
                                }
                            }

                            if (Function == nullptr)
                            {
                                BindingMessage = TEXT("Unable to resolve function for binding action.");
                            }
                            else
                            {
                                UK2Node_CallFunction* CallNode = FEdGraphSchemaAction_K2NewNode::SpawnNode<UK2Node_CallFunction>(
                                    EventGraph,
                                    FVector2D(-700.0f, static_cast<float>(BaseY)),
                                    EK2NewNodeFlags::SelectNewNode,
                                    [Function](UK2Node_CallFunction* NewNode)
                                    {
                                        NewNode->SetFromFunction(Function);
                                    });
                                if (CallNode == nullptr)
                                {
                                    BindingMessage = TEXT("Failed to spawn call function node for binding.");
                                }
                                else
                                {
                                    UEdGraphPin* ThenPin = EventNode->FindPin(UEdGraphSchema_K2::PN_Then);
                                    UEdGraphPin* ExecPin = CallNode->FindPin(UEdGraphSchema_K2::PN_Execute);
                                    if (ThenPin != nullptr && ExecPin != nullptr)
                                    {
                                        Schema->TryCreateConnection(ThenPin, ExecPin);
                                    }

                                    if (ActionMode.Equals(TEXT("print_string"), ESearchCase::IgnoreCase))
                                    {
                                        FString MessageValue = FString::Printf(TEXT("%s.%s"), *WidgetName, *EventName);
                                        Binding->TryGetStringField(TEXT("message"), MessageValue);
                                        if (UEdGraphPin* MessagePin = CallNode->FindPin(TEXT("InString")))
                                        {
                                            Schema->TrySetDefaultValue(*MessagePin, MessageValue);
                                        }
                                    }

                                    if (const TSharedPtr<FJsonObject>* PinDefaultsObj = nullptr;
                                        Binding->TryGetObjectField(TEXT("pin_defaults"), PinDefaultsObj) &&
                                        PinDefaultsObj != nullptr && PinDefaultsObj->IsValid())
                                    {
                                        for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*PinDefaultsObj)->Values)
                                        {
                                            UEdGraphPin* TargetPin = CallNode->FindPin(*Pair.Key);
                                            if (TargetPin == nullptr || !Pair.Value.IsValid())
                                            {
                                                continue;
                                            }
                                            FString ValueString;
                                            if (Pair.Value->TryGetString(ValueString))
                                            {
                                                Schema->TrySetDefaultValue(*TargetPin, ValueString);
                                                continue;
                                            }
                                            double NumberValue = 0.0;
                                            bool BoolValue = false;
                                            if (Pair.Value->TryGetNumber(NumberValue))
                                            {
                                                Schema->TrySetDefaultValue(*TargetPin, FString::SanitizeFloat(NumberValue));
                                            }
                                            else if (Pair.Value->TryGetBool(BoolValue))
                                            {
                                                Schema->TrySetDefaultValue(*TargetPin, BoolValue ? TEXT("true") : TEXT("false"));
                                            }
                                        }
                                    }

                                    bBindingSuccess = true;
                                    bChanged = true;
                                    BindingMessage = TEXT("Widget event bound.");
                                }
                            }
                        }
                    }
                }
            }
        }

        BaseY += 220;
        TSharedRef<FJsonObject> BindingResult = MakeShared<FJsonObject>();
        BindingResult->SetNumberField(TEXT("index"), i);
        BindingResult->SetStringField(TEXT("widget"), WidgetName);
        BindingResult->SetStringField(TEXT("event"), EventName);
        BindingResult->SetBoolField(TEXT("success"), bBindingSuccess);
        BindingResult->SetStringField(TEXT("message"), BindingMessage);
        BindingResults.Add(MakeShared<FJsonValueObject>(BindingResult));

        if (bBindingSuccess)
        {
            ++Applied;
        }
        else
        {
            ++Failed;
        }
    }

    if (!Request.bDryRun && bChanged)
    {
        FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(WidgetBlueprint);
        WidgetBlueprint->MarkPackageDirty();
        if (bCompileAfter)
        {
            FKismetEditorUtilities::CompileBlueprint(WidgetBlueprint);
        }
    }

    TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetStringField(TEXT("widget_blueprint"), WidgetBlueprintPath);
    Result->SetBoolField(TEXT("dry_run"), Request.bDryRun);
    Result->SetBoolField(TEXT("changed"), Request.bDryRun ? false : bChanged);
    Result->SetNumberField(TEXT("bindings_requested"), BindingsArray->Num());
    Result->SetNumberField(TEXT("bindings_applied"), Applied);
    Result->SetNumberField(TEXT("bindings_failed"), Failed);
    Result->SetBoolField(TEXT("compiled"), !Request.bDryRun && bChanged && bCompileAfter);
    Result->SetArrayField(TEXT("binding_results"), BindingResults);

    const bool bSuccess = Failed == 0;
    return {
        bSuccess,
        bSuccess ? TEXT("bind_widget_events completed.") : TEXT("bind_widget_events completed with failures."),
        SerializePayload(Result),
        bSuccess ? TEXT("OK") : TEXT("PARTIAL_FAILURE")};
}

static FAgentActionResult HandleGenerateWidgetTemplate(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString WidgetBlueprintPath;
    FString TemplateId = TEXT("hud_basic");
    FString StylePreset = TEXT("minimal");
    bool bCompileAfter = true;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("widget_blueprint"), WidgetBlueprintPath);
        if (WidgetBlueprintPath.IsEmpty())
        {
            Payload->TryGetStringField(TEXT("blueprint_path"), WidgetBlueprintPath);
        }
        Payload->TryGetStringField(TEXT("template_id"), TemplateId);
        Payload->TryGetStringField(TEXT("style_preset"), StylePreset);
        Payload->TryGetBoolField(TEXT("compile_after"), bCompileAfter);
    }
    if (WidgetBlueprintPath.IsEmpty())
    {
        return {false, TEXT("Missing widget_blueprint (or blueprint_path)."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    const FString Template = TemplateId.TrimStartAndEnd().ToLower();
    const FString Style = StylePreset.TrimStartAndEnd().ToLower();
    TArray<TSharedPtr<FJsonValue>> Operations;
    TArray<TSharedPtr<FJsonValue>> Bindings;

    {
        TSharedRef<FJsonObject> Op = MakeShared<FJsonObject>();
        Op->SetStringField(TEXT("op"), TEXT("ensure_root"));
        Op->SetStringField(TEXT("widget_class"), TEXT("CanvasPanel"));
        Op->SetStringField(TEXT("name"), TEXT("Root"));
        Operations.Add(MakeShared<FJsonValueObject>(Op));
    }
    {
        TSharedRef<FJsonObject> Header = MakeShared<FJsonObject>();
        Header->SetStringField(TEXT("op"), TEXT("add_widget"));
        Header->SetStringField(TEXT("widget_class"), TEXT("TextBlock"));
        Header->SetStringField(TEXT("name"), TEXT("HeaderText"));
        Header->SetStringField(TEXT("parent"), TEXT("Root"));
        Header->SetStringField(TEXT("text"), TEXT("Objectives"));
        Header->SetArrayField(TEXT("position"), {MakeShared<FJsonValueNumber>(32.0), MakeShared<FJsonValueNumber>(24.0)});
        Header->SetArrayField(TEXT("size"), {MakeShared<FJsonValueNumber>(360.0), MakeShared<FJsonValueNumber>(48.0)});
        Operations.Add(MakeShared<FJsonValueObject>(Header));
    }
    if (Template == TEXT("inventory_grid") || Template == TEXT("menu_shell"))
    {
        TSharedRef<FJsonObject> Grid = MakeShared<FJsonObject>();
        Grid->SetStringField(TEXT("op"), TEXT("add_widget"));
        Grid->SetStringField(TEXT("widget_class"), TEXT("UniformGridPanel"));
        Grid->SetStringField(TEXT("name"), TEXT("MainGrid"));
        Grid->SetStringField(TEXT("parent"), TEXT("Root"));
        Grid->SetArrayField(TEXT("position"), {MakeShared<FJsonValueNumber>(48.0), MakeShared<FJsonValueNumber>(90.0)});
        Grid->SetArrayField(TEXT("size"), {MakeShared<FJsonValueNumber>(820.0), MakeShared<FJsonValueNumber>(480.0)});
        Operations.Add(MakeShared<FJsonValueObject>(Grid));
    }
    {
        TSharedRef<FJsonObject> Button = MakeShared<FJsonObject>();
        Button->SetStringField(TEXT("op"), TEXT("add_widget"));
        Button->SetStringField(TEXT("widget_class"), TEXT("Button"));
        Button->SetStringField(TEXT("name"), TEXT("PrimaryActionButton"));
        Button->SetStringField(TEXT("parent"), TEXT("Root"));
        Button->SetArrayField(TEXT("position"), {MakeShared<FJsonValueNumber>(32.0), MakeShared<FJsonValueNumber>(92.0)});
        Button->SetArrayField(TEXT("size"), {MakeShared<FJsonValueNumber>(220.0), MakeShared<FJsonValueNumber>(48.0)});
        Operations.Add(MakeShared<FJsonValueObject>(Button));
    }
    {
        TSharedRef<FJsonObject> Progress = MakeShared<FJsonObject>();
        Progress->SetStringField(TEXT("op"), TEXT("add_widget"));
        Progress->SetStringField(TEXT("widget_class"), TEXT("ProgressBar"));
        Progress->SetStringField(TEXT("name"), TEXT("ObjectiveProgressBar"));
        Progress->SetStringField(TEXT("parent"), TEXT("Root"));
        Progress->SetArrayField(TEXT("position"), {MakeShared<FJsonValueNumber>(32.0), MakeShared<FJsonValueNumber>(150.0)});
        Progress->SetArrayField(TEXT("size"), {MakeShared<FJsonValueNumber>(320.0), MakeShared<FJsonValueNumber>(18.0)});
        Operations.Add(MakeShared<FJsonValueObject>(Progress));
    }
    {
        TSharedRef<FJsonObject> StyleOp = MakeShared<FJsonObject>();
        StyleOp->SetStringField(TEXT("op"), TEXT("set_property"));
        StyleOp->SetStringField(TEXT("widget"), TEXT("HeaderText"));
        StyleOp->SetStringField(TEXT("property"), TEXT("font_size"));
        StyleOp->SetNumberField(TEXT("value"), Style == TEXT("menu_clean") ? 30.0 : 24.0);
        Operations.Add(MakeShared<FJsonValueObject>(StyleOp));
    }
    {
        TSharedRef<FJsonObject> StyleColorOp = MakeShared<FJsonObject>();
        StyleColorOp->SetStringField(TEXT("op"), TEXT("set_property"));
        StyleColorOp->SetStringField(TEXT("widget"), TEXT("HeaderText"));
        StyleColorOp->SetStringField(TEXT("property"), TEXT("text_color"));
        if (Style == TEXT("diegetic_overlay"))
        {
            StyleColorOp->SetArrayField(TEXT("value"), {MakeShared<FJsonValueNumber>(0.70), MakeShared<FJsonValueNumber>(1.0), MakeShared<FJsonValueNumber>(0.85), MakeShared<FJsonValueNumber>(1.0)});
        }
        else
        {
            StyleColorOp->SetArrayField(TEXT("value"), {MakeShared<FJsonValueNumber>(0.92), MakeShared<FJsonValueNumber>(0.97), MakeShared<FJsonValueNumber>(1.0), MakeShared<FJsonValueNumber>(1.0)});
        }
        Operations.Add(MakeShared<FJsonValueObject>(StyleColorOp));
    }

    {
        TSharedRef<FJsonObject> Binding = MakeShared<FJsonObject>();
        Binding->SetStringField(TEXT("widget"), TEXT("PrimaryActionButton"));
        Binding->SetStringField(TEXT("event"), TEXT("OnClicked"));
        Binding->SetStringField(TEXT("action"), TEXT("set_progress"));
        Binding->SetNumberField(TEXT("percent"), 1.0);
        Bindings.Add(MakeShared<FJsonValueObject>(Binding));
    }

    if (Payload.IsValid())
    {
        const TArray<TSharedPtr<FJsonValue>>* UserBindings = nullptr;
        if (Payload->TryGetArrayField(TEXT("bindings"), UserBindings) && UserBindings != nullptr)
        {
            for (const TSharedPtr<FJsonValue>& Item : *UserBindings)
            {
                if (Item.IsValid() && Item->Type == EJson::Object)
                {
                    Bindings.Add(Item);
                }
            }
        }
    }

    TSharedRef<FJsonObject> ModifyPayload = MakeShared<FJsonObject>();
    ModifyPayload->SetStringField(TEXT("widget_blueprint"), WidgetBlueprintPath);
    ModifyPayload->SetBoolField(TEXT("compile_after"), false);
    ModifyPayload->SetArrayField(TEXT("operations"), Operations);
    FAgentActionResult ModifyResult = HandleModifyWidgetTree(Request, ModifyPayload);
    if (!ModifyResult.bSuccess)
    {
        return ModifyResult;
    }

    TSharedRef<FJsonObject> BindPayload = MakeShared<FJsonObject>();
    BindPayload->SetStringField(TEXT("widget_blueprint"), WidgetBlueprintPath);
    BindPayload->SetBoolField(TEXT("compile_after"), bCompileAfter);
    BindPayload->SetArrayField(TEXT("bindings"), Bindings);
    FAgentActionResult BindResult = HandleBindWidgetEvents(Request, BindPayload);

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetStringField(TEXT("widget_blueprint"), WidgetBlueprintPath);
    Out->SetStringField(TEXT("template_id"), TemplateId);
    Out->SetStringField(TEXT("style_preset"), StylePreset);
    Out->SetArrayField(TEXT("operations"), Operations);
    Out->SetArrayField(TEXT("bindings"), Bindings);
    Out->SetStringField(TEXT("modify_message"), ModifyResult.Message);
    Out->SetStringField(TEXT("bind_message"), BindResult.Message);
    return {
        BindResult.bSuccess,
        BindResult.bSuccess ? TEXT("generate_widget_template completed.") : TEXT("generate_widget_template completed with failures."),
        SerializePayload(Out),
        BindResult.bSuccess ? TEXT("OK") : NormalizeErrorCode(BindResult)};
}

static FAgentActionResult HandleAnalyzeWidgetTree(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString WidgetBlueprintPath;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("widget_blueprint"), WidgetBlueprintPath);
        if (WidgetBlueprintPath.IsEmpty())
        {
            Payload->TryGetStringField(TEXT("blueprint_path"), WidgetBlueprintPath);
        }
    }
    if (WidgetBlueprintPath.IsEmpty())
    {
        return {false, TEXT("Missing widget_blueprint (or blueprint_path)."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    UWidgetBlueprint* WidgetBlueprint = LoadObject<UWidgetBlueprint>(nullptr, *WidgetBlueprintPath);
    if (WidgetBlueprint == nullptr || WidgetBlueprint->WidgetTree == nullptr)
    {
        return {false, FString::Printf(TEXT("Widget blueprint not found: %s"), *WidgetBlueprintPath), TEXT(""), TEXT("ASSET_NOT_FOUND")};
    }

    TArray<UWidget*> AllWidgets;
    WidgetBlueprint->WidgetTree->GetAllWidgets(AllWidgets);
    UWidget* RootWidget = WidgetBlueprint->WidgetTree->RootWidget;
    TArray<TSharedPtr<FJsonValue>> WidgetItems;
    TArray<TSharedPtr<FJsonValue>> LintItems;
    TSet<FString> BoundWidgetNames;

    if (WidgetBlueprint->UbergraphPages.Num() > 0)
    {
        UEdGraph* EventGraph = WidgetBlueprint->UbergraphPages[0];
        if (EventGraph != nullptr)
        {
            for (UEdGraphNode* Node : EventGraph->Nodes)
            {
                UK2Node_ComponentBoundEvent* BoundEventNode = Cast<UK2Node_ComponentBoundEvent>(Node);
                if (BoundEventNode != nullptr)
                {
                    const FString ComponentName = BoundEventNode->ComponentPropertyName.ToString();
                    if (!ComponentName.IsEmpty())
                    {
                        BoundWidgetNames.Add(ComponentName);
                    }
                }
            }
        }
    }

    if (RootWidget == nullptr)
    {
        TSharedRef<FJsonObject> MissingRoot = MakeShared<FJsonObject>();
        MissingRoot->SetStringField(TEXT("rule_id"), TEXT("missing_root"));
        MissingRoot->SetStringField(TEXT("severity"), TEXT("high"));
        MissingRoot->SetStringField(TEXT("message"), TEXT("Widget blueprint has no root widget."));
        LintItems.Add(MakeShared<FJsonValueObject>(MissingRoot));
    }

    int32 InteractiveControls = 0;
    int32 InteractiveBound = 0;
    for (UWidget* Widget : AllWidgets)
    {
        if (Widget == nullptr)
        {
            continue;
        }
        const FString WidgetName = Widget->GetName();
        const FString WidgetClass = Widget->GetClass() != nullptr ? Widget->GetClass()->GetName() : TEXT("<unknown>");
        const FString ParentName = Widget->GetParent() != nullptr ? Widget->GetParent()->GetName() : TEXT("");

        TSharedRef<FJsonObject> Item = MakeShared<FJsonObject>();
        Item->SetStringField(TEXT("name"), WidgetName);
        Item->SetStringField(TEXT("class"), WidgetClass);
        Item->SetStringField(TEXT("parent"), ParentName);
        WidgetItems.Add(MakeShared<FJsonValueObject>(Item));

        if (Widget != RootWidget && Widget->GetParent() == nullptr)
        {
            TSharedRef<FJsonObject> Orphan = MakeShared<FJsonObject>();
            Orphan->SetStringField(TEXT("rule_id"), TEXT("orphan_widget"));
            Orphan->SetStringField(TEXT("severity"), TEXT("medium"));
            Orphan->SetStringField(TEXT("message"), FString::Printf(TEXT("Widget '%s' has no parent."), *WidgetName));
            LintItems.Add(MakeShared<FJsonValueObject>(Orphan));
        }

        if (Cast<UButton>(Widget) != nullptr)
        {
            ++InteractiveControls;
            if (BoundWidgetNames.Contains(WidgetName))
            {
                ++InteractiveBound;
            }
            else
            {
                TSharedRef<FJsonObject> Unbound = MakeShared<FJsonObject>();
                Unbound->SetStringField(TEXT("rule_id"), TEXT("unbound_interactive_control"));
                Unbound->SetStringField(TEXT("severity"), TEXT("medium"));
                Unbound->SetStringField(TEXT("message"), FString::Printf(TEXT("Interactive widget '%s' has no bound event."), *WidgetName));
                LintItems.Add(MakeShared<FJsonValueObject>(Unbound));
            }
        }

        if (UCanvasPanelSlot* CanvasSlot = Cast<UCanvasPanelSlot>(Widget->Slot))
        {
            const FVector2D Size = CanvasSlot->GetSize();
            if (Size.X <= 1.0f || Size.Y <= 1.0f)
            {
                TSharedRef<FJsonObject> Sizing = MakeShared<FJsonObject>();
                Sizing->SetStringField(TEXT("rule_id"), TEXT("inaccessible_layout_sizing"));
                Sizing->SetStringField(TEXT("severity"), TEXT("low"));
                Sizing->SetStringField(TEXT("message"), FString::Printf(TEXT("Widget '%s' has near-zero canvas size."), *WidgetName));
                LintItems.Add(MakeShared<FJsonValueObject>(Sizing));
            }
        }
    }

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetStringField(TEXT("widget_blueprint"), WidgetBlueprintPath);
    Out->SetBoolField(TEXT("dry_run"), Request.bDryRun);
    Out->SetNumberField(TEXT("widget_count"), AllWidgets.Num());
    Out->SetArrayField(TEXT("widgets"), WidgetItems);
    Out->SetArrayField(TEXT("lint_findings"), LintItems);
    Out->SetNumberField(TEXT("interactive_controls"), InteractiveControls);
    Out->SetNumberField(TEXT("interactive_bound"), InteractiveBound);
    Out->SetNumberField(TEXT("binding_completeness"), InteractiveControls > 0 ? (100.0 * static_cast<double>(InteractiveBound) / static_cast<double>(InteractiveControls)) : 100.0);
    return BuildPassThroughResult(TEXT("analyze_widget_tree completed."), Out);
}

static void CollectAssetRelationshipPaths(
    IAssetRegistry& AssetRegistry,
    const FString& RootAssetPath,
    const int32 InDepth,
    const bool bReferencers,
    TSet<FString>& OutPaths)
{
    const int32 Depth = FMath::Clamp(InDepth, 1, 6);
    TArray<FName> Frontier;
    Frontier.Add(FName(*RootAssetPath));
    TSet<FName> Visited;
    Visited.Add(FName(*RootAssetPath));

    for (int32 Layer = 0; Layer < Depth && Frontier.Num() > 0; ++Layer)
    {
        TArray<FName> Next;
        for (const FName& PackageName : Frontier)
        {
            TArray<FName> Related;
            if (bReferencers)
            {
                AssetRegistry.GetReferencers(
                    PackageName,
                    Related,
                    UE::AssetRegistry::EDependencyCategory::Package,
                    UE::AssetRegistry::EDependencyQuery::NoRequirements);
            }
            else
            {
                AssetRegistry.GetDependencies(
                    PackageName,
                    Related,
                    UE::AssetRegistry::EDependencyCategory::Package,
                    UE::AssetRegistry::EDependencyQuery::NoRequirements);
            }

            for (const FName& Name : Related)
            {
                if (Name.IsNone() || Visited.Contains(Name))
                {
                    continue;
                }
                Visited.Add(Name);
                const FString Path = Name.ToString();
                if (!Path.IsEmpty())
                {
                    OutPaths.Add(Path);
                }
                Next.Add(Name);
            }
        }
        Frontier = MoveTemp(Next);
    }
}

static FAgentActionResult HandleListAssetDependencies(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString AssetPath;
    int32 Depth = 1;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("asset_path"), AssetPath);
        Depth = ReadIntOrDefault(Payload, TEXT("depth"), 1);
    }
    if (AssetPath.IsEmpty())
    {
        return {false, TEXT("list_asset_dependencies requires asset_path."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    FAssetRegistryModule& AssetRegistryModule = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry"));
    IAssetRegistry& AssetRegistry = AssetRegistryModule.Get();
    TSet<FString> Dependencies;
    CollectAssetRelationshipPaths(AssetRegistry, AssetPath, Depth, false, Dependencies);

    TArray<FString> Sorted = Dependencies.Array();
    Sorted.Sort();
    TArray<TSharedPtr<FJsonValue>> Values;
    for (const FString& Item : Sorted)
    {
        Values.Add(MakeShared<FJsonValueString>(Item));
    }
    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetStringField(TEXT("asset_path"), AssetPath);
    Out->SetNumberField(TEXT("depth"), Depth);
    Out->SetArrayField(TEXT("dependencies"), Values);
    Out->SetNumberField(TEXT("dependency_count"), Values.Num());
    Out->SetBoolField(TEXT("dry_run"), Request.bDryRun);
    return BuildPassThroughResult(TEXT("list_asset_dependencies completed."), Out);
}

static FAgentActionResult HandleListAssetReferencers(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString AssetPath;
    int32 Depth = 1;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("asset_path"), AssetPath);
        Depth = ReadIntOrDefault(Payload, TEXT("depth"), 1);
    }
    if (AssetPath.IsEmpty())
    {
        return {false, TEXT("list_asset_referencers requires asset_path."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    FAssetRegistryModule& AssetRegistryModule = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry"));
    IAssetRegistry& AssetRegistry = AssetRegistryModule.Get();
    TSet<FString> Referencers;
    CollectAssetRelationshipPaths(AssetRegistry, AssetPath, Depth, true, Referencers);

    TArray<FString> Sorted = Referencers.Array();
    Sorted.Sort();
    TArray<TSharedPtr<FJsonValue>> Values;
    for (const FString& Item : Sorted)
    {
        Values.Add(MakeShared<FJsonValueString>(Item));
    }
    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetStringField(TEXT("asset_path"), AssetPath);
    Out->SetNumberField(TEXT("depth"), Depth);
    Out->SetArrayField(TEXT("referencers"), Values);
    Out->SetNumberField(TEXT("referencer_count"), Values.Num());
    Out->SetBoolField(TEXT("dry_run"), Request.bDryRun);
    return BuildPassThroughResult(TEXT("list_asset_referencers completed."), Out);
}

static FAgentActionResult HandleAnalyzeAssetImpact(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString AssetPath;
    FString ChangeType = TEXT("modify");
    int32 Depth = 2;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("asset_path"), AssetPath);
        Payload->TryGetStringField(TEXT("change_type"), ChangeType);
        Depth = ReadIntOrDefault(Payload, TEXT("depth"), 2);
    }
    if (AssetPath.IsEmpty())
    {
        return {false, TEXT("analyze_asset_impact requires asset_path."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    FAssetRegistryModule& AssetRegistryModule = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry"));
    IAssetRegistry& AssetRegistry = AssetRegistryModule.Get();
    TSet<FString> Dependencies;
    TSet<FString> Referencers;
    CollectAssetRelationshipPaths(AssetRegistry, AssetPath, Depth, false, Dependencies);
    CollectAssetRelationshipPaths(AssetRegistry, AssetPath, Depth, true, Referencers);

    TArray<FString> Deps = Dependencies.Array();
    TArray<FString> Refs = Referencers.Array();
    Deps.Sort();
    Refs.Sort();

    TArray<TSharedPtr<FJsonValue>> DepValues;
    for (const FString& Item : Deps)
    {
        DepValues.Add(MakeShared<FJsonValueString>(Item));
    }
    TArray<TSharedPtr<FJsonValue>> RefValues;
    for (const FString& Item : Refs)
    {
        RefValues.Add(MakeShared<FJsonValueString>(Item));
    }

    TArray<FString> RiskFlags;
    if (Refs.Num() > 12)
    {
        RiskFlags.Add(TEXT("HIGH_REFERENCER_COUNT"));
    }
    if (Deps.Num() > 20)
    {
        RiskFlags.Add(TEXT("HIGH_DEPENDENCY_FANOUT"));
    }
    if (ChangeType.ToLower().StartsWith(TEXT("remove")))
    {
        RiskFlags.Add(TEXT("DESTRUCTIVE_CHANGE_TYPE"));
    }

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetStringField(TEXT("asset_path"), AssetPath);
    Out->SetStringField(TEXT("change_type"), ChangeType);
    Out->SetNumberField(TEXT("depth"), Depth);
    Out->SetArrayField(TEXT("dependencies"), DepValues);
    Out->SetArrayField(TEXT("referencers"), RefValues);
    Out->SetArrayField(TEXT("risk_flags"), [&RiskFlags]() {
        TArray<TSharedPtr<FJsonValue>> Values;
        for (const FString& Flag : RiskFlags)
        {
            Values.Add(MakeShared<FJsonValueString>(Flag));
        }
        return Values;
    }());
    Out->SetNumberField(TEXT("risk_score"), static_cast<double>(Refs.Num() * 2 + Deps.Num()));
    Out->SetBoolField(TEXT("dry_run"), Request.bDryRun);
    return BuildPassThroughResult(TEXT("analyze_asset_impact completed."), Out);
}

static FAgentActionResult HandleAnalyzeProjectHotspots(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString PackagePath = TEXT("/Game");
    bool bRecursive = true;
    int32 MaxAssets = 250;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("package_path"), PackagePath);
        Payload->TryGetBoolField(TEXT("recursive"), bRecursive);
        MaxAssets = ReadIntOrDefault(Payload, TEXT("max_assets"), 250);
    }
    MaxAssets = FMath::Clamp(MaxAssets, 1, 2000);

    FARFilter Filter;
    Filter.PackagePaths.Add(*PackagePath);
    Filter.bRecursivePaths = bRecursive;
    Filter.bRecursiveClasses = true;

    FAssetRegistryModule& AssetRegistryModule = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry"));
    IAssetRegistry& AssetRegistry = AssetRegistryModule.Get();
    TArray<FAssetData> Assets;
    AssetRegistry.GetAssets(Filter, Assets);

    TArray<TSharedPtr<FJsonValue>> Hotspots;
    int32 Processed = 0;
    for (const FAssetData& Asset : Assets)
    {
        if (Processed >= MaxAssets)
        {
            break;
        }
        ++Processed;
        const FString PackageName = Asset.PackageName.ToString();
        TSet<FString> Dependencies;
        TSet<FString> Referencers;
        CollectAssetRelationshipPaths(AssetRegistry, PackageName, 1, false, Dependencies);
        CollectAssetRelationshipPaths(AssetRegistry, PackageName, 1, true, Referencers);

        const bool bBlueprint = Asset.AssetClassPath.ToString().ToLower().Contains(TEXT("blueprint"));
        const double Score = static_cast<double>(Referencers.Num() * 2 + Dependencies.Num() + (bBlueprint ? 3 : 0));
        TSharedRef<FJsonObject> Item = MakeShared<FJsonObject>();
        Item->SetStringField(TEXT("asset"), PackageName);
        Item->SetStringField(TEXT("class_path"), Asset.AssetClassPath.ToString());
        Item->SetNumberField(TEXT("dependency_count"), Dependencies.Num());
        Item->SetNumberField(TEXT("referencer_count"), Referencers.Num());
        Item->SetNumberField(TEXT("risk_score"), Score);
        Hotspots.Add(MakeShared<FJsonValueObject>(Item));
    }

    Hotspots.Sort([](const TSharedPtr<FJsonValue>& A, const TSharedPtr<FJsonValue>& B) {
        const TSharedPtr<FJsonObject> AO = A.IsValid() ? A->AsObject() : nullptr;
        const TSharedPtr<FJsonObject> BO = B.IsValid() ? B->AsObject() : nullptr;
        const double AV = AO.IsValid() ? AO->GetNumberField(TEXT("risk_score")) : 0.0;
        const double BV = BO.IsValid() ? BO->GetNumberField(TEXT("risk_score")) : 0.0;
        return AV > BV;
    });

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetStringField(TEXT("package_path"), PackagePath);
    Out->SetNumberField(TEXT("processed_assets"), Processed);
    Out->SetArrayField(TEXT("hotspot_items"), Hotspots);
    Out->SetBoolField(TEXT("dry_run"), Request.bDryRun);
    return BuildPassThroughResult(TEXT("analyze_project_hotspots completed."), Out);
}

static FAgentActionResult HandleGenerateLayoutFromTemplate(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString LayoutId = TEXT("city_grid");
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("layout_id"), LayoutId);
    }

    if (LayoutId.ToLower().Contains(TEXT("line")) || LayoutId.ToLower().Contains(TEXT("spline")))
    {
        return HandleLayoutAlongSpline(Request, Payload);
    }
    return HandleCreateLevelChunk(Request, Payload);
}

static FAgentActionResult HandleScatterAssetsWithConstraints(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString ClassPath = TEXT("/Script/Engine.StaticMeshActor");
    FString StaticMeshPath;
    FString FolderPath = TEXT("AgentGenerated/Scatter");
    int32 Count = ReadIntOrDefault(Payload, TEXT("count"), 100);
    Count = FMath::Clamp(Count, 1, 3000);

    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("class_path"), ClassPath);
        Payload->TryGetStringField(TEXT("static_mesh_path"), StaticMeshPath);
        Payload->TryGetStringField(TEXT("folder_path"), FolderPath);
    }

    FVector MinBounds(0.0f, 0.0f, 0.0f);
    FVector MaxBounds(5000.0f, 5000.0f, 0.0f);
    const TArray<TSharedPtr<FJsonValue>>* Bounds = nullptr;
    if (Payload.IsValid() && Payload->TryGetArrayField(TEXT("bounds"), Bounds) && Bounds != nullptr && Bounds->Num() == 4)
    {
        double X0 = 0.0;
        double Y0 = 0.0;
        double X1 = 5000.0;
        double Y1 = 5000.0;
        if ((*Bounds)[0]->TryGetNumber(X0) && (*Bounds)[1]->TryGetNumber(Y0) && (*Bounds)[2]->TryGetNumber(X1) && (*Bounds)[3]->TryGetNumber(Y1))
        {
            MinBounds = FVector(static_cast<float>(FMath::Min(X0, X1)), static_cast<float>(FMath::Min(Y0, Y1)), 0.0f);
            MaxBounds = FVector(static_cast<float>(FMath::Max(X0, X1)), static_cast<float>(FMath::Max(Y0, Y1)), 0.0f);
        }
    }

    const int32 Seed = ReadIntOrDefault(Payload, TEXT("seed"), 1337);
    FRandomStream Random(Seed);
    TArray<FString> Tags = ReadStringArray(Payload, TEXT("tags"));
    if (Tags.Num() == 0)
    {
        Tags.Add(TEXT("AgentScatter"));
    }

    TArray<TSharedPtr<FJsonValue>> Actors;
    Actors.Reserve(Count);
    for (int32 Index = 0; Index < Count; ++Index)
    {
        const float X = Random.FRandRange(MinBounds.X, MaxBounds.X);
        const float Y = Random.FRandRange(MinBounds.Y, MaxBounds.Y);
        const float Z = ReadFloatOrDefault(Payload, TEXT("base_z"), 0.0f);

        TSharedRef<FJsonObject> Spawn = MakeShared<FJsonObject>();
        Spawn->SetStringField(TEXT("class_path"), ClassPath);
        Spawn->SetStringField(TEXT("static_mesh_path"), StaticMeshPath);
        Spawn->SetStringField(TEXT("folder_path"), FolderPath);
        Spawn->SetStringField(TEXT("actor_label"), FString::Printf(TEXT("Scatter_%04d"), Index + 1));
        Spawn->SetArrayField(TEXT("location"), {MakeShared<FJsonValueNumber>(X), MakeShared<FJsonValueNumber>(Y), MakeShared<FJsonValueNumber>(Z)});

        TArray<TSharedPtr<FJsonValue>> TagValues;
        for (const FString& Tag : Tags)
        {
            TagValues.Add(MakeShared<FJsonValueString>(Tag));
        }
        Spawn->SetArrayField(TEXT("tags"), TagValues);
        Actors.Add(MakeShared<FJsonValueObject>(Spawn));
    }

    TSharedRef<FJsonObject> Batch = MakeShared<FJsonObject>();
    Batch->SetArrayField(TEXT("actors"), Actors);
    return HandleBatchSpawnActors(Request, Batch);
}

static FAgentActionResult HandleClearGeneratedLayoutByToken(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString CleanupToken;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("cleanup_token"), CleanupToken);
    }
    if (CleanupToken.IsEmpty())
    {
        return {false, TEXT("clear_generated_layout_by_token requires cleanup_token."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    TSharedRef<FJsonObject> Query = MakeShared<FJsonObject>();
    Query->SetBoolField(TEXT("only_generated"), false);
    Query->SetArrayField(TEXT("tags"), {MakeShared<FJsonValueString>(CleanupToken)});
    return HandleClearMapLayout(Request, Query);
}

static FString NormalizeBlueprintObjectPath(const FString& BlueprintPathOrObjectPath)
{
    if (BlueprintPathOrObjectPath.Contains(TEXT(".")))
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

static UBlueprint* ResolveBlueprintAsset(const FString& BlueprintPathOrObjectPath)
{
    const FString ObjectPath = NormalizeBlueprintObjectPath(BlueprintPathOrObjectPath);
    UBlueprint* Blueprint = FindObject<UBlueprint>(nullptr, *ObjectPath);
    if (Blueprint == nullptr)
    {
        Blueprint = LoadObject<UBlueprint>(nullptr, *ObjectPath);
    }
    return Blueprint;
}

static AActor* FindWorldActorByLabelOrName(UWorld* World, const FString& ActorLabelOrName)
{
    if (World == nullptr || ActorLabelOrName.IsEmpty())
    {
        return nullptr;
    }
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        AActor* Actor = *It;
        if (Actor == nullptr)
        {
            continue;
        }
        if (Actor->GetActorLabel().Equals(ActorLabelOrName, ESearchCase::IgnoreCase)
            || Actor->GetName().Equals(ActorLabelOrName, ESearchCase::IgnoreCase))
        {
            return Actor;
        }
    }
    return nullptr;
}

static bool SetReflectedScalarProperty(UObject* TargetObject, const FString& PropertyName, const TSharedPtr<FJsonValue>& Value, FString& OutError)
{
    OutError.Reset();
    if (TargetObject == nullptr || PropertyName.IsEmpty() || !Value.IsValid())
    {
        OutError = TEXT("Target object/property/value are required.");
        return false;
    }

    FProperty* Property = TargetObject->GetClass()->FindPropertyByName(FName(*PropertyName));
    if (Property == nullptr)
    {
        OutError = FString::Printf(TEXT("Property not found: %s"), *PropertyName);
        return false;
    }

    void* ValuePtr = Property->ContainerPtrToValuePtr<void>(TargetObject);
    if (FBoolProperty* BoolProp = CastField<FBoolProperty>(Property))
    {
        bool bValue = false;
        if (!Value->TryGetBool(bValue))
        {
            OutError = TEXT("Expected boolean value.");
            return false;
        }
        BoolProp->SetPropertyValue(ValuePtr, bValue);
        return true;
    }
    if (FIntProperty* IntProp = CastField<FIntProperty>(Property))
    {
        double Number = 0.0;
        if (!Value->TryGetNumber(Number))
        {
            OutError = TEXT("Expected numeric value.");
            return false;
        }
        IntProp->SetPropertyValue(ValuePtr, static_cast<int32>(Number));
        return true;
    }
    if (FFloatProperty* FloatProp = CastField<FFloatProperty>(Property))
    {
        double Number = 0.0;
        if (!Value->TryGetNumber(Number))
        {
            OutError = TEXT("Expected numeric value.");
            return false;
        }
        FloatProp->SetPropertyValue(ValuePtr, static_cast<float>(Number));
        return true;
    }
    if (FDoubleProperty* DoubleProp = CastField<FDoubleProperty>(Property))
    {
        double Number = 0.0;
        if (!Value->TryGetNumber(Number))
        {
            OutError = TEXT("Expected numeric value.");
            return false;
        }
        DoubleProp->SetPropertyValue(ValuePtr, Number);
        return true;
    }
    if (FStrProperty* StrProp = CastField<FStrProperty>(Property))
    {
        FString StringValue;
        if (!Value->TryGetString(StringValue))
        {
            OutError = TEXT("Expected string value.");
            return false;
        }
        StrProp->SetPropertyValue(ValuePtr, StringValue);
        return true;
    }
    if (FNameProperty* NameProp = CastField<FNameProperty>(Property))
    {
        FString StringValue;
        if (!Value->TryGetString(StringValue))
        {
            OutError = TEXT("Expected string value.");
            return false;
        }
        NameProp->SetPropertyValue(ValuePtr, FName(*StringValue));
        return true;
    }
    if (FTextProperty* TextProp = CastField<FTextProperty>(Property))
    {
        FString StringValue;
        if (!Value->TryGetString(StringValue))
        {
            OutError = TEXT("Expected string value.");
            return false;
        }
        TextProp->SetPropertyValue(ValuePtr, FText::FromString(StringValue));
        return true;
    }

    OutError = FString::Printf(TEXT("Unsupported property type: %s"), *Property->GetClass()->GetName());
    return false;
}

static FAgentActionResult HandleSetReflectedProperty(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString TargetType = TEXT("blueprint_cdo");
    FString PropertyName;
    bool bCompileAfter = false;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("target_type"), TargetType);
        Payload->TryGetStringField(TEXT("property_name"), PropertyName);
        Payload->TryGetBoolField(TEXT("compile_after"), bCompileAfter);
    }
    if (PropertyName.IsEmpty())
    {
        return {false, TEXT("set_reflected_property requires property_name."), TEXT(""), TEXT("MISSING_FIELD")};
    }
    const TSharedPtr<FJsonValue>* ValuePtr = Payload.IsValid() ? Payload->Values.Find(TEXT("value")) : nullptr;
    if (ValuePtr == nullptr || !ValuePtr->IsValid())
    {
        return {false, TEXT("set_reflected_property requires value."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    UObject* TargetObject = nullptr;
    UBlueprint* TargetBlueprint = nullptr;
    FString TargetPath;
    if (TargetType.Equals(TEXT("blueprint_cdo"), ESearchCase::IgnoreCase))
    {
        FString BlueprintPath;
        if (Payload.IsValid())
        {
            Payload->TryGetStringField(TEXT("blueprint_path"), BlueprintPath);
        }
        if (BlueprintPath.IsEmpty())
        {
            return {false, TEXT("blueprint_cdo target requires blueprint_path."), TEXT(""), TEXT("MISSING_FIELD")};
        }
        TargetBlueprint = ResolveBlueprintAsset(BlueprintPath);
        if (TargetBlueprint == nullptr || TargetBlueprint->GeneratedClass == nullptr)
        {
            return {false, TEXT("Failed to resolve blueprint generated class."), TEXT(""), TEXT("ASSET_NOT_FOUND")};
        }
        TargetObject = TargetBlueprint->GeneratedClass->GetDefaultObject();
        TargetPath = BlueprintPath;
    }
    else if (TargetType.Equals(TEXT("component_template"), ESearchCase::IgnoreCase))
    {
        FString BlueprintPath;
        FString ComponentName;
        if (Payload.IsValid())
        {
            Payload->TryGetStringField(TEXT("blueprint_path"), BlueprintPath);
            Payload->TryGetStringField(TEXT("component_name"), ComponentName);
        }
        if (BlueprintPath.IsEmpty() || ComponentName.IsEmpty())
        {
            return {false, TEXT("component_template target requires blueprint_path and component_name."), TEXT(""), TEXT("MISSING_FIELD")};
        }
        TargetBlueprint = ResolveBlueprintAsset(BlueprintPath);
        if (TargetBlueprint == nullptr || TargetBlueprint->SimpleConstructionScript == nullptr)
        {
            return {false, TEXT("Blueprint has no component construction script."), TEXT(""), TEXT("ASSET_NOT_FOUND")};
        }
        for (USCS_Node* Node : TargetBlueprint->SimpleConstructionScript->GetAllNodes())
        {
            if (Node == nullptr)
            {
                continue;
            }
            const FString VariableName = Node->GetVariableName().ToString();
            const FString TemplateName = Node->ComponentTemplate != nullptr ? Node->ComponentTemplate->GetName() : TEXT("");
            if (VariableName.Equals(ComponentName, ESearchCase::IgnoreCase) || TemplateName.Equals(ComponentName, ESearchCase::IgnoreCase))
            {
                TargetObject = Node->ComponentTemplate;
                break;
            }
        }
        if (TargetObject == nullptr)
        {
            return {false, TEXT("Component template not found."), TEXT(""), TEXT("NOT_FOUND")};
        }
        TargetPath = BlueprintPath;
    }
    else if (TargetType.Equals(TEXT("world_actor"), ESearchCase::IgnoreCase))
    {
        FString ActorId;
        if (Payload.IsValid())
        {
            Payload->TryGetStringField(TEXT("actor"), ActorId);
            if (ActorId.IsEmpty())
            {
                Payload->TryGetStringField(TEXT("actor_label"), ActorId);
            }
        }
        if (ActorId.IsEmpty())
        {
            return {false, TEXT("world_actor target requires actor or actor_label."), TEXT(""), TEXT("MISSING_FIELD")};
        }
        UWorld* EditorWorld = (GEditor != nullptr) ? GEditor->GetEditorWorldContext().World() : nullptr;
        if (EditorWorld == nullptr)
        {
            return {false, TEXT("No editor world found."), TEXT(""), TEXT("WORLD_NOT_FOUND")};
        }
        TargetObject = FindWorldActorByLabelOrName(EditorWorld, ActorId);
        if (TargetObject == nullptr)
        {
            return {false, TEXT("Actor not found in editor world."), TEXT(""), TEXT("NOT_FOUND")};
        }
        TargetPath = TargetObject->GetPathName();
    }
    else
    {
        return {false, TEXT("Unsupported target_type. Use blueprint_cdo, component_template, or world_actor."), TEXT(""), TEXT("INVALID_FIELD")};
    }

    FString SetError;
    if (Request.bDryRun)
    {
        const bool bOk = SetReflectedScalarProperty(TargetObject, PropertyName, *ValuePtr, SetError);
        if (bOk)
        {
            return {true, TEXT("Dry run property validation succeeded."), TEXT(""), TEXT("OK")};
        }
        return {false, SetError, TEXT(""), TEXT("INVALID_FIELD")};
    }

    TargetObject->Modify();
    const bool bApplied = SetReflectedScalarProperty(TargetObject, PropertyName, *ValuePtr, SetError);
    if (!bApplied)
    {
        return {false, SetError, TEXT(""), TEXT("INVALID_FIELD")};
    }

    if (TargetBlueprint != nullptr)
    {
        FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(TargetBlueprint);
        TargetBlueprint->MarkPackageDirty();
        if (bCompileAfter)
        {
            FKismetEditorUtilities::CompileBlueprint(TargetBlueprint);
        }
    }
    else if (TargetObject->GetOutermost() != nullptr)
    {
        TargetObject->GetOutermost()->MarkPackageDirty();
    }

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetStringField(TEXT("target_type"), TargetType);
    Out->SetStringField(TEXT("target"), TargetPath);
    Out->SetStringField(TEXT("property_name"), PropertyName);
    Out->SetBoolField(TEXT("compiled"), TargetBlueprint != nullptr && bCompileAfter);
    return BuildPassThroughResult(TEXT("set_reflected_property completed."), Out);
}

static FAgentActionResult HandleCreateBlueprintFunction(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString BlueprintPath;
    FString FunctionName;
    FString Category;
    bool bCompileAfter = true;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("blueprint_path"), BlueprintPath);
        Payload->TryGetStringField(TEXT("function_name"), FunctionName);
        Payload->TryGetStringField(TEXT("category"), Category);
        Payload->TryGetBoolField(TEXT("compile_after"), bCompileAfter);
    }
    if (BlueprintPath.IsEmpty() || FunctionName.IsEmpty())
    {
        return {false, TEXT("create_blueprint_function requires blueprint_path and function_name."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    UBlueprint* Blueprint = ResolveBlueprintAsset(BlueprintPath);
    if (Blueprint == nullptr)
    {
        return {false, TEXT("Blueprint not found."), TEXT(""), TEXT("ASSET_NOT_FOUND")};
    }
    for (UEdGraph* Graph : Blueprint->FunctionGraphs)
    {
        if (Graph != nullptr && Graph->GetName().Equals(FunctionName, ESearchCase::IgnoreCase))
        {
            return {false, TEXT("Function graph already exists."), TEXT(""), TEXT("ALREADY_EXISTS")};
        }
    }
    if (Request.bDryRun)
    {
        TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
        Out->SetStringField(TEXT("blueprint"), Blueprint->GetPathName());
        Out->SetStringField(TEXT("function_name"), FunctionName);
        Out->SetStringField(TEXT("category"), Category);
        return BuildPassThroughResult(TEXT("Dry run function graph validation succeeded."), Out);
    }

    Blueprint->Modify();
    UEdGraph* NewGraph = FBlueprintEditorUtils::CreateNewGraph(
        Blueprint,
        FName(*FunctionName),
        UEdGraph::StaticClass(),
        UEdGraphSchema_K2::StaticClass());
    if (NewGraph == nullptr)
    {
        return {false, TEXT("Failed to create function graph."), TEXT(""), TEXT("EXEC_FAILED")};
    }
    FBlueprintEditorUtils::AddFunctionGraph(Blueprint, NewGraph, true, static_cast<UFunction*>(nullptr));
    FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
    Blueprint->MarkPackageDirty();
    if (bCompileAfter)
    {
        FKismetEditorUtilities::CompileBlueprint(Blueprint);
    }

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetStringField(TEXT("blueprint"), Blueprint->GetPathName());
    Out->SetStringField(TEXT("function_name"), FunctionName);
    Out->SetStringField(TEXT("category"), Category);
    Out->SetBoolField(TEXT("compiled"), bCompileAfter);
    return BuildPassThroughResult(TEXT("create_blueprint_function completed."), Out);
}

static FAgentActionResult HandleCreateBlueprintMacro(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString BlueprintPath;
    FString MacroName;
    FString Category;
    bool bCompileAfter = true;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("blueprint_path"), BlueprintPath);
        Payload->TryGetStringField(TEXT("macro_name"), MacroName);
        Payload->TryGetStringField(TEXT("category"), Category);
        Payload->TryGetBoolField(TEXT("compile_after"), bCompileAfter);
    }
    if (BlueprintPath.IsEmpty() || MacroName.IsEmpty())
    {
        return {false, TEXT("create_blueprint_macro requires blueprint_path and macro_name."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    UBlueprint* Blueprint = ResolveBlueprintAsset(BlueprintPath);
    if (Blueprint == nullptr)
    {
        return {false, TEXT("Blueprint not found."), TEXT(""), TEXT("ASSET_NOT_FOUND")};
    }
    for (UEdGraph* Graph : Blueprint->MacroGraphs)
    {
        if (Graph != nullptr && Graph->GetName().Equals(MacroName, ESearchCase::IgnoreCase))
        {
            return {false, TEXT("Macro graph already exists."), TEXT(""), TEXT("ALREADY_EXISTS")};
        }
    }
    if (Request.bDryRun)
    {
        TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
        Out->SetStringField(TEXT("blueprint"), Blueprint->GetPathName());
        Out->SetStringField(TEXT("macro_name"), MacroName);
        Out->SetStringField(TEXT("category"), Category);
        return BuildPassThroughResult(TEXT("Dry run macro graph validation succeeded."), Out);
    }

    Blueprint->Modify();
    UEdGraph* NewGraph = FBlueprintEditorUtils::CreateNewGraph(
        Blueprint,
        FName(*MacroName),
        UEdGraph::StaticClass(),
        UEdGraphSchema_K2::StaticClass());
    if (NewGraph == nullptr)
    {
        return {false, TEXT("Failed to create macro graph."), TEXT(""), TEXT("EXEC_FAILED")};
    }
    FBlueprintEditorUtils::AddMacroGraph(Blueprint, NewGraph, true, nullptr);
    FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
    Blueprint->MarkPackageDirty();
    if (bCompileAfter)
    {
        FKismetEditorUtilities::CompileBlueprint(Blueprint);
    }

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetStringField(TEXT("blueprint"), Blueprint->GetPathName());
    Out->SetStringField(TEXT("macro_name"), MacroName);
    Out->SetStringField(TEXT("category"), Category);
    Out->SetBoolField(TEXT("compiled"), bCompileAfter);
    return BuildPassThroughResult(TEXT("create_blueprint_macro completed."), Out);
}

static UEdGraph* ResolveBlueprintGraph(UBlueprint* Blueprint, const FString& GraphName)
{
    if (Blueprint == nullptr)
    {
        return nullptr;
    }
    if (!GraphName.IsEmpty())
    {
        for (UEdGraph* Graph : Blueprint->UbergraphPages)
        {
            if (Graph != nullptr && Graph->GetName().Equals(GraphName, ESearchCase::IgnoreCase))
            {
                return Graph;
            }
        }
        for (UEdGraph* Graph : Blueprint->FunctionGraphs)
        {
            if (Graph != nullptr && Graph->GetName().Equals(GraphName, ESearchCase::IgnoreCase))
            {
                return Graph;
            }
        }
        for (UEdGraph* Graph : Blueprint->MacroGraphs)
        {
            if (Graph != nullptr && Graph->GetName().Equals(GraphName, ESearchCase::IgnoreCase))
            {
                return Graph;
            }
        }
        return nullptr;
    }

    if (Blueprint->UbergraphPages.Num() > 0 && Blueprint->UbergraphPages[0] != nullptr)
    {
        return Blueprint->UbergraphPages[0];
    }
    if (Blueprint->FunctionGraphs.Num() > 0 && Blueprint->FunctionGraphs[0] != nullptr)
    {
        return Blueprint->FunctionGraphs[0];
    }
    if (Blueprint->MacroGraphs.Num() > 0 && Blueprint->MacroGraphs[0] != nullptr)
    {
        return Blueprint->MacroGraphs[0];
    }
    return nullptr;
}

static UEdGraphNode* FindNodeByNameOrTitle(const UEdGraph* Graph, const FString& NodeName, const FString& NodeTitleContains)
{
    if (Graph == nullptr)
    {
        return nullptr;
    }
    if (!NodeName.IsEmpty())
    {
        for (UEdGraphNode* Node : Graph->Nodes)
        {
            if (Node != nullptr && Node->GetName().Equals(NodeName, ESearchCase::IgnoreCase))
            {
                return Node;
            }
        }
    }
    if (!NodeTitleContains.IsEmpty())
    {
        for (UEdGraphNode* Node : Graph->Nodes)
        {
            if (Node == nullptr)
            {
                continue;
            }
            const FString Title = Node->GetNodeTitle(ENodeTitleType::ListView).ToString();
            if (Title.Contains(NodeTitleContains, ESearchCase::IgnoreCase))
            {
                return Node;
            }
        }
    }
    return nullptr;
}

static UEdGraphPin* FindNodePinByName(const UEdGraphNode* Node, const FString& PinName)
{
    if (Node == nullptr || PinName.IsEmpty())
    {
        return nullptr;
    }
    for (UEdGraphPin* Pin : Node->Pins)
    {
        if (Pin != nullptr && Pin->PinName.ToString().Equals(PinName, ESearchCase::IgnoreCase))
        {
            return Pin;
        }
    }
    return nullptr;
}

static bool IsWildcardPin(const UEdGraphPin* Pin)
{
    if (Pin == nullptr)
    {
        return false;
    }
    return Pin->PinType.PinCategory == UEdGraphSchema_K2::PC_Wildcard;
}

static bool ValidatePinTypeContract(const UEdGraphPin* FromPin, const UEdGraphPin* ToPin, FString& OutReason)
{
    OutReason.Reset();
    if (FromPin == nullptr || ToPin == nullptr)
    {
        OutReason = TEXT("Source/target pin missing.");
        return false;
    }
    if (FromPin->Direction != EGPD_Output || ToPin->Direction != EGPD_Input)
    {
        OutReason = TEXT("Connections must be output -> input.");
        return false;
    }

    const FName ExecCategory = UEdGraphSchema_K2::PC_Exec;
    const bool bFromExec = FromPin->PinType.PinCategory == ExecCategory;
    const bool bToExec = ToPin->PinType.PinCategory == ExecCategory;
    if (bFromExec != bToExec)
    {
        OutReason = TEXT("Cannot connect exec pin to data pin.");
        return false;
    }
    if (bFromExec && bToExec)
    {
        return true;
    }

    if (!IsWildcardPin(FromPin) && !IsWildcardPin(ToPin))
    {
        if (FromPin->PinType.PinCategory != ToPin->PinType.PinCategory)
        {
            OutReason = TEXT("Pin categories are incompatible.");
            return false;
        }
        if (FromPin->PinType.ContainerType != ToPin->PinType.ContainerType)
        {
            OutReason = TEXT("Pin container types are incompatible.");
            return false;
        }
        UObject* FromSubObj = FromPin->PinType.PinSubCategoryObject.Get();
        UObject* ToSubObj = ToPin->PinType.PinSubCategoryObject.Get();
        if (FromSubObj != nullptr && ToSubObj != nullptr)
        {
            const UClass* FromClass = Cast<UClass>(FromSubObj);
            const UClass* ToClass = Cast<UClass>(ToSubObj);
            if (FromClass != nullptr && ToClass != nullptr)
            {
                const bool bAssignable = FromClass == ToClass || FromClass->IsChildOf(ToClass) || ToClass->IsChildOf(FromClass);
                if (!bAssignable)
                {
                    OutReason = TEXT("Pin object types are incompatible.");
                    return false;
                }
            }
            else if (FromSubObj != ToSubObj)
            {
                OutReason = TEXT("Pin subcategory objects are incompatible.");
                return false;
            }
        }
    }
    return true;
}

static FAgentActionResult HandleWireBlueprintPins(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString BlueprintPath;
    FString GraphName;
    FString Operation = TEXT("connect");
    FString FromNodeName;
    FString FromNodeTitleContains;
    FString FromPinName;
    FString ToNodeName;
    FString ToNodeTitleContains;
    FString ToPinName;
    bool bCompileAfter = true;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("blueprint_path"), BlueprintPath);
        Payload->TryGetStringField(TEXT("graph_name"), GraphName);
        Payload->TryGetStringField(TEXT("operation"), Operation);
        Payload->TryGetStringField(TEXT("from_node_name"), FromNodeName);
        Payload->TryGetStringField(TEXT("from_node_title_contains"), FromNodeTitleContains);
        Payload->TryGetStringField(TEXT("from_pin_name"), FromPinName);
        Payload->TryGetStringField(TEXT("to_node_name"), ToNodeName);
        Payload->TryGetStringField(TEXT("to_node_title_contains"), ToNodeTitleContains);
        Payload->TryGetStringField(TEXT("to_pin_name"), ToPinName);
        Payload->TryGetBoolField(TEXT("compile_after"), bCompileAfter);
    }
    if (BlueprintPath.IsEmpty() || FromPinName.IsEmpty() || ToPinName.IsEmpty())
    {
        return {false, TEXT("wire_blueprint_pins requires blueprint_path, from_pin_name, and to_pin_name."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    UBlueprint* Blueprint = ResolveBlueprintAsset(BlueprintPath);
    UEdGraph* Graph = ResolveBlueprintGraph(Blueprint, GraphName);
    if (Blueprint == nullptr || Graph == nullptr)
    {
        return {false, TEXT("Blueprint or target graph not found."), TEXT(""), TEXT("GRAPH_NOT_FOUND")};
    }

    UEdGraphNode* FromNode = FindNodeByNameOrTitle(Graph, FromNodeName, FromNodeTitleContains);
    UEdGraphNode* ToNode = FindNodeByNameOrTitle(Graph, ToNodeName, ToNodeTitleContains);
    if (FromNode == nullptr || ToNode == nullptr)
    {
        return {false, TEXT("Source or target node was not found in graph."), TEXT(""), TEXT("NODE_NOT_FOUND")};
    }

    UEdGraphPin* FromPin = FindNodePinByName(FromNode, FromPinName);
    UEdGraphPin* ToPin = FindNodePinByName(ToNode, ToPinName);
    if (FromPin == nullptr || ToPin == nullptr)
    {
        return {false, TEXT("Source or target pin was not found on selected node."), TEXT(""), TEXT("PIN_NOT_FOUND")};
    }

    const UEdGraphSchema_K2* K2Schema = Cast<UEdGraphSchema_K2>(Graph->GetSchema());
    if (K2Schema == nullptr)
    {
        return {false, TEXT("Target graph does not use K2 schema."), TEXT(""), TEXT("SCHEMA_NOT_SUPPORTED")};
    }

    const bool bDisconnect = Operation.Equals(TEXT("disconnect"), ESearchCase::IgnoreCase);
    bool bChanged = false;
    if (bDisconnect)
    {
        const bool bHadLink = FromPin->LinkedTo.Contains(ToPin);
        if (!Request.bDryRun && bHadLink)
        {
            Blueprint->Modify();
            Graph->Modify();
            FromPin->BreakLinkTo(ToPin);
            bChanged = true;
        }
        TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
        Out->SetStringField(TEXT("blueprint"), Blueprint->GetPathName());
        Out->SetStringField(TEXT("graph_name"), Graph->GetName());
        Out->SetStringField(TEXT("operation"), TEXT("disconnect"));
        Out->SetBoolField(TEXT("link_existed"), bHadLink);
        Out->SetBoolField(TEXT("changed"), bChanged);
        return BuildPassThroughResult(bHadLink ? TEXT("wire_blueprint_pins disconnect succeeded.") : TEXT("wire_blueprint_pins disconnect found no existing link."), Out);
    }

    FString ContractReason;
    if (!ValidatePinTypeContract(FromPin, ToPin, ContractReason))
    {
        return {false, FString::Printf(TEXT("Pin contract validation failed: %s"), *ContractReason), TEXT(""), TEXT("PIN_CONTRACT_INVALID")};
    }

    const FPinConnectionResponse CanConnect = K2Schema->CanCreateConnection(FromPin, ToPin);
    if (CanConnect.Response == ECanCreateConnectionResponse::CONNECT_RESPONSE_DISALLOW)
    {
        return {false, FString::Printf(TEXT("Connection disallowed: %s"), *CanConnect.Message.ToString()), TEXT(""), TEXT("PIN_CONNECT_DISALLOWED")};
    }

    bool bConnected = FromPin->LinkedTo.Contains(ToPin);
    if (!Request.bDryRun)
    {
        Blueprint->Modify();
        Graph->Modify();
        bConnected = K2Schema->TryCreateConnection(FromPin, ToPin);
        bChanged = bConnected;
        if (bConnected)
        {
            FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
            Blueprint->MarkPackageDirty();
            if (bCompileAfter)
            {
                FKismetEditorUtilities::CompileBlueprint(Blueprint);
            }
        }
    }

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetStringField(TEXT("blueprint"), Blueprint->GetPathName());
    Out->SetStringField(TEXT("graph_name"), Graph->GetName());
    Out->SetStringField(TEXT("operation"), TEXT("connect"));
    Out->SetBoolField(TEXT("connected"), bConnected || Request.bDryRun);
    Out->SetBoolField(TEXT("changed"), bChanged);
    Out->SetStringField(TEXT("connection_response"), CanConnect.Message.ToString());
    Out->SetBoolField(TEXT("compiled"), !Request.bDryRun && bCompileAfter && bConnected);
    return BuildPassThroughResult(Request.bDryRun ? TEXT("Dry run pin connection validation succeeded.") : TEXT("wire_blueprint_pins connect completed."), Out);
}

static FAgentActionResult HandleBlueprintNodeAuthoring(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString BlueprintPath;
    FString GraphName;
    FString Operation = TEXT("spawn_function_call");
    FString NodeName;
    FString TargetNodeName;
    FString TargetNodeTitleContains;
    FString FunctionClassPath;
    FString FunctionName;
    FString CustomEventName;
    FVector2D NodePosition(0.0f, 0.0f);
    bool bCompileAfter = true;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("blueprint_path"), BlueprintPath);
        Payload->TryGetStringField(TEXT("graph_name"), GraphName);
        Payload->TryGetStringField(TEXT("operation"), Operation);
        Payload->TryGetStringField(TEXT("node_name"), NodeName);
        Payload->TryGetStringField(TEXT("target_node_name"), TargetNodeName);
        Payload->TryGetStringField(TEXT("target_node_title_contains"), TargetNodeTitleContains);
        Payload->TryGetStringField(TEXT("function_class_path"), FunctionClassPath);
        Payload->TryGetStringField(TEXT("function_name"), FunctionName);
        Payload->TryGetStringField(TEXT("custom_event_name"), CustomEventName);
        Payload->TryGetBoolField(TEXT("compile_after"), bCompileAfter);
        ReadVector2Field(Payload, TEXT("node_position"), NodePosition);
    }
    const bool bReplace = Operation.Equals(TEXT("replace_function_call"), ESearchCase::IgnoreCase);
    const bool bSpawnFunction = Operation.Equals(TEXT("spawn_function_call"), ESearchCase::IgnoreCase) || bReplace;
    const bool bSpawnCustomEvent = Operation.Equals(TEXT("spawn_custom_event"), ESearchCase::IgnoreCase);
    const bool bSpawnBranchNode = Operation.Equals(TEXT("spawn_branch_node"), ESearchCase::IgnoreCase);
    if (!bSpawnFunction && !bSpawnCustomEvent && !bSpawnBranchNode)
    {
        return {false, FString::Printf(TEXT("Unsupported node authoring operation: %s"), *Operation), TEXT(""), TEXT("INVALID_FIELD")};
    }
    if (BlueprintPath.IsEmpty())
    {
        return {false, TEXT("blueprint_node_authoring requires blueprint_path."), TEXT(""), TEXT("MISSING_FIELD")};
    }
    if (bSpawnFunction && (FunctionClassPath.IsEmpty() || FunctionName.IsEmpty()))
    {
        return {false, TEXT("blueprint_node_authoring requires blueprint_path, function_class_path, and function_name."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    UBlueprint* Blueprint = ResolveBlueprintAsset(BlueprintPath);
    UEdGraph* Graph = ResolveBlueprintGraph(Blueprint, GraphName);
    if (Blueprint == nullptr || Graph == nullptr)
    {
        return {false, TEXT("Blueprint or target graph not found."), TEXT(""), TEXT("GRAPH_NOT_FOUND")};
    }

    UClass* OwnerClass = nullptr;
    UFunction* TargetFunction = nullptr;
    if (bSpawnFunction)
    {
        OwnerClass = LoadObject<UClass>(nullptr, *FunctionClassPath);
        if (OwnerClass == nullptr)
        {
            OwnerClass = FindObject<UClass>(nullptr, *FunctionClassPath);
        }
        if (OwnerClass == nullptr)
        {
            return {false, TEXT("function_class_path could not be resolved."), TEXT(""), TEXT("ASSET_NOT_FOUND")};
        }
        TargetFunction = OwnerClass->FindFunctionByName(FName(*FunctionName));
        if (TargetFunction == nullptr)
        {
            return {false, TEXT("function_name was not found on function_class_path."), TEXT(""), TEXT("NOT_FOUND")};
        }
    }
    if (bReplace && TargetNodeName.IsEmpty() && TargetNodeTitleContains.IsEmpty())
    {
        return {false, TEXT("replace_function_call requires target_node_name or target_node_title_contains."), TEXT(""), TEXT("MISSING_FIELD")};
    }
    UEdGraphNode* ReplaceNode = nullptr;
    if (bReplace)
    {
        ReplaceNode = FindNodeByNameOrTitle(Graph, TargetNodeName, TargetNodeTitleContains);
        if (Cast<UK2Node_CallFunction>(ReplaceNode) == nullptr)
        {
            return {false, TEXT("replace_function_call target must be an existing call-function node."), TEXT(""), TEXT("INVALID_TARGET")};
        }
    }

    if (Request.bDryRun)
    {
        TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
        Out->SetStringField(TEXT("blueprint"), Blueprint->GetPathName());
        Out->SetStringField(TEXT("graph_name"), Graph->GetName());
        Out->SetStringField(TEXT("operation"), Operation);
        if (bSpawnFunction && OwnerClass != nullptr)
        {
            Out->SetStringField(TEXT("function"), FString::Printf(TEXT("%s::%s"), *OwnerClass->GetName(), *FunctionName));
        }
        if (bSpawnCustomEvent)
        {
            const FString EventName = !CustomEventName.IsEmpty() ? CustomEventName : (!NodeName.IsEmpty() ? NodeName : TEXT("AgentCustomEvent"));
            Out->SetStringField(TEXT("custom_event_name"), EventName);
        }
        return BuildPassThroughResult(TEXT("Dry run node authoring validation succeeded."), Out);
    }

    Blueprint->Modify();
    Graph->Modify();

    UK2Node_CallFunction* NewCallNode = nullptr;
    UK2Node_CustomEvent* NewCustomEventNode = nullptr;
    UK2Node_IfThenElse* NewBranchNode = nullptr;
    UEdGraphNode* NewNodeGeneric = nullptr;
    if (bSpawnFunction)
    {
        NewCallNode = FEdGraphSchemaAction_K2NewNode::SpawnNode<UK2Node_CallFunction>(
            Graph,
            NodePosition,
            EK2NewNodeFlags::SelectNewNode,
            [TargetFunction](UK2Node_CallFunction* NewNode)
            {
                NewNode->SetFromFunction(TargetFunction);
            });
        if (NewCallNode == nullptr)
        {
            return {false, TEXT("Failed to spawn call function node."), TEXT(""), TEXT("EXEC_FAILED")};
        }
        if (!NodeName.IsEmpty())
        {
            NewCallNode->Rename(*NodeName, nullptr, REN_DontCreateRedirectors);
        }
        NewNodeGeneric = NewCallNode;
    }
    else if (bSpawnCustomEvent)
    {
        const FString EventName = !CustomEventName.IsEmpty() ? CustomEventName : (!NodeName.IsEmpty() ? NodeName : TEXT("AgentCustomEvent"));
        NewCustomEventNode = FEdGraphSchemaAction_K2NewNode::SpawnNode<UK2Node_CustomEvent>(
            Graph,
            NodePosition,
            EK2NewNodeFlags::SelectNewNode,
            [EventName](UK2Node_CustomEvent* NewNode)
            {
                NewNode->CustomFunctionName = FName(*EventName);
            });
        if (NewCustomEventNode == nullptr)
        {
            return {false, TEXT("Failed to spawn custom event node."), TEXT(""), TEXT("EXEC_FAILED")};
        }
        if (!NodeName.IsEmpty())
        {
            NewCustomEventNode->Rename(*NodeName, nullptr, REN_DontCreateRedirectors);
        }
        NewNodeGeneric = NewCustomEventNode;
    }
    else if (bSpawnBranchNode)
    {
        bool bConditionDefault = false;
        const bool bHasConditionDefault = Payload.IsValid() && Payload->HasTypedField<EJson::Boolean>(TEXT("condition_default"));
        if (Payload.IsValid())
        {
            Payload->TryGetBoolField(TEXT("condition_default"), bConditionDefault);
        }
        NewBranchNode = FEdGraphSchemaAction_K2NewNode::SpawnNode<UK2Node_IfThenElse>(
            Graph,
            NodePosition,
            EK2NewNodeFlags::SelectNewNode,
            [](UK2Node_IfThenElse* NewNode) {});
        if (NewBranchNode == nullptr)
        {
            return {false, TEXT("Failed to spawn branch node."), TEXT(""), TEXT("EXEC_FAILED")};
        }
        if (bHasConditionDefault)
        {
            if (UEdGraphPin* ConditionPin = NewBranchNode->GetConditionPin())
            {
                ConditionPin->DefaultValue = bConditionDefault ? TEXT("true") : TEXT("false");
            }
        }
        if (!NodeName.IsEmpty())
        {
            NewBranchNode->Rename(*NodeName, nullptr, REN_DontCreateRedirectors);
        }
        NewNodeGeneric = NewBranchNode;
    }

    int32 RewiredLinks = 0;
    int32 SkippedRewireLinks = 0;
    FString ReplacedNodeName;
    if (bReplace && NewCallNode != nullptr)
    {
        UK2Node_CallFunction* OldCallNode = Cast<UK2Node_CallFunction>(ReplaceNode);
        ReplacedNodeName = OldCallNode->GetName();
        for (UEdGraphPin* OldPin : OldCallNode->Pins)
        {
            if (OldPin == nullptr)
            {
                continue;
            }
            UEdGraphPin* NewPin = FindNodePinByName(NewCallNode, OldPin->PinName.ToString());
            if (NewPin == nullptr)
            {
                continue;
            }
            if (OldPin->Direction == EGPD_Input && OldPin->LinkedTo.Num() == 0 && !OldPin->DefaultValue.IsEmpty())
            {
                NewPin->DefaultValue = OldPin->DefaultValue;
            }
            TArray<UEdGraphPin*> LinkedPins = OldPin->LinkedTo;
            for (UEdGraphPin* Linked : LinkedPins)
            {
                if (Linked == nullptr)
                {
                    continue;
                }
                bool bLinked = false;
                if (OldPin->Direction == EGPD_Input)
                {
                    FString Why;
                    bLinked = ValidatePinTypeContract(Linked, NewPin, Why) && Graph->GetSchema()->TryCreateConnection(Linked, NewPin);
                }
                else
                {
                    FString Why;
                    bLinked = ValidatePinTypeContract(NewPin, Linked, Why) && Graph->GetSchema()->TryCreateConnection(NewPin, Linked);
                }
                if (bLinked)
                {
                    ++RewiredLinks;
                }
                else
                {
                    ++SkippedRewireLinks;
                }
            }
            OldPin->BreakAllPinLinks();
        }
        FBlueprintEditorUtils::RemoveNode(Blueprint, OldCallNode, true);
    }

    FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
    Blueprint->MarkPackageDirty();
    if (bCompileAfter)
    {
        FKismetEditorUtilities::CompileBlueprint(Blueprint);
    }

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetStringField(TEXT("blueprint"), Blueprint->GetPathName());
    Out->SetStringField(TEXT("graph_name"), Graph->GetName());
    Out->SetStringField(TEXT("operation"), bReplace ? TEXT("replace_function_call") : Operation);
    Out->SetStringField(TEXT("new_node_name"), NewNodeGeneric != nullptr ? NewNodeGeneric->GetName() : TEXT(""));
    if (bSpawnFunction && OwnerClass != nullptr)
    {
        Out->SetStringField(TEXT("function"), FString::Printf(TEXT("%s::%s"), *OwnerClass->GetName(), *FunctionName));
    }
    if (bSpawnCustomEvent && NewCustomEventNode != nullptr)
    {
        Out->SetStringField(TEXT("custom_event_name"), NewCustomEventNode->CustomFunctionName.ToString());
    }
    Out->SetNumberField(TEXT("rewired_links"), RewiredLinks);
    Out->SetNumberField(TEXT("skipped_rewire_links"), SkippedRewireLinks);
    Out->SetStringField(TEXT("replaced_node_name"), ReplacedNodeName);
    Out->SetBoolField(TEXT("compiled"), bCompileAfter);
    return BuildPassThroughResult(TEXT("blueprint_node_authoring completed."), Out);
}

static FAgentActionResult HandleBlueprintCompileDiagnostics(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString BlueprintPath;
    FString GraphName;
    bool bIncludePins = true;
    int32 MaxNodes = 500;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("blueprint_path"), BlueprintPath);
        Payload->TryGetStringField(TEXT("graph_name"), GraphName);
        Payload->TryGetBoolField(TEXT("include_pins"), bIncludePins);
        Payload->TryGetNumberField(TEXT("max_nodes"), MaxNodes);
    }
    if (BlueprintPath.IsEmpty())
    {
        return {false, TEXT("blueprint_compile_diagnostics requires blueprint_path."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    TSharedRef<FJsonObject> CompilePayload = MakeShared<FJsonObject>();
    CompilePayload->SetStringField(TEXT("blueprint_path"), BlueprintPath);
    const FAgentActionResult CompileResult = ExecuteNamedAction(TEXT("compile_blueprint"), CompilePayload, Request.bDryRun);

    TSharedRef<FJsonObject> InspectPayload = MakeShared<FJsonObject>();
    InspectPayload->SetStringField(TEXT("blueprint_path"), BlueprintPath);
    if (!GraphName.IsEmpty())
    {
        InspectPayload->SetStringField(TEXT("graph_name"), GraphName);
    }
    InspectPayload->SetNumberField(TEXT("max_nodes"), FMath::Clamp(MaxNodes, 1, 2000));
    InspectPayload->SetBoolField(TEXT("include_pins"), bIncludePins);
    const FAgentActionResult InspectResult = ExecuteNamedAction(TEXT("inspect_blueprint_graph"), InspectPayload, true);

    TSharedRef<FJsonObject> AnalyzePayload = MakeShared<FJsonObject>();
    AnalyzePayload->SetStringField(TEXT("blueprint_path"), BlueprintPath);
    if (!GraphName.IsEmpty())
    {
        AnalyzePayload->SetStringField(TEXT("graph_name"), GraphName);
    }
    AnalyzePayload->SetNumberField(TEXT("max_nodes"), FMath::Clamp(MaxNodes, 1, 2000));
    AnalyzePayload->SetBoolField(TEXT("include_pins"), bIncludePins);
    const FAgentActionResult AnalyzeResult = ExecuteNamedAction(TEXT("analyze_blueprint_graph"), AnalyzePayload, true);

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetStringField(TEXT("blueprint_path"), BlueprintPath);
    Out->SetBoolField(TEXT("compile_success"), CompileResult.bSuccess);
    Out->SetStringField(TEXT("compile_message"), CompileResult.Message);
    Out->SetStringField(TEXT("compile_error_code"), NormalizeErrorCode(CompileResult));

    auto AttachPayload = [&Out](const FString& FieldName, const FAgentActionResult& ActionResult)
    {
        if (ActionResult.PayloadJson.IsEmpty())
        {
            return;
        }
        TSharedPtr<FJsonObject> Parsed = MakeShared<FJsonObject>();
        FString ParseError;
        if (ParseJsonObject(ActionResult.PayloadJson, Parsed, ParseError) && Parsed.IsValid())
        {
            Out->SetObjectField(FieldName, Parsed.ToSharedRef());
        }
    };
    AttachPayload(TEXT("graph_inventory"), InspectResult);
    AttachPayload(TEXT("graph_analysis"), AnalyzeResult);

    TArray<TSharedPtr<FJsonValue>> RiskFlags;
    if (!CompileResult.bSuccess)
    {
        RiskFlags.Add(MakeShared<FJsonValueString>(TEXT("COMPILE_FAILED")));
    }
    if (!AnalyzeResult.bSuccess)
    {
        RiskFlags.Add(MakeShared<FJsonValueString>(TEXT("ANALYSIS_UNAVAILABLE")));
    }
    if (!InspectResult.bSuccess)
    {
        RiskFlags.Add(MakeShared<FJsonValueString>(TEXT("GRAPH_INVENTORY_UNAVAILABLE")));
    }
    Out->SetArrayField(TEXT("risk_flags"), RiskFlags);

    const bool bSuccess = CompileResult.bSuccess;
    return {
        bSuccess,
        bSuccess ? TEXT("Blueprint compile diagnostics completed.") : TEXT("Blueprint compile diagnostics found compile failures."),
        SerializePayload(Out),
        bSuccess ? TEXT("OK") : TEXT("COMPILE_FAILED")};
}

static FAgentActionResult HandleModifyBlueprintComponents(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString BlueprintPath;
    FString Operation = TEXT("add_component");
    bool bCompileAfter = true;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("blueprint_path"), BlueprintPath);
        Payload->TryGetStringField(TEXT("operation"), Operation);
        Payload->TryGetBoolField(TEXT("compile_after"), bCompileAfter);
    }
    if (BlueprintPath.IsEmpty())
    {
        return {false, TEXT("modify_blueprint_components requires blueprint_path."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    UBlueprint* Blueprint = ResolveBlueprintAsset(BlueprintPath);
    if (Blueprint == nullptr || Blueprint->SimpleConstructionScript == nullptr)
    {
        return {false, TEXT("Blueprint or SimpleConstructionScript not found."), TEXT(""), TEXT("ASSET_NOT_FOUND")};
    }
    USimpleConstructionScript* SCS = Blueprint->SimpleConstructionScript;

    auto FindNodeByName = [&](const FString& Name) -> USCS_Node*
    {
        if (Name.IsEmpty())
        {
            return nullptr;
        }
        for (USCS_Node* Node : SCS->GetAllNodes())
        {
            if (Node == nullptr)
            {
                continue;
            }
            const FString VariableName = Node->GetVariableName().ToString();
            const FString TemplateName = Node->ComponentTemplate != nullptr ? Node->ComponentTemplate->GetName() : TEXT("");
            if (VariableName.Equals(Name, ESearchCase::IgnoreCase) || TemplateName.Equals(Name, ESearchCase::IgnoreCase))
            {
                return Node;
            }
        }
        return nullptr;
    };

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetStringField(TEXT("blueprint"), Blueprint->GetPathName());
    Out->SetStringField(TEXT("operation"), Operation);

    if (Operation.Equals(TEXT("add_component"), ESearchCase::IgnoreCase))
    {
        FString ClassPath;
        FString ComponentName;
        FString ParentComponent;
        if (Payload.IsValid())
        {
            Payload->TryGetStringField(TEXT("class_path"), ClassPath);
            Payload->TryGetStringField(TEXT("component_name"), ComponentName);
            Payload->TryGetStringField(TEXT("parent_component"), ParentComponent);
        }
        if (ClassPath.IsEmpty() || ComponentName.IsEmpty())
        {
            return {false, TEXT("add_component requires class_path and component_name."), TEXT(""), TEXT("MISSING_FIELD")};
        }
        UClass* CompClass = LoadObject<UClass>(nullptr, *ClassPath);
        if (CompClass == nullptr)
        {
            CompClass = FindObject<UClass>(nullptr, *ClassPath);
        }
        if (CompClass == nullptr || !CompClass->IsChildOf(UActorComponent::StaticClass()))
        {
            return {false, TEXT("class_path must resolve to an ActorComponent class."), TEXT(""), TEXT("INVALID_FIELD")};
        }
        if (FindNodeByName(ComponentName) != nullptr)
        {
            return {false, TEXT("Component name already exists."), TEXT(""), TEXT("ALREADY_EXISTS")};
        }
        if (!Request.bDryRun)
        {
            Blueprint->Modify();
            SCS->Modify();
            USCS_Node* NewNode = SCS->CreateNode(CompClass, FName(*ComponentName));
            if (NewNode == nullptr)
            {
                return {false, TEXT("Failed to create component node."), TEXT(""), TEXT("EXEC_FAILED")};
            }
            USCS_Node* ParentNode = FindNodeByName(ParentComponent);
            if (ParentNode != nullptr)
            {
                ParentNode->AddChildNode(NewNode);
            }
            else
            {
                SCS->AddNode(NewNode);
            }
        }
        Out->SetStringField(TEXT("component_name"), ComponentName);
    }
    else if (Operation.Equals(TEXT("remove_component"), ESearchCase::IgnoreCase))
    {
        FString ComponentName;
        if (Payload.IsValid())
        {
            Payload->TryGetStringField(TEXT("component_name"), ComponentName);
        }
        USCS_Node* TargetNode = FindNodeByName(ComponentName);
        if (TargetNode == nullptr)
        {
            return {false, TEXT("Component node not found."), TEXT(""), TEXT("NOT_FOUND")};
        }
        if (!Request.bDryRun)
        {
            Blueprint->Modify();
            SCS->Modify();
            SCS->RemoveNode(TargetNode);
        }
        Out->SetStringField(TEXT("component_name"), ComponentName);
    }
    else if (Operation.Equals(TEXT("set_component_property"), ESearchCase::IgnoreCase))
    {
        FString ComponentName;
        FString PropertyName;
        if (Payload.IsValid())
        {
            Payload->TryGetStringField(TEXT("component_name"), ComponentName);
            Payload->TryGetStringField(TEXT("property_name"), PropertyName);
        }
        USCS_Node* TargetNode = FindNodeByName(ComponentName);
        if (TargetNode == nullptr || TargetNode->ComponentTemplate == nullptr)
        {
            return {false, TEXT("Component template not found."), TEXT(""), TEXT("NOT_FOUND")};
        }
        const TSharedPtr<FJsonValue>* ValuePtr = Payload.IsValid() ? Payload->Values.Find(TEXT("value")) : nullptr;
        if (ValuePtr == nullptr || !ValuePtr->IsValid())
        {
            return {false, TEXT("set_component_property requires value."), TEXT(""), TEXT("MISSING_FIELD")};
        }
        FString Error;
        if (!Request.bDryRun)
        {
            Blueprint->Modify();
            TargetNode->ComponentTemplate->Modify();
        }
        if (!SetReflectedScalarProperty(TargetNode->ComponentTemplate, PropertyName, *ValuePtr, Error))
        {
            return {false, Error, TEXT(""), TEXT("INVALID_FIELD")};
        }
        Out->SetStringField(TEXT("component_name"), ComponentName);
        Out->SetStringField(TEXT("property_name"), PropertyName);
    }
    else
    {
        return {false, TEXT("Unsupported component operation. Use add_component/remove_component/set_component_property."), TEXT(""), TEXT("INVALID_FIELD")};
    }

    if (!Request.bDryRun)
    {
        FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
        Blueprint->MarkPackageDirty();
        if (bCompileAfter)
        {
            FKismetEditorUtilities::CompileBlueprint(Blueprint);
        }
    }
    Out->SetBoolField(TEXT("compiled"), !Request.bDryRun && bCompileAfter);
    return BuildPassThroughResult(TEXT("modify_blueprint_components completed."), Out);
}

static FAgentActionResult HandleEditActorTransform(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    UWorld* EditorWorld = (GEditor != nullptr) ? GEditor->GetEditorWorldContext().World() : nullptr;
    if (EditorWorld == nullptr)
    {
        return {false, TEXT("No editor world found."), TEXT(""), TEXT("WORLD_NOT_FOUND")};
    }

    FString ActorId;
    FString Operation = TEXT("set_transform");
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("actor"), ActorId);
        if (ActorId.IsEmpty())
        {
            Payload->TryGetStringField(TEXT("actor_label"), ActorId);
        }
        Payload->TryGetStringField(TEXT("operation"), Operation);
    }
    if (ActorId.IsEmpty())
    {
        return {false, TEXT("edit_actor_transform requires actor or actor_label."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    AActor* Target = FindWorldActorByLabelOrName(EditorWorld, ActorId);
    if (Target == nullptr)
    {
        return {false, TEXT("Actor not found in editor world."), TEXT(""), TEXT("NOT_FOUND")};
    }

    const FVector Location = ReadVectorOrDefault(Payload, TEXT("location"), Target->GetActorLocation());
    const FVector RotationEuler = ReadVectorOrDefault(Payload, TEXT("rotation"), Target->GetActorRotation().Euler());
    const FVector Scale = ReadVectorOrDefault(Payload, TEXT("scale"), Target->GetActorScale3D());

    if (!Request.bDryRun)
    {
        Target->Modify();
        if (Operation.Equals(TEXT("set_location"), ESearchCase::IgnoreCase))
        {
            Target->SetActorLocation(Location);
        }
        else if (Operation.Equals(TEXT("set_rotation"), ESearchCase::IgnoreCase))
        {
            Target->SetActorRotation(FRotator::MakeFromEuler(RotationEuler));
        }
        else if (Operation.Equals(TEXT("set_scale"), ESearchCase::IgnoreCase))
        {
            Target->SetActorScale3D(Scale);
        }
        else
        {
            Target->SetActorLocationAndRotation(Location, FRotator::MakeFromEuler(RotationEuler));
            Target->SetActorScale3D(Scale);
        }
        EditorWorld->MarkPackageDirty();
    }

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetStringField(TEXT("actor"), Target->GetName());
    Out->SetStringField(TEXT("actor_label"), Target->GetActorLabel());
    Out->SetStringField(TEXT("operation"), Operation);
    Out->SetArrayField(
        TEXT("location"),
        {
            MakeShared<FJsonValueNumber>(Location.X),
            MakeShared<FJsonValueNumber>(Location.Y),
            MakeShared<FJsonValueNumber>(Location.Z),
        });
    Out->SetArrayField(
        TEXT("rotation"),
        {
            MakeShared<FJsonValueNumber>(RotationEuler.X),
            MakeShared<FJsonValueNumber>(RotationEuler.Y),
            MakeShared<FJsonValueNumber>(RotationEuler.Z),
        });
    Out->SetArrayField(
        TEXT("scale"),
        {
            MakeShared<FJsonValueNumber>(Scale.X),
            MakeShared<FJsonValueNumber>(Scale.Y),
            MakeShared<FJsonValueNumber>(Scale.Z),
        });
    return BuildPassThroughResult(Request.bDryRun ? TEXT("Dry run actor transform validation succeeded.") : TEXT("edit_actor_transform completed."), Out);
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
    TArray<FString> Tags = ReadStringArray(Payload, TEXT("tags"));
    if (Tags.Num() == 0)
    {
        Tags.Add(TEXT("CityChunk"));
    }

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
            TArray<TSharedPtr<FJsonValue>> TagValues;
            for (const FString& Tag : Tags)
            {
                TagValues.Add(MakeShared<FJsonValueString>(Tag));
            }
            Spawn->SetArrayField(TEXT("tags"), TagValues);
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

static bool TrySetObjectProperty(UObject* Target, const FName PropertyName, UObject* Value)
{
    if (Target == nullptr)
    {
        return false;
    }
    if (FObjectPropertyBase* ObjProp = CastField<FObjectPropertyBase>(Target->GetClass()->FindPropertyByName(PropertyName)))
    {
        void* ValuePtr = ObjProp->ContainerPtrToValuePtr<void>(Target);
        ObjProp->SetObjectPropertyValue(ValuePtr, Value);
        return true;
    }
    return false;
}

static bool TrySetBoolProperty(UObject* Target, const FName PropertyName, const bool bValue)
{
    if (Target == nullptr)
    {
        return false;
    }
    if (FBoolProperty* BoolProp = CastField<FBoolProperty>(Target->GetClass()->FindPropertyByName(PropertyName)))
    {
        void* ValuePtr = BoolProp->ContainerPtrToValuePtr<void>(Target);
        BoolProp->SetPropertyValue(ValuePtr, bValue);
        return true;
    }
    return false;
}

static bool TrySetFloatProperty(UObject* Target, const FName PropertyName, const float Value)
{
    if (Target == nullptr)
    {
        return false;
    }
    if (FFloatProperty* FloatProp = CastField<FFloatProperty>(Target->GetClass()->FindPropertyByName(PropertyName)))
    {
        void* ValuePtr = FloatProp->ContainerPtrToValuePtr<void>(Target);
        FloatProp->SetPropertyValue(ValuePtr, Value);
        return true;
    }
    if (FDoubleProperty* DoubleProp = CastField<FDoubleProperty>(Target->GetClass()->FindPropertyByName(PropertyName)))
    {
        void* ValuePtr = DoubleProp->ContainerPtrToValuePtr<void>(Target);
        DoubleProp->SetPropertyValue(ValuePtr, static_cast<double>(Value));
        return true;
    }
    return false;
}

static bool TrySetIntProperty(UObject* Target, const FName PropertyName, const int64 Value)
{
    if (Target == nullptr)
    {
        return false;
    }
    if (FIntProperty* IntProp = CastField<FIntProperty>(Target->GetClass()->FindPropertyByName(PropertyName)))
    {
        void* ValuePtr = IntProp->ContainerPtrToValuePtr<void>(Target);
        IntProp->SetPropertyValue(ValuePtr, static_cast<int32>(Value));
        return true;
    }
    if (FInt64Property* Int64Prop = CastField<FInt64Property>(Target->GetClass()->FindPropertyByName(PropertyName)))
    {
        void* ValuePtr = Int64Prop->ContainerPtrToValuePtr<void>(Target);
        Int64Prop->SetPropertyValue(ValuePtr, Value);
        return true;
    }
    if (FByteProperty* ByteProp = CastField<FByteProperty>(Target->GetClass()->FindPropertyByName(PropertyName)))
    {
        void* ValuePtr = ByteProp->ContainerPtrToValuePtr<void>(Target);
        ByteProp->SetPropertyValue(ValuePtr, static_cast<uint8>(Value));
        return true;
    }
    return false;
}

static bool TrySetEnumProperty(UObject* Target, const FName PropertyName, const int64 Value)
{
    if (Target == nullptr)
    {
        return false;
    }
    if (FEnumProperty* EnumProp = CastField<FEnumProperty>(Target->GetClass()->FindPropertyByName(PropertyName)))
    {
        if (FNumericProperty* Underlying = EnumProp->GetUnderlyingProperty())
        {
            void* ValuePtr = Underlying->ContainerPtrToValuePtr<void>(Target);
            Underlying->SetIntPropertyValue(ValuePtr, Value);
            return true;
        }
    }
    return false;
}

static bool ClearObjectArrayProperty(UObject* Target, const FName PropertyName)
{
    if (Target == nullptr)
    {
        return false;
    }
    FArrayProperty* ArrProp = CastField<FArrayProperty>(Target->GetClass()->FindPropertyByName(PropertyName));
    if (ArrProp == nullptr || CastField<FObjectPropertyBase>(ArrProp->Inner) == nullptr)
    {
        return false;
    }
    FScriptArrayHelper Helper(ArrProp, ArrProp->ContainerPtrToValuePtr<void>(Target));
    Helper.EmptyValues();
    return true;
}

static bool AddObjectToArrayProperty(UObject* Target, const FName PropertyName, UObject* Value)
{
    if (Target == nullptr || Value == nullptr)
    {
        return false;
    }
    FArrayProperty* ArrProp = CastField<FArrayProperty>(Target->GetClass()->FindPropertyByName(PropertyName));
    FObjectPropertyBase* InnerObj = ArrProp ? CastField<FObjectPropertyBase>(ArrProp->Inner) : nullptr;
    if (ArrProp == nullptr || InnerObj == nullptr)
    {
        return false;
    }
    FScriptArrayHelper Helper(ArrProp, ArrProp->ContainerPtrToValuePtr<void>(Target));
    const int32 Index = Helper.AddValue();
    void* ElemPtr = Helper.GetRawPtr(Index);
    InnerObj->SetObjectPropertyValue(ElemPtr, Value);
    return true;
}

static bool SetStructIntField(void* StructValue, UStruct* StructType, const FName& FieldName, const int32 Value)
{
    if (StructValue == nullptr || StructType == nullptr)
    {
        return false;
    }
    if (FIntProperty* IntProp = CastField<FIntProperty>(StructType->FindPropertyByName(FieldName)))
    {
        void* ValuePtr = IntProp->ContainerPtrToValuePtr<void>(StructValue);
        IntProp->SetPropertyValue(ValuePtr, Value);
        return true;
    }
    if (FInt64Property* Int64Prop = CastField<FInt64Property>(StructType->FindPropertyByName(FieldName)))
    {
        void* ValuePtr = Int64Prop->ContainerPtrToValuePtr<void>(StructValue);
        Int64Prop->SetPropertyValue(ValuePtr, static_cast<int64>(Value));
        return true;
    }
    return false;
}

static bool TrySetLinearColorProperty(UObject* Target, const FName PropertyName, const FLinearColor& Value)
{
    if (Target == nullptr)
    {
        return false;
    }
    FStructProperty* StructProp = CastField<FStructProperty>(Target->GetClass()->FindPropertyByName(PropertyName));
    if (StructProp == nullptr)
    {
        return false;
    }
    if (StructProp->Struct != TBaseStructure<FLinearColor>::Get())
    {
        return false;
    }
    void* ValuePtr = StructProp->ContainerPtrToValuePtr<void>(Target);
    *reinterpret_cast<FLinearColor*>(ValuePtr) = Value;
    return true;
}

static bool TrySetBoxProperty(UObject* Target, const FName PropertyName, const FBox& Value)
{
    if (Target == nullptr)
    {
        return false;
    }
    FStructProperty* StructProp = CastField<FStructProperty>(Target->GetClass()->FindPropertyByName(PropertyName));
    if (StructProp == nullptr || StructProp->Struct == nullptr)
    {
        return false;
    }
    if (StructProp->Struct->GetName().ToLower() != TEXT("box"))
    {
        return false;
    }
    void* ValuePtr = StructProp->ContainerPtrToValuePtr<void>(Target);
    *reinterpret_cast<FBox*>(ValuePtr) = Value;
    return true;
}

static bool TrySetNameProperty(UObject* Target, const FName PropertyName, const FName Value)
{
    if (Target == nullptr)
    {
        return false;
    }
    if (FNameProperty* NameProp = CastField<FNameProperty>(Target->GetClass()->FindPropertyByName(PropertyName)))
    {
        void* ValuePtr = NameProp->ContainerPtrToValuePtr<void>(Target);
        NameProp->SetPropertyValue(ValuePtr, Value);
        return true;
    }
    return false;
}

static bool ReadArray2Field(const TSharedPtr<FJsonObject>& Payload, const FString& Field, float& OutA, float& OutB)
{
    const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
    if (!Payload.IsValid() || !Payload->TryGetArrayField(Field, Arr) || Arr == nullptr || Arr->Num() != 2)
    {
        return false;
    }
    double A = 0.0;
    double B = 0.0;
    if (!(*Arr)[0].IsValid() || !(*Arr)[1].IsValid())
    {
        return false;
    }
    if (!(*Arr)[0]->TryGetNumber(A) || !(*Arr)[1]->TryGetNumber(B))
    {
        return false;
    }
    OutA = static_cast<float>(A);
    OutB = static_cast<float>(B);
    return true;
}

static bool ReadArray4Field(const TSharedPtr<FJsonObject>& Payload, const FString& Field, FLinearColor& OutColor)
{
    const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
    if (!Payload.IsValid() || !Payload->TryGetArrayField(Field, Arr) || Arr == nullptr || Arr->Num() != 4)
    {
        return false;
    }
    double R = 1.0;
    double G = 1.0;
    double B = 1.0;
    double A = 1.0;
    if (!(*Arr)[0].IsValid() || !(*Arr)[1].IsValid() || !(*Arr)[2].IsValid() || !(*Arr)[3].IsValid())
    {
        return false;
    }
    if (!(*Arr)[0]->TryGetNumber(R) || !(*Arr)[1]->TryGetNumber(G) || !(*Arr)[2]->TryGetNumber(B) || !(*Arr)[3]->TryGetNumber(A))
    {
        return false;
    }
    OutColor = FLinearColor(static_cast<float>(R), static_cast<float>(G), static_cast<float>(B), static_cast<float>(A));
    return true;
}

static FString NormalizeLookupKey(const FString& InKey)
{
    FString Key = InKey.TrimStartAndEnd().ToLower();
    Key.ReplaceInline(TEXT(" "), TEXT(""));
    Key.ReplaceInline(TEXT("_"), TEXT(""));
    Key.ReplaceInline(TEXT("-"), TEXT(""));
    return Key;
}

static FString NormalizeNiagaraUserParameterKey(const FString& InKey)
{
    FString Key = NormalizeLookupKey(InKey);
    Key.ReplaceInline(TEXT("user."), TEXT(""));
    return Key;
}

static bool ResolveNiagaraUserParameterType(const FString& InTypeName, FNiagaraTypeDefinition& OutType)
{
    const FString Key = NormalizeLookupKey(InTypeName);
    if (Key.IsEmpty() || Key == TEXT("float") || Key == TEXT("scalar"))
    {
        OutType = FNiagaraTypeDefinition::GetFloatDef();
        return true;
    }
    if (Key == TEXT("int") || Key == TEXT("int32") || Key == TEXT("integer"))
    {
        OutType = FNiagaraTypeDefinition::GetIntDef();
        return true;
    }
    if (Key == TEXT("bool") || Key == TEXT("boolean"))
    {
        OutType = FNiagaraTypeDefinition::GetBoolDef();
        return true;
    }
    if (Key == TEXT("vec2") || Key == TEXT("vector2") || Key == TEXT("float2"))
    {
        OutType = FNiagaraTypeDefinition::GetVec2Def();
        return true;
    }
    if (Key == TEXT("vec3") || Key == TEXT("vector3") || Key == TEXT("float3"))
    {
        OutType = FNiagaraTypeDefinition::GetVec3Def();
        return true;
    }
    if (Key == TEXT("vec4") || Key == TEXT("vector4") || Key == TEXT("float4"))
    {
        OutType = FNiagaraTypeDefinition::GetVec4Def();
        return true;
    }
    if (Key == TEXT("color") || Key == TEXT("linearcolor"))
    {
        OutType = FNiagaraTypeDefinition::GetColorDef();
        return true;
    }
    if (Key == TEXT("position"))
    {
        OutType = FNiagaraTypeDefinition::GetPositionDef();
        return true;
    }
    if (Key == TEXT("quat") || Key == TEXT("quaternion"))
    {
        OutType = FNiagaraTypeDefinition::GetQuatDef();
        return true;
    }
    return false;
}

static bool TrySetNiagaraUserParameterFromOperation(
    FNiagaraUserRedirectionParameterStore& Store,
    const FNiagaraVariable& Variable,
    const TSharedPtr<FJsonObject>& Operation)
{
    if (!Operation.IsValid())
    {
        return false;
    }
    const FNiagaraTypeDefinition& TypeDef = Variable.GetType();

    if (TypeDef == FNiagaraTypeDefinition::GetFloatDef())
    {
        double Value = 0.0;
        if (Operation->TryGetNumberField(TEXT("value"), Value))
        {
            return Store.SetParameterValue<float>(static_cast<float>(Value), Variable, true);
        }
        return false;
    }
    if (TypeDef == FNiagaraTypeDefinition::GetIntDef())
    {
        double Value = 0.0;
        if (Operation->TryGetNumberField(TEXT("value"), Value))
        {
            return Store.SetParameterValue<int32>(static_cast<int32>(Value), Variable, true);
        }
        return false;
    }
    if (TypeDef == FNiagaraTypeDefinition::GetBoolDef())
    {
        bool bValue = false;
        if (Operation->TryGetBoolField(TEXT("value"), bValue))
        {
            return Store.SetParameterValue<FNiagaraBool>(FNiagaraBool(bValue), Variable, true);
        }
        double Numeric = 0.0;
        if (Operation->TryGetNumberField(TEXT("value"), Numeric))
        {
            return Store.SetParameterValue<FNiagaraBool>(FNiagaraBool(Numeric != 0.0), Variable, true);
        }
        FString TextValue;
        if (Operation->TryGetStringField(TEXT("value"), TextValue))
        {
            const FString Key = NormalizeLookupKey(TextValue);
            if (Key == TEXT("1") || Key == TEXT("true") || Key == TEXT("yes") || Key == TEXT("on"))
            {
                return Store.SetParameterValue<FNiagaraBool>(FNiagaraBool(true), Variable, true);
            }
            if (Key == TEXT("0") || Key == TEXT("false") || Key == TEXT("no") || Key == TEXT("off"))
            {
                return Store.SetParameterValue<FNiagaraBool>(FNiagaraBool(false), Variable, true);
            }
        }
        return false;
    }
    if (TypeDef == FNiagaraTypeDefinition::GetVec2Def())
    {
        float X = 0.0f;
        float Y = 0.0f;
        if (ReadArray2Field(Operation, TEXT("value"), X, Y) || ReadArray2Field(Operation, TEXT("vector2_value"), X, Y))
        {
            return Store.SetParameterValue<FVector2f>(FVector2f(X, Y), Variable, true);
        }
        return false;
    }
    if (TypeDef == FNiagaraTypeDefinition::GetVec3Def() || TypeDef == FNiagaraTypeDefinition::GetPositionDef())
    {
        const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
        if (Operation->TryGetArrayField(TEXT("value"), Arr) || Operation->TryGetArrayField(TEXT("vector3_value"), Arr))
        {
            if (Arr != nullptr && Arr->Num() == 3 && (*Arr)[0].IsValid() && (*Arr)[1].IsValid() && (*Arr)[2].IsValid())
            {
                double X = 0.0;
                double Y = 0.0;
                double Z = 0.0;
                if ((*Arr)[0]->TryGetNumber(X) && (*Arr)[1]->TryGetNumber(Y) && (*Arr)[2]->TryGetNumber(Z))
                {
                    if (TypeDef == FNiagaraTypeDefinition::GetPositionDef())
                    {
                        return Store.SetParameterValue<FNiagaraPosition>(
                            FNiagaraPosition(static_cast<float>(X), static_cast<float>(Y), static_cast<float>(Z)),
                            Variable,
                            true);
                    }
                    return Store.SetParameterValue<FVector3f>(
                        FVector3f(static_cast<float>(X), static_cast<float>(Y), static_cast<float>(Z)),
                        Variable,
                        true);
                }
            }
        }
        return false;
    }
    if (TypeDef == FNiagaraTypeDefinition::GetVec4Def())
    {
        FLinearColor VectorValue = FLinearColor::Black;
        if (ReadArray4Field(Operation, TEXT("value"), VectorValue) || ReadArray4Field(Operation, TEXT("vector_value"), VectorValue))
        {
            return Store.SetParameterValue<FVector4f>(
                FVector4f(VectorValue.R, VectorValue.G, VectorValue.B, VectorValue.A),
                Variable,
                true);
        }
        return false;
    }
    if (TypeDef == FNiagaraTypeDefinition::GetColorDef())
    {
        FLinearColor ColorValue = FLinearColor::White;
        if (ReadArray4Field(Operation, TEXT("value"), ColorValue) || ReadArray4Field(Operation, TEXT("color_value"), ColorValue))
        {
            return Store.SetParameterValue<FLinearColor>(ColorValue, Variable, true);
        }
        return false;
    }
    if (TypeDef == FNiagaraTypeDefinition::GetQuatDef())
    {
        FLinearColor QuaternionValue = FLinearColor(0.f, 0.f, 0.f, 1.f);
        if (ReadArray4Field(Operation, TEXT("value"), QuaternionValue) || ReadArray4Field(Operation, TEXT("quaternion_value"), QuaternionValue))
        {
            return Store.SetParameterValue<FQuat4f>(
                FQuat4f(QuaternionValue.R, QuaternionValue.G, QuaternionValue.B, QuaternionValue.A),
                Variable,
                true);
        }
        return false;
    }
    return false;
}

static UClass* ResolveMaterialExpressionClass(const FString& ClassPathOrAlias)
{
    const FString Alias = NormalizeLookupKey(ClassPathOrAlias);
    if (Alias == TEXT("constant"))
    {
        return UMaterialExpressionConstant::StaticClass();
    }
    if (Alias == TEXT("constant2vector"))
    {
        return UMaterialExpressionConstant2Vector::StaticClass();
    }
    if (Alias == TEXT("constant3vector"))
    {
        return UMaterialExpressionConstant3Vector::StaticClass();
    }
    if (Alias == TEXT("constant4vector"))
    {
        return UMaterialExpressionConstant4Vector::StaticClass();
    }
    if (Alias == TEXT("texturesample"))
    {
        return UMaterialExpressionTextureSample::StaticClass();
    }
    return ResolveClassByPath(ClassPathOrAlias);
}

static void BuildMaterialExpressionLookup(UMaterial* Material, TMap<FString, UMaterialExpression*>& OutMap)
{
    OutMap.Reset();
    if (Material == nullptr)
    {
        return;
    }

    for (UMaterialExpression* Expression : Material->GetExpressionCollection().Expressions)
    {
        if (Expression == nullptr)
        {
            continue;
        }
        OutMap.Add(NormalizeLookupKey(Expression->GetName()), Expression);
        OutMap.Add(NormalizeLookupKey(Expression->GetPathName()), Expression);
    }
}

static UMaterialExpression* ResolveMaterialExpressionByKey(UMaterial* Material, TMap<FString, UMaterialExpression*>& Lookup, const FString& Key)
{
    if (Material == nullptr)
    {
        return nullptr;
    }
    const FString Normalized = NormalizeLookupKey(Key);
    if (Normalized.IsEmpty())
    {
        return nullptr;
    }
    if (UMaterialExpression** Found = Lookup.Find(Normalized))
    {
        return *Found;
    }
    BuildMaterialExpressionLookup(Material, Lookup);
    if (UMaterialExpression** FoundAfterRebuild = Lookup.Find(Normalized))
    {
        return *FoundAfterRebuild;
    }
    return nullptr;
}

static bool ConnectExpressionStructField(UObject* InputOwner, const FName InputFieldName, UMaterialExpression* SourceExpression, const int32 OutputIndex)
{
    if (InputOwner == nullptr)
    {
        return false;
    }
    FStructProperty* StructProp = CastField<FStructProperty>(InputOwner->GetClass()->FindPropertyByName(InputFieldName));
    if (StructProp == nullptr)
    {
        return false;
    }
    void* StructPtr = StructProp->ContainerPtrToValuePtr<void>(InputOwner);
    const bool bSetExpression = SetStructObjectField(StructPtr, StructProp->Struct, TEXT("Expression"), SourceExpression);
    const bool bSetOutput = SetStructIntField(StructPtr, StructProp->Struct, TEXT("OutputIndex"), OutputIndex);
    return bSetExpression && bSetOutput;
}

static FName ResolveMaterialPropertyFieldName(const FString& InPropertyName)
{
    const FString Key = NormalizeLookupKey(InPropertyName);
    if (Key == TEXT("basecolor"))
    {
        return TEXT("BaseColor");
    }
    if (Key == TEXT("metallic"))
    {
        return TEXT("Metallic");
    }
    if (Key == TEXT("specular"))
    {
        return TEXT("Specular");
    }
    if (Key == TEXT("roughness"))
    {
        return TEXT("Roughness");
    }
    if (Key == TEXT("normal"))
    {
        return TEXT("Normal");
    }
    if (Key == TEXT("emissivecolor"))
    {
        return TEXT("EmissiveColor");
    }
    if (Key == TEXT("opacity"))
    {
        return TEXT("Opacity");
    }
    if (Key == TEXT("opacitymask"))
    {
        return TEXT("OpacityMask");
    }
    if (Key == TEXT("worldpositionoffset"))
    {
        return TEXT("WorldPositionOffset");
    }
    if (Key == TEXT("displacement"))
    {
        return TEXT("Displacement");
    }
    if (Key == TEXT("subsurfacecolor"))
    {
        return TEXT("SubsurfaceColor");
    }
    if (Key == TEXT("clearcoat"))
    {
        return TEXT("ClearCoat");
    }
    if (Key == TEXT("clearcoatroughness"))
    {
        return TEXT("ClearCoatRoughness");
    }
    if (Key == TEXT("ambientocclusion"))
    {
        return TEXT("AmbientOcclusion");
    }
    if (Key == TEXT("refraction"))
    {
        return TEXT("Refraction");
    }
    if (Key == TEXT("pixeldepthoffset"))
    {
        return TEXT("PixelDepthOffset");
    }
    if (Key == TEXT("materialattributes"))
    {
        return TEXT("MaterialAttributes");
    }
    if (Key == TEXT("frontmaterial"))
    {
        return TEXT("FrontMaterial");
    }
    if (Key == TEXT("surfacethickness"))
    {
        return TEXT("SurfaceThickness");
    }
    return NAME_None;
}

static bool ConnectMaterialProperty(UMaterial* Material, const FString& MaterialPropertyName, UMaterialExpression* SourceExpression, const int32 OutputIndex)
{
    if (Material == nullptr)
    {
        return false;
    }
    UMaterialEditorOnlyData* EditorData = Material->GetEditorOnlyData();
    if (EditorData == nullptr)
    {
        return false;
    }
    const FName FieldName = ResolveMaterialPropertyFieldName(MaterialPropertyName);
    if (FieldName.IsNone())
    {
        return false;
    }
    return ConnectExpressionStructField(EditorData, FieldName, SourceExpression, OutputIndex);
}

static bool DisconnectMaterialProperty(UMaterial* Material, const FString& MaterialPropertyName)
{
    return ConnectMaterialProperty(Material, MaterialPropertyName, nullptr, 0);
}

static void DisconnectAllMaterialProperties(UMaterial* Material)
{
    const TCHAR* PropertyNames[] = {
        TEXT("BaseColor"),
        TEXT("Metallic"),
        TEXT("Specular"),
        TEXT("Roughness"),
        TEXT("Normal"),
        TEXT("EmissiveColor"),
        TEXT("Opacity"),
        TEXT("OpacityMask"),
        TEXT("WorldPositionOffset"),
        TEXT("Displacement"),
        TEXT("SubsurfaceColor"),
        TEXT("ClearCoat"),
        TEXT("ClearCoatRoughness"),
        TEXT("AmbientOcclusion"),
        TEXT("Refraction"),
        TEXT("PixelDepthOffset"),
        TEXT("MaterialAttributes"),
        TEXT("FrontMaterial"),
        TEXT("SurfaceThickness"),
    };
    for (const TCHAR* Name : PropertyNames)
    {
        DisconnectMaterialProperty(Material, Name);
    }
}

static void ApplyMaterialExpressionDefaults(UMaterialExpression* Expression, const TSharedPtr<FJsonObject>& Operation)
{
    if (Expression == nullptr || !Operation.IsValid())
    {
        return;
    }

    double NumberValue = 0.0;
    if (Operation->TryGetNumberField(TEXT("scalar_value"), NumberValue))
    {
        TrySetFloatProperty(Expression, TEXT("R"), static_cast<float>(NumberValue));
        TrySetFloatProperty(Expression, TEXT("Constant"), static_cast<float>(NumberValue));
    }

    float Vec2A = 0.0f;
    float Vec2B = 0.0f;
    if (ReadArray2Field(Operation, TEXT("vector2_value"), Vec2A, Vec2B))
    {
        TrySetFloatProperty(Expression, TEXT("R"), Vec2A);
        TrySetFloatProperty(Expression, TEXT("G"), Vec2B);
    }

    FLinearColor VectorValue = FLinearColor::White;
    if (ReadArray4Field(Operation, TEXT("vector_value"), VectorValue))
    {
        TrySetLinearColorProperty(Expression, TEXT("Constant"), VectorValue);
        TrySetFloatProperty(Expression, TEXT("R"), VectorValue.R);
        TrySetFloatProperty(Expression, TEXT("G"), VectorValue.G);
        TrySetFloatProperty(Expression, TEXT("B"), VectorValue.B);
        TrySetFloatProperty(Expression, TEXT("A"), VectorValue.A);
    }

    FString TexturePath;
    if (Operation->TryGetStringField(TEXT("texture_path"), TexturePath) && !TexturePath.IsEmpty())
    {
        UObject* TextureObj = ResolveAssetObject(TexturePath);
        if (TextureObj != nullptr)
        {
            TrySetObjectProperty(Expression, TEXT("Texture"), TextureObj);
        }
    }
}

static UMovieSceneFloatTrack* FindFloatTrack(UMovieScene* MovieScene, const FString& TrackName, const FString& PropertyName)
{
    if (MovieScene == nullptr)
    {
        return nullptr;
    }
    const FString NormalizedTrack = NormalizeLookupKey(TrackName);
    const FString NormalizedProperty = NormalizeLookupKey(PropertyName);
    for (UMovieSceneTrack* Track : MovieScene->GetTracks())
    {
        UMovieSceneFloatTrack* FloatTrack = Cast<UMovieSceneFloatTrack>(Track);
        if (FloatTrack == nullptr)
        {
            continue;
        }
        const FString ExistingTrackName = NormalizeLookupKey(FloatTrack->GetDisplayName().ToString());
        const FString ExistingPropertyName = NormalizeLookupKey(FloatTrack->GetPropertyName().ToString());
        if (!NormalizedTrack.IsEmpty() && ExistingTrackName == NormalizedTrack)
        {
            return FloatTrack;
        }
        if (!NormalizedProperty.IsEmpty() && ExistingPropertyName == NormalizedProperty)
        {
            return FloatTrack;
        }
    }
    return nullptr;
}

static UMovieSceneFloatTrack* EnsureFloatTrack(UMovieScene* MovieScene, const FString& TrackName, const FString& PropertyName, const FString& PropertyPath)
{
    if (MovieScene == nullptr)
    {
        return nullptr;
    }
    UMovieSceneFloatTrack* Track = FindFloatTrack(MovieScene, TrackName, PropertyName);
    if (Track == nullptr)
    {
        Track = MovieScene->AddTrack<UMovieSceneFloatTrack>();
    }
    if (Track == nullptr)
    {
        return nullptr;
    }
    if (!TrackName.IsEmpty())
    {
        Track->SetDisplayName(FText::FromString(TrackName));
    }
    if (!PropertyName.IsEmpty())
    {
        Track->SetPropertyNameAndPath(*PropertyName, PropertyPath.IsEmpty() ? PropertyName : PropertyPath);
    }
    return Track;
}

static UMovieSceneFloatSection* EnsureFloatSection(UMovieSceneFloatTrack* Track, const int32 SectionIndex)
{
    if (Track == nullptr)
    {
        return nullptr;
    }

    const TArray<UMovieSceneSection*>& Sections = Track->GetAllSections();
    if (Sections.IsValidIndex(SectionIndex))
    {
        return Cast<UMovieSceneFloatSection>(Sections[SectionIndex]);
    }

    UMovieSceneSection* NewSection = Track->CreateNewSection();
    if (NewSection == nullptr)
    {
        return nullptr;
    }
    Track->AddSection(*NewSection);
    return Cast<UMovieSceneFloatSection>(NewSection);
}

static UAnimationStateMachineGraph* FindAnimationStateMachineGraph(UAnimBlueprint* AnimBlueprint, const FString& StateMachineName)
{
    if (AnimBlueprint == nullptr)
    {
        return nullptr;
    }

    TArray<UEdGraph*> AllGraphs;
    AnimBlueprint->GetAllGraphs(AllGraphs);
    UAnimationStateMachineGraph* FirstStateMachineGraph = nullptr;
    const FString NormalizedTarget = NormalizeLookupKey(StateMachineName);
    for (UEdGraph* Graph : AllGraphs)
    {
        UAnimationStateMachineGraph* StateMachineGraph = Cast<UAnimationStateMachineGraph>(Graph);
        if (StateMachineGraph == nullptr)
        {
            continue;
        }
        if (FirstStateMachineGraph == nullptr)
        {
            FirstStateMachineGraph = StateMachineGraph;
        }
        if (!NormalizedTarget.IsEmpty() && NormalizeLookupKey(StateMachineGraph->GetName()) == NormalizedTarget)
        {
            return StateMachineGraph;
        }
    }
    return FirstStateMachineGraph;
}

static UAnimStateNode* FindAnimStateNodeByName(UAnimationStateMachineGraph* StateMachineGraph, const FString& StateName)
{
    if (StateMachineGraph == nullptr)
    {
        return nullptr;
    }
    const FString NormalizedTarget = NormalizeLookupKey(StateName);
    for (UEdGraphNode* Node : StateMachineGraph->Nodes)
    {
        UAnimStateNode* StateNode = Cast<UAnimStateNode>(Node);
        if (StateNode == nullptr)
        {
            continue;
        }
        if (NormalizeLookupKey(StateNode->GetStateName()) == NormalizedTarget)
        {
            return StateNode;
        }
    }
    return nullptr;
}

static FAgentActionResult HandleCreateBehaviorTreeAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    return HandleCreateNativeAssetTyped(
        Request,
        Payload,
        TEXT("BT_AgentTree"),
        TEXT("/Game/AgentGenerated/AI"),
        TEXT("/Script/AIModule.BehaviorTree"),
        TEXT("/Script/BehaviorTreeEditor.BehaviorTreeFactory"),
        TEXT("BehaviorTreeEditor"));
}

static FAgentActionResult HandleCreateBlackboardDataAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    return HandleCreateNativeAssetTyped(
        Request,
        Payload,
        TEXT("BB_AgentData"),
        TEXT("/Game/AgentGenerated/AI"),
        TEXT("/Script/AIModule.BlackboardData"),
        TEXT("/Script/BehaviorTreeEditor.BlackboardDataFactory"),
        TEXT("BehaviorTreeEditor"));
}

static FAgentActionResult HandleCreateEQSQueryAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    return HandleCreateNativeAssetTyped(
        Request,
        Payload,
        TEXT("EQS_AgentQuery"),
        TEXT("/Game/AgentGenerated/AI"),
        TEXT("/Script/AIModule.EnvQuery"),
        TEXT("/Script/EnvironmentQueryEditor.EnvironmentQueryFactory"),
        TEXT("EnvironmentQueryEditor"));
}

static FAgentActionResult HandleCreateAnimBlueprintAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString AssetName = TEXT("ABP_AgentCharacter");
    FString PackagePath = TEXT("/Game/AgentGenerated/Animation");
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("asset_name"), AssetName);
        Payload->TryGetStringField(TEXT("package_path"), PackagePath);
    }

    TSharedRef<FJsonObject> Nested = MakeShared<FJsonObject>();
    Nested->SetStringField(TEXT("asset_name"), AssetName);
    Nested->SetStringField(TEXT("package_path"), PackagePath);
    Nested->SetStringField(TEXT("parent_class"), TEXT("/Script/Engine.AnimInstance"));
    return ExecuteNamedAction(TEXT("create_blueprint"), Nested, Request.bDryRun);
}

static FAgentActionResult HandleCreateMaterialAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    return HandleCreateNativeAssetTyped(
        Request,
        Payload,
        TEXT("M_AgentMaterial"),
        TEXT("/Game/AgentGenerated/Materials"),
        TEXT("/Script/Engine.Material"),
        TEXT("/Script/UnrealEd.MaterialFactoryNew"),
        TEXT("UnrealEd"));
}

static FAgentActionResult HandleCreateNiagaraSystemAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    return HandleCreateNativeAssetTyped(
        Request,
        Payload,
        TEXT("NS_AgentSystem"),
        TEXT("/Game/AgentGenerated/VFX"),
        TEXT("/Script/Niagara.NiagaraSystem"),
        TEXT("/Script/NiagaraEditor.NiagaraSystemFactoryNew"),
        TEXT("NiagaraEditor"));
}

static FAgentActionResult HandleCreateLevelSequenceAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    return HandleCreateNativeAssetTyped(
        Request,
        Payload,
        TEXT("LS_AgentSequence"),
        TEXT("/Game/AgentGenerated/Cinematics"),
        TEXT("/Script/LevelSequence.LevelSequence"),
        TEXT("/Script/LevelSequenceEditor.LevelSequenceFactoryNew"),
        TEXT("LevelSequenceEditor"));
}

static FAgentActionResult HandleEditBlackboardDataAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString BlackboardPath;
    bool bReplaceExisting = false;
    const TArray<TSharedPtr<FJsonValue>>* KeysArray = nullptr;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("blackboard_path"), BlackboardPath);
        if (BlackboardPath.IsEmpty())
        {
            Payload->TryGetStringField(TEXT("asset_path"), BlackboardPath);
        }
        Payload->TryGetBoolField(TEXT("replace_existing"), bReplaceExisting);
        Payload->TryGetArrayField(TEXT("keys"), KeysArray);
    }
    if (BlackboardPath.IsEmpty())
    {
        return {false, TEXT("edit_blackboard_data_asset requires blackboard_path or asset_path."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    UObject* BlackboardObj = ResolveAssetObject(BlackboardPath);
    if (BlackboardObj == nullptr)
    {
        return {false, FString::Printf(TEXT("Blackboard asset not found: %s"), *BlackboardPath), TEXT(""), TEXT("ASSET_NOT_FOUND")};
    }

    FArrayProperty* KeysProp = CastField<FArrayProperty>(BlackboardObj->GetClass()->FindPropertyByName(TEXT("Keys")));
    FStructProperty* EntryStructProp = KeysProp ? CastField<FStructProperty>(KeysProp->Inner) : nullptr;
    if (KeysProp == nullptr || EntryStructProp == nullptr)
    {
        return {false, TEXT("Blackboard schema keys are not editable via reflection on this engine version."), TEXT(""), TEXT("UNSUPPORTED")};
    }

    const int32 RequestedCount = (KeysArray && KeysArray->Num() > 0) ? KeysArray->Num() : 0;
    if (Request.bDryRun)
    {
        TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
        Out->SetBoolField(TEXT("dry_run"), true);
        Out->SetStringField(TEXT("blackboard_path"), BlackboardPath);
        Out->SetNumberField(TEXT("requested_keys"), RequestedCount);
        Out->SetBoolField(TEXT("replace_existing"), bReplaceExisting);
        return {true, TEXT("Dry run blackboard schema edit succeeded."), SerializePayload(Out), TEXT("OK")};
    }

    FScriptArrayHelper KeysHelper(KeysProp, KeysProp->ContainerPtrToValuePtr<void>(BlackboardObj));
    if (bReplaceExisting)
    {
        KeysHelper.EmptyValues();
    }

    TSet<FName> ExistingNames;
    FNameProperty* EntryNameProp = CastField<FNameProperty>(EntryStructProp->Struct->FindPropertyByName(TEXT("EntryName")));
    if (EntryNameProp != nullptr)
    {
        for (int32 Index = 0; Index < KeysHelper.Num(); ++Index)
        {
            void* EntryValue = KeysHelper.GetRawPtr(Index);
            void* NamePtr = EntryNameProp->ContainerPtrToValuePtr<void>(EntryValue);
            ExistingNames.Add(EntryNameProp->GetPropertyValue(NamePtr));
        }
    }

    int32 Added = 0;
    if (KeysArray != nullptr)
    {
        for (const TSharedPtr<FJsonValue>& Value : *KeysArray)
        {
            const TSharedPtr<FJsonObject>* KeyObjPtr = nullptr;
            if (!Value.IsValid() || !Value->TryGetObject(KeyObjPtr) || KeyObjPtr == nullptr || !KeyObjPtr->IsValid())
            {
                continue;
            }
            const TSharedPtr<FJsonObject>& KeyObj = *KeyObjPtr;
            FString KeyName;
            KeyObj->TryGetStringField(TEXT("name"), KeyName);
            if (KeyName.IsEmpty())
            {
                continue;
            }

            const FName EntryName(*KeyName);
            if (ExistingNames.Contains(EntryName))
            {
                continue;
            }

            FString KeyTypeClassPath = TEXT("/Script/AIModule.BlackboardKeyType_Object");
            bool bInstanceSynced = false;
            KeyObj->TryGetStringField(TEXT("key_type_class"), KeyTypeClassPath);
            KeyObj->TryGetBoolField(TEXT("instance_synced"), bInstanceSynced);
            UClass* KeyTypeClass = ResolveClassByPath(KeyTypeClassPath);
            if (KeyTypeClass == nullptr)
            {
                continue;
            }

            const int32 NewIndex = KeysHelper.AddValue();
            void* EntryValue = KeysHelper.GetRawPtr(NewIndex);
            EntryStructProp->InitializeValue(EntryValue);
            SetStructNameField(EntryValue, EntryStructProp->Struct, TEXT("EntryName"), EntryName);
            UObject* KeyTypeObj = NewObject<UObject>(BlackboardObj, KeyTypeClass, NAME_None, RF_Transactional);
            SetStructObjectField(EntryValue, EntryStructProp->Struct, TEXT("KeyType"), KeyTypeObj);
            SetStructBoolField(EntryValue, EntryStructProp->Struct, TEXT("bInstanceSynced"), bInstanceSynced);
            ExistingNames.Add(EntryName);
            ++Added;
        }
    }

    BlackboardObj->MarkPackageDirty();
    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetBoolField(TEXT("dry_run"), false);
    Out->SetStringField(TEXT("blackboard_path"), BlackboardPath);
    Out->SetNumberField(TEXT("added_keys"), Added);
    Out->SetNumberField(TEXT("total_keys"), KeysHelper.Num());
    Out->SetBoolField(TEXT("replace_existing"), bReplaceExisting);
    return {true, TEXT("Blackboard schema edited."), SerializePayload(Out), TEXT("OK")};
}

static FAgentActionResult HandleEditBehaviorTreeAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString BehaviorTreePath;
    FString BlackboardPath;
    FString RootClassPath = TEXT("/Script/AIModule.BTComposite_Selector");
    const TArray<TSharedPtr<FJsonValue>>* TasksArray = nullptr;
    const TArray<TSharedPtr<FJsonValue>>* OperationsArray = nullptr;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("behavior_tree_path"), BehaviorTreePath);
        if (BehaviorTreePath.IsEmpty())
        {
            Payload->TryGetStringField(TEXT("asset_path"), BehaviorTreePath);
        }
        Payload->TryGetStringField(TEXT("blackboard_path"), BlackboardPath);
        Payload->TryGetStringField(TEXT("root_class_path"), RootClassPath);
        Payload->TryGetArrayField(TEXT("tasks"), TasksArray);
        Payload->TryGetArrayField(TEXT("operations"), OperationsArray);
    }
    if (BehaviorTreePath.IsEmpty())
    {
        return {false, TEXT("edit_behavior_tree_asset requires behavior_tree_path or asset_path."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    UObject* BehaviorTreeObj = ResolveAssetObject(BehaviorTreePath);
    if (BehaviorTreeObj == nullptr)
    {
        return {false, FString::Printf(TEXT("Behavior tree asset not found: %s"), *BehaviorTreePath), TEXT(""), TEXT("ASSET_NOT_FOUND")};
    }
    UClass* RootClass = ResolveClassByPath(RootClassPath);
    if (RootClass == nullptr)
    {
        return {false, FString::Printf(TEXT("root_class_path not found: %s"), *RootClassPath), TEXT(""), TEXT("CLASS_NOT_FOUND")};
    }
    UObject* BlackboardObj = BlackboardPath.IsEmpty() ? nullptr : ResolveAssetObject(BlackboardPath);

    int32 RequestedTasks = (TasksArray && TasksArray->Num() > 0) ? TasksArray->Num() : 0;
    const int32 RequestedOps = (OperationsArray && OperationsArray->Num() > 0) ? OperationsArray->Num() : 0;
    if (Request.bDryRun)
    {
        TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
        Out->SetBoolField(TEXT("dry_run"), true);
        Out->SetStringField(TEXT("behavior_tree_path"), BehaviorTreePath);
        Out->SetStringField(TEXT("root_class_path"), RootClassPath);
        Out->SetNumberField(TEXT("requested_tasks"), RequestedTasks);
        Out->SetNumberField(TEXT("requested_operations"), RequestedOps);
        Out->SetBoolField(TEXT("blackboard_bound"), BlackboardObj != nullptr);
        return {true, TEXT("Dry run behavior tree edit succeeded."), SerializePayload(Out), TEXT("OK")};
    }

    if (BlackboardObj != nullptr)
    {
        TrySetObjectProperty(BehaviorTreeObj, TEXT("BlackboardAsset"), BlackboardObj);
    }

    auto SetRootNode = [&](const FString& InRootClassPath) -> UObject*
    {
        UClass* RequestedRootClass = ResolveClassByPath(InRootClassPath);
        if (RequestedRootClass == nullptr)
        {
            return nullptr;
        }
        UObject* NewRootNode = NewObject<UObject>(BehaviorTreeObj, RequestedRootClass, NAME_None, RF_Transactional);
        if (!TrySetObjectProperty(BehaviorTreeObj, TEXT("RootNode"), NewRootNode))
        {
            return nullptr;
        }
        return NewRootNode;
    };

    UObject* RootNodeObj = SetRootNode(RootClassPath);
    if (RootNodeObj == nullptr)
    {
        return {false, TEXT("BehaviorTree RootNode is not writable for this engine version."), TEXT(""), TEXT("UNSUPPORTED")};
    }

    FArrayProperty* ChildrenProp = nullptr;
    FStructProperty* ChildStructProp = nullptr;
    TUniquePtr<FScriptArrayHelper> ChildrenHelper;
    auto RebindChildren = [&]() -> bool
    {
        ChildrenProp = CastField<FArrayProperty>(RootNodeObj->GetClass()->FindPropertyByName(TEXT("Children")));
        ChildStructProp = ChildrenProp ? CastField<FStructProperty>(ChildrenProp->Inner) : nullptr;
        if (ChildrenProp == nullptr || ChildStructProp == nullptr)
        {
            return false;
        }
        ChildrenHelper = MakeUnique<FScriptArrayHelper>(ChildrenProp, ChildrenProp->ContainerPtrToValuePtr<void>(RootNodeObj));
        return true;
    };
    if (!RebindChildren())
    {
        return {false, TEXT("Behavior tree root children array is not writable for this engine version."), TEXT(""), TEXT("UNSUPPORTED")};
    }

    auto AddTaskChild = [&](const FString& TaskClassPath, const float WaitTime) -> bool
    {
        if (!ChildrenHelper.IsValid() || ChildStructProp == nullptr)
        {
            return false;
        }
        UClass* TaskClass = ResolveClassByPath(TaskClassPath);
        if (TaskClass == nullptr)
        {
            return false;
        }
        UObject* TaskNodeObj = NewObject<UObject>(BehaviorTreeObj, TaskClass, NAME_None, RF_Transactional);
        TrySetFloatProperty(TaskNodeObj, TEXT("WaitTime"), WaitTime);
        const int32 NewIndex = ChildrenHelper->AddValue();
        void* ChildValue = ChildrenHelper->GetRawPtr(NewIndex);
        ChildStructProp->InitializeValue(ChildValue);
        return SetStructObjectField(ChildValue, ChildStructProp->Struct, TEXT("ChildTask"), TaskNodeObj);
    };

    auto AddCompositeChild = [&](const FString& CompositeClassPath) -> bool
    {
        if (!ChildrenHelper.IsValid() || ChildStructProp == nullptr)
        {
            return false;
        }
        UClass* CompositeClass = ResolveClassByPath(CompositeClassPath);
        if (CompositeClass == nullptr)
        {
            return false;
        }
        UObject* CompositeNodeObj = NewObject<UObject>(BehaviorTreeObj, CompositeClass, NAME_None, RF_Transactional);
        const int32 NewIndex = ChildrenHelper->AddValue();
        void* ChildValue = ChildrenHelper->GetRawPtr(NewIndex);
        ChildStructProp->InitializeValue(ChildValue);
        return SetStructObjectField(ChildValue, ChildStructProp->Struct, TEXT("ChildComposite"), CompositeNodeObj);
    };

    int32 CreatedComposites = 0;
    int32 AppliedOps = 0;
    int32 CreatedTasks = 0;
    if (OperationsArray != nullptr && OperationsArray->Num() > 0)
    {
        for (const TSharedPtr<FJsonValue>& Value : *OperationsArray)
        {
            const TSharedPtr<FJsonObject>* OpObj = nullptr;
            if (!Value.IsValid() || !Value->TryGetObject(OpObj) || OpObj == nullptr || !OpObj->IsValid())
            {
                continue;
            }
            FString OpName;
            (*OpObj)->TryGetStringField(TEXT("op"), OpName);
            if (OpName.IsEmpty())
            {
                (*OpObj)->TryGetStringField(TEXT("operation"), OpName);
            }
            const FString NormalizedOp = NormalizeLookupKey(OpName);
            if (NormalizedOp.IsEmpty())
            {
                continue;
            }
            if (NormalizedOp == TEXT("setblackboardasset"))
            {
                FString LocalBlackboardPath;
                (*OpObj)->TryGetStringField(TEXT("blackboard_path"), LocalBlackboardPath);
                UObject* LocalBlackboard = ResolveAssetObject(LocalBlackboardPath);
                if (LocalBlackboard != nullptr && TrySetObjectProperty(BehaviorTreeObj, TEXT("BlackboardAsset"), LocalBlackboard))
                {
                    ++AppliedOps;
                }
                continue;
            }
            if (NormalizedOp == TEXT("setrootclass"))
            {
                FString LocalRootClassPath = RootClassPath;
                (*OpObj)->TryGetStringField(TEXT("root_class_path"), LocalRootClassPath);
                UObject* NewRoot = SetRootNode(LocalRootClassPath);
                if (NewRoot != nullptr)
                {
                    RootNodeObj = NewRoot;
                    if (RebindChildren())
                    {
                        ++AppliedOps;
                    }
                }
                continue;
            }
            if (NormalizedOp == TEXT("clearrootchildren"))
            {
                if (ChildrenHelper.IsValid())
                {
                    ChildrenHelper->EmptyValues();
                    ++AppliedOps;
                }
                continue;
            }
            if (NormalizedOp == TEXT("addtaskchild"))
            {
                FString TaskClassPath = TEXT("/Script/AIModule.BTTask_Wait");
                float WaitTime = 0.2f;
                (*OpObj)->TryGetStringField(TEXT("class_path"), TaskClassPath);
                (*OpObj)->TryGetNumberField(TEXT("wait_time"), WaitTime);
                if (AddTaskChild(TaskClassPath, WaitTime))
                {
                    ++CreatedTasks;
                    ++AppliedOps;
                }
                continue;
            }
            if (NormalizedOp == TEXT("addcompositechild"))
            {
                FString CompositeClassPath = TEXT("/Script/AIModule.BTComposite_Sequence");
                (*OpObj)->TryGetStringField(TEXT("class_path"), CompositeClassPath);
                if (AddCompositeChild(CompositeClassPath))
                {
                    ++CreatedComposites;
                    ++AppliedOps;
                }
                continue;
            }
        }
    }
    else
    {
        if (ChildrenHelper.IsValid())
        {
            ChildrenHelper->EmptyValues();
        }
        if (TasksArray != nullptr)
        {
            for (const TSharedPtr<FJsonValue>& Value : *TasksArray)
            {
                FString TaskClassPath = TEXT("/Script/AIModule.BTTask_Wait");
                float WaitTime = 0.2f;
                if (Value.IsValid())
                {
                    FString TaskClassFromString;
                    if (Value->TryGetString(TaskClassFromString) && !TaskClassFromString.IsEmpty())
                    {
                        TaskClassPath = TaskClassFromString;
                    }
                    else
                    {
                        const TSharedPtr<FJsonObject>* TaskObj = nullptr;
                        if (Value->TryGetObject(TaskObj) && TaskObj != nullptr && TaskObj->IsValid())
                        {
                            (*TaskObj)->TryGetStringField(TEXT("class_path"), TaskClassPath);
                            (*TaskObj)->TryGetNumberField(TEXT("wait_time"), WaitTime);
                        }
                    }
                }
                if (AddTaskChild(TaskClassPath, WaitTime))
                {
                    ++CreatedTasks;
                }
            }
        }
    }

    if (CreatedTasks == 0 && CreatedComposites == 0 && ChildrenHelper.IsValid() && ChildrenHelper->Num() == 0)
    {
        if (AddTaskChild(TEXT("/Script/AIModule.BTTask_Wait"), 0.2f))
        {
            ++CreatedTasks;
        }
    }

    BehaviorTreeObj->MarkPackageDirty();
    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetBoolField(TEXT("dry_run"), false);
    Out->SetStringField(TEXT("behavior_tree_path"), BehaviorTreePath);
    Out->SetStringField(TEXT("root_class_path"), RootClassPath);
    Out->SetBoolField(TEXT("blackboard_bound"), BlackboardObj != nullptr);
    Out->SetNumberField(TEXT("task_nodes_created"), CreatedTasks);
    Out->SetNumberField(TEXT("composite_nodes_created"), CreatedComposites);
    Out->SetNumberField(TEXT("operations_applied"), AppliedOps);
    Out->SetNumberField(TEXT("root_children_count"), ChildrenHelper.IsValid() ? ChildrenHelper->Num() : 0);
    return {true, TEXT("Behavior tree edited."), SerializePayload(Out), TEXT("OK")};
}

static FAgentActionResult HandleEditEQSQueryAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString EQSPath;
    bool bReplaceOptions = true;
    const TArray<TSharedPtr<FJsonValue>>* OptionsArray = nullptr;
    const TArray<TSharedPtr<FJsonValue>>* OperationsArray = nullptr;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("eqs_path"), EQSPath);
        if (EQSPath.IsEmpty())
        {
            Payload->TryGetStringField(TEXT("asset_path"), EQSPath);
        }
        Payload->TryGetBoolField(TEXT("replace_options"), bReplaceOptions);
        Payload->TryGetArrayField(TEXT("options"), OptionsArray);
        Payload->TryGetArrayField(TEXT("operations"), OperationsArray);
    }
    if (EQSPath.IsEmpty())
    {
        return {false, TEXT("edit_eqs_query_asset requires eqs_path or asset_path."), TEXT(""), TEXT("MISSING_FIELD")};
    }
    UObject* EQSObj = ResolveAssetObject(EQSPath);
    if (EQSObj == nullptr)
    {
        return {false, FString::Printf(TEXT("EQS asset not found: %s"), *EQSPath), TEXT(""), TEXT("ASSET_NOT_FOUND")};
    }

    const int32 RequestedOptions = (OptionsArray && OptionsArray->Num() > 0) ? OptionsArray->Num() : 0;
    const int32 RequestedOps = (OperationsArray && OperationsArray->Num() > 0) ? OperationsArray->Num() : 0;
    if (Request.bDryRun)
    {
        TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
        Out->SetBoolField(TEXT("dry_run"), true);
        Out->SetStringField(TEXT("eqs_path"), EQSPath);
        Out->SetNumberField(TEXT("requested_options"), RequestedOptions);
        Out->SetNumberField(TEXT("requested_operations"), RequestedOps);
        Out->SetBoolField(TEXT("replace_options"), bReplaceOptions);
        return {true, TEXT("Dry run EQS edit succeeded."), SerializePayload(Out), TEXT("OK")};
    }

    int32 CreatedOptions = 0;
    int32 CreatedTests = 0;
    int32 AppliedOps = 0;

    auto AddOptionFromObject = [&](const TSharedPtr<FJsonObject>& OptionObj) -> bool
    {
        if (!OptionObj.IsValid())
        {
            return false;
        }
        FString OptionClassPath = TEXT("/Script/AIModule.EnvQueryOption");
        FString GeneratorClassPath = TEXT("/Script/AIModule.EnvQueryGenerator_ActorsOfClass");
        const TArray<TSharedPtr<FJsonValue>>* TestsArray = nullptr;
        OptionObj->TryGetStringField(TEXT("option_class_path"), OptionClassPath);
        OptionObj->TryGetStringField(TEXT("generator_class_path"), GeneratorClassPath);
        OptionObj->TryGetArrayField(TEXT("test_class_paths"), TestsArray);

        UClass* OptionClass = ResolveClassByPath(OptionClassPath);
        if (OptionClass == nullptr)
        {
            return false;
        }
        UObject* OptionInstance = NewObject<UObject>(EQSObj, OptionClass, NAME_None, RF_Transactional);
        UClass* GeneratorClass = ResolveClassByPath(GeneratorClassPath);
        if (GeneratorClass != nullptr)
        {
            UObject* GeneratorInstance = NewObject<UObject>(OptionInstance, GeneratorClass, NAME_None, RF_Transactional);
            TrySetObjectProperty(OptionInstance, TEXT("Generator"), GeneratorInstance);
        }
        if (TestsArray != nullptr)
        {
            for (const TSharedPtr<FJsonValue>& TestValue : *TestsArray)
            {
                FString TestClassPath;
                if (!TestValue.IsValid() || !TestValue->TryGetString(TestClassPath) || TestClassPath.IsEmpty())
                {
                    continue;
                }
                UClass* TestClass = ResolveClassByPath(TestClassPath);
                if (TestClass == nullptr)
                {
                    continue;
                }
                UObject* TestInstance = NewObject<UObject>(OptionInstance, TestClass, NAME_None, RF_Transactional);
                if (AddObjectToArrayProperty(OptionInstance, TEXT("Tests"), TestInstance))
                {
                    ++CreatedTests;
                }
            }
        }
        if (AddObjectToArrayProperty(EQSObj, TEXT("Options"), OptionInstance))
        {
            ++CreatedOptions;
            return true;
        }
        return false;
    };

    if (OperationsArray != nullptr && OperationsArray->Num() > 0)
    {
        for (const TSharedPtr<FJsonValue>& Value : *OperationsArray)
        {
            const TSharedPtr<FJsonObject>* OpObj = nullptr;
            if (!Value.IsValid() || !Value->TryGetObject(OpObj) || OpObj == nullptr || !OpObj->IsValid())
            {
                continue;
            }
            FString OpName;
            (*OpObj)->TryGetStringField(TEXT("op"), OpName);
            if (OpName.IsEmpty())
            {
                (*OpObj)->TryGetStringField(TEXT("operation"), OpName);
            }
            const FString NormalizedOp = NormalizeLookupKey(OpName);
            if (NormalizedOp.IsEmpty())
            {
                continue;
            }
            if (NormalizedOp == TEXT("clearoptions"))
            {
                if (ClearObjectArrayProperty(EQSObj, TEXT("Options")))
                {
                    ++AppliedOps;
                }
                continue;
            }
            if (NormalizedOp == TEXT("addoption"))
            {
                const TSharedPtr<FJsonObject>* OptionObj = nullptr;
                if ((*OpObj)->TryGetObjectField(TEXT("option"), OptionObj) && OptionObj != nullptr && OptionObj->IsValid())
                {
                    if (AddOptionFromObject(*OptionObj))
                    {
                        ++AppliedOps;
                    }
                }
                else if (AddOptionFromObject(*OpObj))
                {
                    ++AppliedOps;
                }
                continue;
            }
            if (NormalizedOp == TEXT("setgeneratoronoption"))
            {
                const int32 OptionIndex = ReadIntOrDefault(*OpObj, TEXT("option_index"), -1);
                FString GeneratorClassPath = TEXT("/Script/AIModule.EnvQueryGenerator_ActorsOfClass");
                (*OpObj)->TryGetStringField(TEXT("generator_class_path"), GeneratorClassPath);
                FArrayProperty* OptionsProp = CastField<FArrayProperty>(EQSObj->GetClass()->FindPropertyByName(TEXT("Options")));
                FObjectPropertyBase* InnerObj = OptionsProp ? CastField<FObjectPropertyBase>(OptionsProp->Inner) : nullptr;
                if (OptionsProp != nullptr && InnerObj != nullptr)
                {
                    FScriptArrayHelper OptionsHelper(OptionsProp, OptionsProp->ContainerPtrToValuePtr<void>(EQSObj));
                    if (OptionsHelper.IsValidIndex(OptionIndex))
                    {
                        UObject* OptionInstance = InnerObj->GetObjectPropertyValue(OptionsHelper.GetRawPtr(OptionIndex));
                        UClass* GeneratorClass = ResolveClassByPath(GeneratorClassPath);
                        if (OptionInstance != nullptr && GeneratorClass != nullptr)
                        {
                            UObject* GeneratorInstance = NewObject<UObject>(OptionInstance, GeneratorClass, NAME_None, RF_Transactional);
                            if (TrySetObjectProperty(OptionInstance, TEXT("Generator"), GeneratorInstance))
                            {
                                ++AppliedOps;
                            }
                        }
                    }
                }
                continue;
            }
            if (NormalizedOp == TEXT("addtesttooption"))
            {
                const int32 OptionIndex = ReadIntOrDefault(*OpObj, TEXT("option_index"), -1);
                FString TestClassPath;
                (*OpObj)->TryGetStringField(TEXT("test_class_path"), TestClassPath);
                FArrayProperty* OptionsProp = CastField<FArrayProperty>(EQSObj->GetClass()->FindPropertyByName(TEXT("Options")));
                FObjectPropertyBase* InnerObj = OptionsProp ? CastField<FObjectPropertyBase>(OptionsProp->Inner) : nullptr;
                if (OptionsProp != nullptr && InnerObj != nullptr)
                {
                    FScriptArrayHelper OptionsHelper(OptionsProp, OptionsProp->ContainerPtrToValuePtr<void>(EQSObj));
                    if (OptionsHelper.IsValidIndex(OptionIndex))
                    {
                        UObject* OptionInstance = InnerObj->GetObjectPropertyValue(OptionsHelper.GetRawPtr(OptionIndex));
                        UClass* TestClass = ResolveClassByPath(TestClassPath);
                        if (OptionInstance != nullptr && TestClass != nullptr)
                        {
                            UObject* TestInstance = NewObject<UObject>(OptionInstance, TestClass, NAME_None, RF_Transactional);
                            if (AddObjectToArrayProperty(OptionInstance, TEXT("Tests"), TestInstance))
                            {
                                ++CreatedTests;
                                ++AppliedOps;
                            }
                        }
                    }
                }
                continue;
            }
        }
    }
    else
    {
        if (bReplaceOptions)
        {
            ClearObjectArrayProperty(EQSObj, TEXT("Options"));
        }
        if (OptionsArray != nullptr)
        {
            for (const TSharedPtr<FJsonValue>& Value : *OptionsArray)
            {
                const TSharedPtr<FJsonObject>* OptionObj = nullptr;
                if (!Value.IsValid() || !Value->TryGetObject(OptionObj) || OptionObj == nullptr || !OptionObj->IsValid())
                {
                    continue;
                }
                AddOptionFromObject(*OptionObj);
            }
        }
    }

    EQSObj->MarkPackageDirty();
    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetBoolField(TEXT("dry_run"), false);
    Out->SetStringField(TEXT("eqs_path"), EQSPath);
    Out->SetNumberField(TEXT("options_created"), CreatedOptions);
    Out->SetNumberField(TEXT("tests_created"), CreatedTests);
    Out->SetNumberField(TEXT("operations_applied"), AppliedOps);
    return {true, TEXT("EQS query edited."), SerializePayload(Out), TEXT("OK")};
}

static FAgentActionResult HandleEditAnimBlueprintStateMachine(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString AnimBlueprintPath;
    FString StateMachineName = TEXT("LocomotionSM");
    const TArray<TSharedPtr<FJsonValue>>* StatesArray = nullptr;
    const TArray<TSharedPtr<FJsonValue>>* OperationsArray = nullptr;
    bool bCompileAfter = true;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("anim_blueprint_path"), AnimBlueprintPath);
        if (AnimBlueprintPath.IsEmpty())
        {
            Payload->TryGetStringField(TEXT("asset_path"), AnimBlueprintPath);
        }
        Payload->TryGetStringField(TEXT("state_machine_name"), StateMachineName);
        Payload->TryGetArrayField(TEXT("states"), StatesArray);
        Payload->TryGetArrayField(TEXT("operations"), OperationsArray);
        Payload->TryGetBoolField(TEXT("compile_after"), bCompileAfter);
    }
    if (AnimBlueprintPath.IsEmpty())
    {
        return {false, TEXT("edit_anim_blueprint_state_machine requires anim_blueprint_path or asset_path."), TEXT(""), TEXT("MISSING_FIELD")};
    }

    UAnimBlueprint* AnimBlueprint = Cast<UAnimBlueprint>(ResolveAssetObject(AnimBlueprintPath));
    if (AnimBlueprint == nullptr)
    {
        return {false, FString::Printf(TEXT("AnimBlueprint asset not found: %s"), *AnimBlueprintPath), TEXT(""), TEXT("ASSET_NOT_FOUND")};
    }

    UAnimationStateMachineGraph* StateMachineGraph = FindAnimationStateMachineGraph(AnimBlueprint, StateMachineName);
    if (StateMachineGraph == nullptr)
    {
        return {false, TEXT("No state machine graph found. Create a state machine in the AnimGraph first, then re-run edit operations."), TEXT(""), TEXT("STATE_MACHINE_NOT_FOUND")};
    }

    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetBoolField(TEXT("dry_run"), Request.bDryRun);
    Out->SetStringField(TEXT("anim_blueprint_path"), AnimBlueprintPath);
    Out->SetStringField(TEXT("state_machine_name"), StateMachineName);
    Out->SetStringField(TEXT("state_machine_graph"), StateMachineGraph->GetPathName());
    Out->SetNumberField(TEXT("requested_states"), StatesArray ? StatesArray->Num() : 0);
    Out->SetNumberField(TEXT("requested_operations"), OperationsArray ? OperationsArray->Num() : 0);
    if (Request.bDryRun)
    {
        return {true, TEXT("Dry run AnimBlueprint state-machine edit succeeded."), SerializePayload(Out), TEXT("OK")};
    }

    AnimBlueprint->Modify();
    StateMachineGraph->Modify();

    auto AddStateNode = [&](const FString& InStateName, const int32 PosX, const int32 PosY) -> UAnimStateNode*
    {
        const FString SafeStateName = ObjectTools::SanitizeObjectName(InStateName);
        if (SafeStateName.IsEmpty())
        {
            return nullptr;
        }
        if (UAnimStateNode* Existing = FindAnimStateNodeByName(StateMachineGraph, SafeStateName))
        {
            return Existing;
        }
        UAnimStateNode* NewState = NewObject<UAnimStateNode>(StateMachineGraph, UAnimStateNode::StaticClass(), NAME_None, RF_Transactional);
        if (NewState == nullptr)
        {
            return nullptr;
        }
        StateMachineGraph->AddNode(NewState, true, false);
        NewState->CreateNewGuid();
        NewState->PostPlacedNewNode();
        NewState->AllocateDefaultPins();
        NewState->NodePosX = PosX;
        NewState->NodePosY = PosY;
        if (NewState->BoundGraph != nullptr)
        {
            FBlueprintEditorUtils::RenameGraph(NewState->BoundGraph, SafeStateName);
        }
        return NewState;
    };

    auto ConnectEntryToState = [&](UAnimStateNode* StateNode) -> bool
    {
        if (StateNode == nullptr || StateMachineGraph->EntryNode == nullptr)
        {
            return false;
        }
        UEdGraphPin* EntryPin = StateMachineGraph->EntryNode->GetOutputPin();
        UEdGraphPin* TargetPin = StateNode->GetInputPin();
        const UEdGraphSchema* GraphSchema = StateMachineGraph->GetSchema();
        if (EntryPin == nullptr || TargetPin == nullptr || GraphSchema == nullptr)
        {
            return false;
        }
        return GraphSchema->TryCreateConnection(EntryPin, TargetPin);
    };

    auto AddTransition = [&](UAnimStateNode* FromState, UAnimStateNode* ToState, const float CrossfadeDuration) -> bool
    {
        if (FromState == nullptr || ToState == nullptr)
        {
            return false;
        }
        UAnimStateTransitionNode* Transition = NewObject<UAnimStateTransitionNode>(StateMachineGraph, UAnimStateTransitionNode::StaticClass(), NAME_None, RF_Transactional);
        if (Transition == nullptr)
        {
            return false;
        }
        StateMachineGraph->AddNode(Transition, true, false);
        Transition->CreateNewGuid();
        Transition->PostPlacedNewNode();
        Transition->AllocateDefaultPins();
        Transition->NodePosX = (FromState->NodePosX + ToState->NodePosX) / 2;
        Transition->NodePosY = (FromState->NodePosY + ToState->NodePosY) / 2;
        Transition->CrossfadeDuration = CrossfadeDuration;
        Transition->CreateConnections(FromState, ToState);
        return true;
    };

    int32 StateCount = 0;
    int32 TransitionCount = 0;
    int32 AppliedOps = 0;

    if (OperationsArray != nullptr && OperationsArray->Num() > 0)
    {
        for (const TSharedPtr<FJsonValue>& Value : *OperationsArray)
        {
            const TSharedPtr<FJsonObject>* OpObj = nullptr;
            if (!Value.IsValid() || !Value->TryGetObject(OpObj) || OpObj == nullptr || !OpObj->IsValid())
            {
                continue;
            }
            FString OpName;
            (*OpObj)->TryGetStringField(TEXT("op"), OpName);
            if (OpName.IsEmpty())
            {
                (*OpObj)->TryGetStringField(TEXT("operation"), OpName);
            }
            const FString NormalizedOp = NormalizeLookupKey(OpName);
            if (NormalizedOp.IsEmpty())
            {
                continue;
            }
            if (NormalizedOp == TEXT("addstate"))
            {
                FString StateName;
                (*OpObj)->TryGetStringField(TEXT("state_name"), StateName);
                if (StateName.IsEmpty())
                {
                    continue;
                }
                FVector2D NodePos(static_cast<float>(220 * (StateCount + 1)), 0.0f);
                ReadVector2Field(*OpObj, TEXT("node_position"), NodePos);
                UAnimStateNode* AddedState = AddStateNode(StateName, static_cast<int32>(NodePos.X), static_cast<int32>(NodePos.Y));
                if (AddedState != nullptr)
                {
                    ++StateCount;
                    ++AppliedOps;
                }
                continue;
            }
            if (NormalizedOp == TEXT("connectentry"))
            {
                FString StateName;
                (*OpObj)->TryGetStringField(TEXT("state_name"), StateName);
                UAnimStateNode* StateNode = FindAnimStateNodeByName(StateMachineGraph, StateName);
                if (StateNode != nullptr && ConnectEntryToState(StateNode))
                {
                    ++AppliedOps;
                }
                continue;
            }
            if (NormalizedOp == TEXT("addtransition"))
            {
                FString FromStateName;
                FString ToStateName;
                float CrossfadeDuration = 0.2f;
                (*OpObj)->TryGetStringField(TEXT("from_state"), FromStateName);
                (*OpObj)->TryGetStringField(TEXT("to_state"), ToStateName);
                (*OpObj)->TryGetNumberField(TEXT("crossfade_duration"), CrossfadeDuration);
                UAnimStateNode* FromState = FindAnimStateNodeByName(StateMachineGraph, FromStateName);
                UAnimStateNode* ToState = FindAnimStateNodeByName(StateMachineGraph, ToStateName);
                if (AddTransition(FromState, ToState, CrossfadeDuration))
                {
                    ++TransitionCount;
                    ++AppliedOps;
                }
                continue;
            }
        }
    }
    else if (StatesArray != nullptr)
    {
        TArray<UAnimStateNode*> OrderedStates;
        int32 Index = 0;
        for (const TSharedPtr<FJsonValue>& Value : *StatesArray)
        {
            const TSharedPtr<FJsonObject>* StateObj = nullptr;
            if (!Value.IsValid() || !Value->TryGetObject(StateObj) || StateObj == nullptr || !StateObj->IsValid())
            {
                continue;
            }
            FString StateName;
            (*StateObj)->TryGetStringField(TEXT("state_name"), StateName);
            if (StateName.IsEmpty())
            {
                continue;
            }
            const int32 X = 240 * (Index + 1);
            const int32 Y = 0;
            UAnimStateNode* AddedState = AddStateNode(StateName, X, Y);
            if (AddedState != nullptr)
            {
                OrderedStates.Add(AddedState);
                ++StateCount;
                ++Index;
            }
        }
        if (OrderedStates.Num() > 0)
        {
            ConnectEntryToState(OrderedStates[0]);
        }
        for (int32 I = 0; I + 1 < OrderedStates.Num(); ++I)
        {
            if (AddTransition(OrderedStates[I], OrderedStates[I + 1], 0.2f))
            {
                ++TransitionCount;
            }
        }
    }

    AnimBlueprint->MarkPackageDirty();

    bool bCompileSuccess = true;
    FString CompileMessage = TEXT("Compile skipped.");
    if (bCompileAfter)
    {
        TSharedRef<FJsonObject> CompilePayload = MakeShared<FJsonObject>();
        CompilePayload->SetStringField(TEXT("blueprint_path"), AnimBlueprintPath);
        const FAgentActionResult CompileResult = ExecuteNamedAction(TEXT("compile_blueprint"), CompilePayload, false);
        bCompileSuccess = CompileResult.bSuccess;
        CompileMessage = CompileResult.Message;
    }

    Out->SetNumberField(TEXT("states_added"), StateCount);
    Out->SetNumberField(TEXT("transitions_added"), TransitionCount);
    Out->SetNumberField(TEXT("operations_applied"), AppliedOps);
    Out->SetBoolField(TEXT("compile_after"), bCompileAfter);
    Out->SetBoolField(TEXT("compile_success"), bCompileSuccess);
    Out->SetStringField(TEXT("compile_message"), CompileMessage);
    return {bCompileSuccess, TEXT("AnimBlueprint state-machine graph edited."), SerializePayload(Out), bCompileSuccess ? TEXT("OK") : TEXT("COMPILE_FAILED")};
}

static FAgentActionResult HandleEditMaterialAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString MaterialPath;
    bool bTwoSided = false;
    int32 BlendMode = 0;
    int32 ShadingModel = 1;
    const TArray<TSharedPtr<FJsonValue>>* OperationsArray = nullptr;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("material_path"), MaterialPath);
        if (MaterialPath.IsEmpty())
        {
            Payload->TryGetStringField(TEXT("asset_path"), MaterialPath);
        }
        Payload->TryGetBoolField(TEXT("two_sided"), bTwoSided);
        BlendMode = ReadIntOrDefault(Payload, TEXT("blend_mode"), 0);
        ShadingModel = ReadIntOrDefault(Payload, TEXT("shading_model"), 1);
        Payload->TryGetArrayField(TEXT("operations"), OperationsArray);
    }
    if (MaterialPath.IsEmpty())
    {
        return {false, TEXT("edit_material_asset requires material_path or asset_path."), TEXT(""), TEXT("MISSING_FIELD")};
    }
    UObject* MaterialObj = ResolveAssetObject(MaterialPath);
    if (MaterialObj == nullptr)
    {
        return {false, FString::Printf(TEXT("Material asset not found: %s"), *MaterialPath), TEXT(""), TEXT("ASSET_NOT_FOUND")};
    }
    UMaterial* Material = Cast<UMaterial>(MaterialObj);
    if (Material == nullptr)
    {
        return {false, TEXT("Resolved asset is not a UMaterial."), TEXT(""), TEXT("INVALID_ASSET_TYPE")};
    }

    const int32 RequestedOps = (OperationsArray && OperationsArray->Num() > 0) ? OperationsArray->Num() : 0;
    int32 ExpressionsCreated = 0;
    int32 ExpressionsRemoved = 0;
    int32 ConnectionsApplied = 0;
    int32 OperationsApplied = 0;

    if (!Request.bDryRun)
    {
        Material->Modify();
        TrySetBoolProperty(Material, TEXT("TwoSided"), bTwoSided);
        TrySetIntProperty(Material, TEXT("BlendMode"), static_cast<int64>(BlendMode));
        TrySetIntProperty(Material, TEXT("ShadingModel"), static_cast<int64>(ShadingModel));

        TMap<FString, UMaterialExpression*> ExpressionLookup;
        BuildMaterialExpressionLookup(Material, ExpressionLookup);
        int32 NextNodeX = 0;
        int32 NextNodeY = 0;

        if (OperationsArray != nullptr)
        {
            for (const TSharedPtr<FJsonValue>& Value : *OperationsArray)
            {
                const TSharedPtr<FJsonObject>* OpObj = nullptr;
                if (!Value.IsValid() || !Value->TryGetObject(OpObj) || OpObj == nullptr || !OpObj->IsValid())
                {
                    continue;
                }
                FString OpName;
                (*OpObj)->TryGetStringField(TEXT("op"), OpName);
                if (OpName.IsEmpty())
                {
                    (*OpObj)->TryGetStringField(TEXT("operation"), OpName);
                }
                const FString NormalizedOp = NormalizeLookupKey(OpName);
                if (NormalizedOp.IsEmpty())
                {
                    continue;
                }
                if (NormalizedOp == TEXT("cleargraph"))
                {
                    Material->GetExpressionCollection().Empty();
                    DisconnectAllMaterialProperties(Material);
                    BuildMaterialExpressionLookup(Material, ExpressionLookup);
                    ++OperationsApplied;
                    continue;
                }
                if (NormalizedOp == TEXT("createexpression"))
                {
                    FString ClassPath;
                    FString ExpressionName;
                    (*OpObj)->TryGetStringField(TEXT("expression_class_path"), ClassPath);
                    if (ClassPath.IsEmpty())
                    {
                        (*OpObj)->TryGetStringField(TEXT("class_path"), ClassPath);
                    }
                    (*OpObj)->TryGetStringField(TEXT("expression_name"), ExpressionName);
                    UClass* ExpressionClass = ResolveMaterialExpressionClass(ClassPath);
                    if (ExpressionClass == nullptr || !ExpressionClass->IsChildOf(UMaterialExpression::StaticClass()))
                    {
                        continue;
                    }
                    const FString SafeName = ObjectTools::SanitizeObjectName(ExpressionName);
                    const FName ObjectName = SafeName.IsEmpty() ? NAME_None : FName(*SafeName);
                    UMaterialExpression* NewExpression = NewObject<UMaterialExpression>(Material, ExpressionClass, ObjectName, RF_Transactional);
                    if (NewExpression == nullptr)
                    {
                        continue;
                    }
                    FVector2D NodePos(static_cast<float>(NextNodeX), static_cast<float>(NextNodeY));
                    if (!ReadVector2Field(*OpObj, TEXT("node_position"), NodePos))
                    {
                        NextNodeX += 240;
                    }
                    NewExpression->MaterialExpressionEditorX = static_cast<int32>(NodePos.X);
                    NewExpression->MaterialExpressionEditorY = static_cast<int32>(NodePos.Y);
                    NewExpression->Material = Material;
                    ApplyMaterialExpressionDefaults(NewExpression, *OpObj);
                    Material->GetExpressionCollection().AddExpression(NewExpression);
                    BuildMaterialExpressionLookup(Material, ExpressionLookup);
                    ++ExpressionsCreated;
                    ++OperationsApplied;
                    continue;
                }
                if (NormalizedOp == TEXT("removeexpression"))
                {
                    FString ExpressionKey;
                    (*OpObj)->TryGetStringField(TEXT("expression_name"), ExpressionKey);
                    UMaterialExpression* Expression = ResolveMaterialExpressionByKey(Material, ExpressionLookup, ExpressionKey);
                    if (Expression != nullptr)
                    {
                        Material->GetExpressionCollection().RemoveExpression(Expression);
                        BuildMaterialExpressionLookup(Material, ExpressionLookup);
                        ++ExpressionsRemoved;
                        ++OperationsApplied;
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("connectexpressioninput"))
                {
                    FString FromExpression;
                    FString ToExpression;
                    FString InputName;
                    const int32 OutputIndex = ReadIntOrDefault(*OpObj, TEXT("output_index"), 0);
                    (*OpObj)->TryGetStringField(TEXT("from_expression"), FromExpression);
                    (*OpObj)->TryGetStringField(TEXT("to_expression"), ToExpression);
                    (*OpObj)->TryGetStringField(TEXT("to_input_name"), InputName);
                    if (InputName.IsEmpty())
                    {
                        (*OpObj)->TryGetStringField(TEXT("input_name"), InputName);
                    }
                    UMaterialExpression* FromNode = ResolveMaterialExpressionByKey(Material, ExpressionLookup, FromExpression);
                    UMaterialExpression* ToNode = ResolveMaterialExpressionByKey(Material, ExpressionLookup, ToExpression);
                    if (FromNode != nullptr && ToNode != nullptr && !InputName.IsEmpty())
                    {
                        if (ConnectExpressionStructField(ToNode, *InputName, FromNode, OutputIndex))
                        {
                            ++ConnectionsApplied;
                            ++OperationsApplied;
                        }
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("connecttomaterialproperty"))
                {
                    FString FromExpression;
                    FString MaterialProperty;
                    const int32 OutputIndex = ReadIntOrDefault(*OpObj, TEXT("output_index"), 0);
                    (*OpObj)->TryGetStringField(TEXT("from_expression"), FromExpression);
                    (*OpObj)->TryGetStringField(TEXT("material_property"), MaterialProperty);
                    UMaterialExpression* FromNode = ResolveMaterialExpressionByKey(Material, ExpressionLookup, FromExpression);
                    if (FromNode != nullptr && ConnectMaterialProperty(Material, MaterialProperty, FromNode, OutputIndex))
                    {
                        ++ConnectionsApplied;
                        ++OperationsApplied;
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("disconnectmaterialproperty"))
                {
                    FString MaterialProperty;
                    (*OpObj)->TryGetStringField(TEXT("material_property"), MaterialProperty);
                    if (!MaterialProperty.IsEmpty() && DisconnectMaterialProperty(Material, MaterialProperty))
                    {
                        ++ConnectionsApplied;
                        ++OperationsApplied;
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("setexpressionscalar"))
                {
                    FString ExpressionKey;
                    FString PropertyName = TEXT("R");
                    const float ScalarValue = ReadFloatOrDefault(*OpObj, TEXT("value"), 0.0f);
                    (*OpObj)->TryGetStringField(TEXT("expression_name"), ExpressionKey);
                    (*OpObj)->TryGetStringField(TEXT("property_name"), PropertyName);
                    UMaterialExpression* Expression = ResolveMaterialExpressionByKey(Material, ExpressionLookup, ExpressionKey);
                    if (Expression != nullptr && TrySetFloatProperty(Expression, *PropertyName, ScalarValue))
                    {
                        ++OperationsApplied;
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("setexpressionvector"))
                {
                    FString ExpressionKey;
                    FString PropertyName = TEXT("Constant");
                    FLinearColor VectorValue = FLinearColor::White;
                    (*OpObj)->TryGetStringField(TEXT("expression_name"), ExpressionKey);
                    (*OpObj)->TryGetStringField(TEXT("property_name"), PropertyName);
                    UMaterialExpression* Expression = ResolveMaterialExpressionByKey(Material, ExpressionLookup, ExpressionKey);
                    if (Expression != nullptr && ReadArray4Field(*OpObj, TEXT("vector_value"), VectorValue) && TrySetLinearColorProperty(Expression, *PropertyName, VectorValue))
                    {
                        ++OperationsApplied;
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("setexpressiontexture"))
                {
                    FString ExpressionKey;
                    FString TexturePath;
                    (*OpObj)->TryGetStringField(TEXT("expression_name"), ExpressionKey);
                    (*OpObj)->TryGetStringField(TEXT("texture_path"), TexturePath);
                    UMaterialExpression* Expression = ResolveMaterialExpressionByKey(Material, ExpressionLookup, ExpressionKey);
                    UObject* TextureObj = ResolveAssetObject(TexturePath);
                    if (Expression != nullptr && TextureObj != nullptr && TrySetObjectProperty(Expression, TEXT("Texture"), TextureObj))
                    {
                        ++OperationsApplied;
                    }
                    continue;
                }
            }
        }

        Material->PostEditChange();
        Material->MarkPackageDirty();
    }
    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetBoolField(TEXT("dry_run"), Request.bDryRun);
    Out->SetStringField(TEXT("material_path"), MaterialPath);
    Out->SetBoolField(TEXT("two_sided"), bTwoSided);
    Out->SetNumberField(TEXT("blend_mode"), BlendMode);
    Out->SetNumberField(TEXT("shading_model"), ShadingModel);
    Out->SetNumberField(TEXT("requested_operations"), RequestedOps);
    Out->SetNumberField(TEXT("operations_applied"), OperationsApplied);
    Out->SetNumberField(TEXT("expressions_created"), ExpressionsCreated);
    Out->SetNumberField(TEXT("expressions_removed"), ExpressionsRemoved);
    Out->SetNumberField(TEXT("connections_applied"), ConnectionsApplied);
    return {true, TEXT("Material asset edited."), SerializePayload(Out), TEXT("OK")};
}

static FAgentActionResult HandleEditNiagaraSystemGraph(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString NiagaraPath;
    int32 RandomSeed = 0;
    const TArray<TSharedPtr<FJsonValue>>* OperationsArray = nullptr;
    bool bDeterminism = false;
    bool bHasDeterminism = false;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("niagara_system_path"), NiagaraPath);
        if (NiagaraPath.IsEmpty())
        {
            Payload->TryGetStringField(TEXT("asset_path"), NiagaraPath);
        }
        RandomSeed = ReadIntOrDefault(Payload, TEXT("deterministic_seed"), 0);
        Payload->TryGetArrayField(TEXT("operations"), OperationsArray);
        bHasDeterminism = Payload->TryGetBoolField(TEXT("determinism"), bDeterminism);
    }
    if (NiagaraPath.IsEmpty())
    {
        return {false, TEXT("edit_niagara_system_graph requires niagara_system_path or asset_path."), TEXT(""), TEXT("MISSING_FIELD")};
    }
    UObject* NiagaraObj = ResolveAssetObject(NiagaraPath);
    if (NiagaraObj == nullptr)
    {
        return {false, FString::Printf(TEXT("Niagara system not found: %s"), *NiagaraPath), TEXT(""), TEXT("ASSET_NOT_FOUND")};
    }
    UNiagaraSystem* NiagaraSystem = Cast<UNiagaraSystem>(NiagaraObj);
    if (NiagaraSystem == nullptr)
    {
        return {false, TEXT("Resolved asset is not a UNiagaraSystem."), TEXT(""), TEXT("INVALID_ASSET_TYPE")};
    }

    const int32 RequestedOps = (OperationsArray && OperationsArray->Num() > 0) ? OperationsArray->Num() : 0;
    int32 AppliedOps = 0;
    int32 AddedEmitters = 0;
    int32 RemovedEmitters = 0;
    int32 RenamedEmitters = 0;
    int32 ToggledEmitters = 0;
    int32 EmitterSettingsUpdated = 0;
    int32 UserParametersAdded = 0;
    int32 UserParametersRemoved = 0;
    int32 UserParametersRenamed = 0;
    int32 UserParametersUpdated = 0;
    int32 PlaybackRangeUpdates = 0;
    if (!Request.bDryRun)
    {
        NiagaraSystem->Modify();
        TrySetIntProperty(NiagaraSystem, TEXT("RandomSeed"), static_cast<int64>(RandomSeed));
        TrySetIntProperty(NiagaraSystem, TEXT("RandomSeedOffset"), static_cast<int64>(RandomSeed));
        if (bHasDeterminism)
        {
            TrySetBoolProperty(NiagaraSystem, TEXT("bDeterminism"), bDeterminism);
        }

        auto FindHandleByName = [&](const FString& HandleName) -> FNiagaraEmitterHandle*
        {
            const FString NormalizedName = NormalizeLookupKey(HandleName);
            if (NormalizedName.IsEmpty())
            {
                return nullptr;
            }
            for (FNiagaraEmitterHandle& Handle : NiagaraSystem->GetEmitterHandles())
            {
                if (NormalizeLookupKey(Handle.GetName().ToString()) == NormalizedName)
                {
                    return &Handle;
                }
            }
            return nullptr;
        };
        FNiagaraUserRedirectionParameterStore& UserStore = NiagaraSystem->GetExposedParameters();
        auto FindUserParameterByName = [&](const FString& ParameterName, FNiagaraVariable& OutVariable) -> bool
        {
            const FString NormalizedName = NormalizeNiagaraUserParameterKey(ParameterName);
            if (NormalizedName.IsEmpty())
            {
                return false;
            }
            TArray<FNiagaraVariable> UserParameters;
            UserStore.GetUserParameters(UserParameters);
            for (const FNiagaraVariable& Candidate : UserParameters)
            {
                if (NormalizeNiagaraUserParameterKey(Candidate.GetName().ToString()) == NormalizedName)
                {
                    OutVariable = Candidate;
                    return true;
                }
            }
            return false;
        };
        UNiagaraSystemEditorData* NiagaraEditorData = Cast<UNiagaraSystemEditorData>(NiagaraSystem->GetEditorData());

        if (OperationsArray != nullptr)
        {
            for (const TSharedPtr<FJsonValue>& Value : *OperationsArray)
            {
                const TSharedPtr<FJsonObject>* OpObj = nullptr;
                if (!Value.IsValid() || !Value->TryGetObject(OpObj) || OpObj == nullptr || !OpObj->IsValid())
                {
                    continue;
                }
                FString OpName;
                (*OpObj)->TryGetStringField(TEXT("op"), OpName);
                if (OpName.IsEmpty())
                {
                    (*OpObj)->TryGetStringField(TEXT("operation"), OpName);
                }
                const FString NormalizedOp = NormalizeLookupKey(OpName);
                if (NormalizedOp.IsEmpty())
                {
                    continue;
                }
                if (NormalizedOp == TEXT("addemitterhandle"))
                {
                    FString EmitterPath;
                    FString EmitterName = TEXT("Emitter");
                    FString VersionString;
                    (*OpObj)->TryGetStringField(TEXT("emitter_asset_path"), EmitterPath);
                    (*OpObj)->TryGetStringField(TEXT("emitter_name"), EmitterName);
                    (*OpObj)->TryGetStringField(TEXT("emitter_version"), VersionString);
                    UNiagaraEmitter* EmitterAsset = Cast<UNiagaraEmitter>(ResolveAssetObject(EmitterPath));
                    if (EmitterAsset != nullptr)
                    {
                        FGuid VersionGuid;
                        if (!FGuid::Parse(VersionString, VersionGuid))
                        {
                            VersionGuid = EmitterAsset->GetExposedVersion().VersionGuid;
                        }
                        const FNiagaraEmitterHandle NewHandle = NiagaraSystem->AddEmitterHandle(*EmitterAsset, *EmitterName, VersionGuid);
                        if (NewHandle.IsValid())
                        {
                            ++AddedEmitters;
                            ++AppliedOps;
                        }
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("removeemitterhandle"))
                {
                    FString EmitterName;
                    (*OpObj)->TryGetStringField(TEXT("emitter_name"), EmitterName);
                    const FString NormalizedName = NormalizeLookupKey(EmitterName);
                    TArray<FNiagaraEmitterHandle> HandlesToRemove;
                    for (const FNiagaraEmitterHandle& Handle : NiagaraSystem->GetEmitterHandles())
                    {
                        if (NormalizeLookupKey(Handle.GetName().ToString()) == NormalizedName)
                        {
                            HandlesToRemove.Add(Handle);
                        }
                    }
                    for (const FNiagaraEmitterHandle& Handle : HandlesToRemove)
                    {
                        NiagaraSystem->RemoveEmitterHandle(Handle);
                        ++RemovedEmitters;
                        ++AppliedOps;
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("renameemitterhandle"))
                {
                    FString CurrentName;
                    FString NewName;
                    (*OpObj)->TryGetStringField(TEXT("current_name"), CurrentName);
                    (*OpObj)->TryGetStringField(TEXT("new_name"), NewName);
                    if (FNiagaraEmitterHandle* Handle = FindHandleByName(CurrentName))
                    {
                        Handle->SetName(*NewName, *NiagaraSystem);
                        ++RenamedEmitters;
                        ++AppliedOps;
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("setemitterenabled"))
                {
                    FString EmitterName;
                    bool bEnabled = true;
                    (*OpObj)->TryGetStringField(TEXT("emitter_name"), EmitterName);
                    (*OpObj)->TryGetBoolField(TEXT("enabled"), bEnabled);
                    if (FNiagaraEmitterHandle* Handle = FindHandleByName(EmitterName))
                    {
                        Handle->SetIsEnabled(bEnabled, *NiagaraSystem, true);
                        ++ToggledEmitters;
                        ++AppliedOps;
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("setemitterlocalspace"))
                {
                    FString EmitterName;
                    bool bLocalSpace = false;
                    (*OpObj)->TryGetStringField(TEXT("emitter_name"), EmitterName);
                    (*OpObj)->TryGetBoolField(TEXT("local_space"), bLocalSpace);
                    if (FNiagaraEmitterHandle* Handle = FindHandleByName(EmitterName))
                    {
                        if (FVersionedNiagaraEmitterData* EmitterData = Handle->GetEmitterData())
                        {
                            EmitterData->bLocalSpace = bLocalSpace;
                            ++EmitterSettingsUpdated;
                            ++AppliedOps;
                        }
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("setemitterdeterminism"))
                {
                    FString EmitterName;
                    bool bEmitterDeterminism = false;
                    bool bHasEmitterDeterminism = false;
                    int32 EmitterSeed = 0;
                    bool bHasEmitterSeed = false;
                    (*OpObj)->TryGetStringField(TEXT("emitter_name"), EmitterName);
                    bHasEmitterDeterminism = (*OpObj)->TryGetBoolField(TEXT("determinism"), bEmitterDeterminism);
                    if (!bHasEmitterDeterminism)
                    {
                        bHasEmitterDeterminism = (*OpObj)->TryGetBoolField(TEXT("enabled"), bEmitterDeterminism);
                    }
                    double SeedNumber = 0.0;
                    if ((*OpObj)->TryGetNumberField(TEXT("random_seed"), SeedNumber))
                    {
                        EmitterSeed = static_cast<int32>(SeedNumber);
                        bHasEmitterSeed = true;
                    }
                    else if ((*OpObj)->TryGetNumberField(TEXT("deterministic_seed"), SeedNumber))
                    {
                        EmitterSeed = static_cast<int32>(SeedNumber);
                        bHasEmitterSeed = true;
                    }
                    if (FNiagaraEmitterHandle* Handle = FindHandleByName(EmitterName))
                    {
                        if (FVersionedNiagaraEmitterData* EmitterData = Handle->GetEmitterData())
                        {
                            bool bChanged = false;
                            if (bHasEmitterDeterminism)
                            {
                                EmitterData->bDeterminism = bEmitterDeterminism;
                                bChanged = true;
                            }
                            if (bHasEmitterSeed)
                            {
                                EmitterData->RandomSeed = EmitterSeed;
                                bChanged = true;
                            }
                            if (bChanged)
                            {
                                ++EmitterSettingsUpdated;
                                ++AppliedOps;
                            }
                        }
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("setemittersimtarget"))
                {
                    FString EmitterName;
                    FString SimTargetString;
                    bool bHasSimTarget = false;
                    ENiagaraSimTarget SimTarget = ENiagaraSimTarget::CPUSim;
                    (*OpObj)->TryGetStringField(TEXT("emitter_name"), EmitterName);
                    if ((*OpObj)->TryGetStringField(TEXT("sim_target"), SimTargetString))
                    {
                        const FString SimKey = NormalizeLookupKey(SimTargetString);
                        if (SimKey == TEXT("gpu") || SimKey == TEXT("gpucomputesim") || SimKey == TEXT("gpucompute"))
                        {
                            SimTarget = ENiagaraSimTarget::GPUComputeSim;
                            bHasSimTarget = true;
                        }
                        else if (SimKey == TEXT("cpu") || SimKey == TEXT("cpusim"))
                        {
                            SimTarget = ENiagaraSimTarget::CPUSim;
                            bHasSimTarget = true;
                        }
                    }
                    if (!bHasSimTarget)
                    {
                        double SimTargetNumeric = 0.0;
                        if ((*OpObj)->TryGetNumberField(TEXT("sim_target_value"), SimTargetNumeric))
                        {
                            SimTarget = static_cast<ENiagaraSimTarget>(static_cast<int32>(SimTargetNumeric));
                            bHasSimTarget = true;
                        }
                    }
                    if (bHasSimTarget)
                    {
                        if (FNiagaraEmitterHandle* Handle = FindHandleByName(EmitterName))
                        {
                            if (FVersionedNiagaraEmitterData* EmitterData = Handle->GetEmitterData())
                            {
                                EmitterData->SimTarget = SimTarget;
                                ++EmitterSettingsUpdated;
                                ++AppliedOps;
                            }
                        }
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("setemitterbounds"))
                {
                    FString EmitterName;
                    FString BoundsMode;
                    bool bHasMode = false;
                    ENiagaraEmitterCalculateBoundMode Mode = ENiagaraEmitterCalculateBoundMode::Dynamic;
                    bool bHasBounds = false;
                    FBox FixedBounds(EForceInit::ForceInitToZero);
                    (*OpObj)->TryGetStringField(TEXT("emitter_name"), EmitterName);
                    if ((*OpObj)->TryGetStringField(TEXT("bounds_mode"), BoundsMode))
                    {
                        const FString BoundsKey = NormalizeLookupKey(BoundsMode);
                        if (BoundsKey == TEXT("dynamic"))
                        {
                            Mode = ENiagaraEmitterCalculateBoundMode::Dynamic;
                            bHasMode = true;
                        }
                        else if (BoundsKey == TEXT("fixed"))
                        {
                            Mode = ENiagaraEmitterCalculateBoundMode::Fixed;
                            bHasMode = true;
                        }
                        else if (BoundsKey == TEXT("programmable"))
                        {
                            Mode = ENiagaraEmitterCalculateBoundMode::Programmable;
                            bHasMode = true;
                        }
                    }
                    if (!bHasMode)
                    {
                        double ModeNumeric = 0.0;
                        if ((*OpObj)->TryGetNumberField(TEXT("bounds_mode_value"), ModeNumeric))
                        {
                            Mode = static_cast<ENiagaraEmitterCalculateBoundMode>(static_cast<int32>(ModeNumeric));
                            bHasMode = true;
                        }
                    }
                    const TArray<TSharedPtr<FJsonValue>>* FixedBoundsArray = nullptr;
                    if ((*OpObj)->TryGetArrayField(TEXT("fixed_bounds"), FixedBoundsArray) && FixedBoundsArray != nullptr && FixedBoundsArray->Num() == 6)
                    {
                        double MinX = 0.0;
                        double MinY = 0.0;
                        double MinZ = 0.0;
                        double MaxX = 0.0;
                        double MaxY = 0.0;
                        double MaxZ = 0.0;
                        if ((*FixedBoundsArray)[0].IsValid() && (*FixedBoundsArray)[1].IsValid() && (*FixedBoundsArray)[2].IsValid()
                            && (*FixedBoundsArray)[3].IsValid() && (*FixedBoundsArray)[4].IsValid() && (*FixedBoundsArray)[5].IsValid()
                            && (*FixedBoundsArray)[0]->TryGetNumber(MinX) && (*FixedBoundsArray)[1]->TryGetNumber(MinY) && (*FixedBoundsArray)[2]->TryGetNumber(MinZ)
                            && (*FixedBoundsArray)[3]->TryGetNumber(MaxX) && (*FixedBoundsArray)[4]->TryGetNumber(MaxY) && (*FixedBoundsArray)[5]->TryGetNumber(MaxZ))
                        {
                            FixedBounds = FBox(
                                FVector(static_cast<float>(MinX), static_cast<float>(MinY), static_cast<float>(MinZ)),
                                FVector(static_cast<float>(MaxX), static_cast<float>(MaxY), static_cast<float>(MaxZ)));
                            bHasBounds = true;
                        }
                    }
                    if (!bHasBounds)
                    {
                        FVector BoundsMin = FVector::ZeroVector;
                        FVector BoundsMax = FVector::ZeroVector;
                        const TArray<TSharedPtr<FJsonValue>>* BoundsMinArray = nullptr;
                        const TArray<TSharedPtr<FJsonValue>>* BoundsMaxArray = nullptr;
                        if ((*OpObj)->TryGetArrayField(TEXT("bounds_min"), BoundsMinArray)
                            && (*OpObj)->TryGetArrayField(TEXT("bounds_max"), BoundsMaxArray)
                            && BoundsMinArray != nullptr
                            && BoundsMaxArray != nullptr
                            && BoundsMinArray->Num() == 3
                            && BoundsMaxArray->Num() == 3)
                        {
                            double MinX = 0.0;
                            double MinY = 0.0;
                            double MinZ = 0.0;
                            double MaxX = 0.0;
                            double MaxY = 0.0;
                            double MaxZ = 0.0;
                            if ((*BoundsMinArray)[0].IsValid() && (*BoundsMinArray)[1].IsValid() && (*BoundsMinArray)[2].IsValid()
                                && (*BoundsMaxArray)[0].IsValid() && (*BoundsMaxArray)[1].IsValid() && (*BoundsMaxArray)[2].IsValid()
                                && (*BoundsMinArray)[0]->TryGetNumber(MinX) && (*BoundsMinArray)[1]->TryGetNumber(MinY) && (*BoundsMinArray)[2]->TryGetNumber(MinZ)
                                && (*BoundsMaxArray)[0]->TryGetNumber(MaxX) && (*BoundsMaxArray)[1]->TryGetNumber(MaxY) && (*BoundsMaxArray)[2]->TryGetNumber(MaxZ))
                            {
                                BoundsMin = FVector(static_cast<float>(MinX), static_cast<float>(MinY), static_cast<float>(MinZ));
                                BoundsMax = FVector(static_cast<float>(MaxX), static_cast<float>(MaxY), static_cast<float>(MaxZ));
                                FixedBounds = FBox(BoundsMin, BoundsMax);
                                bHasBounds = true;
                            }
                        }
                    }
                    if (FNiagaraEmitterHandle* Handle = FindHandleByName(EmitterName))
                    {
                        if (FVersionedNiagaraEmitterData* EmitterData = Handle->GetEmitterData())
                        {
                            bool bChanged = false;
                            if (bHasMode)
                            {
                                EmitterData->CalculateBoundsMode = Mode;
                                bChanged = true;
                            }
                            if (bHasBounds)
                            {
                                EmitterData->FixedBounds = FixedBounds;
                                bChanged = true;
                            }
                            if (bChanged)
                            {
                                ++EmitterSettingsUpdated;
                                ++AppliedOps;
                            }
                        }
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("setsystemplaybackrange"))
                {
                    if (NiagaraEditorData != nullptr)
                    {
                        double Start = 0.0;
                        double End = 5.0;
                        if ((*OpObj)->TryGetNumberField(TEXT("playback_start"), Start)
                            && (*OpObj)->TryGetNumberField(TEXT("playback_end"), End))
                        {
                            NiagaraEditorData->Modify();
                            NiagaraEditorData->SetPlaybackRange(TRange<float>(static_cast<float>(Start), static_cast<float>(End)));
                            ++PlaybackRangeUpdates;
                            ++AppliedOps;
                        }
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("adduserparameter"))
                {
                    FString ParameterName;
                    FString TypeName = TEXT("float");
                    bool bInitialize = true;
                    (*OpObj)->TryGetStringField(TEXT("parameter_name"), ParameterName);
                    (*OpObj)->TryGetStringField(TEXT("parameter_type"), TypeName);
                    (*OpObj)->TryGetBoolField(TEXT("initialize"), bInitialize);
                    FNiagaraTypeDefinition TypeDef;
                    if (!ParameterName.IsEmpty() && ResolveNiagaraUserParameterType(TypeName, TypeDef))
                    {
                        FNiagaraVariable UserVariable(TypeDef, *ParameterName);
                        FNiagaraUserRedirectionParameterStore::MakeUserVariable(UserVariable);
                        const bool bAdded = UserStore.AddParameter(UserVariable, bInitialize, true);
                        if (bAdded)
                        {
                            if (NiagaraEditorData != nullptr)
                            {
                                NiagaraEditorData->FindOrAddUserScriptVariable(UserVariable, *NiagaraSystem);
                            }
                            ++UserParametersAdded;
                            ++AppliedOps;
                        }
                        if (TrySetNiagaraUserParameterFromOperation(UserStore, UserVariable, *OpObj))
                        {
                            ++UserParametersUpdated;
                        }
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("removeuserparameter"))
                {
                    FString ParameterName;
                    (*OpObj)->TryGetStringField(TEXT("parameter_name"), ParameterName);
                    FNiagaraVariable ExistingVariable;
                    if (FindUserParameterByName(ParameterName, ExistingVariable))
                    {
                        if (UserStore.RemoveParameter(ExistingVariable))
                        {
                            if (NiagaraEditorData != nullptr)
                            {
                                NiagaraEditorData->RemoveUserScriptVariable(ExistingVariable);
                            }
                            ++UserParametersRemoved;
                            ++AppliedOps;
                        }
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("renameuserparameter"))
                {
                    FString CurrentName;
                    FString NewName;
                    (*OpObj)->TryGetStringField(TEXT("current_name"), CurrentName);
                    (*OpObj)->TryGetStringField(TEXT("new_name"), NewName);
                    if (!NewName.IsEmpty())
                    {
                        FNiagaraVariable ExistingVariable;
                        if (FindUserParameterByName(CurrentName, ExistingVariable))
                        {
                            UserStore.RenameParameter(ExistingVariable, *NewName);
                            if (NiagaraEditorData != nullptr)
                            {
                                NiagaraEditorData->RenameUserScriptVariable(ExistingVariable, *NewName);
                            }
                            ++UserParametersRenamed;
                            ++AppliedOps;
                        }
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("setuserparametervalue"))
                {
                    FString ParameterName;
                    FString ParameterType = TEXT("float");
                    bool bAllowCreate = false;
                    (*OpObj)->TryGetStringField(TEXT("parameter_name"), ParameterName);
                    (*OpObj)->TryGetStringField(TEXT("parameter_type"), ParameterType);
                    (*OpObj)->TryGetBoolField(TEXT("allow_create"), bAllowCreate);
                    FNiagaraVariable ExistingVariable;
                    bool bHasVariable = FindUserParameterByName(ParameterName, ExistingVariable);
                    if (!bHasVariable && bAllowCreate)
                    {
                        FNiagaraTypeDefinition CreateType;
                        if (ResolveNiagaraUserParameterType(ParameterType, CreateType))
                        {
                            ExistingVariable = FNiagaraVariable(CreateType, *ParameterName);
                            FNiagaraUserRedirectionParameterStore::MakeUserVariable(ExistingVariable);
                            bHasVariable = UserStore.AddParameter(ExistingVariable, true, true);
                            if (bHasVariable)
                            {
                                if (NiagaraEditorData != nullptr)
                                {
                                    NiagaraEditorData->FindOrAddUserScriptVariable(ExistingVariable, *NiagaraSystem);
                                }
                                ++UserParametersAdded;
                                ++AppliedOps;
                            }
                        }
                    }
                    if (bHasVariable && TrySetNiagaraUserParameterFromOperation(UserStore, ExistingVariable, *OpObj))
                    {
                        ++UserParametersUpdated;
                        ++AppliedOps;
                    }
                    continue;
                }
            }
        }
        NiagaraSystem->PostEditChange();
        NiagaraSystem->MarkPackageDirty();
    }
    TArray<FNiagaraVariable> UserParameters;
    NiagaraSystem->GetExposedParameters().GetUserParameters(UserParameters);
    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetBoolField(TEXT("dry_run"), Request.bDryRun);
    Out->SetStringField(TEXT("niagara_system_path"), NiagaraPath);
    Out->SetNumberField(TEXT("deterministic_seed"), RandomSeed);
    Out->SetNumberField(TEXT("requested_operations"), RequestedOps);
    Out->SetNumberField(TEXT("operations_applied"), AppliedOps);
    Out->SetNumberField(TEXT("emitters_added"), AddedEmitters);
    Out->SetNumberField(TEXT("emitters_removed"), RemovedEmitters);
    Out->SetNumberField(TEXT("emitters_renamed"), RenamedEmitters);
    Out->SetNumberField(TEXT("emitters_toggled"), ToggledEmitters);
    Out->SetNumberField(TEXT("emitter_settings_updated"), EmitterSettingsUpdated);
    Out->SetNumberField(TEXT("user_parameters_added"), UserParametersAdded);
    Out->SetNumberField(TEXT("user_parameters_removed"), UserParametersRemoved);
    Out->SetNumberField(TEXT("user_parameters_renamed"), UserParametersRenamed);
    Out->SetNumberField(TEXT("user_parameters_updated"), UserParametersUpdated);
    Out->SetNumberField(TEXT("playback_range_updates"), PlaybackRangeUpdates);
    Out->SetNumberField(TEXT("user_parameter_count"), UserParameters.Num());
    Out->SetNumberField(TEXT("emitter_count"), NiagaraSystem->GetEmitterHandles().Num());
    return {true, TEXT("Niagara system edited."), SerializePayload(Out), TEXT("OK")};
}

static FAgentActionResult HandleEditLevelSequenceAsset(const FAgentActionRequest& Request, const TSharedPtr<FJsonObject>& Payload)
{
    FString SequencePath;
    int32 PlaybackStart = 0;
    int32 PlaybackEnd = 300;
    const TArray<TSharedPtr<FJsonValue>>* OperationsArray = nullptr;
    if (Payload.IsValid())
    {
        Payload->TryGetStringField(TEXT("level_sequence_path"), SequencePath);
        if (SequencePath.IsEmpty())
        {
            Payload->TryGetStringField(TEXT("asset_path"), SequencePath);
        }
        PlaybackStart = ReadIntOrDefault(Payload, TEXT("playback_start"), 0);
        PlaybackEnd = ReadIntOrDefault(Payload, TEXT("playback_end"), 300);
        Payload->TryGetArrayField(TEXT("operations"), OperationsArray);
    }
    if (SequencePath.IsEmpty())
    {
        return {false, TEXT("edit_level_sequence_asset requires level_sequence_path or asset_path."), TEXT(""), TEXT("MISSING_FIELD")};
    }
    UObject* SequenceObj = ResolveAssetObject(SequencePath);
    if (SequenceObj == nullptr)
    {
        return {false, FString::Printf(TEXT("Level sequence not found: %s"), *SequencePath), TEXT(""), TEXT("ASSET_NOT_FOUND")};
    }
    ULevelSequence* LevelSequence = Cast<ULevelSequence>(SequenceObj);
    if (LevelSequence == nullptr)
    {
        return {false, TEXT("Resolved asset is not a ULevelSequence."), TEXT(""), TEXT("INVALID_ASSET_TYPE")};
    }
    UMovieScene* MovieScene = LevelSequence->GetMovieScene();
    if (MovieScene == nullptr)
    {
        return {false, TEXT("Level sequence has no MovieScene."), TEXT(""), TEXT("INVALID_ASSET_STATE")};
    }

    const int32 RequestedOps = (OperationsArray && OperationsArray->Num() > 0) ? OperationsArray->Num() : 0;
    int32 AppliedOps = 0;
    int32 TracksEnsured = 0;
    int32 KeysAdded = 0;
    if (!Request.bDryRun)
    {
        LevelSequence->Modify();
        MovieScene->Modify();

        const int32 PlaybackDuration = FMath::Max(1, PlaybackEnd - PlaybackStart);
        MovieScene->SetPlaybackRange(FFrameNumber(PlaybackStart), PlaybackDuration, true);

        if (OperationsArray != nullptr)
        {
            for (const TSharedPtr<FJsonValue>& Value : *OperationsArray)
            {
                const TSharedPtr<FJsonObject>* OpObj = nullptr;
                if (!Value.IsValid() || !Value->TryGetObject(OpObj) || OpObj == nullptr || !OpObj->IsValid())
                {
                    continue;
                }
                FString OpName;
                (*OpObj)->TryGetStringField(TEXT("op"), OpName);
                if (OpName.IsEmpty())
                {
                    (*OpObj)->TryGetStringField(TEXT("operation"), OpName);
                }
                const FString NormalizedOp = NormalizeLookupKey(OpName);
                if (NormalizedOp.IsEmpty())
                {
                    continue;
                }
                if (NormalizedOp == TEXT("setplaybackrange"))
                {
                    const int32 OpStart = ReadIntOrDefault(*OpObj, TEXT("playback_start"), PlaybackStart);
                    const int32 OpEnd = ReadIntOrDefault(*OpObj, TEXT("playback_end"), PlaybackEnd);
                    const int32 OpDuration = FMath::Max(1, OpEnd - OpStart);
                    MovieScene->SetPlaybackRange(FFrameNumber(OpStart), OpDuration, true);
                    ++AppliedOps;
                    continue;
                }
                if (NormalizedOp == TEXT("ensurefloattrack"))
                {
                    FString TrackName;
                    FString PropertyName;
                    FString PropertyPath;
                    (*OpObj)->TryGetStringField(TEXT("track_name"), TrackName);
                    (*OpObj)->TryGetStringField(TEXT("property_name"), PropertyName);
                    (*OpObj)->TryGetStringField(TEXT("property_path"), PropertyPath);
                    UMovieSceneFloatTrack* Track = EnsureFloatTrack(MovieScene, TrackName, PropertyName, PropertyPath);
                    if (Track != nullptr)
                    {
                        ++TracksEnsured;
                        ++AppliedOps;
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("addfloatkey"))
                {
                    FString TrackName;
                    FString PropertyName;
                    FString PropertyPath;
                    FString Interp = TEXT("linear");
                    const int32 SectionIndex = ReadIntOrDefault(*OpObj, TEXT("section_index"), 0);
                    const int32 Frame = ReadIntOrDefault(*OpObj, TEXT("frame"), 0);
                    const float KeyValue = ReadFloatOrDefault(*OpObj, TEXT("value"), 0.0f);
                    (*OpObj)->TryGetStringField(TEXT("track_name"), TrackName);
                    (*OpObj)->TryGetStringField(TEXT("property_name"), PropertyName);
                    (*OpObj)->TryGetStringField(TEXT("property_path"), PropertyPath);
                    (*OpObj)->TryGetStringField(TEXT("interp"), Interp);

                    UMovieSceneFloatTrack* Track = EnsureFloatTrack(MovieScene, TrackName, PropertyName, PropertyPath);
                    UMovieSceneFloatSection* Section = EnsureFloatSection(Track, SectionIndex);
                    if (Section != nullptr)
                    {
                        const FFrameNumber KeyFrame(Frame);
                        Section->SetRange(TRange<FFrameNumber>::Hull(Section->GetRange(), TRange<FFrameNumber>::Inclusive(KeyFrame, KeyFrame)));
                        const FString InterpKey = NormalizeLookupKey(Interp);
                        FMovieSceneFloatChannel& Channel = Section->GetChannel();
                        if (InterpKey == TEXT("constant"))
                        {
                            Channel.AddConstantKey(KeyFrame, KeyValue);
                        }
                        else if (InterpKey == TEXT("cubic"))
                        {
                            Channel.AddCubicKey(KeyFrame, KeyValue, ERichCurveTangentMode::RCTM_Auto);
                        }
                        else
                        {
                            Channel.AddLinearKey(KeyFrame, KeyValue);
                        }
                        ++KeysAdded;
                        ++AppliedOps;
                    }
                    continue;
                }
                if (NormalizedOp == TEXT("setfloatdefault"))
                {
                    FString TrackName;
                    FString PropertyName;
                    FString PropertyPath;
                    const int32 SectionIndex = ReadIntOrDefault(*OpObj, TEXT("section_index"), 0);
                    const float DefaultValue = ReadFloatOrDefault(*OpObj, TEXT("value"), 0.0f);
                    (*OpObj)->TryGetStringField(TEXT("track_name"), TrackName);
                    (*OpObj)->TryGetStringField(TEXT("property_name"), PropertyName);
                    (*OpObj)->TryGetStringField(TEXT("property_path"), PropertyPath);
                    UMovieSceneFloatTrack* Track = EnsureFloatTrack(MovieScene, TrackName, PropertyName, PropertyPath);
                    UMovieSceneFloatSection* Section = EnsureFloatSection(Track, SectionIndex);
                    if (Section != nullptr)
                    {
                        Section->GetChannel().SetDefault(DefaultValue);
                        ++AppliedOps;
                    }
                    continue;
                }
            }
        }
        LevelSequence->MarkPackageDirty();
    }
    TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
    Out->SetBoolField(TEXT("dry_run"), Request.bDryRun);
    Out->SetStringField(TEXT("level_sequence_path"), SequencePath);
    Out->SetNumberField(TEXT("playback_start"), PlaybackStart);
    Out->SetNumberField(TEXT("playback_end"), PlaybackEnd);
    Out->SetNumberField(TEXT("requested_operations"), RequestedOps);
    Out->SetNumberField(TEXT("operations_applied"), AppliedOps);
    Out->SetNumberField(TEXT("tracks_ensured"), TracksEnsured);
    Out->SetNumberField(TEXT("keys_added"), KeysAdded);
    return {true, TEXT("Level sequence edited."), SerializePayload(Out), TEXT("OK")};
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
    if (Name == TEXT("generate_widget_template"))
    {
        return UnrealAgentPrivate::HandleGenerateWidgetTemplate(Request, Payload);
    }
    if (Name == TEXT("analyze_widget_tree"))
    {
        return UnrealAgentPrivate::HandleAnalyzeWidgetTree(Request, Payload);
    }
    if (Name == TEXT("set_reflected_property"))
    {
        return UnrealAgentPrivate::HandleSetReflectedProperty(Request, Payload);
    }
    if (Name == TEXT("create_blueprint_function"))
    {
        return UnrealAgentPrivate::HandleCreateBlueprintFunction(Request, Payload);
    }
    if (Name == TEXT("create_blueprint_macro"))
    {
        return UnrealAgentPrivate::HandleCreateBlueprintMacro(Request, Payload);
    }
    if (Name == TEXT("wire_blueprint_pins"))
    {
        return UnrealAgentPrivate::HandleWireBlueprintPins(Request, Payload);
    }
    if (Name == TEXT("blueprint_node_authoring"))
    {
        return UnrealAgentPrivate::HandleBlueprintNodeAuthoring(Request, Payload);
    }
    if (Name == TEXT("blueprint_compile_diagnostics"))
    {
        return UnrealAgentPrivate::HandleBlueprintCompileDiagnostics(Request, Payload);
    }
    if (Name == TEXT("modify_blueprint_components"))
    {
        return UnrealAgentPrivate::HandleModifyBlueprintComponents(Request, Payload);
    }
    if (Name == TEXT("edit_actor_transform"))
    {
        return UnrealAgentPrivate::HandleEditActorTransform(Request, Payload);
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
    if (Name == TEXT("generate_layout_from_template"))
    {
        return UnrealAgentPrivate::HandleGenerateLayoutFromTemplate(Request, Payload);
    }
    if (Name == TEXT("scatter_assets_with_constraints"))
    {
        return UnrealAgentPrivate::HandleScatterAssetsWithConstraints(Request, Payload);
    }
    if (Name == TEXT("clear_generated_layout_by_token"))
    {
        return UnrealAgentPrivate::HandleClearGeneratedLayoutByToken(Request, Payload);
    }
    if (Name == TEXT("list_asset_dependencies"))
    {
        return UnrealAgentPrivate::HandleListAssetDependencies(Request, Payload);
    }
    if (Name == TEXT("list_asset_referencers"))
    {
        return UnrealAgentPrivate::HandleListAssetReferencers(Request, Payload);
    }
    if (Name == TEXT("analyze_asset_impact"))
    {
        return UnrealAgentPrivate::HandleAnalyzeAssetImpact(Request, Payload);
    }
    if (Name == TEXT("analyze_project_hotspots"))
    {
        return UnrealAgentPrivate::HandleAnalyzeProjectHotspots(Request, Payload);
    }
    if (Name == TEXT("create_data_asset"))
    {
        return UnrealAgentPrivate::HandleCreateDataAsset(Request, Payload);
    }
    if (Name == TEXT("create_behavior_tree_asset"))
    {
        return UnrealAgentPrivate::HandleCreateBehaviorTreeAsset(Request, Payload);
    }
    if (Name == TEXT("edit_behavior_tree_asset"))
    {
        return UnrealAgentPrivate::HandleEditBehaviorTreeAsset(Request, Payload);
    }
    if (Name == TEXT("create_blackboard_data_asset"))
    {
        return UnrealAgentPrivate::HandleCreateBlackboardDataAsset(Request, Payload);
    }
    if (Name == TEXT("edit_blackboard_data_asset"))
    {
        return UnrealAgentPrivate::HandleEditBlackboardDataAsset(Request, Payload);
    }
    if (Name == TEXT("create_eqs_query_asset"))
    {
        return UnrealAgentPrivate::HandleCreateEQSQueryAsset(Request, Payload);
    }
    if (Name == TEXT("edit_eqs_query_asset"))
    {
        return UnrealAgentPrivate::HandleEditEQSQueryAsset(Request, Payload);
    }
    if (Name == TEXT("create_anim_blueprint_asset"))
    {
        return UnrealAgentPrivate::HandleCreateAnimBlueprintAsset(Request, Payload);
    }
    if (Name == TEXT("edit_anim_blueprint_state_machine"))
    {
        return UnrealAgentPrivate::HandleEditAnimBlueprintStateMachine(Request, Payload);
    }
    if (Name == TEXT("create_material_asset"))
    {
        return UnrealAgentPrivate::HandleCreateMaterialAsset(Request, Payload);
    }
    if (Name == TEXT("edit_material_asset"))
    {
        return UnrealAgentPrivate::HandleEditMaterialAsset(Request, Payload);
    }
    if (Name == TEXT("create_niagara_system_asset"))
    {
        return UnrealAgentPrivate::HandleCreateNiagaraSystemAsset(Request, Payload);
    }
    if (Name == TEXT("edit_niagara_system_graph"))
    {
        return UnrealAgentPrivate::HandleEditNiagaraSystemGraph(Request, Payload);
    }
    if (Name == TEXT("create_level_sequence_asset"))
    {
        return UnrealAgentPrivate::HandleCreateLevelSequenceAsset(Request, Payload);
    }
    if (Name == TEXT("edit_level_sequence_asset"))
    {
        return UnrealAgentPrivate::HandleEditLevelSequenceAsset(Request, Payload);
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
