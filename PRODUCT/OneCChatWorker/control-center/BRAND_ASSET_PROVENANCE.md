# OneC Orbit approved brand asset (2026-10-20)

The operator explicitly approved the conversation-uploaded `OneCOrbit.AppIcon.ico` as the final product icon after ChatGPT supplied only ICO. This **supersedes** the earlier requirement to recover `OneCOrbit.BrandMark.256.png` with SHA-256 `88f23574...`. No claim of derivation or binary equivalence to that unavailable original PNG is made.

## Immutable approved source

- `Assets/OneCOrbit.AppIcon.ico`: **47,783 bytes**, SHA-256 `eb85cbcbf76f4467871e4dbf753ab128bce1363735759796b7b7f59774accca1`.
- Seven 32-bit PNG frames in the Windows ICO, at **16, 24, 32, 48, 64, 128, 256** pixels.
- `Assets/OneCOrbit.BrandMark.256.png`: **21,030 bytes**, SHA-256 `d052b7937b81f2967af91a4ae595772fc20a5ebb5ea3d689343e7d687103f1a2`. Extracted exactly, without scaling, cropping, rendering or modification, from the 7th ICO directory entry (0x00 width and height denote 256). The PowerShell 5.1 packaging regression asserts full byte-for-byte equality to that embedded frame, not just the two independent hashes.

## Presentation and verifiable Windows behavior

- The built self-contained WPF EXE uses the approved **ICO as `ApplicationIcon`**. The taskbar and Alt+Tab use the actual native PE icon group; `System.Drawing.Icon.ExtractAssociatedIcon(Environment.ProcessPath)` supplies that same compiled icon for the notification tray, avoiding GDI+ direct-stream decoding of PNG-encoded ICO frames.
- `MainWindow`, the project wizard and the compact 28-pixel sidebar brand use the approved 256px frame as a WPF assembly-scoped resource. Assembly-qualified `pack://application:,,,/OneCArchitecture.ControlCenter;component/...` URIs also work in the standalone real WPF fixture executable.
- The installed OneC Orbit shortcut explicitly points `IconLocation` to the installed EXE's first native icon; the installer verifies this without creating an extra icon file in a new global location.
- RU/EN, light/dark, DPI 100/125/150%, keyboard/focus and native packaged executable checks remain required. Screenshots and FA exact-head evidence are acceptance gates; documentation alone is not an icon PASS.

No production install/update/migration or live worker/S4/Source change is authorized by this brand commit.
