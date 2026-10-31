"""メール仕分けの画面（pywebview の窓）。提案を見て、人が「移す」を押したメールだけを移す。

使い方（Windows、Outlook を開いた状態で）:
  uv run python -m mail_shiwake.app --store "メール仕分けの試し" --folder "届いたメール"

振り分け先のフォルダ（お手本が入っているフォルダ）は --targets で、カンマ区切りで指定する。

窓の中身は ui/ の HTML・CSS・JavaScript。JavaScript から下の Api のメソッドを呼ぶ（pywebview の js_api）。
"""

from __future__ import annotations

import argparse
import threading
from pathlib import Path

import webview

from .embedder import Embedder
from .mover import OutlookMover
from .sorter import Sorter

UI = Path(__file__).resolve().parent / "ui"
EXAMPLES_PER_FOLDER = 50  # フォルダごとに覚えるお手本の数（新しい順）
UNSURE_GAP = 0.03  # 1位と2位の近さの差がこれより小さいと「迷っています」（練習用の8通で決めた値）
SNIPPET_CHARS = 60  # カードに出す本文の頭の文字数


class Api:
    """窓の JavaScript から呼ばれるメソッド（名前が _ で始まるものは呼ばれない）。

    お手本は、Outlook の振り分け先のフォルダに入っているメールそのもの（4番から）。
    pywebview はメソッドを別のスレッドで動かすので、Outlook（COM）にはそのスレッドの中でつなぐ。
    """

    def __init__(self, store: str | None, folder: str, targets: list[str]) -> None:
        self._store, self._folder, self._targets = store, folder, targets
        self._lock = threading.Lock()
        self._sorter: Sorter | None = None
        self._examples: dict[str, list[tuple[str, str]]] = {}
        self._last: dict[str, tuple[str, str]] = {}  # 最後に読んだ届いたメール（EntryID → 件名・本文）

    def _outlook(self, work):
        """このスレッドで COM を準備して Outlook につなぎ、work(つないだ窓口) の結果を返す。"""
        import pythoncom  # pywin32。別のスレッドで COM を使う前に初期化する

        pythoncom.CoInitialize()
        try:
            mover = OutlookMover()
            result = work(mover)
            del mover  # Outlook の部品は、COM を片づける前に手放す
            return result
        finally:
            pythoncom.CoUninitialize()

    def _folders(self) -> list[dict]:
        return [{"name": f, "count": len(self._examples.get(f, []))} for f in self._targets]

    def learn(self) -> dict:
        """振り分け先のフォルダのメールを、お手本として覚える。フォルダとお手本の数を返す。"""
        def read_targets(o: OutlookMover):
            return {f: [(m.subject, m.body) for m in o.read(f, limit=EXAMPLES_PER_FOLDER, store=self._store)]
                    for f in self._targets}

        examples = self._outlook(read_targets)
        with self._lock:
            self._examples = examples
            if self._sorter is None:
                self._sorter = Sorter(Embedder())
            self._sorter.learn(self._examples)
            return {"folders": self._folders()}

    def mails(self) -> dict:
        """届いたメールのフォルダを読み、1通ずつ提案を付けて返す（読むだけ）。"""
        if self._sorter is None:
            raise RuntimeError("先にお手本を覚えてください")
        mails = self._outlook(lambda o: o.read(self._folder, limit=50, store=self._store))
        with self._lock:
            self._last = {m.entry_id: (m.subject, m.body) for m in mails}
            out = []
            for m in mails:
                ranked = self._sorter.suggest(m.subject, m.body)
                top = ranked[0]
                second = ranked[1] if len(ranked) > 1 else None  # フォルダが1つだけなら迷いようがない
                out.append({
                    "id": m.entry_id,
                    "subject": m.subject,
                    "snippet": snippet(m.body),
                    "folder": top.folder,
                    "unsure": second is not None and (top.score - second.score) < UNSURE_GAP,
                    "second": second.folder if second else None,
                })
        return {"mails": out, "source": self._store or "受信トレイ", "folderName": self._folder or "受信トレイ",
                "targets": self._targets}

    def move(self, entry_id: str, folder: str) -> dict:
        """人が「移す」を押したメールを、選んだフォルダへ移す。移したメールは、すぐにお手本に加える。"""
        if folder not in self._targets:
            raise ValueError(f"「{folder}」は振り分け先ではありません")
        if entry_id not in self._last:
            raise LookupError("そのメールは、いまの一覧にありません")
        self._outlook(lambda o: o.move(entry_id, folder, store=self._store))
        subject, body = self._last.pop(entry_id)
        with self._lock:
            self._examples.setdefault(folder, []).append((subject, body))
            self._sorter.learn(self._examples)  # 選び直したメールも、ここで新しいお手本になる
        moved = {"subject": subject, "folder": folder}
        try:
            result = self.mails()  # 残りのメールの提案を出し直す
        except Exception as e:  # 移すのはできたので、一覧の読み直しの失敗とは分けて知らせる
            return {"moved": moved, "folders": self._folders(), "listError": str(e)}
        result.update({"moved": moved, "folders": self._folders()})
        return result


def snippet(body: str) -> str:
    """カードに出す本文の頭（改行や空白はまとめて1つにする）。"""
    return " ".join(body.split())[:SNIPPET_CHARS]


def page() -> str:
    """ui/ の HTML に CSS と JavaScript を埋めこんだ1枚のページを作る。"""
    html = (UI / "index.html").read_text(encoding="utf-8")
    css = (UI / "style.css").read_text(encoding="utf-8")
    js = (UI / "app.js").read_text(encoding="utf-8")
    return html.replace("/*STYLE*/", css).replace("/*SCRIPT*/", js)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", default=None, help="受信トレイの代わりに読む、データファイル（.pst など）の名前")
    ap.add_argument("--folder", default="", help='届いたメールのフォルダ（"/" で区切る。空なら一番上か受信トレイ）')
    ap.add_argument("--targets", default="請求書,注文,問い合わせ,お知らせ",
                    help="振り分け先のフォルダ（カンマ区切り）。中のメールがお手本になる")
    args = ap.parse_args()
    webview.create_window("メール仕分け", html=page(), js_api=Api(args.store, args.folder, [t.strip() for t in args.targets.split(",") if t.strip()]),
                          width=1180, height=760, min_size=(760, 520))
    webview.start()


if __name__ == "__main__":
    main()
