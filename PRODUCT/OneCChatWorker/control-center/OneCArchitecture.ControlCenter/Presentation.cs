using System.Globalization;

namespace OneCArchitecture.ControlCenter;

// Bounded copy over owner facts; never establishes lifecycle eligibility.
internal static class Presentation
{
    public static string Status(string? state) => Localization.Get(state switch
    {
        "PROJECT_SELECTION_REQUIRED" => "ChooseProject",
        "PROJECT_READY" or "ACCEPTED" or "READY" => "ProjectReady",
        "PROJECT_NEEDS_APPLY" or "CATALOG_DRIFT" or "APPLY_REQUIRED" or "SNAPSHOT_ROOT_MISSING" => "SourceNeedsAttention",
        "PROJECT_NEEDS_VERIFY" or "RECOVERY_REQUIRED" or "INCOMPLETE_APPLY_RESIDUE" => "RecoveryRequired",
        "PROJECT_DRAFT" => "ProjectDraft",
        "NO_PROJECTS" => "NoProjects",
        "NOT_INSTALLED" => "NotInstalled",
        "REMOTE_AUTH_MISSING" => "EnrollmentMissing",
        "RUNNING" or "TASK_ACTIVE" or "CONNECTED" => "Connected",
        "STARTING" or "RUNNING_NO_CONNECT_EVIDENCE" => "ConnectionUnconfirmed",
        "ACTIVE_ADMISSION_OFFLINE" => "SessionOffline",
        "START_INCOMPLETE" => "StartIncomplete",
        "CONTINUE_AVAILABLE" => "ContinuationAvailable",
        "OFFLINE" => "Offline",
        "ACTIVE" => "SessionRecorded",
        "STOPPED" or "EXPIRED" or "TASK_EXPIRED" or "TASK_EXHAUSTED" => "SessionEnded",
        "PASS" or "COMMITTED" or "OK" => "Verified",
        "FAIL" or "FAILED" or "ABORTED" => "DidNotComplete",
        "NONE" or "NOT_STARTED" => "NoOperation",
        "PREPARED" or "READY_FOR_ACCEPT" => "UpdatePrepared",
        "RUNNING_OPERATION" or "IN_PROGRESS" or "APPLYING" => "ActionInProgress",
        null or "" => "UnknownState",
        _ => "UnknownState"
    });

    public static string Reason(string? reason) => Localization.Get(reason switch
    {
        "PROJECT_READY" or "AVAILABLE" => "StartAccessHelp",
        "PROJECT_SELECTION_REQUIRED" => "ProjectSelectionHelp",
        "SESSION_ALREADY_EXISTS" or "RUNNING" or "TASK_ACTIVE" => "SessionAlreadyExists",
        "ACTIVE_ADMISSION_OFFLINE" => "OfflineRecoveryBlocked",
        "STARTING" => "ConnectionWaitHelp",
        "CONTINUE_AVAILABLE" => "ContinueHelp",
        "NO_VERIFIED_CONTINUATION" => "ContinuationUnavailable",
        "NO_ACTIVE_SESSION" => "NoActiveTask",
        "SOURCE_UPDATE_ACTIVE" => "SourceUpdateActiveHelp",
        "NO_SOURCE_UPDATE" => "SourceUpdateNone",
        "VERIFICATION_NOT_REQUIRED" => "VerificationNotRequired",
        "NO_ARTIFACTS" => "NoArtifacts",
        "PROJECT_NEEDS_APPLY" => "SourceAttentionHelp",
        "PROJECT_NEEDS_VERIFY" or "RECOVERY_REQUIRED" => "RecoveryHelp",
        "NO_PROJECTS" => "NoProjectsHelp",
        "PROJECT_DRAFT" => "ProjectDraftHelp",
        "NOT_INSTALLED" => "NotInstalledHelp",
        "REMOTE_AUTH_MISSING" => "EnrollmentMissingHelp",
        "START_INCOMPLETE" => "StartIncompleteHelp",
        _ => "OwnerEvidenceRequired"
    });

    public static string Expiry(string? value)
    {
        if (!DateTimeOffset.TryParse(value, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out var expiry))
            return Localization.Get("ExpiryUnavailable");
        return Localization.Get(expiry <= DateTimeOffset.UtcNow ? "ExpiryElapsed" : "ExpiresAt") + " " +
            expiry.ToLocalTime().ToString("g", Localization.CurrentCulture);
    }

    public static string Outcome(string? value)
    {
        if (value?.Contains("INVALID_READ_ARGS", StringComparison.Ordinal) == true) return Localization.Get("ReadArgumentBound");
        if (value?.Contains("HELPER_OFFLINE", StringComparison.Ordinal) == true) return Localization.Get("Offline");
        if (value?.Contains("HELPER_STATE_PERSIST_FAILED", StringComparison.Ordinal) == true) return Localization.Get("PersistenceFailure");
        if (value?.Contains("HELPER_TIMEOUT", StringComparison.Ordinal) == true) return Localization.Get("ResultUnconfirmed");
        return Status(value);
    }

    public static string Operation(string? value) => Localization.Get(value?.ToUpperInvariant() switch
    {
        "READ" or "SOURCE_READ" => "OperationRead",
        "SEARCH" or "SOURCE_SEARCH" => "OperationSearch",
        "CONTEXT" or "SOURCE_CONTEXT" => "OperationContext",
        "PROPOSAL_WRITE" or "PROPOSAL_READ" => "OperationProposal",
        "TASK_CHECKPOINT_WRITE" => "OperationCheckpoint",
        "APPLY" => "ApplyRefresh", "VERIFY" => "Verify", "REPAIR" => "Repair", "UPDATE" => "Update",
        "START" => "StartWork", "STOP" => "StopWork", "CONTINUE" => "ContinueWork",
        _ => "UnknownOperation"
    });
}
