#!/usr/bin/env python3
"""check.py の回帰テスト。

使い方:
    python3 scripts/test_check.py

外部依存なし。失敗すると非 0 で終了する。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check import check, split_sentences  # noqa: E402

FAILURES = []


def expect(cond, msg):
    if not cond:
        FAILURES.append(msg)


def kinds(issues):
    return [k for _, k, _ in issues]


# 「ください」で終わる文は敬体として扱う（常体と誤判定しない）
issues, _, stats = check("資料を確認しました。\n問題なければ承認をお願いします。\n明日までにご確認ください。\n")
expect(stats["文体"] == "敬体", "「ください」が常体扱いされている")
expect("文体" not in kinds(issues), "「ください」で文体混在が誤検出されている")

# 終助詞（か・ね・よ）がついても文体を判定できる
_, _, stats = check("これで良いですか。\n次に進みますね。\n")
expect(stats["文体"] == "敬体", "終助詞つきの敬体を判定できていない")
_, _, stats = check("これで良いか。\n次に進むよ。\n")
expect(stats["文体"] == "常体", "終助詞つきの常体を判定できていない")

# インラインコードや URL を含む普通の文は、箇条書き扱いにせず文体チェックの対象にする
issues, _, stats = check("設定は変更できます。\n詳細は `config.py` を見る。\n次の手順に進みます。\n")
expect(stats["文体"] == "混在", "コード入りの常体文が文体チェックから漏れている")
sents = split_sentences("詳細は https://example.com を見る。\n")
expect(sents and sents[0][2] is False, "URL 入りの文が箇条書き扱いになっている")

# 本物の箇条書きは文体チェックの対象外
_, _, stats = check("手順は次のとおりです。\n- 設定を開く\n- 値を変える\n")
expect(stats["文体"] == "敬体", "箇条書きが文体混在の原因になっている")

# YAML frontmatter は本文として数えない
fm = "---\nname: x\ndescription: とても長い説明文がここに入ります。" + "あ" * 100 + "\n---\n\n本文です。\n"
issues, _, stats = check(fm)
expect(stats["文の数"] == 1, "frontmatter が本文として数えられている")
expect("長さ" not in kinds(issues), "frontmatter の長文が指摘されている")

# コードブロック・見出し・表は対象外
_, _, stats = check("# 見出し\n\n| a | b |\n|---|---|\n\n```\nprint('x')\n```\n\n本文です。\n")
expect(stats["文の数"] == 1, "コードブロック・見出し・表が本文として数えられている")

# 「」内の句点で文を切らない
sents = split_sentences("「はい。わかりました。」と答えた。\n")
expect(len(sents) == 1, "「」内の句点で文が分割されている")

# 冗長表現・AI調・曖昧語・長文を検出する
issues, score, _ = check("この機能を使用することができます。\n")
expect("冗長" in kinds(issues), "冗長表現を検出できていない")
issues, _, _ = check("重要なのは、テストを書くことです。\n")
expect("AI調" in kinds(issues), "AI調を検出できていない")
issues, _, _ = check("ざっくり言うと、だいたい合っています。\n")
expect("曖昧" in kinds(issues), "曖昧語を検出できていない")
issues, _, _ = check("あ" * 81 + "。\n")
expect("長さ" in kinds(issues), "80字超の文を検出できていない")

# 悪い例の行は表現チェックの対象外
issues, _, _ = check("悪い: この機能を使用することができます。\n")
expect("冗長" not in kinds(issues), "「悪い:」の例示行が冗長表現として指摘されている")

# 問題のない文章は 100 点
_, score, _ = check("結論を先に書きます。\n理由は読み手が先に知りたいからです。\n")
expect(score == 100, f"問題のない文章が {score} 点になっている")

# 空入力は落ちない
issues, score, stats = check("")
expect(issues == [] and score == 0, "空入力の扱いが変わっている")

if FAILURES:
    print(f"FAIL {len(FAILURES)} 件:")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("OK")
