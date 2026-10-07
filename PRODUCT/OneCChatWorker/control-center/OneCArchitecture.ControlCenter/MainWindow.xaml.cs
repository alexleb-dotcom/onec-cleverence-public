using System.Collections.ObjectModel;
using System.IO;
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;

namespace OneCArchitecture.ControlCenter;

public partial class MainWindow : Window
{
    private readonly WorkerClient _worker = new();
    private readonly DispatcherTimer _timer = new() { Interval = TimeSpan.FromSeconds(4) };
    private UiPreferences _preferences = PreferencesStore.Load();
    private JsonObject? _context;
    private bool _refreshing;
    private bool _mutationsEnabled = true;
    private bool _settingsInitializing;

    private sealed record ProjectRow(string ProjectId, string DisplayName, string State, int Participants);
    private sealed record ActivityRow(string Time, int Seq, string Operation, string Target, long Bytes, string Duration, string Outcome);

    public MainWindow()
    {
        InitializeComponent();
        ApplyLocalization();
        InitializeSettings();
        _timer.Tick += async (_, _) => await RefreshContextAsync();
        Loaded += async (_, _) =>
        {
            ShowPage("Home");
            await RefreshContextAsync();
            _timer.Start();
        };
    }

    private void InitializeSettings()
    {
        _settingsInitializing = true;
        var language = _preferences.Language;
        var theme = _preferences.Theme;
        SelectComboByTag(LanguageCombo, language);
        SelectComboByTag(ThemeCombo, theme);
        StartupCheckBox.IsChecked = _preferences.StartWithWindows;
        _settingsInitializing = false;
    }

    private static void SelectComboByTag(System.Windows.Controls.ComboBox combo, string value)
    {
        foreach (var item in combo.Items.OfType<ComboBoxItem>())
        {
            if (string.Equals(item.Tag?.ToString(), value, StringComparison.OrdinalIgnoreCase))
            {
                combo.SelectedItem = item;
                return;
            }
        }
        combo.SelectedIndex = 0;
    }

    private void ApplyLocalization()
    {
        Title = Localization.Get("AppTitle");
        NavHomeButton.Content = Localization.Get("NavHome");
        NavProjectsButton.Content = Localization.Get("NavProjects");
        NavWorkButton.Content = Localization.Get("NavWork");
        NavActivityButton.Content = Localization.Get("NavActivity");
        NavMaintenanceButton.Content = Localization.Get("NavMaintenance");
        NavSettingsButton.Content = Localization.Get("NavSettings");
        NavAdvancedButton.Content = Localization.Get("NavAdvanced");
        CurrentWorkLabel.Text = Localization.Get("CurrentWork");
        RecommendedLabel.Text = Localization.Get("Recommended");
        McpTitleLabel.Text = Localization.Get("McpTitle");
        CheckpointTitleLabel.Text = Localization.Get("CheckpointTitle");
        SourceTitleLabel.Text = Localization.Get("SourceTitle");
        OutputTitleLabel.Text = Localization.Get("OutputTitle");
        RefreshButton.Content = Localization.Get("Refresh");
        HomeOpenOutputButton.Content = Localization.Get("OpenOutput");
        HomeOpenSourceButton.Content = Localization.Get("OpenSource");
        OpenSourceButton.Content = Localization.Get("OpenSource");
        StartButton.Content = Localization.Get("StartWork");
        ContinueButton.Content = Localization.Get("ContinueWork");
        StopButton.Content = Localization.Get("StopWork");
        HomeStopButton.Content = Localization.Get("StopWork");
        ApplyButton.Content = Localization.Get("ApplyRefresh");
        MaintenanceApplyButton.Content = Localization.Get("ApplyRefresh");
        VerifyButton.Content = Localization.Get("Verify");
        RepairButton.Content = Localization.Get("Repair");
        UpdateButton.Content = Localization.Get("Update");
        LanguageLabel.Text = Localization.Get("Language");
        ThemeLabel.Text = Localization.Get("Theme");
        CloseHintText.Text = Localization.Get("CloseHint");
    }

    private async Task RefreshContextAsync()
    {
        if (_refreshing) return;
        _refreshing = true;
        try
        {
            var result = await _worker.GetContextAsync();
            if (result.ExitCode != 0 || result.Json is null)
            {
                RecommendationText.Text = "UI_CONTEXT unavailable";
                RecommendationReasonText.Text = string.IsNullOrWhiteSpace(result.StandardError)
                    ? $"Worker exit={result.ExitCode}" : result.StandardError.Trim();
                HelperBadge.Text = "Helper —";
                return;
            }
            _context = result.Json;
            ApplyContext(result.Json);
        }
        catch (Exception ex)
        {
            RecommendationText.Text = "UI_CONTEXT unavailable";
            RecommendationReasonText.Text = ex.Message;
        }
        finally { _refreshing = false; }
    }

    private void ApplyContext(JsonObject ctx)
    {
        ProductVersionText.Text = $"Control Center · Worker {Text(ctx, "product", "version") ?? "—"}";
        LastUpdatedText.Text = $"Updated {DateTime.Now:T}";
        var helper = Text(ctx, "work", "helper", "status") ?? "OFFLINE";
        HelperBadge.Text = $"Helper · {helper}";
        RecommendationText.Text = Text(ctx, "recommendation", "action") ?? "—";
        RecommendationReasonText.Text = Text(ctx, "recommendation", "reason") ?? "";

        var projectName = Text(ctx, "selected_project", "display_name") ?? Text(ctx, "work", "project_id") ?? "—";
        var taskGoal = Text(ctx, "work", "task_goal");
        HomeProjectText.Text = projectName;
        HomeTaskText.Text = taskGoal ?? Localization.Get("NoActiveTask");
        HomeHelperText.Text = $"Helper: {helper}";

        SourceStateText.Text = Text(ctx, "source", "state") ?? "—";
        var checkpoint = Node(ctx, "work", "checkpoint") as JsonObject;
        CheckpointStateText.Text = checkpoint is null ? "No checkpoint" : (Text(checkpoint, "head_status") ?? "Available");
        CheckpointSummaryText.Text = checkpoint is null
            ? "Semantic recovery state is not available for the current task."
            : $"seq {Text(checkpoint, "head_seq") ?? "—"} · {Text(checkpoint, "updated_utc") ?? ""}";
        WorkCheckpointText.Text = checkpoint is null
            ? "No verified TASK_CHECKPOINT_V1 is available."
            : $"Checkpoint {Text(checkpoint, "head_seq")} · {Text(checkpoint, "head_status")} · {Text(checkpoint, "updated_utc")}";

        var output = Node(ctx, "output") as JsonObject;
        var taskCount = Long(output, "task_count");
        OutputStateText.Text = output is null ? "No Output" : $"{taskCount} task folder(s)";
        OutputSummaryText.Text = GetProposalSummary(output);

        var s4Available = Bool(ctx, "s4", "accounting_available");
        McpStateText.Text = s4Available ? (Text(ctx, "s4", "projection", "task_state") ?? "ACTIVE") : Localization.Get("AccountingUnavailable");
        var usedReq = Long(ctx, "s4", "projection", "accounting", "task_requests_used");
        var usedBytes = Long(ctx, "s4", "projection", "accounting", "task_result_bytes_used");
        McpUsageText.Text = s4Available ? $"{usedReq} requests · {usedBytes:N0} bytes returned" : "Relay accounting projection is not available.";
        var epoch = Long(ctx, "s4", "projection", "epoch_seq");
        var rollovers = Long(ctx, "s4", "projection", "activity", "epoch_rollovers");
        McpEpochText.Text = s4Available ? $"Epoch {epoch} · {rollovers} rollover(s)" : "";
        McpPolicyText.Text = Localization.Get("AccountingPending");

        WorkStatusText.Text = Bool(ctx, "work", "active") ? projectName : Localization.Get("NoActiveTask");
        WorkDetailText.Text = taskGoal ?? Text(ctx, "recommendation", "reason") ?? "";

        var projects = new ObservableCollection<ProjectRow>();
        if (Node(ctx, "projects") is JsonArray arr)
        {
            foreach (var n in arr.OfType<JsonObject>())
                projects.Add(new(
                    Text(n, "project_id") ?? "",
                    Text(n, "display_name") ?? Text(n, "project_id") ?? "",
                    Text(n, "readiness") ?? Text(n, "fast_state") ?? "—",
                    (int)Long(n, "participant_count")));
        }
        ProjectsList.ItemsSource = projects;

        var activities = new ObservableCollection<ActivityRow>();
        if (Node(ctx, "s4", "projection", "activity", "events") is JsonArray events)
        {
            foreach (var n in events.OfType<JsonObject>())
            {
                var target = Text(n, "safe_result", "path")
                    ?? Text(n, "safe_request", "path")
                    ?? Text(n, "safe_request", "query")
                    ?? "—";
                var time = Text(n, "committed_utc") ?? Text(n, "created_utc") ?? "—";
                var durationMs = Double(n, "safe_result", "duration_ms");
                var outcome = Text(n, "safe_result", "status") ?? Text(n, "state") ?? "—";
                if (Bool(n, "safe_result", "read_back_verified")) outcome += " · read-back";
                activities.Add(new(
                    time,
                    (int)Long(n, "seq"),
                    Text(n, "op") ?? "—",
                    target,
                    Long(n, "charged_bytes"),
                    durationMs > 0 ? $"{durationMs:N1} ms" : "—",
                    outcome));
            }
        }
        ActivityList.ItemsSource = activities;
        ActivitySummaryText.Text = s4Available
            ? $"Authoritative relay activity · {usedReq} durable requests · {usedBytes:N0} bytes"
            : Localization.Get("AccountingUnavailable");

        var opType = Text(ctx, "operation", "current", "operation_type");
        var opState = Text(ctx, "operation", "current", "state");
        var opMessage = Text(ctx, "operation", "current", "message");
        OperationText.Text = opType is null ? "No operation in progress." : $"{opType} · {opState}\n{opMessage}";
        DiagnosticsText.Text = $"State: {Text(ctx, "recommendation", "state")}\nRecovery: {Text(ctx, "operation", "recovery", "classification")}\nFast contract: {Text(ctx, "state_check_contract")}";

        AdvancedText.Text = ctx.ToJsonString(new JsonSerializerOptions { WriteIndented = true });
        UpdateReadOnlyAvailability(ctx);
    }

    private void UpdateReadOnlyAvailability(JsonObject ctx)
    {
        var source = Text(ctx, "navigation", "source_root");
        var output = Text(ctx, "navigation", "output_root");
        HomeOpenSourceButton.IsEnabled = OpenSourceButton.IsEnabled = !string.IsNullOrWhiteSpace(source);
        HomeOpenOutputButton.IsEnabled = !string.IsNullOrWhiteSpace(output);

        var active = Bool(ctx, "work", "active");
        var state = Text(ctx, "recommendation", "state") ?? "";
        StartButton.IsEnabled = _mutationsEnabled && !active && state == "PROJECT_READY";
        ContinueButton.IsEnabled = _mutationsEnabled && state == "CONTINUE_AVAILABLE";
        StopButton.IsEnabled = HomeStopButton.IsEnabled = _mutationsEnabled && active;
        ApplyButton.IsEnabled = MaintenanceApplyButton.IsEnabled = _mutationsEnabled && state is "PROJECT_NEEDS_APPLY" or "PROJECT_READY";
        VerifyButton.IsEnabled = _mutationsEnabled && state == "PROJECT_NEEDS_VERIFY";
        RepairButton.IsEnabled = _mutationsEnabled && state is "PROJECT_NEEDS_VERIFY" or "RECOVERY_REQUIRED";
        UpdateButton.IsEnabled = _mutationsEnabled;
        AddProjectButton.IsEnabled = _mutationsEnabled;
    }

    private void Nav_Click(object sender, RoutedEventArgs e)
    {
        if (sender is System.Windows.Controls.Button b && b.Tag is string page) ShowPage(page);
    }

    private void ShowPage(string name)
    {
        foreach (var control in new FrameworkElement[] { HomePage, ProjectsPage, WorkPage, ActivityPage, MaintenancePage, SettingsPage, AdvancedPage })
            control.Visibility = Visibility.Collapsed;
        FrameworkElement target = name switch
        {
            "Projects" => ProjectsPage, "Work" => WorkPage, "Activity" => ActivityPage,
            "Maintenance" => MaintenancePage, "Settings" => SettingsPage, "Advanced" => AdvancedPage, _ => HomePage
        };
        target.Visibility = Visibility.Visible;
        PageTitle.Text = name switch
        {
            "Projects" => Localization.Get("NavProjects"), "Work" => Localization.Get("NavWork"),
            "Activity" => Localization.Get("NavActivity"), "Maintenance" => Localization.Get("NavMaintenance"),
            "Settings" => Localization.Get("NavSettings"), "Advanced" => Localization.Get("NavAdvanced"),
            _ => Localization.Get("NavHome")
        };
    }

    private async void Refresh_Click(object sender, RoutedEventArgs e) => await RefreshContextAsync();

    private void OpenSource_Click(object sender, RoutedEventArgs e) => OpenFolder(Text(_context, "navigation", "source_root"));
    private void OpenOutput_Click(object sender, RoutedEventArgs e) => OpenFolder(Text(_context, "navigation", "output_root"));
    private static void OpenFolder(string? path)
    {
        if (string.IsNullOrWhiteSpace(path) || !Directory.Exists(path)) return;
        var psi = new ProcessStartInfo("explorer.exe") { UseShellExecute = false };
        psi.ArgumentList.Add(path);
        Process.Start(psi);
    }

    private async void Start_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled || _context is null) return;
        var projectId = Text(_context, "selected_project", "project_id");
        var goal = TaskGoalTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(projectId) || string.IsNullOrWhiteSpace(goal)) return;
        var result = await _worker.RunAsync(WorkerAction.Start, new(ProjectId: projectId, TaskId: WorkerClient.CreateTaskId(goal), TaskGoal: goal));
        await ShowActionResultAndRefresh("START", result);
    }

    private async void Continue_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled) return;
        var result = await _worker.RunAsync(WorkerAction.Continue, new());
        await ShowActionResultAndRefresh("CONTINUE", result);
    }

    private async void Stop_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled) return;
        if (System.Windows.MessageBox.Show(Localization.Get("StopWork") + "?", Localization.Get("AppTitle"), MessageBoxButton.YesNo, MessageBoxImage.Question) != MessageBoxResult.Yes) return;
        var result = await _worker.RunAsync(WorkerAction.Stop, new(), elevated: true);
        await ShowActionResultAndRefresh("STOP", result);
    }

    private async void Apply_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled || _context is null) return;
        var projectId = Text(_context, "selected_project", "project_id");
        if (string.IsNullOrWhiteSpace(projectId)) return;
        var result = await _worker.RunAsync(WorkerAction.Apply, new(ProjectId: projectId));
        await ShowActionResultAndRefresh("APPLY", result);
    }

    private async void Verify_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled || _context is null) return;
        var projectId = Text(_context, "selected_project", "project_id");
        if (string.IsNullOrWhiteSpace(projectId)) return;
        var result = await _worker.RunAsync(WorkerAction.Verify, new(ProjectId: projectId));
        await ShowActionResultAndRefresh("VERIFY", result);
    }

    private async void Repair_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled || _context is null) return;
        var projectId = Text(_context, "selected_project", "project_id");
        if (string.IsNullOrWhiteSpace(projectId)) return;
        var result = await _worker.RunAsync(WorkerAction.Repair, new(ProjectId: projectId), elevated: true);
        await ShowActionResultAndRefresh("REPAIR", result);
    }

    private async void Update_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled) return;
        var result = await _worker.RunAsync(WorkerAction.Update, new(), elevated: true);
        await ShowActionResultAndRefresh("UPDATE", result);
    }

    private async void AddProject_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled) return;
        var wizard = new ProjectWizardWindow { Owner = this };
        if (wizard.ShowDialog() != true || wizard.Result is null) return;
        var w = wizard.Result;

        var steps = new (WorkerAction Action, WorkerActionArgs Args, string Name)[]
        {
            (WorkerAction.AddProject, new(DisplayName: w.ProjectName, ProjectId: w.ProjectId), "ADD_PROJECT"),
            (WorkerAction.AddParticipant, new(ProjectId: w.ProjectId, ParticipantId: w.ParticipantId, Role: w.Role), "ADD_PARTICIPANT"),
            (WorkerAction.SetMain, new(ProjectId: w.ProjectId, ParticipantId: w.ParticipantId, SourcePath: w.MainPath), "SET_MAIN")
        };
        foreach (var step in steps)
        {
            var result = await _worker.RunAsync(step.Action, step.Args);
            if (result.ExitCode != 0)
            {
                System.Windows.MessageBox.Show($"{step.Name}: {result.StandardError}", Localization.Get("AppTitle"), MessageBoxButton.OK, MessageBoxImage.Warning);
                await RefreshContextAsync();
                return;
            }
        }

        if (!string.IsNullOrWhiteSpace(w.ExtensionId) && !string.IsNullOrWhiteSpace(w.ExtensionPath))
        {
            var ext = await _worker.RunAsync(
                WorkerAction.AddExtension,
                new(ProjectId: w.ProjectId, ParticipantId: w.ParticipantId, ExtensionId: w.ExtensionId, SourcePath: w.ExtensionPath));
            if (ext.ExitCode != 0)
            {
                System.Windows.MessageBox.Show($"ADD_EXTENSION: {ext.StandardError}", Localization.Get("AppTitle"), MessageBoxButton.OK, MessageBoxImage.Warning);
                await RefreshContextAsync();
                return;
            }
        }

        var apply = await _worker.RunAsync(WorkerAction.Apply, new(ProjectId: w.ProjectId));
        await ShowActionResultAndRefresh("APPLY", apply);
    }

    private async Task ShowActionResultAndRefresh(string action, WorkerCallResult result)
    {
        if (result.ExitCode != 0 && result.ExitCode != 1223)
            System.Windows.MessageBox.Show($"{action}: {result.StandardError}", Localization.Get("AppTitle"), MessageBoxButton.OK, MessageBoxImage.Warning);
        await RefreshContextAsync();
    }

    private void ThemeCombo_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_settingsInitializing || ThemeCombo.SelectedItem is not ComboBoxItem item) return;
        var theme = item.Tag?.ToString() ?? "system";
        _preferences = _preferences with { Theme = theme };
        PreferencesStore.Save(_preferences);
        ThemeService.Apply(theme);
    }

    private void LanguageCombo_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_settingsInitializing || LanguageCombo.SelectedItem is not ComboBoxItem item) return;
        var lang = item.Tag?.ToString() ?? "system";
        _preferences = _preferences with { Language = lang };
        PreferencesStore.Save(_preferences);
        var resolved = lang == "system"
            ? (System.Globalization.CultureInfo.CurrentUICulture.Name.StartsWith("ru", StringComparison.OrdinalIgnoreCase) ? "ru" : "en")
            : lang;
        Localization.SetLanguage(resolved);
        ApplyLocalization();
        ShowPage(HomePage.Visibility == Visibility.Visible ? "Home" :
            ProjectsPage.Visibility == Visibility.Visible ? "Projects" :
            WorkPage.Visibility == Visibility.Visible ? "Work" :
            ActivityPage.Visibility == Visibility.Visible ? "Activity" :
            MaintenancePage.Visibility == Visibility.Visible ? "Maintenance" :
            SettingsPage.Visibility == Visibility.Visible ? "Settings" : "Advanced");
    }

    private void StartupCheckBox_Changed(object sender, RoutedEventArgs e)
    {
        if (_settingsInitializing) return;
        _preferences = _preferences with { StartWithWindows = StartupCheckBox.IsChecked == true };
        PreferencesStore.Save(_preferences);
        try { StartupRegistration.Apply(_preferences.StartWithWindows); }
        catch (Exception ex)
        {
            System.Windows.MessageBox.Show($"Startup preference could not be applied: {ex.Message}", Localization.Get("AppTitle"), MessageBoxButton.OK, MessageBoxImage.Warning);
        }
    }

    private void Window_Closing(object? sender, System.ComponentModel.CancelEventArgs e)
    {
        if (App.IsExplicitExit) return;
        e.Cancel = true;
        Hide();
    }

    private static JsonNode? Node(JsonNode? node, params string[] path)
    {
        JsonNode? cur = node;
        foreach (var part in path)
        {
            if (cur is not JsonObject obj || !obj.TryGetPropertyValue(part, out cur)) return null;
        }
        return cur;
    }

    private static string? Text(JsonNode? node, params string[] path)
    {
        var n = Node(node, path);
        if (n is null) return null;
        try { return n.GetValue<string>(); } catch { return n.ToJsonString().Trim('"'); }
    }

    private static long Long(JsonNode? node, params string[] path)
    {
        var n = Node(node, path);
        if (n is null) return 0;
        try { return n.GetValue<long>(); } catch { return 0; }
    }

    private static bool Bool(JsonNode? node, params string[] path)
    {
        var n = Node(node, path);
        if (n is null) return false;
        try { return n.GetValue<bool>(); } catch { return false; }
    }

    private static double Double(JsonNode? node, params string[] path)
    {
        var n = Node(node, path);
        if (n is null) return 0;
        try { return n.GetValue<double>(); } catch { return 0; }
    }

    private static string GetProposalSummary(JsonObject? output)
    {
        if (output?["tasks"] is not JsonArray tasks || tasks.Count == 0) return "No proposal receipts.";
        var latest = tasks.OfType<JsonObject>().FirstOrDefault();
        if (latest is null) return "No proposal receipts.";
        return $"{Text(latest, "task_id")} · {Text(latest, "status") ?? "PROPOSAL_NOT_APPLIED"} · {Long(latest, "proposal_files")} file(s)";
    }
}
