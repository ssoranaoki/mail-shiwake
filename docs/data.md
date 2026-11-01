# メール仕分けのデータ（--json）

メール仕分けは窓を開かずに提案をデータ（JSON）で出せます。自分で作った別の画面や道具から、提案を読むときに使います。

```
mail-shiwake --json                 # 画面（標準出力）に書く
mail-shiwake --json suggestions.json  # ファイルに書く（exe ではこちら）
```

- 読むだけです。メールを移す・消す・書きかえることはしません
- 窓と同じ設定ファイル（`ホームフォルダ\.mail-shiwake\settings.json`）を使います。`--store`・`--folder`・`--targets` を付けると、設定ファイルより優先します
- データはパソコンの中にだけ書きます。インターネットへは送りません。件名や本文の頭が入るので、ファイルの置き場所に気をつけてください

## いちばん上の項目

| 項目 | 型 | 意味 |
|---|---|---|
| `schema` | 数 | データの形の版。いまは `1`。項目の意味が変わったら上げます |
| `app` | 文字 | いつも `"mail-shiwake"` |
| `version` | 文字または null | メール仕分けの版 |
| `generatedAt` | 文字 | データを作った日時（ISO 8601、UTC） |
| `status` | 文字 | `ok`（提案あり）・`missing_folders`（振り分け先のフォルダが見つからない）・`no_examples`（振り分け先にメールが1通も無い） |
| `nextSteps` | 配列 | 次にできる操作（下の表） |
| `learn` | オブジェクト | お手本を覚えた結果（下の表） |
| `source` | 文字 | 読んだ場所（データファイルの名前、または `受信トレイ`）。`status` が `ok` のときだけ |
| `folderName` | 文字 | 届いたメールを読んだフォルダ。`ok` のときだけ |
| `targets` | 文字の配列 | 振り分け先のフォルダ。`ok` のときだけ |
| `bulkFolder` | 文字または null | 配信メールをまとめて移す先（窓で選んだもの）。`ok` のときだけ |
| `autoMove` | オブジェクト | 「自動で移す」の状態。`enabled`（スイッチがオンか）・`trustedFolders`（信頼のあるフォルダ）。`ok` のときだけ |
| `thresholds` | オブジェクト | 判断に使った線。`unsureGap`（1位と2位の差がこれ未満なら迷う）・`importantGap`（大事の度合いがこれ以上なら大事かも）・`minFlagged`（旗付きのお手本がこれ未満なら大事を見分けない）。`ok` のときだけ |
| `mails` | 配列 | 届いたメール1通ずつ（下の表）。新しい順。`ok` のときだけ |

## learn

| 項目 | 型 | 意味 |
|---|---|---|
| `folders` | 配列 | 振り分け先ごとの `name`（フォルダ）・`count`（お手本の数）・`needed`（お手本があと何通あるとよいか。3通以上あれば 0。0通のフォルダは提案に出ません）・`trust`（信頼。`count` 最近の記録の数・`misses` 外れの数・`window` 見る数・`trusted` 信頼あり。最近の `window` 通で外れが1通以下なら信頼あり） |
| `flagged` | 数 | 「大事」のお手本にした旗付きメールの数 |
| `minFlagged` | 数 | 大事を見分けるのに要る旗付きメールの数 |
| `missing` | 文字の配列 | 見つからなかったフォルダ（`missing_folders` のときだけ） |
| `where` | 文字 | フォルダを作る場所（`missing_folders` のときだけ） |
| `empty` | 真偽 | 振り分け先にメールが1通も無い（`no_examples` のときだけ） |

## mails（1通ずつ）

| 項目 | 型 | 意味 |
|---|---|---|
| `id` | 文字 | Outlook の EntryID。メールを移すと変わります |
| `subject` | 文字 | 件名 |
| `snippet` | 文字 | 本文の頭（URL は省き、60文字まで） |
| `received` | 文字または null | 受け取った日時（ISO 8601） |
| `folder` | 文字 | 提案するフォルダ（いちばん近いお手本のフォルダ） |
| `scores` | 配列 | フォルダごとの `folder` と `score`（いちばん似たお手本との近さ、コサイン類似度）。近い順 |
| `gap` | 数または null | 1位と2位の近さの差。振り分け先が1つなら null |
| `unsure` | 真偽 | `gap` が `unsureGap` 未満（迷っている） |
| `second` | 文字または null | 2番目に近いフォルダ |
| `flagged` | 真偽 | Outlook で旗が付いている |
| `importanceScore` | 数または null | 大事の度合い（「大事」のお手本との近さから「ふつう」のお手本との近さを引いたもの。プラスなら大事寄り）。旗付きのお手本が足りなければ null |
| `important` | 真偽 | 旗が無く、`importanceScore` が `importantGap` 以上（大事かも） |
| `bulk` | 真偽 | 配信メール（メルマガ・宣伝・一斉のお知らせ） |
| `bulkReason` | 文字または null | 配信メールと見分けたヘッダー（`List-Unsubscribe`・`List-Id`・`Precedence`） |
| `group` | 文字 | 窓のどこに出すか。`main`（上の一覧）か `bulk`（配信メールの箱）。旗付きや大事かもの配信メールは `main` |
| `autoMove` | 真偽 | 提案どおりにまとめて移せるメール（`main` で、迷っておらず、大事かもでもない） |
| `autoReady` | 真偽 | 「自動で移す」がオンなら自動で移すメール（`autoMove` で、旗が無く、提案先のフォルダに信頼があり、前に元に戻したメールでない） |

## nextSteps（次にできる操作）

`action` が操作の種類です。ほかの項目は操作ごとに違います。

| action | ほかの項目 | 意味 |
|---|---|---|
| `create_folders` | `folders`・`where` | このフォルダを Outlook に作る |
| `add_examples` | `folders`（・`need`） | 振り分け先のフォルダに、お手本のメールを入れる（`need` 通以上が目安） |
| `choose_targets` | なし | 窓の「振り分け先を選ぶ」で、ほかのフォルダを選ぶ |
| `flag_more` | `have`・`need` | Outlook で大事なメールに旗を付ける（いま `have` 通、`need` 通以上で大事を見分ける） |
| `check_important` | `count` | 大事かもしれないメールを見る |
| `review_unsure` | `count` | 迷っているメールの提案を確かめる |
| `move_many` | `count` | 窓で、迷っていないメールを提案どおりにまとめて移す |
| `move` | `count` | 提案を見て、窓で1通ずつ移す |
| `choose_bulk_folder` | `count` | 配信メールを移す先を、窓で選ぶ |
| `move_bulk` | `count`・`folder` | 窓で配信メールをまとめて移す |
