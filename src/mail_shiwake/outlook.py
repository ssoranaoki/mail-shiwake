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


@dataclass
class Mail:
    entry_id: str  # Outlook の中でメールを見分ける番号（あとで「移す」ときに使う）
    subject: str
    body: str
    received: datetime | None


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
        """
        f = self.inbox() if store is None else self._store_root(store)
        for name in [p for p in path.split("/") if p]:
            f = f.Folders.Item(name)
        return f

    def _store_root(self, name: str):
        for st in self._ns.Stores:
            root = st.GetRootFolder()
            # データファイルの名前は、Outlook の左の一覧に出る一番上のフォルダの名前と同じことが多い
            if name in (st.DisplayName, root.Name):
                return root
        raise LookupError(f"「{name}」という名前のデータファイルが Outlook にありません")

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
            received = item.ReceivedTime
            # 送っていない下書きは、受け取った日時が 4501年1月1日（日時なしの印）になる
            if not isinstance(received, datetime) or received.year >= 4500:
                received = None
            mails.append(Mail(item.EntryID, item.Subject or "", item.Body or "", received))
        return mails
