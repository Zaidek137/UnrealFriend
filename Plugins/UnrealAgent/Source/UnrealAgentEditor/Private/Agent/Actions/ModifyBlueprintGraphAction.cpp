#include "Agent/Actions/ModifyBlueprintGraphAction.h"

#include "Agent/AgentJsonUtils.h"
#include "Dom/JsonObject.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraphSchema_K2.h"
#include "EdGraphSchema_K2_Actions.h"
#include "Engine/Blueprint.h"
#include "GameFramework/Actor.h"
#include "K2Node_CallFunction.h"
#include "K2Node_Event.h"
#include "K2Node_IfThenElse.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Misc/PackageName.h"
#include "ScopedTransaction.h"

namespace UnrealAgentPrivate
{
static FString NormalizeBlueprintObjectPath(const FString& BlueprintPathOrObjectPath)
{
    if (BlueprintPathOrObjectPath.Contains(TEXT(".")))
    {
        return BlueprintPathOrObjectPath;
    }

    if (!BlueprintPathOrObjectPath.StartsWith(TEXT("/")))
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

static bool ReadVector2Field(const TSharedPtr<FJsonObject>& JsonObject, const FString& FieldName, FVector2D& OutVector)
{
    const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
    if (!JsonObject->TryGetArrayField(FieldName, Values) || Values == nullptr || Values->Num() != 2)
    {
        return false;
    }

    double X = 0.0;
    double Y = 0.0;
    if (!(*Values)[0].IsValid() || !(*Values)[1].IsValid())
    {
        return false;
    }

    if (!(*Values)[0]->TryGetNumber(X) || !(*Values)[1]->TryGetNumber(Y))
    {
        return false;
    }

    OutVector = FVector2D(static_cast<float>(X), static_cast<float>(Y));
    return true;
}

static UEdGraph* ResolveEventGraph(UBlueprint* Blueprint)
{
    if (Blueprint == nullptr)
    {
        return nullptr;
    }

    for (UEdGraph* Graph : Blueprint->UbergraphPages)
    {
        if (Graph != nullptr)
        {
            return Graph;
        }
    }

    return nullptr;
}

static UClass* ResolveClassPath(const FString& ClassPath)
{
    if (ClassPath.IsEmpty())
    {
        return nullptr;
    }

    UClass* ClassObject = FindObject<UClass>(nullptr, *ClassPath);
    if (ClassObject == nullptr)
    {
        ClassObject = LoadObject<UClass>(nullptr, *ClassPath);
    }
    return ClassObject;
}

static UK2Node_Event* FindBeginPlayNode(const UEdGraph* EventGraph)
{
    if (EventGraph == nullptr)
    {
        return nullptr;
    }

    for (UEdGraphNode* Node : EventGraph->Nodes)
    {
        UK2Node_Event* EventNode = Cast<UK2Node_Event>(Node);
        if (EventNode == nullptr)
        {
            continue;
        }

        if (EventNode->EventReference.GetMemberName() == FName(TEXT("ReceiveBeginPlay")))
        {
            return EventNode;
        }
    }

    return nullptr;
}

static UK2Node_Event* EnsureBeginPlayNode(
    UEdGraph* EventGraph,
    const FVector2D& Position,
    bool& bCreated
)
{
    bCreated = false;
    UK2Node_Event* BeginPlayNode = FindBeginPlayNode(EventGraph);
    if (BeginPlayNode != nullptr)
    {
        return BeginPlayNode;
    }

    BeginPlayNode = FEdGraphSchemaAction_K2NewNode::SpawnNode<UK2Node_Event>(
        EventGraph,
        Position,
        EK2NewNodeFlags::SelectNewNode,
        [](UK2Node_Event* NewNode)
        {
            NewNode->EventReference.SetExternalMember(
                FName(TEXT("ReceiveBeginPlay")),
                AActor::StaticClass()
            );
            NewNode->bOverrideFunction = true;
        }
    );
    bCreated = BeginPlayNode != nullptr;
    return BeginPlayNode;
}

static UFunction* ResolveFunction(const FString& ClassPath, const FString& FunctionName)
{
    UClass* OwnerClass = ResolveClassPath(ClassPath);
    if (OwnerClass == nullptr || FunctionName.IsEmpty())
    {
        return nullptr;
    }
    return OwnerClass->FindFunctionByName(FName(*FunctionName));
}

static UK2Node_CallFunction* FindCallFunctionNode(const UEdGraph* EventGraph, const UFunction* TargetFunction)
{
    if (EventGraph == nullptr || TargetFunction == nullptr)
    {
        return nullptr;
    }

    for (UEdGraphNode* Node : EventGraph->Nodes)
    {
        UK2Node_CallFunction* CallNode = Cast<UK2Node_CallFunction>(Node);
        if (CallNode == nullptr)
        {
            continue;
        }

        if (CallNode->GetTargetFunction() == TargetFunction)
        {
            return CallNode;
        }
    }

    return nullptr;
}

static TArray<UK2Node_CallFunction*> FindCallFunctionNodes(const UEdGraph* EventGraph, const UFunction* TargetFunction)
{
    TArray<UK2Node_CallFunction*> Nodes;
    if (EventGraph == nullptr || TargetFunction == nullptr)
    {
        return Nodes;
    }

    for (UEdGraphNode* Node : EventGraph->Nodes)
    {
        UK2Node_CallFunction* CallNode = Cast<UK2Node_CallFunction>(Node);
        if (CallNode == nullptr)
        {
            continue;
        }
        if (CallNode->GetTargetFunction() == TargetFunction)
        {
            Nodes.Add(CallNode);
        }
    }
    return Nodes;
}

static UK2Node_CallFunction* SpawnFunctionNode(
    UEdGraph* EventGraph,
    UFunction* TargetFunction,
    const FVector2D& NodePosition
)
{
    if (EventGraph == nullptr || TargetFunction == nullptr)
    {
        return nullptr;
    }

    return FEdGraphSchemaAction_K2NewNode::SpawnNode<UK2Node_CallFunction>(
        EventGraph,
        NodePosition,
        EK2NewNodeFlags::SelectNewNode,
        [TargetFunction](UK2Node_CallFunction* NewNode)
        {
            NewNode->SetFromFunction(TargetFunction);
        }
    );
}

static UEdGraphNode* FindNodeByName(const UEdGraph* EventGraph, const FString& NodeName)
{
    if (EventGraph == nullptr || NodeName.IsEmpty())
    {
        return nullptr;
    }

    for (UEdGraphNode* Node : EventGraph->Nodes)
    {
        if (Node != nullptr && Node->GetName().Equals(NodeName, ESearchCase::IgnoreCase))
        {
            return Node;
        }
    }
    return nullptr;
}

static bool StringContainsIgnoreCase(const FString& Source, const FString& Needle)
{
    return Needle.IsEmpty() || Source.Contains(Needle, ESearchCase::IgnoreCase, ESearchDir::FromStart);
}

static bool NodeMatchesGenericFilters(
    const UEdGraphNode* Node,
    const FString& NodeNameContains,
    const FString& NodeTitleContains,
    const FString& NodeClassPath,
    const FString& FunctionClassPath,
    const FString& FunctionName
)
{
    if (Node == nullptr)
    {
        return false;
    }

    if (!StringContainsIgnoreCase(Node->GetName(), NodeNameContains))
    {
        return false;
    }

    const FString NodeTitle = Node->GetNodeTitle(ENodeTitleType::ListView).ToString();
    if (!StringContainsIgnoreCase(NodeTitle, NodeTitleContains))
    {
        return false;
    }

    if (!NodeClassPath.IsEmpty() && !Node->GetClass()->GetPathName().Equals(NodeClassPath, ESearchCase::IgnoreCase))
    {
        return false;
    }

    if (!FunctionClassPath.IsEmpty() || !FunctionName.IsEmpty())
    {
        const UK2Node_CallFunction* CallNode = Cast<UK2Node_CallFunction>(Node);
        if (CallNode == nullptr)
        {
            return false;
        }
        const UFunction* TargetFunction = CallNode->GetTargetFunction();
        if (TargetFunction == nullptr)
        {
            return false;
        }
        if (!FunctionName.IsEmpty() && !TargetFunction->GetName().Equals(FunctionName, ESearchCase::IgnoreCase))
        {
            return false;
        }
        if (!FunctionClassPath.IsEmpty() && !TargetFunction->GetOuterUClass()->GetPathName().Equals(FunctionClassPath, ESearchCase::IgnoreCase))
        {
            return false;
        }
    }

    return true;
}

static bool JsonValueToPinDefault(const TSharedPtr<FJsonValue>& JsonValue, FString& OutDefaultValue)
{
    if (!JsonValue.IsValid())
    {
        return false;
    }

    if (JsonValue->Type == EJson::String)
    {
        OutDefaultValue = JsonValue->AsString();
        return true;
    }
    if (JsonValue->Type == EJson::Boolean)
    {
        OutDefaultValue = JsonValue->AsBool() ? TEXT("true") : TEXT("false");
        return true;
    }
    if (JsonValue->Type == EJson::Number)
    {
        OutDefaultValue = FString::SanitizeFloat(JsonValue->AsNumber());
        return true;
    }
    return false;
}

static int32 ApplyFunctionInputDefaults(UK2Node_CallFunction* CallNode, const TSharedPtr<FJsonObject>& InputsObject)
{
    if (CallNode == nullptr || !InputsObject.IsValid())
    {
        return 0;
    }

    int32 UpdatedPins = 0;
    for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : InputsObject->Values)
    {
        UEdGraphPin* Pin = CallNode->FindPin(Pair.Key);
        if (Pin == nullptr)
        {
            continue;
        }

        FString DefaultValue;
        if (!JsonValueToPinDefault(Pair.Value, DefaultValue))
        {
            continue;
        }

        Pin->DefaultValue = DefaultValue;
        ++UpdatedPins;
    }

    return UpdatedPins;
}

static UK2Node_IfThenElse* FindBranchConnectedToBeginPlay(UK2Node_Event* BeginPlayNode)
{
    if (BeginPlayNode == nullptr)
    {
        return nullptr;
    }

    UEdGraphPin* BeginPlayThenPin = BeginPlayNode->FindPin(UEdGraphSchema_K2::PN_Then);
    if (BeginPlayThenPin == nullptr)
    {
        return nullptr;
    }

    for (UEdGraphPin* LinkedPin : BeginPlayThenPin->LinkedTo)
    {
        if (LinkedPin == nullptr)
        {
            continue;
        }

        UEdGraphNode* OwningNode = LinkedPin->GetOwningNode();
        if (OwningNode == nullptr)
        {
            continue;
        }

        UK2Node_IfThenElse* BranchNode = Cast<UK2Node_IfThenElse>(OwningNode);
        if (BranchNode != nullptr)
        {
            return BranchNode;
        }
    }

    return nullptr;
}

static bool ConnectExecPins(UEdGraphPin* OutputPin, UEdGraphPin* InputPin)
{
    if (OutputPin == nullptr || InputPin == nullptr)
    {
        return false;
    }

    if (OutputPin->LinkedTo.Contains(InputPin))
    {
        return true;
    }

    const UEdGraphSchema_K2* K2Schema = GetDefault<UEdGraphSchema_K2>();
    return K2Schema != nullptr && K2Schema->TryCreateConnection(OutputPin, InputPin);
}

static bool IsNodePositionOccupied(
    const UEdGraph* EventGraph,
    const FVector2D& Position,
    const float MinXDistance = 220.0f,
    const float MinYDistance = 150.0f
)
{
    if (EventGraph == nullptr)
    {
        return false;
    }

    for (const UEdGraphNode* Node : EventGraph->Nodes)
    {
        if (Node == nullptr)
        {
            continue;
        }

        if (FMath::Abs(static_cast<float>(Node->NodePosX) - Position.X) < MinXDistance &&
            FMath::Abs(static_cast<float>(Node->NodePosY) - Position.Y) < MinYDistance)
        {
            return true;
        }
    }

    return false;
}

static FVector2D FindFreeNodePosition(
    const UEdGraph* EventGraph,
    const FVector2D& PreferredPosition
)
{
    // Scan in a small grid around preferred position until we find open space.
    constexpr float StepX = 260.0f;
    constexpr float StepY = 180.0f;
    constexpr int32 MaxCols = 6;
    constexpr int32 MaxRows = 8;

    for (int32 Row = 0; Row < MaxRows; ++Row)
    {
        for (int32 Col = 0; Col < MaxCols; ++Col)
        {
            const FVector2D Candidate(
                PreferredPosition.X + static_cast<float>(Col) * StepX,
                PreferredPosition.Y + static_cast<float>(Row) * StepY
            );
            if (!IsNodePositionOccupied(EventGraph, Candidate))
            {
                return Candidate;
            }
        }
    }

    // Fallback far-right placement.
    return FVector2D(
        PreferredPosition.X + static_cast<float>(MaxCols) * StepX,
        PreferredPosition.Y
    );
}

static bool BuildPinTypeFromRequest(
    const FString& VariableType,
    const FString& SubtypeClassPath,
    FEdGraphPinType& OutPinType,
    FString& OutError
)
{
    OutPinType = FEdGraphPinType();
    OutError.Reset();

    const FString TypeLower = VariableType.ToLower();
    if (TypeLower == TEXT("bool") || TypeLower == TEXT("boolean"))
    {
        OutPinType.PinCategory = UEdGraphSchema_K2::PC_Boolean;
        return true;
    }
    if (TypeLower == TEXT("int") || TypeLower == TEXT("integer"))
    {
        OutPinType.PinCategory = UEdGraphSchema_K2::PC_Int;
        return true;
    }
    if (TypeLower == TEXT("float"))
    {
        OutPinType.PinCategory = UEdGraphSchema_K2::PC_Real;
        OutPinType.PinSubCategory = UEdGraphSchema_K2::PC_Float;
        return true;
    }
    if (TypeLower == TEXT("string"))
    {
        OutPinType.PinCategory = UEdGraphSchema_K2::PC_String;
        return true;
    }
    if (TypeLower == TEXT("name"))
    {
        OutPinType.PinCategory = UEdGraphSchema_K2::PC_Name;
        return true;
    }
    if (TypeLower == TEXT("vector"))
    {
        OutPinType.PinCategory = UEdGraphSchema_K2::PC_Struct;
        OutPinType.PinSubCategoryObject = TBaseStructure<FVector>::Get();
        return true;
    }
    if (TypeLower == TEXT("rotator"))
    {
        OutPinType.PinCategory = UEdGraphSchema_K2::PC_Struct;
        OutPinType.PinSubCategoryObject = TBaseStructure<FRotator>::Get();
        return true;
    }
    if (TypeLower == TEXT("transform"))
    {
        OutPinType.PinCategory = UEdGraphSchema_K2::PC_Struct;
        OutPinType.PinSubCategoryObject = TBaseStructure<FTransform>::Get();
        return true;
    }
    if (TypeLower == TEXT("object"))
    {
        OutPinType.PinCategory = UEdGraphSchema_K2::PC_Object;
        OutPinType.PinSubCategoryObject = ResolveClassPath(SubtypeClassPath);
        if (OutPinType.PinSubCategoryObject == nullptr)
        {
            OutPinType.PinSubCategoryObject = UObject::StaticClass();
        }
        return true;
    }
    if (TypeLower == TEXT("class"))
    {
        OutPinType.PinCategory = UEdGraphSchema_K2::PC_Class;
        OutPinType.PinSubCategoryObject = ResolveClassPath(SubtypeClassPath);
        if (OutPinType.PinSubCategoryObject == nullptr)
        {
            OutPinType.PinSubCategoryObject = UObject::StaticClass();
        }
        return true;
    }

    OutError = FString::Printf(TEXT("Unsupported variable_type: %s"), *VariableType);
    return false;
}
} // namespace UnrealAgentPrivate

FString FModifyBlueprintGraphAction::GetName() const
{
    return TEXT("modify_blueprint_graph");
}

FString FModifyBlueprintGraphAction::GetDescription() const
{
    return TEXT("Graph ops: add_variable, remove_variable, set_default, add_branch, call_function, remove_function_call, remove_nodes, disconnect_pin, add_print_string_on_begin_play.");
}

FAgentActionResult FModifyBlueprintGraphAction::Execute(const FAgentActionRequest& Request)
{
    FString BlueprintPathOrObjectPath;
    FString Operation = TEXT("add_print_string_on_begin_play");
    bool bCompileAfter = true;

    TSharedPtr<FJsonObject> Payload = MakeShared<FJsonObject>();
    if (!Request.PayloadJson.IsEmpty())
    {
        FString ParseError;
        if (!UnrealAgentPrivate::ParseJsonObject(Request.PayloadJson, Payload, ParseError))
        {
            return {false, ParseError, TEXT("")};
        }

        Payload->TryGetStringField(TEXT("blueprint_path"), BlueprintPathOrObjectPath);
        Payload->TryGetStringField(TEXT("operation"), Operation);
        Payload->TryGetBoolField(TEXT("compile_after"), bCompileAfter);
    }

    if (BlueprintPathOrObjectPath.IsEmpty())
    {
        return {false, TEXT("Missing required payload field: blueprint_path"), TEXT("")};
    }

    const FString ObjectPath = UnrealAgentPrivate::NormalizeBlueprintObjectPath(BlueprintPathOrObjectPath);
    UBlueprint* Blueprint = FindObject<UBlueprint>(nullptr, *ObjectPath);
    if (Blueprint == nullptr)
    {
        Blueprint = LoadObject<UBlueprint>(nullptr, *ObjectPath);
    }

    if (Blueprint == nullptr)
    {
        return {false, FString::Printf(TEXT("Failed to load blueprint: %s"), *ObjectPath), TEXT("")};
    }

    UEdGraph* EventGraph = UnrealAgentPrivate::ResolveEventGraph(Blueprint);
    if (EventGraph == nullptr)
    {
        return {false, TEXT("Blueprint has no valid Event Graph."), TEXT("")};
    }

    const TSharedRef<FJsonObject> ResultPayload = MakeShared<FJsonObject>();
    ResultPayload->SetStringField(TEXT("blueprint"), Blueprint->GetPathName());
    ResultPayload->SetStringField(TEXT("event_graph"), EventGraph->GetName());
    ResultPayload->SetStringField(TEXT("operation"), Operation);
    ResultPayload->SetBoolField(TEXT("compile_after"), bCompileAfter);

    if (Request.bDryRun)
    {
        return {
            true,
            TEXT("Dry run successful. Graph was not modified."),
            UnrealAgentPrivate::SerializePayload(ResultPayload)
        };
    }

    const FScopedTransaction Transaction(NSLOCTEXT("UnrealAgent", "ModifyBlueprintGraphAction", "Agent Modify Blueprint Graph"));
    bool bMutatedBlueprint = false;

    if (Operation == TEXT("add_print_string_on_begin_play"))
    {
        FString Message = TEXT("Hello from UnrealAgent");
        FVector2D EventNodePos(-320.0f, 0.0f);
        FVector2D PrintNodePos(120.0f, 0.0f);
        bool bCustomPrintNodePos = false;
        Payload->TryGetStringField(TEXT("message"), Message);
        FVector2D ParsedPos;
        if (UnrealAgentPrivate::ReadVector2Field(Payload, TEXT("event_node_pos"), ParsedPos))
        {
            EventNodePos = ParsedPos;
        }
        if (UnrealAgentPrivate::ReadVector2Field(Payload, TEXT("print_node_pos"), ParsedPos))
        {
            PrintNodePos = ParsedPos;
            bCustomPrintNodePos = true;
        }

        bool bCreatedBeginPlay = false;
        UK2Node_Event* BeginPlayNode = UnrealAgentPrivate::EnsureBeginPlayNode(EventGraph, EventNodePos, bCreatedBeginPlay);
        if (BeginPlayNode == nullptr)
        {
            return {false, TEXT("Failed to create or find BeginPlay node."), TEXT("")};
        }

        UFunction* PrintFunction = UKismetSystemLibrary::StaticClass()->FindFunctionByName(
            GET_FUNCTION_NAME_CHECKED(UKismetSystemLibrary, PrintString)
        );
        if (PrintFunction == nullptr)
        {
            return {false, TEXT("Could not resolve UKismetSystemLibrary::PrintString."), TEXT("")};
        }

        UK2Node_CallFunction* PrintNode = UnrealAgentPrivate::FindCallFunctionNode(EventGraph, PrintFunction);
        bool bCreatedPrintNode = false;
        if (PrintNode == nullptr)
        {
            if (!bCustomPrintNodePos)
            {
                PrintNodePos = UnrealAgentPrivate::FindFreeNodePosition(
                    EventGraph,
                    FVector2D(static_cast<float>(BeginPlayNode->NodePosX) + 340.0f, static_cast<float>(BeginPlayNode->NodePosY))
                );
            }
            PrintNode = UnrealAgentPrivate::SpawnFunctionNode(EventGraph, PrintFunction, PrintNodePos);
            bCreatedPrintNode = PrintNode != nullptr;
            bMutatedBlueprint = bMutatedBlueprint || bCreatedPrintNode;
        }

        if (PrintNode == nullptr)
        {
            return {false, TEXT("Failed to create or find PrintString node."), TEXT("")};
        }

        UEdGraphPin* InStringPin = PrintNode->FindPin(TEXT("InString"));
        if (InStringPin != nullptr)
        {
            InStringPin->DefaultValue = Message;
            bMutatedBlueprint = true;
        }

        UEdGraphPin* BeginPlayThenPin = BeginPlayNode->FindPin(UEdGraphSchema_K2::PN_Then);
        UEdGraphPin* PrintExecPin = PrintNode->FindPin(UEdGraphSchema_K2::PN_Execute);
        if (!UnrealAgentPrivate::ConnectExecPins(BeginPlayThenPin, PrintExecPin))
        {
            return {false, TEXT("Failed to connect BeginPlay -> PrintString."), TEXT("")};
        }
        bMutatedBlueprint = true;

        ResultPayload->SetStringField(TEXT("message"), Message);
        ResultPayload->SetBoolField(TEXT("created_begin_play_node"), bCreatedBeginPlay);
        ResultPayload->SetBoolField(TEXT("created_print_node"), bCreatedPrintNode);
    }
    else if (Operation == TEXT("add_variable"))
    {
        FString VariableName;
        FString VariableType = TEXT("bool");
        FString SubtypeClassPath;
        FString DefaultValue = TEXT("false");
        FString Category = TEXT("Agent");
        Payload->TryGetStringField(TEXT("variable_name"), VariableName);
        Payload->TryGetStringField(TEXT("variable_type"), VariableType);
        Payload->TryGetStringField(TEXT("subtype_class"), SubtypeClassPath);
        Payload->TryGetStringField(TEXT("default_value"), DefaultValue);
        Payload->TryGetStringField(TEXT("category"), Category);

        if (VariableName.IsEmpty())
        {
            return {false, TEXT("Missing required field for add_variable: variable_name"), TEXT("")};
        }

        UBlueprint* ExistingVarOwner = nullptr;
        if (FBlueprintEditorUtils::FindNewVariableIndexAndBlueprint(Blueprint, FName(*VariableName), ExistingVarOwner) != INDEX_NONE)
        {
            return {false, FString::Printf(TEXT("Variable already exists: %s"), *VariableName), TEXT("")};
        }

        FEdGraphPinType PinType;
        FString TypeError;
        if (!UnrealAgentPrivate::BuildPinTypeFromRequest(VariableType, SubtypeClassPath, PinType, TypeError))
        {
            return {false, TypeError, TEXT("")};
        }

        const bool bAdded = FBlueprintEditorUtils::AddMemberVariable(Blueprint, FName(*VariableName), PinType, DefaultValue);
        if (!bAdded)
        {
            return {false, TEXT("Failed to add Blueprint variable."), TEXT("")};
        }

        if (!Category.IsEmpty())
        {
            FBlueprintEditorUtils::SetBlueprintVariableCategory(
                Blueprint,
                FName(*VariableName),
                nullptr,
                FText::FromString(Category),
                true
            );
        }

        bMutatedBlueprint = true;
        ResultPayload->SetStringField(TEXT("variable_name"), VariableName);
        ResultPayload->SetStringField(TEXT("variable_type"), VariableType);
        ResultPayload->SetStringField(TEXT("default_value"), DefaultValue);
        ResultPayload->SetStringField(TEXT("category"), Category);
    }
    else if (Operation == TEXT("remove_variable"))
    {
        FString VariableName;
        bool bFailIfMissing = false;
        Payload->TryGetStringField(TEXT("variable_name"), VariableName);
        Payload->TryGetBoolField(TEXT("fail_if_missing"), bFailIfMissing);

        if (VariableName.IsEmpty())
        {
            return {false, TEXT("Missing required field for remove_variable: variable_name"), TEXT("")};
        }

        UBlueprint* ExistingVarOwner = nullptr;
        const int32 ExistingIndex = FBlueprintEditorUtils::FindNewVariableIndexAndBlueprint(Blueprint, FName(*VariableName), ExistingVarOwner);
        if (ExistingIndex == INDEX_NONE)
        {
            if (bFailIfMissing)
            {
                return {false, FString::Printf(TEXT("Variable not found: %s"), *VariableName), TEXT("")};
            }
            ResultPayload->SetStringField(TEXT("variable_name"), VariableName);
            ResultPayload->SetBoolField(TEXT("removed"), false);
            ResultPayload->SetBoolField(TEXT("missing"), true);
        }
        else
        {
            FBlueprintEditorUtils::RemoveMemberVariable(Blueprint, FName(*VariableName));
            bMutatedBlueprint = true;
            ResultPayload->SetStringField(TEXT("variable_name"), VariableName);
            ResultPayload->SetBoolField(TEXT("removed"), true);
            ResultPayload->SetBoolField(TEXT("missing"), false);
        }
    }
    else if (Operation == TEXT("set_default"))
    {
        FString VariableName;
        FString DefaultValue;
        FString FunctionClassPath;
        FString FunctionName;
        FString NodeNameContains;
        FString NodeTitleContains;
        FString PinName = TEXT("InString");
        bool bCreateIfMissing = false;
        FVector2D NodePos(360.0f, 120.0f);

        Payload->TryGetStringField(TEXT("variable_name"), VariableName);
        Payload->TryGetStringField(TEXT("default_value"), DefaultValue);
        Payload->TryGetStringField(TEXT("class_path"), FunctionClassPath);
        Payload->TryGetStringField(TEXT("function_name"), FunctionName);
        Payload->TryGetStringField(TEXT("node_name_contains"), NodeNameContains);
        Payload->TryGetStringField(TEXT("node_title_contains"), NodeTitleContains);
        Payload->TryGetStringField(TEXT("pin_name"), PinName);
        Payload->TryGetBoolField(TEXT("create_if_missing"), bCreateIfMissing);
        FVector2D ParsedPos;
        if (UnrealAgentPrivate::ReadVector2Field(Payload, TEXT("node_pos"), ParsedPos))
        {
            NodePos = ParsedPos;
        }

        if (DefaultValue.IsEmpty())
        {
            return {false, TEXT("Missing required field for set_default: default_value"), TEXT("")};
        }

        if (!VariableName.IsEmpty())
        {
            UBlueprint* VarOwner = nullptr;
            if (FBlueprintEditorUtils::FindNewVariableIndexAndBlueprint(Blueprint, FName(*VariableName), VarOwner) == INDEX_NONE)
            {
                return {false, FString::Printf(TEXT("Variable not found: %s"), *VariableName), TEXT("")};
            }

            FBlueprintEditorUtils::SetBlueprintVariableMetaData(
                Blueprint,
                FName(*VariableName),
                nullptr,
                FName(TEXT("DefaultValue")),
                DefaultValue
            );
            bMutatedBlueprint = true;
            ResultPayload->SetStringField(TEXT("target"), TEXT("variable"));
            ResultPayload->SetStringField(TEXT("variable_name"), VariableName);
            ResultPayload->SetStringField(TEXT("default_value"), DefaultValue);
        }
        else
        {
            if (FunctionClassPath.IsEmpty() || FunctionName.IsEmpty())
            {
                return {false, TEXT("set_default requires either variable_name, or class_path + function_name."), TEXT("")};
            }

            UFunction* TargetFunction = UnrealAgentPrivate::ResolveFunction(FunctionClassPath, FunctionName);
            if (TargetFunction == nullptr)
            {
                return {
                    false,
                    FString::Printf(TEXT("Could not resolve function %s on %s"), *FunctionName, *FunctionClassPath),
                    TEXT("")
                };
            }

            UK2Node_CallFunction* CallNode = nullptr;
            TArray<UK2Node_CallFunction*> Candidates = UnrealAgentPrivate::FindCallFunctionNodes(EventGraph, TargetFunction);
            for (UK2Node_CallFunction* Candidate : Candidates)
            {
                if (UnrealAgentPrivate::NodeMatchesGenericFilters(
                        Candidate,
                        NodeNameContains,
                        NodeTitleContains,
                        TEXT(""),
                        FunctionClassPath,
                        FunctionName))
                {
                    CallNode = Candidate;
                    break;
                }
            }
            bool bCreatedNode = false;
            if (CallNode == nullptr && bCreateIfMissing)
            {
                CallNode = UnrealAgentPrivate::SpawnFunctionNode(EventGraph, TargetFunction, NodePos);
                bCreatedNode = CallNode != nullptr;
                bMutatedBlueprint = bMutatedBlueprint || bCreatedNode;
            }

            if (CallNode == nullptr)
            {
                return {false, TEXT("Function node not found for set_default."), TEXT("")};
            }

            UEdGraphPin* TargetPin = CallNode->FindPin(PinName);
            if (TargetPin == nullptr)
            {
                return {false, FString::Printf(TEXT("Pin not found: %s"), *PinName), TEXT("")};
            }

            TargetPin->DefaultValue = DefaultValue;
            bMutatedBlueprint = true;
            ResultPayload->SetStringField(TEXT("target"), TEXT("function_pin"));
            ResultPayload->SetStringField(TEXT("class_path"), FunctionClassPath);
            ResultPayload->SetStringField(TEXT("function_name"), FunctionName);
            ResultPayload->SetStringField(TEXT("node_name"), CallNode->GetName());
            ResultPayload->SetStringField(TEXT("pin_name"), PinName);
            ResultPayload->SetStringField(TEXT("default_value"), DefaultValue);
            ResultPayload->SetBoolField(TEXT("created_node"), bCreatedNode);
        }
    }
    else if (Operation == TEXT("add_branch"))
    {
        FVector2D EventNodePos(-320.0f, 0.0f);
        FVector2D BranchNodePos(-20.0f, 0.0f);
        bool bCustomBranchNodePos = false;
        bool bConditionDefault = false;
        bool bHasConditionDefault = false;

        FVector2D ParsedPos;
        if (UnrealAgentPrivate::ReadVector2Field(Payload, TEXT("event_node_pos"), ParsedPos))
        {
            EventNodePos = ParsedPos;
        }
        if (UnrealAgentPrivate::ReadVector2Field(Payload, TEXT("branch_node_pos"), ParsedPos))
        {
            BranchNodePos = ParsedPos;
            bCustomBranchNodePos = true;
        }
        if (Payload->TryGetBoolField(TEXT("condition_default"), bConditionDefault))
        {
            bHasConditionDefault = true;
        }

        bool bCreatedBeginPlayNode = false;
        UK2Node_Event* BeginPlayNode = UnrealAgentPrivate::EnsureBeginPlayNode(EventGraph, EventNodePos, bCreatedBeginPlayNode);
        if (BeginPlayNode == nullptr)
        {
            return {false, TEXT("Failed to create or find BeginPlay node."), TEXT("")};
        }

        UK2Node_IfThenElse* BranchNode = UnrealAgentPrivate::FindBranchConnectedToBeginPlay(BeginPlayNode);
        bool bCreatedBranchNode = false;
        if (BranchNode == nullptr)
        {
            if (!bCustomBranchNodePos)
            {
                BranchNodePos = UnrealAgentPrivate::FindFreeNodePosition(
                    EventGraph,
                    FVector2D(static_cast<float>(BeginPlayNode->NodePosX) + 300.0f, static_cast<float>(BeginPlayNode->NodePosY))
                );
            }
            BranchNode = FEdGraphSchemaAction_K2NewNode::SpawnNode<UK2Node_IfThenElse>(
                EventGraph,
                BranchNodePos,
                EK2NewNodeFlags::SelectNewNode,
                [](UK2Node_IfThenElse* NewNode) {}
            );
            bCreatedBranchNode = BranchNode != nullptr;
            bMutatedBlueprint = bMutatedBlueprint || bCreatedBranchNode;
        }

        if (BranchNode == nullptr)
        {
            return {false, TEXT("Failed to create or find Branch node."), TEXT("")};
        }

        UEdGraphPin* BeginPlayThenPin = BeginPlayNode->FindPin(UEdGraphSchema_K2::PN_Then);
        UEdGraphPin* BranchExecPin = BranchNode->FindPin(UEdGraphSchema_K2::PN_Execute);
        if (!UnrealAgentPrivate::ConnectExecPins(BeginPlayThenPin, BranchExecPin))
        {
            return {false, TEXT("Failed to connect BeginPlay -> Branch."), TEXT("")};
        }
        bMutatedBlueprint = true;

        if (bHasConditionDefault)
        {
            if (UEdGraphPin* ConditionPin = BranchNode->GetConditionPin())
            {
                ConditionPin->DefaultValue = bConditionDefault ? TEXT("true") : TEXT("false");
                bMutatedBlueprint = true;
            }
        }

        ResultPayload->SetBoolField(TEXT("created_begin_play_node"), bCreatedBeginPlayNode);
        ResultPayload->SetBoolField(TEXT("created_branch_node"), bCreatedBranchNode);
        ResultPayload->SetBoolField(TEXT("condition_default"), bConditionDefault);
    }
    else if (Operation == TEXT("call_function"))
    {
        FString ClassPath;
        FString FunctionName;
        FString ExecSource = TEXT("begin_play");
        FVector2D EventNodePos(-320.0f, 0.0f);
        FVector2D NodePos(320.0f, 0.0f);
        bool bCustomNodePos = false;
        bool bCreateIfMissing = true;

        Payload->TryGetStringField(TEXT("class_path"), ClassPath);
        Payload->TryGetStringField(TEXT("function_name"), FunctionName);
        Payload->TryGetStringField(TEXT("exec_source"), ExecSource);
        Payload->TryGetBoolField(TEXT("create_if_missing"), bCreateIfMissing);
        FVector2D ParsedPos;
        if (UnrealAgentPrivate::ReadVector2Field(Payload, TEXT("event_node_pos"), ParsedPos))
        {
            EventNodePos = ParsedPos;
        }
        if (UnrealAgentPrivate::ReadVector2Field(Payload, TEXT("node_pos"), ParsedPos))
        {
            NodePos = ParsedPos;
            bCustomNodePos = true;
        }

        if (ClassPath.IsEmpty() || FunctionName.IsEmpty())
        {
            return {false, TEXT("call_function requires class_path and function_name."), TEXT("")};
        }

        UFunction* TargetFunction = UnrealAgentPrivate::ResolveFunction(ClassPath, FunctionName);
        if (TargetFunction == nullptr)
        {
            return {
                false,
                FString::Printf(TEXT("Could not resolve function %s on %s"), *FunctionName, *ClassPath),
                TEXT("")
            };
        }

        UK2Node_CallFunction* CallNode = UnrealAgentPrivate::FindCallFunctionNode(EventGraph, TargetFunction);
        bool bCreatedNode = false;
        if (CallNode == nullptr && bCreateIfMissing)
        {
            if (!bCustomNodePos)
            {
                // Default to a rightward flow from BeginPlay lane.
                NodePos = FVector2D(320.0f, 0.0f);
            }
            CallNode = UnrealAgentPrivate::SpawnFunctionNode(EventGraph, TargetFunction, NodePos);
            bCreatedNode = CallNode != nullptr;
            bMutatedBlueprint = bMutatedBlueprint || bCreatedNode;
        }

        if (CallNode == nullptr)
        {
            return {false, TEXT("Function node not found and create_if_missing is false."), TEXT("")};
        }

        const TSharedPtr<FJsonObject>* InputsObjectPtr = nullptr;
        if (Payload->TryGetObjectField(TEXT("inputs"), InputsObjectPtr) && InputsObjectPtr != nullptr && InputsObjectPtr->IsValid())
        {
            const int32 UpdatedPins = UnrealAgentPrivate::ApplyFunctionInputDefaults(CallNode, *InputsObjectPtr);
            bMutatedBlueprint = bMutatedBlueprint || UpdatedPins > 0;
            ResultPayload->SetNumberField(TEXT("updated_input_pins"), UpdatedPins);
        }

        if (ExecSource != TEXT("none"))
        {
            bool bCreatedBeginPlayNode = false;
            UK2Node_Event* BeginPlayNode = UnrealAgentPrivate::EnsureBeginPlayNode(EventGraph, EventNodePos, bCreatedBeginPlayNode);
            if (BeginPlayNode == nullptr)
            {
                return {false, TEXT("Failed to create or find BeginPlay node for function call wiring."), TEXT("")};
            }

            UEdGraphPin* SourceExecPin = nullptr;
            if (ExecSource == TEXT("begin_play"))
            {
                if (bCreatedNode && !bCustomNodePos)
                {
                    NodePos = UnrealAgentPrivate::FindFreeNodePosition(
                        EventGraph,
                        FVector2D(static_cast<float>(BeginPlayNode->NodePosX) + 340.0f, static_cast<float>(BeginPlayNode->NodePosY))
                    );
                    CallNode->NodePosX = static_cast<int32>(NodePos.X);
                    CallNode->NodePosY = static_cast<int32>(NodePos.Y);
                }
                SourceExecPin = BeginPlayNode->FindPin(UEdGraphSchema_K2::PN_Then);
            }
            else if (ExecSource == TEXT("branch_true") || ExecSource == TEXT("branch_false"))
            {
                UK2Node_IfThenElse* BranchNode = UnrealAgentPrivate::FindBranchConnectedToBeginPlay(BeginPlayNode);
                if (BranchNode == nullptr)
                {
                    const FVector2D BranchPos = UnrealAgentPrivate::FindFreeNodePosition(
                        EventGraph,
                        FVector2D(static_cast<float>(BeginPlayNode->NodePosX) + 280.0f, static_cast<float>(BeginPlayNode->NodePosY))
                    );
                    BranchNode = FEdGraphSchemaAction_K2NewNode::SpawnNode<UK2Node_IfThenElse>(
                        EventGraph,
                        BranchPos,
                        EK2NewNodeFlags::SelectNewNode,
                        [](UK2Node_IfThenElse* NewNode) {}
                    );
                    if (BranchNode != nullptr)
                    {
                        UEdGraphPin* BeginPlayThenPin = BeginPlayNode->FindPin(UEdGraphSchema_K2::PN_Then);
                        UEdGraphPin* BranchExecPin = BranchNode->FindPin(UEdGraphSchema_K2::PN_Execute);
                        UnrealAgentPrivate::ConnectExecPins(BeginPlayThenPin, BranchExecPin);
                        bMutatedBlueprint = true;
                    }
                }

                if (BranchNode != nullptr)
                {
                    if (bCreatedNode && !bCustomNodePos)
                    {
                        const float YOffset = ExecSource == TEXT("branch_true") ? -120.0f : 120.0f;
                        const FVector2D AutoPos = UnrealAgentPrivate::FindFreeNodePosition(
                            EventGraph,
                            FVector2D(static_cast<float>(BranchNode->NodePosX) + 340.0f, static_cast<float>(BranchNode->NodePosY) + YOffset)
                        );
                        CallNode->NodePosX = static_cast<int32>(AutoPos.X);
                        CallNode->NodePosY = static_cast<int32>(AutoPos.Y);
                    }
                    SourceExecPin = ExecSource == TEXT("branch_true")
                        ? BranchNode->GetThenPin()
                        : BranchNode->GetElsePin();
                }
            }
            else
            {
                return {false, FString::Printf(TEXT("Unsupported exec_source: %s"), *ExecSource), TEXT("")};
            }

            UEdGraphPin* CallExecPin = CallNode->FindPin(UEdGraphSchema_K2::PN_Execute);
            if (!UnrealAgentPrivate::ConnectExecPins(SourceExecPin, CallExecPin))
            {
                return {false, TEXT("Failed to wire exec source to function call."), TEXT("")};
            }
            bMutatedBlueprint = true;
        }

        ResultPayload->SetStringField(TEXT("class_path"), ClassPath);
        ResultPayload->SetStringField(TEXT("function_name"), FunctionName);
        ResultPayload->SetStringField(TEXT("exec_source"), ExecSource);
        ResultPayload->SetBoolField(TEXT("created_node"), bCreatedNode);
    }
    else if (Operation == TEXT("remove_function_call"))
    {
        FString ClassPath;
        FString FunctionName;
        bool bRemoveAll = true;
        bool bDisconnectOnly = false;
        bool bFailIfMissing = false;

        Payload->TryGetStringField(TEXT("class_path"), ClassPath);
        Payload->TryGetStringField(TEXT("function_name"), FunctionName);
        Payload->TryGetBoolField(TEXT("remove_all"), bRemoveAll);
        Payload->TryGetBoolField(TEXT("disconnect_only"), bDisconnectOnly);
        Payload->TryGetBoolField(TEXT("fail_if_missing"), bFailIfMissing);

        if (ClassPath.IsEmpty() || FunctionName.IsEmpty())
        {
            return {false, TEXT("remove_function_call requires class_path and function_name."), TEXT("")};
        }

        UFunction* TargetFunction = UnrealAgentPrivate::ResolveFunction(ClassPath, FunctionName);
        if (TargetFunction == nullptr)
        {
            return {
                false,
                FString::Printf(TEXT("Could not resolve function %s on %s"), *FunctionName, *ClassPath),
                TEXT("")
            };
        }

        TArray<UK2Node_CallFunction*> Matches = UnrealAgentPrivate::FindCallFunctionNodes(EventGraph, TargetFunction);
        if (!bRemoveAll && Matches.Num() > 1)
        {
            Matches.SetNum(1);
        }

        if (Matches.Num() == 0)
        {
            if (bFailIfMissing)
            {
                return {false, TEXT("remove_function_call found no matching nodes."), TEXT("")};
            }
            ResultPayload->SetStringField(TEXT("class_path"), ClassPath);
            ResultPayload->SetStringField(TEXT("function_name"), FunctionName);
            ResultPayload->SetBoolField(TEXT("disconnect_only"), bDisconnectOnly);
            ResultPayload->SetNumberField(TEXT("matched_nodes"), 0);
            ResultPayload->SetNumberField(TEXT("removed_nodes"), 0);
            ResultPayload->SetNumberField(TEXT("disconnected_nodes"), 0);
        }
        else
        {
            int32 DisconnectedNodes = 0;
            int32 RemovedNodes = 0;
            for (UK2Node_CallFunction* Node : Matches)
            {
                if (Node == nullptr)
                {
                    continue;
                }
                Node->Modify();
                Node->BreakAllNodeLinks();
                ++DisconnectedNodes;
                if (!bDisconnectOnly)
                {
                    Node->DestroyNode();
                    ++RemovedNodes;
                }
            }

            bMutatedBlueprint = DisconnectedNodes > 0 || RemovedNodes > 0;
            ResultPayload->SetStringField(TEXT("class_path"), ClassPath);
            ResultPayload->SetStringField(TEXT("function_name"), FunctionName);
            ResultPayload->SetBoolField(TEXT("disconnect_only"), bDisconnectOnly);
            ResultPayload->SetNumberField(TEXT("matched_nodes"), Matches.Num());
            ResultPayload->SetNumberField(TEXT("removed_nodes"), RemovedNodes);
            ResultPayload->SetNumberField(TEXT("disconnected_nodes"), DisconnectedNodes);
        }
    }
    else if (Operation == TEXT("remove_nodes"))
    {
        FString NodeNameContains;
        FString NodeTitleContains;
        FString NodeClassPath;
        FString FunctionClassPath;
        FString FunctionName;
        bool bRemoveAll = true;
        bool bDisconnectOnly = false;
        bool bFailIfMissing = false;

        Payload->TryGetStringField(TEXT("node_name_contains"), NodeNameContains);
        Payload->TryGetStringField(TEXT("node_title_contains"), NodeTitleContains);
        Payload->TryGetStringField(TEXT("node_class_path"), NodeClassPath);
        Payload->TryGetStringField(TEXT("function_class_path"), FunctionClassPath);
        Payload->TryGetStringField(TEXT("function_name"), FunctionName);
        Payload->TryGetBoolField(TEXT("remove_all"), bRemoveAll);
        Payload->TryGetBoolField(TEXT("disconnect_only"), bDisconnectOnly);
        Payload->TryGetBoolField(TEXT("fail_if_missing"), bFailIfMissing);

        if (NodeNameContains.IsEmpty() && NodeTitleContains.IsEmpty() && NodeClassPath.IsEmpty() && FunctionClassPath.IsEmpty() && FunctionName.IsEmpty())
        {
            return {false, TEXT("remove_nodes requires at least one filter field."), TEXT("")};
        }

        TArray<UEdGraphNode*> Matches;
        for (UEdGraphNode* Node : EventGraph->Nodes)
        {
            if (UnrealAgentPrivate::NodeMatchesGenericFilters(
                Node,
                NodeNameContains,
                NodeTitleContains,
                NodeClassPath,
                FunctionClassPath,
                FunctionName))
            {
                Matches.Add(Node);
            }
        }

        if (!bRemoveAll && Matches.Num() > 1)
        {
            Matches.SetNum(1);
        }

        if (Matches.Num() == 0)
        {
            if (bFailIfMissing)
            {
                return {false, TEXT("remove_nodes found no matching nodes."), TEXT("")};
            }
            ResultPayload->SetNumberField(TEXT("matched_nodes"), 0);
            ResultPayload->SetNumberField(TEXT("removed_nodes"), 0);
            ResultPayload->SetNumberField(TEXT("disconnected_nodes"), 0);
        }
        else
        {
            int32 DisconnectedNodes = 0;
            int32 RemovedNodes = 0;
            for (UEdGraphNode* Node : Matches)
            {
                if (Node == nullptr)
                {
                    continue;
                }
                Node->Modify();
                Node->BreakAllNodeLinks();
                ++DisconnectedNodes;
                if (!bDisconnectOnly)
                {
                    Node->DestroyNode();
                    ++RemovedNodes;
                }
            }

            bMutatedBlueprint = DisconnectedNodes > 0 || RemovedNodes > 0;
            ResultPayload->SetNumberField(TEXT("matched_nodes"), Matches.Num());
            ResultPayload->SetNumberField(TEXT("removed_nodes"), RemovedNodes);
            ResultPayload->SetNumberField(TEXT("disconnected_nodes"), DisconnectedNodes);
        }
    }
    else if (Operation == TEXT("disconnect_pin"))
    {
        FString FromNodeName;
        FString FromPinName;
        FString ToNodeName;
        FString ToPinName;
        bool bFailIfMissing = false;
        Payload->TryGetStringField(TEXT("from_node_name"), FromNodeName);
        Payload->TryGetStringField(TEXT("from_pin_name"), FromPinName);
        Payload->TryGetStringField(TEXT("to_node_name"), ToNodeName);
        Payload->TryGetStringField(TEXT("to_pin_name"), ToPinName);
        Payload->TryGetBoolField(TEXT("fail_if_missing"), bFailIfMissing);

        if (FromNodeName.IsEmpty() || FromPinName.IsEmpty() || ToNodeName.IsEmpty() || ToPinName.IsEmpty())
        {
            return {
                false,
                TEXT("disconnect_pin requires from_node_name, from_pin_name, to_node_name, to_pin_name."),
                TEXT("")
            };
        }

        UEdGraphNode* FromNode = UnrealAgentPrivate::FindNodeByName(EventGraph, FromNodeName);
        UEdGraphNode* ToNode = UnrealAgentPrivate::FindNodeByName(EventGraph, ToNodeName);
        if (FromNode == nullptr || ToNode == nullptr)
        {
            if (bFailIfMissing)
            {
                return {false, TEXT("disconnect_pin could not find source or target node."), TEXT("")};
            }
            ResultPayload->SetBoolField(TEXT("disconnected"), false);
            ResultPayload->SetBoolField(TEXT("missing_node"), true);
        }
        else
        {
            UEdGraphPin* FromPin = FromNode->FindPin(FromPinName);
            UEdGraphPin* ToPin = ToNode->FindPin(ToPinName);
            if (FromPin == nullptr || ToPin == nullptr)
            {
                if (bFailIfMissing)
                {
                    return {false, TEXT("disconnect_pin could not find source or target pin."), TEXT("")};
                }
                ResultPayload->SetBoolField(TEXT("disconnected"), false);
                ResultPayload->SetBoolField(TEXT("missing_pin"), true);
            }
            else
            {
                const bool bHadLink = FromPin->LinkedTo.Contains(ToPin) || ToPin->LinkedTo.Contains(FromPin);
                if (bHadLink)
                {
                    FromPin->BreakLinkTo(ToPin);
                    bMutatedBlueprint = true;
                }
                else if (bFailIfMissing)
                {
                    return {false, TEXT("disconnect_pin did not find an existing link between pins."), TEXT("")};
                }
                ResultPayload->SetBoolField(TEXT("disconnected"), bHadLink);
                ResultPayload->SetBoolField(TEXT("had_link"), bHadLink);
            }
        }

        ResultPayload->SetStringField(TEXT("from_node_name"), FromNodeName);
        ResultPayload->SetStringField(TEXT("from_pin_name"), FromPinName);
        ResultPayload->SetStringField(TEXT("to_node_name"), ToNodeName);
        ResultPayload->SetStringField(TEXT("to_pin_name"), ToPinName);
    }
    else
    {
        return {
            false,
            FString::Printf(TEXT("Unsupported operation: %s"), *Operation),
            TEXT("")
        };
    }

    if (bMutatedBlueprint)
    {
        FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
    }

    FString CompileStatus = TEXT("NotCompiled");
    if (bCompileAfter)
    {
        FKismetEditorUtilities::CompileBlueprint(Blueprint);
        if (const UEnum* StatusEnum = StaticEnum<EBlueprintStatus>())
        {
            CompileStatus = StatusEnum->GetNameStringByValue(static_cast<int64>(Blueprint->Status));
        }
    }
    ResultPayload->SetStringField(TEXT("compile_status"), CompileStatus);

    const bool bCompileSucceeded = !bCompileAfter || Blueprint->Status != BS_Error;
    return {
        bCompileSucceeded,
        bCompileSucceeded ? TEXT("Blueprint graph modified.") : TEXT("Blueprint graph modified, but compile reported errors."),
        UnrealAgentPrivate::SerializePayload(ResultPayload)
    };
}
