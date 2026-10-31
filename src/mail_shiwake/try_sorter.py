"""振り分けの頭を、練習用のメールで試す。

使い方:
  python -m mail_shiwake.try_sorter               # 練習用メールで振り分けを試す
  python -m mail_shiwake.try_sorter --selftest    # 公式 README の例（火星）を再現できるか確かめる
  python -m mail_shiwake.try_sorter --dtype fp32  # 精度の高いモデル（約1.1GB）で試す
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .embedder import Embedder
from .sorter import Sorter

SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "sample_mails.json"


def selftest(embedder: Embedder) -> bool:
    """公式 README（onnx-community/embeddinggemma-2-ONNX）の Text search の例を再現する。"""
    query = "Which planet is known as the Red Planet?"
    documents = [
        "Venus is often called Earth's twin because of its similar size and proximity.",
        "Mars, known for its reddish appearance, is often referred to as the Red Planet.",
        "Jupiter, the largest planet in our solar system, has a prominent red spot.",
        "Saturn, famous for its rings, is sometimes mistaken for the Red Planet.",
    ]
    (q,) = embedder.embed([query], prompt="query")
    d = embedder.embed(documents, prompt="document")
    scores = d @ q
    for score, doc in sorted(zip(scores, documents), reverse=True):
        print(f"  {score:.3f}  {doc[:60]}")
    ok = int(scores.argmax()) == 1
    print("README の例（q4 で Mars が 1位・約 0.854）と比べてください:", "1位は Mars ✔" if ok else "1位が Mars ではない ✘")
    return ok


def main() -> int:
    # Windows でパイプやファイルに出すと cp932 になり、✔ などが書けずに止まる。どの OS でも UTF-8 で出す
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="振り分けの頭を試す")
    parser.add_argument("--dtype", default="q4", choices=["q4", "quantized", "fp32"])
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    t0 = time.perf_counter()
    embedder = Embedder(dtype=args.dtype)
    print(f"モデルを読み込みました（{args.dtype}、{time.perf_counter() - t0:.1f} 秒）")

    if args.selftest:
        return 0 if selftest(embedder) else 1

    data = json.loads(SAMPLES.read_text(encoding="utf-8"))
    examples = {f: [(m["subject"], m["body"]) for m in mails] for f, mails in data["examples"].items()}
    sorter = Sorter(embedder)
    t0 = time.perf_counter()
    sorter.learn(examples)
    count = sum(len(v) for v in examples.values())
    print(f"お手本 {count} 通を覚えました（{time.perf_counter() - t0:.1f} 秒）\n")

    correct = 0
    for mail in data["new_mails"]:
        ranked = sorter.suggest(mail["subject"], mail["body"])
        top = ranked[0]
        hit = top.folder == mail["answer"]
        correct += hit
        others = "、".join(f"{r.folder} {r.score:.2f}" for r in ranked[1:])
        print(f"{'✔' if hit else '✘'} {mail['subject']}")
        print(f"    → {top.folder}（近さ {top.score:.2f}、いちばん似ていたお手本「{top.nearest_example}」）")
        print(f"      ほか：{others}" + ("" if hit else f"　正解は {mail['answer']}"))
    print(f"\n正解 {correct} / {len(data['new_mails'])} 通")
    return 0


if __name__ == "__main__":
    sys.exit(main())
