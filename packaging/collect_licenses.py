"""exe に入れる部品のライセンス文を集める（exe を作るときに build_exe.ps1 から呼ぶ）。

プロジェクトの環境に入っている部品（Python の配布物）ごとに、LICENSE・COPYING・NOTICE などのファイルを
dist/mail-shiwake/THIRD-PARTY-LICENSES/<部品の名前>/ に写し、一覧 README.txt を作る。Python 本体のライセンスも入れる。
ライセンス文のファイルが見つからない部品は、一覧に「見つからない」と書き、最後に名前を表示する（人が確かめる）。
"""
import shutil
import sys
from importlib import metadata
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/mail-shiwake/THIRD-PARTY-LICENSES")
# 配布物にライセンス文が入っていない部品は、元のリポジトリから取ったものをここに置いておく（SOURCE.txt に取った場所）
EXTRA = Path(__file__).resolve().parent / "licenses-extra"
WORDS = ("LICEN", "COPYING", "NOTICE", "THIRDPARTY", "THIRD_PARTY", "THIRD-PARTY", "AUTHORS")
SKIP = {"mail-shiwake"}  # メール仕分け自身は LICENSE を別に入れる

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
lines, missing = [], []
for dist in sorted(metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
    name = dist.metadata["Name"]
    if name.lower() in SKIP:
        continue
    lic = dist.metadata.get("License-Expression") or next(
        (c.split("::")[-1].strip() for c in dist.metadata.get_all("Classifier") or [] if c.startswith("License ::")),
        (dist.metadata.get("License") or "").splitlines()[0][:60] if dist.metadata.get("License") else "")
    found = []
    for f in dist.files or []:
        base = Path(str(f)).name.upper().replace(" ", "")
        if any(w in base for w in WORDS) and not base.endswith((".PY", ".PYC", ".PYD", ".DLL", ".SO")):
            src = Path(dist.locate_file(f))
            if src.is_file():
                dest = OUT / name / str(f).replace("/", "__")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
                found.append(dest.name)
    extra = EXTRA / name
    if not found and extra.is_dir():
        shutil.copytree(extra, OUT / name, dirs_exist_ok=True)
        found = [f"{p.name}（元のリポジトリから取得）" for p in sorted(extra.iterdir())]
    lines.append(f"{name} {dist.version}  ライセンス: {lic or '（表記なし）'}  ファイル: {', '.join(found) if found else '見つからない'}")
    if not found:
        missing.append(name)

py_license = Path(sys.base_prefix) / "LICENSE.txt"
if py_license.is_file():
    (OUT / "Python").mkdir()
    shutil.copyfile(py_license, OUT / "Python" / "LICENSE.txt")
    lines.insert(0, f"Python {sys.version.split()[0]}  ライセンス: PSF  ファイル: LICENSE.txt")
else:
    missing.append("Python 本体")

(OUT / "README.txt").write_text(
    "メール仕分けの exe に入っている部品と、そのライセンス文の一覧です。\n"
    "それぞれのライセンス文は、部品の名前のフォルダにあります。\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
print(f"部品 {len(lines)} 個のライセンス文を {OUT} に集めました")
print("ライセンス文のファイルが見つからない部品:", ", ".join(missing) if missing else "なし")
