# web-design

Webサイト・LP・UIを「AI感なく、かつ使える形で」作るための Claude Code スキル。

この種のガイドは通常「こうすると良くなる」の列挙で終わる。本スキルは**各項目を対照実験にかけ、
効果が確認できなかったものを削除している**。残っているのは測って差が出た項目だけ。

## 検証で否定された通説

「AIっぽさ」の代表例としてよく挙げられる項目を、禁止した条件／しない条件で比較した。

| よく言われる対策 | 実測結果 |
| --- | --- |
| 紫系グラデーションを避ける | **空振り** — 禁止しない対照群でも0件。現行モデルはそもそも出さない |
| 絵文字をUIに入れない | **空振り** — 対照群でも0件 |
| 角丸カードの均一グリッドを避ける | **有効** — 対照群6箇所・3列 → 0 |
| 無意味なアニメーションを入れない | **有効** — 対照群3件 → 0 |
| 出力の冗長さを抑える | **有効** — 対照群は7倍のサイズ（44KB vs 6KB） |

色の癖は既に解消しており、**現在残っているのは構造の癖**（均一なカードグリッド）だった。

## 見た目だけ直すとUXが壊れる

さらに重要な結果として、**見た目の禁止リストだけを適用すると、何も指示しない対照群より
UXが悪化した。**

| | 対照群 | 見た目リストのみ | UX＋見た目 |
| --- | --- | --- | --- |
| コントラスト違反 | 0 | **4**（最悪 2.71:1） | **0**（最悪 6.15:1） |
| `:focus` | あり | **なし** | あり |
| `prefers-reduced-motion` | あり | **なし** | あり |
| `<main>` | あり | **なし** | あり |

「角丸を使うな」「アニメを入れるな」「短くしろ」と縛った結果、フォーカス表示と
`prefers-reduced-motion` が削られた。対照群は指示なしでそれらを実装していた。

このため手順は **UX要件（`ux.md`）→ 見た目の禁止（`forbid.md`）** の順に固定してある。
使えないものを綺麗にしても意味がないため。

## 構成

```
SKILL.md                    手順（Step 0〜6）
ux.md                       UX要件。WCAG 2.2 + WebAIM頻出6カテゴリ。先に読む
forbid.md                   見た目の禁止リスト。各項目に検証ステータス付き
design-spec.template.yaml   案件ごとの仕様テンプレ
references/
  measure.py                静的チェック（構造・セマンティクス・見た目）
  contrast.py               コントラスト実測（Chrome headless）
  verification-2026-08.md   検証ログ（方法・結果・限界）
  samples/                  A=対照 / B=見た目のみ / B2=UX＋見た目（各2題材）
```

## 使い方

Claude Code のユーザースキルとして `~/.claude/skills/web-design/` に置く。成果物の判定：

```bash
python3 references/measure.py  <file.html>   # UX項目に X が残っていたら未完成
python3 references/contrast.py <file.html>   # 違反 0 件にする
```

## 方法論

新しい禁止項目を足すときは、**対照群（その項目を渡さない条件）を別セッションで生成し、
機械測定で比較する**。主観で判定しない。生成した本人は必ずバイアスを持つため。

そして**測定器自体を疑うこと**。この検証では測定スクリプトに4件のバグが混入し、うち2件は
違反を見逃す偽陰性だった（Chrome が `color-mix()` を `color(srgb ...)` で返すため、該当要素が
黙って検査対象外になっていた等）。**「違反0件」と出たら、まず測定器を確認する。**

## 参考文献

**手法の下敷き**

- Adam Wathan, Steve Schoger『Refactoring UI』 https://refactoringui.com/
  — 白黒で設計してから色を足す、間隔・活字・色を制約されたスケールに載せる、余白を多めに取ってから削る。
  本スキルの Step 1・2 はこの考え方に沿う。デザイン教育を受けていない実装者向けという立ち位置も近い。

**現象の記録**

- Kyle Chayka「The generic style of AI web design」 https://kylechayka.substack.com/p/the-generic-style-of-ai-web-design
- Nielsen Norman Group「State of UX 2026」 https://www.nngroup.com/articles/state-of-ux-2026/
  — UIは重要だが差別化要因ではなくなっていく、という指摘。見た目のAI感を消す作業に長期の優位性は期待しない方がよい。
- Adobe調査（2025）— AI生成インターフェースの42%超が類似したナビゲーション構造を持つ

**UX・アクセシビリティの根拠**

- WCAG 2.2 https://www.w3.org/TR/WCAG22/
- WebAIM Million https://webaim.org/projects/million/
  — 全エラーの96%が7年連続で同じ6カテゴリ（低コントラスト / alt欠落 / ラベル欠落 / 空リンク / lang欠落 / 空ボタン）
- 「Can Generative AI Create Accessible Websites?」ACM SIGACCESS 第27回
  https://dl.acm.org/doi/full/10.1145/3663547.3759755
  — AI生成6サイトから308件のエラー、うちWCAG違反47.1%
- Baymard Institute https://baymard.com/ — 42,000時間の実測に基づくガイドライン
- GOV.UK Design System https://design-system.service.gov.uk/

**参照するデザインシステム**（Step 3 で名指しする先）

デジタル庁 https://www.digital.go.jp/policies/servicedesign/designsystem ／
IBM Carbon https://carbondesignsystem.com/ ／
Apple HIG https://developer.apple.com/design/human-interface-guidelines/ ／
Material Design 3 https://m3.material.io/

## ライセンスと注意

`references/samples/` の内容はすべて架空のサンプルデータ。実在の人物・企業・案件とは関係ない。

検証は各条件 n=1、単一モデル（Claude Opus 5）、題材2種という限られた条件で行っている。
一般化する前に `references/verification-2026-08.md` の「限界」を必ず読むこと。
