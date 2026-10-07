using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Windows;
using Forms = System.Windows.Forms;

namespace OneCArchitecture.ControlCenter;

internal sealed record ProjectWizardResult(
    string ProjectId, string ProjectName, string ParticipantId, string SystemName, string Role,
    string MainPath, string? ExtensionId, string? ExtensionName, string? ExtensionPath);

public partial class ProjectWizardWindow : Window
{
    internal ProjectWizardResult? Result { get; private set; }

    public ProjectWizardWindow()
    {
        InitializeComponent();
        RoleBox.Text = "ERP";
        SystemNameBox.Text = "Основная база 1С";
    }

    private void BrowseMain_Click(object sender, RoutedEventArgs e) => BrowseInto(MainPathBox);
    private void BrowseExtension_Click(object sender, RoutedEventArgs e) => BrowseInto(ExtensionPathBox);

    private static void BrowseInto(System.Windows.Controls.TextBox box)
    {
        using var dlg = new Forms.FolderBrowserDialog { ShowNewFolderButton = false };
        if (dlg.ShowDialog() == Forms.DialogResult.OK) box.Text = dlg.SelectedPath;
    }

    private void ExtensionCheck_Changed(object sender, RoutedEventArgs e)
    {
        var enabled = ExtensionCheck.IsChecked == true;
        ExtensionNameBox.IsEnabled = enabled;
        ExtensionPathBox.IsEnabled = enabled;
        BrowseExtensionButton.IsEnabled = enabled;
    }

    private void Create_Click(object sender, RoutedEventArgs e)
    {
        var projectName = ProjectNameBox.Text.Trim();
        var systemName = SystemNameBox.Text.Trim();
        var role = RoleBox.Text.Trim();
        var mainPath = MainPathBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(projectName) || string.IsNullOrWhiteSpace(systemName) ||
            string.IsNullOrWhiteSpace(mainPath))
        {
            System.Windows.MessageBox.Show("Project name, system/base and main XML folder are required.", "OneC Architecture");
            return;
        }

        if (!Directory.Exists(mainPath) || !File.Exists(Path.Combine(mainPath, "Configuration.xml")))
        {
            System.Windows.MessageBox.Show("The selected main folder must directly contain Configuration.xml. Worker validation will run again before commit.", "OneC Architecture");
            return;
        }

        string? extId = null, extName = null, extPath = null;
        if (ExtensionCheck.IsChecked == true)
        {
            extName = ExtensionNameBox.Text.Trim();
            extPath = ExtensionPathBox.Text.Trim();
            if (string.IsNullOrWhiteSpace(extName) || string.IsNullOrWhiteSpace(extPath) ||
                !Directory.Exists(extPath) || !File.Exists(Path.Combine(extPath, "Configuration.xml")))
            {
                System.Windows.MessageBox.Show("Extension name and a folder containing Configuration.xml are required.", "OneC Architecture");
                return;
            }
            extId = SafeId(extName, "ext");
        }

        Result = new(
            SafeId(projectName, "project"), projectName,
            SafeId(systemName, "main"), systemName, role, mainPath,
            extId, extName, extPath);
        DialogResult = true;
    }

    internal static string SafeId(string text, string fallback)
    {
        var chars = text.Normalize().Where(c => c <= 127 && char.IsLetterOrDigit(c)).Take(32).ToArray();
        var readable = new string(chars).ToLowerInvariant();
        if (string.IsNullOrEmpty(readable)) readable = fallback;
        var hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(text))).ToLowerInvariant()[..8];
        return $"{readable}-{hash}";
    }
}