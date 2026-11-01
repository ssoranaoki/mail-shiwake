# このファイルは BOM 付きの UTF-8 で保存する（Windows PowerShell 5.1 が日本語のコメントを読み違えないように）
# Windows 用の exe（フォルダごと配る形）を作る。プロジェクトのフォルダで:  powershell -File packaging\build_exe.ps1
# 作るもの: dist\mail-shiwake\mail-shiwake.exe と、配る zip dist\mail-shiwake-<版>-windows.zip
$ErrorActionPreference = "Stop"
$version = (Select-String -Path pyproject.toml -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
# 開発用に起動したメール仕分け（uv run）が動いていると、入れ直しに失敗して古い中身の exe ができる（2026-11-01 に起きた）
if (Get-Process -Name mail-shiwake -ErrorAction SilentlyContinue) {
  throw "メール仕分けが動いています。窓を閉じてから、もう一度実行してください"
}
uv sync
if ($LASTEXITCODE -ne 0) { throw "uv sync に失敗しました（終了コード $LASTEXITCODE）" }
# exe の版の情報（製品名・版）を pyproject.toml から作る
uv run python packaging/make_version_info.py packaging/version_info.generated.txt
if ($LASTEXITCODE -ne 0) { throw "版の情報を作れませんでした" }
# win32timezone は、pywin32 が Outlook の日時を直すときに動いている途中で読みこむ部品で、自動では見つからないので指定する
uv run --with "pyinstaller>=6.22" pyinstaller --noconfirm --clean --windowed --onedir `
  --name mail-shiwake `
  --version-file packaging/version_info.generated.txt `
  --paths src `
  --hidden-import win32timezone `
  --add-data "src/mail_shiwake/ui:mail_shiwake/ui" `
  packaging/launcher.py
Copy-Item LICENSE, README.md dist\mail-shiwake\
# ブラウザで落とした zip をエクスプローラーで展開すると、中のファイルに「インターネットから来た」印（Mark of the Web）が付き、
# .NET Framework が窓の部品の Python.Runtime.dll を読まなくなる。exe の隣の設定で、同梱の DLL を読んでよいと伝える
# （Microsoft の <loadFromRemoteSources> 要素）
Set-Content -Path dist\mail-shiwake\mail-shiwake.exe.config -Encoding UTF8 -Value @'
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <runtime>
    <loadFromRemoteSources enabled="true"/>
  </runtime>
</configuration>
'@
# exe に入れた部品のライセンス文を集める（MIT・BSD・Apache-2.0 などは、一緒に配るときに添える決まりがある）
uv run python packaging/collect_licenses.py dist/mail-shiwake/THIRD-PARTY-LICENSES
if ($LASTEXITCODE -ne 0) { throw "部品のライセンス文を集められませんでした" }
$zip = "dist\mail-shiwake-$version-windows.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path dist\mail-shiwake -DestinationPath $zip
Write-Output "できました: $zip"
