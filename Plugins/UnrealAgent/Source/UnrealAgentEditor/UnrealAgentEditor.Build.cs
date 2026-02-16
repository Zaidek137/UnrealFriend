using UnrealBuildTool;

public class UnrealAgentEditor : ModuleRules
{
    public UnrealAgentEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(
            new[]
            {
                "Core",
                "CoreUObject",
                "Engine",
                "HTTPServer",
                "EditorSubsystem",
                "UnrealEd",
                "UnrealAgentRuntime"
            }
        );

        PrivateDependencyModuleNames.AddRange(
            new[]
            {
                "AssetTools",
                "Kismet",
                "BlueprintGraph",
                "Json",
                "JsonUtilities"
            }
        );
    }
}
