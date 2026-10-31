# メール仕分け

お手本を数通見せるだけで、Outlook のメールを話題ごとのフォルダへ振り分ける提案を出すソフトです。
メールの中身はパソコンの外に出しません。

- 件名の言葉が同じかどうかではなく、意味の近さで比べます。件名に「請求」が無い「お支払いのお願い」も、請求書のフォルダを提案できます
- 意味の近さは Google の埋め込みモデル [EmbeddingGemma 2](https://huggingface.co/google/embeddinggemma-2) を、あなたのパソコンの中で動かして計算します
- メールを移すのは、あなたが「移す」を押したときだけです。提案に自信がないメールには「迷っています」と出ます
- 違うフォルダを選び直して移したメールは、すぐに新しいお手本になります

## 動く環境

- Windows のクラシック版 Outlook（新しい Outlook for Windows では確かめていません）
- 振り分けの考え方の部分（振り分けの頭）は Mac・Linux でも動く作りですが、Outlook とつなぐ部分は Windows 専用です
- はじめて起動するときだけ、モデルのファイル（約207MB）を Hugging Face からダウンロードします。そのあとはインターネットにつながっていなくても動きます

## 入れ方

### A. exe で入れる（Windows）

1. [Releases](../../releases) から `mail-shiwake-<版>-windows.zip` をダウンロードして展開します
2. 中の `mail-shiwake.exe` をダブルクリックします

### B. uv で入れる

[uv](https://docs.astral.sh/uv/getting-started/installation/) を入れてから、次のコマンドを実行します。

```
uv tool install git+https://github.com/ssoranaoki/mail-shiwake
mail-shiwake
```

## 使い方

1. Outlook の受信トレイの下に、振り分け先のフォルダ（はじめは「請求書」「注文」「問い合わせ」「お知らせ」）を作ります
2. それぞれのフォルダに、お手本になるメールを何通か入れておきます。フォルダの中のメールがそのままお手本になります
3. メール仕分けを起動すると、受信トレイのメールに、振り分け先の提案が付いて並びます
4. 提案でよければ「移す」を押します。違っていたら、カードの欄でフォルダを選び直してから「移す」を押します

### 設定

はじめて起動すると、`ホームフォルダ\.mail-shiwake\settings.json` ができます。振り分け先のフォルダの名前などはここで変えられます。

```json
{
  "store": null,
  "folder": "",
  "targets": ["請求書", "注文", "問い合わせ", "お知らせ"]
}
```

- `targets`：振り分け先のフォルダ（受信トレイの下）
- `folder`：届いたメールを読むフォルダ（`""` なら受信トレイ）
- `store`：受信トレイの代わりに、名前を指定したデータファイル（.pst など）を読むとき

## メールとプライバシー

- メール仕分けはメールの件名と本文をパソコンの中だけで計算に使います。メールの中身をインターネットへ送ることはありません
- Outlook に書きこむのは、あなたが「移す」を押したときのメールの移動だけです。メールを消す・書きかえる・送ることはしません
- インターネットを使うのは、はじめのモデルのダウンロードだけです。使うモデルの版は固定してあり、2回目からは更新を確かめにも行きません

## しくみを学ぶ

このソフトの作り方と、中で何が起きているかを説明した WEB 教科書を用意しています（準備中）。

## ライセンス

[Apache License 2.0](LICENSE)

Windows 用の exe には、中に入っている部品（onnxruntime・tokenizers・pywebview・Python など）のライセンス文を、`THIRD-PARTY-LICENSES` フォルダに入れています。

モデル EmbeddingGemma 2（[onnx-community/embeddinggemma-2-ONNX](https://huggingface.co/onnx-community/embeddinggemma-2-ONNX)）は、このソフトには含まれていません。はじめて起動したときに Hugging Face からダウンロードします。モデルのライセンスは Apache-2.0 です。
