using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json.Nodes;

namespace OneCArchitecture.ControlCenter;

internal enum WorkerAction
{
    UiContext, Apply, Verify, Repair, Start, Continue, Stop, Update,
    AddProject, AddParticipant, SetMain, AddExtension
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
    bool ReplaceExisting = false);

internal sealed record WorkerCallResult(int ExitCode, JsonObject? Json, string StandardOutput, string StandardError);

internal sealed class WorkerClient
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
            [WorkerAction.AddExtension] = "ADD_EXTENSION"
        };

    public string LauncherPath { get; }
    public string WorkerRoot { get; }
    public string ProgramDataRoot { get; }

    public WorkerClient()
    {
        LauncherPath = Environment.GetEnvironmentVariable("ONEC_CONTROL_CENTER_LAUNCHER")
            ?? @"C:\OneCChatWorker\OneCChatWorker.ps1";
        WorkerRoot = Environment.GetEnvironmentVariable("ONEC_CONTROL_CENTER_WORKER_ROOT")
            ?? @"C:\OneCChatWorker";
        ProgramDataRoot = Environment.GetEnvironmentVariable("ONEC_CONTROL_CENTER_PROGRAM_DATA")
            ?? @"C:\ProgramData\OneCChatWorker";
    }

    public Task<WorkerCallResult> GetContextAsync(CancellationToken token = default) =>
        RunAsync(WorkerAction.UiContext, new(), false, token);

    public async Task<WorkerCallResult> RunAsync(
        WorkerAction action, WorkerActionArgs args, bool elevated = false, CancellationToken token = default)
    {
        if (!Modes.TryGetValue(action, out var mode))
            throw new InvalidOperationException("WORKER_ACTION_NOT_ALLOWLISTED");
        if (!File.Exists(LauncherPath))
            return new(2, null, "", "WORKER_LAUNCHER_NOT_FOUND");

        var psi = new ProcessStartInfo("powershell.exe")
        {
            UseShellExecute = elevated,
            CreateNoWindow = !elevated,
            RedirectStandardOutput = !elevated,
            RedirectStandardError = !elevated,
            WindowStyle = elevated ? ProcessWindowStyle.Hidden : ProcessWindowStyle.Hidden,
            Verb = elevated ? "runas" : ""
        };
        Add(psi, "-NoProfile");
        Add(psi, "-ExecutionPolicy"); Add(psi, "Bypass");
        Add(psi, "-File"); Add(psi, LauncherPath);
        Add(psi, "-Mode"); Add(psi, mode);
        Add(psi, "-WorkerRoot"); Add(psi, WorkerRoot);
        Add(psi, "-ProgramDataRoot"); Add(psi, ProgramDataRoot);
        if (!elevated) Add(psi, "-Json");

        AddIf(psi, "-ProjectId", args.ProjectId);
        AddIf(psi, "-ParticipantId", args.ParticipantId);
        AddIf(psi, "-ExtensionId", args.ExtensionId);
        AddIf(psi, "-SourcePath", args.SourcePath);
        AddIf(psi, "-DisplayName", args.DisplayName);
        AddIf(psi, "-Role", args.Role);
        AddIf(psi, "-TaskId", args.TaskId);
        AddIf(psi, "-TaskGoal", args.TaskGoal);
        if (args.ReplaceExisting) Add(psi, "-ReplaceExisting");

        try
        {
            using var process = Process.Start(psi) ?? throw new InvalidOperationException("WORKER_PROCESS_START_FAILED");
            if (elevated)
            {
                await process.WaitForExitAsync(token);
                return new(process.ExitCode, null, "", "");
            }

            var stdoutTask = process.StandardOutput.ReadToEndAsync(token);
            var stderrTask = process.StandardError.ReadToEndAsync(token);
            await process.WaitForExitAsync(token);
            var stdout = await stdoutTask;
            var stderr = await stderrTask;
            JsonObject? json = null;
            if (!string.IsNullOrWhiteSpace(stdout))
            {
                try { json = JsonNode.Parse(stdout) as JsonObject; } catch { }
            }
            return new(process.ExitCode, json, stdout, stderr);
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
