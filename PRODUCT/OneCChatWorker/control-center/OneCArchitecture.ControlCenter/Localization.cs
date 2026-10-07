using System.Globalization;
using System.Resources;

namespace OneCArchitecture.ControlCenter;

internal static class Localization
{
    private static readonly ResourceManager Manager =
        new("OneCArchitecture.ControlCenter.Resources.Strings", typeof(Localization).Assembly);

    public static CultureInfo CurrentCulture { get; private set; } =
        CultureInfo.CurrentUICulture.Name.StartsWith("ru", StringComparison.OrdinalIgnoreCase)
            ? CultureInfo.GetCultureInfo("ru")
            : CultureInfo.GetCultureInfo("en");

    public static string Get(string key) => Manager.GetString(key, CurrentCulture) ?? key;

    public static void SetLanguage(string? language)
    {
        CurrentCulture = string.Equals(language, "ru", StringComparison.OrdinalIgnoreCase)
            ? CultureInfo.GetCultureInfo("ru")
            : CultureInfo.GetCultureInfo("en");
        CultureInfo.CurrentUICulture = CurrentCulture;
    }
}
