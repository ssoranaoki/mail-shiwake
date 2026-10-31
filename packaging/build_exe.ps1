# このファイルは BOM 付きの UTF-8 で保存する（Windows PowerShell 5.1 が日本語のコメントを読み違えないように）
# Windows 用の exe（フォルダごと配る形）を作る。プロジェクトのフォルダで:  powershell -File packaging\build_exe.ps1
# 作るもの: dist\mail-shiwake\mail-shiwake.exe と、配る zip dist\mail-shiwake-<版>-windows.zip
$ErrorActionPreference = "Stop"
$version = (Select-String -Path pyproject.toml -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
uv sync
# win32timezone は、pywin32 が Outlook の日時を直すときに動いている途中で読みこむ部品で、自動では見つからないので指定する
uv run --with "pyinstaller>=6.22" pyinstaller --noconfirm --clean --windowed --onedir `
  --name mail-shiwake `
  --paths src `
  --hidden-import win32timezone `
  --add-data "src/mail_shiwake/ui:mail_shiwake/ui" `
  packaging/launcher.py
Copy-Item LICENSE, README.md dist\mail-shiwake\
$zip = "dist\mail-shiwake-$version-windows.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path dist\mail-shiwake -DestinationPath $zip
Write-Output "できました: $zip"
