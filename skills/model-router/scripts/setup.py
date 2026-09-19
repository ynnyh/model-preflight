#!/usr/bin/env python3
"""model-router onboarding：写入/更新某个 agent 环境的模型映射，并可冒烟测试。

用法：
  python setup.py --env zcode --file mapping.json      # mapping 格式见 reference/config-schema.md
  python setup.py --env zcode --interactive            # 逐档询问
  python setup.py --env zcode --smoke-test             # 需已设置 TYPESAFE_API_KEY
"""
import argparse
import json
import os
import sys
from pathlib import Path

GLOBAL_CONFIG = Path.home() / ".config" / "model-router" / "config.json"
DEFAULT_ROUTING = {
    "trigger_mode": "session",
    "thresholds": {"auto": 0.6, "escalate": 0.3},
    "trivial_noul": 0.95,
    "fallback_tier": "reasoning",
}

ASK_TIERS = ["fast_small", "balanced", "reasoning"]


def read_thinking(prompt):
    raw = input(prompt).strip()
    if not raw or raw.lower() in ("n", "none", "null"):
        return None
    if raw in ("low", "high"):
        return raw
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) == 1:
        return parts[0]
    out = {}
    if len(parts) >= 2:
        out["low"] = parts[0]
        out["high"] = parts[-1]
    return out


def interactive_mapping():
    tiers = {}
    print("逐档配置（思考档位可直接输入该环境的叫法，如：低,最高；不支持思考输入 n）")
    for tier in ASK_TIERS:
        model = input(f"[{tier}] 模型 id：").strip()
        if not model:
            continue
        thinking = read_thinking(f"[{tier}] 思考档位（low,high 或固定值或 n）：")
        tiers[tier] = {"model": model, "thinking": thinking}
    return {"tiers": tiers}


def load_or_init():
    if GLOBAL_CONFIG.exists():
        return json.loads(GLOBAL_CONFIG.read_text(encoding="utf-8"))
    return {"version": 1, "routing": dict(DEFAULT_ROUTING), "environments": {}}


def smoke_test(env_name):
    if not os.environ.get("TYPESAFE_API_KEY"):
        print(json.dumps({"error": "TYPESAFE_API_KEY 未设置，先配置环境变量"}, ensure_ascii=False))
        return 3
    try:
        from typesafe_sdk import Noul, TypeSafeClient
        with TypeSafeClient() as client:
            resp = client.system_one(
                state={"request": "把这句话翻译成英文：你好，世界。"},
                questions={"sanity": Noul(instructions="这个请求是简单的文本任务吗？")},
            )
        ok = resp.nouls["sanity"].noul
        print(json.dumps({"smoke_test": "passed", "sanity_noul": ok, "env": env_name}, ensure_ascii=False))
        return 0
    except Exception as e:
        print(json.dumps({"smoke_test": "failed", "error": str(e)}, ensure_ascii=False))
        return 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True, help="环境名：zcode / codex / claude / ...")
    ap.add_argument("--file", help="映射 JSON 文件（含 tiers 字段或直接是 tiers）")
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--smoke-test", action="store_true", help="只跑连通性冒烟测试")
    a = ap.parse_args()

    if a.smoke_test:
        return smoke_test(a.env)

    if not GLOBAL_CONFIG.exists():
        GLOBAL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    cfg = load_or_init()
    cfg.setdefault("routing", DEFAULT_ROUTING)
    cfg.setdefault("environments", {})

    if a.file:
        mapping = json.loads(Path(a.file).read_text(encoding="utf-8"))
        if "tiers" not in mapping:
            mapping = {"tiers": mapping}
    elif a.interactive:
        mapping = interactive_mapping()
    else:
        print(json.dumps({"error": "需要 --file 或 --interactive 或 --smoke-test"}, ensure_ascii=False))
        return 2

    mapping["updated"] = mapping.get("updated") or __import__("datetime").date.today().isoformat()
    cfg["environments"][a.env] = mapping
    GLOBAL_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "config": str(GLOBAL_CONFIG), "env": a.env,
                      "tiers": sorted(mapping["tiers"].keys())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
