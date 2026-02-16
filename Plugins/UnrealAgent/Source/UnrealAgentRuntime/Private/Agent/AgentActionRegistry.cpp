#include "Agent/AgentActionRegistry.h"

#include "Misc/ScopeLock.h"

FAgentActionRegistry& FAgentActionRegistry::Get()
{
    static FAgentActionRegistry Instance;
    return Instance;
}

void FAgentActionRegistry::RegisterAction(TSharedRef<IAgentAction> Action)
{
    const FString Name = Action->GetName();
    if (Name.IsEmpty())
    {
        return;
    }

    FScopeLock Lock(&Mutex);
    Actions.Add(Name, Action);
}

void FAgentActionRegistry::UnregisterAction(const FString& ActionName)
{
    FScopeLock Lock(&Mutex);
    Actions.Remove(ActionName);
}

bool FAgentActionRegistry::HasAction(const FString& ActionName) const
{
    FScopeLock Lock(&Mutex);
    return Actions.Contains(ActionName);
}

TArray<FString> FAgentActionRegistry::GetActionNames() const
{
    FScopeLock Lock(&Mutex);
    TArray<FString> Names;
    Actions.GetKeys(Names);
    Names.Sort();
    return Names;
}

TArray<FAgentActionDescriptor> FAgentActionRegistry::GetActionDescriptors() const
{
    FScopeLock Lock(&Mutex);

    TArray<FAgentActionDescriptor> Descriptors;
    Descriptors.Reserve(Actions.Num());
    for (const TPair<FString, TSharedRef<IAgentAction>>& Pair : Actions)
    {
        FAgentActionDescriptor Descriptor;
        Descriptor.Name = Pair.Key;
        Descriptor.Description = Pair.Value->GetDescription();
        Descriptors.Add(MoveTemp(Descriptor));
    }

    Descriptors.Sort(
        [](const FAgentActionDescriptor& Left, const FAgentActionDescriptor& Right)
        {
            return Left.Name < Right.Name;
        }
    );
    return Descriptors;
}

FAgentActionResult FAgentActionRegistry::Execute(const FAgentActionRequest& Request) const
{
    TSharedPtr<IAgentAction> Action;
    {
        FScopeLock Lock(&Mutex);
        const TSharedRef<IAgentAction>* Found = Actions.Find(Request.ActionName);
        if (Found == nullptr)
        {
            return {
                false,
                FString::Printf(TEXT("Unknown action: %s"), *Request.ActionName),
                TEXT(""),
                TEXT("UNKNOWN_ACTION")
            };
        }
        Action = *Found;
    }

    return Action->Execute(Request);
}
