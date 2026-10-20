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
            if (args.Length == 3 && args[0] == "--packaged") return PackagedProbe.Run(args[1], args[2]);
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
            fake.UpdatePassed = true;
            Pump((Task)Call(w, "RefreshContextAsync")!);
            Call(w, "ShowPage", "Maintenance");
            Check(Control<TextBlock>(w, "OperationText").Text.Contains(Localization.Get("Verified")) &&
                Control<TextBlock>(w, "HelperBadge").Text.Contains(Localization.Get("Offline")), "F-G UPDATE PASS and Helper OFFLINE remain distinct");
            Render((FrameworkElement)w.Content, Path.Combine(output, "ru-dark-update-pass-helper-offline-Maintenance.png"), 1);
            fake.UpdatePassed = false;
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
                        Render((FrameworkElement)w.Content, Path.Combine(output, $"{language}-{theme}-{dpi.ToString("0.00", System.Globalization.CultureInfo.InvariantCulture)}-{page}.png"), dpi);
                    }
                    var wizard = new ProjectWizardWindow();
                    Render((FrameworkElement)wizard.Content, Path.Combine(output, $"{language}-{theme}-{dpi.ToString("0.00", System.Globalization.CultureInfo.InvariantCulture)}-Wizard.png"), dpi, 640, 620);
                    var label = (TextBlock)wizard.FindName("WizardExtensionFolderLabel");
                    Check(label.TextWrapping == TextWrapping.Wrap && (language != "ru" || label.ActualHeight >= label.FontSize * 2),
                        "full extension folder label wraps without overlap " + language + " " + theme + " " + dpi);
                    Check(wizard.Title == Localization.Get("AddProject"), "wizard title localized " + language);
                }
                Call(w, "ShowPage", "Projects");
                var row = (ListViewItem)list.ItemContainerGenerator.ContainerFromIndex(1);
                Check(row is not null && row.Focusable && list.SelectionMode == SelectionMode.Single, "keyboard-selectable project row");
                Check(Control<Button>(w, "ContinueButton").ToolTip is string reason && !string.IsNullOrWhiteSpace(reason), "disabled action reason present " + language);
            }
            TestExtensionSync(output);
            var screenshots = Directory.EnumerateFiles(output, "*.png").Count();
            File.WriteAllText(Path.Combine(output, "result.json"), System.Text.Json.JsonSerializer.Serialize(new { result = "PASS", checks = _checks, screenshots, fixture_only = true, production_access = false }));
            Console.WriteLine("CONTROL_CENTER_WPF_FIXTURE_PASS checks=" + _checks + " screenshots=" + screenshots);
            return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
    }

    private static JsonObject SyncContext()
    {
        var ctx = FixtureWorker.Context("RetailGroup");
        ctx["generated_utc"] = DateTimeOffset.UtcNow.ToString("o");
        ctx["source"]!["snapshot_id"] = "snapshot-before";
        ctx["source"]!["artifacts"] = JsonNode.Parse("""
        [{"key":"do|MAIN|main","participant_id":"do","artifact_type":"MAIN","artifact_id":"main"},
         {"key":"un|MAIN|main","participant_id":"un","artifact_type":"MAIN","artifact_id":"main"},
         {"key":"do|EXTENSION|bitdo","participant_id":"do","artifact_type":"EXTENSION","artifact_id":"bitdo"},
         {"key":"un|EXTENSION|bit","participant_id":"un","artifact_type":"EXTENSION","artifact_id":"bit"}]
        """);
        ctx["actions"]!["sync_extension"] = new JsonObject { ["enabled"] = true };
        ctx["actions"]!["prepare_source_update"]!["enabled"] = true;
        return ctx;
    }

    private static void TestExtensionSync(string output)
    {
        var fake = new FixtureWorker { ContextOverride = SyncContext() };
        var w = new MainWindow(fake, fixture: true);
        Pump((Task)Call(w, "RefreshContextAsync")!);
        var combo = Control<ComboBox>(w, "SourceArtifactCombo");
        void Select(string key) => combo.SelectedItem = combo.Items.Cast<object>().Single(a => a.GetType().GetProperty("Key")!.GetValue(a)?.ToString() == key);
        void Reload(JsonObject ctx) { fake.ContextOverride = ctx; Pump((Task)Call(w, "RefreshContextAsync")!); }
        var button = Control<Button>(w, "SyncExtensionButton");
        Select("do|MAIN|main");
        Check(!button.IsEnabled && Call(w, "SyncExtensionArgs") is null, "SYNC Main is ineligible");
        foreach (var tuple in new[] { ("do", "bitdo"), ("un", "bit") })
        {
            Select($"{tuple.Item1}|EXTENSION|{tuple.Item2}");
            var args = (WorkerActionArgs)Call(w, "SyncExtensionArgs")!;
            Check(button.IsEnabled && args.ProjectId == "RetailGroup" && args.ParticipantId == tuple.Item1 && args.ExtensionId == tuple.Item2 && args.SourcePath is null,
                "SYNC exact project/participant/extension " + tuple);
            foreach (var elevated in new[] { false, true })
            {
                var psi = new WorkerClient().CreateStartInfo(WorkerAction.SyncExtension, args, elevated);
                var wire = psi.ArgumentList.ToArray();
                string Value(string name) => wire[Array.IndexOf(wire, name) + 1];
                Check(Value("-Mode") == "SYNC_EXTENSION" && Value("-ProjectId") == args.ProjectId &&
                    Value("-ParticipantId") == args.ParticipantId && Value("-ExtensionId") == args.ExtensionId &&
                    psi.UseShellExecute == elevated && (!elevated || psi.Verb == "runas"), "SYNC typed wire/elevation " + tuple + " " + elevated);
            }
        }
        bool rejected = false;
        try { new WorkerClient().CreateStartInfo(WorkerAction.SyncExtension, new(ProjectId: "RetailGroup"), false); }
        catch (InvalidOperationException) { rejected = true; }
        Check(rejected, "SYNC missing typed identity rejected before process start");
        var baseline = SyncContext();
        Select("un|EXTENSION|bit");
        foreach (var block in new[] { "active", "incoming", "promotion", "recovery", "new", "key", "project" })
        {
            var ctx = (JsonObject)baseline.DeepClone();
            switch (block)
            {
                case "active": ctx["work"]!["active"] = true; break;
                case "incoming": ctx["source"]!["source_update"]!["status"] = "PREPARED_WRITABLE"; break;
                case "promotion": ctx["source"]!["source_update"]!["promotion_state"] = "RECOVERY_REQUIRED"; break;
                case "recovery": ctx["operation"]!["recovery"] = new JsonObject { ["classification"] = "RECOVERY_REQUIRED" }; break;
                case "new": ctx["source"]!["state"] = "CATALOG_DRIFT"; break;
                case "key": ctx["source"]!["artifacts"]![3]!["key"] = "un|EXTENSION|wrong"; break;
                case "project": ctx["selected_project"]!["project_id"] = "Other"; break;
            }
            Reload(ctx);
            Check(!button.IsEnabled && Call(w, "SyncExtensionArgs") is null, "SYNC disabled " + block);
        }
        Reload(baseline); Select("un|EXTENSION|bit");
        var pending = SyncContext();
        pending["source"]!["source_update"] = JsonNode.Parse("""
        {"project_id":"RetailGroup","status":"PREPARED_WRITABLE","generation_id":"G1",
        "slots":[{"key":"un|EXTENSION|bit","slot_path":"isolated-selected-slot"}]}
        """);
        pending["actions"]!["accept_source_update"]!["enabled"] = true;
        pending["actions"]!["cancel_source_update"]!["enabled"] = true;
        Reload(pending);
        var observed = (WorkerActionArgs)Call(w, "ObservedSourceUpdateArgs")!;
        Check(observed.ProjectId == "RetailGroup" && observed.ExpectedGenerationId == "G1" && observed.ExpectedArtifactKey == "un|EXTENSION|bit", "Advanced exact observed generation/project/key");
        Check((string?)Call(w, "SelectedSourceUpdateSlotPath", pending) == "isolated-selected-slot" && Control<Button>(w, "OpenIncomingButton").IsEnabled,
            "OpenIncoming uses selected exact slot without probing filesystem");
        Check(Control<TextBlock>(w, "SourceUpdateStatusText").Text == Localization.Get("SourceFolderPrepared"), "prepared folder makes no validation claim");
        Select("do|EXTENSION|bitdo");
        Check(Call(w, "ObservedSourceUpdateArgs") is null && !Control<Button>(w, "OpenIncomingButton").IsEnabled &&
            !Control<Button>(w, "AcceptSourceUpdateButton").IsEnabled && !Control<Button>(w, "CancelSourceUpdateButton").IsEnabled, "different selected key cannot open/accept/cancel G1");
        Select("un|EXTENSION|bit");
        var changedGeneration = (JsonObject)pending.DeepClone(); changedGeneration["source"]!["source_update"]!["generation_id"] = "G2";
        Reload(changedGeneration);
        Check(((WorkerActionArgs)Call(w, "ObservedSourceUpdateArgs")!).ExpectedGenerationId == "G2" && observed.ExpectedGenerationId == "G1", "generation change retains immutable original request; new observation is G2");
        var wrongProject = (JsonObject)pending.DeepClone(); wrongProject["source"]!["source_update"]!["project_id"] = "Other";
        Reload(wrongProject); Check(Call(w, "ObservedSourceUpdateArgs") is null, "Advanced mismatched update project fails closed");

        foreach (var status in new[] { "NO_CHANGE", "READY", "MISSING", "WRONG_KEY", "OLD_OPERATION", "WRONG_GENERATION", "FAIL" })
        {
            Reload(SyncContext()); Select("un|EXTENSION|bit");
            fake.SyncStatus = status;
            Call(w, "SyncExtension_Click", w, new RoutedEventArgs()); Drain();
            Check(fake.Calls.Last().Action == WorkerAction.SyncExtension && fake.Calls.Last().Args.ParticipantId == "un" && fake.Calls.Last().Args.ExtensionId == "bit", "fake elevated SYNC selected un/bit " + status);
            Check(Control<TextBlock>(w, "SourceSyncResultText").Text == Localization.Get(status == "NO_CHANGE" ? "SyncNoChange" : status == "READY" ? "SyncReady" : "SyncUnverified"), "null JSON elevated result verified/fails closed " + status);
        }
        Reload(SyncContext()); Select("un|EXTENSION|bit");
        var oldContext = (JsonObject)fake.ContextOverride!.DeepClone();
        var delayed = new TaskCompletionSource<WorkerCallResult>(); fake.Pending = delayed;
        var oldPoll = (Task)Call(w, "RefreshContextAsync")!;
        fake.SyncStatus = "READY"; Call(w, "SyncExtension_Click", w, new RoutedEventArgs()); Drain();
        delayed.SetResult(new(0, oldContext, "", "")); Pump(oldPoll);
        var contextField = typeof(MainWindow).GetField("_context", Private)!;
        Check(((JsonObject)contextField.GetValue(w)!)["source"]!["snapshot_id"]!.GetValue<string>() == "snapshot-after", "delayed pre-SYNC poll cannot restore an old canonical generation");
        Check(fake.Calls.All(c => c.Action == WorkerAction.SyncExtension), "SYNC no APPLY/START/STOP fallback");
        foreach (var language in new[] { "ru", "en" })
        foreach (var theme in new[] { "dark", "light" })
        foreach (var dpi in new[] { 1.0, 1.25, 1.5 })
        {
            Localization.SetLanguage(language); ThemeService.Apply(theme); Call(w, "ApplyLocalization");
            Reload(SyncContext()); Select("un|EXTENSION|bit"); Call(w, "ShowPage", "Maintenance");
            Check(button.Focusable && combo.Focusable && !Control<Expander>(w, "SourceAdvancedExpander").IsExpanded &&
                !string.IsNullOrWhiteSpace(Control<TextBlock>(w, "SyncExtensionHelpText").Text), "SYNC keyboard/normal vs Advanced " + language + theme + dpi);
            Render((FrameworkElement)w.Content, Path.Combine(output, $"sync-{language}-{theme}-{dpi}-Maintenance.png"), dpi);
            var selectedText = combo.Template.FindName("PART_Popup", combo) is not null && combo.SelectionBoxItemTemplate is not null;
            Check(selectedText, "selected artifact uses display template rather than record identity " + language + theme + dpi);
        }
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
    public JsonObject? ContextOverride;
    public string? SyncStatus;
    public bool Fail;
    public bool Empty;
    public bool UpdatePassed;
    public TaskCompletionSource<WorkerCallResult>? Pending;
    public Task<WorkerCallResult> GetContextAsync(string? projectId, CancellationToken token = default)
    {
        ContextRequests.Add(projectId);
        if (Pending is { } pending) { Pending = null; return pending.Task; }
        var ctx = ContextOverride is not null ? (JsonObject)ContextOverride.DeepClone() : Context(projectId, State);
        if (UpdatePassed) ctx["operation"] = new JsonObject { ["current"] = new JsonObject { ["operation_type"] = "UPDATE", ["state"] = "PASS" } };
        if (Empty) { ctx["projects"] = new JsonArray(); ctx["selected_project"] = null; ctx["recommendation"]!["state"] = "NO_PROJECTS"; foreach (var action in ctx["actions"]!.AsObject()) action.Value!["enabled"] = false; }
        return Task.FromResult(Fail ? new WorkerCallResult(2, null, "", "fixture diagnostic") : new(0, ctx, "", ""));
    }
    public Task<WorkerCallResult> RunAsync(WorkerAction action, WorkerActionArgs args, bool elevated = false, CancellationToken token = default)
    {
        Calls.Add((action, args));
        if (action == WorkerAction.SyncExtension && SyncStatus is { } status && ContextOverride is { } ctx)
        {
            var now = DateTimeOffset.UtcNow;
            var snapshot = status is "READY" or "WRONG_GENERATION" ? "snapshot-after" : "snapshot-before";
            var operation = new JsonObject {
                ["operation_id"] = status == "OLD_OPERATION" ? "old" : Guid.NewGuid().ToString("N"),
                ["operation_type"] = "SOURCE_UPDATE_QUICK_SYNC", ["state"] = status == "FAIL" ? "FAIL" : "PASS",
                ["project_id"] = args.ProjectId, ["participant_id"] = args.ParticipantId, ["artifact_id"] = args.ExtensionId,
                ["started_utc"] = (status == "OLD_OPERATION" ? now.AddHours(-1) : now).ToString("o"), ["ended_utc"] = now.ToString("o"),
                ["sync_extension_result"] = new JsonObject { ["status"] = status == "READY" || status == "WRONG_GENERATION" ? "READY" : "NO_CHANGE",
                    ["artifact_key"] = status == "WRONG_KEY" ? "do|EXTENSION|bitdo" : $"{args.ParticipantId}|EXTENSION|{args.ExtensionId}",
                    ["source_snapshot_id"] = snapshot, ["generation_id"] = status == "READY" ? "G-new" : null }
            };
            ctx["operation"]!["last"] = status == "MISSING" ? null : operation;
            ctx["generated_utc"] = DateTimeOffset.UtcNow.ToString("o"); ctx["source"]!["snapshot_id"] = snapshot;
        }
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
