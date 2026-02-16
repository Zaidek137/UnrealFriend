#include "Agent/Actions/BlueprintAnalysisShared.h"

#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "Engine/Blueprint.h"

namespace UnrealAgentPrivate
{
namespace
{
bool IsExecPin(const UEdGraphPin* Pin)
{
    return Pin != nullptr && Pin->PinType.PinCategory == FName(TEXT("exec"));
}

FString NodeLabel(const UEdGraphNode* Node)
{
    return Node != nullptr ? Node->GetNodeTitle(ENodeTitleType::ListView).ToString() : TEXT("");
}

FString SafePinDefault(const UEdGraphPin* Pin)
{
    return Pin != nullptr ? Pin->GetDefaultAsString() : TEXT("");
}

TArray<const UEdGraphPin*> CollectExecPins(const UEdGraphNode* Node, const EEdGraphPinDirection Direction)
{
    TArray<const UEdGraphPin*> Out;
    if (Node == nullptr)
    {
        return Out;
    }

    for (const UEdGraphPin* Pin : Node->Pins)
    {
        if (Pin == nullptr || Pin->Direction != Direction || !IsExecPin(Pin))
        {
            continue;
        }
        Out.Add(Pin);
    }

    return Out;
}

const UEdGraphPin* FindPinByName(const UEdGraphNode* Node, const TCHAR* Name)
{
    if (Node == nullptr)
    {
        return nullptr;
    }

    for (const UEdGraphPin* Pin : Node->Pins)
    {
        if (Pin != nullptr && Pin->PinName == FName(Name))
        {
            return Pin;
        }
    }

    return nullptr;
}

bool IsEntryNode(const UEdGraphNode* Node)
{
    if (Node == nullptr)
    {
        return false;
    }

    const FString ClassPath = Node->GetClass()->GetPathName();
    return ClassPath.Contains(TEXT("K2Node_Event"))
        || ClassPath.Contains(TEXT("K2Node_FunctionEntry"))
        || ClassPath.Contains(TEXT("K2Node_Tunnel"));
}

bool IsFunctionCallNode(const UEdGraphNode* Node)
{
    return Node != nullptr && Node->GetClass()->GetPathName().Contains(TEXT("K2Node_CallFunction"));
}

bool IsBranchNode(const UEdGraphNode* Node)
{
    return Node != nullptr && Node->GetClass()->GetPathName().Contains(TEXT("K2Node_IfThenElse"));
}

bool IsEnumNode(const UEdGraphNode* Node)
{
    if (Node == nullptr)
    {
        return false;
    }
    const FString ClassPath = Node->GetClass()->GetPathName();
    return ClassPath.Contains(TEXT("K2Node_Enum")) || ClassPath.Contains(TEXT("CastByteToEnum"));
}

TSharedRef<FJsonObject> BuildLinkedNodeRef(const UEdGraphPin* LinkedPin)
{
    TSharedRef<FJsonObject> Ref = MakeShared<FJsonObject>();
    if (LinkedPin == nullptr || LinkedPin->GetOwningNode() == nullptr)
    {
        return Ref;
    }

    const UEdGraphNode* LinkedNode = LinkedPin->GetOwningNode();
    Ref->SetStringField(TEXT("node_name"), LinkedNode->GetName());
    Ref->SetStringField(TEXT("node_title"), NodeLabel(LinkedNode));
    Ref->SetStringField(TEXT("pin_name"), LinkedPin->PinName.ToString());
    Ref->SetStringField(TEXT("pin_direction"), LinkedPin->Direction == EGPD_Input ? TEXT("input") : TEXT("output"));
    return Ref;
}

void CollectNodeConstants(const UEdGraphNode* Node, TArray<TSharedPtr<FJsonValue>>& OutConstants)
{
    if (Node == nullptr)
    {
        return;
    }

    TArray<TSharedPtr<FJsonValue>> PinDefaults;
    for (const UEdGraphPin* Pin : Node->Pins)
    {
        if (Pin == nullptr)
        {
            continue;
        }

        const FString DefaultText = SafePinDefault(Pin);
        if (DefaultText.IsEmpty())
        {
            continue;
        }

        TSharedRef<FJsonObject> Constant = MakeShared<FJsonObject>();
        Constant->SetStringField(TEXT("pin_name"), Pin->PinName.ToString());
        Constant->SetStringField(TEXT("default_value"), DefaultText);
        Constant->SetStringField(TEXT("category"), Pin->PinType.PinCategory.ToString());
        PinDefaults.Add(MakeShared<FJsonValueObject>(Constant));
    }

    if (PinDefaults.Num() > 0)
    {
        TSharedRef<FJsonObject> NodeConstant = MakeShared<FJsonObject>();
        NodeConstant->SetStringField(TEXT("node_name"), Node->GetName());
        NodeConstant->SetStringField(TEXT("node_title"), NodeLabel(Node));
        NodeConstant->SetStringField(TEXT("node_class"), Node->GetClass()->GetPathName());
        NodeConstant->SetArrayField(TEXT("pin_defaults"), PinDefaults);
        OutConstants.Add(MakeShared<FJsonValueObject>(NodeConstant));
    }
}

void BuildTraceFromEntry(
    const UEdGraphNode* Entry,
    const TMap<const UEdGraphNode*, TArray<const UEdGraphNode*>>& ExecAdjacency,
    const int32 MaxDepth,
    TArray<TSharedPtr<FJsonValue>>& OutTraces)
{
    if (Entry == nullptr)
    {
        return;
    }

    const TArray<const UEdGraphNode*>* Neighbors = ExecAdjacency.Find(Entry);
    if (Neighbors == nullptr || Neighbors->Num() == 0)
    {
        return;
    }

    TSet<const UEdGraphNode*> Visited;
    const UEdGraphNode* Current = Entry;

    TSharedRef<FJsonObject> Trace = MakeShared<FJsonObject>();
    Trace->SetStringField(TEXT("entry_node"), Entry->GetName());
    Trace->SetStringField(TEXT("entry_title"), NodeLabel(Entry));

    TArray<TSharedPtr<FJsonValue>> Steps;
    int32 Depth = 0;

    while (Current != nullptr && Depth < MaxDepth)
    {
        TSharedRef<FJsonObject> Step = MakeShared<FJsonObject>();
        Step->SetNumberField(TEXT("step_index"), Depth);
        Step->SetStringField(TEXT("node_name"), Current->GetName());
        Step->SetStringField(TEXT("node_title"), NodeLabel(Current));
        Step->SetStringField(TEXT("node_class"), Current->GetClass()->GetPathName());
        Steps.Add(MakeShared<FJsonValueObject>(Step));

        Visited.Add(Current);
        const TArray<const UEdGraphNode*>* NextNodes = ExecAdjacency.Find(Current);
        if (NextNodes == nullptr || NextNodes->Num() == 0)
        {
            break;
        }

        const UEdGraphNode* Next = nullptr;
        for (const UEdGraphNode* Candidate : *NextNodes)
        {
            if (Candidate != nullptr && !Visited.Contains(Candidate))
            {
                Next = Candidate;
                break;
            }
        }

        if (Next == nullptr)
        {
            break;
        }

        Current = Next;
        ++Depth;
    }

    Trace->SetArrayField(TEXT("steps"), Steps);
    OutTraces.Add(MakeShared<FJsonValueObject>(Trace));
}
} // namespace

bool AnalyzeGraph(
    const UBlueprint* Blueprint,
    const UEdGraph* Graph,
    const FGraphAnalysisOptions& Options,
    TSharedRef<FJsonObject>& OutAnalysis,
    FString& OutError)
{
    if (Blueprint == nullptr || Graph == nullptr)
    {
        OutError = TEXT("Blueprint or graph is null.");
        return false;
    }

    const int32 MaxNodes = FMath::Clamp(Options.MaxNodes, 1, 2000);
    const int32 MaxTraceDepth = FMath::Clamp(Options.MaxTraceDepth, 1, 256);

    TArray<TSharedPtr<FJsonValue>> Nodes;
    TArray<TSharedPtr<FJsonValue>> EntryNodes;
    TArray<TSharedPtr<FJsonValue>> ExecEdges;
    TArray<TSharedPtr<FJsonValue>> DeadExecOutputs;
    TArray<TSharedPtr<FJsonValue>> BranchGuards;
    TArray<TSharedPtr<FJsonValue>> FunctionCalls;
    TArray<TSharedPtr<FJsonValue>> Delays;
    TArray<TSharedPtr<FJsonValue>> PrintStrings;
    TArray<TSharedPtr<FJsonValue>> EnumValues;
    TArray<TSharedPtr<FJsonValue>> Constants;
    TArray<TSharedPtr<FJsonValue>> Contradictions;

    TArray<const UEdGraphNode*> EntryNodeRefs;
    TMap<const UEdGraphNode*, TArray<const UEdGraphNode*>> ExecAdjacency;
    TSet<FString> SeenEdgeKeys;

    int32 Count = 0;
    for (const UEdGraphNode* Node : Graph->Nodes)
    {
        if (Node == nullptr)
        {
            continue;
        }

        if (Count >= MaxNodes)
        {
            break;
        }

        TSharedRef<FJsonObject> NodeObject = MakeShared<FJsonObject>();
        NodeObject->SetStringField(TEXT("name"), Node->GetName());
        NodeObject->SetStringField(TEXT("title"), NodeLabel(Node));
        NodeObject->SetStringField(TEXT("class"), Node->GetClass()->GetPathName());
        NodeObject->SetNumberField(TEXT("pos_x"), Node->NodePosX);
        NodeObject->SetNumberField(TEXT("pos_y"), Node->NodePosY);

        if (Options.bIncludePins)
        {
            TArray<TSharedPtr<FJsonValue>> Pins;
            for (const UEdGraphPin* Pin : Node->Pins)
            {
                if (Pin == nullptr)
                {
                    continue;
                }

                TSharedRef<FJsonObject> PinObj = MakeShared<FJsonObject>();
                PinObj->SetStringField(TEXT("name"), Pin->PinName.ToString());
                PinObj->SetStringField(TEXT("direction"), Pin->Direction == EGPD_Input ? TEXT("input") : TEXT("output"));
                PinObj->SetStringField(TEXT("category"), Pin->PinType.PinCategory.ToString());
                PinObj->SetNumberField(TEXT("links"), Pin->LinkedTo.Num());
                const FString PinDefault = SafePinDefault(Pin);
                if (!PinDefault.IsEmpty())
                {
                    PinObj->SetStringField(TEXT("default_value"), PinDefault);
                }

                TArray<TSharedPtr<FJsonValue>> LinkedRefs;
                for (const UEdGraphPin* Linked : Pin->LinkedTo)
                {
                    LinkedRefs.Add(MakeShared<FJsonValueObject>(BuildLinkedNodeRef(Linked)));
                }
                PinObj->SetArrayField(TEXT("linked_to"), LinkedRefs);
                Pins.Add(MakeShared<FJsonValueObject>(PinObj));
            }
            NodeObject->SetArrayField(TEXT("pins"), Pins);
        }

        Nodes.Add(MakeShared<FJsonValueObject>(NodeObject));
        ++Count;

        if (IsEntryNode(Node))
        {
            EntryNodeRefs.Add(Node);
            TSharedRef<FJsonObject> Entry = MakeShared<FJsonObject>();
            Entry->SetStringField(TEXT("node_name"), Node->GetName());
            Entry->SetStringField(TEXT("node_title"), NodeLabel(Node));
            Entry->SetStringField(TEXT("node_class"), Node->GetClass()->GetPathName());
            EntryNodes.Add(MakeShared<FJsonValueObject>(Entry));
        }

        for (const UEdGraphPin* OutExecPin : CollectExecPins(Node, EGPD_Output))
        {
            if (OutExecPin->LinkedTo.Num() == 0)
            {
                TSharedRef<FJsonObject> Dead = MakeShared<FJsonObject>();
                Dead->SetStringField(TEXT("node_name"), Node->GetName());
                Dead->SetStringField(TEXT("node_title"), NodeLabel(Node));
                Dead->SetStringField(TEXT("pin_name"), OutExecPin->PinName.ToString());
                DeadExecOutputs.Add(MakeShared<FJsonValueObject>(Dead));
            }

            for (const UEdGraphPin* LinkedPin : OutExecPin->LinkedTo)
            {
                if (LinkedPin == nullptr || LinkedPin->GetOwningNode() == nullptr)
                {
                    continue;
                }

                const UEdGraphNode* NextNode = LinkedPin->GetOwningNode();
                ExecAdjacency.FindOrAdd(Node).AddUnique(NextNode);

                const FString EdgeKey = FString::Printf(
                    TEXT("%s:%s->%s:%s"),
                    *Node->GetName(),
                    *OutExecPin->PinName.ToString(),
                    *NextNode->GetName(),
                    *LinkedPin->PinName.ToString());

                if (SeenEdgeKeys.Contains(EdgeKey))
                {
                    continue;
                }
                SeenEdgeKeys.Add(EdgeKey);

                TSharedRef<FJsonObject> Edge = MakeShared<FJsonObject>();
                Edge->SetStringField(TEXT("from_node"), Node->GetName());
                Edge->SetStringField(TEXT("from_title"), NodeLabel(Node));
                Edge->SetStringField(TEXT("from_pin"), OutExecPin->PinName.ToString());
                Edge->SetStringField(TEXT("to_node"), NextNode->GetName());
                Edge->SetStringField(TEXT("to_title"), NodeLabel(NextNode));
                Edge->SetStringField(TEXT("to_pin"), LinkedPin->PinName.ToString());
                ExecEdges.Add(MakeShared<FJsonValueObject>(Edge));
            }
        }

        if (IsBranchNode(Node))
        {
            const UEdGraphPin* CondPin = FindPinByName(Node, TEXT("Condition"));
            const UEdGraphPin* ThenPin = FindPinByName(Node, TEXT("Then"));
            const UEdGraphPin* ElsePin = FindPinByName(Node, TEXT("Else"));

            TSharedRef<FJsonObject> Branch = MakeShared<FJsonObject>();
            Branch->SetStringField(TEXT("node_name"), Node->GetName());
            Branch->SetStringField(TEXT("node_title"), NodeLabel(Node));

            TArray<TSharedPtr<FJsonValue>> ConditionSources;
            if (CondPin != nullptr)
            {
                Branch->SetStringField(TEXT("condition_default"), SafePinDefault(CondPin));
                for (const UEdGraphPin* Linked : CondPin->LinkedTo)
                {
                    ConditionSources.Add(MakeShared<FJsonValueObject>(BuildLinkedNodeRef(Linked)));
                }
            }
            Branch->SetArrayField(TEXT("condition_sources"), ConditionSources);
            Branch->SetNumberField(TEXT("then_links"), ThenPin != nullptr ? ThenPin->LinkedTo.Num() : 0);
            Branch->SetNumberField(TEXT("else_links"), ElsePin != nullptr ? ElsePin->LinkedTo.Num() : 0);
            BranchGuards.Add(MakeShared<FJsonValueObject>(Branch));
        }

        if (IsFunctionCallNode(Node))
        {
            const UEdGraphPin* SelfPin = FindPinByName(Node, TEXT("self"));
            const FString Title = NodeLabel(Node);

            TSharedRef<FJsonObject> Call = MakeShared<FJsonObject>();
            Call->SetStringField(TEXT("node_name"), Node->GetName());
            Call->SetStringField(TEXT("node_title"), Title);
            Call->SetStringField(TEXT("node_class"), Node->GetClass()->GetPathName());
            Call->SetStringField(TEXT("target"), (SelfPin != nullptr && SelfPin->LinkedTo.Num() > 0) ? TEXT("external") : TEXT("self"));
            Call->SetNumberField(TEXT("self_pin_links"), SelfPin != nullptr ? SelfPin->LinkedTo.Num() : 0);
            FunctionCalls.Add(MakeShared<FJsonValueObject>(Call));

            if (Title.Equals(TEXT("Print String"), ESearchCase::IgnoreCase))
            {
                const UEdGraphPin* InStringPin = FindPinByName(Node, TEXT("In String"));
                const UEdGraphPin* DurationPin = FindPinByName(Node, TEXT("Duration"));
                TSharedRef<FJsonObject> Print = MakeShared<FJsonObject>();
                Print->SetStringField(TEXT("node_name"), Node->GetName());
                Print->SetStringField(TEXT("message"), InStringPin != nullptr ? SafePinDefault(InStringPin) : TEXT(""));
                Print->SetStringField(TEXT("duration"), DurationPin != nullptr ? SafePinDefault(DurationPin) : TEXT(""));
                PrintStrings.Add(MakeShared<FJsonValueObject>(Print));
            }

            if (Title.Equals(TEXT("Delay"), ESearchCase::IgnoreCase))
            {
                const UEdGraphPin* DurationPin = FindPinByName(Node, TEXT("Duration"));
                TSharedRef<FJsonObject> Delay = MakeShared<FJsonObject>();
                Delay->SetStringField(TEXT("node_name"), Node->GetName());
                Delay->SetStringField(TEXT("duration"), DurationPin != nullptr ? SafePinDefault(DurationPin) : TEXT(""));
                Delays.Add(MakeShared<FJsonValueObject>(Delay));
            }
        }

        if (IsEnumNode(Node))
        {
            TArray<TSharedPtr<FJsonValue>> PinDefaults;
            for (const UEdGraphPin* Pin : Node->Pins)
            {
                if (Pin == nullptr)
                {
                    continue;
                }

                const FString DefaultText = SafePinDefault(Pin);
                if (DefaultText.IsEmpty())
                {
                    continue;
                }

                TSharedRef<FJsonObject> EnumPin = MakeShared<FJsonObject>();
                EnumPin->SetStringField(TEXT("pin_name"), Pin->PinName.ToString());
                EnumPin->SetStringField(TEXT("default_value"), DefaultText);
                EnumPin->SetStringField(TEXT("category"), Pin->PinType.PinCategory.ToString());
                PinDefaults.Add(MakeShared<FJsonValueObject>(EnumPin));
            }

            if (PinDefaults.Num() > 0)
            {
                TSharedRef<FJsonObject> Enum = MakeShared<FJsonObject>();
                Enum->SetStringField(TEXT("node_name"), Node->GetName());
                Enum->SetStringField(TEXT("node_title"), NodeLabel(Node));
                Enum->SetArrayField(TEXT("pin_defaults"), PinDefaults);
                EnumValues.Add(MakeShared<FJsonValueObject>(Enum));
            }
        }

        CollectNodeConstants(Node, Constants);
    }

    // Contradiction check: dead exec pin must not appear as an exec edge source pin.
    TSet<FString> EdgeSourcePins;
    for (const TSharedPtr<FJsonValue>& EdgeValue : ExecEdges)
    {
        const TSharedPtr<FJsonObject>* EdgeObj = nullptr;
        if (!EdgeValue.IsValid() || !EdgeValue->TryGetObject(EdgeObj) || !EdgeObj || !EdgeObj->IsValid())
        {
            continue;
        }

        FString FromNode;
        FString FromPin;
        (*EdgeObj)->TryGetStringField(TEXT("from_node"), FromNode);
        (*EdgeObj)->TryGetStringField(TEXT("from_pin"), FromPin);
        if (!FromNode.IsEmpty() && !FromPin.IsEmpty())
        {
            EdgeSourcePins.Add(FromNode + TEXT(":") + FromPin);
        }
    }

    for (const TSharedPtr<FJsonValue>& DeadValue : DeadExecOutputs)
    {
        const TSharedPtr<FJsonObject>* DeadObj = nullptr;
        if (!DeadValue.IsValid() || !DeadValue->TryGetObject(DeadObj) || !DeadObj || !DeadObj->IsValid())
        {
            continue;
        }

        FString NodeName;
        FString PinName;
        (*DeadObj)->TryGetStringField(TEXT("node_name"), NodeName);
        (*DeadObj)->TryGetStringField(TEXT("pin_name"), PinName);
        if (EdgeSourcePins.Contains(NodeName + TEXT(":") + PinName))
        {
            TSharedRef<FJsonObject> Contradiction = MakeShared<FJsonObject>();
            Contradiction->SetStringField(TEXT("type"), TEXT("dead_exec_pin_has_outgoing_edge"));
            Contradiction->SetStringField(TEXT("node_name"), NodeName);
            Contradiction->SetStringField(TEXT("pin_name"), PinName);
            Contradictions.Add(MakeShared<FJsonValueObject>(Contradiction));
        }
    }

    TArray<TSharedPtr<FJsonValue>> PathTraces;
    for (const UEdGraphNode* Entry : EntryNodeRefs)
    {
        BuildTraceFromEntry(Entry, ExecAdjacency, MaxTraceDepth, PathTraces);
    }

    OutAnalysis->SetStringField(TEXT("blueprint"), Blueprint->GetPathName());
    OutAnalysis->SetStringField(TEXT("graph_name"), Graph->GetName());
    OutAnalysis->SetNumberField(TEXT("total_nodes"), Graph->Nodes.Num());
    OutAnalysis->SetNumberField(TEXT("returned_nodes"), Nodes.Num());
    OutAnalysis->SetBoolField(TEXT("truncated"), Graph->Nodes.Num() > Nodes.Num());
    OutAnalysis->SetArrayField(TEXT("nodes"), Nodes);
    OutAnalysis->SetArrayField(TEXT("entry_nodes"), EntryNodes);
    OutAnalysis->SetArrayField(TEXT("exec_edges"), ExecEdges);
    OutAnalysis->SetArrayField(TEXT("path_traces"), PathTraces);
    OutAnalysis->SetArrayField(TEXT("dead_exec_outputs"), DeadExecOutputs);
    OutAnalysis->SetArrayField(TEXT("branch_guards"), BranchGuards);
    OutAnalysis->SetArrayField(TEXT("function_calls"), FunctionCalls);
    OutAnalysis->SetArrayField(TEXT("delays"), Delays);
    OutAnalysis->SetArrayField(TEXT("print_strings"), PrintStrings);
    OutAnalysis->SetArrayField(TEXT("enum_values"), EnumValues);
    OutAnalysis->SetArrayField(TEXT("constants"), Constants);
    OutAnalysis->SetArrayField(TEXT("contradictions"), Contradictions);
    OutAnalysis->SetBoolField(TEXT("analysis_ok"), Contradictions.Num() == 0);

    return true;
}

void AppendPinSnapshot(const UEdGraph* Graph, TArray<TSharedPtr<FJsonValue>>& OutPins)
{
    if (Graph == nullptr)
    {
        return;
    }

    for (const UEdGraphNode* Node : Graph->Nodes)
    {
        if (Node == nullptr)
        {
            continue;
        }

        for (const UEdGraphPin* Pin : Node->Pins)
        {
            if (Pin == nullptr)
            {
                continue;
            }

            TSharedRef<FJsonObject> PinObj = MakeShared<FJsonObject>();
            PinObj->SetStringField(TEXT("node_name"), Node->GetName());
            PinObj->SetStringField(TEXT("node_title"), NodeLabel(Node));
            PinObj->SetStringField(TEXT("pin_name"), Pin->PinName.ToString());
            PinObj->SetStringField(TEXT("direction"), Pin->Direction == EGPD_Input ? TEXT("input") : TEXT("output"));
            PinObj->SetStringField(TEXT("category"), Pin->PinType.PinCategory.ToString());
            PinObj->SetNumberField(TEXT("links"), Pin->LinkedTo.Num());
            const FString DefaultText = SafePinDefault(Pin);
            if (!DefaultText.IsEmpty())
            {
                PinObj->SetStringField(TEXT("default_value"), DefaultText);
            }
            OutPins.Add(MakeShared<FJsonValueObject>(PinObj));
        }
    }
}
} // namespace UnrealAgentPrivate
