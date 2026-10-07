using Microsoft.Win32;

namespace OneCArchitecture.ControlCenter;

internal static class StartupRegistration
{
    private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string ValueName = "OneCArchitectureControlCenter";

    public static void Apply(bool enabled)
    {
        using var key = Registry.CurrentUser.CreateSubKey(RunKey, writable: true);
        if (enabled)
        {
            var exe = Environment.ProcessPath;
            if (string.IsNullOrWhiteSpace(exe)) throw new InvalidOperationException("CONTROL_CENTER_PROCESS_PATH_UNAVAILABLE");
            key.SetValue(ValueName, Quote(exe), RegistryValueKind.String);
        }
        else
        {
            key.DeleteValue(ValueName, throwOnMissingValue: false);
        }
    }

    private static string Quote(string value)
    {
        var sanitized = value.Replace(((char)34).ToString(), string.Empty);
        return ((char)34) + sanitized + ((char)34).ToString();
    }
}
