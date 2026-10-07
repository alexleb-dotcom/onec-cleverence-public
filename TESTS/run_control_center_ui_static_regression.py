from __future__ import annotations
import hashlib, json, re, sys
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
PRODUCT=ROOT/"PRODUCT"/"OneCChatWorker"
CC=PRODUCT/"control-center"/"OneCArchitecture.ControlCenter"
results=[]

def rec(name, ok, detail=""):
    results.append({"name":name,"pass":bool(ok),"detail":str(detail)})
    if not ok:
        raise AssertionError(f"{name}: {detail}")

def text(p): return p.read_text(encoding="utf-8-sig")
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

try:
    csproj=text(CC/"OneCArchitecture.ControlCenter.csproj")
    xaml=text(CC/"MainWindow.xaml")
    main=text(CC/"MainWindow.xaml.cs")
    app=text(CC/"App.xaml.cs")
    client=text(CC/"WorkerClient.cs")
    startup=text(CC/"StartupRegistration.cs")
    prefs=text(CC/"PreferencesStore.cs")
    theme=text(CC/"ThemeService.cs")
    manifest=text(CC/"app.manifest")
    launcher=text(PRODUCT/"OneCChatWorker.ps1")
    core=text(PRODUCT/"core"/"OneCChatWorker.Core.psm1")
    relay=text(PRODUCT/"relay"/"src"/"index.js")
    accounting=text(PRODUCT/"relay"/"src"/"s4-accounting.js")
    helper=text(PRODUCT/"runtime"/"hosted-helper.mjs")
    lock=json.loads(text(PRODUCT/"runtime.lock.json"))
    policy=json.loads(text(ROOT/"TOOLS"/"SHAREABLE_BINARY_REVIEW_POLICY.json"))
    exe=PRODUCT/"control-center"/"publish"/"OneCArchitecture.ControlCenter.exe"

    rec("wpf_dotnet10_self_contained_win_x64",
        "<TargetFramework>net10.0-windows</TargetFramework>" in csproj and
        "<UseWPF>true</UseWPF>" in csproj and
        "<RuntimeIdentifier>win-x64</RuntimeIdentifier>" in csproj and
        "<SelfContained>true</SelfContained>" in csproj and
        "<PublishSingleFile>true</PublishSingleFile>" in csproj)
    rec("dpi_manifest_permonitorv2",
        "<ApplicationManifest>app.manifest</ApplicationManifest>" in csproj and
        "<ApplicationHighDpiMode>PerMonitorV2</ApplicationHighDpiMode>" in csproj and "longPathAware" in manifest)
    all_ui="\n".join([xaml,main,app,client,startup,prefs,theme])
    rec("no_webview_loopback_service_ps7",
        not re.search(r"WebView2|HttpListener|Kestrel|ServiceBase|WindowsService|\bpwsh\b|PowerShell 7", all_ui, re.I))
    rec("native_user_session_tray",
        "NotifyIcon" in app and "Shutdown()" in app and "Window_Closing" in main and "e.Cancel = true" in main and "Hide();" in main)
    close=main[main.index("private void Window_Closing"):]
    rec("gui_close_does_not_stop_worker", not re.search(r"WorkerAction\.Stop|STOP|Stop-Worker", close))

    enum=re.search(r"internal enum WorkerAction\s*\{([^}]+)\}",client,re.S)
    rec("typed_worker_enum_present", enum is not None)
    actions={x.strip() for x in enum.group(1).replace("\n"," ").split(",") if x.strip()}
    expected={"UiContext","Apply","Verify","Repair","Start","Continue","Stop","Update","AddProject","AddParticipant","SetMain","AddExtension"}
    rec("typed_worker_actions_exact",actions==expected,sorted(actions))
    rec("typed_process_arguments_no_shell_concat","ArgumentList.Add" in client and "cmd.exe" not in client and " -Command " not in client)
    rec("no_password_capture",not re.search(r"PasswordBox|NetworkCredential|SecureString|savecred|CredentialManager|OneCSourceReader password",all_ui,re.I))

    ui_block=launcher[launcher.index("function Get-UiContext"):launcher.index("function Run-UiContext")]
    rec("ui_context_v1_bounded_fast","UI_CONTEXT_V1" in ui_block and "FAST_STATE_CHECK_V1" in ui_block and "fast_only=$true" in ui_block and "bounded=$true" in ui_block)
    rec("ui_context_no_deep_or_acquisition",not re.search(r"Get-TreeDigest|Verify-WorkerProject|Invoke-SourceAcquisition|Get-ChildItem\s+-Recurse|source_read|source_search",ui_block,re.I))
    rec("ui_context_no_secret_projection",not re.search(r"helper-secret|password|credential|token|authorization",ui_block,re.I))
    rec("relay_ui_projection_same_s4_owner","s4UiProjection(record)" in relay and "request_receipts" in accounting and "S4_DURABLE_TASK_ACCOUNTING_V1" in accounting)
    rec("helper_ui_cache_read_only","saveUiProjection" in helper and "ui-projection" in helper)

    sections=["HomePage","ProjectsPage","WorkPage","ActivityPage","MaintenancePage","SettingsPage","AdvancedPage"]
    rec("seven_navigation_sections",all(f'x:Name="{x}"' in xaml for x in sections))
    rec("home_state_cards",all(x in xaml for x in ["McpTitleLabel","CheckpointTitleLabel","SourceTitleLabel","OutputTitleLabel"]))
    rec("mcp_activity_timeline",'x:Name="ActivityList"' in xaml and "Recent MCP activity" in xaml)
    rec("checkpoint_continue_worker_owned","CONTINUE_AVAILABLE" in main and "WorkerAction.Continue" in main and "Continue-WorkerAdmission" in core)
    rec("maintenance_uses_worker_actions",all(x in main for x in ["WorkerAction.Apply","WorkerAction.Verify","WorkerAction.Repair"]) and "Invoke-SourceAcquisition" not in main)
    rec("advanced_only_technical_json","AdvancedText.Text = ctx.ToJsonString" in main and "head_checkpoint_sha256" not in xaml)
    rec("pending_s4_caps_not_numeric","AccountingPending" in main and not re.search(r"task_requests_limit|task_result_bytes_limit|task_requests_remaining|task_result_bytes_remaining",main))
    rec("exact_six_model_surface",lock["hosted_mcp"]["model_surface"]==["source_context","source_search","source_read","proposal_write","proposal_read","task_checkpoint_write"])
    rec("control_center_exact_six_surface",lock["control_center"]["model_surface"]==lock["hosted_mcp"]["model_surface"])

    rec("theme_system_light_dark",all(f'Tag="{x}"' in xaml for x in ["system","light","dark"]) and "AppsUseLightTheme" in theme)
    en=ET.parse(CC/"Resources"/"Strings.resx").getroot()
    ru=ET.parse(CC/"Resources"/"Strings.ru.resx").getroot()
    enmap={x.attrib["name"]:(x.findtext("value") or "") for x in en.findall("data")}
    rumap={x.attrib["name"]:(x.findtext("value") or "") for x in ru.findall("data")}
    rec("ru_en_key_parity",set(enmap)==set(rumap),f"en={len(enmap)} ru={len(rumap)}")
    rec("ru_en_distinct_home",enmap.get("NavHome")=="Home" and rumap.get("NavHome") and rumap.get("NavHome")!="Home")
    rec("keyboard_accessibility_basics",'KeyboardNavigation.TabNavigation="Cycle"' in xaml and xaml.count("AutomationProperties.Name")>=8)
    rec("min_window_and_layout_rounding",'MinWidth="920"' in xaml and 'MinHeight="620"' in xaml and 'UseLayoutRounding="True"' in xaml and 'SnapsToDevicePixels="True"' in xaml)

    rec("startup_explicit_operator_choice",
        "Start Control Center with Windows (operator choice)" in xaml and
        "StartupCheckBox_Changed" in main and "Registry.CurrentUser" in startup and
        "CurrentVersion\\Run" in startup and "StartupRegistration.Apply" not in app and
        "bool StartWithWindows = false" in prefs)
    rec("preferences_are_ui_only",not re.search(r"project|task|account|admission|secret|credential",prefs,re.I))

    rec("install_owner_control_center","function Install-ControlCenterArtifact" in core and "$controlCenter=Install-ControlCenterArtifact" in core and "Get-ControlCenterStartMenuShortcutPath" in core)
    rec("update_reuses_install_owner","function Run-Update" in launcher and "Install-OneCChatWorker" in launcher[launcher.index("function Run-Update"):launcher.index("function Run-AddProject")])
    rec("start_menu_shortcut_owned","OneC Architecture Control Center.lnk" in core and "WScript.Shell" in core)
    rec("uninstall_removes_shortcut","Get-ControlCenterStartMenuShortcutPath" in core[core.index("function Get-UninstallPlan"):core.index("function Invoke-SafeUninstall")])

    rec("published_exe_exists",exe.is_file())
    rec("published_exe_pe",exe.read_bytes()[:2]==b"MZ")
    rec("published_exe_below_github_hard_limit",exe.stat().st_size<100*1024*1024,exe.stat().st_size)
    exe_sha=sha(exe)
    rel="control-center/publish/OneCArchitecture.ControlCenter.exe"
    rec("runtime_lock_binary_hash",lock["components"].get(rel)==exe_sha,f"{lock['components'].get(rel)} vs {exe_sha}")
    prow=next((x for x in policy["reviewed_binary_files"] if x["path"]=="PRODUCT/OneCChatWorker/"+rel),None)
    rec("shareable_binary_policy_exact",prow is not None and prow["sha256"]==exe_sha, None if prow is None else prow["sha256"])
    cc=lock["control_center"]
    rec("unsigned_internal_pilot_explicit",cc["signing_status"]=="UNSIGNED_INTERNAL_PILOT")
    rec("package_no_extra_runtime_surface",cc["service"] is False and cc["loopback_listener"] is False and cc["webview2"] is False and cc["powershell7_required"] is False)

    print(json.dumps({"result":"PASS","checks":len(results),"results":results,"binary_sha256":exe_sha,"binary_bytes":exe.stat().st_size},ensure_ascii=False))
except Exception as e:
    print(json.dumps({"result":"FAIL","checks":len(results),"results":results,"error":repr(e)},ensure_ascii=False),file=sys.stderr)
    raise
