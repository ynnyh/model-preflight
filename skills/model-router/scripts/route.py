#!/usr/bin/env python3
"""model-router 路由器：Jev 判断抽象档位 → 环境映射 → 具体模型 + 思考参数。

用法：
  python route.py --text "用户请求原文" [--env zcode] [--project .] [--dry-run]
  python route.py --state-file state.json [--env zcode]

输出：单行 JSON（tier / model / thinking / confidence / reason / degraded）
退出码：0 成功或降级成功；2 配置缺失；3 密钥缺失；4 SDK 错误
"""
import argparse
import json
import os
import sys
from pathlib import Path

GLOBAL_CONFIG = Path.home() / ".config" / "model-router" / "config.json"

TIER_ORDER = ["no_llm", "fast_small", "balanced", "reasoning"]


def get_api_key():
    """环境变量优先；Windows 上兜底读用户级注册表（免受进程环境未刷新影响）。"""
    key = os.environ.get("TYPESAFE_API_KEY")
    if key:
        return key
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                val, _ = winreg.QueryValueEx(k, "TYPESAFE_API_KEY")
                if val:
                    return val
        except OSError:
            pass
    return None


def load_config(project_dir):
    cfg = json.loads(GLOBAL_CONFIG.read_text(encoding="utf-8"))
    pc = Path(project_dir) / ".typesafe-router.json"
    if pc.exists():
        override = json.loads(pc.read_text(encoding="utf-8"))
        cfg.setdefault("routing", {}).update(override.get("routing", {}))
        cfg.setdefault("environments", {}).update(override.get("environments", {}))
    return cfg


def build_questions():
    from typesafe_sdk import Choice, Noul, Score

    return {
        "model_tier": Choice(
            instructions="处理这个请求应使用哪个模型档位？",
            criteria={
                "no_llm": "纯规则或查表即可完成，无需任何语言模型",
                "fast_small": "简单改写、提取、分类、格式转换，小模型足以保证质量",
                "balanced": "常规生成与理解任务，中等模型可胜任",
                "reasoning": "多步推理、代码、数学、复杂规划，需要最强推理模型",
            },
        ),
        "difficulty": Score(
            instructions="这个任务对语言模型的能力要求有多高？",
            criteria=[
                "直接回答或查找，无推理链条",
                "需要理解上下文并组织较好的回答",
                "需要多步推理或高精度输出，弱模型容易出错",
            ],
        ),
        "thinking": Score(
            instructions="正确处理这个请求需要模型进行多深入的推理？",
            criteria=[
                "直接回答即可，几乎不需要推理（改写、格式转换、简单问答）",
                "需要权衡多个因素组织回答（总结、常规写作、一般分析）",
                "必须逐步推理、验证中间结果才能答对（代码、数学、规划）",
            ],
        ),
        "is_trivial": Noul(instructions="这个请求是否简单到任何模型都能答对？"),
        "needs_review_test": Noul(instructions="这个任务完成后，是否需要测试验证（跑测试或补写测试）才能视为完成？"),
    }


def pick_tier(tier_ans, trivial, routing):
    conf = getattr(tier_ans, "confidence", None)
    th = routing.get("thresholds", {"auto": 0.6, "escalate": 0.3})
    if trivial > routing.get("trivial_noul", 0.95):
        return "fast_small", conf, f"is_trivial={trivial:.2f} 极简单，直接走最快档"
    if conf is not None and conf >= th.get("auto", 0.6):
        return tier_ans.choice, conf, f"confidence={conf:.2f} 达标，按 Jev 选择"
    if conf is not None and conf >= th.get("escalate", 0.3):
        i = TIER_ORDER.index(tier_ans.choice) if tier_ans.choice in TIER_ORDER else TIER_ORDER.index("balanced")
        upgraded = TIER_ORDER[min(i + 1, len(TIER_ORDER) - 1)]
        return upgraded, conf, f"confidence={conf:.2f} 介于两档之间，升一档保守处理"
    fallback = routing.get("fallback_tier", "reasoning")
    return fallback, conf, f"confidence={conf} 过低或缺失，用兜底档"


def resolve_thinking(entry, depth):
    t = entry.get("thinking")
    if t is None:
        return None
    if isinstance(t, dict):
        if depth < 1.5:
            return None
        return t["low"] if depth < 2.5 else t["high"]
    return t


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="用户请求原文")
    src.add_argument("--state-file", help="state JSON 文件路径")
    ap.add_argument("--env", default=os.environ.get("MODEL_ROUTER_ENV", "default"))
    ap.add_argument("--project", default=".")
    ap.add_argument("--dry-run", action="store_true", help="只打印解析后的配置，不调 API")
    ap.add_argument("--human", action="store_true", help="人类可读输出（默认 JSON）")
    a = ap.parse_args()

    if not GLOBAL_CONFIG.exists():
        print(json.dumps({"error": f"全局配置不存在：{GLOBAL_CONFIG}，先运行 setup.py"}, ensure_ascii=False))
        return 2
    cfg = load_config(a.project)
    env = cfg.get("environments", {}).get(a.env)
    if not env:
        print(json.dumps({"error": f"环境 '{a.env}' 尚无模型映射，先运行 setup.py --env {a.env} 补齐"}, ensure_ascii=False))
        return 2

    state = json.loads(Path(a.state_file).read_text(encoding="utf-8")) if a.state_file else {"request": a.text}
    routing = cfg.get("routing", {})

    if a.dry_run:
        print(json.dumps({"env": a.env, "state": state, "routing": routing}, ensure_ascii=False, indent=2))
        return 0

    api_key = get_api_key()
    if not api_key:
        print(json.dumps({"error": "TYPESAFE_API_KEY 未设置，请配置环境变量（见 SKILL.md 密钥一节）"}, ensure_ascii=False))
        return 3
    os.environ["TYPESAFE_API_KEY"] = api_key  # 注册表兜底时同步给 SDK 进程环境
    try:
        from typesafe_sdk import TypeSafeClient
    except ImportError:
        print(json.dumps({"error": "缺少依赖：pip install typesafe-sdk"}, ensure_ascii=False))
        return 4

    try:
        with TypeSafeClient() as client:
            resp = client.system_one(state=state, questions=build_questions())
        tier_ans = resp.choices["model_tier"]
        trivial = resp.nouls["is_trivial"].noul
        depth = resp.scores["thinking"].score
        needs_test = resp.nouls["needs_review_test"].noul
        tier, conf, reason = pick_tier(tier_ans, trivial, routing)
        degraded = False
    except Exception as e:  # 路由器故障不能阻断主流程：降级到兜底档
        fallback = routing.get("fallback_tier", "reasoning")
        tier, conf, reason, depth, needs_test, degraded = fallback, None, f"TypeSafe 调用失败（{e}），降级到兜底档", None, None, True

    tiers = env.get("tiers", env)
    entry = tiers.get(tier)
    if entry is None:  # 该环境没映射这个档位：退到 reasoning，再不行退到任意可用档
        entry = tiers.get("reasoning") or next(iter(tiers.values()), None)
        if entry is None:
            print(json.dumps({"error": f"环境 '{a.env}' 没有任何可用档位映射"}, ensure_ascii=False))
            return 2
        reason += f"（档位 {tier} 未映射，退到 {os.path.basename(str(entry.get('model')))} 所在档）"

    thinking_val = resolve_thinking(entry, depth if depth is not None else 3)
    result = {
        "tier": tier,
        "model": entry.get("model"),
        "thinking": thinking_val,
        "confidence": conf,
        "difficulty": resp.scores["difficulty"].score if not degraded else None,
        "thinking_depth": depth,
        "needs_review_test": bool(needs_test > 0.6) if needs_test is not None else None,
        "reason": reason,
        "degraded": degraded,
    }
    if a.human:
        print(f"建议模型：{result['model']}")
        print(f"思考强度：{thinking_val if thinking_val else '不开思考'}")
        print(f"完成后需测试验证：{'是' if result['needs_review_test'] else ('否' if result['needs_review_test'] is not None else '未知')}")
        if degraded:
            print("注意：路由器降级运行（TypeSafe 调用失败，已用兜底档）")
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
