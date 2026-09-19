#!/usr/bin/env python3
"""model-router 复盘器：任务完成后，用 Jev 对照「需求 vs 产出」做后置检测。

用法：
  python review.py --task "需求原文" --summary "产出摘要" [--diff-file path]
  python review.py --task-file task.md --summary-file summary.md [--dry-run]

输出 JSON：needs_test / test_scope / completeness / risk / has_gap / actions / degraded
退出码：0 成功或降级；3 密钥缺失；4 SDK 错误
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
AUDIT_LOG = Path.home() / ".config" / "model-router" / "audit.log"
DEFAULT_REVIEW = {"needs_test": 0.6, "risk_high": 2.5, "completeness_low": 1.5, "has_gap": 0.8}


def audit(record):
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_arg(value, path):
    if value:
        return value
    if path:
        return Path(path).read_text(encoding="utf-8")
    return None


def decide(a_ans, scope_ans, comp_ans, risk_ans, gap, th):
    actions = []
    if a_ans.noul > th.get("needs_test", 0.6):
        actions.append({"action": f"补测试（范围：{scope_ans.choice}）", "scope": scope_ans.choice})
    if comp_ans.score <= th.get("completeness_low", 1.5) or gap > th.get("has_gap", 0.8):
        actions.append({"action": "产出与需求存在缺口：列出缺口清单，返工或明确告知用户"})
    if risk_ans.score >= th.get("risk_high", 2.5):
        actions.append({"action": "高风险改动：建议人工 review + 完整回归"})
    if not actions:
        actions.append({"action": "收尾：未触发任何检测动作"})
    return actions


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--task", help="需求原文")
    src.add_argument("--task-file", help="需求文件路径")
    ap.add_argument("--summary", help="产出摘要（做了什么、改了哪些文件、结果如何）")
    ap.add_argument("--summary-file", help="产出摘要文件路径")
    ap.add_argument("--diff-file", help="（可选）diff 文件路径，只取前 8000 字符")
    ap.add_argument("--dry-run", action="store_true", help="只打印 state，不调 API")
    a = ap.parse_args()

    task = read_arg(a.task, a.task_file)
    summary = read_arg(a.summary, a.summary_file)
    if not summary:
        print(json.dumps({"error": "需要 --summary 或 --summary-file（产出摘要）"}, ensure_ascii=False))
        return 2
    state = {"task": task, "result_summary": summary}
    if a.diff_file:
        state["diff_excerpt"] = Path(a.diff_file).read_text(encoding="utf-8")[:8000]

    if a.dry_run:
        print(json.dumps({"state": state}, ensure_ascii=False, indent=2))
        return 0

    if not os.environ.get("TYPESAFE_API_KEY"):
        print(json.dumps({"error": "TYPESAFE_API_KEY 未设置；无 key 时由会话模型按本维度自行复盘（见 SKILL.md 无 key 降级模式）"}, ensure_ascii=False))
        return 3
    try:
        from typesafe_sdk import Choice, Noul, Score, TypeSafeClient
    except ImportError:
        print(json.dumps({"error": "缺少依赖：pip install typesafe-sdk"}, ensure_ascii=False))
        return 4

    th = dict(DEFAULT_REVIEW)
    try:
        cfg_path = Path.home() / ".config" / "model-router" / "config.json"
        if cfg_path.exists():
            th.update(json.loads(cfg_path.read_text(encoding="utf-8")).get("routing", {}).get("review_thresholds", {}))
    except Exception:
        pass

    try:
        with TypeSafeClient() as client:
            resp = client.system_one(
                state=state,
                questions={
                    "needs_test": Noul(instructions="这次改动是否需要测试验证才能视为完成？"),
                    "test_scope": Choice(
                        instructions="若需要测试，合适的范围是什么？",
                        criteria={
                            "smoke": "冒烟验证主路径即可",
                            "unit": "针对改动逻辑补单元测试",
                            "regression": "涉及核心链路，需要完整回归",
                        },
                    ),
                    "completeness": Score(
                        instructions="对照需求，这次产出的完成度如何？",
                        criteria=[
                            "有明显缺口，需求未完整实现",
                            "基本完成，存在次要缺口",
                            "完整实现需求且处理了边界情况",
                        ],
                    ),
                    "risk": Score(
                        instructions="这次改动的风险等级有多高？",
                        criteria=[
                            "低：局部改动，易于回滚",
                            "中：影响相关模块，需要基本验证",
                            "高：触碰核心路径或难以回滚",
                        ],
                    ),
                    "has_gap": Noul(instructions="产出与需求之间是否存在明显缺口？"),
                },
            )
        degraded = False
    except Exception as e:
        print(json.dumps({"error": f"TypeSafe 调用失败：{e}", "degraded": True}, ensure_ascii=False))
        return 0

    nt, scope = resp.nouls["needs_test"], resp.choices["test_scope"]
    comp, risk, gap = resp.scores["completeness"], resp.scores["risk"], resp.nouls["has_gap"]
    result = {
        "needs_test": nt.noul,
        "test_scope": scope.choice if nt.noul > 0.5 else None,
        "completeness": comp.score,
        "risk": risk.score,
        "has_gap": gap.noul,
        "actions": decide(nt, scope, comp, risk, gap.noul, th),
        "degraded": degraded,
    }
    audit({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "kind": "review",
        "needs_test": result["needs_test"],
        "completeness": result["completeness"],
        "risk": result["risk"],
        "has_gap": result["has_gap"],
        "actions": [x["action"] for x in result["actions"]],
    })
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
