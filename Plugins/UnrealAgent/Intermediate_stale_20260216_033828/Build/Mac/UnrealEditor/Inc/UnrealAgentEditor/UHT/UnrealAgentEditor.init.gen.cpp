// Copyright Epic Games, Inc. All Rights Reserved.
/*===========================================================================
	Generated code exported from UnrealHeaderTool.
	DO NOT modify this manually! Edit the corresponding .h files instead!
===========================================================================*/

#include "UObject/GeneratedCppIncludes.h"
PRAGMA_DISABLE_DEPRECATION_WARNINGS
void EmptyLinkFunctionForGeneratedCodeUnrealAgentEditor_init() {}
static_assert(!UE_WITH_CONSTINIT_UOBJECT, "This generated code can only be compiled with !UE_WITH_CONSTINIT_OBJECT");	static FPackageRegistrationInfo Z_Registration_Info_UPackage__Script_UnrealAgentEditor;
	FORCENOINLINE UPackage* Z_Construct_UPackage__Script_UnrealAgentEditor()
	{
		if (!Z_Registration_Info_UPackage__Script_UnrealAgentEditor.OuterSingleton)
		{
		static const UECodeGen_Private::FPackageParams PackageParams = {
			"/Script/UnrealAgentEditor",
			nullptr,
			0,
			PKG_CompiledIn | 0x00000040,
			0xF3E2B5FE,
			0x6F157D36,
			METADATA_PARAMS(0, nullptr)
		};
		UECodeGen_Private::ConstructUPackage(Z_Registration_Info_UPackage__Script_UnrealAgentEditor.OuterSingleton, PackageParams);
	}
	return Z_Registration_Info_UPackage__Script_UnrealAgentEditor.OuterSingleton;
}
static FRegisterCompiledInInfo Z_CompiledInDeferPackage_UPackage__Script_UnrealAgentEditor(Z_Construct_UPackage__Script_UnrealAgentEditor, TEXT("/Script/UnrealAgentEditor"), Z_Registration_Info_UPackage__Script_UnrealAgentEditor, CONSTRUCT_RELOAD_VERSION_INFO(FPackageReloadVersionInfo, 0xF3E2B5FE, 0x6F157D36));
PRAGMA_ENABLE_DEPRECATION_WARNINGS
