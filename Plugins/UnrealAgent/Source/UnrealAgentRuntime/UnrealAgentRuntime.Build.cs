using UnrealBuildTool;

public class UnrealAgentRuntime : ModuleRules
{
    public UnrealAgentRuntime(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(
            new[]
            {
                "Core",
                "CoreUObject",
                "Engine",
                "Json",
                "JsonUtilities"
            }
        );
    }
}
