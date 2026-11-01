"""フォルダごとの信頼（提案どおりに移したか、選び直したか）を貯める。

自動で移すのは、信頼のあるフォルダへの提案だけ。数えるのは、迷っていない提案（自動で移す対象になりうるもの）だけ。
記録は結果（当たり・外れ）と、元に戻したメールの文面のハッシュだけで、件名や本文は残さない。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

TRUST_WINDOW = 20  # 最近の何通で見るか
TRUST_MAX_MISS = 1  # その中の外れ（選び直し・元に戻す）がこれ以下なら信頼あり
MAX_SKIP = 1000  # 自動では移さないメール（元に戻したもの）を覚えておく数


class Trust:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._log: dict[str, list[bool]] = {}  # フォルダ → 最近の結果（True が当たり）。古い順
        self._skip: list[str] = []  # 元に戻したメールの、文面のハッシュ（自動ではもう移さない）
        if path is not None and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._log = {f: [bool(x) for x in v][-TRUST_WINDOW:] for f, v in data.get("folders", {}).items()}
                self._skip = [str(x) for x in data.get("skip", [])][-MAX_SKIP:]
            except Exception:  # 壊れたファイルは使わず、最初から貯める
                self._log, self._skip = {}, []

    @staticmethod
    def mail_key(subject: str, body: str) -> str:
        return hashlib.sha256(f"{subject}\0{body}".encode("utf-8")).hexdigest()

    def skip(self, subject: str, body: str) -> None:
        """元に戻したメールを、これからは自動で移さない。"""
        k = self.mail_key(subject, body)
        if k not in self._skip:
            self._skip.append(k)
            del self._skip[:-MAX_SKIP]
            self._save()

    def skipped(self, subject: str, body: str) -> bool:
        return self.mail_key(subject, body) in self._skip

    def record(self, folder: str, hit: bool) -> None:
        """提案したフォルダについて、当たり（そのまま移した）か外れ（選び直した・元に戻した）かを貯める。"""
        log = self._log.setdefault(folder, [])
        log.append(hit)
        del log[:-TRUST_WINDOW]
        self._save()

    def status(self, folder: str) -> dict:
        log = self._log.get(folder, [])
        misses = sum(not x for x in log)
        return {"count": len(log), "misses": misses, "window": TRUST_WINDOW,
                "trusted": len(log) >= TRUST_WINDOW and misses <= TRUST_MAX_MISS}

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "window": TRUST_WINDOW, "folders": self._log, "skip": self._skip},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
