# Balkan Frontier 1999 — HOI4 1.20.x

## CMD launcher (fixed)
The current `Balkan_Frontier_1999_CMD_Launcher.bat` no longer performs recursive PowerShell searches or opens a Windows file-picker dialog. It checks only the launcher's folder, immediate child folders and a full ZIP package located beside the BAT. If necessary, it asks for the ZIP path as text and extracts it using Windows `tar.exe`.

Place the full ZIP beside the BAT, or extract the full ZIP and keep the folder `Balkan_Frontier_1999` beside the BAT. Run the BAT normally; administrator privileges are not required.

The launcher copies the mod into the user's HOI4 mod directory, generates the local .mod descriptor and passes it to `hoi4.exe` for direct launch. If automatic game detection fails, it asks for the full path to `hoi4.exe`.

## Compatibility
The mod targets HOI4 1.20.x. The root descriptor had previously carried settings copied from another mod (The Fire Rises, 1.19.*) and excessive `replace_path` directives, including a replacement for country tags. That descriptor was replaced with a minimal Balkan Frontier descriptor. File-level checks are not a substitute for testing a full campaign in the user's actual game installation.
