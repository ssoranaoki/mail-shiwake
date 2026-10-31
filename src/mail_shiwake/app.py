"""メール仕分けの画面（pywebview の窓）。3番：提案を見るだけで、まだメールは移さない。

使い方（Windows、Outlook を開いた状態で）:
  uv run python -m mail_shiwake.app --store "メール仕分けの試し" --folder "届いたメール"

窓の中身は ui/ の HTML・CSS・JavaScript。JavaScript から下の Api のメソッドを呼ぶ（pywebview の js_api）。
"""

from __future__ import annotations

import argparse
import json
import threading
from pathlib import Path

import webview

from .embedder import Embedder
from .outlook import OutlookReader
from .sorter import Sorter

UI = Path(__file__).resolve().parent / "ui"
SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "sample_mails.json"
UNSURE_GAP = 0.03  # 1位と2位の近さの差がこれより小さいと「迷っています」（練習用の8通で決めた値）
SNIPPET_CHARS = 60  # カードに出す本文の頭の文字数


class Api:
    """窓の JavaScript から呼ばれるメソッド（名前が _ で始まるものは呼ばれない）。

    pywebview はメソッドを別のスレッドで動かすので、Outlook（COM）にはそのスレッドの中でつなぐ。
    """

    def __init__(self, store: str | None, folder: str) -> None:
        self._store, self._folder = store, folder
        self._lock = threading.Lock()
        self._sorter: Sorter | None = None
        self._examples: dict[str, list[tuple[str, str]]] = {}

    def learn(self) -> dict:
        """お手本を覚える（今は練習用の samples/sample_mails.json）。フォルダとお手本の数を返す。"""
        with self._lock:
            data = json.loads(SAMPLES.read_text(encoding="utf-8"))
            self._examples = {f: [(m["subject"], m["body"]) for m in ms] for f, ms in data["examples"].items()}
            if self._sorter is None:
                self._sorter = Sorter(Embedder())
            self._sorter.learn(self._examples)
            return {"folders": [{"name": f, "count": len(ms)} for f, ms in self._examples.items()]}

    def mails(self) -> dict:
        """Outlook のフォルダのメールを読み、1通ずつ提案を付けて返す（読むだけ）。"""
        import pythoncom  # pywin32。別のスレッドで COM を使う前に初期化する

        pythoncom.CoInitialize()
        try:
            reader = OutlookReader()
            mails = reader.read(self._folder, limit=50, store=self._store)
        finally:
            pythoncom.CoUninitialize()
        with self._lock:
            if self._sorter is None:
                raise RuntimeError("先にお手本を覚えてください")
            out = []
            for m in mails:
                top, second = self._sorter.suggest(m.subject, m.body)[:2]
                out.append({
                    "id": m.entry_id,
                    "subject": m.subject,
                    "snippet": " ".join(m.body.split())[:SNIPPET_CHARS],
                    "folder": top.folder,
                    "unsure": (top.score - second.score) < UNSURE_GAP,
                    "second": second.folder,
                })
        return {"mails": out, "source": self._store or "受信トレイ", "folderName": self._folder or "受信トレイ"}


def page() -> str:
    """ui/ の HTML に CSS と JavaScript を埋めこんだ1枚のページを作る。"""
    html = (UI / "index.html").read_text(encoding="utf-8")
    css = (UI / "style.css").read_text(encoding="utf-8")
    js = (UI / "app.js").read_text(encoding="utf-8")
    return html.replace("/*STYLE*/", css).replace("/*SCRIPT*/", js)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", default=None, help="受信トレイの代わりに読む、データファイル（.pst など）の名前")
    ap.add_argument("--folder", default="", help='読むフォルダ（"/" で区切る。空なら一番上か受信トレイ）')
    args = ap.parse_args()
    webview.create_window("メール仕分け", html=page(), js_api=Api(args.store, args.folder),
                          width=1180, height=760, min_size=(760, 520))
    webview.start()


if __name__ == "__main__":
    main()
