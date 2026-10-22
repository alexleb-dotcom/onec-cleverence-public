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
            var orbitEvidence = args.Length == 1 ? args[0] : Path.Combine(Path.GetTempPath(), "onec-ui-fixture");
            Environment.SetEnvironmentVariable("ONEC_CONTROL_CENTER_PREFERENCES_ROOT", Path.Combine(orbitEvidence, "preferences"));
            // D2 primary overview button is owner-derived NAVIGATION ONLY.
            // These scenarios never invoke real Worker, runas, Source or S4.
            Check(MainWindow.OwnerHomeAction(null, false, null) == ("Projects", "ChooseProject"),
                "D2 no selected project opens catalog");
            Check(MainWindow.OwnerHomeAction(null, false, "NeoHim") == ("Refresh", "WorkspaceCheckStatus"),
                "D2 pending identity only offers read-only context refresh");
            var d2Ready = FixtureWorker.Context("RetailGroup", "PROJECT_READY");
            Check(MainWindow.OwnerHomeAction(d2Ready, true, "RetailGroup") == ("Work", "WorkspacePrepareNewTask"),
                "D2 allowed START leads to task preparation screen, never executes START");
            Check(MainWindow.OwnerHomeAction(d2Ready, true, "NeoHim") == ("Refresh", "WorkspaceCheckStatus"),
                "D2 wrong selected identity cannot borrow another project's action");
            var d2Active = FixtureWorker.Context("RetailGroup", "RUNNING");
            Check(MainWindow.OwnerHomeAction(d2Active, true, "RetailGroup") == ("Work", "WorkspaceOpenCurrentTask"),
                "D2 connected active work opens current work rather than reminting");
            Check(MainWindow.OwnerHomeAction(d2Active, true, "NeoHim") == ("Refresh", "WorkspaceCheckStatus"),
                "D2 foreign owner project never authorizes cross-project navigation");
            var d2Other = FixtureWorker.Context("NeoHim", "RUNNING");
            Check(MainWindow.OwnerHomeAction(d2Other, true, "NeoHim") == ("Projects", "WorkspaceReviewOtherProject"),
                "D2 matching selected NeoHim with active RetailGroup task routes to catalog");
            var d2Offline = FixtureWorker.Context("RetailGroup", "ACTIVE_ADMISSION_OFFLINE");
            Check(MainWindow.OwnerHomeAction(d2Offline, true, "RetailGroup") == ("Refresh", "WorkspaceCheckConnection"),
                "D2 active admission with helper offline never starts or continues");
            var d2Checkpoint = FixtureWorker.Context("RetailGroup", "PROJECT_READY");
            d2Checkpoint["actions"]!["start"]!["enabled"] = false;
            d2Checkpoint["actions"]!["continue"] = new System.Text.Json.Nodes.JsonObject { ["enabled"] = true };
            d2Checkpoint["work"]!["checkpoint"] = new System.Text.Json.Nodes.JsonObject { ["head_seq"] = 10 };
            Check(MainWindow.OwnerHomeAction(d2Checkpoint, true, "RetailGroup") == ("Work", "WorkspaceOpenSavedWork"),
                "D2 only verified eligible checkpoint yields continuation navigation");
            var d2Hold = FixtureWorker.Context("NeoHim", "PROJECT_NEEDS_APPLY");
            Check(MainWindow.OwnerHomeAction(d2Hold, true, "NeoHim") == ("Refresh", "WorkspaceCheckStatus"),
                "D2 owner HOLD does not advertise START or CONTINUE");
            Check(StartupRegistration.ValueName == "OneC Orbit" &&
                StartupRegistration.Quote(@"C:\Synthetic Orbit\Orbit.exe") == "\"C:\\Synthetic Orbit\\Orbit.exe\"", "Orbit Run value and quoted command");
            Check(!WorkerClient.NeedsMigration(@"C:\Synthetic\worker", @"C:\Synthetic\pd", null,
                _ => throw new Exception("custom root probe"), _ => throw new Exception("custom legacy probe")), "custom roots never probe legacy");
            Check(WorkerClient.NeedsMigration(@"C:\OneCOrbit", @"C:\ProgramData\OneCOrbit", null,
                _ => false, _ => true), "legacy-only GUI blocks without actual filesystem probes");
            Check(!WorkerClient.NeedsMigration(@"C:\OneCOrbit", @"C:\ProgramData\OneCOrbit", null,
                _ => true, _ => throw new Exception("complete Orbit legacy probe")), "complete Orbit skips legacy probes");
            Check(!WorkerClient.NeedsMigration(@"C:\OneCOrbit", @"C:\ProgramData\OneCOrbit", "fake-launcher",
                _ => throw new Exception("override probe"), _ => throw new Exception("override legacy probe")), "fake launcher override preserved");
            var preferences = new UiPreferences("ru", "dark", false);
            PreferencesStore.Save(preferences);
            Check(PreferencesStore.Load() == preferences && File.Exists(Path.Combine(orbitEvidence, "preferences", "preferences.json")), "isolated preference roundtrip");
            SynchronizationContext.SetSynchronizationContext(new DispatcherSynchronizationContext());
            var app = new App(); app.InitializeComponent(); // No OnStartup, tray, worker or settings writes.
            foreach (var language in new[] { "en", "ru" })
            {
                Localization.SetLanguage(language);
                Check(Presentation.Status("ORBIT_PARTIAL_INSTALL") == Localization.Get("OrbitPartialInstall") &&
                    Presentation.Reason("ORBIT_PARTIAL_INSTALL") == Localization.Get("OrbitPartialInstallHelp") &&
                    Presentation.Reason("ORBIT_PARTIAL_INSTALL") != Presentation.Reason("MIGRATION_REQUIRED"),
                    "distinct Orbit partial and legacy copy " + language);
                foreach (var code in new[] { "PROJECT_ADMISSION_ACTIVE", "SOURCE_UPDATE_STATE_INVALID", "RECOVERY_REQUIRED", "SOURCE_UPDATE_RECOVERY_REQUIRED" })
                    Check(Presentation.Reason(code) != Localization.Get("OwnerEvidenceRequired") && Presentation.Reason(code) != code, "localized source update reason " + language + " " + code);
            }
            var output = args.Length == 1 ? args[0] : Path.Combine(Path.GetTempPath(), "onec-ui-fixture");
            Directory.CreateDirectory(output);
            var fake = new FixtureWorker();
            Localization.SetLanguage("ru"); ThemeService.Apply("dark");
            var w = new MainWindow(fake, fixture: true);
            Pump((Task)Call(w, "RefreshContextAsync")!);
            Call(w, "ShowContextFailure", 2, "MIGRATION_REQUIRED", "");
            Check(Control<TextBlock>(w, "RecommendationText").Text == Localization.Get("MigrationRequired") &&
                !Control<Button>(w, "StartButton").IsEnabled && !Control<Button>(w, "UpdateButton").IsEnabled,
                "migration hold displayed with mutations disabled");
            Render((FrameworkElement)w.Content, Path.Combine(output, "ru-dark-migration-required.png"), 1);
            var partialContext = FixtureWorker.Context(null, "MIGRATION_REQUIRED");
            partialContext["recommendation"]!["reason_code"] = "ORBIT_PARTIAL_INSTALL";
            partialContext["projects"] = new JsonArray();
            partialContext["selected_project"] = null;
            foreach (var action in partialContext["actions"]!.AsObject()) action.Value!["enabled"] = false;
            fake.ContextOverride = partialContext;
            Pump((Task)Call(w, "RefreshContextAsync")!);
            Check(Control<TextBlock>(w, "RecommendationText").Text == Localization.Get("OrbitPartialInstall") &&
                Control<TextBlock>(w, "RecommendationReasonText").Text == Localization.Get("OrbitPartialInstallHelp") &&
                !Control<Button>(w, "StartButton").IsEnabled && !Control<Button>(w, "UpdateButton").IsEnabled,
                "WPF Orbit partial recovery is truthful and blocks mutations");
            Render((FrameworkElement)w.Content, Path.Combine(output, "ru-dark-orbit-partial-install.png"), 1);
            fake.ContextOverride = null;
            Pump((Task)Call(w, "RefreshContextAsync")!);
            Check(!Control<Button>(w, "StartButton").IsEnabled, "initial multiple projects require explicit choice");
            Check(Control<Button>(w, "HomePrimaryButton").Tag as string == "Projects", "Home directs unselected context to Projects");
            var callsBeforeHomeNavigation = fake.Calls.Count;
            Control<Button>(w, "HomePrimaryButton").RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            Check(Control<FrameworkElement>(w, "ProjectsPage").Visibility == Visibility.Visible && fake.Calls.Count == callsBeforeHomeNavigation,
                "Home primary navigation dispatches no worker mutation");
            var list = Control<ListView>(w, "ProjectsList");
            Call(w, "ShowPage", "Projects");
            Render((FrameworkElement)w.Content, Path.Combine(output, "ru-dark-unselected-Projects.png"), 1);
            list.SelectedIndex = 1; Drain();
            Check(fake.ContextRequests.Last() == "RetailGroup", "selection goes to canonical UI_CONTEXT ProjectId");
            Check(Control<Button>(w, "StartButton").IsEnabled, "second accepted project independent of first drift");
            Call(w, "ShowPage", "Home");
            Check(Control<Grid>(w, "HomeStatusStrip").ColumnDefinitions.Count == 3 &&
                Control<TextBlock>(w, "SourceTitleLabel").Text == Localization.Get("SourceTitle") &&
                Control<TextBlock>(w, "HomeHelperLabel").Text == Localization.Get("HelperLabel") &&
                Control<TextBlock>(w, "CurrentWorkLabel").Text == Localization.Get("CurrentWork") &&
                Control<Button>(w, "HomeDetailsButton").Tag as string == "Advanced",
                "D2 concise overview has exactly one CTA plus three read-only status sections and secondary diagnostics");

            var beforeD2Nav = fake.Calls.Count;
            Check(Control<Button>(w, "HomePrimaryButton").Tag as string == "Work",
                "D2 owner-enabled new task routes to Work without directly issuing START");
            Control<Button>(w, "HomePrimaryButton").RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            Check(Control<FrameworkElement>(w, "WorkPage").Visibility == Visibility.Visible &&
                fake.Calls.Count == beforeD2Nav,
                "D2 actual WPF primary click only navigates Work, never dispatches Worker");
            Call(w, "ShowPage", "Home");
            Check(Control<FrameworkElement>(w, "ProjectTabs").Visibility == Visibility.Visible &&
                Control<Button>(w, "NavWorkButton").Visibility == Visibility.Collapsed &&
                Control<Button>(w, "NavActivityButton").Visibility == Visibility.Collapsed &&
                Control<Button>(w, "NavMaintenanceButton").Visibility == Visibility.Collapsed &&
                Control<Button>(w, "NavAdvancedButton").Visibility == Visibility.Collapsed,
                "D1 primary sidebar contains only three destinations; selected project exposes four tabs");
            foreach (var (page, present, hidden) in new[] {
                ("Source", "MaintenanceGeneralPanel", "MaintenanceExtensionPanel"),
                ("Extensions", "MaintenanceExtensionPanel", "MaintenanceGeneralPanel") })
            {
                var beforeNav = fake.Calls.Count;
                Call(w, "ShowPage", page);
                Check(Control<FrameworkElement>(w, present).Visibility == Visibility.Visible &&
                    Control<FrameworkElement>(w, hidden).Visibility == Visibility.Collapsed &&
                    fake.Calls.Count == beforeNav,
                    "D1 scoped " + page + " routes without triggering Worker mutation");
            }
            Call(w, "ShowPage", "Activity");
            Check(Control<FrameworkElement>(w, "ActivityPage").Visibility == Visibility.Visible &&
                System.Windows.Automation.AutomationProperties.GetItemStatus(Control<Button>(w, "ProjectHistoryTab")) == "Selected",
                "D1 History tab opens owner-provided activity without an independent primary nav");
            Call(w, "ShowPage", "Settings");
            Check(Control<FrameworkElement>(w, "ProjectTabs").Visibility == Visibility.Collapsed &&
                Control<Button>(w, "SettingsMaintenanceButton").Tag as string == "Maintenance" &&
                Control<Button>(w, "SettingsAdvancedButton").Tag as string == "Advanced",
                "D1 project tabs hidden in Settings; legacy maintenance and diagnostics are discoverable");
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

            // FA #122 regression: simulate a genuine owner-confirmed old-project
            // header, then hold a previous poll while choosing another project.
            // Header transition must remove stale owner claims in the SAME
            // dispatcher turn, before a new UI_CONTEXT can finish.
            Control<TextBlock>(w, "LastUpdatedText").Text = Localization.Get("WorkspaceVerifiedAt") + " 10:10";
            Control<TextBlock>(w, "WorkspaceNoticeText").Text = Localization.Get("WorkspaceConnectionUnverified");
            Control<TextBlock>(w, "GlobalWarningText").Text = Localization.Get("OtherProjectsWarning");
            Control<TextBlock>(w, "HelperBadge").Text = "CONNECTED";
            Control<TextBlock>(w, "HomeTaskText").Text = "RetailGroup old task";
            Control<TextBlock>(w, "OutputStateText").Text = "RetailGroup 8 tasks";
            Control<TextBlock>(w, "OutputSummaryText").Text = "RetailGroup 2 proposals";
            Control<TextBlock>(w, "ActivitySummaryText").Text = "RetailGroup 4 activities";
            Control<TextBlock>(w, "McpEpochText").Text = "RetailGroup expiry";
            Control<TextBlock>(w, "OperationText").Text = "RetailGroup operation";
            var beforeSelectionCalls = fake.Calls.Count;
            var stale = new TaskCompletionSource<WorkerCallResult>();
            fake.Pending = stale;
            var refresh = (Task)Call(w, "RefreshContextAsync")!;
            list.SelectedIndex = 0;
            Check(Control<TextBlock>(w, "SelectedProjectText").Text.Contains("NeoHim") &&
                Control<TextBlock>(w, "LastUpdatedText").Text == Localization.Get("WorkspaceVerificationPending") &&
                Control<TextBlock>(w, "WorkspaceNoticeText").Text == Localization.Get("WorkspaceVerificationPending") &&
                Control<TextBlock>(w, "GlobalWarningText").Text.Length == 0,
                "D1 switching project immediately clears previous owner time and warning while pending");
            Check(!Control<TextBlock>(w, "HelperBadge").Text.Contains("CONNECTED") &&
                !Control<TextBlock>(w, "HomeTaskText").Text.Contains("RetailGroup") &&
                !Control<Button>(w, "StartButton").IsEnabled &&
                fake.Calls.Count == beforeSelectionCalls,
                "D1 pending identity invalidates previous Helper/task proof and forbids mutations");
            Call(w, "ShowPage", "Home");
            Check(Control<TextBlock>(w, "OutputStateText").Text == Localization.Get("WorkspaceVerificationPending") &&
                Control<TextBlock>(w, "OutputSummaryText").Text == Localization.Get("WorkspaceVerificationPending") &&
                Control<TextBlock>(w, "ActivitySummaryText").Text == Localization.Get("WorkspaceVerificationPending") &&
                Control<TextBlock>(w, "McpEpochText").Text == Localization.Get("WorkspaceVerificationPending") &&
                Control<TextBlock>(w, "OperationText").Text == Localization.Get("WorkspaceVerificationPending") &&
                !Control<Button>(w, "StartButton").IsEnabled && fake.Calls.Count == beforeSelectionCalls,
                "D1 pending project switch hides old Output/Activity on Home");
            Call(w, "ShowPage", "Projects");
            Render((FrameworkElement)w.Content, Path.Combine(output, "ru-dark-loading-Projects.png"), 1);
            stale.SetResult(new(0, FixtureWorker.Context("RetailGroup"), "", ""));
            Pump(refresh);
            Check(fake.ContextRequests.Last() == "NeoHim" && !Control<Button>(w, "StartButton").IsEnabled,
                "out of order context discarded and new project fetched");
            Check(Control<TextBlock>(w, "RecommendationText").Text == Localization.Get("SourceNeedsAttention"), "chosen drift recommendation honest");
            var failedNewReadback = new TaskCompletionSource<WorkerCallResult>();
            fake.Pending = failedNewReadback;
            list.SelectedIndex = 1;
            Check(Control<TextBlock>(w, "LastUpdatedText").Text == Localization.Get("WorkspaceVerificationPending") &&
                Control<TextBlock>(w, "SelectedProjectText").Text.Contains("RetailGroup"),
                "second project switch stays unverified throughout stalled context request");
            failedNewReadback.SetResult(new(2, null, "", "fixture synthetic failure"));
            Drain();
            Call(w, "ShowPage", "Home");
            Check(Control<TextBlock>(w, "LastUpdatedText").Text == Localization.Get("WorkspaceVerificationUnknown") &&
                Control<TextBlock>(w, "WorkspaceNoticeText").Text == Localization.Get("WorkspaceVerificationUnknown") &&
                !Control<Button>(w, "StartButton").IsEnabled,
                "failed owner readback remains UNKNOWN / actions disabled");
            Check(Control<TextBlock>(w, "OutputStateText").Text == Localization.Get("WorkspaceVerificationUnknown") &&
                Control<TextBlock>(w, "OutputSummaryText").Text == Localization.Get("WorkspaceVerificationUnknown") &&
                Control<TextBlock>(w, "ActivitySummaryText").Text == Localization.Get("WorkspaceVerificationUnknown") &&
                Control<TextBlock>(w, "McpEpochText").Text == Localization.Get("WorkspaceVerificationUnknown") &&
                Control<TextBlock>(w, "OperationText").Text == Localization.Get("WorkspaceVerificationUnknown"),
                "failed readback leaves Output/Activity/expiry/operation UNKNOWN");
            Pump((Task)Call(w, "RefreshContextAsync")!);
            Check(Control<Button>(w, "StartButton").IsEnabled && fake.Calls.Count == beforeSelectionCalls,
                "fresh matched Worker context restores selected project, without new mutation");

            // FA #122 P0: a successful request for NeoHim can return
            // RetailGroup JSON. This is not an old request: it must be
            // rejected by comparing the RESPONSE selected_project identity.
            var foreignCalls = fake.Calls.Count;
            fake.ContextOverride = FixtureWorker.Context("RetailGroup", "PROJECT_READY");
            Call(w, "ShowPage", "Projects");
            list.SelectedIndex = 0; Drain();
            Check(fake.ContextRequests.Last() == "NeoHim" &&
                Control<TextBlock>(w, "LastUpdatedText").Text == Localization.Get("WorkspaceVerificationUnknown") &&
                Control<TextBlock>(w, "WorkspaceNoticeText").Text == Localization.Get("WorkspaceVerificationUnknown") &&
                !Control<TextBlock>(w, "SelectedProjectText").Text.Contains("RetailGroup") &&
                !Control<Button>(w, "ApplyButton").IsEnabled &&
                !Control<Button>(w, "VerifyButton").IsEnabled &&
                !Control<Button>(w, "RepairButton").IsEnabled &&
                !Control<Button>(w, "StartButton").IsEnabled,
                "D1 returned foreign RetailGroup JSON for current NeoHim request fails closed");
            Call(w, "Apply_Click", w, new RoutedEventArgs());
            Call(w, "Verify_Click", w, new RoutedEventArgs());
            Call(w, "Repair_Click", w, new RoutedEventArgs());
            Drain();
            Check(fake.Calls.Count == foreignCalls,
                "D1 foreign response forbids all project-scoped Worker mutations");
            fake.ContextOverride = FixtureWorker.Context("RetailGroup", "PROJECT_READY");
            fake.ContextOverride["selected_project"] = null;
            Pump((Task)Call(w, "RefreshContextAsync")!);
            Check(!Control<Button>(w, "ApplyButton").IsEnabled &&
                Control<TextBlock>(w, "LastUpdatedText").Text == Localization.Get("WorkspaceVerificationUnknown"),
                "D1 missing selected_project response fails closed");
            Check(!MainWindow.OwnerResponseMatchesRequested("Проект-Кириллица-01", FixtureWorker.Context("NeoHim")) &&
                MainWindow.OwnerResponseMatchesRequested("Проект-Кириллица-01",
                    new JsonObject { ["selected_project"] = new JsonObject { ["project_id"] = "Проект-Кириллица-01" } }),
                "D1 exact owner ID check handles long Cyrillic and rejects foreign ID");
            fake.ContextOverride = null;
            Pump((Task)Call(w, "RefreshContextAsync")!);
            Check(!Control<Button>(w, "StartButton").IsEnabled &&
                Control<TextBlock>(w, "SelectedProjectText").Text.Contains("NeoHim"),
                "D1 only exact matching NeoHim response restores verified owner projection");
            list.SelectedIndex = 1; Drain();
            Check(Control<Button>(w, "StartButton").IsEnabled && fake.Calls.Count == foreignCalls,
                "D1 matching RetailGroup response restores permitted actions with zero replay");

            fake.State = "ACTIVE_ADMISSION_OFFLINE";
            Pump((Task)Call(w, "RefreshContextAsync")!);
            Call(w, "ShowPage", "Work");
            Render((FrameworkElement)w.Content, Path.Combine(output, "ru-dark-offline-Work.png"), 1);
            Check(!Control<Button>(w, "StartButton").IsEnabled && !Control<Button>(w, "ContinueButton").IsEnabled,
                "offline existing admission has no new START or CONTINUE");
            Check(Control<Button>(w, "HomePrimaryButton").Tag as string == "Refresh" &&
                Control<Button>(w, "HomePrimaryButton").Content?.ToString() == Localization.Get("WorkspaceCheckConnection"),
                "D2 offline active work only offers read-only connection recheck");
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
            Check(Control<Button>(w, "HomePrimaryButton").Tag as string == "Refresh" &&
                Control<Button>(w, "HomePrimaryButton").Content?.ToString() == Localization.Get("WorkspaceCheckStatus"),
                "D2 failed context only offers read-only refresh, no stale project action");
            var beforeD2Refresh = fake.Calls.Count;
            Control<Button>(w, "HomePrimaryButton").RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            Drain();
            Check(fake.Calls.Count == beforeD2Refresh && !Control<Button>(w, "StartButton").IsEnabled,
                "D2 actual primary refresh on failed context makes zero Worker mutations");
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
            // A request for selected RetailGroup may not accept a successful
            // response that omits selected_project, even when the catalog is
            // empty. The UI must remain UNKNOWN rather than treat it as a new
            // authoritative no-project state.
            Check(Control<TextBlock>(w, "LastUpdatedText").Text == Localization.Get("WorkspaceVerificationUnknown") &&
                !Control<Button>(w, "StartButton").IsEnabled &&
                !Control<Button>(w, "ApplyButton").IsEnabled &&
                !Control<Button>(w, "AddProjectButton").IsEnabled,
                "missing selected project in catalog response fails closed");
            Render((FrameworkElement)w.Content, Path.Combine(output, "ru-dark-owner-id-missing-Projects.png"), 1);
            fake.Empty = false;

            foreach (var language in new[] { "ru", "en" })
            foreach (var theme in new[] { "dark", "light" })
            {
                Localization.SetLanguage(language); ThemeService.Apply(theme);
                Call(w, "ApplyLocalization");
                Pump((Task)Call(w, "RefreshContextAsync")!);
                Check(Control<TextBlock>(w, "HomeHelperLabel").Text == Localization.Get("HelperLabel") &&
                    System.Windows.Automation.AutomationProperties.GetName(Control<Grid>(w, "HomeStatusStrip")) == Localization.Get("WorkspaceOverview"),
                    "D2 status strip native WPF automation and Helper label localized " + language + theme);
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
                    Call(w, "ShowPage", "Home");
                    // 920 x 620 outer window, allowing for native frame/title bar.
                    Render((FrameworkElement)w.Content, Path.Combine(output, $"ux6-{language}-{theme}-{dpi}-min-Home.png"), dpi, 904, 581);
                    var primary = Control<Button>(w, "HomePrimaryButton");
                    var home = Control<ScrollViewer>(w, "HomePage");
                    Check(primary.ActualWidth >= 80 && primary.ActualHeight >= 36 && home.ViewportWidth > 500,
                        $"minimum Home retains readable content and primary target {language}{theme}{dpi}: width={primary.ActualWidth}, height={primary.ActualHeight}, viewport={home.ViewportWidth}");
                    Check(Control<Grid>(w, "HomeStatusStrip").ActualWidth > 450 &&
                        Control<TextBlock>(w, "HomeTaskText").TextWrapping == TextWrapping.Wrap &&
                        Control<TextBlock>(w, "HomeProjectText").TextWrapping == TextWrapping.Wrap,
                        "D2 owner status strip and long project/task names reflow at minimum viewport " + language + theme + dpi);
                    Check(System.Windows.Automation.AutomationProperties.GetItemStatus(Control<Button>(w, "NavHomeButton")) == "Selected",
                        "selected navigation exposed without Enter default action " + language + theme + dpi);
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
            TestPendingAdmission(output);
            TestOverlappingAdmissionRefresh();
            TestExtensionSync(output);
            var screenshots = Directory.EnumerateFiles(output, "*.png").Count();
            File.WriteAllText(Path.Combine(output, "result.json"), System.Text.Json.JsonSerializer.Serialize(new { result = "PASS", checks = _checks, screenshots, fixture_only = true, production_access = false }));
            Console.WriteLine("CONTROL_CENTER_WPF_FIXTURE_PASS checks=" + _checks + " screenshots=" + screenshots);
            return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
    }

    // Hosted Windows only: no external password prompt, user account or process.
    // A delayed fake Worker result models the whole credential/admission interval.
    private static void TestPendingAdmission(string output)
    {
        var fake = new FixtureWorker();
        var w = new MainWindow(fake, fixture: true);
        Pump((Task)Call(w, "RefreshContextAsync")!);
        var list = Control<ListView>(w, "ProjectsList");
        list.SelectedIndex = 1; Drain();
        Check(Control<Button>(w, "StartButton").IsEnabled,
            "D2C canonical selected RetailGroup permits START before credential request");
        var pendingStart = new TaskCompletionSource<WorkerCallResult>();
        fake.PendingAdmissionResult = pendingStart;
        var beforeCalls = fake.Calls.Count;
        Call(w, "Start_Click", w, new RoutedEventArgs()); Drain();
        Check(fake.Calls.Count == beforeCalls + 1 &&
            fake.Calls.Last().Action == WorkerAction.Start &&
            fake.Calls.Last().Args.ProjectId == "RetailGroup" &&
            !list.IsEnabled && !Control<Button>(w, "StartButton").IsEnabled &&
            !Control<Button>(w, "ContinueButton").IsEnabled &&
            !Control<Button>(w, "HomePrimaryButton").IsEnabled &&
            Control<Button>(w, "HomePrimaryButton").Tag as string == "AdmissionPending" &&
            Control<TextBlock>(w, "WorkspaceNoticeText").Text.Contains("RetailGroup"),
            "D2C pending START freezes project and changes primary CTA to disabled admission state");
        var beforeReads = fake.ContextRequests.Count;
        list.SelectedIndex = 0; Drain();
        Check(list.SelectedItem is not null &&
            list.SelectedItem.GetType().GetProperty("ProjectId")?.GetValue(list.SelectedItem)?.ToString() == "RetailGroup" &&
            fake.ContextRequests.Count == beforeReads && fake.Calls.Count == beforeCalls + 1,
            "D2C synthetic cross-project selection during START password prompt is rejected");
        Call(w, "Continue_Click", w, new RoutedEventArgs()); Drain();
        Check(fake.Calls.Count == beforeCalls + 1,
            "D2C pending START cannot dispatch concurrent CONTINUE");
        Render((FrameworkElement)w.Content, Path.Combine(output, "d2c-ru-pending-start.png"), 1, 904, 581);
        pendingStart.SetResult(new WorkerCallResult(1223, null, "", "UAC_CANCELLED")); Drain();
        Check(list.IsEnabled && Control<Button>(w, "HomePrimaryButton").IsEnabled &&
            !Control<TextBlock>(w, "WorkspaceNoticeText").Text.Contains(Localization.Get("WorkspaceAdmissionPending")) &&
            fake.Calls.Count == beforeCalls + 1,
            "D2C cancellation releases UI lock and does not retry START");

        var allowedContinue = FixtureWorker.Context("RetailGroup", "PROJECT_READY");
        allowedContinue["actions"]!["start"]!["enabled"] = false;
        allowedContinue["actions"]!["continue"]!["enabled"] = true;
        allowedContinue["work"]!["checkpoint"] = new JsonObject { ["head_seq"] = 15 };
        allowedContinue["work"]!["project_id"] = "RetailGroup";
        fake.ContextOverride = allowedContinue;
        Pump((Task)Call(w, "RefreshContextAsync")!);
        Check(Control<Button>(w, "ContinueButton").IsEnabled,
            "D2C same-project verified checkpoint permits explicit CONTINUE");
        var pendingContinue = new TaskCompletionSource<WorkerCallResult>();
        fake.PendingAdmissionResult = pendingContinue;
        Call(w, "Continue_Click", w, new RoutedEventArgs()); Drain();
        Check(!list.IsEnabled && !Control<Button>(w, "HomePrimaryButton").IsEnabled &&
            fake.Calls.Count == beforeCalls + 2 && fake.Calls.Last().Action == WorkerAction.Continue,
            "D2C pending CONTINUE freezes project and suppresses other mutations");
        list.SelectedIndex = 0; Drain();
        Check(list.SelectedItem is not null &&
            list.SelectedItem.GetType().GetProperty("ProjectId")?.GetValue(list.SelectedItem)?.ToString() == "RetailGroup" &&
            fake.Calls.Count == beforeCalls + 2,
            "D2C CONTINUE rejects mid-prompt selection and never mints START");
        pendingContinue.SetResult(new WorkerCallResult(0, null, "", "")); Drain();
        Check(list.IsEnabled && Control<Button>(w, "HomePrimaryButton").IsEnabled &&
            fake.Calls.Count == beforeCalls + 2,
            "D2C completed CONTINUE releases pending admission without replay");

        allowedContinue["work"]!["project_id"] = "NeoHim";
        fake.ContextOverride = allowedContinue;
        Pump((Task)Call(w, "RefreshContextAsync")!);
        Call(w, "Continue_Click", w, new RoutedEventArgs()); Drain();
        Check(fake.Calls.Count == beforeCalls + 2,
            "D2C owner context with foreign task ID cannot dispatch unscoped CONTINUE");
    }

    // FA regression: a four-second timer poll is still in flight when a
    // credential START/CONTINUE finishes. Only a *subsequent* owner read may
    // unlock mutation eligibility, even when the old poll fails or is stale.
    private static void TestOverlappingAdmissionRefresh()
    {
        foreach (var (caseName, continuation, commandExit, postOutcome, oldPollFails) in new[]
        {
            ("START_SUCCESS", false, 0, "RUNNING", false),
            ("START_CANCELLED", false, 1223, "PROJECT_READY", false),
            ("START_POST_READ_ERROR", false, 0, "ERROR", true),
            ("CONTINUE_SUCCESS", true, 0, "RUNNING", false),
            ("CONTINUE_NONZERO_FOREIGN", true, 3, "FOREIGN", false),
            ("CONTINUE_MISSING_OWNER", true, 0, "MISSING", true)
        })
        {
            var fake = new FixtureWorker();
            var w = new MainWindow(fake, fixture: true);
            Pump((Task)Call(w, "RefreshContextAsync")!);
            var list = Control<ListView>(w, "ProjectsList");
            list.SelectedIndex = 1; Drain();
            var eligible = FixtureWorker.Context("RetailGroup", "PROJECT_READY");
            if (continuation)
            {
                eligible["actions"]!["start"]!["enabled"] = false;
                eligible["actions"]!["continue"]!["enabled"] = true;
                eligible["work"]!["checkpoint"] = new JsonObject { ["head_seq"] = 42 };
                eligible["work"]!["project_id"] = "RetailGroup";
            }
            fake.ContextOverride = eligible;
            Pump((Task)Call(w, "RefreshContextAsync")!);
            Check(Control<Button>(w, continuation ? "ContinueButton" : "StartButton").IsEnabled,
                caseName + " starts from verified eligible owner state");
            var delayedTimer = new TaskCompletionSource<WorkerCallResult>();
            fake.Pending = delayedTimer;
            var timerRead = (Task)Call(w, "RefreshContextAsync")!;
            Check(!timerRead.IsCompleted, caseName + " timer GetContext is actually pending");
            var readsBefore = fake.ContextRequests.Count;
            var callsBefore = fake.Calls.Count;
            var pendingCommand = new TaskCompletionSource<WorkerCallResult>();
            fake.PendingAdmissionResult = pendingCommand;
            Call(w, continuation ? "Continue_Click" : "Start_Click", w, new RoutedEventArgs()); Drain();
            Check(fake.Calls.Count == callsBefore + 1 &&
                fake.Calls.Last().Action == (continuation ? WorkerAction.Continue : WorkerAction.Start) &&
                !list.IsEnabled && !Control<Button>(w, "StartButton").IsEnabled &&
                !Control<Button>(w, "ContinueButton").IsEnabled,
                caseName + " admission freezes exact owner during concurrent timer");
            // Supply a second independently controlled response AFTER the old
            // timer consumes its Pending TCS. This is the real post-action read.
            var postReadback = new TaskCompletionSource<WorkerCallResult>();
            fake.Pending = postReadback;
            pendingCommand.SetResult(new WorkerCallResult(commandExit, null,
                commandExit == 3 ? "FIXTURE_NONZERO" : "", commandExit == 1223 ? "UAC_CANCELLED" : ""));
            Drain();
            if (commandExit == 3)
                Check(Control<TextBox>(w, "AdvancedText").Text.Contains("FIXTURE_NONZERO"),
                    caseName + " nonzero warning retained without unattended modal dialog");
            Check(!timerRead.IsCompleted && !list.IsEnabled &&
                fake.ContextRequests.Count == readsBefore &&
                !Control<Button>(w, "HomePrimaryButton").IsEnabled,
                caseName + " completed worker does NOT release before canonical readback");
            list.SelectedIndex = 0; Drain();
            Check(list.SelectedItem is not null &&
                list.SelectedItem.GetType().GetProperty("ProjectId")?.GetValue(list.SelectedItem)?.ToString() == "RetailGroup",
                caseName + " programmed cross-project switch remains pinned during pending readback");
            Call(w, continuation ? "Continue_Click" : "Start_Click", w, new RoutedEventArgs()); Drain();
            Check(fake.Calls.Count == callsBefore + 1,
                caseName + " repeated Enter/click cannot open second admission prompt");
            var oldReply = oldPollFails ? new WorkerCallResult(2, null, "", "OLD_TIMER_FAILURE") :
                new WorkerCallResult(0, (JsonObject)eligible.DeepClone(), "", "");
            delayedTimer.SetResult(oldReply); Drain();
            Check(!timerRead.IsCompleted && !list.IsEnabled &&
                fake.ContextRequests.Count == readsBefore + 1 &&
                !Control<Button>(w, "StartButton").IsEnabled &&
                !Control<Button>(w, "ContinueButton").IsEnabled,
                caseName + " even stale/failed timer reply must await real post-action owner read");
            Call(w, continuation ? "Continue_Click" : "Start_Click", w, new RoutedEventArgs()); Drain();
            Check(fake.Calls.Count == callsBefore + 1,
                caseName + " no replay while post-action owner TCS is unresolved");
            WorkerCallResult freshReply;
            if (postOutcome == "ERROR") freshReply = new(2, null, "", "POST_ACTION_CONTEXT_UNAVAILABLE");
            else
            {
                var fresh = FixtureWorker.Context(postOutcome == "FOREIGN" ? "NeoHim" : "RetailGroup",
                    postOutcome == "RUNNING" ? "RUNNING" : "PROJECT_READY");
                if (postOutcome == "MISSING") fresh["selected_project"] = null;
                freshReply = new(0, fresh, "", "");
            }
            postReadback.SetResult(freshReply);
            Pump(timerRead); Drain();
            Check(list.IsEnabled && fake.Calls.Count == callsBefore + 1 &&
                Control<Button>(w, "HomePrimaryButton").IsEnabled,
                caseName + " unlocks only after post-action owner settles");
            if (postOutcome is "ERROR" or "FOREIGN" or "MISSING")
                Check(!Control<Button>(w, "StartButton").IsEnabled &&
                    !Control<Button>(w, "ContinueButton").IsEnabled &&
                    Control<TextBlock>(w, "LastUpdatedText").Text == Localization.Get("WorkspaceVerificationUnknown"),
                    caseName + " invalid post-action owner is UNKNOWN/HOLD, never old START/CONTINUE");
            else if (postOutcome == "RUNNING")
                Check(!Control<Button>(w, "StartButton").IsEnabled &&
                    !Control<Button>(w, "ContinueButton").IsEnabled,
                    caseName + " fresh running task does not mint second START/CONTINUE");
            else
                Check(Control<Button>(w, "StartButton").IsEnabled && commandExit == 1223,
                    caseName + " UAC cancellation restores fresh owner action without hidden replay");
        }
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
        foreach (var language in new[] { "en", "ru" })
        {
            Localization.SetLanguage(language); Call(w, "ApplyLocalization");
            foreach (var reason in new[] { "PROJECT_ADMISSION_ACTIVE", "SOURCE_UPDATE_STATE_INVALID", "RECOVERY_REQUIRED" })
            {
                var blocked = (JsonObject)pending.DeepClone();
                blocked["actions"]!["accept_source_update"] = new JsonObject { ["enabled"] = false, ["reason"] = reason };
                blocked["actions"]!["cancel_source_update"] = new JsonObject { ["enabled"] = reason != "RECOVERY_REQUIRED", ["reason"] = reason == "RECOVERY_REQUIRED" ? reason : "AVAILABLE" };
                Reload(blocked);
                Check(!Control<Button>(w, "AcceptSourceUpdateButton").IsEnabled &&
                    (string?)Control<Button>(w, "AcceptSourceUpdateButton").ToolTip == Presentation.Reason(reason), "owner Accept reason reaches WPF tooltip " + language + " " + reason);
                Check(Control<Button>(w, "CancelSourceUpdateButton").IsEnabled == (reason != "RECOVERY_REQUIRED"), "owner Cancel eligibility reaches WPF " + language + " " + reason);
            }
        }
        Reload(pending);
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
    public TaskCompletionSource<WorkerCallResult>? PendingAdmissionResult;
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
        if ((action is WorkerAction.Start or WorkerAction.Continue) &&
            PendingAdmissionResult is { } pendingAdmission)
        {
            PendingAdmissionResult = null;
            return pendingAdmission.Task;
        }
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
