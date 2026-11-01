"""exe に入れる版の情報（Windows の「プロパティ」→「詳細」に出るもの）を、pyproject.toml の版から作る。

PyInstaller の --version-file に渡すテキスト（VSVersionInfo の形）を書く。
コード署名（SignPath Foundation）の条件に合わせ、製品名はプロジェクト名、製品の版はビルドごとに同じ値にする。
  uv run python packaging/make_version_info.py packaging/version_info.generated.txt
"""
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
nums = [int(x) for x in version.split(".")[:3]] + [0]
tup = tuple((nums + [0, 0, 0, 0])[:4])
strings = {
    "CompanyName": "ssoranaoki",
    "FileDescription": "mail-shiwake - sorts classic Outlook mail by example, on your PC",
    "FileVersion": version,
    "InternalName": "mail-shiwake",
    "LegalCopyright": "Copyright 2026 ssoranaoki. Licensed under the Apache License 2.0",
    "OriginalFilename": "mail-shiwake.exe",
    "ProductName": "mail-shiwake",
    "ProductVersion": version,
}
text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tup}, prodvers={tup}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
{chr(10).join(f"      StringStruct({k!r}, {v!r})," for k, v in strings.items())}
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
out = Path(sys.argv[1] if len(sys.argv) > 1 else "packaging/version_info.generated.txt")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(text, encoding="utf-8")
print(f"{out}: {version}")
