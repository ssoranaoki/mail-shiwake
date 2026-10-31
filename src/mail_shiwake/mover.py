"""Outlook のメールを、人が選んだフォルダへ移す（4番。Windows 専用）。

- 移すのは、画面で人が「移す」を押したときだけ。自動では移さない
- 使う書きこみの命令は MailItem.Move の一つだけ。消す・書きかえる・送る命令は使わない
"""

from __future__ import annotations

from .outlook import OL_MAIL, OutlookReader


class OutlookMover(OutlookReader):
    def move(self, entry_id: str, dest_path: str, store: str | None = None) -> str:
        """EntryID のメールを、dest_path のフォルダへ移す。移した先のフォルダの名前を返す。"""
        dest = self.folder(dest_path, store)
        # メールを ID で取り出す。データファイルが違うと見つからないので、移す先と同じデータファイルの ID を渡す
        item = self._ns.GetItemFromID(entry_id, dest.StoreID)
        if item.Class != OL_MAIL:
            raise ValueError("メールではないものは移しません")
        item.Move(dest)
        return dest.Name
