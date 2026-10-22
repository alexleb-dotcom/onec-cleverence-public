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
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr h);
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
        while (timer.Elapsed < TimeSpan.FromSeconds(20))
        {
            try { if (condition()) return; }
            catch (InvalidOperationException ex) when (ex.Message.StartsWith("CONTROL_MISSING:", StringComparison.Ordinal)) { }
            catch (ElementNotAvailableException) { }
            Thread.Sleep(100);
        }
        throw new TimeoutException("PACKAGED_TIMEOUT:" + name);
    }
    static AutomationElement Find(string id) => Root.FindFirst(TreeScope.Descendants,
        new PropertyCondition(AutomationElement.AutomationIdProperty, id)) ?? throw new InvalidOperationException("CONTROL_MISSING:" + id);
    static string FocusId
    {
        get { try { return AutomationElement.FocusedElement?.Current.AutomationId ?? ""; } catch (ElementNotAvailableException) { return ""; } }
    }
    static string FocusName
    {
        get { try { return AutomationElement.FocusedElement?.Current.Name ?? ""; } catch (ElementNotAvailableException) { return ""; } }
    }
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
        Trace.Add(new { key, focus = FocusId, focused_name = FocusName });
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
    static IEnumerable<AutomationElement> OwnedWindows()
    {
        foreach(var top in AutomationElement.RootElement.FindAll(TreeScope.Children,
            new PropertyCondition(AutomationElement.ProcessIdProperty, Owned.Id)).Cast<AutomationElement>())
        {
            yield return top;
            foreach(var child in top.FindAll(TreeScope.Descendants,
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Window)).Cast<AutomationElement>())
                if(child.Current.ProcessId == Owned.Id) yield return child;
        }
    }
    static AutomationElement OwnedNativeDialog()
    {
        AutomationElement? found = null;
        Wait(() => {
            found = null;
            foreach(var top in AutomationElement.RootElement.FindAll(TreeScope.Children,
                new PropertyCondition(AutomationElement.ProcessIdProperty, Owned.Id)).Cast<AutomationElement>())
            {
                found = top.Current.ClassName == "#32770" ? top : top.FindFirst(TreeScope.Descendants,
                    new PropertyCondition(AutomationElement.ClassNameProperty, "#32770"));
                if(found is not null) break;
            }
            return found is not null;
        }, "owned native dialog");
        return found!;
    }
    static void ClickNativeOk(AutomationElement dialog)
    {
        var ok = dialog.FindFirst(TreeScope.Descendants, new PropertyCondition(AutomationElement.AutomationIdProperty, "1"))
            ?? throw new InvalidOperationException("NATIVE_OK_BUTTON_MISSING");
        var handle = new IntPtr(dialog.Current.NativeWindowHandle);
        ((InvokePattern)ok.GetCurrentPattern(InvokePattern.Pattern)).Invoke();
        Wait(() => !IsWindow(handle), "native dialog closes");
    }
    static void PickArchive(string button, string archive)
    {
        var wizard = Root;
        ((InvokePattern)Find(button).GetCurrentPattern(InvokePattern.Pattern)).Invoke();
        var dialog = OwnedNativeDialog();
        var edits = dialog.FindAll(TreeScope.Descendants,
            new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Edit)).Cast<AutomationElement>().ToArray();
        Console.WriteLine("NATIVE_EDITS " + string.Join(" | ", edits.Select(x => x.Current.AutomationId + ":" + x.Current.Name)));
        var fileName = edits.FirstOrDefault(x => x.Current.AutomationId == "1148")
            ?? edits.FirstOrDefault(x => x.Current.Name.StartsWith("File name", StringComparison.OrdinalIgnoreCase))
            ?? edits.LastOrDefault(x => x.Current.IsEnabled && x.TryGetCurrentPattern(ValuePattern.Pattern, out _))
            ?? throw new InvalidOperationException("NATIVE_FILE_NAME_EDIT_MISSING");
        var handle = new IntPtr(dialog.Current.NativeWindowHandle);
        SetForegroundWindow(handle);
        Wait(() => { GetWindowThreadProcessId(GetForegroundWindow(), out var foregroundPid); return foregroundPid == Owned.Id; }, "owned file dialog foreground");
        fileName.SetFocus();
        ((ValuePattern)fileName.GetCurrentPattern(ValuePattern.Pattern)).SetValue(archive);
        Console.WriteLine("NATIVE_FILENAME " + fileName.Current.AutomationId + " = " + ((ValuePattern)fileName.GetCurrentPattern(ValuePattern.Pattern)).Current.Value);
        Key(13);
        Wait(() => !IsWindow(handle), "native archive selection closes dialog");
        Root = wizard;
    }

    public static int Installed(string exe, string evidence, bool firstRun, string? mainArchive = null, string? extensionArchive = null)
    {
        Directory.CreateDirectory(evidence);
        var prefs = Path.Combine(evidence, "prefs"); Directory.CreateDirectory(prefs);
        File.WriteAllText(Path.Combine(prefs, "preferences.json"), """{"Language":"en","Theme":"light","StartWithWindows":false}""");
        var psi = new ProcessStartInfo(exe) { UseShellExecute = false };
        psi.Environment["ONEC_CONTROL_CENTER_PREFERENCES_ROOT"] = prefs;
        Owned = Process.Start(psi)!;
        try
        {
            AutomationElement? dialog = null;
            Wait(() => {
                dialog = OwnedWindows().LastOrDefault(x => x.Current.NativeWindowHandle != 0 && x.FindFirst(TreeScope.Descendants,
                    new PropertyCondition(AutomationElement.AutomationIdProperty, firstRun ? "ProjectNameBox" : "RecommendationText")) is not null);
                return dialog is not null;
            }, firstRun ? "automatic installed first project wizard" : "installed project reopen");
            Root = dialog!; Window = new IntPtr(Root.Current.NativeWindowHandle);
            Shot(Path.Combine(evidence, firstRun ? "first-run-wizard.png" : "installed-readback.png"));
            if (firstRun)
            {
                Assert(Find("BrowseMainButton").Current.IsEnabled, "MAIN archive picker enabled");
                Assert(Find("ExtensionCheck").Current.IsEnabled, "optional extensions available");
                if (mainArchive is null)
                    ((InvokePattern)Find("CancelButton").GetCurrentPattern(InvokePattern.Pattern)).Invoke();
                else
                {
                    ((ValuePattern)Find("ProjectNameBox").GetCurrentPattern(ValuePattern.Pattern)).SetValue("fixture");
                    ((ValuePattern)Find("SystemNameBox").GetCurrentPattern(ValuePattern.Pattern)).SetValue("main");
                    PickArchive("BrowseMainButton", mainArchive);
                    ((TogglePattern)Find("ExtensionCheck").GetCurrentPattern(TogglePattern.Pattern)).Toggle();
                    PickArchive("BrowseExtensionButton", extensionArchive!);
                    ((InvokePattern)Find("CreateButton").GetCurrentPattern(InvokePattern.Pattern)).Invoke();
                    var review = OwnedNativeDialog();
                    Root = review; Window = new IntPtr(review.Current.NativeWindowHandle);
                    Shot(Path.Combine(evidence, "wizard-review.png"));
                    ClickNativeOk(review);
                    var result = OwnedNativeDialog();
                    Root = result; Window = new IntPtr(result.Current.NativeWindowHandle);
                    Assert(result.FindAll(TreeScope.Descendants, new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Text))
                        .Cast<AutomationElement>().Any(x => x.Current.Name.Contains("State confirmed by Worker", StringComparison.OrdinalIgnoreCase)),
                        "wizard result requires accepted canonical Worker readback");
                    Shot(Path.Combine(evidence, "wizard-result.png"));
                    ClickNativeOk(result);
                }
            }
            File.WriteAllText(Path.Combine(evidence, "result.json"), JsonSerializer.Serialize(new {
                result="PASS", first_run=firstRun, native_archive_dialogs_and_wizard_publication=mainArchive is not null, actual_installed_exe_sha256=Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(exe))).ToLowerInvariant(),
                owner="real installed Worker", human_uac_consent="NOT_PROVED"
            }));
            return 0;
        }
        catch
        {
            foreach(var window in OwnedWindows())
            {
                Console.WriteLine("OWNED_WINDOW " + window.Current.Name);
                Console.WriteLine(string.Join(" | ", window.FindAll(TreeScope.Descendants,
                    new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Text)).Cast<AutomationElement>().Select(x => x.Current.Name)));
                Root=window; Window=new IntPtr(window.Current.NativeWindowHandle);
                Shot(Path.Combine(evidence, "failure-" + window.Current.NativeWindowHandle + ".png"));
            }
            throw;
        }
        finally { if (!Owned.HasExited) { Owned.Kill(); Owned.WaitForExit(10000); } Owned.Dispose(); }
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
 $body=[IO.File]::ReadAllText((Join-Path $PSScriptRoot $file),[Text.Encoding]::UTF8)
 $bytes=[Text.UTF8Encoding]::new($false).GetBytes($body)
 [Console]::OpenStandardOutput().Write($bytes,0,$bytes.Length); exit 0
}
if($Mode -ne 'START' -or $ProjectId -ne 'RetailGroup'){throw 'FIXTURE_OPERATION_REJECTED'}
# Capture only: never load a worker module, reserve admission or execute START.
@{mode=$Mode;project_id=$ProjectId;task_id=$TaskId;fake_owner=$true} | ConvertTo-Json -Compress | Add-Content (Join-Path $PSScriptRoot 'captured.jsonl')
[Console]::Write('{}')
""");
        foreach (var id in new[] { "unselected", "NeoHim", "RetailGroup" })
        {
            var ctx = FixtureWorker.Context(id == "unselected" ? null : id);
            // Owner-provided Unicode must round-trip across REAL powershell.exe -File,
            // WorkerClient UTF-8 capture, JsonNode, and the packaged WPF automation tree.
            foreach (var project in ctx["projects"]!.AsArray().OfType<JsonObject>())
                project["display_name"] = project["project_id"]!.GetValue<string>() + " — ТОЛЬКО ТЕСТ";
            if (ctx["selected_project"] is JsonObject selected)
                selected["display_name"] = selected["project_id"]!.GetValue<string>() + " — ТОЛЬКО ТЕСТ";
            // Disable every mutation except a fake START; wizard cancellation is UI-only.
            foreach (var action in ctx["actions"]!.AsObject()) if (action.Key is not ("start" or "add_project")) action.Value!["enabled"] = false;
            if (id == "RetailGroup")
            {
                // No source trees or native owner: UI selection gates only. This
                // lane must stay usable without administrator or OS consent.
                ctx["source"]!["artifacts"] = JsonNode.Parse("""
                [{"key":"fixture|MAIN|main","participant_id":"fixture","artifact_type":"MAIN","artifact_id":"main"},
                 {"key":"fixture|EXTENSION|testext","participant_id":"fixture","artifact_type":"EXTENSION","artifact_id":"testext"}]
                """);
                ctx["actions"]!["sync_extension"] = new JsonObject { ["enabled"] = true, ["reason"] = "AVAILABLE" };
            }
            ctx["operation"] = new JsonObject { ["current"] = new JsonObject { ["operation_type"] = "UPDATE", ["state"] = "PASS" } };
            File.WriteAllText(Path.Combine(scratch, id + ".json"),
                ctx.ToJsonString(new JsonSerializerOptions {
                    Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
                }), new System.Text.UTF8Encoding(false));
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
            Console.WriteLine("PACKAGED_WINDOW title=" + Owned.MainWindowTitle + " class=" + Root.Current.ClassName);
            Wait(() => Find("RecommendationText").Current.Name.Length > 0, "initial context");
            Assert(Find("RecommendationText").Current.Name.Length > 0, "packaged fake-owner UI context rendered");
            Shot(Path.Combine(evidence, "packaged-startup.png"));
            SetForegroundWindow(Window);
            Wait(() => GetForegroundWindow() == Window, "owned foreground");
            Shot(Path.Combine(evidence, "packaged-ru-dark-Home.png"));
            Page("NavProjectsButton", Localization.Get("NavProjects"));
            var projectElements = Find("ProjectsList").FindAll(TreeScope.Descendants, Condition.TrueCondition);
            Assert(projectElements.Cast<AutomationElement>().Any(x =>
                x.Current.Name.Contains("RetailGroup — ТОЛЬКО ТЕСТ", StringComparison.Ordinal)),
                "real packaged WPF preserves owner-provided Cyrillic and em dash, no U+FFFD");
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
            TabTo("SourceArtifactCombo"); Key(36); // Home selects Main.
            Wait(() => !Find("SyncExtensionButton").Current.IsEnabled, "Main cannot sync");
            Assert(FocusWithin("SourceArtifactCombo"), "Main selected through actual combo keyboard input");
            Key(35); // End selects the only synthetic extension.
            Wait(() => Find("SyncExtensionButton").Current.IsEnabled, "selected extension can sync");
            Assert(FocusWithin("SourceArtifactCombo"), "extension selected through actual combo keyboard input");
            TabTo("SyncExtensionButton");
            Shot(Path.Combine(evidence, "packaged-ru-dark-SYNC-keyboard-focus-Maintenance.png"));
            // Do not press Space here: the real packaged handler requests runas.
            // An unattended UI-only lane cannot provide or cancel OS consent.
            Assert(File.ReadAllLines(capture).Length == 1, "source selection/focus dispatches no mutation");
            File.WriteAllText(Path.Combine(evidence, "packaged-result.json"), JsonSerializer.Serialize(new {
                result="PASS", executable_sha256=sha, pid=Owned.Id, process_executable="isolated copy of distributed EXE",
                native_hwnd_capture=true, keyboard="Tab / arrows / Enter / Space through native key events", trace=Trace,
                captured_start=JsonNode.Parse(File.ReadAllText(capture)), fixture_owner=true, production_access=false,
                source_combo_keyboard_selection=true, sync_button_keyboard_focus=true,
                sync_keyboard_activation="NOT_PROVED", elevated_canonical_readback="NOT_PROVED", os_uac="NOT_PROVED",
                limitations=new[]{"Synthetic owner; Sync activation requires separate human OS consent test. No source publication proven.", "No production execution; no physical multi-monitor DPI migration tested."}
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
