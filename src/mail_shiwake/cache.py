"""一度計算した数字の列（埋め込み）を覚えておき、同じ文章は計算し直さない。

時間がかかるのは、文章を数字の列にするところ（1通 約0.1秒）で、比べるところはお手本が何万通でも一瞬。
お手本を足すたび・メールを移すたびに全部を計算し直さないよう、文章ごとに覚えておく。

覚えるときの名前（キー）は、文章そのものではなく、文章から作ったハッシュ（SHA-256）。
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict

import numpy as np

DIM = 768
BATCH = 32  # 一度にモデルへ渡す数（長いメールが多くても、メモリを使いすぎないように）


class CachedEmbedder:
    def __init__(self, embedder, max_items: int = 5000) -> None:
        self.embedder = embedder
        self.max_items = max_items
        self._vectors: OrderedDict[str, np.ndarray] = OrderedDict()  # 古く使ったものから捨てる
        self.computed = 0  # 実際に計算した数（確かめ用）

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
        for k in keys:
            self._vectors.move_to_end(k)
        out = np.stack([self._vectors[k] for k in keys]) if keys else np.zeros((0, DIM), dtype=np.float32)
        while len(self._vectors) > self.max_items:  # 返す配列を作ってから、古く使ったものを捨てる
            self._vectors.popitem(last=False)
        return out
