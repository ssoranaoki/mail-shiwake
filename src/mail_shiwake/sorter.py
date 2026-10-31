"""お手本メールと比べて、合いそうなフォルダを近さの順に並べる（振り分けの頭）。

メールソフトには触らない。メールの文章とフォルダ名だけを受け取るので、
Outlook でも Thunderbird でも IMAP でも、同じものを使える。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .embedder import Embedder

BODY_CHARS = 1000  # 本文は先頭からこの文字数まで使う（長いメールでも計算を軽くする）


def mail_text(subject: str, body: str) -> str:
    """件名と本文の先頭を、埋め込みにする1つの文章にまとめる。"""
    return f"{subject.strip()}\n{body.strip()[:BODY_CHARS]}"


@dataclass
class Suggestion:
    folder: str
    score: float  # そのフォルダでいちばん似ているお手本とのコサイン類似度
    nearest_example: str  # いちばん似ていたお手本（件名）


class Sorter:
    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self.folders: list[str] = []
        self.example_vectors: list[np.ndarray] = []  # フォルダごとに (お手本の数, 768)
        self.example_subjects: list[list[str]] = []

    def learn(self, examples: dict[str, list[tuple[str, str]]]) -> None:
        """フォルダ名 → [(件名, 本文), ...] のお手本を覚える（数字の列にして持っておく）。"""
        self.folders, self.example_vectors, self.example_subjects = [], [], []
        for folder, mails in examples.items():
            if not mails:
                continue
            vectors = self.embedder.embed([mail_text(s, b) for s, b in mails], prompt="classification")
            self.folders.append(folder)
            self.example_vectors.append(vectors)
            self.example_subjects.append([s for s, _ in mails])

    def suggest(self, subject: str, body: str) -> list[Suggestion]:
        """1通のメールについて、フォルダを近い順に並べて返す。"""
        if not self.folders:
            raise RuntimeError("先に learn() でお手本を覚えてください")
        (vec,) = self.embedder.embed([mail_text(subject, body)], prompt="classification")
        results = []
        for folder, vectors, subjects in zip(self.folders, self.example_vectors, self.example_subjects):
            sims = vectors @ vec  # 長さ1にそろえてあるので、内積 = コサイン類似度
            best = int(np.argmax(sims))
            results.append(Suggestion(folder, float(sims[best]), subjects[best]))
        return sorted(results, key=lambda r: r.score, reverse=True)
