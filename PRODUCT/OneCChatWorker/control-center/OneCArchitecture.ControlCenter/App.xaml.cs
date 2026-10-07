using System.Windows;
using Forms = System.Windows.Forms;

namespace OneCArchitecture.ControlCenter;

public partial class App : System.Windows.Application
{
    private Forms.NotifyIcon? _tray;
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
        _tray = new Forms.NotifyIcon
        {
            Text = "OneC Architecture",
            Icon = System.Drawing.SystemIcons.Application,
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
        base.OnExit(e);
    }
}
