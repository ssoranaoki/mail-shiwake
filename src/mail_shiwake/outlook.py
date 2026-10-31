"""クラシック版 Outlook からメールを読む窓口（読むだけ。Windows 専用）。

- メールを移す・消す・書きかえる操作は、ここには一つもない（移すのは「移す」の単位で作る）
- メールの中身はパソコンの中の Outlook から読むだけで、どこにも送らない
- Outlook の操作は COM（Windows の仕組み）を pywin32 で呼ぶ。名前と番号は Microsoft の Outlook VBA の資料に合わせた
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

OL_FOLDER_INBOX = 6  # OlDefaultFolders.olFolderInbox
OL_MAIL = 43  # OlObjectClass.olMail（メール以外の会議の招待などは読まない）
OL_MAIL_ITEM = 0  # OlItemType.olMailItem（Folder.DefaultItemType がこれならメールのフォルダ）
# OlDefaultFolders: 削除済み 3・送信トレイ 4・送信済み 5・下書き 16・迷惑メール 23（振り分け先にしない）
OL_SPECIAL_FOLDERS = (3, 4, 5, 16, 23)


@dataclass
class Mail:
    entry_id: str  # Outlook の中でメールを見分ける番号（あとで「移す」ときに使う）
    subject: str
    body: str
    received: datetime | None
    flagged: bool = False  # 旗（フラグ）が付いているか（MailItem.IsMarkedAsTask）


class OutlookReader:
    def __init__(self) -> None:
        try:
            import win32com.client  # Windows で pywin32 が入っているときだけ使える
        except ImportError as e:
            raise RuntimeError("Outlook とつなぐ部分は、Windows のクラシック版 Outlook でだけ動きます") from e
        self._app = win32com.client.Dispatch("Outlook.Application")
        self._ns = self._app.GetNamespace("MAPI")

    def inbox(self):
        return self._ns.GetDefaultFolder(OL_FOLDER_INBOX)

    def folder(self, path: str = "", store: str | None = None):
        """"/" で区切ったフォルダの名前をたどる。

        store を指定しなければ受信トレイから下を、指定すればその名前のデータファイル（ストア）の一番上から下をたどる。
        受信トレイの下に無ければ、受信トレイと同じ並び（アカウントの一番上）も探す。
        IMAP のアカウントには、受信トレイの下にフォルダを作れないものがあるため。
        """
        if store is not None:
            return self._walk(self._store_root(store), path)
        inbox = self.inbox()
        try:
            return self._walk(inbox, path)
        except Exception:  # COM は見つからないとき com_error を出す
            if not path.strip("/"):
                raise
            return self._walk(inbox.Parent, path)  # Folder.Parent: 受信トレイの1つ上のフォルダ

    @staticmethod
    def _walk(f, path: str):
        for name in [p for p in path.split("/") if p]:
            f = f.Folders.Item(name)
        return f

    def missing_folders(self, paths: list[str], store: str | None = None) -> list[str]:
        """paths のうち、Outlook に見つからないフォルダの名前を返す。"""
        missing = []
        for p in paths:
            try:
                self.folder(p, store)
            except Exception:  # COM は見つからないとき com_error を出す
                missing.append(p)
        return missing

    def _store_root(self, name: str):
        for st in self._ns.Stores:
            root = st.GetRootFolder()
            # データファイルの名前は、Outlook の左の一覧に出る一番上のフォルダの名前と同じことが多い
            if name in (st.DisplayName, root.Name):
                return root
        raise LookupError(f"「{name}」という名前のデータファイルが Outlook にありません")

    def mail_folders(self, store: str | None = None, max_depth: int = 3) -> list[dict]:
        """振り分け先に選べるメールのフォルダの一覧（path・name・depth・count）。

        path は folder() に渡せる形。store を指定しなければ、受信トレイの下と、受信トレイと同じ並びを返す。
        カレンダー・連絡先などメール以外のフォルダと、送信済み・削除済みなどの決まったフォルダは入れない。
        """
        out: list[dict] = []

        def walk(parent, prefix: str, depth: int, skip: set[str]) -> None:
            for f in parent.Folders:
                if f.DefaultItemType != OL_MAIL_ITEM or f.EntryID in skip:
                    continue
                path = f"{prefix}{f.Name}"
                out.append({"path": path, "name": f.Name, "depth": depth, "count": f.Items.Count})
                if depth + 1 < max_depth:
                    walk(f, path + "/", depth + 1, skip)

        if store is not None:
            root = self._store_root(store)
            walk(root, "", 0, self._special_ids(root.Store))
            return out
        inbox = self.inbox()
        skip = self._special_ids(inbox.Store) | {inbox.EntryID}
        walk(inbox, "", 0, skip)
        seen = {d["path"] for d in out}
        before = len(out)
        walk(inbox.Parent, "", 0, skip)  # 受信トレイと同じ並び（IMAP など）
        out[before:] = [d for d in out[before:] if d["path"] not in seen]  # 同じ名前なら受信トレイの下を使う（folder() と同じ順）
        return out

    @staticmethod
    def _special_ids(store) -> set[str]:
        """送信済み・削除済みなど、振り分け先にしない決まったフォルダの EntryID。"""
        ids = set()
        for t in OL_SPECIAL_FOLDERS:
            try:
                f = store.GetDefaultFolder(t)  # そのストアに無い種類は None（または失敗）
            except Exception:
                continue
            if f is not None:
                ids.add(f.EntryID)
        return ids

    def list_folders(self, path: str = "", store: str | None = None) -> list[str]:
        """そのフォルダのすぐ下にあるフォルダの名前の一覧。"""
        return [sub.Name for sub in self.folder(path, store).Folders]

    def read(self, path: str = "", limit: int = 50, store: str | None = None) -> list[Mail]:
        """フォルダのメールを、新しい順に最大 limit 通読む。"""
        items = self.folder(path, store).Items
        items.Sort("[ReceivedTime]", True)
        mails: list[Mail] = []
        for item in items:
            if len(mails) >= limit:
                break
            if item.Class != OL_MAIL:
                continue
            mails.append(self._mail(item))
        return mails

    def flagged(self, paths: list[str], scan: int = 300, limit: int = 50, store: str | None = None) -> list[Mail]:
        """フォルダの新しいメール scan 通ずつから、旗の付いたものを集め、新しい順に最大 limit 通返す。"""
        found: list[Mail] = []
        for p in paths:
            items = self.folder(p, store).Items
            items.Sort("[ReceivedTime]", True)
            for n, item in enumerate(items):
                if n >= scan:
                    break
                if item.Class == OL_MAIL and item.IsMarkedAsTask:
                    found.append(self._mail(item))
        found.sort(key=lambda m: m.received.timestamp() if m.received else 0.0, reverse=True)
        return found[:limit]

    @staticmethod
    def _mail(item) -> Mail:
        received = item.ReceivedTime
        # 送っていない下書きは、受け取った日時が 4501年1月1日（日時なしの印）になる
        if not isinstance(received, datetime) or received.year >= 4500:
            received = None
        return Mail(item.EntryID, item.Subject or "", item.Body or "", received, bool(item.IsMarkedAsTask))
