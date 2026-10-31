"""Outlook のフォルダのメールを読み、振り分けの提案を表示する（読むだけ。メールは移さない）。

使い方（Windows、Outlook を開いた状態で）:
  uv run python -m mail_shiwake.try_outlook --list                  # 受信トレイの下のフォルダの一覧
  uv run python -m mail_shiwake.try_outlook --folder "フォルダ名"    # そのフォルダのメールに提案を出す
  uv run python -m mail_shiwake.try_outlook --store "データファイル名" --folder "フォルダ名"

お手本は、今は練習用の samples/sample_mails.json を使う（自分のお手本を選ぶのは画面の単位で作る）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .embedder import Embedder
from .outlook import OutlookReader
from .sorter import Sorter

SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "sample_mails.json"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--folder", default="", help='受信トレイから下のフォルダ（"/" で区切る。空なら受信トレイ）')
    ap.add_argument("--store", default=None, help="受信トレイの代わりに読む、データファイル（.pst など）の名前")
    ap.add_argument("--list", action="store_true", help="フォルダの一覧を出す")
    ap.add_argument("--limit", type=int, default=20, help="読むメールの数（新しい順）")
    args = ap.parse_args()

    outlook = OutlookReader()
    if args.list:
        for name in outlook.list_folders(args.folder, args.store):
            print(name)
        return

    mails = outlook.read(args.folder, limit=args.limit, store=args.store)
    print(f"Outlook から {len(mails)} 通を読みました（読むだけで、何も書きこんでいません）")

    data = json.loads(SAMPLES.read_text(encoding="utf-8"))
    sorter = Sorter(Embedder())
    sorter.learn({f: [(m["subject"], m["body"]) for m in ms] for f, ms in data["examples"].items()})
    for mail in mails:
        top, second = sorter.suggest(mail.subject, mail.body)[:2]
        print(f"・{mail.subject}")
        print(f"    → {top.folder}（近さ {top.score:.2f}、2位 {second.folder} {second.score:.2f}）")


if __name__ == "__main__":
    main()
