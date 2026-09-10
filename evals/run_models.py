#!/usr/bin/env python3
"""evals.json の試験文を、スキルあり・なしの両方で `claude -p` に流し、回答と費用を保存する。

使い方:
    python3 evals/run_models.py --out /path/to/outdir claude-sonnet-5 claude-haiku-4-5-20251001

出力: <out>/<model>/eval-<id>-<name>/<with_skill|without_skill>/outputs/response.md と timing.json
採点は evals.json の expectations を基準に、別途 Claude に読ませて行う。
"""
import argparse, concurrent.futures, json, os, pathlib, subprocess, time

ROOT = pathlib.Path(__file__).resolve().parent.parent

WITH = """You are executing a test task for a Claude Code skill.

First read the skill file at {skill}/SKILL.md and follow its instructions exactly (including reading the references/ files it points you to for this situation, and running {skill}/scripts/check.py with python3 when the skill says to). The skill's root directory is {skill}. Do not modify any files. Reply with your final answer to the user only, in Japanese.

--- TASK ---
{task}
--- END TASK ---"""

WITHOUT = """Do NOT read any files and do not use any tools; answer using only your own judgment. Reply with your final answer to the user only, in Japanese.

--- TASK ---
{task}
--- END TASK ---"""


def slug(ev):
    return f"eval-{ev['id']}-{ev.get('name', '')}".rstrip("-")


def run(model, ev, cond, out, skill):
    d = out / model / slug(ev) / cond / "outputs"
    d.mkdir(parents=True, exist_ok=True)
    prompt = (WITH if cond == "with_skill" else WITHOUT).format(skill=skill, task=ev["prompt"])
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", model,
           "--allowedTools", "Read,Glob,Grep,Bash(python3:*),Bash(python:*)"]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(out),
                       stdin=subprocess.DEVNULL, timeout=900)
    dt = time.time() - t0
    try:
        j = json.loads(p.stdout)
    except Exception:
        j = {"is_error": True, "result": p.stdout[-2000:], "stderr": p.stderr[-2000:]}
    (d / "response.md").write_text(j.get("result", ""))
    usage = j.get("usage") or {}
    meta = {
        "model": model, "duration_ms": int(dt * 1000), "total_duration_seconds": round(dt, 1),
        "is_error": j.get("is_error"), "total_cost_usd": j.get("total_cost_usd"),
        "num_turns": j.get("num_turns"), "usage": usage,
        "total_tokens": sum(v for k, v in usage.items() if isinstance(v, int) and "tokens" in k),
    }
    (d.parent / "timing.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return f"{model} {slug(ev)} {cond}: err={j.get('is_error')} cost={j.get('total_cost_usd')} {dt:.0f}s"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+", help="claude -p に渡すモデル ID")
    ap.add_argument("--out", required=True, help="結果の出力先ディレクトリ")
    ap.add_argument("--skill", default=str(ROOT), help="スキルのルート（既定: このリポジトリ）")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    evals = json.load(open(ROOT / "evals" / "evals.json"))["evals"]
    out = pathlib.Path(args.out)
    jobs = [(m, ev, c, out, args.skill) for m in args.models for ev in evals for c in ("with_skill", "without_skill")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for line in ex.map(lambda a: run(*a), jobs):
            print(line, flush=True)


if __name__ == "__main__":
    main()
