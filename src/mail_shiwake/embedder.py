"""文章を EmbeddingGemma 2 で768個の数字の列（埋め込み）にする。

- モデルは ONNX 版（onnx-community/embeddinggemma-2-ONNX）の文章用の部分だけを使う。
  画像・動画・音声の入力欄には、空の配列を渡す。
- モデルのファイルは最初に1回だけダウンロードし、あとはパソコンの中だけで計算する。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

REPO_ID = "onnx-community/embeddinggemma-2-ONNX"
# 使うモデルの版（コミット）を固定する。版を固定すると、2回目からは手元のファイルだけを使い、
# 起動のたびに Hugging Face へ「新しい版がないか」を確かめに行かない（huggingface_hub の動き）
REVISION = "daa72c51243991dfcaf9f9137d2c573d8f7790c0"  # 2026-10-31 時点の main

# モデルカードの「使い方の指示（接頭辞）」。config_sentence_transformers.json の prompts と同じ文字列
PROMPTS = {
    "classification": "task: classification | query: ",
    "query": "task: search result | query: ",
    "document": "title: none | text: ",
    "similarity": "task: sentence similarity | query: ",
}

# 量子化の種類ごとのファイル名（この3つでは q4 がいちばん軽い。重み 約174MB＋tokenizer.json 約32MB で合計 約207MB）
MODEL_FILES = {
    "q4": "onnx/model_q4.onnx",
    "quantized": "onnx/model_quantized.onnx",
    "fp32": "onnx/model.onnx",
}

FEATURE_DIM = 512  # 画像・動画・音声の入力欄の幅（モデルの入力の形から）

# モデルの置き場所。Windows・Mac・Linux とも、ホームの下の .mail-shiwake/models
# Hugging Face の共有の置き場（キャッシュ）のまま読むと、onnxruntime 1.31 が「重み（.onnx_data）が
# モデルのフォルダの外にある」と読み込みを断った（Windows）。アプリ専用の1つのフォルダへ落として並べる
MODEL_DIR = Path.home() / ".mail-shiwake" / "models" / "embeddinggemma-2-onnx"


class Embedder:
    def __init__(self, dtype: str = "q4", max_tokens: int = 512, local_only: bool = False) -> None:
        if dtype not in MODEL_FILES:
            raise ValueError(f"dtype は {list(MODEL_FILES)} のどれか: {dtype}")
        model_file = MODEL_FILES[dtype]
        # .onnx（骨組み）と .onnx_data（重み）は同じフォルダに置く必要がある
        def fetch(filename: str) -> str:
            return hf_hub_download(
                REPO_ID, filename, revision=REVISION, local_dir=MODEL_DIR, local_files_only=local_only
            )

        model_path = fetch(model_file)
        fetch(model_file + "_data")
        tokenizer_path = fetch("tokenizer.json")

        self.tokenizer = Tokenizer.from_file(tokenizer_path)
        self.tokenizer.enable_truncation(max_length=max_tokens)
        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.input_names = {i.name for i in self.session.get_inputs()}
        self.model_path = Path(model_path)

    def embed(self, texts: list[str], prompt: str = "classification") -> np.ndarray:
        """文章のリストを、長さ1にそろえた (件数, 768) の配列にする。"""
        prefix = PROMPTS[prompt]
        encodings = self.tokenizer.encode_batch([prefix + t for t in texts])
        width = max(len(e.ids) for e in encodings)
        ids = np.zeros((len(texts), width), dtype=np.int64)
        mask = np.zeros((len(texts), width), dtype=np.int64)
        for row, e in enumerate(encodings):
            ids[row, : len(e.ids)] = e.ids
            mask[row, : len(e.ids)] = 1

        feeds = {"input_ids": ids, "attention_mask": mask}
        empty = np.zeros((0, FEATURE_DIM), dtype=np.float32)
        for name in ("image_features", "video_features", "audio_features"):
            if name in self.input_names:
                feeds[name] = empty

        (vectors,) = self.session.run(["sentence_embedding"], feeds)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.maximum(norms, 1e-12)
