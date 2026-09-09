#!/usr/bin/env python3
"""日本語の文章を機械的にチェックし、指摘と点数を出す。

使い方:
    python check.py path/to/text.md
    cat text.md | python check.py

出力: 指摘一覧（行番号つき）と、100点満点の点数。
点数は目安であり、構成や具体性は測れない。文が整っていても構成が悪い文章は
高得点になる。必ず references/rubric.md の採点表と併用し、食い違ったら採点表を信じる。
"""
import re
import sys

LONG_SENTENCE = 80
WARN_SENTENCE = 60

# 冗長表現と置き換え候補
REDUNDANT = {
    "することができ": "できる",
    "することが可能": "できる",
    "を行う": "（動詞にする）",
    "を行い": "（動詞にする）",
    "を実施": "（動詞にする）",
    "ということ": "（削除）",
    "において": "で",
    "における": "の",
    "に関して": "は / を",
    "について": "は / を",
    "のような形で": "のように",
    "と思われ": "（断定する）",
    "と考えられ": "（断定する）",
    "させていただ": "する / します",
    "非常に": "（数値で示す）",
    "とても": "（数値で示す）",
    "大変": "（数値で示す）",
    "基本的に": "（例外を書く）",
    "原則として": "（例外を書く）",
    "まず最初に": "まず",
    "各々それぞれ": "それぞれ",
    "ないわけではない": "（肯定形にする）",
    "ではないかと思": "だと思う / だ",
    "いかがでしたでしょうか": "（削除）",
    "参考になれば幸い": "（削除）",
    "以下に説明します": "（削除）",
    "ご存知の通り": "（削除）",
}

# AI調・翻訳調の兆候
AI_PATTERNS = {
    r"^(まず|次に|最後に|また|さらに)[、,]": "段落頭の接続詞が機械的",
    r"^(重要なのは|注目すべきは|ポイントは)": "「重要なのは」で始めない",
    r"することが重要です[。]?$": "「〜が重要です」で締めない",
    r"を心がけましょう[。]?$": "「〜しましょう」で締めない",
    r"することを確実に": "翻訳調（必ず〜する）",
    r"のうちの一つ": "翻訳調（〜の一つ）",
    r"あなた": "不要な人称代名詞",
    r"私たち": "不要な人称代名詞",
}

# 曖昧語（重なると確信がなく見える）
HEDGES = ["ざっくり", "だいたい", "≒", "イメージです", "イメージとしては", "的な感じ", "かなと思", "かもしれません"]

# 終助詞（か・ね・よ）と句読点は文体判定に影響させない
KEIGO_END = re.compile(r"(です|ます|でした|ました|ません|でしょう|ましょう|ください)(か|ね|よ)?[。！？!?]?$")
JOTAI_END = re.compile(r"(だ|である|だった|であった|ではない|でない|ない|る|た|う|く|い)(か|ね|よ)?[。！？!?]?$")


def split_sentences(text):
    """行番号つきで文を切り出す。コードブロック・表・見出し・URL は除外する。"""
    sentences = []
    in_code = False
    in_frontmatter = False
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        # 先頭の YAML frontmatter（--- で囲まれた部分）は本文ではないので飛ばす
        if lineno == 1 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not stripped:
            continue
        if stripped.startswith(("#", "|", "---")):
            continue
        body = re.sub(r"^([-*+]|\d+\.)\s+", "", stripped)
        # 箇条書き判定は URL・インラインコードを除去する前に行う。
        # 除去後に比べると、コードや URL を含む普通の文まで箇条書き扱いになる
        is_bullet = body != stripped
        body = re.sub(r"https?://\S+", "", body)
        body = re.sub(r"`[^`]*`", "", body)
        # 「」内の句点では文を切らない
        body = re.sub(r"「[^」]*」", lambda m: m.group(0).replace("。", "\u0000"), body)
        for s in re.split(r"(?<=[。！？!?])", body):
            s = s.replace("\u0000", "。")
            s = s.strip()
            if s:
                sentences.append((lineno, s, is_bullet))
    return sentences


def check(text):
    issues = []
    sents = split_sentences(text)
    if not sents:
        return issues, 0, {}

    # 一文の長さ
    lengths = [len(s) for _, s, _ in sents]
    long_count = 0
    for lineno, s, _ in sents:
        n = len(s)
        if n > LONG_SENTENCE:
            long_count += 1
            issues.append((lineno, "長さ", f"{n}字。分割を検討: 「{s[:30]}…」"))
        elif n > WARN_SENTENCE:
            issues.append((lineno, "長さ", f"{n}字（やや長い）: 「{s[:30]}…」"))

    def body_of(s):
        # 「」内の引用と「悪い例」の行は、表現チェックの対象から外す（例示のため）
        if s.startswith(("悪い:", "悪い例", "悪い目次")):
            return ""
        return re.sub(r"「[^」]*」", "", s)

    # 冗長表現
    redundant_count = 0
    for lineno, s, _ in sents:
        for pat, alt in REDUNDANT.items():
            if pat in body_of(s):
                redundant_count += 1
                issues.append((lineno, "冗長", f"「{pat}」→ {alt}"))

    # AI調・翻訳調
    ai_count = 0
    for lineno, s, _ in sents:
        for pat, msg in AI_PATTERNS.items():
            if re.search(pat, body_of(s)):
                ai_count += 1
                issues.append((lineno, "AI調", f"{msg}: 「{s[:30]}…」"))

    # 曖昧語の重なり
    hedge_count = 0
    for lineno, s, _ in sents:
        hits = [h for h in HEDGES if h in body_of(s)]
        if hits:
            hedge_count += len(hits)
            issues.append((lineno, "曖昧", f"「{'」「'.join(hits)}」。正確に書くか、正の定義の場所を示す"))

    # 文体の混在（箇条書きは除外）
    keigo = [(l, s) for l, s, b in sents if not b and KEIGO_END.search(s)]
    jotai = [(l, s) for l, s, b in sents if not b and not KEIGO_END.search(s) and JOTAI_END.search(s)]
    mixed = bool(keigo) and bool(jotai)
    if mixed:
        minority = jotai if len(jotai) < len(keigo) else keigo
        label = "常体" if minority is jotai else "敬体"
        for l, s in minority[:5]:
            issues.append((l, "文体", f"{label}が混在: 「{s[:30]}…」"))

    # 同じ語尾の連続（3回以上）
    tail_repeat = 0
    prev_tail, run = None, 0
    for lineno, s, _ in sents:
        m = re.search(r"(です|ます|ました|でした|である|だ)[。！？!?]?$", s)
        tail = m.group(1) if m else None
        if tail and tail == prev_tail:
            run += 1
            if run == 2:
                tail_repeat += 1
                issues.append((lineno, "単調", f"「〜{tail}」が3文以上連続"))
        else:
            run = 0
        prev_tail = tail

    # 助詞の連続
    for lineno, s, _ in sents:
        if re.search(r"の[^の。、]{1,8}の[^の。、]{1,8}の[^の。、]{1,8}の", s):
            issues.append((lineno, "助詞", "「の」が4連続。語順を変える"))

    # 点数（100点満点、下限0）
    n = len(sents)
    score = 100
    score -= min(30, int(30 * long_count / max(n, 1) * 3))       # 長文の割合
    score -= min(25, redundant_count * 3)                          # 冗長表現
    score -= min(15, ai_count * 3)                                 # AI調
    score -= min(10, max(0, hedge_count - 1) * 3)                  # 曖昧語（2個目から減点）
    score -= 15 if mixed else 0                                    # 文体混在
    score -= min(10, tail_repeat * 3)                              # 単調
    score = max(0, score)

    stats = {
        "文の数": n,
        "平均文字数": round(sum(lengths) / n, 1),
        "80字超の文": long_count,
        "冗長表現": redundant_count,
        "AI調の兆候": ai_count,
        "曖昧語": hedge_count,
        "文体": "混在" if mixed else ("敬体" if keigo else "常体"),
    }
    return issues, score, stats


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    issues, score, stats = check(text)
    print(f"点数: {score} / 100")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print()
    if not issues:
        print("指摘なし")
        return
    print(f"指摘 {len(issues)} 件:")
    for lineno, kind, msg in sorted(issues):
        print(f"  L{lineno:>3} [{kind}] {msg}")


if __name__ == "__main__":
    main()
