"""Outlook の「新しいメールが届いた」の知らせ（NewMailEx）を受け取り、窓に伝える。

1分ごとの見張り（窓の watchNew）より早く新着を出すための近道。知らせが鳴らないアカウントや、
Outlook につなげないときは何もしない（そのときは1分ごとの見張りが拾う）。

- NewMailEx は受信トレイに新しいアイテムが届くたびに、EntryID を1つ渡して鳴る。Outlook のルールより前に鳴るので、
  ここではメールを読まず「届いたかも」とだけ伝え、窓がいつもの手順（new_mail_count → mails）で読み直す
- 知らせは**別のプログラム（子プロセス）**で待つ。同じプログラムの中のスレッドで待つと、お手本を覚える処理の
  Outlook とのやりとりが止まった（2026-11-01 _dev/tools/test_check_newmail.py で、なし 6秒で通る／あり 止まる）
- 受け手には NewMailEx 以外の知らせ（ItemLoad など）も届く。受け取りを待たせると Outlook が待たされるので、
  子は PumpMessages で待たずに受け取り続ける
- 子プロセスとは 127.0.0.1 の小さな通り道（ソケット）でつなぐ。子は知らせのたびに "new" を、5秒ごとに "." を送り、
  送れなくなったら（窓のプログラムが終わったら）自分も終わる
- 2026-11-01、この PC の Outlook で NewMailEx が鳴ることを _dev/tools/test_newmailex.py で確かめた（ItemAdd は鳴らなかった）

出典: Microsoft Learn「Application.NewMailEx event (Outlook)」、pywin32 win32com/client/__init__.py の DispatchWithEvents
"""
from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
from typing import Callable

FLAG = "--listen-newmail"  # 子プロセスとして起動するときの印（app.main が見る）


def start(notify: Callable[[], None]) -> threading.Thread | None:
    """子プロセスを起こし、知らせが届くたびに notify を呼ぶスレッドを始める（Windows でだけ）。"""
    if sys.platform != "win32":
        return None
    t = threading.Thread(target=_serve, args=(notify,), name="outlook-newmail", daemon=True)
    t.start()
    return t


def _serve(notify: Callable[[], None]) -> None:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))  # この PC の中だけ。空いている番号を使う
        server.listen(1)
        port = server.getsockname()[1]
        if getattr(sys, "frozen", False):  # exe のときは、同じ exe を印つきで
            cmd = [sys.executable, FLAG, str(port)]
        else:
            cmd = [sys.executable, "-m", "mail_shiwake.newmail", str(port)]
        try:
            subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError:
            return
        server.settimeout(60)
        try:
            conn, _ = server.accept()
        except OSError:  # 子が Outlook につなげなかった
            return
    with conn, conn.makefile("r", encoding="ascii") as lines:
        for line in lines:
            if line.strip() == "new":
                try:
                    notify()
                except Exception:  # 窓が閉じかけているときなど
                    pass


def child(port: int) -> None:
    """子プロセスの本体。Outlook の知らせを待ち、親に伝える。"""
    import os

    import pythoncom
    import win32com.client

    conn = socket.create_connection(("127.0.0.1", port))
    lock = threading.Lock()

    def send(data: bytes) -> None:
        try:
            with lock:
                conn.sendall(data)
        except OSError:  # 親（窓のプログラム）が終わった
            os._exit(0)

    class Events:
        def OnNewMailEx(self, entry_ids):  # メソッドの名前は「On ＋ 知らせの名前」（pywin32 の決まり）
            send(b"new\n")

    def heartbeat() -> None:
        while True:
            time.sleep(5)
            send(b".\n")  # 親が終わっていれば、ここで送れずに終わる

    pythoncom.CoInitialize()
    outlook = win32com.client.DispatchWithEvents("Outlook.Application", Events)  # noqa: F841  持っている間だけ届く
    threading.Thread(target=heartbeat, daemon=True).start()
    # 知らせは待たせずに受け取り続ける（PumpMessages は止まらない受け取りの輪）。
    # 受け手には NewMailEx 以外の知らせ（メールを読み込むたびの ItemLoad など）も届き、0.2 秒おきにしか受け取らないと、
    # Outlook が1通ごとに待たされて、お手本を読むのが止まったように遅くなった（2026-11-01）
    pythoncom.PumpMessages()


if __name__ == "__main__":
    child(int(sys.argv[1]))
