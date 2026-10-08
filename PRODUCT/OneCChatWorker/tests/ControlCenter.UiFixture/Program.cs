using System.IO;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using OneCArchitecture.ControlCenter;
using Localization = OneCArchitecture.ControlCenter.Localization;

internal static class Program
{
    private static int _checks;
    private static readonly BindingFlags Private = BindingFlags.Instance | BindingFlags.NonPublic;
    private static void Check(bool ok, string name)
    {
        if (!ok) throw new InvalidOperationException("ASSERTION_FAILED:" + name);
        _checks++; Console.WriteLine("PASS " + name);
    }
    private static object? Call(object window, string method, params object[] args) =>
        window.GetType().GetMethod(method, Private)!.Invoke(window, args);
    private static T Control<T>(MainWindow w, string name) where T : class => (T)w.FindName(name);
    private static void Pump(Task task)
    {
        var frame = new DispatcherFrame();
        task.ContinueWith(_ => Dispatcher.CurrentDispatcher.BeginInvoke(() => frame.Continue = false),
            CancellationToken.None, TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.FromCurrentSynchronizationContext());
        Dispatcher.PushFrame(frame);
        task.GetAwaiter().GetResult();
    }
    private static void Drain()
    {
        var frame = new DispatcherFrame();
        Dispatcher.CurrentDispatcher.BeginInvoke(DispatcherPriority.ApplicationIdle, () => frame.Continue = false);
        Dispatcher.PushFrame(frame);
    }

    [STAThread]
    public static int Main(string[] args)
    {
        try
        {
            SynchronizationContext.SetSynchronizationContext(new DispatcherSynchronizationContext());
            var app = new App(); app.InitializeComponent(); // No OnStartup, tray, worker or settings writes.
            var output = args.Length == 1 ? args[0] : Path.Combine(Path.GetTempPath(), "onec-ui-fixture");
            Directory.CreateDirectory(output);
            var fake = new FixtureWorker();
            Localization.SetLanguage("ru"); ThemeService.Apply("dark");
            var w = new MainWindow(fake, fixture: true);
            Pump((Task)Call(w, "RefreshContextAsync")!);
            Check(!Control<Button>(w, "StartButton").IsEnabled, "initial multiple projects require explicit choice");
            var list = Control<ListView>(w, "ProjectsList");
            Call(w, "ShowPage", "Projects");
            Render((FrameworkElement)w.Content, Path.Combine(output, "ru-dark-unselected-Projects.png"), 1);
            list.SelectedIndex = 1; Drain();
            Check(fake.ContextRequests.Last() == "RetailGroup", "selection goes to canonical UI_CONTEXT ProjectId");
            Check(Control<Button>(w, "StartButton").IsEnabled, "second accepted project independent of first drift");
            foreach (var page in new[] { "Home", "Projects", "Work", "Maintenance" })
            {
                Call(w, "ShowPage", page);
                Check(Control<TextBlock>(w, "SelectedProjectText").Text.Contains("RetailGroup"), "selection retained on " + page);
            }
            Call(w, "Start_Click", w, new RoutedEventArgs()); Drain();
            Check(fake.Calls.Count == 1 && fake.Calls[0].Action == WorkerAction.Start &&
                fake.Calls[0].Args.ProjectId == "RetailGroup", "typed START targets only selected RetailGroup (fake owner)");
            Check(fake.Calls[0].Args.TaskGoal!.Contains(Localization.Get("ReferenceAccessGoal")), "empty business task permits general reference access");
            Check(fake.Calls.All(c => c.Action == WorkerAction.Start), "no auto APPLY VERIFY REPAIR STOP CONTINUE UPDATE");

            // A pending old response must never enable actions for a new visible selection.
            var stale = new TaskCompletionSource<WorkerCallResult>();
            fake.Pending = stale;
            var refresh = (Task)Call(w, "RefreshContextAsync")!;
            list.SelectedIndex = 0;
            Check(!Control<Button>(w, "StartButton").IsEnabled, "selection change disables stale action immediately");
            Render((FrameworkElement)w.Content, Path.Combine(output, "ru-dark-loading-Projects.png"), 1);
            stale.SetResult(new(0, FixtureWorker.Context("RetailGroup"), "", ""));
            Pump(refresh);
            Check(fake.ContextRequests.Last() == "NeoHim" && !Control<Button>(w, "StartButton").IsEnabled,
                "out of order context discarded and new project fetched");
            Check(Control<TextBlock>(w, "RecommendationText").Text == Localization.Get("SourceNeedsAttention"), "chosen drift recommendation honest");
            list.SelectedIndex = 1; Drain();

            fake.State = "ACTIVE_ADMISSION_OFFLINE";
            Pump((Task)Call(w, "RefreshContextAsync")!);
            Call(w, "ShowPage", "Work");
            Render((FrameworkElement)w.Content, Path.Combine(output, "ru-dark-offline-Work.png"), 1);
            Check(!Control<Button>(w, "StartButton").IsEnabled && !Control<Button>(w, "ContinueButton").IsEnabled,
                "offline existing admission has no new START or CONTINUE");
            Check(Control<TextBlock>(w, "RecommendationReasonText").Text.Contains(Localization.Get("OfflineRecoveryBlocked")), "offline recovery blocked reason rendered");
            Check(!Control<TextBlock>(w, "RecommendationReasonText").Text.Contains("Clear incomplete"), "offline never recommends clearing admission");
            fake.State = "RUNNING";
            Pump((Task)Call(w, "RefreshContextAsync")!);
            Render((FrameworkElement)w.Content, Path.Combine(output, "ru-dark-connected-Work.png"), 1);
            Check(Control<TextBlock>(w, "SessionHelpText").Text.Contains(Localization.Get("SessionHelp")), "new chat distinct from access session");
            Check(!Control<Button>(w, "StartButton").IsEnabled, "active connected session not reminted");
            Check(Presentation.Outcome("INVALID_READ_ARGS") != Presentation.Outcome("HELPER_OFFLINE") &&
                Presentation.Outcome("INVALID_READ_ARGS").Contains("20"), "max20 input error distinct from transport failure");
            Check(Presentation.Expiry("2020-01-01T00:00:00Z").Contains(Localization.Get("ExpiryElapsed")), "expired owner timestamp displayed truthfully");
            Check(Presentation.Expiry(null) == Localization.Get("ExpiryUnavailable"), "missing expiry not invented");
            fake.Fail = true;
            Pump((Task)Call(w, "RefreshContextAsync")!);
            Call(w, "ShowPage", "Home");
            Render((FrameworkElement)w.Content, Path.Combine(output, "ru-dark-error-Home.png"), 1);
            Check(!Control<Button>(w, "StartButton").IsEnabled && !Control<Button>(w, "StopButton").IsEnabled &&
                !Control<Button>(w, "UpdateButton").IsEnabled, "failed refresh clears old action eligibility");
            Check(Control<TextBox>(w, "AdvancedText").Text.Contains("fixture diagnostic") &&
                !Control<TextBlock>(w, "RecommendationReasonText").Text.Contains("fixture diagnostic"), "raw failure only Advanced");
            fake.Fail = false; fake.State = null;
            fake.Empty = true;
            Pump((Task)Call(w, "RefreshContextAsync")!);
            Call(w, "ShowPage", "Projects");
            Check(Control<TextBlock>(w, "ProjectsHintText").Text == Localization.Get("NoProjects"), "empty project list has explanation");
            Render((FrameworkElement)w.Content, Path.Combine(output, "ru-dark-empty-Projects.png"), 1);
            fake.Empty = false;

            foreach (var language in new[] { "ru", "en" })
            foreach (var theme in new[] { "dark", "light" })
            {
                Localization.SetLanguage(language); ThemeService.Apply(theme);
                Call(w, "ApplyLocalization");
                Pump((Task)Call(w, "RefreshContextAsync")!);
                foreach (var background in new[] { "CardBrush", "CardAltBrush", "SelectionBrush", "HoverBrush" })
                    Check(Contrast(Brush("TextBrush"), Brush(background)) >= 4.5, language + " " + theme + " readable " + background);
                Check(Contrast(Brush("MutedTextBrush"), Brush("CardAltBrush")) >= 4.5, theme + " disabled text contrast");
                foreach (var dpi in new[] { 1.0, 1.25, 1.5 })
                {
                    foreach (var page in new[] { "Home", "Projects", "Work", "Maintenance" })
                    {
                        Call(w, "ShowPage", page);
                        Render((FrameworkElement)w.Content, Path.Combine(output, $"{language}-{theme}-{dpi:0.00}-{page}.png"), dpi);
                    }
                    var wizard = new ProjectWizardWindow();
                    Render((FrameworkElement)wizard.Content, Path.Combine(output, $"{language}-{theme}-{dpi:0.00}-Wizard.png"), dpi, 640, 620);
                    Check(wizard.Title == Localization.Get("AddProject"), "wizard title localized " + language);
                }
                Call(w, "ShowPage", "Projects");
                var row = (ListViewItem)list.ItemContainerGenerator.ContainerFromIndex(1);
                Check(row is not null && row.Focusable && list.SelectionMode == SelectionMode.Single, "keyboard-selectable project row");
                Check(Control<Button>(w, "ContinueButton").ToolTip is string reason && !string.IsNullOrWhiteSpace(reason), "disabled action reason present " + language);
            }
            var screenshots = Directory.EnumerateFiles(output, "*.png").Count();
            File.WriteAllText(Path.Combine(output, "result.json"), System.Text.Json.JsonSerializer.Serialize(new { result = "PASS", checks = _checks, screenshots, fixture_only = true, production_access = false }));
            Console.WriteLine("CONTROL_CENTER_WPF_FIXTURE_PASS checks=" + _checks + " screenshots=" + screenshots);
            return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
    }

    private static Color Brush(string name) => ((SolidColorBrush)Application.Current.Resources[name]).Color;
    private static double Contrast(Color a, Color b)
    {
        static double L(Color c)
        {
            static double C(byte b) { var s = b / 255.0; return s <= .04045 ? s / 12.92 : Math.Pow((s + .055) / 1.055, 2.4); }
            return .2126 * C(c.R) + .7152 * C(c.G) + .0722 * C(c.B);
        }
        var x = L(a); var y = L(b); return (Math.Max(x, y) + .05) / (Math.Min(x, y) + .05);
    }
    private static void Render(FrameworkElement view, string path, double scale, double width = 1124, double height = 710)
    {
        view.Measure(new Size(width, height)); view.Arrange(new Rect(0, 0, width, height)); view.UpdateLayout();
        var bitmap = new RenderTargetBitmap((int)(width * scale), (int)(height * scale), 96 * scale, 96 * scale, PixelFormats.Pbgra32);
        bitmap.Render(view);
        var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(bitmap));
        using var file = File.Create(path); png.Save(file);
    }
}

internal sealed class FixtureWorker : IWorkerClient
{
    public List<string?> ContextRequests { get; } = [];
    public List<(WorkerAction Action, WorkerActionArgs Args)> Calls { get; } = [];
    public string? State;
    public bool Fail;
    public bool Empty;
    public TaskCompletionSource<WorkerCallResult>? Pending;
    public Task<WorkerCallResult> GetContextAsync(string? projectId, CancellationToken token = default)
    {
        ContextRequests.Add(projectId);
        if (Pending is { } pending) { Pending = null; return pending.Task; }
        var ctx = Context(projectId, State);
        if (Empty) { ctx["projects"] = new JsonArray(); ctx["selected_project"] = null; ctx["recommendation"]!["state"] = "NO_PROJECTS"; foreach (var action in ctx["actions"]!.AsObject()) action.Value!["enabled"] = false; }
        return Task.FromResult(Fail ? new WorkerCallResult(2, null, "", "fixture diagnostic") : new(0, ctx, "", ""));
    }
    public Task<WorkerCallResult> RunAsync(WorkerAction action, WorkerActionArgs args, bool elevated = false, CancellationToken token = default)
    {
        Calls.Add((action, args));
        return Task.FromResult(new WorkerCallResult(0, null, "", "")); // No process or filesystem action.
    }
    public static JsonObject Context(string? projectId, string? overrideState = null)
    {
        var state = overrideState ?? (projectId == "RetailGroup" ? "PROJECT_READY" : projectId == "NeoHim" ? "PROJECT_NEEDS_APPLY" : "PROJECT_SELECTION_REQUIRED");
        var active = state is "RUNNING" or "ACTIVE_ADMISSION_OFFLINE";
        var ctx = JsonNode.Parse("""
        {"schema":"UI_CONTEXT_V1","product":{"version":"fixture","integrity_status":"PASS"},
        "projects":[{"project_id":"NeoHim","display_name":"NeoHim","active":true,"fast_state":"CATALOG_DRIFT","participant_count":1},
                    {"project_id":"RetailGroup","display_name":"RetailGroup","active":true,"fast_state":"ACCEPTED","participant_count":2}],
        "source":{"state":"ACCEPTED","artifacts":[],"source_update":{"status":"NONE"}},
        "work":{"active":false,"helper":{"status":"OFFLINE"}},"s4":{"accounting_available":false},
        "navigation":{},"operation":{},"recommendation":{},"actions":{}}
        """)!.AsObject();
        ctx["selected_project"] = ctx["projects"]!.AsArray().OfType<JsonObject>().FirstOrDefault(p => p["project_id"]!.GetValue<string>() == projectId)?.DeepClone();
        ctx["recommendation"]!["state"] = state;
        ctx["source"]!["state"] = projectId == "RetailGroup" ? "ACCEPTED" : "CATALOG_DRIFT";
        ctx["work"]!["active"] = active;
        ctx["work"]!["project_id"] = active ? "RetailGroup" : null;
        ctx["work"]!["helper"]!["status"] = state == "RUNNING" ? "CONNECTED" : "OFFLINE";
        ctx["work"]!["task_expires_utc"] = active ? DateTimeOffset.UtcNow.AddHours(1).ToString("o") : null;
        foreach (var key in new[] { "start", "continue", "stop", "apply", "verify", "repair", "update", "add_project", "prepare_source_update", "accept_source_update", "cancel_source_update" })
        {
            var enabled = key switch { "start" => state == "PROJECT_READY", "apply" => state == "PROJECT_READY" || state == "PROJECT_NEEDS_APPLY", "stop" => active, "update" or "add_project" => true, _ => false };
            var reason = enabled ? "AVAILABLE" : key switch {
                "continue" => "NO_VERIFIED_CONTINUATION", "stop" => "NO_ACTIVE_SESSION",
                "accept_source_update" or "cancel_source_update" => "NO_SOURCE_UPDATE",
                "prepare_source_update" => "NO_ARTIFACTS",
                "verify" or "repair" when state == "PROJECT_READY" => "VERIFICATION_NOT_REQUIRED", _ => state };
            ctx["actions"]![key] = new JsonObject { ["enabled"] = enabled, ["reason"] = reason };
        }
        return ctx;
    }
}
