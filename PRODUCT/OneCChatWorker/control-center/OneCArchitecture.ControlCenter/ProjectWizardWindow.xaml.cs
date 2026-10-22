using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Windows;
using Forms = System.Windows.Forms;

namespace OneCArchitecture.ControlCenter;

internal sealed record ProjectWizardResult(
    string ProjectId, string ProjectName, string ParticipantId, string SystemName, string Role,
    string MainPath, string? ExtensionId, string? ExtensionName, string? ExtensionPath,
    string[] ExtensionArchives);

public partial class ProjectWizardWindow : Window
{
    private string[] _extensionArchives = [];
    internal ProjectWizardResult? Result { get; private set; }

    public ProjectWizardWindow()
    {
        InitializeComponent();
        RoleBox.Text = "ERP";
        SystemNameBox.Text = Localization.Get("WizardDefaultSystem");
        Title = Localization.Get("AddProject");
        WizardTitleLabel.Text = Localization.Get("WizardTitle");
        WizardProjectLabel.Text = Localization.Get("WizardProjectName");
        WizardSystemLabel.Text = Localization.Get("WizardSystemName");
        WizardRoleLabel.Text = Localization.Get("WizardRole");
        WizardMainLabel.Text = Localization.CurrentCulture.TwoLetterISOLanguageName == "ru" ? "Основная конфигурация (.zip)" : "MAIN XML export (.zip)";
        WizardExtensionLabel.Text = Localization.Get("WizardExtensionName");
        WizardExtensionFolderLabel.Text = Localization.CurrentCulture.TwoLetterISOLanguageName == "ru" ? "Архивы расширений (.zip)" : "EXTENSION XML exports (.zip)";
        ExtensionCheck.Content = Localization.CurrentCulture.TwoLetterISOLanguageName == "ru" ? "Добавить расширения (до 15)" : "Add extensions (up to 15)";
        ExtensionNameBox.Text = "1C / ONEC — ZIP of XML; .cf / .cfe unsupported";
        ExtensionNameBox.IsReadOnly = true;
        MainPathBox.IsReadOnly = ExtensionPathBox.IsReadOnly = true;
        BrowseMainButton.Content = BrowseExtensionButton.Content = Localization.Get("WizardBrowse");
        CancelButton.Content = Localization.Get("WizardCancel");
        CreateButton.Content = Localization.Get("WizardCreate");
        ExtensionNameBox.ToolTip = ExtensionPathBox.ToolTip = BrowseExtensionButton.ToolTip = Localization.Get("WizardExtensionDisabled");
    }

    private void BrowseMain_Click(object sender, RoutedEventArgs e) => BrowseInto(MainPathBox);
    private void BrowseExtension_Click(object sender, RoutedEventArgs e)
    {
        using var dlg = new Forms.OpenFileDialog { Filter = "1C XML export ZIP (*.zip)|*.zip", Multiselect = true, CheckFileExists = true };
        if (dlg.ShowDialog() == Forms.DialogResult.OK)
        {
            if (dlg.FileNames.Length > 15) { System.Windows.MessageBox.Show("Maximum 15 extensions."); return; }
            _extensionArchives = dlg.FileNames;
            ExtensionPathBox.Text = string.Join("; ", dlg.FileNames);
        }
    }

    private static void BrowseInto(System.Windows.Controls.TextBox box)
    {
        using var dlg = new Forms.OpenFileDialog { Filter = "1C XML export ZIP (*.zip)|*.zip", CheckFileExists = true };
        if (dlg.ShowDialog() == Forms.DialogResult.OK) box.Text = dlg.FileName;
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
            System.Windows.MessageBox.Show(Localization.Get("WizardRequired"), "OneC Orbit");
            return;
        }

        // Only metadata is collected here. Worker validates and extracts archives.
        if (!mainPath.EndsWith(".zip", StringComparison.OrdinalIgnoreCase)) return;
        var archives = ExtensionCheck.IsChecked == true ? _extensionArchives : [];
        if (ExtensionCheck.IsChecked == true && archives.Length == 0) return;
        var review = $"{projectName} / {systemName} / ONEC\nMAIN: {mainPath}\n" +
            string.Join("\n", archives.Select((p, i) => $"EXTENSION {i + 1}: {p}")) +
            (Localization.CurrentCulture.TwoLetterISOLanguageName == "ru" ? "\n\nИмпорт проверит Worker. Требуется UAC. Продолжить?" : "\n\nWorker will validate imports. UAC is required. Continue?");
        if (System.Windows.MessageBox.Show(review, "OneC Orbit — Review", MessageBoxButton.OKCancel) != MessageBoxResult.OK) return;

        Result = new(
            SafeId(projectName, "project"), projectName,
            SafeId(systemName, "main"), systemName, role, mainPath,
            null, null, null, archives);
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