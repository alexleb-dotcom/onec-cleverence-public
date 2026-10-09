using System.Text;
using System.Text.Json;
using OneCArchitecture.ControlCenter;
var root = Path.GetFullPath(args[0]);
Directory.CreateDirectory(root);
var launcher = Path.Combine(root, "capture.ps1");
File.WriteAllText(launcher, """
param([string]$Mode,[string]$WorkerRoot,[string]$ProgramDataRoot,[switch]$Json,
[string]$ProjectId,[string]$ExpectedGenerationId,[string]$ExpectedArtifactKey)
@{mode=$Mode;project=$ProjectId;generation=$ExpectedGenerationId;key=$ExpectedArtifactKey}|ConvertTo-Json -Compress
""", new UTF8Encoding(true));
Environment.SetEnvironmentVariable("ONEC_CONTROL_CENTER_LAUNCHER", launcher);
Environment.SetEnvironmentVariable("ONEC_CONTROL_CENTER_WORKER_ROOT", Path.Combine(root, "worker"));
Environment.SetEnvironmentVariable("ONEC_CONTROL_CENTER_PROGRAM_DATA", Path.Combine(root, "data"));
var client = new WorkerClient();
var cases = new List<string>();
void Check(bool ok, string name) { if (!ok) throw new Exception(name); cases.Add(name); Console.WriteLine("PASS " + name); }
var expected = new WorkerActionArgs(ProjectId: "RetailGroup", ExpectedGenerationId: "update-1111111111111111", ExpectedArtifactKey: "un|EXTENSION|bit");
foreach (var action in new[] { WorkerAction.AcceptSourceUpdate, WorkerAction.CancelSourceUpdate })
{
    foreach (var elevated in new[] { false, true })
    {
        var psi = client.CreateStartInfo(action, expected, elevated);
        var a = psi.ArgumentList.ToArray();
        Check(a[Array.IndexOf(a, "-ExpectedGenerationId") + 1] == expected.ExpectedGenerationId, $"{action} elevated={elevated} exact generation");
        Check(a[Array.IndexOf(a, "-ExpectedArtifactKey") + 1] == expected.ExpectedArtifactKey, $"{action} elevated={elevated} exact key");
        Check(psi.UseShellExecute == elevated && psi.Verb == (elevated ? "runas" : "") && psi.WindowStyle == System.Diagnostics.ProcessWindowStyle.Hidden, $"{action} elevated={elevated} existing process policy");
    }
    var result = await client.RunAsync(action, expected);
    Check(result.ExitCode == 0 && result.Json?["generation"]?.GetValue<string>() == expected.ExpectedGenerationId &&
        result.Json?["key"]?.GetValue<string>() == expected.ExpectedArtifactKey && result.Json?["project"]?.GetValue<string>() == "RetailGroup", $"{action} actual PowerShell child argv round-trip");
    bool rejected = false;
    try { client.CreateStartInfo(action, new(ProjectId: "RetailGroup"), false); }
    catch (InvalidOperationException ex) { rejected = ex.Message == "SOURCE_UPDATE_EXPECTED_IDENTITY_REQUIRED"; }
    Check(rejected, $"{action} typed ProjectId-only rejected before process start");
}
File.WriteAllText(Path.Combine(root, "typed-wire.json"), JsonSerializer.Serialize(new { result = "PASS", checks = cases.Count, cases, actual_uac_executed = false }, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine($"TYPED_SOURCE_FENCE_PASS checks={cases.Count}");
