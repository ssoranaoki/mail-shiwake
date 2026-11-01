# メール仕分け

お手本を数通見せるだけで、Outlook のメールを話題ごとのフォルダへ振り分ける提案を出すソフトです。
メールの中身はパソコンの外に出しません。

- 件名の言葉が同じかどうかではなく、意味の近さで比べます。件名に「請求」が無い「お支払いのお願い」も、請求書のフォルダを提案できます
- 意味の近さは Google の埋め込みモデル [EmbeddingGemma 2](https://huggingface.co/google/embeddinggemma-2) を、あなたのパソコンの中で動かして計算します
- メールを移すのは、あなたが「移す」を押したときだけです。提案に自信がないメールには「迷っています」と出ます
- 「自動で移す」をオンにすると、提案がよく当たっているフォルダ（最近の20通で選び直しが1通以下）への、迷っていない提案だけを、起動したときと、新しいメールが届いたとき（窓を開いている間。Outlook の新着の知らせですぐ気づき、知らせが届かないアカウントでも1分ごとに見ます）に自動で移します。最初はオフです。自動で移したメールは「元に戻す」で戻せます
- 違うフォルダを選び直して移したメールは、すぐに新しいお手本になります

## 動く環境

- 連携できるメールソフトは、Windows のクラシック版 Outlook だけです
- 新しい Outlook for Windows、Mac や Linux のメールソフトには、まだ対応していません（振り分けの考え方の部分は OS に寄らない作りにしてあり、ほかのメールソフトとの窓口を足せば広げられます）
- はじめて起動するときだけ、モデルのファイル（約207MB）を Hugging Face からダウンロードします。そのあとはインターネットにつながっていなくても動きます

## 入れ方

### A. exe で入れる（Windows）

1. [Releases](../../releases) から `mail-shiwake-<版>-windows.zip` をダウンロードします
2. 展開する前に、zip を右クリック →「プロパティ」→「全般」の下の「許可する」にチェックを付けて「OK」を押します
3. zip を展開し、中の `mail-shiwake.exe` をダブルクリックします

いまの exe には電子署名（コード署名）が付いていないため、2 をしないと、起動するときに「発行元：不明」の警告が出ます。「Windows によって PC が保護されました」と出たときは、「詳細情報」を押してから「実行」を押します。署名は、オープンソース向けの無料の署名（SignPath Foundation）に申し込んで、付ける予定です。

### B. uv で入れる

[uv](https://docs.astral.sh/uv/getting-started/installation/) を入れてから、次のコマンドを実行します。

```
uv tool install git+https://github.com/ssoranaoki/mail-shiwake
mail-shiwake
```

## 使い方

1. Outlook の受信トレイの下に、振り分け先のフォルダ（はじめは「請求書」「注文」「問い合わせ」「お知らせ」）を作ります。IMAP のアカウントなどで受信トレイの下に作れないときは、受信トレイと同じ並びに作ります（受信トレイの下に無ければ、同じ並びも探します）
2. それぞれのフォルダに、お手本になるメールを何通か入れておきます。フォルダの中のメールがそのままお手本になります
3. メール仕分けを起動すると、受信トレイのメールに、振り分け先の提案が付いて並びます
4. 提案でよければ「移す」を押します。違っていたら、カードの欄でフォルダを選び直してから「移す」を押します
5. 迷っていないメールは、一覧の上のボタンでまとめて移せます。迷っているメールと「★ 大事かも」のメールは、1通ずつ確かめて移します

上のバーの「読み直す」で間隔（5分〜60分ごと）を選ぶと、窓を開いている間、その間隔で「お手本を覚える」を繰り返し、新しく届いたメールにも提案を付けます。操作の途中なら、その回は飛ばします。

どれにも当てはまらないメールのために、「その他」のようなフォルダも作って振り分け先に入れておくと、無理な提案が減ります。お手本が少ないフォルダには、左の一覧に「あと N 通」と出ます。

### 設定

はじめて起動すると、`ホームフォルダ\.mail-shiwake\settings.json` ができます。振り分け先のフォルダの名前などはここで変えられます。

```json
{
  "store": null,
  "folder": "",
  "targets": ["請求書", "注文", "問い合わせ", "お知らせ"]
}
```

- `targets`：振り分け先のフォルダ（受信トレイの下、または受信トレイと同じ並び）
- `folder`：届いたメールを読むフォルダ（`""` なら受信トレイ）
- `store`：受信トレイの代わりに、名前を指定したデータファイル（.pst など）を読むとき

## 提案をデータで受け取る

`mail-shiwake --json` で、窓を開かずに提案を JSON で受け取れます。自分で作った別の画面や道具から使うときのためのものです。読むだけで、メールは移しません。項目の意味は [docs/data.md](docs/data.md) にあります。

## メールとプライバシー

- メール仕分けはメールの件名と本文をパソコンの中だけで計算に使います。メールの中身をインターネットへ送ることはありません
- Outlook に書きこむのは、メールの移動だけです。移すのは、あなたが「移す」を押したときと、「自動で移す」をオンにしたときです。メールを消す・書きかえる・送ることはしません
- フォルダごとの当たり・外れの記録（件名や本文は入れません）を `ホームフォルダ\.mail-shiwake\trust.json` に保存します
- インターネットを使うのは、はじめのモデルのダウンロードだけです。使うモデルの版は固定してあり、2回目からは更新を確かめにも行きません
- 計算を速くするため、メールから作った数字の列（埋め込み）を `ホームフォルダ\.mail-shiwake\vectors` に保存します。件名や本文は保存しません。消しても、次に起動したときに計算し直すだけです

## 削除のしかた

1. メール仕分けの窓を閉じます
2. exe で入れたときは、展開したフォルダを消します。uv で入れたときは `uv tool uninstall mail-shiwake` を実行します
3. 設定・モデル・計算の記録を消すときは、`ホームフォルダ\.mail-shiwake` フォルダを消します

Outlook のメールとフォルダは、消しても変わりません。

## Code signing policy

Windows 用の exe には SignPath Foundation の無料のコード署名を付けるため、申し込みをしています。署名を付けた版から、次のとおりになります。

- Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/)
- exe はこのリポジトリのソースから GitHub Actions で自動的に作ります（[.github/workflows/build-windows.yml](.github/workflows/build-windows.yml)）
- Committers and reviewers: [ssoranaoki](https://github.com/ssoranaoki)
- Approvers: [ssoranaoki](https://github.com/ssoranaoki)
- Privacy policy: This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it. ただし、はじめて起動するときだけ、モデルのファイルを Hugging Face からダウンロードします（メールの内容は送りません）。くわしくは「メールとプライバシー」を見てください

## ライセンス

[Apache License 2.0](LICENSE)

Windows 用の exe には、中に入っている部品（onnxruntime・tokenizers・pywebview・Python など）のライセンス文を、`THIRD-PARTY-LICENSES` フォルダに入れています。

モデル EmbeddingGemma 2（[onnx-community/embeddinggemma-2-ONNX](https://huggingface.co/onnx-community/embeddinggemma-2-ONNX)）は、このソフトには含まれていません。はじめて起動したときに Hugging Face からダウンロードします。モデルのライセンスは Apache-2.0 です。
