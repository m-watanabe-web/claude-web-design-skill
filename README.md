# web-design

Webサイト・LP・UIを「AI感なく、かつ使える形で」作るための Claude Code スキル。

一般的なこの種のガイドと違い、**主張を実測で検証し、効果がなかった項目を削除している**のが特徴。

## 検証で分かったこと

出典（技術系動画2本）で最も強調されていた項目が、測ると**何も禁止していなかった**。

| 主張 | 実測結果 |
| --- | --- |
| 紫グラデーションを禁止すべき | **空振り**（禁止しない対照群でも0件） |
| 絵文字を禁止すべき | **空振り**（対照群でも0件） |
| 角丸カードの均一グリッドを避ける | **有効**（対照群6箇所 → 0） |
| 無意味なアニメーションを避ける | **有効**（対照群3件 → 0） |

さらに、**見た目の禁止リストだけを適用するとUXが対照群より悪化した**（フォーカス表示・
`prefers-reduced-motion`・`<main>` が削られた）。このため手順は「UX要件 → 見た目の禁止」の順。

詳細・限界・生成物は [`references/verification-2026-08.md`](references/verification-2026-08.md)。

## 構成

```
SKILL.md                 手順（Step 0〜6）
ux.md                    UX要件。WCAG 2.2 + WebAIM頻出6カテゴリ。forbid.md より先に読む
forbid.md                見た目の禁止リスト。各項目に検証ステータス付き
design-spec.template.yaml  案件ごとの仕様テンプレ
references/
  measure.py             静的チェック（構造・セマンティクス・見た目）
  contrast.py            コントラスト実測（Chrome headless）
  verification-2026-08.md 検証ログ
  samples/               A=対照 / B=見た目のみ / B2=UX＋見た目（各2題材）
```

## 使い方

Claude Code のユーザースキルとして `~/.claude/skills/web-design/` に置く。
成果物の判定：

```bash
python3 references/measure.py  <file.html>   # UX項目に X が残っていたら未完成
python3 references/contrast.py <file.html>   # 違反 0 件にする
```

## 方法論

新しい禁止項目を足すときは、必ず**対照群（その項目を渡さない条件）を別セッションで生成し、
機械測定で比較する**。主観で判定しない。

そして**測定器自体を疑うこと**。この検証では測定スクリプトに4件のバグが混入し、
うち2件は違反を見逃す偽陰性だった。**「違反0件」と出たら、まず測定器を確認する。**
