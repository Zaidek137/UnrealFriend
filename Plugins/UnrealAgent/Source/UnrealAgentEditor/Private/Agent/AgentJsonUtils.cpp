#include "Agent/AgentJsonUtils.h"

#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

bool UnrealAgentPrivate::ParseJsonObject(const FString& JsonString, TSharedPtr<FJsonObject>& OutObject, FString& OutError)
{
    OutObject.Reset();
    OutError.Reset();

    const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonString);
    if (!FJsonSerializer::Deserialize(Reader, OutObject) || !OutObject.IsValid())
    {
        OutError = TEXT("Invalid JSON object payload.");
        return false;
    }

    return true;
}

FString UnrealAgentPrivate::NormalizeErrorCode(const FAgentActionResult& Result)
{
    if (!Result.ErrorCode.IsEmpty())
    {
        return Result.ErrorCode;
    }

    if (Result.bSuccess)
    {
        return TEXT("OK");
    }

    const FString MessageLower = Result.Message.ToLower();
    if (MessageLower.Contains(TEXT("invalid json")) || MessageLower.Contains(TEXT("payload")))
    {
        return TEXT("INVALID_PAYLOAD");
    }
    if (MessageLower.Contains(TEXT("missing required")))
    {
        return TEXT("MISSING_FIELD");
    }
    if (MessageLower.Contains(TEXT("failed to load")))
    {
        return TEXT("ASSET_LOAD_FAILED");
    }
    if (MessageLower.Contains(TEXT("compile")))
    {
        return TEXT("COMPILE_FAILED");
    }
    if (MessageLower.Contains(TEXT("unknown action")))
    {
        return TEXT("UNKNOWN_ACTION");
    }
    return TEXT("ACTION_FAILED");
}

FString UnrealAgentPrivate::SerializePayload(const TSharedRef<FJsonObject>& Payload)
{
    FString Serialized;
    const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Serialized);
    FJsonSerializer::Serialize(Payload, Writer);
    return Serialized;
}

FString UnrealAgentPrivate::SerializeActionResult(const FAgentActionResult& Result)
{
    TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
    Root->SetBoolField(TEXT("success"), Result.bSuccess);
    Root->SetStringField(TEXT("message"), Result.Message);
    Root->SetStringField(TEXT("error_code"), NormalizeErrorCode(Result));

    if (!Result.PayloadJson.IsEmpty())
    {
        TSharedPtr<FJsonObject> Payload;
        FString ParseError;
        if (ParseJsonObject(Result.PayloadJson, Payload, ParseError) && Payload.IsValid())
        {
            Root->SetObjectField(TEXT("payload"), Payload.ToSharedRef());
        }
        else
        {
            Root->SetStringField(TEXT("payload_raw"), Result.PayloadJson);
        }
    }

    return SerializePayload(Root);
}
