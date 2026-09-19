#!/usr/bin/env python3
"""model-router 子任务执行器：按路由建议真正发起 LLM 调用（OpenAI 兼容接口）。

用法：
  python call.py --route --prompt "任务" [--env zcode]      # 先路由再调用（一条命令闭环）
  python call.py --model glm-5.3-flash --prompt "任务"      # 跳过路由直接调用

环境变量：
  TYPESAFE_API_KEY        路由判断用（--route 时需要）
  MODEL_ROUTER_API_BASE   子调用 API 基址，默认 https://open.bigmodel.co/api/paas/v4
  MODEL_ROUTER_API_KEY    子调用密钥；未设置时依次回退 ZHIPU_API_KEY / BIGMODEL_API_KEY
  MODEL_ROUTER_EXTRA_JSON 透传给 API 的额外字段，如 '{"thinking":{"type":"enabled"}}'
                          （各平台思考参数的 API 写法以其官方文档为准）

输出：JSON（model / thinking / content / usage）；退出码 0 成功，2/3/4 同 route.py 约定，5 调用失败。
仅用标准库，无第三方依赖。
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_BASE = "https://open.bigmodel.co/api/paas/v4"
AUDIT_LOG = Path.home() / ".config" / "model-router" / "audit.log"


def audit(record):
    """每次真实调用追加一行 JSONL 到本地账本；审计失败不阻断主任务。"""
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def api_key():
    for name in ("MODEL_ROUTER_API_KEY", "ZHIPU_API_KEY", "BIGMODEL_API_KEY"):
        if os.environ.get(name):
            return os.environ[name], name
    return None, "MODEL_ROUTER_API_KEY / ZHIPU_API_KEY / BIGMODEL_API_KEY"


def route(prompt, env):
    cmd = [sys.executable, str(HERE / "route.py"), "--text", prompt, "--env", env]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        print(p.stdout.strip() or p.stderr.strip(), file=sys.stderr)
        sys.exit(p.returncode)
    return json.loads(p.stdout)


def call(model, prompt, extra):
    base = os.environ.get("MODEL_ROUTER_API_BASE", DEFAULT_BASE).rstrip("/")
    key, key_name = api_key()
    if not key:
        print(json.dumps({"error": f"子调用密钥未设置：{key_name}（见脚本头部说明）"}, ensure_ascii=False))
        sys.exit(3)
    body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if extra:
        body.update(extra)
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(json.dumps({"error": f"API HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}"}, ensure_ascii=False))
        sys.exit(5)
    except Exception as e:
        print(json.dumps({"error": f"调用失败：{e}"}, ensure_ascii=False))
        sys.exit(5)
    return data


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--route", action="store_true", help="先走路由判断再调用")
    src.add_argument("--model", help="直接指定模型 id，跳过路由")
    ap.add_argument("--prompt", required=True, help="子任务内容")
    ap.add_argument("--env", default=os.environ.get("MODEL_ROUTER_ENV", "default"))
    ap.add_argument("--thinking", help="思考档位（覆盖路由结果，如：低）")
    ap.add_argument("--dry-run", action="store_true", help="只打印将使用的 model/thinking，不调用")
    a = ap.parse_args()

    if a.route:
        decision = route(a.prompt, a.env)
    else:
        decision = {"model": a.model, "thinking": None, "tier": "manual", "degraded": False}
    if a.thinking:
        decision["thinking"] = a.thinking

    model, thinking = decision.get("model"), decision.get("thinking")
    if a.dry_run:
        print(json.dumps({"model": model, "thinking": thinking, "tier": decision.get("tier")}, ensure_ascii=False))
        return 0

    extra = {}
    if os.environ.get("MODEL_ROUTER_EXTRA_JSON"):
        extra.update(json.loads(os.environ["MODEL_ROUTER_EXTRA_JSON"]))
    if thinking is not None:
        extra.setdefault("thinking", {"type": "enabled"})  # 缺省仅开思考；具体档位写法按官方文档用 EXTRA_JSON 补

    data = call(model, a.prompt, extra)
    choice = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    audit({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "tier": decision.get("tier"),
        "model": model,
        "thinking": thinking,
        "routed_by": "jev" if a.route else "manual",
        "prompt_chars": len(a.prompt),
        "prompt_head": a.prompt[:200],
        "usage": data.get("usage"),
    })
    print(json.dumps({
        "model": model,
        "thinking": thinking,
        "tier": decision.get("tier"),
        "content": choice,
        "usage": data.get("usage"),
        "routed_by": "jev" if a.route else "manual",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
