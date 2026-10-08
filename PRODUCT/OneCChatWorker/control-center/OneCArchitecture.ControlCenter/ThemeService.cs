using Microsoft.Win32;
using System.Windows;
using System.Windows.Media;

namespace OneCArchitecture.ControlCenter;

internal static class ThemeService
{
    public static bool ResolveDark(string theme) =>
        theme.Equals("dark", StringComparison.OrdinalIgnoreCase) ||
        (theme.Equals("system", StringComparison.OrdinalIgnoreCase) && IsSystemDark());

    private static bool IsSystemDark()
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
            return Convert.ToInt32(key?.GetValue("AppsUseLightTheme", 1)) == 0;
        }
        catch { return false; }
    }

    public static void Apply(string theme)
    {
        var dark = ResolveDark(theme);
        Set("WindowBrush", dark ? "#171717" : "#F4F6F8");
        Set("NavBrush", dark ? "#111827" : "#FFFFFF");
        Set("CardBrush", dark ? "#20242B" : "#FFFFFF");
        Set("CardAltBrush", dark ? "#292E37" : "#F8FAFC");
        Set("PopupBrush", dark ? "#20242B" : "#FFFFFF");
        Set("HoverBrush", dark ? "#323946" : "#E9EEF6");
        Set("SelectionBrush", dark ? "#1E3A5F" : "#DBEAFE");
        Set("TextBrush", dark ? "#F3F4F6" : "#172033");
        Set("MutedTextBrush", dark ? "#AAB2C0" : "#667085");
        Set("BorderBrush", dark ? "#384152" : "#DCE2EA");
        Set("AccentBrush", "#2563EB");
        Set("SuccessBrush", dark ? "#34D399" : "#047857");
        Set("WarningBrush", dark ? "#FBBF24" : "#B45309");
        Set("DangerBrush", dark ? "#FB7185" : "#BE123C");
    }

    private static void Set(string key, string color) =>
        System.Windows.Application.Current.Resources[key] = new SolidColorBrush((System.Windows.Media.Color)System.Windows.Media.ColorConverter.ConvertFromString(color));
}
