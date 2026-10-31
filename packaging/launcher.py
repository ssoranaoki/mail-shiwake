"""exe（PyInstaller）の入り口。メール仕分けの画面を開く。

窓だけで起動する exe には文字を出す先（標準出力・標準エラー）が無い。
モデルのダウンロードの進み具合などを書こうとして止まらないように、捨て先を用意しておく。
"""
import os
import sys

for name in ("stdout", "stderr"):
    if getattr(sys, name) is None:
        setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))

from mail_shiwake.app import main  # noqa: E402

main()
