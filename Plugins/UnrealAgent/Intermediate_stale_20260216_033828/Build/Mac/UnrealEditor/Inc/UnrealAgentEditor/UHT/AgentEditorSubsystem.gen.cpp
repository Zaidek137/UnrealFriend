// Copyright Epic Games, Inc. All Rights Reserved.
/*===========================================================================
	Generated code exported from UnrealHeaderTool.
	DO NOT modify this manually! Edit the corresponding .h files instead!
===========================================================================*/

#include "UObject/GeneratedCppIncludes.h"
#include "Agent/AgentEditorSubsystem.h"

PRAGMA_DISABLE_DEPRECATION_WARNINGS
static_assert(!UE_WITH_CONSTINIT_UOBJECT, "This generated code can only be compiled with !UE_WITH_CONSTINIT_OBJECT");
void EmptyLinkFunctionForGeneratedCodeAgentEditorSubsystem() {}

// ********** Begin Cross Module References ********************************************************
EDITORSUBSYSTEM_API UClass* Z_Construct_UClass_UEditorSubsystem();
UNREALAGENTEDITOR_API UClass* Z_Construct_UClass_UAgentEditorSubsystem();
UNREALAGENTEDITOR_API UClass* Z_Construct_UClass_UAgentEditorSubsystem_NoRegister();
UPackage* Z_Construct_UPackage__Script_UnrealAgentEditor();
// ********** End Cross Module References **********************************************************

// ********** Begin Class UAgentEditorSubsystem Function ExecuteAction *****************************
struct Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics
{
	struct AgentEditorSubsystem_eventExecuteAction_Parms
	{
		FString ActionName;
		FString PayloadJson;
		bool bDryRun;
		FString ReturnValue;
	};
#if WITH_METADATA
	static constexpr UECodeGen_Private::FMetaDataPairParam Function_MetaDataParams[] = {
		{ "Category", "UnrealAgent" },
		{ "CPP_Default_bDryRun", "false" },
		{ "ModuleRelativePath", "Public/Agent/AgentEditorSubsystem.h" },
	};
	static constexpr UECodeGen_Private::FMetaDataPairParam NewProp_ActionName_MetaData[] = {
		{ "NativeConst", "" },
	};
	static constexpr UECodeGen_Private::FMetaDataPairParam NewProp_PayloadJson_MetaData[] = {
		{ "NativeConst", "" },
	};
#endif // WITH_METADATA

// ********** Begin Function ExecuteAction constinit property declarations *************************
	static const UECodeGen_Private::FStrPropertyParams NewProp_ActionName;
	static const UECodeGen_Private::FStrPropertyParams NewProp_PayloadJson;
	static void NewProp_bDryRun_SetBit(void* Obj);
	static const UECodeGen_Private::FBoolPropertyParams NewProp_bDryRun;
	static const UECodeGen_Private::FStrPropertyParams NewProp_ReturnValue;
	static const UECodeGen_Private::FPropertyParamsBase* const PropPointers[];
// ********** End Function ExecuteAction constinit property declarations ***************************
	static const UECodeGen_Private::FFunctionParams FuncParams;
};

// ********** Begin Function ExecuteAction Property Definitions ************************************
const UECodeGen_Private::FStrPropertyParams Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::NewProp_ActionName = { "ActionName", nullptr, (EPropertyFlags)0x0010000000000080, UECodeGen_Private::EPropertyGenFlags::Str, RF_Public|RF_Transient|RF_MarkAsNative, nullptr, nullptr, 1, STRUCT_OFFSET(AgentEditorSubsystem_eventExecuteAction_Parms, ActionName), METADATA_PARAMS(UE_ARRAY_COUNT(NewProp_ActionName_MetaData), NewProp_ActionName_MetaData) };
const UECodeGen_Private::FStrPropertyParams Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::NewProp_PayloadJson = { "PayloadJson", nullptr, (EPropertyFlags)0x0010000000000080, UECodeGen_Private::EPropertyGenFlags::Str, RF_Public|RF_Transient|RF_MarkAsNative, nullptr, nullptr, 1, STRUCT_OFFSET(AgentEditorSubsystem_eventExecuteAction_Parms, PayloadJson), METADATA_PARAMS(UE_ARRAY_COUNT(NewProp_PayloadJson_MetaData), NewProp_PayloadJson_MetaData) };
void Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::NewProp_bDryRun_SetBit(void* Obj)
{
	((AgentEditorSubsystem_eventExecuteAction_Parms*)Obj)->bDryRun = 1;
}
const UECodeGen_Private::FBoolPropertyParams Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::NewProp_bDryRun = { "bDryRun", nullptr, (EPropertyFlags)0x0010000000000080, UECodeGen_Private::EPropertyGenFlags::Bool | UECodeGen_Private::EPropertyGenFlags::NativeBool, RF_Public|RF_Transient|RF_MarkAsNative, nullptr, nullptr, 1, sizeof(bool), sizeof(AgentEditorSubsystem_eventExecuteAction_Parms), &Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::NewProp_bDryRun_SetBit, METADATA_PARAMS(0, nullptr) };
const UECodeGen_Private::FStrPropertyParams Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::NewProp_ReturnValue = { "ReturnValue", nullptr, (EPropertyFlags)0x0010000000000580, UECodeGen_Private::EPropertyGenFlags::Str, RF_Public|RF_Transient|RF_MarkAsNative, nullptr, nullptr, 1, STRUCT_OFFSET(AgentEditorSubsystem_eventExecuteAction_Parms, ReturnValue), METADATA_PARAMS(0, nullptr) };
const UECodeGen_Private::FPropertyParamsBase* const Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::PropPointers[] = {
	(const UECodeGen_Private::FPropertyParamsBase*)&Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::NewProp_ActionName,
	(const UECodeGen_Private::FPropertyParamsBase*)&Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::NewProp_PayloadJson,
	(const UECodeGen_Private::FPropertyParamsBase*)&Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::NewProp_bDryRun,
	(const UECodeGen_Private::FPropertyParamsBase*)&Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::NewProp_ReturnValue,
};
static_assert(UE_ARRAY_COUNT(Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::PropPointers) < 2048);
// ********** End Function ExecuteAction Property Definitions **************************************
const UECodeGen_Private::FFunctionParams Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::FuncParams = { { (UObject*(*)())Z_Construct_UClass_UAgentEditorSubsystem, nullptr, "ExecuteAction", 	Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::PropPointers, 
	UE_ARRAY_COUNT(Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::PropPointers), 
sizeof(Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::AgentEditorSubsystem_eventExecuteAction_Parms),
RF_Public|RF_Transient|RF_MarkAsNative, (EFunctionFlags)0x04020401, 0, 0, METADATA_PARAMS(UE_ARRAY_COUNT(Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::Function_MetaDataParams), Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::Function_MetaDataParams)},  };
static_assert(sizeof(Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::AgentEditorSubsystem_eventExecuteAction_Parms) < MAX_uint16);
UFunction* Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction()
{
	static UFunction* ReturnFunction = nullptr;
	if (!ReturnFunction)
	{
		UECodeGen_Private::ConstructUFunction(&ReturnFunction, Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction_Statics::FuncParams);
	}
	return ReturnFunction;
}
DEFINE_FUNCTION(UAgentEditorSubsystem::execExecuteAction)
{
	P_GET_PROPERTY(FStrProperty,Z_Param_ActionName);
	P_GET_PROPERTY(FStrProperty,Z_Param_PayloadJson);
	P_GET_UBOOL(Z_Param_bDryRun);
	P_FINISH;
	P_NATIVE_BEGIN;
	*(FString*)Z_Param__Result=P_THIS->ExecuteAction(Z_Param_ActionName,Z_Param_PayloadJson,Z_Param_bDryRun);
	P_NATIVE_END;
}
// ********** End Class UAgentEditorSubsystem Function ExecuteAction *******************************

// ********** Begin Class UAgentEditorSubsystem Function ListActions *******************************
struct Z_Construct_UFunction_UAgentEditorSubsystem_ListActions_Statics
{
	struct AgentEditorSubsystem_eventListActions_Parms
	{
		TArray<FString> ReturnValue;
	};
#if WITH_METADATA
	static constexpr UECodeGen_Private::FMetaDataPairParam Function_MetaDataParams[] = {
		{ "Category", "UnrealAgent" },
		{ "ModuleRelativePath", "Public/Agent/AgentEditorSubsystem.h" },
	};
#endif // WITH_METADATA

// ********** Begin Function ListActions constinit property declarations ***************************
	static const UECodeGen_Private::FStrPropertyParams NewProp_ReturnValue_Inner;
	static const UECodeGen_Private::FArrayPropertyParams NewProp_ReturnValue;
	static const UECodeGen_Private::FPropertyParamsBase* const PropPointers[];
// ********** End Function ListActions constinit property declarations *****************************
	static const UECodeGen_Private::FFunctionParams FuncParams;
};

// ********** Begin Function ListActions Property Definitions **************************************
const UECodeGen_Private::FStrPropertyParams Z_Construct_UFunction_UAgentEditorSubsystem_ListActions_Statics::NewProp_ReturnValue_Inner = { "ReturnValue", nullptr, (EPropertyFlags)0x0000000000000000, UECodeGen_Private::EPropertyGenFlags::Str, RF_Public|RF_Transient|RF_MarkAsNative, nullptr, nullptr, 1, 0, METADATA_PARAMS(0, nullptr) };
const UECodeGen_Private::FArrayPropertyParams Z_Construct_UFunction_UAgentEditorSubsystem_ListActions_Statics::NewProp_ReturnValue = { "ReturnValue", nullptr, (EPropertyFlags)0x0010000000000580, UECodeGen_Private::EPropertyGenFlags::Array, RF_Public|RF_Transient|RF_MarkAsNative, nullptr, nullptr, 1, STRUCT_OFFSET(AgentEditorSubsystem_eventListActions_Parms, ReturnValue), EArrayPropertyFlags::None, METADATA_PARAMS(0, nullptr) };
const UECodeGen_Private::FPropertyParamsBase* const Z_Construct_UFunction_UAgentEditorSubsystem_ListActions_Statics::PropPointers[] = {
	(const UECodeGen_Private::FPropertyParamsBase*)&Z_Construct_UFunction_UAgentEditorSubsystem_ListActions_Statics::NewProp_ReturnValue_Inner,
	(const UECodeGen_Private::FPropertyParamsBase*)&Z_Construct_UFunction_UAgentEditorSubsystem_ListActions_Statics::NewProp_ReturnValue,
};
static_assert(UE_ARRAY_COUNT(Z_Construct_UFunction_UAgentEditorSubsystem_ListActions_Statics::PropPointers) < 2048);
// ********** End Function ListActions Property Definitions ****************************************
const UECodeGen_Private::FFunctionParams Z_Construct_UFunction_UAgentEditorSubsystem_ListActions_Statics::FuncParams = { { (UObject*(*)())Z_Construct_UClass_UAgentEditorSubsystem, nullptr, "ListActions", 	Z_Construct_UFunction_UAgentEditorSubsystem_ListActions_Statics::PropPointers, 
	UE_ARRAY_COUNT(Z_Construct_UFunction_UAgentEditorSubsystem_ListActions_Statics::PropPointers), 
sizeof(Z_Construct_UFunction_UAgentEditorSubsystem_ListActions_Statics::AgentEditorSubsystem_eventListActions_Parms),
RF_Public|RF_Transient|RF_MarkAsNative, (EFunctionFlags)0x54020401, 0, 0, METADATA_PARAMS(UE_ARRAY_COUNT(Z_Construct_UFunction_UAgentEditorSubsystem_ListActions_Statics::Function_MetaDataParams), Z_Construct_UFunction_UAgentEditorSubsystem_ListActions_Statics::Function_MetaDataParams)},  };
static_assert(sizeof(Z_Construct_UFunction_UAgentEditorSubsystem_ListActions_Statics::AgentEditorSubsystem_eventListActions_Parms) < MAX_uint16);
UFunction* Z_Construct_UFunction_UAgentEditorSubsystem_ListActions()
{
	static UFunction* ReturnFunction = nullptr;
	if (!ReturnFunction)
	{
		UECodeGen_Private::ConstructUFunction(&ReturnFunction, Z_Construct_UFunction_UAgentEditorSubsystem_ListActions_Statics::FuncParams);
	}
	return ReturnFunction;
}
DEFINE_FUNCTION(UAgentEditorSubsystem::execListActions)
{
	P_FINISH;
	P_NATIVE_BEGIN;
	*(TArray<FString>*)Z_Param__Result=P_THIS->ListActions();
	P_NATIVE_END;
}
// ********** End Class UAgentEditorSubsystem Function ListActions *********************************

// ********** Begin Class UAgentEditorSubsystem ****************************************************
FClassRegistrationInfo Z_Registration_Info_UClass_UAgentEditorSubsystem;
UClass* UAgentEditorSubsystem::GetPrivateStaticClass()
{
	using TClass = UAgentEditorSubsystem;
	if (!Z_Registration_Info_UClass_UAgentEditorSubsystem.InnerSingleton)
	{
		GetPrivateStaticClassBody(
			TClass::StaticPackage(),
			TEXT("AgentEditorSubsystem"),
			Z_Registration_Info_UClass_UAgentEditorSubsystem.InnerSingleton,
			StaticRegisterNativesUAgentEditorSubsystem,
			sizeof(TClass),
			alignof(TClass),
			TClass::StaticClassFlags,
			TClass::StaticClassCastFlags(),
			TClass::StaticConfigName(),
			(UClass::ClassConstructorType)InternalConstructor<TClass>,
			(UClass::ClassVTableHelperCtorCallerType)InternalVTableHelperCtorCaller<TClass>,
			UOBJECT_CPPCLASS_STATICFUNCTIONS_FORCLASS(TClass),
			&TClass::Super::StaticClass,
			&TClass::WithinClass::StaticClass
		);
	}
	return Z_Registration_Info_UClass_UAgentEditorSubsystem.InnerSingleton;
}
UClass* Z_Construct_UClass_UAgentEditorSubsystem_NoRegister()
{
	return UAgentEditorSubsystem::GetPrivateStaticClass();
}
struct Z_Construct_UClass_UAgentEditorSubsystem_Statics
{
#if WITH_METADATA
	static constexpr UECodeGen_Private::FMetaDataPairParam Class_MetaDataParams[] = {
		{ "IncludePath", "Agent/AgentEditorSubsystem.h" },
		{ "ModuleRelativePath", "Public/Agent/AgentEditorSubsystem.h" },
	};
#endif // WITH_METADATA

// ********** Begin Class UAgentEditorSubsystem constinit property declarations ********************
// ********** End Class UAgentEditorSubsystem constinit property declarations **********************
	static constexpr UE::CodeGen::FClassNativeFunction Funcs[] = {
		{ .NameUTF8 = UTF8TEXT("ExecuteAction"), .Pointer = &UAgentEditorSubsystem::execExecuteAction },
		{ .NameUTF8 = UTF8TEXT("ListActions"), .Pointer = &UAgentEditorSubsystem::execListActions },
	};
	static UObject* (*const DependentSingletons[])();
	static constexpr FClassFunctionLinkInfo FuncInfo[] = {
		{ &Z_Construct_UFunction_UAgentEditorSubsystem_ExecuteAction, "ExecuteAction" }, // 1792322861
		{ &Z_Construct_UFunction_UAgentEditorSubsystem_ListActions, "ListActions" }, // 3394090427
	};
	static_assert(UE_ARRAY_COUNT(FuncInfo) < 2048);
	static constexpr FCppClassTypeInfoStatic StaticCppClassTypeInfo = {
		TCppClassTypeTraits<UAgentEditorSubsystem>::IsAbstract,
	};
	static const UECodeGen_Private::FClassParams ClassParams;
}; // struct Z_Construct_UClass_UAgentEditorSubsystem_Statics
UObject* (*const Z_Construct_UClass_UAgentEditorSubsystem_Statics::DependentSingletons[])() = {
	(UObject* (*)())Z_Construct_UClass_UEditorSubsystem,
	(UObject* (*)())Z_Construct_UPackage__Script_UnrealAgentEditor,
};
static_assert(UE_ARRAY_COUNT(Z_Construct_UClass_UAgentEditorSubsystem_Statics::DependentSingletons) < 16);
const UECodeGen_Private::FClassParams Z_Construct_UClass_UAgentEditorSubsystem_Statics::ClassParams = {
	&UAgentEditorSubsystem::StaticClass,
	nullptr,
	&StaticCppClassTypeInfo,
	DependentSingletons,
	FuncInfo,
	nullptr,
	nullptr,
	UE_ARRAY_COUNT(DependentSingletons),
	UE_ARRAY_COUNT(FuncInfo),
	0,
	0,
	0x001000A0u,
	METADATA_PARAMS(UE_ARRAY_COUNT(Z_Construct_UClass_UAgentEditorSubsystem_Statics::Class_MetaDataParams), Z_Construct_UClass_UAgentEditorSubsystem_Statics::Class_MetaDataParams)
};
void UAgentEditorSubsystem::StaticRegisterNativesUAgentEditorSubsystem()
{
	UClass* Class = UAgentEditorSubsystem::StaticClass();
	FNativeFunctionRegistrar::RegisterFunctions(Class, MakeConstArrayView(Z_Construct_UClass_UAgentEditorSubsystem_Statics::Funcs));
}
UClass* Z_Construct_UClass_UAgentEditorSubsystem()
{
	if (!Z_Registration_Info_UClass_UAgentEditorSubsystem.OuterSingleton)
	{
		UECodeGen_Private::ConstructUClass(Z_Registration_Info_UClass_UAgentEditorSubsystem.OuterSingleton, Z_Construct_UClass_UAgentEditorSubsystem_Statics::ClassParams);
	}
	return Z_Registration_Info_UClass_UAgentEditorSubsystem.OuterSingleton;
}
UAgentEditorSubsystem::UAgentEditorSubsystem() {}
DEFINE_VTABLE_PTR_HELPER_CTOR_NS(, UAgentEditorSubsystem);
UAgentEditorSubsystem::~UAgentEditorSubsystem() {}
// ********** End Class UAgentEditorSubsystem ******************************************************

// ********** Begin Registration *******************************************************************
struct Z_CompiledInDeferFile_FID_ericdiaz_Desktop_Unreal_Friend_Plugins_UnrealAgent_Source_UnrealAgentEditor_Public_Agent_AgentEditorSubsystem_h__Script_UnrealAgentEditor_Statics
{
	static constexpr FClassRegisterCompiledInInfo ClassInfo[] = {
		{ Z_Construct_UClass_UAgentEditorSubsystem, UAgentEditorSubsystem::StaticClass, TEXT("UAgentEditorSubsystem"), &Z_Registration_Info_UClass_UAgentEditorSubsystem, CONSTRUCT_RELOAD_VERSION_INFO(FClassReloadVersionInfo, sizeof(UAgentEditorSubsystem), 3695436483U) },
	};
}; // Z_CompiledInDeferFile_FID_ericdiaz_Desktop_Unreal_Friend_Plugins_UnrealAgent_Source_UnrealAgentEditor_Public_Agent_AgentEditorSubsystem_h__Script_UnrealAgentEditor_Statics 
static FRegisterCompiledInInfo Z_CompiledInDeferFile_FID_ericdiaz_Desktop_Unreal_Friend_Plugins_UnrealAgent_Source_UnrealAgentEditor_Public_Agent_AgentEditorSubsystem_h__Script_UnrealAgentEditor_267986672{
	TEXT("/Script/UnrealAgentEditor"),
	Z_CompiledInDeferFile_FID_ericdiaz_Desktop_Unreal_Friend_Plugins_UnrealAgent_Source_UnrealAgentEditor_Public_Agent_AgentEditorSubsystem_h__Script_UnrealAgentEditor_Statics::ClassInfo, UE_ARRAY_COUNT(Z_CompiledInDeferFile_FID_ericdiaz_Desktop_Unreal_Friend_Plugins_UnrealAgent_Source_UnrealAgentEditor_Public_Agent_AgentEditorSubsystem_h__Script_UnrealAgentEditor_Statics::ClassInfo),
	nullptr, 0,
	nullptr, 0,
};
// ********** End Registration *********************************************************************

PRAGMA_ENABLE_DEPRECATION_WARNINGS
