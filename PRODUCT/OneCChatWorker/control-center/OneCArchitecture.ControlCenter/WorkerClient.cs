using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json.Nodes;

namespace OneCArchitecture.ControlCenter;

internal enum WorkerAction
{
    UiContext, Apply, Verify, Repair, Start, Continue, Stop, Update,
    AddProject, AddParticipant, SetMain, AddExtension,
    PrepareSourceUpdate, AcceptSourceUpdate, CancelSourceUpdate, SyncExtension
}

internal sealed record WorkerActionArgs(
    string? ProjectId = null,
    string? ParticipantId = null,
    string? ExtensionId = null,
    string? SourcePath = null,
    string? DisplayName = null,
    string? Role = null,
    string? TaskId = null,
    string? TaskGoal = null,
    string? ArtifactSelection = null,
    bool ReplaceExisting = false,
    bool SelectedArtifactFullSafeImport = false,
    string? ExpectedGenerationId = null,
    string? ExpectedArtifactKey = null);

internal sealed record WorkerCallResult(int ExitCode, JsonObject? Json, string StandardOutput, string StandardError);

internal interface IWorkerClient
{
    Task<WorkerCallResult> GetContextAsync(string? projectId, CancellationToken token = default);
    Task<WorkerCallResult> RunAsync(WorkerAction action, WorkerActionArgs args, bool elevated = false, CancellationToken token = default);
}

internal sealed class WorkerClient : IWorkerClient
{
    private static readonly IReadOnlyDictionary<WorkerAction, string> Modes =
        new Dictionary<WorkerAction, string>
        {
            [WorkerAction.UiContext] = "UI_CONTEXT",
            [WorkerAction.Apply] = "APPLY",
            [WorkerAction.Verify] = "VERIFY",
            [WorkerAction.Repair] = "REPAIR",
            [WorkerAction.Start] = "START",
            [WorkerAction.Continue] = "CONTINUE",
            [WorkerAction.Stop] = "STOP",
            [WorkerAction.Update] = "UPDATE",
            [WorkerAction.AddProject] = "ADD_PROJECT",
            [WorkerAction.AddParticipant] = "ADD_PARTICIPANT",
            [WorkerAction.SetMain] = "SET_MAIN",
            [WorkerAction.AddExtension] = "ADD_EXTENSION",
            [WorkerAction.SyncExtension] = "SYNC_EXTENSION",
            [WorkerAction.PrepareSourceUpdate] = "PREPARE_SOURCE_UPDATE",
            [WorkerAction.AcceptSourceUpdate] = "ACCEPT_SOURCE_UPDATE",
            [WorkerAction.CancelSourceUpdate] = "CANCEL_SOURCE_UPDATE"
        };

    public string LauncherPath { get; }
    public string WorkerRoot { get; }
    public string ProgramDataRoot { get; }

    public WorkerClient()
    {
        WorkerRoot = Environment.GetEnvironmentVariable("ONEC_CONTROL_CENTER_WORKER_ROOT")
            ?? @"C:\OneCOrbit";
        ProgramDataRoot = Environment.GetEnvironmentVariable("ONEC_CONTROL_CENTER_PROGRAM_DATA")
            ?? @"C:\ProgramData\OneCOrbit";
        LauncherPath = Environment.GetEnvironmentVariable("ONEC_CONTROL_CENTER_LAUNCHER")
            ?? Path.Combine(WorkerRoot, "OneCChatWorker.ps1");
    }

    // Inject existence checks for isolated fixtures; never inspect Source contents.
    internal static bool NeedsMigration(string workerRoot, string programDataRoot, string? launcherOverride,
        Func<string, bool> fileExists, Func<string, bool> directoryExists) =>
        workerRoot.TrimEnd((char)92).Equals(@"C:\OneCOrbit", StringComparison.OrdinalIgnoreCase) &&
        programDataRoot.TrimEnd((char)92).Equals(@"C:\ProgramData\OneCOrbit", StringComparison.OrdinalIgnoreCase) &&
        launcherOverride is null &&
        !(fileExists(Path.Combine(workerRoot, "projects.json")) &&
          fileExists(Path.Combine(programDataRoot, "installed-state.json"))) &&
        (directoryExists(@"C:\OneCChatWorker") || directoryExists(@"C:\ProgramData\OneCChatWorker"));

    // UI_CONTEXT is a read-only authority query. A hung helper must never hold
    // the UI's single-flight admission readback indefinitely.
    internal static readonly TimeSpan OwnerContextDeadline = TimeSpan.FromSeconds(25);

    public Task<WorkerCallResult> GetContextAsync(string? projectId, CancellationToken token = default) =>
        ReadContextWithDeadlineAsync(
            deadlineToken => RunAsync(WorkerAction.UiContext, new(ProjectId: projectId), false, deadlineToken),
            OwnerContextDeadline, token);

    // An unresponsive owner must return UNKNOWN/HOLD through the usual GUI
    // failure path. No cached START/CONTINUE eligibility may be substituted.
    internal static async Task<WorkerCallResult> ReadContextWithDeadlineAsync(
        Func<CancellationToken, Task<WorkerCallResult>> read,
        TimeSpan deadline, CancellationToken token = default)
    {
        if (deadline <= TimeSpan.Zero) throw new ArgumentOutOfRangeException(nameof(deadline));
        token.ThrowIfCancellationRequested();
        using var bounded = CancellationTokenSource.CreateLinkedTokenSource(token);
        bounded.CancelAfter(deadline);
        try { return await read(bounded.Token).WaitAsync(bounded.Token); }
        catch (OperationCanceledException) when (!token.IsCancellationRequested && bounded.IsCancellationRequested)
        {
            return new(2, null, "", "UI_CONTEXT_TIMEOUT");
        }
    }

    internal ProcessStartInfo CreateStartInfo(WorkerAction action, WorkerActionArgs args, bool elevated)
    {
        if (action == WorkerAction.SyncExtension &&
            (string.IsNullOrWhiteSpace(args.ProjectId) || string.IsNullOrWhiteSpace(args.ParticipantId) || string.IsNullOrWhiteSpace(args.ExtensionId)))
            throw new InvalidOperationException("SYNC_EXTENSION_IDENTITY_REQUIRED");
        if ((action is WorkerAction.AcceptSourceUpdate or WorkerAction.CancelSourceUpdate) &&
            (string.IsNullOrWhiteSpace(args.ExpectedGenerationId) || string.IsNullOrWhiteSpace(args.ExpectedArtifactKey)))
            throw new InvalidOperationException("SOURCE_UPDATE_EXPECTED_IDENTITY_REQUIRED");
        if (!Modes.TryGetValue(action, out var mode))
            throw new InvalidOperationException("WORKER_ACTION_NOT_ALLOWLISTED");

        // START/CONTINUE call native runas.exe inside the Worker; runas requires
        // a visible, interactive Windows console to ask for the restricted
        // restricted account credential. Never capture/store it in WPF.
        // All non-interactive UI_CONTEXT/other actions keep their previous
        // hidden redirected process boundary.
        var interactiveAdmission = !elevated && (action is WorkerAction.Start or WorkerAction.Continue);
        var redirected = !elevated && !interactiveAdmission;
        var psi = new ProcessStartInfo("powershell.exe")
        {
            UseShellExecute = !redirected,
            CreateNoWindow = redirected,
            RedirectStandardOutput = redirected,
            RedirectStandardError = redirected,
            WindowStyle = interactiveAdmission ? ProcessWindowStyle.Normal : ProcessWindowStyle.Hidden,
            Verb = elevated ? "runas" : ""
        };
        if (redirected)
        {
            psi.StandardOutputEncoding = new UTF8Encoding(false, true);
            psi.StandardErrorEncoding = new UTF8Encoding(false);
        }
        Add(psi, "-NoProfile");
        Add(psi, "-ExecutionPolicy"); Add(psi, "Bypass");
        Add(psi, "-File"); Add(psi, LauncherPath);
        Add(psi, "-Mode"); Add(psi, mode);
        Add(psi, "-WorkerRoot"); Add(psi, WorkerRoot);
        Add(psi, "-ProgramDataRoot"); Add(psi, ProgramDataRoot);
        if (redirected) Add(psi, "-Json");

        AddIf(psi, "-ProjectId", args.ProjectId);
        AddIf(psi, "-ParticipantId", args.ParticipantId);
        AddIf(psi, "-ExtensionId", args.ExtensionId);
        AddIf(psi, "-SourcePath", args.SourcePath);
        AddIf(psi, "-DisplayName", args.DisplayName);
        AddIf(psi, "-Role", args.Role);
        AddIf(psi, "-TaskId", args.TaskId);
        AddIf(psi, "-TaskGoal", args.TaskGoal);
        AddIf(psi, "-ArtifactSelection", args.ArtifactSelection);
        AddIf(psi, "-ExpectedGenerationId", args.ExpectedGenerationId);
        AddIf(psi, "-ExpectedArtifactKey", args.ExpectedArtifactKey);
        if (args.ReplaceExisting) Add(psi, "-ReplaceExisting");
        if (args.SelectedArtifactFullSafeImport) Add(psi, "-SelectedArtifactFullSafeImport");

        return psi;
    }

    public async Task<WorkerCallResult> RunAsync(
        WorkerAction action, WorkerActionArgs args, bool elevated = false, CancellationToken token = default)
    {
        if (NeedsMigration(WorkerRoot, ProgramDataRoot,
            Environment.GetEnvironmentVariable("ONEC_CONTROL_CENTER_LAUNCHER"), File.Exists, Directory.Exists))
            return new(2, null, "", "MIGRATION_REQUIRED");
        if (!File.Exists(LauncherPath))
            return new(2, null, "", "WORKER_LAUNCHER_NOT_FOUND");
        var psi = CreateStartInfo(action, args, elevated);

        try
        {
            using var process = Process.Start(psi) ?? throw new InvalidOperationException("WORKER_PROCESS_START_FAILED");
            try
            {
            if (!psi.RedirectStandardOutput)
            {
                // Interactive admission output belongs to the password-console,
                // not the GUI. Refresh the canonical UI_CONTEXT after exit;
                // never infer successful connection from process ExitCode=0.
                await process.WaitForExitAsync(token);
                return new(process.ExitCode, null, "",
                    (elevated || process.ExitCode == 0) ? "" : "INTERACTIVE_WORKER_EXIT_" + process.ExitCode);
            }

            var stdoutTask = process.StandardOutput.ReadToEndAsync(token);
            var stderrTask = process.StandardError.ReadToEndAsync(token);
            await process.WaitForExitAsync(token);
            string stdout;
            string stderr;
            try
            {
                stdout = await stdoutTask;
                stderr = await stderrTask;
            }
            catch (DecoderFallbackException)
            {
                // Do not silently replace valid owner-provided Unicode with U+FFFD.
                return new(2, null, "", "WORKER_OUTPUT_NOT_UTF8");
            }
            JsonObject? json = null;
            if (!string.IsNullOrWhiteSpace(stdout))
            {
                try { json = JsonNode.Parse(stdout) as JsonObject; } catch { }
            }
            return new(process.ExitCode, json, stdout, stderr);
            }
            catch (OperationCanceledException) when (action == WorkerAction.UiContext)
            {
                // The deadline owns ONLY its read-only UI_CONTEXT subprocess.
                // Never kill an interactive credential prompt or active task.
                try { if (!process.HasExited) process.Kill(entireProcessTree: true); }
                catch (InvalidOperationException) { /* exited concurrently */ }
                catch (System.ComponentModel.Win32Exception) { /* best effort */ }
                throw;
            }
        }
        catch (System.ComponentModel.Win32Exception ex) when (ex.NativeErrorCode == 1223)
        {
            return new(1223, null, "", "UAC_CANCELLED");
        }
    }

    private static void Add(ProcessStartInfo psi, string value) => psi.ArgumentList.Add(value);
    private static void AddIf(ProcessStartInfo psi, string key, string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return;
        Add(psi, key); Add(psi, value);
    }

    public static string CreateTaskId(string taskGoal)
    {
        var safe = new string(taskGoal.Where(c => c <= 127 && char.IsLetterOrDigit(c)).Take(18).ToArray()).ToLowerInvariant();
        if (string.IsNullOrEmpty(safe)) safe = "task";
        var hash = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(Encoding.UTF8.GetBytes(taskGoal)))
            .ToLowerInvariant()[..8];
        return $"{safe}-{DateTime.UtcNow:yyyyMMddHHmm}-{hash}";
    }
}
