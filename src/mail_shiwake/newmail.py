"""Outlook の「新しいメールが届いた」の知らせ（NewMailEx）を受け取り、窓に伝える。

1分ごとの見張り（窓の watchNew）より早く新着を出すための近道。知らせが鳴らないアカウントや、
Outlook につなげないときは何もしない（そのときは1分ごとの見張りが拾う）。

- NewMailEx は受信トレイに新しいアイテムが届くたびに、EntryID を1つ渡して鳴る。Outlook のルールより前に鳴るので、
  ここではメールを読まず「届いたかも」とだけ窓に伝え、窓がいつもの手順（new_mail_count → mails）で読み直す
- COM の知らせは、受け手を作ったスレッドが PumpWaitingMessages で配っている間だけ届く。そのため専用のスレッドで待つ
- 2026-11-01、この PC の Outlook で鳴ることを _dev/tools/test_newmailex.py で確かめた（ItemAdd は鳴らなかった）

出典: Microsoft Learn「Application.NewMailEx event (Outlook)」、pywin32 win32com/client/__init__.py の DispatchWithEvents
"""
from __future__ import annotations

import threading
import time
from typing import Callable


def start(notify: Callable[[], None]) -> threading.Thread | None:
    """知らせを待つスレッドを始める。notify は新着の知らせが鳴るたびに（そのスレッドで）呼ばれる。"""
    try:
        import pythoncom  # noqa: F401  Windows で pywin32 が入っているときだけ
    except ImportError:
        return None
    t = threading.Thread(target=_listen, args=(notify,), name="outlook-newmail", daemon=True)
    t.start()
    return t


def _listen(notify: Callable[[], None]) -> None:
    import pythoncom
    import win32com.client

    class Events:
        def OnNewMailEx(self, entry_ids):  # メソッドの名前は「On ＋ 知らせの名前」（pywin32 の決まり）
            try:
                notify()
            except Exception:  # 窓が閉じかけているときなど。知らせを受けるのは続ける
                pass

    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.DispatchWithEvents("Outlook.Application", Events)  # noqa: F841  持っている間だけ届く
        while True:
            pythoncom.PumpWaitingMessages()  # このスレッドで、届いた知らせを配る
            time.sleep(0.2)
    except Exception:  # Outlook につなげない・知らせを付けられないときは、1分ごとの見張りに任せる
        return
    finally:
        pythoncom.CoUninitialize()
