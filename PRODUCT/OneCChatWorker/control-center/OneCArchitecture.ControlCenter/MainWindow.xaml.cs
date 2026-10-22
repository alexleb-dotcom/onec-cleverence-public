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
    private string _currentPage = "Home";
    private string? _selectedProjectId;
    // Selected project is frozen while an external START/CONTINUE admission is pending.
    private string? _pendingAdmissionProjectId;

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
        NavHomeButton.Content = Localization.Get("WorkspaceMine");
        ProjectOverviewTab.Content = Localization.Get("WorkspaceOverview");
        ProjectSourceTab.Content = Localization.Get("WorkspaceSource");
        ProjectExtensionsTab.Content = Localization.Get("WorkspaceExtensions");
        ProjectHistoryTab.Content = Localization.Get("WorkspaceHistory");
        SettingsToolsLabel.Text = Localization.Get("WorkspaceTools");
        SettingsMaintenanceButton.Content = Localization.Get("NavMaintenance");
        SettingsAdvancedButton.Content = Localization.Get("NavAdvanced");
        NavProjectsButton.Content = Localization.Get("WorkspaceAllProjects");
        NavWorkButton.Content = Localization.Get("NavWork");
        NavActivityButton.Content = Localization.Get("NavActivity");
        NavMaintenanceButton.Content = Localization.Get("NavMaintenance");
        NavSettingsButton.Content = Localization.Get("NavSettings");
        NavAdvancedButton.Content = Localization.Get("NavAdvanced");
        HomeDetailsButton.Content = Localization.Get("NavAdvanced");
        WorkDetailsLabel.Text = Localization.Get("WorkRecovery");
        UpdateHomeNavigation();
        CurrentWorkLabel.Text = Localization.Get("CurrentWork");
        HomeHelperLabel.Text = Localization.Get("HelperLabel");
        System.Windows.Automation.AutomationProperties.SetName(HomeStatusStrip, Localization.Get("WorkspaceOverview"));
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
        SyncExtensionButton.Content = Localization.Get("SyncExtension");
        SourceAdvancedLabel.Text = Localization.Get("SourceAdvanced");
        if (SourceSyncResultText.Tag is string resultKey) SourceSyncResultText.Text = Localization.Get(resultKey);
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
            NavSettingsButton, NavAdvancedButton, ProjectOverviewTab, ProjectSourceTab, ProjectExtensionsTab, ProjectHistoryTab,
            SettingsMaintenanceButton, SettingsAdvancedButton, RefreshButton, HomeOpenSourceButton, HomeOpenOutputButton,
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
            // A completed request is not proof that the returned JSON belongs
            // to that project. Reject missing/foreign selected_project before
            // any owner projection or action eligibility is accepted.
            if (!OwnerResponseMatchesRequested(requestedProject, result.Json))
            {
                ShowContextFailure(2, "UI_CONTEXT_PROJECT_ID_MISMATCH", "");
                return;
            }
            // A poll begun before a mutation may finish after its fresh readback.
            // Keep the newer canonical projection instead of restoring an old generation.
            if (DateTimeOffset.TryParse(Text(_context, "generated_utc"), out var currentUtc) &&
                DateTimeOffset.TryParse(Text(result.Json, "generated_utc"), out var responseUtc) && responseUtc < currentUtc) return;
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
        ClearOwnerProjection(Localization.Get("WorkspaceVerificationUnknown"));
        ProjectTabs.Visibility = Visibility.Collapsed;
        SourceStateText.Text = McpStateText.Text = WorkStatusText.Text = Localization.Get("UnknownState");
        WorkDetailText.Text = Localization.Get("UiContextReason");
        var orbitPartial = raw.Contains("ORBIT_PARTIAL_INSTALL", StringComparison.Ordinal);
        var migrationRequired = raw.Contains("MIGRATION_REQUIRED", StringComparison.Ordinal);
        RecommendationText.Text = Localization.Get(orbitPartial ? "OrbitPartialInstall" : migrationRequired ? "MigrationRequired" : "UiContextUnavailable");
        RecommendationReasonText.Text = Localization.Get(orbitPartial ? "OrbitPartialInstallHelp" : migrationRequired ? "MigrationRequiredHelp" : "UiContextReason") +
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
        var verified = Text(ctx, "generated_utc");
        LastUpdatedText.Text = DateTimeOffset.TryParse(verified, out var ownerTimestamp)
            ? $"{Localization.Get("WorkspaceVerifiedAt")} {ownerTimestamp.ToLocalTime():g}"
            : Localization.Get("WorkspaceVerificationUnknown");
        var helper = Text(ctx, "work", "helper", "status") ?? "OFFLINE";
        HelperBadge.Text = $"{Localization.Get("HelperLabel")} · {helper}";

        var recommendationState = Text(ctx, "recommendation", "state") ?? "";
        var recommendationReason = Text(ctx, "recommendation", "reason_code") == "ORBIT_PARTIAL_INSTALL"
            ? "ORBIT_PARTIAL_INSTALL" : recommendationState;
        RecommendationText.Text = RecommendationTitle(recommendationReason);
        RecommendationReasonText.Text = Presentation.Reason(recommendationReason);
        if (SourceSyncResultText.Tag as string == "SyncUnverified")
        {
            RecommendationText.Text = Localization.Get("SyncUnverified");
            RecommendationReasonText.Text = Localization.Get("SyncInspect");
        }

        var projectName = Text(ctx, "selected_project", "display_name") ?? Localization.Get("ChooseProject");
        var workProjectId = Text(ctx, "work", "project_id");
        var workProjectName = (Node(ctx, "projects") as JsonArray)?.OfType<JsonObject>()
            .FirstOrDefault(p => Text(p, "project_id") == workProjectId)?["display_name"]?.GetValue<string>() ?? workProjectId;
        var taskGoal = Text(ctx, "work", "task_goal");
        var chosenProjectId = Text(ctx, "selected_project", "project_id");
        UpdateProjectTabsVisibility();
        WorkspaceNoticeText.Text = Bool(ctx, "work", "active") && !string.IsNullOrWhiteSpace(workProjectId)
            && workProjectId != chosenProjectId
            ? Localization.Get("WorkspaceOtherTask") + " " + (workProjectName ?? "")
            : Bool(ctx, "work", "active") && helper != "CONNECTED"
                ? Localization.Get("WorkspaceConnectionUnverified")
                : "";
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
        WorkDetailText.Text = Presentation.Reason(recommendationReason) + "\n" + Presentation.Expiry(Text(ctx, "work", "task_expires_utc"));
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
        // Retain the item containers (and keyboard focus) when polling returns
        // the same catalog. Replacing identical rows breaks arrow/Tab navigation.
        if (ProjectsList.ItemsSource is not ObservableCollection<ProjectRow> currentProjects ||
            !currentProjects.SequenceEqual(projects)) ProjectsList.ItemsSource = projects;
        ProjectsList.SelectedItem = ProjectsList.Items.OfType<ProjectRow>().FirstOrDefault(p => p.ProjectId == _selectedProjectId);
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
        _applyingContext = true;
        if (SourceArtifactCombo.ItemsSource is not ObservableCollection<ArtifactRow> currentArtifacts ||
            !currentArtifacts.SequenceEqual(artifacts)) SourceArtifactCombo.ItemsSource = artifacts;
        SourceArtifactCombo.SelectedItem = SourceArtifactCombo.Items.OfType<ArtifactRow>().FirstOrDefault(a => a.Key == previousArtifactKey)
            ?? SourceArtifactCombo.Items.OfType<ArtifactRow>().FirstOrDefault();
        _applyingContext = false;

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
        DiagnosticsText.Text = Presentation.Reason(recommendationReason) + "\n" + Localization.Get("PackageIsNotConnection") + "\n" + Localization.Get("ReadOnlyPreservation");

        var updateStatus = Text(ctx, "source", "source_update", "status") ?? "NONE";
        SourceUpdateStatusText.Text = updateStatus == "NONE"
            ? $"{Localization.Get("SourceUpdateNone")} {Localization.Get("SourceUpdateChoose")}"
            : updateStatus == "PREPARED_WRITABLE" ? Localization.Get("SourceFolderPrepared")
            : $"{Localization.Get("SourceUpdateTitle")}: {Presentation.Status(updateStatus)}";

        AdvancedText.Text = ctx.ToJsonString(new JsonSerializerOptions { WriteIndented = true });
        UpdateReadOnlyAvailability(ctx);
        UpdateHomeNavigation();
    }

    private string RecommendationTitle(string state) => Presentation.Status(state);

    internal static bool OwnerResponseMatchesRequested(string? requestedProject, JsonObject response) =>
        string.IsNullOrWhiteSpace(requestedProject) ||
        string.Equals(Text(response, "selected_project", "project_id"), requestedProject, StringComparison.Ordinal);

    private bool VerifiedContextMatchesSelection(JsonObject? ctx) =>
        _contextReady && ctx is not null &&
        string.Equals(Text(ctx, "selected_project", "project_id"), _selectedProjectId, StringComparison.Ordinal);

    private void UpdateReadOnlyAvailability(JsonObject ctx)
    {
        var trusted = VerifiedContextMatchesSelection(ctx);
        var source = Text(ctx, "navigation", "source_root");
        var output = Text(ctx, "navigation", "output_root");
        HomeOpenSourceButton.IsEnabled = OpenSourceButton.IsEnabled = trusted && !string.IsNullOrWhiteSpace(source);
        HomeOpenOutputButton.IsEnabled = trusted && !string.IsNullOrWhiteSpace(output);

        var updateStatus = Text(ctx, "source", "source_update", "status") ?? "NONE";
        var sourceUpdateActive = updateStatus != "NONE";
        var slotPath = SelectedSourceUpdateSlotPath(ctx);

        foreach (var (button, key) in ActionButtons())
        {
            button.IsEnabled = _mutationsEnabled && trusted && Bool(ctx, "actions", key, "enabled");
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
        var selectedUpdate = ObservedSourceUpdateArgs();
        AcceptSourceUpdateButton.IsEnabled &= selectedUpdate is not null;
        CancelSourceUpdateButton.IsEnabled &= selectedUpdate is not null;
        PrepareSourceUpdateButton.IsEnabled &= SelectedArtifactMatches(ctx);
        SyncExtensionButton.IsEnabled &= SyncExtensionArgs() is not null;
        SyncExtensionHelpText.Text = SyncExtensionButton.IsEnabled ? Localization.Get("SyncExtensionHelp")
            : !_mutationsEnabled ? Localization.Get("ActionInProgress") : Localization.Get("SyncExtensionBlocked");
        SyncExtensionButton.ToolTip = SyncExtensionHelpText.Text;
        System.Windows.Automation.AutomationProperties.SetHelpText(SyncExtensionButton, SyncExtensionHelpText.Text);
        OpenIncomingButton.IsEnabled = trusted && sourceUpdateActive && !string.IsNullOrWhiteSpace(slotPath);
        OpenIncomingButton.ToolTip = Localization.Get("IncomingUnavailable");
        HomeOpenSourceButton.ToolTip = OpenSourceButton.ToolTip = Localization.Get("SourceUnavailable");
        HomeOpenOutputButton.ToolTip = Localization.Get("OutputUnavailable");
    }

    private IEnumerable<(System.Windows.Controls.Button Button, string Key)> ActionButtons() =>
    [ (StartButton, "start"), (ContinueButton, "continue"), (StopButton, "stop"), (HomeStopButton, "stop"),
      (ApplyButton, "apply"), (MaintenanceApplyButton, "apply"), (VerifyButton, "verify"), (RepairButton, "repair"),
      (SyncExtensionButton, "sync_extension"), (UpdateButton, "update"), (AddProjectButton, "add_project"), (PrepareSourceUpdateButton, "prepare_source_update"),
      (AcceptSourceUpdateButton, "accept_source_update"), (CancelSourceUpdateButton, "cancel_source_update") ];

    private void DisableActions(string reason)
    {
        foreach (var (button, _) in ActionButtons()) { button.IsEnabled = false; button.ToolTip = reason; }
        HomeOpenSourceButton.IsEnabled = OpenSourceButton.IsEnabled = HomeOpenOutputButton.IsEnabled = OpenIncomingButton.IsEnabled = false;
        ActionAvailabilityText.Text = MaintenanceAvailabilityText.Text = reason;
    }

    // All globally visible owner facts belong to the OLD project until a
    // matching UI_CONTEXT readback arrives. Clear them synchronously when
    // changing the project identity, before the first asynchronous await.
    private void ClearOwnerProjection(string reason)
    {
        LastUpdatedText.Text = reason;
        WorkspaceNoticeText.Text = reason;
        HelperBadge.Text = Localization.Get("HelperLabel") + ": " + Localization.Get("UnknownState");
        GlobalWarningText.Text = "";
        HomeTaskText.Text = Localization.Get("UnknownState");
        HomeHelperText.Text = Localization.Get("UnknownState");
        // The entire owner projection belongs to the previous project until
        // a matching fresh UI_CONTEXT arrives. Hide old Output/Activity facts.
        OutputStateText.Text = reason;
        OutputSummaryText.Text = reason;
        ActivitySummaryText.Text = reason;
        ActivityList.ItemsSource = null;
        SourceStateText.Text = reason;
        SourceUpdateStatusText.Text = reason;
        SourceArtifactCombo.ItemsSource = null;
        SourceSyncResultText.Tag = null;
        SourceSyncResultText.Text = "";
        McpEpochText.Text = reason;
        McpPolicyText.Text = reason;
        OperationText.Text = reason;
        DiagnosticsText.Text = reason;
        AdvancedText.Text = "";
        McpStateText.Text = Localization.Get("UnknownState");
        McpUsageText.Text = Localization.Get("UnknownState");
        CheckpointStateText.Text = Localization.Get("UnknownState");
        CheckpointSummaryText.Text = "";
        WorkCheckpointText.Text = Localization.Get("UnknownState");
        SessionHelpText.Text = "";
        UpdateHomeNavigation();
        UpdateProjectTabsVisibility();
    }

    private async void ProjectsList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_applyingContext) return;
        if (_pendingAdmissionProjectId is { } pinnedId)
        {
            // Keyboard/mouse is blocked at the ListView; also reject synthetic
            // or programmatic selection changes during the password prompt.
            _applyingContext = true;
            try
            {
                ProjectsList.SelectedItem = ProjectsList.Items.OfType<ProjectRow>()
                    .FirstOrDefault(p => p.ProjectId == pinnedId);
            }
            finally { _applyingContext = false; }
            return;
        }
        if (ProjectsList.SelectedItem is not ProjectRow row || row.ProjectId == _selectedProjectId) return;
        _selectedProjectId = row.ProjectId;
        _contextReady = false;
        _context = null;
        ClearOwnerProjection(Localization.Get("WorkspaceVerificationPending"));
        SelectedProjectText.Text = Localization.Get("SelectedProject") + ": " + row.DisplayName;
        HomeProjectText.Text = WorkStatusText.Text = row.DisplayName;
        RecommendationText.Text = WorkDetailText.Text = Localization.Get("LoadingProject");
        RecommendationReasonText.Text = "";
        SourceStateText.Text = SourceUpdateStatusText.Text = Localization.Get("UnknownState");
        SourceArtifactCombo.ItemsSource = null;
        SourceSyncResultText.Tag = null; SourceSyncResultText.Text = "";
        DisableActions(Localization.Get("LoadingProject"));
        await RefreshContextAsync();
    }

    private bool SelectedArtifactMatches(JsonObject ctx) =>
        _contextReady && Text(ctx, "selected_project", "project_id") == _selectedProjectId &&
        SourceArtifactCombo.SelectedItem is ArtifactRow a &&
        a.Key == $"{a.ParticipantId}|{a.ArtifactType}|{a.ArtifactId}" &&
        (Node(ctx, "source", "artifacts") as JsonArray)?.OfType<JsonObject>().Count(n =>
            Text(n, "key") == a.Key && Text(n, "participant_id") == a.ParticipantId &&
            Text(n, "artifact_type") == a.ArtifactType && Text(n, "artifact_id") == a.ArtifactId) == 1;

    private WorkerActionArgs? SyncExtensionArgs()
    {
        if (_context is not { } ctx || !SelectedArtifactMatches(ctx) ||
            SourceArtifactCombo.SelectedItem is not ArtifactRow { ArtifactType: "EXTENSION" } a ||
            Text(ctx, "source", "state") != "ACCEPTED" || Bool(ctx, "work", "active") ||
            Text(ctx, "source", "source_update", "status") != "NONE" ||
            !string.IsNullOrWhiteSpace(Text(ctx, "source", "source_update", "promotion_state")) ||
            Text(ctx, "operation", "recovery", "classification") == "RECOVERY_REQUIRED" ||
            !Bool(ctx, "actions", "sync_extension", "enabled")) return null;
        return new(ProjectId: _selectedProjectId, ParticipantId: a.ParticipantId, ExtensionId: a.ArtifactId);
    }

    private string? SelectedSourceUpdateSlotPath(JsonObject ctx)
    {
        var expected = ObservedSourceUpdateArgs();
        if (expected is null || Node(ctx, "source", "source_update", "slots") is not JsonArray slots) return null;
        return slots.OfType<JsonObject>().Where(s => Text(s, "key") == expected.ExpectedArtifactKey)
            .Select(s => Text(s, "slot_path")).SingleOrDefault();
    }

    private void SourceArtifact_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_applyingContext || _context is null) return;
        SourceSyncResultText.Tag = null; SourceSyncResultText.Text = "";
        UpdateReadOnlyAvailability(_context);
    }

    // Pure verification of the existing canonical operation; no file inspection or replay.
    internal static string? VerifiedSyncOutcome(JsonObject ctx, WorkerActionArgs args,
        string? previousOperationId, DateTimeOffset requestedUtc, string? previousSnapshot)
    {
        var op = Node(ctx, "operation", "last");
        var result = Node(op, "sync_extension_result");
        var status = Text(result, "status");
        var key = $"{args.ParticipantId}|EXTENSION|{args.ExtensionId}";
        if (Text(ctx, "selected_project", "project_id") != args.ProjectId ||
            Text(op, "project_id") != args.ProjectId || Text(op, "participant_id") != args.ParticipantId ||
            Text(op, "artifact_id") != args.ExtensionId || Text(result, "artifact_key") != key ||
            Text(op, "operation_type") != "SOURCE_UPDATE_QUICK_SYNC" || Text(op, "state") != "PASS" ||
            string.IsNullOrWhiteSpace(Text(op, "operation_id")) || Text(op, "operation_id") == previousOperationId ||
            !DateTimeOffset.TryParse(Text(op, "started_utc"), out var started) || started < requestedUtc ||
            !DateTimeOffset.TryParse(Text(op, "ended_utc"), out var ended) || ended < started ||
            !DateTimeOffset.TryParse(Text(ctx, "generated_utc"), out var generated) || generated < ended ||
            Text(ctx, "source", "state") != "ACCEPTED" || Bool(ctx, "work", "active") ||
            Text(ctx, "source", "source_update", "status") != "NONE" ||
            !string.IsNullOrWhiteSpace(Text(ctx, "source", "source_update", "promotion_state")) ||
            Text(ctx, "operation", "recovery", "classification") == "RECOVERY_REQUIRED" ||
            string.IsNullOrWhiteSpace(Text(result, "source_snapshot_id")) ||
            Text(result, "source_snapshot_id") != Text(ctx, "source", "snapshot_id") ||
            (Node(ctx, "source", "artifacts") as JsonArray)?.OfType<JsonObject>().Count(n => Text(n, "key") == key) != 1)
            return null;
        if (status == "NO_CHANGE" && Text(result, "source_snapshot_id") == previousSnapshot) return status;
        if (status == "READY" && !string.IsNullOrWhiteSpace(Text(result, "generation_id")) &&
            Text(result, "source_snapshot_id") != previousSnapshot) return status;
        return null;
    }

    private async void SyncExtension_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled || !SyncExtensionButton.IsEnabled || SyncExtensionArgs() is not { } args) return;
        var previousOperation = Text(_context, "operation", "last", "operation_id");
        var previousSnapshot = Text(_context, "source", "snapshot_id");
        var requestedUtc = DateTimeOffset.UtcNow;
        _mutationsEnabled = false;
        _timer.Stop();
        ProjectsList.IsEnabled = SourceArtifactCombo.IsEnabled = false;
        SourceSyncResultText.Tag = null; SourceSyncResultText.Text = "";
        DisableActions(Localization.Get("ActionInProgress"));
        try
        {
            var result = await _worker.RunAsync(WorkerAction.SyncExtension, args, elevated: true);
            // UAC supplies an exit code but no JSON. Always read the native owner again.
            var readback = await _worker.GetContextAsync(args.ProjectId);
            string? outcome = null;
            if (readback.ExitCode == 0 && readback.Json is { } ctx &&
                Text(ctx, "selected_project", "project_id") == _selectedProjectId && args.ProjectId == _selectedProjectId)
            {
                SourceSyncResultText.Tag = null;
                _context = ctx; _contextReady = true;
                ApplyContext(ctx);
                if (result.ExitCode == 0) outcome = VerifiedSyncOutcome(ctx, args, previousOperation, requestedUtc, previousSnapshot);
            }
            else ShowContextFailure(readback.ExitCode, readback.StandardError, readback.StandardOutput);
            SourceSyncResultText.Tag = outcome == "NO_CHANGE" ? "SyncNoChange" : outcome == "READY" ? "SyncReady" : "SyncUnverified";
            SourceSyncResultText.Text = Localization.Get((string)SourceSyncResultText.Tag);
            if (outcome is null && _context is not null)
            {
                // A generic PROJECT_READY recommendation is not proof of this action.
                RecommendationText.Text = Localization.Get("SyncUnverified");
                RecommendationReasonText.Text = Localization.Get("SyncInspect");
            }
        }
        catch (Exception ex)
        {
            ShowContextFailure(-1, ex.ToString(), "");
            SourceSyncResultText.Tag = "SyncUnverified";
            SourceSyncResultText.Text = Localization.Get("SyncUnverified");
        }
        finally
        {
            _mutationsEnabled = true;
            ProjectsList.IsEnabled = SourceArtifactCombo.IsEnabled = true;
            if (_contextReady && _context is not null) UpdateReadOnlyAvailability(_context);
            if (IsLoaded) _timer.Start();
        }
    }

    private void Nav_Click(object sender, RoutedEventArgs e)
    {
        if (sender is System.Windows.Controls.Button b && b.Tag is string page) ShowPage(page);
    }

    // D2: UI_CONTEXT determines the owner-proven next navigation intent.
    // This button may open a page or refresh UI_CONTEXT; it NEVER calls RunAsync.
    internal static (string Destination, string LabelKey) OwnerHomeAction(
        JsonObject? ctx, bool contextReady, string? selectedProjectId)
    {
        if (string.IsNullOrWhiteSpace(selectedProjectId)) return ("Projects", "ChooseProject");
        if (!contextReady || ctx is null ||
            Text(ctx, "selected_project", "project_id") != selectedProjectId)
            return ("Refresh", "WorkspaceCheckStatus");

        var active = Bool(ctx, "work", "active");
        var taskProjectId = Text(ctx, "work", "project_id");
        if (active && taskProjectId != selectedProjectId)
            return ("Projects", "WorkspaceReviewOtherProject");
        if (active)
            return Text(ctx, "work", "helper", "status") == "CONNECTED"
                ? ("Work", "WorkspaceOpenCurrentTask")
                : ("Refresh", "WorkspaceCheckConnection");

        if (Bool(ctx, "actions", "continue", "enabled") &&
            Node(ctx, "work", "checkpoint") is JsonObject)
            return ("Work", "WorkspaceOpenSavedWork");
        if (Bool(ctx, "actions", "start", "enabled"))
            return ("Work", "WorkspacePrepareNewTask");
        return ("Refresh", "WorkspaceCheckStatus");
    }

    private void UpdateHomeNavigation()
    {
        if (_pendingAdmissionProjectId is { } pinnedId)
        {
            var message = Localization.Get("WorkspaceAdmissionPending");
            HomePrimaryButton.Tag = "AdmissionPending";
            HomePrimaryButton.Content = message;
            HomePrimaryButton.IsEnabled = false;
            WorkspaceNoticeText.Text = message + " · " + pinnedId;
            System.Windows.Automation.AutomationProperties.SetName(HomePrimaryButton, message);
            System.Windows.Automation.AutomationProperties.SetHelpText(HomePrimaryButton, message);
            return;
        }
        HomePrimaryButton.IsEnabled = true;
        var intent = OwnerHomeAction(_context, _contextReady, _selectedProjectId);
        HomePrimaryButton.Tag = intent.Destination;
        HomePrimaryButton.Content = Localization.Get(intent.LabelKey);
        System.Windows.Automation.AutomationProperties.SetName(HomePrimaryButton, HomePrimaryButton.Content.ToString());
        System.Windows.Automation.AutomationProperties.SetHelpText(HomePrimaryButton, Localization.Get("HomeNavigationHelp"));
    }

    private async void HomePrimary_Click(object sender, RoutedEventArgs e)
    {
        // Refresh never opens or restarts Helper; Work navigation does not START.
        var target = HomePrimaryButton.Tag as string;
        if (target == "Refresh") await RefreshContextAsync();
        else if (target is "Projects" or "Work") ShowPage(target);
    }

    // Only project-scoped pages expose tabs. A selected identity alone must not
    // overlay settings, catalog, or technical recovery screens.
    private void UpdateProjectTabsVisibility()
    {
        ProjectTabs.Visibility = _contextReady &&
            !string.IsNullOrWhiteSpace(Text(_context, "selected_project", "project_id")) &&
            _currentPage is "Home" or "Source" or "Extensions" or "Activity" or "Work"
                ? Visibility.Visible : Visibility.Collapsed;
    }

    private void ShowPage(string name)
    {
        _currentPage = name;
        UpdateProjectTabsVisibility();
        MaintenanceGeneralPanel.Visibility = name == "Extensions" ? Visibility.Collapsed : Visibility.Visible;
        MaintenanceExtensionPanel.Visibility = name == "Source" ? Visibility.Collapsed : Visibility.Visible;
        MaintenanceDiagnosticsPanel.Visibility = name is "Source" or "Extensions" ? Visibility.Collapsed : Visibility.Visible;
        foreach (var tab in new[] { ProjectOverviewTab, ProjectSourceTab, ProjectExtensionsTab, ProjectHistoryTab })
            System.Windows.Automation.AutomationProperties.SetItemStatus(tab, tab.Tag?.ToString() == name ? "Selected" : "");

        foreach (var button in new[] { NavHomeButton, NavProjectsButton, NavWorkButton, NavActivityButton,
            NavMaintenanceButton, NavSettingsButton, NavAdvancedButton })
            System.Windows.Automation.AutomationProperties.SetItemStatus(button, button.Tag?.ToString() == name ? "Selected" : "");
        foreach (var control in new FrameworkElement[] { HomePage, ProjectsPage, WorkPage, ActivityPage, MaintenancePage, SettingsPage, AdvancedPage })
            control.Visibility = Visibility.Collapsed;
        FrameworkElement target = name switch
        {
            "Projects" => ProjectsPage, "Work" => WorkPage, "Activity" => ActivityPage,
            "Source" or "Extensions" => MaintenancePage,
            "Maintenance" => MaintenancePage, "Settings" => SettingsPage, "Advanced" => AdvancedPage, _ => HomePage
        };
        target.Visibility = Visibility.Visible;
        PageTitle.Text = name switch
        {
            "Projects" => Localization.Get("WorkspaceAllProjects"), "Work" => Localization.Get("NavWork"),
            "Source" => Localization.Get("WorkspaceSource"), "Extensions" => Localization.Get("WorkspaceExtensions"),
            "Home" => Localization.Get("WorkspaceMine"),
            "Activity" => Localization.Get("NavActivity"), "Maintenance" => Localization.Get("NavMaintenance"),
            "Settings" => Localization.Get("NavSettings"), "Advanced" => Localization.Get("NavAdvanced"),
            _ => Localization.Get("WorkspaceMine")
        };
    }

    private async void Refresh_Click(object sender, RoutedEventArgs e) => await RefreshContextAsync();

    private void OpenSource_Click(object sender, RoutedEventArgs e) => OpenFolder(Text(_context, "navigation", "source_root"));
    private void OpenOutput_Click(object sender, RoutedEventArgs e) => OpenFolder(Text(_context, "navigation", "output_root"));
    private void OpenIncoming_Click(object sender, RoutedEventArgs e)
    {
        if (_context is not null) OpenFolder(SelectedSourceUpdateSlotPath(_context));
    }

    private async void PrepareSourceUpdate_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled || !PrepareSourceUpdateButton.IsEnabled || _context is null || !SelectedArtifactMatches(_context) || SourceArtifactCombo.SelectedItem is not ArtifactRow artifact) return;
        var projectId = Text(_context, "selected_project", "project_id");
        if (string.IsNullOrWhiteSpace(projectId)) return;
        var result = await _worker.RunAsync(
            WorkerAction.PrepareSourceUpdate,
            new(ProjectId: projectId, ArtifactSelection: artifact.Key),
            elevated: true);
        await ShowActionResultAndRefresh("PREPARE_SOURCE_UPDATE", result);
    }

    private WorkerActionArgs? ObservedSourceUpdateArgs()
    {
        if (_context is null || !SelectedArtifactMatches(_context)) return null;
        var projectId = Text(_context, "selected_project", "project_id");
        var update = _context["source"]?["source_update"] as JsonObject;
        var generation = update?["generation_id"]?.GetValue<string>();
        var slots = update?["slots"] as JsonArray;
        if (string.IsNullOrWhiteSpace(projectId) || string.IsNullOrWhiteSpace(generation) ||
            slots is null || slots.Count != 1) return null;
        var key = slots[0]?["key"]?.GetValue<string>();
        if (string.IsNullOrWhiteSpace(key) || key != (SourceArtifactCombo.SelectedItem as ArtifactRow)?.Key ||
            Text(update, "project_id") != projectId || Text(update, "status") == "NONE") return null;
        return new(ProjectId: projectId, ExpectedGenerationId: generation, ExpectedArtifactKey: key);
    }

    private async void AcceptSourceUpdate_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled || !_contextReady || _context is null) return;
        var expected = ObservedSourceUpdateArgs();
        if (expected is null) return;
        var result = await _worker.RunAsync(WorkerAction.AcceptSourceUpdate, expected, elevated: true);
        await ShowActionResultAndRefresh("ACCEPT_SOURCE_UPDATE", result);
    }

    private async void CancelSourceUpdate_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled || !_contextReady || _context is null) return;
        var expected = ObservedSourceUpdateArgs();
        if (expected is null) return;
        if (System.Windows.MessageBox.Show(Localization.Get("CancelSourceUpdate") + "?", Localization.Get("AppTitle"), MessageBoxButton.YesNo, MessageBoxImage.Question) != MessageBoxResult.Yes) return;
        var result = await _worker.RunAsync(WorkerAction.CancelSourceUpdate, expected, elevated: true);
        await ShowActionResultAndRefresh("CANCEL_SOURCE_UPDATE", result);
    }

    private static void OpenFolder(string? path)
    {
        if (string.IsNullOrWhiteSpace(path) || !Directory.Exists(path)) return;
        var psi = new ProcessStartInfo("explorer.exe") { UseShellExecute = false };
        psi.ArgumentList.Add(path);
        Process.Start(psi);
    }

    // GUI-only lease for an external credential prompt or in-flight Worker
    // operation. Never collect a password or infer successful connection.
    private void BeginPendingAdmission(string projectId)
    {
        if (_pendingAdmissionProjectId is not null || projectId != _selectedProjectId)
            throw new InvalidOperationException("ADMISSION_PROJECT_IDENTITY_REQUIRED");
        _pendingAdmissionProjectId = projectId;
        _mutationsEnabled = false;
        ProjectsList.IsEnabled = false;
        DisableActions(Localization.Get("WorkspaceAdmissionPending"));
        UpdateHomeNavigation();
    }

    private void EndPendingAdmission()
    {
        _pendingAdmissionProjectId = null;
        ProjectsList.IsEnabled = true;
        _mutationsEnabled = true;
        if (VerifiedContextMatchesSelection(_context))
            UpdateReadOnlyAvailability(_context!);
        else
            DisableActions(Localization.Get("UiContextReason"));
        UpdateHomeNavigation();
    }

    private async void Start_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled || !VerifiedContextMatchesSelection(_context) ||
            !StartButton.IsEnabled || !Bool(_context, "actions", "start", "enabled")) return;
        var projectId = _selectedProjectId!;
        var goal = TaskGoalTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(goal))
            goal = Localization.Get("ReferenceAccessGoal") + " · " + Text(_context, "selected_project", "display_name");
        BeginPendingAdmission(projectId);
        try
        {
            var result = await _worker.RunAsync(WorkerAction.Start,
                new(ProjectId: projectId, TaskId: WorkerClient.CreateTaskId(goal), TaskGoal: goal));
            await ShowActionResultAndRefresh("START", result);
        }
        catch (Exception ex) { ShowContextFailure(-1, ex.ToString(), ""); }
        finally { EndPendingAdmission(); }
    }

    private async void Continue_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled || !VerifiedContextMatchesSelection(_context) ||
            !ContinueButton.IsEnabled || !Bool(_context, "actions", "continue", "enabled") ||
            Node(_context, "work", "checkpoint") is not JsonObject) return;
        var projectId = _selectedProjectId!;
        var taskProjectId = Text(_context, "work", "project_id");
        if (!string.IsNullOrWhiteSpace(taskProjectId) && taskProjectId != projectId) return;
        BeginPendingAdmission(projectId);
        try
        {
            // Preserve Worker's canonical continuation target and never
            // substitute START or synthesize a checkpoint in the GUI.
            var result = await _worker.RunAsync(WorkerAction.Continue, new());
            await ShowActionResultAndRefresh("CONTINUE", result);
        }
        catch (Exception ex) { ShowContextFailure(-1, ex.ToString(), ""); }
        finally { EndPendingAdmission(); }
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
        if (!_mutationsEnabled || !VerifiedContextMatchesSelection(_context) || !ApplyButton.IsEnabled) return;
        var projectId = Text(_context, "selected_project", "project_id");
        if (string.IsNullOrWhiteSpace(projectId) || projectId != _selectedProjectId) return;
        var result = await _worker.RunAsync(WorkerAction.Apply, new(ProjectId: projectId));
        await ShowActionResultAndRefresh("APPLY", result);
    }

    private async void Verify_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled || !VerifiedContextMatchesSelection(_context) || !VerifyButton.IsEnabled) return;
        var projectId = Text(_context, "selected_project", "project_id");
        if (string.IsNullOrWhiteSpace(projectId) || projectId != _selectedProjectId) return;
        var result = await _worker.RunAsync(WorkerAction.Verify, new(ProjectId: projectId));
        await ShowActionResultAndRefresh("VERIFY", result);
    }

    private async void Repair_Click(object sender, RoutedEventArgs e)
    {
        if (!_mutationsEnabled || !VerifiedContextMatchesSelection(_context) || !RepairButton.IsEnabled) return;
        var projectId = Text(_context, "selected_project", "project_id");
        if (string.IsNullOrWhiteSpace(projectId) || projectId != _selectedProjectId) return;
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
