// Copyright Epic Games, Inc. All Rights Reserved.
/*===========================================================================
	Generated code exported from UnrealHeaderTool.
	DO NOT modify this manually! Edit the corresponding .h files instead!
===========================================================================*/

#include "UObject/GeneratedCppIncludes.h"
#include "Agent/AgentHttpBridgeSubsystem.h"

PRAGMA_DISABLE_DEPRECATION_WARNINGS
static_assert(!UE_WITH_CONSTINIT_UOBJECT, "This generated code can only be compiled with !UE_WITH_CONSTINIT_OBJECT");
void EmptyLinkFunctionForGeneratedCodeAgentHttpBridgeSubsystem() {}

// ********** Begin Cross Module References ********************************************************
EDITORSUBSYSTEM_API UClass* Z_Construct_UClass_UEditorSubsystem();
UNREALAGENTEDITOR_API UClass* Z_Construct_UClass_UAgentHttpBridgeSubsystem();
UNREALAGENTEDITOR_API UClass* Z_Construct_UClass_UAgentHttpBridgeSubsystem_NoRegister();
UPackage* Z_Construct_UPackage__Script_UnrealAgentEditor();
// ********** End Cross Module References **********************************************************

// ********** Begin Class UAgentHttpBridgeSubsystem ************************************************
FClassRegistrationInfo Z_Registration_Info_UClass_UAgentHttpBridgeSubsystem;
UClass* UAgentHttpBridgeSubsystem::GetPrivateStaticClass()
{
	using TClass = UAgentHttpBridgeSubsystem;
	if (!Z_Registration_Info_UClass_UAgentHttpBridgeSubsystem.InnerSingleton)
	{
		GetPrivateStaticClassBody(
			TClass::StaticPackage(),
			TEXT("AgentHttpBridgeSubsystem"),
			Z_Registration_Info_UClass_UAgentHttpBridgeSubsystem.InnerSingleton,
			StaticRegisterNativesUAgentHttpBridgeSubsystem,
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
	return Z_Registration_Info_UClass_UAgentHttpBridgeSubsystem.InnerSingleton;
}
UClass* Z_Construct_UClass_UAgentHttpBridgeSubsystem_NoRegister()
{
	return UAgentHttpBridgeSubsystem::GetPrivateStaticClass();
}
struct Z_Construct_UClass_UAgentHttpBridgeSubsystem_Statics
{
#if WITH_METADATA
	static constexpr UECodeGen_Private::FMetaDataPairParam Class_MetaDataParams[] = {
		{ "IncludePath", "Agent/AgentHttpBridgeSubsystem.h" },
		{ "ModuleRelativePath", "Public/Agent/AgentHttpBridgeSubsystem.h" },
	};
#endif // WITH_METADATA

// ********** Begin Class UAgentHttpBridgeSubsystem constinit property declarations ****************
// ********** End Class UAgentHttpBridgeSubsystem constinit property declarations ******************
	static UObject* (*const DependentSingletons[])();
	static constexpr FCppClassTypeInfoStatic StaticCppClassTypeInfo = {
		TCppClassTypeTraits<UAgentHttpBridgeSubsystem>::IsAbstract,
	};
	static const UECodeGen_Private::FClassParams ClassParams;
}; // struct Z_Construct_UClass_UAgentHttpBridgeSubsystem_Statics
UObject* (*const Z_Construct_UClass_UAgentHttpBridgeSubsystem_Statics::DependentSingletons[])() = {
	(UObject* (*)())Z_Construct_UClass_UEditorSubsystem,
	(UObject* (*)())Z_Construct_UPackage__Script_UnrealAgentEditor,
};
static_assert(UE_ARRAY_COUNT(Z_Construct_UClass_UAgentHttpBridgeSubsystem_Statics::DependentSingletons) < 16);
const UECodeGen_Private::FClassParams Z_Construct_UClass_UAgentHttpBridgeSubsystem_Statics::ClassParams = {
	&UAgentHttpBridgeSubsystem::StaticClass,
	nullptr,
	&StaticCppClassTypeInfo,
	DependentSingletons,
	nullptr,
	nullptr,
	nullptr,
	UE_ARRAY_COUNT(DependentSingletons),
	0,
	0,
	0,
	0x001000A0u,
	METADATA_PARAMS(UE_ARRAY_COUNT(Z_Construct_UClass_UAgentHttpBridgeSubsystem_Statics::Class_MetaDataParams), Z_Construct_UClass_UAgentHttpBridgeSubsystem_Statics::Class_MetaDataParams)
};
void UAgentHttpBridgeSubsystem::StaticRegisterNativesUAgentHttpBridgeSubsystem()
{
}
UClass* Z_Construct_UClass_UAgentHttpBridgeSubsystem()
{
	if (!Z_Registration_Info_UClass_UAgentHttpBridgeSubsystem.OuterSingleton)
	{
		UECodeGen_Private::ConstructUClass(Z_Registration_Info_UClass_UAgentHttpBridgeSubsystem.OuterSingleton, Z_Construct_UClass_UAgentHttpBridgeSubsystem_Statics::ClassParams);
	}
	return Z_Registration_Info_UClass_UAgentHttpBridgeSubsystem.OuterSingleton;
}
UAgentHttpBridgeSubsystem::UAgentHttpBridgeSubsystem() {}
DEFINE_VTABLE_PTR_HELPER_CTOR_NS(, UAgentHttpBridgeSubsystem);
UAgentHttpBridgeSubsystem::~UAgentHttpBridgeSubsystem() {}
// ********** End Class UAgentHttpBridgeSubsystem **************************************************

// ********** Begin Registration *******************************************************************
struct Z_CompiledInDeferFile_FID_ericdiaz_Desktop_Unreal_Friend_Plugins_UnrealAgent_Source_UnrealAgentEditor_Public_Agent_AgentHttpBridgeSubsystem_h__Script_UnrealAgentEditor_Statics
{
	static constexpr FClassRegisterCompiledInInfo ClassInfo[] = {
		{ Z_Construct_UClass_UAgentHttpBridgeSubsystem, UAgentHttpBridgeSubsystem::StaticClass, TEXT("UAgentHttpBridgeSubsystem"), &Z_Registration_Info_UClass_UAgentHttpBridgeSubsystem, CONSTRUCT_RELOAD_VERSION_INFO(FClassReloadVersionInfo, sizeof(UAgentHttpBridgeSubsystem), 1750093188U) },
	};
}; // Z_CompiledInDeferFile_FID_ericdiaz_Desktop_Unreal_Friend_Plugins_UnrealAgent_Source_UnrealAgentEditor_Public_Agent_AgentHttpBridgeSubsystem_h__Script_UnrealAgentEditor_Statics 
static FRegisterCompiledInInfo Z_CompiledInDeferFile_FID_ericdiaz_Desktop_Unreal_Friend_Plugins_UnrealAgent_Source_UnrealAgentEditor_Public_Agent_AgentHttpBridgeSubsystem_h__Script_UnrealAgentEditor_547294290{
	TEXT("/Script/UnrealAgentEditor"),
	Z_CompiledInDeferFile_FID_ericdiaz_Desktop_Unreal_Friend_Plugins_UnrealAgent_Source_UnrealAgentEditor_Public_Agent_AgentHttpBridgeSubsystem_h__Script_UnrealAgentEditor_Statics::ClassInfo, UE_ARRAY_COUNT(Z_CompiledInDeferFile_FID_ericdiaz_Desktop_Unreal_Friend_Plugins_UnrealAgent_Source_UnrealAgentEditor_Public_Agent_AgentHttpBridgeSubsystem_h__Script_UnrealAgentEditor_Statics::ClassInfo),
	nullptr, 0,
	nullptr, 0,
};
// ********** End Registration *********************************************************************

PRAGMA_ENABLE_DEPRECATION_WARNINGS
