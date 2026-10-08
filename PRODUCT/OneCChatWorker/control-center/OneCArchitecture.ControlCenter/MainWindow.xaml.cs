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
    private readonly IWorkerClient _worker;
    private readonly DispatcherTimer _timer = new() { Interval = TimeSpan.FromSeconds(4) };
    private UiPreferences _preferences;
    private JsonObject? _context;
    private bool _refreshing;
    private bool _mutationsEnabled = true;
    private bool _settingsInitializing;
    private bool _applyingContext;
    private bool _refreshAgain;
    private bool _contextReady;
    private string? _selectedProjectId;

    private sealed record ProjectRow(string ProjectId, string DisplayName, string State, int Participants);
    private sealed record ActivityRow(string Time, int Seq, string Operation, string Target, long Bytes, string Duration, string Outcome);
    private sealed record ArtifactRow(string Key, string Display, string ParticipantId, string ArtifactType, string ArtifactId, long Files, long Bytes);
    private string _lastDiagnostic = "";

    public MainWindow() : this(new WorkerClient(), false) { }

    internal MainWindow(IWorkerClient worker, bool fixture)
    {
        _worker = worker;
        _preferences = fixture ? new() : PreferencesStore.Load();
        InitializeComponent();
        ApplyLocalization();
        InitializeSettings();
        DisableActions(Localization.Get("LoadingProject"));
        ProjectsHintText.Text = Localization.Get("LoadingProject");
        _timer.Tick += async (_, _) => await RefreshContextAsync();
        ShowPage("Home");
        if (!fixture) Loaded += async (_, _) =>
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
        AddProjectButton.Content = Localization.Get("AddProject");
        WorkPromptLabel.Text = Localization.Get("WorkPrompt");
        WorkRecoveryLabel.Text = Localization.Get("WorkRecovery");
        CurrentOperationLabel.Text = Localization.Get("CurrentOperation");
        DiagnosticsLabel.Text = Localization.Get("Diagnostics");
        SourceUpdateTitleLabel.Text = Localization.Get("SourceUpdateTitle");
        SourceUpdateSelectLabel.Text = Localization.Get("SourceUpdateArtifact");
        PrepareSourceUpdateButton.Content = Localization.Get("PrepareSourceUpdate");
        OpenIncomingButton.Content = Localization.Get("OpenIncoming");
        AcceptSourceUpdateButton.Content = Localization.Get("AcceptSourceUpdate");
        CancelSourceUpdateButton.Content = Localization.Get("CancelSourceUpdate");
        LanguageLabel.Text = Localization.Get("Language");
        ThemeLabel.Text = Localization.Get("Theme");
        LanguageSystemItem.Content = Localization.Get("LanguageSystem");
        LanguageRuItem.Content = Localization.Get("LanguageRussian");
        LanguageEnItem.Content = Localization.Get("LanguageEnglish");
        ThemeSystemItem.Content = Localization.Get("ThemeSystem");
        ThemeLightItem.Content = Localization.Get("ThemeLight");
        ThemeDarkItem.Content = Localization.Get("ThemeDark");
        StartupCheckBox.Content = Localization.Get("StartupChoice");
        AdvancedTitleLabel.Text = Localization.Get("AdvancedTitle");
        CloseHintText.Text = Localization.Get("CloseHint");
        foreach (var button in ActionButtons().Select(p => p.Button).Concat(new[] {
            NavHomeButton, NavProjectsButton, NavWorkButton, NavActivityButton, NavMaintenanceButton,
            NavSettingsButton, NavAdvancedButton, RefreshButton, HomeOpenSourceButton, HomeOpenOutputButton,
            OpenSourceButton, OpenIncomingButton }))
            System.Windows.Automation.AutomationProperties.SetName(button, button.Content?.ToString() ?? "");
        System.Windows.Automation.AutomationProperties.SetName(ProjectsList, Localization.Get("NavProjects"));
        System.Windows.Automation.AutomationProperties.SetName(ActivityList, Localization.Get("NavActivity"));
        System.Windows.Automation.AutomationProperties.SetName(TaskGoalTextBox, Localization.Get("WorkPrompt"));

        if (ProjectsList.View is GridView projectsView && projectsView.Columns.Count >= 3)
        {
            projectsView.Columns[0].Header = Localization.Get("ProjectHeader");
            projectsView.Columns[1].Header = Localization.Get("StateHeader");
            projectsView.Columns[2].Header = Localization.Get("ParticipantsHeader");
        }
        if (ActivityList.Columns.Count >= 7)
        {
            ActivityList.Columns[0].Header = Localization.Get("TimeHeader");
            ActivityList.Columns[1].Header = Localization.Get("SeqHeader");
            ActivityList.Columns[2].Header = Localization.Get("OperationHeader");
            ActivityList.Columns[3].Header = Localization.Get("TargetHeader");
            ActivityList.Columns[4].Header = Localization.Get("BytesHeader");
            ActivityList.Columns[5].Header = Localization.Get("DurationHeader");
            ActivityList.Columns[6].Header = Localization.Get("OutcomeHeader");
        }
    }

    private async Task RefreshContextAsync()
    {
        if (_refreshing) { _refreshAgain = true; return; }
        _refreshing = true;
        try
        {
          do
          {
            _refreshAgain = false;
            var requestedProject = _selectedProjectId;
            var result = await _worker.GetContextAsync(requestedProject);
            if (requestedProject != _selectedProjectId) { _refreshAgain = true; continue; }
            if (result.ExitCode != 0 || result.Json is null)
            {
                ShowContextFailure(result.ExitCode, result.StandardError, result.StandardOutput);
                return;
            }
            _context = result.Json;
            _contextReady = true;
            if (_selectedProjectId is null) _selectedProjectId = Text(result.Json, "selected_project", "project_id");
            _lastDiagnostic = "";
            ApplyContext(result.Json);
          } while (_refreshAgain);
        }
        catch (Exception ex)
        {
            ShowContextFailure(-1, ex.ToString(), "");
        }
        finally { _refreshing = false; }
    }

    private void ShowContextFailure(int exitCode, string? stderr, string? stdout)
    {
        var raw = string.Join(Environment.NewLine, new[] { stderr, stdout }.Where(x => !string.IsNullOrWhiteSpace(x))).Trim();
        _lastDiagnostic = Bound(raw, 4000);
        _contextReady = false;
        _context = null;
        DisableActions(Localization.Get("UiContextReason"));
        SourceStateText.Text = McpStateText.Text = WorkStatusText.Text = Localization.Get("UnknownState");
        WorkDetailText.Text = Localization.Get("UiContextReason");
        RecommendationText.Text = Localization.Get("UiContextUnavailable");
        RecommendationReasonText.Text = Localization.Get("UiContextReason") +
            (exitCode >= 0 ? $" {Localization.Get("WorkerExit")}: {exitCode}." : "");
        HelperBadge.Text = Localization.Get("HelperLabel") + " · —";
        DiagnosticsText.Text = Localization.Get("UiContextUnavailable");
        AdvancedText.Text = string.IsNullOrWhiteSpace(_lastDiagnostic)
            ? $"{Localization.Get("WorkerExit")}: {exitCode}"
            : _lastDiagnostic;
    }

    private static string Bound(string? value, int maxChars)
    {
        if (string.IsNullOrWhiteSpace(value)) return "";
        var single = value.Replace("\r", " ").Replace("\n", " ").Replace("\t", " ").Trim();
        while (single.Contains("  ", StringComparison.Ordinal)) single = single.Replace("  ", " ", StringComparison.Ordinal);
        return single.Length <= maxChars ? single : single[..maxChars] + "…";
    }

    private void ApplyContext(JsonObject ctx)
    {
        ProductVersionText.Text = $"Control Center · Worker {Text(ctx, "product", "version") ?? "—"}";
        LastUpdatedText.Text = $"{Localization.Get("UpdatedLabel")} {DateTime.Now:T}";
        var helper = Text(ctx, "work", "helper", "status") ?? "OFFLINE";
        HelperBadge.Text = $"{Localization.Get("HelperLabel")} · {helper}";

        var recommendationState = Text(ctx, "recommendation", "state") ?? "";
        RecommendationText.Text = RecommendationTitle(recommendationState);
        RecommendationReasonText.Text = Presentation.Reason(recommendationState) + "\n" + Localization.Get("ReadOnlyPreservation");

        var projectName = Text(ctx, "selected_project", "display_name") ?? Localization.Get("ChooseProject");
        var workProjectId = Text(ctx, "work", "project_id");
        var workProjectName = (Node(ctx, "projects") as JsonArray)?.OfType<JsonObject>()
            .FirstOrDefault(p => Text(p, "project_id") == workProjectId)?["display_name"]?.GetValue<string>() ?? workProjectId;
        var taskGoal = Text(ctx, "work", "task_goal");
        HomeProjectText.Text = projectName;
        SelectedProjectText.Text = Localization.Get("SelectedProject") + ": " + projectName;
        HomeTaskText.Text = Bool(ctx, "work", "active")
            ? $"{Localization.Get("CurrentWork")}: {workProjectName}\n{taskGoal}" : Localization.Get("NoActiveTask");
        HomeHelperText.Text = Presentation.Status(helper);
        HelperBadge.Text = Presentation.Status(helper);

        SourceStateText.Text = Presentation.Status(Text(ctx, "source", "state"));
        var checkpoint = Node(ctx, "work", "checkpoint") as JsonObject;
        CheckpointStateText.Text = checkpoint is null ? Localization.Get("NoCheckpoint") : Localization.Get("CheckpointAvailable");
        CheckpointSummaryText.Text = checkpoint is null
            ? Localization.Get("CheckpointNoRecovery")
            : $"#{Text(checkpoint, "head_seq") ?? "—"} · {Text(checkpoint, "updated_utc") ?? ""}";
        WorkCheckpointText.Text = checkpoint is null
            ? Localization.Get("CheckpointVerified")
            : $"#{Text(checkpoint, "head_seq")} · {Text(checkpoint, "updated_utc")}";

        var output = Node(ctx, "output") as JsonObject;
        var taskCount = Long(output, "task_count");
        OutputStateText.Text = output is null ? Localization.Get("NoOutput") : $"{taskCount} {Localization.Get("OutputTasks")}";
        OutputSummaryText.Text = GetProposalSummary(output);

        var s4Available = Bool(ctx, "s4", "accounting_available");
        McpStateText.Text = s4Available ? Presentation.Status(Text(ctx, "s4", "projection", "task_state")) : Localization.Get("AccountingUnavailable");
        var usedReq = Long(ctx, "s4", "projection", "accounting", "task_requests_used");
        var usedBytes = Long(ctx, "s4", "projection", "accounting", "task_result_bytes_used");
        McpUsageText.Text = s4Available
            ? $"{usedReq:N0} · {usedBytes:N0} {Localization.Get("BytesHeader")}"
            : Localization.Get("RelayUnavailable");
        McpEpochText.Text = Presentation.Expiry(Text(ctx, "work", "task_expires_utc"));
        McpPolicyText.Text = Localization.Get("AccountingPending");

        WorkStatusText.Text = Bool(ctx, "work", "active") ? workProjectName : projectName;
        WorkDetailText.Text = Presentation.Reason(recommendationState) + "\n" + Presentation.Expiry(Text(ctx, "work", "task_expires_utc"));
        SessionHelpText.Text = Localization.Get("SessionHelp");

        var projects = new ObservableCollection<ProjectRow>();
        if (Node(ctx, "projects") is JsonArray arr)
        {
            foreach (var n in arr.OfType<JsonObject>())
                projects.Add(new(
                    Text(n, "project_id") ?? "",
                    Text(n, "display_name") ?? Text(n, "project_id") ?? "",
                    Presentation.Status(Text(n, "fast_state") ?? Text(n, "readiness")),
                    (int)Long(n, "participant_count")));
        }
        _applyingContext = true;
        ProjectsList.ItemsSource = projects;
        ProjectsList.SelectedItem = projects.FirstOrDefault(p => p.ProjectId == _selectedProjectId);
        _applyingContext = false;
        ProjectsHintText.Text = projects.Count == 0 ? Localization.Get("NoProjects") : Localization.Get("ProjectSelectionHelp");
        var otherWarnings = (Node(ctx, "projects") as JsonArray)?.OfType<JsonObject>()
            .Where(p => Text(p, "project_id") != _selectedProjectId && Text(p, "fast_state") != "ACCEPTED" && Bool(p, "active"))
            .Select(p => Text(p, "display_name") ?? "").ToArray() ?? [];
        GlobalWarningText.Text = otherWarnings.Length == 0 ? "" : Localization.Get("OtherProjectsWarning") + ": " + string.Join(", ", otherWarnings);

        var previousArtifactKey = (SourceArtifactCombo.SelectedItem as ArtifactRow)?.Key;
        var artifacts = new ObservableCollection<ArtifactRow>();
        if (Node(ctx, "source", "artifacts") is JsonArray artifactArray)
        {
            foreach (var n in artifactArray.OfType<JsonObject>())
            {
                var key = Text(n, "key") ?? "";
                var participantId = Text(n, "participant_id") ?? "";
                var artifactType = Text(n, "artifact_type") ?? "";
                var artifactId = Text(n, "artifact_id") ?? "";
                var files = Long(n, "files");
                var bytes = Long(n, "bytes");
                var kind = artifactType == "MAIN" ? Localization.Get("ArtifactMain") : Localization.Get("ArtifactExtension");
                var display = $"{kind} · {participantId} / {artifactId} · {files:N0} · {bytes:N0} {Localization.Get("BytesHeader")}";
                artifacts.Add(new(key, display, participantId, artifactType, artifactId, files, bytes));
            }
        }
        SourceArtifactCombo.ItemsSource = artifacts;
        SourceArtifactCombo.SelectedItem = artifacts.FirstOrDefault(a => a.Key == previousArtifactKey) ?? artifacts.FirstOrDefault();

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
                outcome = Presentation.Outcome(outcome);
                if (Bool(n, "safe_result", "read_back_verified")) outcome += " · " + Localization.Get("Verified");
                activities.Add(new(
                    time,
                    (int)Long(n, "seq"),
                    Presentation.Operation(Text(n, "op")),
                    target,
                    Long(n, "charged_bytes"),
                    durationMs > 0 ? $"{durationMs:N1} ms" : "—",
                    outcome));
            }
        }
        ActivityList.ItemsSource = activities;
        ActivitySummaryText.Text = s4Available
            ? $"{Localization.Get("ActivitySummary")} · {usedReq:N0} · {usedBytes:N0} {Localization.Get("BytesHeader")}"
            : Localization.Get("AccountingUnavailable");

        var opType = Text(ctx, "operation", "current", "operation_type");
        var opState = Text(ctx, "operation", "current", "state");
        OperationText.Text = opType is null ? Localization.Get("NoOperation") : $"{Presentation.Operation(opType)} · {Presentation.Status(opState)}";
        DiagnosticsText.Text = Presentation.Reason(recommendationState) + "\n" + Localization.Get("PackageIsNotConnection") + "\n" + Localization.Get("ReadOnlyPreservation");

        var updateStatus = Text(ctx, "source", "source_update", "status") ?? "NONE";
        SourceUpdateStatusText.Text = updateStatus == "NONE"
            ? $"{Localization.Get("SourceUpdateNone")} {Localization.Get("SourceUpdateChoose")}"
            : $"{Localization.Get("SourceUpdateTitle")}: {Presentation.Status(updateStatus)}";

        AdvancedText.Text = ctx.ToJsonString(new JsonSerializerOptions { WriteIndented = true });
        UpdateReadOnlyAvailability(ctx);
    }

    private string RecommendationTitle(string state) => Presentation.Status(state);

    private void UpdateReadOnlyAvailability(JsonObject ctx)
    {
        var source = Text(ctx, "navigation", "source_root");
        var output = Text(ctx, "navigation", "output_root");
        HomeOpenSourceButton.IsEnabled = OpenSourceButton.IsEnabled = !string.IsNullOrWhiteSpace(source);
        HomeOpenOutputButton.IsEnabled = !string.IsNullOrWhiteSpace(output);

        var updateStatus = Text(ctx, "source", "source_update", "status") ?? "NONE";
        var sourceUpdateActive = updateStatus != "NONE";
        var slotPath = FirstSourceUpdateSlotPath(ctx);

        foreach (var (button, key) in ActionButtons())
        {
            button.IsEnabled = _mutationsEnabled && _contextReady && Bool(ctx, "actions", key, "enabled");
            button.ToolTip = button.IsEnabled ? Localization.Get("ReadOnlyPreservation")
                : !_contextReady ? Localization.Get("LoadingProject")
                : !_mutationsEnabled ? Localization.Get("ActionInProgress")
                : Presentation.Reason(Text(ctx, "actions", key, "reason"));
            System.Windows.Automation.AutomationProperties.SetHelpText(button, button.ToolTip?.ToString() ?? "");
        }
        ActionAvailabilityText.Text = (StartButton.IsEnabled ? Localization.Get("StartAccessHelp") : "") + "\n" +
            string.Join("\n", ActionButtons().Where(p => p.Key is "start" or "continue" or "stop" && p.Button != HomeStopButton && !p.Button.IsEnabled)
                .Select(p => $"{p.Button.Content}: {p.Button.ToolTip}"));
        MaintenanceAvailabilityText.Text = string.Join("\n", ActionButtons().Where(p => p.Key is "apply" or "verify" or "repair" or "prepare_source_update" or "accept_source_update" or "cancel_source_update" && p.Button != ApplyButton && !p.Button.IsEnabled)
            .Select(p => $"{p.Button.Content}: {p.Button.ToolTip}"));
        OpenIncomingButton.IsEnabled = sourceUpdateActive && !string.IsNullOrWhiteSpace(slotPath) && Directory.Exists(slotPath);
        OpenIncomingButton.ToolTip = Localization.Get("IncomingUnavailable");
        HomeOpenSourceButton.ToolTip = OpenSourceButton.ToolTip = Localization.Get("SourceUnavailable");
        HomeOpenOutputButton.ToolTip = Localization.Get("OutputUnavailable");
    }

    private IEnumerable<(System.Windows.Controls.Button Button, string Key)> ActionButtons() =>
    [ (StartButton, "start"), (ContinueButton, "continue"), (StopButton, "stop"), (HomeStopButton, "stop"),
      (ApplyButton, "apply"), (MaintenanceApplyButton, "apply"), (VerifyButton, "verify"), (RepairButton, "repair"),
      (UpdateButton, "update"), (AddProjectButton, "add_project"), (PrepareSourceUpdateButton, "prepare_source_update"),
      (AcceptSourceUpdateButton, "accept_source_update"), (CancelSourceUpdateButton, "cancel_source_update") ];

    private void DisableActions(string reason)
    {
        foreach (var (button, _) in ActionButtons()) { button.IsEnabled = false; button.ToolTip = reason; }
        HomeOpenSourceButton.IsEnabled = OpenSourceButton.IsEnabled = HomeOpenOutputButton.IsEnabled = OpenIncomingButton.IsEnabled = false;
        ActionAvailabilityText.Text = MaintenanceAvailabilityText.Text = reason;
    }

    private async void ProjectsList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_applyingContext || ProjectsList.SelectedItem is not ProjectRow row || row.ProjectId == _selectedProjectId) return;
        _selectedProjectId = row.ProjectId;
        _contextReady = false;
        _context = null;
        SelectedProjectText.Text = Localization.Get("SelectedProject") + ": " + row.DisplayName;
        HomeProjectText.Text = WorkStatusText.Text = row.DisplayName;
        RecommendationText.Text = WorkDetailText.Text = Localization.Get("LoadingProject");
        RecommendationReasonText.Text = "";
        SourceStateText.Text = SourceUpdateStatusText.Text = Localization.Get("UnknownState");
        SourceArtifactCombo.ItemsSource = null;
        DisableActions(Localization.Get("LoadingProject"));
        await RefreshContextAsync();
    }

    private static string? FirstSourceUpdateSlotPath(JsonObject ctx)
    {
        if (Node(ctx, "source", "source_update", "slots") is not JsonArray slots) return null;
        return slots.OfType<JsonObject>().Select(s => Text(s, "slot_path")).FirstOrDefault(p => !string.IsNullOrWhiteSpace(p));
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
    private void OpenIncoming_Click(object sender, RoutedEventArgs e)
    {
        if (_context is not null) OpenFolder(FirstSourceUpdateSlotPath(_context));
    }

    private async void PrepareSourceUpdate_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled || _context is null || SourceArtifactCombo.SelectedItem is not ArtifactRow artifact) return;
        var projectId = Text(_context, "selected_project", "project_id");
        if (string.IsNullOrWhiteSpace(projectId)) return;
        var result = await _worker.RunAsync(
            WorkerAction.PrepareSourceUpdate,
            new(ProjectId: projectId, ArtifactSelection: artifact.Key),
            elevated: true);
        await ShowActionResultAndRefresh("PREPARE_SOURCE_UPDATE", result);
    }

    private async void AcceptSourceUpdate_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled || _context is null) return;
        var projectId = Text(_context, "selected_project", "project_id");
        if (string.IsNullOrWhiteSpace(projectId)) return;
        var result = await _worker.RunAsync(WorkerAction.AcceptSourceUpdate, new(ProjectId: projectId), elevated: true);
        await ShowActionResultAndRefresh("ACCEPT_SOURCE_UPDATE", result);
    }

    private async void CancelSourceUpdate_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled || _context is null) return;
        var projectId = Text(_context, "selected_project", "project_id");
        if (string.IsNullOrWhiteSpace(projectId)) return;
        if (System.Windows.MessageBox.Show(Localization.Get("CancelSourceUpdate") + "?", Localization.Get("AppTitle"), MessageBoxButton.YesNo, MessageBoxImage.Question) != MessageBoxResult.Yes) return;
        var result = await _worker.RunAsync(WorkerAction.CancelSourceUpdate, new(ProjectId: projectId), elevated: true);
        await ShowActionResultAndRefresh("CANCEL_SOURCE_UPDATE", result);
    }

    private static void OpenFolder(string? path)
    {
        if (string.IsNullOrWhiteSpace(path) || !Directory.Exists(path)) return;
        var psi = new ProcessStartInfo("explorer.exe") { UseShellExecute = false };
        psi.ArgumentList.Add(path);
        Process.Start(psi);
    }

    private async void Start_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled || !_contextReady || !StartButton.IsEnabled || _context is null) return;
        var projectId = Text(_context, "selected_project", "project_id");
        var goal = TaskGoalTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(projectId) || projectId != _selectedProjectId) return;
        if (string.IsNullOrWhiteSpace(goal)) goal = Localization.Get("ReferenceAccessGoal") + " · " + Text(_context, "selected_project", "display_name");
        _mutationsEnabled = false;
        DisableActions(Localization.Get("ActionInProgress"));
        try
        {
            var result = await _worker.RunAsync(WorkerAction.Start, new(ProjectId: projectId, TaskId: WorkerClient.CreateTaskId(goal), TaskGoal: goal));
            await ShowActionResultAndRefresh("START", result);
        }
        catch (Exception ex) { ShowContextFailure(-1, ex.ToString(), ""); }
        finally { _mutationsEnabled = true; if (_contextReady && _context is not null) UpdateReadOnlyAvailability(_context); }
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
        if (System.Windows.MessageBox.Show(Localization.Get("StopConfirmation"), Localization.Get("AppTitle"), MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes) return;
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
                ShowActionFailure(step.Name, result);
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
                ShowActionFailure("ADD_EXTENSION", ext);
                await RefreshContextAsync();
                return;
            }
        }

        var apply = await _worker.RunAsync(WorkerAction.Apply, new(ProjectId: w.ProjectId));
        _selectedProjectId = w.ProjectId;
        await ShowActionResultAndRefresh("APPLY", apply);
    }

    private async Task ShowActionResultAndRefresh(string action, WorkerCallResult result)
    {
        if (result.ExitCode != 0 && result.ExitCode != 1223)
            ShowActionFailure(action, result);
        await RefreshContextAsync();
    }

    private void ShowActionFailure(string action, WorkerCallResult result)
    {
        _lastDiagnostic = Bound(string.Join(Environment.NewLine, new[] { result.StandardError, result.StandardOutput }.Where(x => !string.IsNullOrWhiteSpace(x))), 4000);
        AdvancedText.Text = _lastDiagnostic;
        System.Windows.MessageBox.Show(
            Localization.Get("ActionFailed") + ". " + Presentation.Outcome(result.StandardError) + " " + Localization.Get("ErrorDetails"),
            Localization.Get("AppTitle"),
            MessageBoxButton.OK,
            MessageBoxImage.Warning);
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
        if (_context is not null) ApplyContext(_context);
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
            _lastDiagnostic = Bound(ex.ToString(), 4000);
            AdvancedText.Text = _lastDiagnostic;
            System.Windows.MessageBox.Show(Localization.Get("StartupError"), Localization.Get("AppTitle"), MessageBoxButton.OK, MessageBoxImage.Warning);
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
        if (output?["tasks"] is not JsonArray tasks || tasks.Count == 0) return Localization.Get("NoProposalReceipts");
        var latest = tasks.OfType<JsonObject>().FirstOrDefault();
        if (latest is null) return Localization.Get("NoProposalReceipts");
        return $"{Localization.Get("ProposalsNotApplied")} · {Long(latest, "proposal_files")} {Localization.Get("ProposalFiles")}";
    }
}
