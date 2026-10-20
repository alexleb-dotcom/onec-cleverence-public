using System.Windows;
using Forms = System.Windows.Forms;

namespace OneCArchitecture.ControlCenter;

public partial class App : System.Windows.Application
{
    private Forms.NotifyIcon? _tray;
    private System.Drawing.Icon? _trayIcon;
    internal static bool IsExplicitExit { get; private set; }

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        var prefs = PreferencesStore.Load();
        var lang = prefs.Language == "system"
            ? (System.Globalization.CultureInfo.CurrentUICulture.Name.StartsWith("ru", StringComparison.OrdinalIgnoreCase) ? "ru" : "en")
            : prefs.Language;
        Localization.SetLanguage(lang);
        ThemeService.Apply(prefs.Theme);

        var window = new MainWindow();
        MainWindow = window;
        CreateTray(window);
        window.Show();
    }

    private void CreateTray(MainWindow window)
    {
        // Extract the real Win32 group icon embedded into our approved-brand EXE.
        // System.Drawing.Icon(Stream) does not reliably decode PNG-based ICO frames.
        _trayIcon = System.Drawing.Icon.ExtractAssociatedIcon(Environment.ProcessPath
            ?? throw new InvalidOperationException("ORBIT_APPROVED_ICON_EXE_PATH_MISSING"))
            ?? throw new InvalidOperationException("ORBIT_APPROVED_ICON_EXE_MISSING");
        _tray = new Forms.NotifyIcon
        {
            Text = "OneC Orbit",
            Icon = _trayIcon,
            Visible = true
        };
        _tray.DoubleClick += (_, _) => ShowWindow(window);
        var menu = new Forms.ContextMenuStrip();
        var open = new Forms.ToolStripMenuItem(Localization.Get("OpenApp"));
        open.Click += (_, _) => ShowWindow(window);
        menu.Items.Add(open);
        menu.Items.Add(new Forms.ToolStripSeparator());
        var exit = new Forms.ToolStripMenuItem(Localization.Get("ExitInterface"));
        exit.Click += (_, _) =>
        {
            IsExplicitExit = true;
            _tray!.Visible = false;
            _tray.Dispose();
            Shutdown();
        };
        menu.Items.Add(exit);
        _tray.ContextMenuStrip = menu;
    }

    private static void ShowWindow(MainWindow window)
    {
        if (!window.IsVisible) window.Show();
        if (window.WindowState == WindowState.Minimized) window.WindowState = WindowState.Normal;
        window.Activate();
    }

    protected override void OnExit(ExitEventArgs e)
    {
        if (_tray is not null) { _tray.Visible = false; _tray.Dispose(); }
        _trayIcon?.Dispose();
        base.OnExit(e);
    }
}
