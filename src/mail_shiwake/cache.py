"""一度計算した数字の列（埋め込み）を覚えておき、同じ文章は計算し直さない。

時間がかかるのは、文章を数字の列にするところ（1通 約0.1秒）で、比べるところはお手本が何万通でも一瞬。
お手本を足すたび・メールを移すたびに全部を計算し直さないよう、文章ごとに覚えておく。

覚えるときの名前（キー）は、文章そのものではなく、文章から作ったハッシュ（SHA-256）。
path を渡すと、覚えた数字の列をパソコンの中のファイルにも残し、次に起動したときも使う（文章は残さない）。
"""

from __future__ import annotations

import hashlib
import os
from collections import OrderedDict
from pathlib import Path

import numpy as np

DIM = 768
BATCH = 32  # 一度にモデルへ渡す数（長いメールが多くても、メモリを使いすぎないように）


class CachedEmbedder:
    def __init__(self, embedder, max_items: int = 5000, path: Path | None = None) -> None:
        self.embedder = embedder
        self.max_items = max_items
        self.path = path
        self._vectors: OrderedDict[str, np.ndarray] = OrderedDict()  # 古く使ったものから捨てる
        self.computed = 0  # 実際に計算した数（確かめ用）
        self.loaded = 0  # ファイルから読んだ数
        self._dirty = False
        if path is not None and path.exists():
            try:
                with np.load(path, allow_pickle=False) as f:
                    for k, v in zip(f["keys"].tolist(), f["vectors"]):
                        self._vectors[k] = v
                self.loaded = len(self._vectors)
            except Exception:  # 壊れたファイルなどは使わず、最初から計算する
                self._vectors.clear()

    def save(self) -> None:
        """覚えた数字の列をファイルに残す（新しく計算したものがあるときだけ）。途中で止まっても前のファイルは残る。"""
        if self.path is None or not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.stem + ".tmp.npz")
        keys = list(self._vectors)
        vectors = np.stack(list(self._vectors.values())) if keys else np.zeros((0, DIM), dtype=np.float32)
        np.savez(tmp, keys=np.array(keys, dtype="<U64"), vectors=vectors.astype(np.float32))
        os.replace(tmp, self.path)
        self._dirty = False

    @staticmethod
    def key(text: str, prompt: str) -> str:
        return hashlib.sha256(f"{prompt}\0{text}".encode("utf-8")).hexdigest()

    def embed(self, texts: list[str], prompt: str = "classification") -> np.ndarray:
        """embedder.embed と同じ形で返す。まだ覚えていない文章だけを計算する。"""
        keys = [self.key(t, prompt) for t in texts]
        todo = list(dict.fromkeys(k for k in keys if k not in self._vectors))  # 同じ文章は1回だけ
        if todo:
            text_of = dict(zip(keys, texts))
            for i in range(0, len(todo), BATCH):
                chunk = todo[i:i + BATCH]
                vecs = self.embedder.embed([text_of[k] for k in chunk], prompt=prompt)
                for k, v in zip(chunk, vecs):
                    self._vectors[k] = v.astype(np.float32)
                self.computed += len(chunk)
            self._dirty = True
        for k in keys:
            self._vectors.move_to_end(k)
        out = np.stack([self._vectors[k] for k in keys]) if keys else np.zeros((0, DIM), dtype=np.float32)
        while len(self._vectors) > self.max_items:  # 返す配列を作ってから、古く使ったものを捨てる
            self._vectors.popitem(last=False)
        return out
