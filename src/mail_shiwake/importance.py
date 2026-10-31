"""大事なメールの見分け。旗（フラグ）を付けたメールを「大事」、旗の無いメールを「ふつう」のお手本にする。

振り分けの頭（sorter.py）と同じで、メールソフトには触らない。数字の列（埋め込み）だけを受け取る。
"""

from __future__ import annotations

import numpy as np

MIN_FLAGGED = 3  # 旗付きのお手本がこれより少ないと、見分けない（たまたま近いだけの印を出さないため）


class Importance:
    def __init__(self, important: np.ndarray, normal: np.ndarray) -> None:
        self.important = important  # (旗付きのお手本の数, 768)
        self.normal = normal  # (旗の無いお手本の数, 768)

    @property
    def ready(self) -> bool:
        return len(self.important) >= MIN_FLAGGED and len(self.normal) > 0

    def score(self, vec: np.ndarray) -> float:
        """「大事」のいちばん近いお手本と、「ふつう」のいちばん近いお手本の近さの差。プラスなら大事寄り。"""
        return float(np.max(self.important @ vec) - np.max(self.normal @ vec))
