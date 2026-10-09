using System.IO;
using System.Text.Json;

namespace OneCArchitecture.ControlCenter;

internal sealed record UiPreferences(string Language = "system", string Theme = "system", bool StartWithWindows = false);

internal static class PreferencesStore
{
    // Process-scoped UI preferences location also allows isolated packaged-UI tests.
    // This never changes the worker's state roots or its authentication/authorization.
    private static readonly string Root = Environment.GetEnvironmentVariable("ONEC_CONTROL_CENTER_PREFERENCES_ROOT") ?? Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "OneCArchitecture", "ControlCenter");
    private static readonly string FilePath = Path.Combine(Root, "preferences.json");

    public static UiPreferences Load()
    {
        try
        {
            if (!File.Exists(FilePath)) return new();
            return JsonSerializer.Deserialize<UiPreferences>(File.ReadAllText(FilePath)) ?? new();
        }
        catch { return new(); }
    }

    public static void Save(UiPreferences value)
    {
        Directory.CreateDirectory(Root);
        var json = JsonSerializer.Serialize(value, new JsonSerializerOptions { WriteIndented = true });
        var tmp = FilePath + ".tmp";
        File.WriteAllText(tmp, json);
        File.Move(tmp, FilePath, true);
    }
}
