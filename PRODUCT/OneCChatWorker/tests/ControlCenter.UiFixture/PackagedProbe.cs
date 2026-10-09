using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Windows.Automation;
using System.Windows.Interop;
using System.Windows.Media.Imaging;
using OneCArchitecture.ControlCenter;

// Drives only the exact packaged process created by this probe. No desktop-wide
// screenshots, installed worker roots, real lifecycle operations or runtime imports.
internal static class PackagedProbe
{
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern void keybd_event(byte key, byte scan, uint flags, UIntPtr extra);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
    [DllImport("user32.dll")] static extern IntPtr GetDC(IntPtr h);
    [DllImport("user32.dll")] static extern int ReleaseDC(IntPtr h, IntPtr dc);
    [DllImport("gdi32.dll")] static extern IntPtr CreateCompatibleDC(IntPtr dc);
    [DllImport("gdi32.dll")] static extern IntPtr CreateCompatibleBitmap(IntPtr dc, int w, int h);
    [DllImport("gdi32.dll")] static extern IntPtr SelectObject(IntPtr dc, IntPtr o);
    [DllImport("gdi32.dll")] static extern bool DeleteDC(IntPtr dc);
    [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr o);
    [StructLayout(LayoutKind.Sequential)] struct RECT { public int Left, Top, Right, Bottom; }
    static readonly List<object> Trace = [];
    static Process Owned = null!;
    static IntPtr Window;
    static AutomationElement Root = null!;
    static void Assert(bool value, string name) { if (!value) throw new InvalidOperationException("PACKAGED_ASSERT:" + name); Console.WriteLine("PASS packaged " + name); }
    static void Wait(Func<bool> condition, string name)
    {
        var timer = Stopwatch.StartNew();
        while (timer.Elapsed < TimeSpan.FromSeconds(20)) { if (condition()) return; Thread.Sleep(100); }
        throw new TimeoutException("PACKAGED_TIMEOUT:" + name);
    }
    static AutomationElement Find(string id) => Root.FindFirst(TreeScope.Descendants,
        new PropertyCondition(AutomationElement.AutomationIdProperty, id)) ?? throw new InvalidOperationException("CONTROL_MISSING:" + id);
    static string FocusId => AutomationElement.FocusedElement?.Current.AutomationId ?? "";
    static bool FocusWithin(string id)
    {
        var node = AutomationElement.FocusedElement;
        while (node is not null && node != Root)
        {
            if (node.Current.AutomationId == id) return true;
            node = TreeWalker.ControlViewWalker.GetParent(node);
        }
        return false;
    }
    static void Key(byte key)
    {
        GetWindowThreadProcessId(GetForegroundWindow(), out var pid);
        Assert(pid == Owned.Id, "keyboard input restricted to owned EXE");
        keybd_event(key, 0, 0, UIntPtr.Zero); keybd_event(key, 0, 2, UIntPtr.Zero);
        Thread.Sleep(120);
        Trace.Add(new { key, focus = FocusId, focused_name = AutomationElement.FocusedElement?.Current.Name });
    }
    static void TabTo(string id)
    {
        for (int i = 0; i < 40 && !FocusWithin(id); i++) Key(9);
        Assert(FocusWithin(id), "Tab focus " + id);
        Assert(AutomationElement.FocusedElement.Current.HasKeyboardFocus, "visible keyboard focus " + id);
    }
    static void Page(string id, string title)
    {
        TabTo(id); Key(13);
        Wait(() => Find("PageTitle").Current.Name == title, title);
    }
    static void Shot(string path)
    {
        GetWindowThreadProcessId(Window, out var pid); Assert(pid == Owned.Id, "capture belongs to packaged PID");
        Assert(GetWindowRect(Window, out var r), "window rectangle");
        var dc = GetDC(Window); var target = CreateCompatibleDC(dc);
        var bitmap = CreateCompatibleBitmap(dc, r.Right-r.Left, r.Bottom-r.Top); var previous = SelectObject(target, bitmap);
        try
        {
            Assert(PrintWindow(Window, target, 2), "native packaged HWND capture");
            var source = Imaging.CreateBitmapSourceFromHBitmap(bitmap, IntPtr.Zero, System.Windows.Int32Rect.Empty, BitmapSizeOptions.FromEmptyOptions());
            var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(source));
            using var stream = File.Create(path); png.Save(stream);
        }
        finally { SelectObject(target, previous); DeleteObject(bitmap); DeleteDC(target); ReleaseDC(Window, dc); }
    }
    public static int Run(string repository, string evidence)
    {
        Localization.SetLanguage("ru");
        repository = Path.GetFullPath(repository); evidence = Path.GetFullPath(evidence);
        var scratch = Path.Combine(Path.GetTempPath(), "onec-packaged-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(scratch); Directory.CreateDirectory(evidence);
        var relative = "PRODUCT/OneCChatWorker/control-center/publish/OneCArchitecture.ControlCenter.exe";
        var original = Path.Combine(repository, relative); var exe = Path.Combine(scratch, "OneCArchitecture.ControlCenter.exe");
        var sha = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(original))).ToLowerInvariant();
        var manifest = JsonNode.Parse(File.ReadAllText(Path.Combine(repository, "DISTRIBUTION_MANIFEST.json")))!;
        // The pinned identity is checked before executing any UI bytes.
        var entry = manifest["files"]!.AsArray().First(n => n!["path"]!.GetValue<string>() == relative)!;
        Assert(entry["sha256"]!.GetValue<string>() == sha && entry["size"]!.GetValue<long>() == new FileInfo(original).Length,
            "manifest pins exact packaged path, size and SHA");
        var runtimeLock = JsonNode.Parse(File.ReadAllText(Path.Combine(repository, "PRODUCT/OneCChatWorker/runtime.lock.json")))!;
        Assert(runtimeLock["components"]!["control-center/publish/OneCArchitecture.ControlCenter.exe"]!.GetValue<string>() == sha,
            "runtime.lock pins exact packaged path and SHA");
        File.Copy(original, exe);
        Assert(Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(exe))).ToLowerInvariant() == sha, "isolated executable bytes match distribution");
        var launcher = Path.Combine(scratch, "mock-owner.ps1");
        File.WriteAllText(launcher, """
param([string]$Mode,[string]$WorkerRoot,[string]$ProgramDataRoot,[switch]$Json,[string]$ProjectId,[string]$TaskId,[string]$TaskGoal)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
if($WorkerRoot -ne $PSScriptRoot -or $ProgramDataRoot -ne $PSScriptRoot){throw 'FIXTURE_ROOT_MISMATCH'}
if($Mode -eq 'UI_CONTEXT') {
 $file=if($ProjectId -eq 'RetailGroup'){'RetailGroup.json'}elseif($ProjectId -eq 'NeoHim'){'NeoHim.json'}else{'unselected.json'}
 [Console]::Write([IO.File]::ReadAllText((Join-Path $PSScriptRoot $file))); exit 0
}
if($Mode -ne 'START' -or $ProjectId -ne 'RetailGroup'){throw 'FIXTURE_OPERATION_REJECTED'}
# Capture only: never load a worker module, reserve admission or execute START.
@{mode=$Mode;project_id=$ProjectId;task_id=$TaskId;fake_owner=$true} | ConvertTo-Json -Compress | Add-Content (Join-Path $PSScriptRoot 'captured.jsonl')
[Console]::Write('{}')
""");
        foreach (var id in new[] { "unselected", "NeoHim", "RetailGroup" })
        {
            var ctx = FixtureWorker.Context(id == "unselected" ? null : id);
            // Disable every mutation except a fake START; wizard cancellation is UI-only.
            foreach (var action in ctx["actions"]!.AsObject()) if (action.Key is not ("start" or "add_project")) action.Value!["enabled"] = false;
            ctx["operation"] = new JsonObject { ["current"] = new JsonObject { ["operation_type"] = "UPDATE", ["state"] = "PASS" } };
            File.WriteAllText(Path.Combine(scratch, id + ".json"), ctx.ToJsonString());
        }
        File.WriteAllText(Path.Combine(scratch, "preferences.json"), """{"Language":"ru","Theme":"dark","StartWithWindows":false}""");
        var psi = new ProcessStartInfo(exe) { UseShellExecute = false, WorkingDirectory = scratch };
        psi.Environment["ONEC_CONTROL_CENTER_LAUNCHER"] = launcher;
        psi.Environment["ONEC_CONTROL_CENTER_WORKER_ROOT"] = scratch;
        psi.Environment["ONEC_CONTROL_CENTER_PROGRAM_DATA"] = scratch;
        psi.Environment["ONEC_CONTROL_CENTER_PREFERENCES_ROOT"] = scratch;
        Owned = Process.Start(psi)!;
        try
        {
            Wait(() => { Owned.Refresh(); Window = Owned.MainWindowHandle; return Window != IntPtr.Zero; }, "packaged process window");
            Root = AutomationElement.FromHandle(Window);
            Assert(string.Equals(Owned.MainModule!.FileName, exe, StringComparison.OrdinalIgnoreCase), "actual process executable identity");
            Wait(() => Find("RecommendationText").Current.Name.Length > 0, "initial context");
            SetForegroundWindow(Window);
            Wait(() => GetForegroundWindow() == Window, "owned foreground");
            Shot(Path.Combine(evidence, "packaged-ru-dark-Home.png"));
            Page("NavProjectsButton", Localization.Get("NavProjects"));
            TabTo("ProjectsList"); Key(40); Key(40);
            Wait(() => Find("SelectedProjectText").Current.Name.Contains("RetailGroup"), "RetailGroup canonical selection");
            // Selecting a project refreshes context asynchronously. Focus must remain
            // inside the list, also across the periodic context refresh.
            Assert(FocusWithin("ProjectsList") && AutomationElement.FocusedElement.Current.Name.Contains("RetailGroup"), "arrow selection retains RetailGroup row focus");
            Thread.Sleep(4500);
            Assert(FocusWithin("ProjectsList") && AutomationElement.FocusedElement.Current.Name.Contains("RetailGroup"), "timer refresh retains RetailGroup row focus");
            Shot(Path.Combine(evidence, "packaged-ru-dark-RetailGroup-keyboard-Projects.png"));
            Page("NavWorkButton", Localization.Get("NavWork"));
            TabTo("StartButton"); Shot(Path.Combine(evidence, "packaged-ru-dark-START-keyboard-focus-Work.png"));
            Key(32); // Space activates START through the real WPF keyboard pipeline.
            var capture = Path.Combine(scratch, "captured.jsonl");
            Wait(() => File.Exists(capture), "fake owner captured keyboard START");
            Assert(File.ReadAllLines(capture).Length == 1 && File.ReadAllText(capture).Contains("RetailGroup"), "exactly one fake START targets RetailGroup");
            Page("NavMaintenanceButton", Localization.Get("NavMaintenance"));
            Assert(Find("OperationText").Current.Name.Contains(Localization.Get("Verified")) && Find("HelperBadge").Current.Name.Contains(Localization.Get("Offline")), "F-G UPDATE PASS is not helper connectivity");
            Shot(Path.Combine(evidence, "packaged-ru-dark-update-pass-helper-offline-Maintenance.png"));
            File.WriteAllText(Path.Combine(evidence, "packaged-result.json"), JsonSerializer.Serialize(new {
                result="PASS", executable_sha256=sha, pid=Owned.Id, process_executable="isolated copy of distributed EXE",
                native_hwnd_capture=true, keyboard="Tab / arrows / Enter / Space through native key events", trace=Trace,
                captured_start=JsonNode.Parse(File.ReadAllText(capture)), fixture_owner=true, production_access=false,
                limitations=new[]{"No production execution; no physical multi-monitor DPI migration tested."}
            }, new JsonSerializerOptions { WriteIndented=true }));
            return 0;
        }
        finally
        {
            File.WriteAllText(Path.Combine(evidence, "keyboard-trace.json"), JsonSerializer.Serialize(Trace, new JsonSerializerOptions { WriteIndented=true }));
            if (!Owned.HasExited) { Owned.Kill(); Owned.WaitForExit(10000); } Owned.Dispose();
        }
    }
}
