"""メール仕分けの画面（pywebview の窓）。提案を見て、人が「移す」を押したメールだけを移す。

使い方（Windows、Outlook を開いた状態で）:
  mail-shiwake                     # 設定ファイル ~/.mail-shiwake/settings.json のとおりに開く（無ければ作る）
  uv run python -m mail_shiwake.app --store "メール仕分けの試し" --folder "届いたメール"   # 試し用（開発）

コマンドで指定したもの（--store・--folder・--targets）は、設定ファイルより優先する。

窓の中身は ui/ の HTML・CSS・JavaScript。JavaScript から下の Api のメソッドを呼ぶ（pywebview の js_api）。
"""

from __future__ import annotations

import argparse
import json
import re
import threading
from pathlib import Path

import webview

import numpy as np

from .embedder import Embedder
from .importance import MIN_FLAGGED, Importance
from .mover import OutlookMover
from .sorter import Sorter, mail_text

UI = Path(__file__).resolve().parent / "ui"
SETTINGS = Path.home() / ".mail-shiwake" / "settings.json"  # 起動の設定（ダブルクリックで起動するときに使う）
DEFAULT_SETTINGS = {
    "store": None,  # 読むデータファイルの名前。null なら受信トレイ
    "folder": "",  # 届いたメールのフォルダ（"" なら受信トレイそのもの）
    "targets": ["請求書", "注文", "問い合わせ", "お知らせ"],  # 振り分け先（中のメールがお手本になる）
}
EXAMPLES_PER_FOLDER = 50  # フォルダごとに覚えるお手本の数（新しい順）
FLAG_SCAN = 300  # 旗付きのお手本を探すとき、フォルダごとに見る新しいメールの数
FLAGGED_EXAMPLES = 50  # 「大事」のお手本にする旗付きメールの数（新しい順）
UNSURE_GAP = 0.03  # 1位と2位の近さの差がこれより小さいと「迷っています」（練習用の8通で決めた値）
SNIPPET_CHARS = 60  # カードに出す本文の頭の文字数


class Api:
    """窓の JavaScript から呼ばれるメソッド（名前が _ で始まるものは呼ばれない）。

    お手本は、Outlook の振り分け先のフォルダに入っているメールそのもの（4番から）。
    pywebview はメソッドを別のスレッドで動かすので、Outlook（COM）にはそのスレッドの中でつなぐ。
    """

    def __init__(self, store: str | None, folder: str, targets: list[str], reload=None) -> None:
        self._store, self._folder, self._targets = store, folder, targets
        self._reload = reload  # 設定を読み直す関数。「お手本を覚える」のたびに呼ぶ（設定ファイルを書き換えたときのため）
        self._lock = threading.Lock()
        self._sorter: Sorter | None = None
        self._examples: dict[str, list[tuple[str, str]]] = {}
        self._last: dict[str, tuple[str, str, bool]] = {}  # 最後に読んだ届いたメール（EntryID → 件名・本文・旗）
        self._flags: dict[str, list[bool]] = {}  # 振り分け先のお手本ごとの旗（_examples と同じ並び）
        self._flagged_vectors = np.zeros((0, 768), dtype=np.float32)  # 旗付きメール（大事のお手本）の数字の列
        self._importance: Importance | None = None

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
        """振り分け先のフォルダのメールを、お手本として覚える。フォルダとお手本の数を返す。

        見つからないフォルダがあれば、覚えずに missing（その名前）と where（作る場所）を返す。画面は「はじめに」の案内を出す。
        """
        if self._reload is not None:
            self._store, self._folder, self._targets = self._reload()

        def read_targets(o: OutlookMover):
            missing = o.missing_folders([self._folder, *self._targets], store=self._store)
            if missing:
                return missing, {}
            read = {f: o.read(f, limit=EXAMPLES_PER_FOLDER, store=self._store) for f in self._targets}
            flagged = o.flagged([self._folder, *self._targets], scan=FLAG_SCAN, limit=FLAGGED_EXAMPLES,
                                store=self._store)
            return [], (read, flagged)

        missing, got = self._outlook(read_targets)
        if missing:
            where = (f"データファイル「{self._store}」の一番上" if self._store
                     else "受信トレイの下（作れないときは、受信トレイと同じ並び）")
            return {"folders": [], "missing": missing, "where": where}
        read, flagged = got
        examples = {f: [(m.subject, m.body) for m in ms] for f, ms in read.items()}
        if not any(examples.values()):  # フォルダはあるが、お手本のメールが1通も無い
            with self._lock:
                self._examples = examples
            return {"folders": self._folders(), "empty": True}
        with self._lock:
            self._examples = examples
            self._flags = {f: [m.flagged for m in ms] for f, ms in read.items()}
            if self._sorter is None:
                self._sorter = Sorter(Embedder())
            self._sorter.learn(self._examples)
            self._flagged_vectors = (self._sorter.embedder.embed([mail_text(m.subject, m.body) for m in flagged],
                                                                 prompt="classification")
                                     if flagged else np.zeros((0, 768), dtype=np.float32))
            self._build_importance()
            return {"folders": self._folders(), "flagged": len(flagged), "minFlagged": MIN_FLAGGED}

    def _build_importance(self) -> None:
        """大事の見分けを作り直す。「ふつう」は振り分け先の旗の無いお手本（振り分けで計算した数字の列を使い回す）。"""
        normal = [v for f, vecs in zip(self._sorter.folders, self._sorter.example_vectors)
                  for v, fl in zip(vecs, self._flags.get(f, [])) if not fl]
        imp = Importance(self._flagged_vectors, np.array(normal) if normal else np.zeros((0, 768), dtype=np.float32))
        self._importance = imp if imp.ready else None

    def folder_choices(self) -> dict:
        """振り分け先に選べるフォルダの一覧と、いま選んでいるもの（画面の「振り分け先を選ぶ」）。"""
        if self._reload is not None:
            self._store, self._folder, self._targets = self._reload()
        folders = self._outlook(lambda o: o.mail_folders(store=self._store))
        folders = [f for f in folders if f["path"] != self._folder]  # 届いたメールのフォルダは選べない
        return {"folders": folders, "selected": list(self._targets)}

    def save_targets(self, targets: list[str]) -> None:
        """選んだ振り分け先を設定ファイルに書く。このあと画面が「お手本を覚える」を呼ぶ。"""
        targets = [t for t in targets if t]
        if len(targets) < 2:
            raise ValueError("振り分け先は2つ以上選んでください")
        s = load_settings()
        s["targets"] = targets
        SETTINGS.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        self._targets = targets

    def mails(self) -> dict:
        """届いたメールのフォルダを読み、1通ずつ提案を付けて返す（読むだけ）。"""
        if self._sorter is None:
            raise RuntimeError("先にお手本を覚えてください")
        mails = self._outlook(lambda o: o.read(self._folder, limit=50, store=self._store))
        with self._lock:
            self._last = {m.entry_id: (m.subject, m.body, m.flagged) for m in mails}
            out = []
            for m in mails:
                vec = self._sorter.vector(m.subject, m.body)
                ranked = self._sorter.rank(vec)
                top = ranked[0]
                second = ranked[1] if len(ranked) > 1 else None  # フォルダが1つだけなら迷いようがない
                out.append({
                    "id": m.entry_id,
                    "subject": m.subject,
                    "snippet": snippet(m.body),
                    "folder": top.folder,
                    "unsure": second is not None and (top.score - second.score) < UNSURE_GAP,
                    "second": second.folder if second else None,
                    # 旗がまだ無く、「ふつう」より「大事」のお手本に、迷いの幅以上近いときだけ印を付ける
                    "important": (not m.flagged and self._importance is not None
                                  and self._importance.score(vec) >= UNSURE_GAP),
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
        subject, body, flagged = self._last.pop(entry_id)
        with self._lock:
            self._examples.setdefault(folder, []).append((subject, body))
            self._flags.setdefault(folder, []).append(flagged)
            self._sorter.learn(self._examples)  # 選び直したメールも、ここで新しいお手本になる
            self._build_importance()
        moved = {"subject": subject, "folder": folder}
        try:
            result = self.mails()  # 残りのメールの提案を出し直す
        except Exception as e:  # 移すのはできたので、一覧の読み直しの失敗とは分けて知らせる
            return {"moved": moved, "folders": self._folders(), "listError": str(e)}
        result.update({"moved": moved, "folders": self._folders()})
        return result


URL = re.compile(r"<?(?:https?|mailto):[^\s>]*>?")  # HTML メールの本文の頭に並びがちな、画像やリンクの URL


def snippet(body: str) -> str:
    """カードに出す本文の頭（URL は省き、改行や空白はまとめて1つにする）。"""
    return " ".join(URL.sub(" ", body).split())[:SNIPPET_CHARS]


def page() -> str:
    """ui/ の HTML に CSS と JavaScript を埋めこんだ1枚のページを作る。"""
    html = (UI / "index.html").read_text(encoding="utf-8")
    css = (UI / "style.css").read_text(encoding="utf-8")
    js = (UI / "app.js").read_text(encoding="utf-8")
    return html.replace("/*STYLE*/", css).replace("/*SCRIPT*/", js)


def check(api: Api) -> None:
    """窓を開かずに、画面が最初にすること（お手本を覚える・メールを読む）を試し、件数だけをファイルに書く。

    exe でだけ起きる問題（入っていない部品など）を、人が窓を見なくても見つけるためのもの。件名や本文は書かない。
    """
    log = SETTINGS.parent / "check.log"
    try:
        # 窓の部品（pywebview が使う pythonnet）も読み込んでおく。.NET が DLL を読めないときはここで分かる
        import clr  # noqa: F401
        learned = api.learn()
        if learned.get("missing"):
            raise RuntimeError(f"見つからないフォルダが {len(learned['missing'])} 個あります")
        if learned.get("empty"):
            raise RuntimeError("振り分け先のフォルダに、お手本のメールが1通もありません")
        folders = learned["folders"]
        mails = api.mails()["mails"]
        text = (f"OK お手本 {sum(f['count'] for f in folders)} 通（{len(folders)} フォルダ）、"
                f"届いたメール {len(mails)} 通、迷っています {sum(m['unsure'] for m in mails)} 通、"
                f"旗 {learned['flagged']} 通、大事かも {sum(m['important'] for m in mails)} 通")
    except Exception as e:
        text = f"NG {type(e).__name__}: {e}"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(text + "\n", encoding="utf-8")
    print(text)


def load_settings() -> dict:
    """設定ファイルを読む。無ければ、ふつうの設定で作っておく（あとで人が直せるように）。"""
    if not SETTINGS.exists():
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(DEFAULT_SETTINGS, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**DEFAULT_SETTINGS, **json.loads(SETTINGS.read_text(encoding="utf-8-sig"))}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", default=None, help="受信トレイの代わりに読む、データファイル（.pst など）の名前")
    ap.add_argument("--folder", default=None, help='届いたメールのフォルダ（"/" で区切る。空なら一番上か受信トレイ）')
    ap.add_argument("--targets", default=None, help="振り分け先のフォルダ（カンマ区切り）。中のメールがお手本になる")
    ap.add_argument("--check", action="store_true",
                    help="窓を開かずに、お手本を覚えてメールを読むところまで確かめ、結果を ~/.mail-shiwake/check.log に書く")
    args = ap.parse_args()

    def config():
        s = load_settings()  # コマンドで指定したものは、設定ファイルより優先する
        store = args.store if args.store is not None else s["store"]
        folder = args.folder if args.folder is not None else s["folder"]
        targets = [t.strip() for t in args.targets.split(",")] if args.targets is not None else list(s["targets"])
        return store, folder, [t for t in targets if t]

    api = Api(*config(), reload=config)
    if args.check:
        check(api)
        return
    webview.create_window("メール仕分け", html=page(), js_api=api,
                          width=1180, height=760, min_size=(760, 520))
    webview.start()


if __name__ == "__main__":
    main()
