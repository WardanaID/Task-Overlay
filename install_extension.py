import os
import json
import shutil
import subprocess
import time
import zipfile

EXT_FOLDER_NAME = "antigravity-tools.antigravity-task-overlay-1.0.0"
EXT_ID = "antigravity-tools.antigravity-task-overlay"
EXT_UUID = "a7f3c910-8142-4c9a-9c5e-1029384756ab"
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
VSIX_PATH = os.path.join(SRC_DIR, "antigravity-task-overlay-1.0.0.vsix")

FILES_TO_COPY = [
    "package.json",
    "extension.js",
    "README.md",
]

CONTENT_TYPES_XML = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".json" ContentType="application/json"/>
  <Default Extension=".js" ContentType="application/javascript"/>
  <Default Extension=".md" ContentType="text/markdown"/>
  <Default Extension=".svg" ContentType="image/svg+xml"/>
  <Default Extension=".vsixmanifest" ContentType="text/xml"/>
</Types>
"""

VSIX_MANIFEST_XML = """<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="antigravity-task-overlay" Version="1.0.0" Publisher="antigravity-tools" />
    <DisplayName>Antigravity Task Overlay</DisplayName>
    <Description xml:space="preserve">Floating real-time task monitor and control panel untuk Antigravity IDE dan VS Code.</Description>
    <Tags>antigravity,overlay,task,monitor</Tags>
    <Categories>Other</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="^1.75.0" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="ui,workspace" />
      <Property Id="Microsoft.VisualStudio.Services.GitHubFlavoredMarkdown" Value="true" />
    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true" />
  </Assets>
</PackageManifest>
"""


def build_vsix():
    with zipfile.ZipFile(VSIX_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES_XML.strip())
        zf.writestr("extension.vsixmanifest", VSIX_MANIFEST_XML.strip())
        for fname in FILES_TO_COPY:
            fpath = os.path.join(SRC_DIR, fname)
            if os.path.exists(fpath):
                zf.write(fpath, f"extension/{fname}")
        svg_path = os.path.join(SRC_DIR, "media", "activity-icon.svg")
        if os.path.exists(svg_path):
            zf.write(svg_path, "extension/media/activity-icon.svg")
    print(f"[OK] Paket VSIX berhasil dibuat: {VSIX_PATH}")


def install_to_ide_root(ide_ext_root: str, ide_name: str):
    if not os.path.exists(ide_ext_root):
        os.makedirs(ide_ext_root, exist_ok=True)

    target_dir = os.path.join(ide_ext_root, EXT_FOLDER_NAME)
    os.makedirs(target_dir, exist_ok=True)
    os.makedirs(os.path.join(target_dir, "media"), exist_ok=True)

    for fname in FILES_TO_COPY:
        src = os.path.join(SRC_DIR, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(target_dir, fname))

    src_icon = os.path.join(SRC_DIR, "media", "activity-icon.svg")
    if os.path.exists(src_icon):
        shutil.copy2(src_icon, os.path.join(target_dir, "media", "activity-icon.svg"))

    # Pastikan tidak tercatat di .obsolete
    obsolete_path = os.path.join(ide_ext_root, ".obsolete")
    if os.path.exists(obsolete_path):
        try:
            with open(obsolete_path, "r", encoding="utf-8") as f:
                obs = json.load(f)
            if isinstance(obs, dict) and EXT_FOLDER_NAME in obs:
                del obs[EXT_FOLDER_NAME]
                with open(obsolete_path, "w", encoding="utf-8") as f:
                    json.dump(obs, f)
        except Exception:
            pass

    # Update extensions.json registry
    ext_json_path = os.path.join(ide_ext_root, "extensions.json")
    entries = []
    if os.path.exists(ext_json_path):
        try:
            with open(ext_json_path, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except Exception:
            entries = []

    if isinstance(entries, list):
        entries = [
            e for e in entries
            if not (isinstance(e, dict) and e.get("identifier", {}).get("id", "").lower() == EXT_ID)
        ]
        norm_path = target_dir.replace("\\", "/")
        if len(norm_path) >= 2 and norm_path[1] == ":":
            norm_path = "/" + norm_path[0].lower() + norm_path[1:]

        new_entry = {
            "identifier": {
                "id": EXT_ID,
                "uuid": EXT_UUID
            },
            "version": "1.0.0",
            "location": {
                "$mid": 1,
                "fsPath": target_dir,
                "_sep": 1,
                "path": norm_path,
                "scheme": "file"
            },
            "relativeLocation": EXT_FOLDER_NAME,
            "metadata": {
                "isApplicationScoped": False,
                "isMachineScoped": False,
                "isBuiltin": False,
                "installedTimestamp": int(time.time() * 1000),
                "pinned": False,
                "source": "vsix",
                "targetPlatform": "universal",
                "updated": False,
                "private": False,
                "isPreReleaseVersion": False,
                "hasPreReleaseVersion": False
            }
        }
        entries.append(new_entry)
        with open(ext_json_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, separators=(",", ":"))

    print(f"[OK] Terpasang di {ide_name}: {target_dir}")


def main():
    build_vsix()
    user_home = os.path.expanduser("~")

    # 1. Pasang via CLI resmi Antigravity IDE jika tersedia
    agy_ide_cli = os.path.join(
        user_home, "AppData", "Local", "Programs", "Antigravity IDE", "bin", "antigravity-ide.cmd"
    )
    if os.path.exists(agy_ide_cli):
        try:
            res = subprocess.run(
                [agy_ide_cli, "--install-extension", VSIX_PATH, "--force"],
                capture_output=True,
                text=True,
                timeout=20
            )
            if res.stdout:
                print(res.stdout.strip())
            if res.stderr:
                print(res.stderr.strip())
        except Exception as e:
            print(f"[INFO] CLI install fallback: {e}")

    # 2. Pastikan file terbaru tersalin ke seluruh folder ekstensi IDE (.antigravity-ide, .antigravity, .vscode)
    targets = [
        (os.path.join(user_home, ".antigravity-ide", "extensions"), "Antigravity IDE (.antigravity-ide)"),
        (os.path.join(user_home, ".antigravity", "extensions"), "Antigravity Legacy (.antigravity)"),
        (os.path.join(user_home, ".vscode", "extensions"), "Visual Studio Code (.vscode)"),
    ]
    for root_path, label in targets:
        install_to_ide_root(root_path, label)


if __name__ == "__main__":
    main()
