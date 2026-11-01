"""Outlook のメールを、人が選んだフォルダへ移す（4番。Windows 専用）。

- 移すのは、画面で人が「移す」を押したときだけ。自動では移さない
- 使う書きこみの命令は MailItem.Move の一つだけ。消す・書きかえる・送る命令は使わない
"""

from __future__ import annotations

from .outlook import OL_MAIL, OutlookReader


class OutlookMover(OutlookReader):
    def move(self, entry_id: str, dest_path: str, store: str | None = None) -> str:
        """EntryID のメールを、dest_path のフォルダへ移す。移したあとのメールの EntryID を返す（元に戻すときに使う）。"""
        dest = self.folder(dest_path, store)
        # メールを ID で取り出す。公式資料では、ふつうデータファイルの印（StoreID）も渡す。届いたメールと移す先は同じデータファイル
        item = self._ns.GetItemFromID(entry_id, dest.StoreID)
        if item.Class != OL_MAIL:
            raise ValueError("メールではないものは移しません")
        moved = item.Move(dest)  # MailItem.Move は、移したあとのメールを返す（EntryID が変わることがある）
        return moved.EntryID
