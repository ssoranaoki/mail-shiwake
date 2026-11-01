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
import sys
import threading
from pathlib import Path

import webview

import numpy as np

from .cache import CachedEmbedder
from .embedder import REVISION, Embedder
from .importance import MIN_FLAGGED, Importance
from . import newmail
from .mover import OutlookMover
from .sorter import Sorter, mail_text
from .trust import Trust

UI = Path(__file__).resolve().parent / "ui"
SETTINGS = Path.home() / ".mail-shiwake" / "settings.json"  # 起動の設定（ダブルクリックで起動するときに使う）
TRUST = SETTINGS.parent / "trust.json"  # フォルダごとの信頼（当たり・外れだけ。件名は入れない）
VECTORS = SETTINGS.parent / "vectors" / f"embeddinggemma-2-{REVISION[:12]}-q4.npz"  # 覚えた数字の列（文章は入れない）
DEFAULT_SETTINGS = {
    "store": None,  # 読むデータファイルの名前。null なら受信トレイ
    "folder": "",  # 届いたメールのフォルダ（"" なら受信トレイそのもの）
    "targets": ["請求書", "注文", "問い合わせ", "お知らせ"],  # 振り分け先（中のメールがお手本になる）
    "bulk_folder": None,  # 配信メールをまとめて移す先（画面で選ぶと覚える）
    "auto_move": False,  # 信頼のあるフォルダへの確かな提案を、起動したときに自動で移す（窓のスイッチで切り替える）
    "refresh_minutes": 0,  # 窓を開いている間、この分ごとに「お手本を覚える」を繰り返す（0 はしない）
}
REFRESH_CHOICES = (0, 5, 15, 30, 60)  # 窓で選べる読み直しの間隔（分）
EXAMPLES_PER_FOLDER = 50  # フォルダごとに覚えるお手本の数（新しい順）
MIN_EXAMPLES = 3  # 振り分け先ごとのお手本がこれより少ないと、「あと何通」と案内する（0通のフォルダは提案に出ない）
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
        self._trust = Trust(TRUST)
        self._suggest: dict[str, tuple[str, bool]] = {}  # 最後の提案（EntryID → 提案したフォルダ、迷っていないか）
        self._auto_ready: dict[str, str] = {}
        self._auto_log: list[dict] = []  # この窓で自動で移したメール（元に戻すため。件名・本文はメモリの中だけ）
        self._window = None  # 窓（作業の様子を知らせる先）。--check・--json では None

    def _activity(self, text: str) -> None:
        """いま何をしているかを、窓のボタンの横に出す（窓が無いときは何もしない）。"""
        if self._window is None:
            return
        try:
            self._window.run_js(f"window.setActivity && window.setActivity({json.dumps(text, ensure_ascii=False)})")
        except Exception:  # 知らせが届かなくても、作業は続ける
            pass

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
        out = []
        for f in self._targets:
            n = len(self._examples.get(f, []))
            out.append({"name": f, "count": n, "needed": max(0, MIN_EXAMPLES - n),  # needed: あと何通あるとよいか
                        "trust": self._trust.status(f)})  # 信頼（最近の当たり・外れ）
        return out

    def learn(self) -> dict:
        """振り分け先のフォルダのメールを、お手本として覚える。フォルダとお手本の数を返す。

        見つからないフォルダがあれば、覚えずに missing（その名前）と where（作る場所）を返す。画面は「はじめに」の案内を出す。
        """
        if self._reload is not None:
            self._store, self._folder, self._targets = self._reload()

        def read_targets(o: OutlookMover):
            self._activity("Outlook で振り分け先のフォルダを探しています…")
            missing = o.missing_folders([self._folder, *self._targets], store=self._store)
            if missing:
                return missing, {}
            read = {}
            for f in self._targets:
                self._activity(f"Outlook から「{f}」のお手本を読んでいます…")
                read[f] = o.read(f, limit=EXAMPLES_PER_FOLDER, store=self._store)
            self._activity("旗の付いたメールを探しています…")
            flagged = o.flagged([self._folder, *self._targets], scan=FLAG_SCAN, limit=FLAGGED_EXAMPLES,
                                store=self._store)
            return [], (read, flagged)

        missing, got = self._outlook(read_targets)
        if missing:
            where = (f"データファイル「{self._store}」の一番上" if self._store
                     else "受信トレイの下（作れないときは、受信トレイと同じ並び）")
            return {"folders": [], "missing": missing, "where": where,
                    "nextSteps": [{"action": "create_folders", "folders": missing, "where": where},
                                  {"action": "choose_targets"}]}
        read, flagged = got
        examples = {f: [(m.subject, m.body) for m in ms] for f, ms in read.items()}
        if not any(examples.values()):  # フォルダはあるが、お手本のメールが1通も無い
            with self._lock:
                self._examples = examples
            return {"folders": self._folders(), "empty": True,
                    "nextSteps": [{"action": "add_examples", "folders": list(self._targets)},
                                  {"action": "choose_targets"}]}
        with self._lock:
            self._examples = examples
            self._flags = {f: [m.flagged for m in ms] for f, ms in read.items()}
            if self._sorter is None:
                self._activity("モデルを読み込んでいます…（はじめてのときはダウンロードに数分かかります）")
                # 一度計算したメールは計算し直さない。数字の列はパソコンの中のファイルにも残す（モデルの版ごと）
                self._sorter = Sorter(CachedEmbedder(Embedder(), path=VECTORS))
            self._activity(f"お手本を覚えています（{sum(len(v) for v in self._examples.values())} 通）…")
            self._sorter.learn(self._examples)
            self._flagged_vectors = (self._sorter.embedder.embed([mail_text(m.subject, m.body) for m in flagged],
                                                                 prompt="classification")
                                     if flagged else np.zeros((0, 768), dtype=np.float32))
            self._build_importance()
            self._sorter.embedder.save()  # 新しく計算した数字の列をファイルに残す（次に起動したとき計算しない）
            steps = [{"action": "add_examples", "folders": [f["name"] for f in self._folders() if f["needed"]],
                      "need": MIN_EXAMPLES}] if any(f["needed"] for f in self._folders()) else []
            if len(flagged) < MIN_FLAGGED:
                steps.append({"action": "flag_more", "have": len(flagged), "need": MIN_FLAGGED})
            return {"folders": self._folders(), "flagged": len(flagged), "minFlagged": MIN_FLAGGED, "nextSteps": steps}

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
        self._activity("Outlook のフォルダを読んでいます…")
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
        self._activity("Outlook から届いたメールを読んでいます…")
        mails = self._outlook(lambda o: o.read(self._folder, limit=50, store=self._store))
        with self._lock:
            self._last = {m.entry_id: (m.subject, m.body, m.flagged) for m in mails}
            self._suggest = {}
            self._auto_ready: dict[str, str] = {}  # 自動で移してよいメール（EntryID → 提案したフォルダ）
            out = []
            for n, m in enumerate(mails, 1):
                if n % 5 == 1:
                    self._activity(f"提案を計算しています（{n} / {len(mails)} 通）…")
                vec = self._sorter.vector(m.subject, m.body)
                ranked = self._sorter.rank(vec)
                top = ranked[0]
                second = ranked[1] if len(ranked) > 1 else None  # フォルダが1つだけなら迷いようがない
                # 旗がまだ無く、「ふつう」より「大事」のお手本に、迷いの幅以上近いときだけ印を付ける
                imp_score = self._importance.score(vec) if self._importance is not None else None
                important = not m.flagged and imp_score is not None and imp_score >= UNSURE_GAP
                out.append({
                    "id": m.entry_id,
                    "subject": m.subject,
                    "snippet": snippet(m.body),
                    "received": m.received.isoformat() if m.received else None,
                    "folder": top.folder,
                    "unsure": second is not None and (top.score - second.score) < UNSURE_GAP,
                    "second": second.folder if second else None,
                    # 近さの数字（コサイン類似度）。画面には出さないが、データには残す
                    "scores": [{"folder": r.folder, "score": round(r.score, 4)} for r in ranked],
                    "gap": round(top.score - second.score, 4) if second else None,  # 1位と2位の差（unsureGap 未満で迷う）
                    "importanceScore": round(imp_score, 4) if imp_score is not None else None,  # プラスなら大事寄り
                    "flagged": m.flagged,
                    "important": important,
                    "bulk": m.bulk_reason is not None,  # 配信メール（メルマガ・宣伝・一斉のお知らせ）
                    "bulkReason": m.bulk_reason,  # 何で見分けたか（ヘッダーの名前）
                    # 画面のどこに出すか: 配信メールは下の箱へ。旗付き・大事かもは配信でも上に残す
                    "group": "bulk" if m.bulk_reason and not m.flagged and not important else "main",
                })
                # 提案どおりにまとめて移してよいか（迷っている・大事かもは、1通ずつ確かめてもらう）
                out[-1]["autoMove"] = out[-1]["group"] == "main" and not out[-1]["unsure"] and not important
                # 自動で移してよいか（まとめて移せる提案で、旗が無く、提案先のフォルダに信頼がある）
                out[-1]["autoReady"] = (out[-1]["autoMove"] and not m.flagged
                                        and self._trust.status(top.folder)["trusted"]
                                        and not self._trust.skipped(m.subject, m.body))  # 元に戻したメールは除く
                if out[-1]["autoReady"]:
                    self._auto_ready[m.entry_id] = top.folder
        self._suggest = {m["id"]: (m["folder"], m["autoMove"]) for m in out}
        self._sorter.embedder.save()
        return {"mails": out, "source": self._store or "受信トレイ", "folderName": self._folder or "受信トレイ",
                "targets": self._targets, "bulkFolder": load_settings().get("bulk_folder"),
                # 判断に使った線（画面の「迷っています」「大事かも」は、この値と比べて決めている）
                "thresholds": {"unsureGap": UNSURE_GAP, "importantGap": UNSURE_GAP, "minFlagged": MIN_FLAGGED},
                "nextSteps": mail_steps(out, load_settings().get("bulk_folder")),
                "refreshMinutes": int(load_settings().get("refresh_minutes") or 0),  # 窓が読み直す間隔（0 はしない）
                "autoMove": {"enabled": bool(load_settings().get("auto_move")),
                             "trustedFolders": [f for f in self._targets if self._trust.status(f)["trusted"]]}}

    def _record_trust(self, entry_id: str, chosen: str) -> None:
        """人が移したメールについて、提案したフォルダの当たり・外れを貯める（迷っていない提案だけ）。"""
        suggested, sure = self._suggest.get(entry_id, (None, False))
        if suggested is not None and sure:
            self._trust.record(suggested, chosen == suggested)

    def move_many(self, moves: list[dict]) -> dict:
        """上の一覧のメールを、それぞれ選ばれたフォルダへまとめて移す（「まとめて移す」を押したときだけ）。

        moves は [{"id": EntryID, "folder": 振り分け先}]。移したメールは、1通ずつ移したときと同じくお手本に加える。
        """
        pairs = [(m["id"], m["folder"]) for m in moves if m.get("id") in self._last]
        if not pairs:
            raise LookupError("移すメールがありません")
        for _, f in pairs:
            if f not in self._targets:
                raise ValueError(f"「{f}」は振り分け先ではありません")

        def work(o: OutlookMover):
            done, failed = [], 0
            for n, (i, f) in enumerate(pairs, 1):
                self._activity(f"Outlook でメールを移しています（{n} / {len(pairs)} 通）…")
                try:
                    o.move(i, f, store=self._store)
                    done.append((i, f))
                except Exception:
                    failed += 1
            return done, failed

        done, failed = self._outlook(work)
        with self._lock:
            for i, f in done:
                self._record_trust(i, f)
                subject, body, flagged = self._last.pop(i)
                self._examples.setdefault(f, []).append((subject, body))
                self._flags.setdefault(f, []).append(flagged)
            if done:
                self._activity("お手本を覚え直しています…")
                self._sorter.learn(self._examples)  # まとめて移したメールも、ここで新しいお手本になる
                self._build_importance()
        info = {"count": len(done), "failed": failed}
        try:
            result = self.mails()
        except Exception as e:
            return {"manyMoved": info, "folders": self._folders(), "listError": str(e)}
        result.update({"manyMoved": info, "folders": self._folders()})
        return result

    def new_mail_count(self) -> dict:
        """届いたメールのフォルダに、いまの一覧に無いメールが何通あるか（窓が1分ごとに見る。本文は読まない）。"""
        if self._sorter is None:
            return {"count": 0}
        ids = self._outlook(lambda o: o.entry_ids(self._folder, limit=50, store=self._store))
        return {"count": sum(i not in self._last for i in ids)}

    def open_mail(self, entry_id: str) -> None:
        """届いたメールを Outlook の窓で開く（迷ったときに中身を読むため）。"""
        if entry_id not in self._last:
            raise LookupError("そのメールは、いまの一覧にありません")
        self._activity("Outlook でメールを開いています…")
        self._outlook(lambda o: o.open(entry_id, self._folder, store=self._store))

    def set_refresh(self, minutes: int) -> dict:
        """読み直しの間隔（分）を設定ファイルに覚える。0 はしない。"""
        minutes = int(minutes)
        if minutes not in REFRESH_CHOICES:
            raise ValueError(f"読み直しの間隔は {REFRESH_CHOICES} のどれかです")
        s = load_settings()
        s["refresh_minutes"] = minutes
        SETTINGS.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"minutes": minutes}

    def set_auto_move(self, enabled: bool) -> dict:
        """「自動で移す」のスイッチ。設定ファイルに覚える。"""
        s = load_settings()
        s["auto_move"] = bool(enabled)
        SETTINGS.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"enabled": bool(enabled)}

    def auto_move(self, keep: list[str] | None = None) -> dict:
        """スイッチがオンのとき、信頼のあるフォルダへの確かな提案（autoReady）を自動で移す。移したメールはお手本に加える。
        keep は、人が画面でチェックを外した・フォルダを選び直したメールの EntryID。自動では移さない。"""
        if not load_settings().get("auto_move"):
            raise RuntimeError("「自動で移す」がオフです")
        skip = set(keep or [])
        pairs = [(i, f) for i, f in self._auto_ready.items() if i in self._last and i not in skip]

        def work(o: OutlookMover):
            done, failed = [], 0
            for n, (i, f) in enumerate(pairs, 1):
                self._activity(f"自動で移しています（{n} / {len(pairs)} 通）…")
                try:
                    done.append((i, f, o.move(i, f, store=self._store)))
                except Exception:
                    failed += 1
            return done, failed

        done, failed = self._outlook(work) if pairs else ([], 0)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        items = []
        with self._lock:
            for i, f, new_id in done:
                subject, body, flagged = self._last.pop(i)
                self._examples.setdefault(f, []).append((subject, body))
                self._flags.setdefault(f, []).append(flagged)
                entry = {"id": new_id, "subject": subject, "folder": f, "movedAt": now}
                self._auto_log.append({**entry, "_body": body, "_flagged": flagged})
                items.append(entry)
            if done:
                self._activity("お手本を覚え直しています…")
                self._sorter.learn(self._examples)
                self._build_importance()
        info = {"count": len(done), "failed": failed, "items": items}
        result = self.mails()
        result.update({"autoMoved": info, "folders": self._folders()})
        return result

    def undo_auto(self, moved_id: str) -> dict:
        """自動で移したメールを、届いたメールのフォルダへ戻す。そのフォルダの「外れ」として信頼に記録し、お手本からも外す。"""
        entry = next((e for e in self._auto_log if e["id"] == moved_id), None)
        if entry is None:
            raise LookupError("そのメールは、自動で移したメールの一覧にありません")
        self._activity("元に戻しています…")
        self._outlook(lambda o: o.move(moved_id, self._folder, store=self._store))
        self._auto_log.remove(entry)
        self._trust.record(entry["folder"], False)
        self._trust.skip(entry["subject"], entry["_body"])
        with self._lock:
            ex, fl = self._examples.get(entry["folder"], []), self._flags.get(entry["folder"], [])
            pair = (entry["subject"], entry["_body"])
            if pair in ex:
                k = len(ex) - 1 - ex[::-1].index(pair)  # いちばん後ろに足したもの
                del ex[k]
                if k < len(fl):
                    del fl[k]
            self._activity("お手本を覚え直しています…")
            self._sorter.learn(self._examples)
            self._build_importance()
        result = self.mails()
        result.update({"undone": {"subject": entry["subject"], "folder": entry["folder"]}, "folders": self._folders()})
        return result

    def move_bulk(self, entry_ids: list[str], folder: str) -> dict:
        """配信メールを、人が選んだフォルダへまとめて移す（「まとめて移す」を押したときだけ）。

        振り分けのお手本には足さない。移す先は設定ファイルに覚えておく。
        """
        ids = [i for i in entry_ids if i in self._last]
        if not ids:
            raise LookupError("移す配信メールがありません")

        def work(o: OutlookMover):
            o.folder(folder, self._store)  # 無いフォルダなら、ここで止まる（1通も移さない）
            moved, failed = 0, 0
            for n, i in enumerate(ids, 1):
                if n % 5 == 1:
                    self._activity(f"Outlook で配信メールを移しています（{n} / {len(ids)} 通）…")
                try:
                    o.move(i, folder, store=self._store)
                    moved += 1
                except Exception:
                    failed += 1
            return moved, failed

        moved, failed = self._outlook(work)
        for i in ids:
            self._last.pop(i, None)
        s = load_settings()
        s["bulk_folder"] = folder
        SETTINGS.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        info = {"count": moved, "failed": failed, "folder": folder}
        try:
            result = self.mails()
        except Exception as e:
            return {"bulkMoved": info, "folders": self._folders(), "listError": str(e)}
        result.update({"bulkMoved": info, "folders": self._folders()})
        return result

    def move(self, entry_id: str, folder: str) -> dict:
        """人が「移す」を押したメールを、選んだフォルダへ移す。移したメールは、すぐにお手本に加える。"""
        if folder not in self._targets:
            raise ValueError(f"「{folder}」は振り分け先ではありません")
        if entry_id not in self._last:
            raise LookupError("そのメールは、いまの一覧にありません")
        self._activity(f"Outlook でメールを「{folder}」へ移しています…")
        self._outlook(lambda o: o.move(entry_id, folder, store=self._store))
        self._record_trust(entry_id, folder)
        subject, body, flagged = self._last.pop(entry_id)
        with self._lock:
            self._examples.setdefault(folder, []).append((subject, body))
            self._flags.setdefault(folder, []).append(flagged)
            self._activity("お手本を覚え直しています…")
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


def mail_steps(mails: list[dict], bulk_folder: str | None) -> list[dict]:
    """届いたメールについて、次にできる操作（画面の文の代わりに、記号と数で）。"""
    main = [m for m in mails if m["group"] == "main"]
    bulk = [m for m in mails if m["group"] == "bulk"]
    steps = []
    if any(m["important"] for m in main):
        steps.append({"action": "check_important", "count": sum(m["important"] for m in main)})
    if any(m["unsure"] for m in main):
        steps.append({"action": "review_unsure", "count": sum(m["unsure"] for m in main)})
    if any(m.get("autoMove") for m in main):
        steps.append({"action": "move_many", "count": sum(bool(m.get("autoMove")) for m in main)})  # 提案どおりにまとめて
    if main:
        steps.append({"action": "move", "count": len(main)})  # 提案を見て1通ずつ移す
    if bulk:
        steps.append({"action": "move_bulk", "count": len(bulk), "folder": bulk_folder} if bulk_folder
                     else {"action": "choose_bulk_folder", "count": len(bulk)})
    return steps


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
                f"旗 {learned['flagged']} 通、大事かも {sum(m['important'] for m in mails)} 通、"
                f"配信メール {sum(m['bulk'] for m in mails)} 通（箱へ {sum(m['group'] == 'bulk' for m in mails)} 通）")
    except Exception as e:
        text = f"NG {type(e).__name__}: {e}"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(text + "\n", encoding="utf-8")
    print(text)


SCHEMA = 1  # --json で出すデータの形の版（項目の意味を変えたら上げる。説明は docs/data.md）


def export(api: Api) -> dict:
    """窓を開かずに、お手本を覚えて提案を出し、そのままのデータを返す（--json。読むだけで、メールは移さない）。"""
    from datetime import datetime, timezone
    from importlib.metadata import PackageNotFoundError, version

    try:
        app_version = version("mail-shiwake")
    except PackageNotFoundError:
        app_version = None
    out = {"schema": SCHEMA, "app": "mail-shiwake", "version": app_version,
           "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    learned = api.learn()
    out["learn"] = learned
    out["nextSteps"] = learned.get("nextSteps", [])
    if learned.get("missing"):
        out["status"] = "missing_folders"
        return out
    if learned.get("empty"):
        out["status"] = "no_examples"
        return out
    out["status"] = "ok"
    got = api.mails()
    steps = learned.get("nextSteps", []) + got.pop("nextSteps", [])
    out.update(got)
    out["nextSteps"] = steps
    return out


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
    ap.add_argument("--json", nargs="?", const="-", default=None, metavar="FILE",
                    help="窓を開かずに、提案をデータ（JSON）で出す。FILE を付けるとそのファイルに、付けないと画面に書く。メールは移さない")
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
    if args.json is not None:
        text = json.dumps(export(api), ensure_ascii=False, indent=2)
        if args.json == "-":
            sys.stdout.reconfigure(encoding="utf-8")
            print(text)
        else:
            Path(args.json).write_text(text + "\n", encoding="utf-8")
        return
    api._window = webview.create_window("メール仕分け", html=page(), js_api=api,
                                        width=1180, height=760, min_size=(760, 520),
                                        maximized=True)  # 起動したときは画面いっぱい（2026-11-01 ユーザー指示）。元に戻すと 1180×760

    def arrived() -> None:  # Outlook の新着の知らせ（NewMailEx）→ 窓に「届いたかも」と伝える。読み直すのは窓
        api._window.run_js("window.mailArrived && window.mailArrived()")

    newmail.start(arrived)
    webview.start()


if __name__ == "__main__":
    main()
