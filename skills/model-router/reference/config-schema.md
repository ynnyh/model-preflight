# model-router 配置结构

## 全局配置（用户级，所有项目共享）

路径：`~/.config/model-router/config.json`

```json
{
  "version": 1,
  "routing": {
    "trigger_mode": "session",
    "thresholds": { "auto": 0.6, "escalate": 0.3 },
    "trivial_noul": 0.95,
    "fallback_tier": "reasoning"
  },
  "environments": {
    "<环境名>": {
      "updated": "2026-09-19",
      "tiers": {
        "fast_small": { "model": "<模型id>", "thinking": null },
        "balanced":   { "model": "<模型id>", "thinking": { "low": "<低档叫法>", "high": "<高档叫法>" } },
        "reasoning":  { "model": "<模型id>", "thinking": "<固定档位或 low/high 映射>" }
      }
    }
  }
}
```

字段说明：

- `routing`：判断层策略，**环境无关，全环境共享一份**。
  - `trigger_mode`：判断触发频率——`session`（默认，每新会话预判一次，结果兼定本会话
    子任务固定档位）/ `manual`（仅用户要求时判断）/ `auto`（每个子任务派发都判断）。
  - `thresholds.auto`：confidence ≥ 此值按 Jev 选择直接执行。
  - `thresholds.escalate`：confidence 落在 escalate~auto 之间时升一档（往更贵方向）。
  - `trivial_noul`：is_trivial 超过此值直接走 fast_small。
  - `fallback_tier`：confidence 过低或 API 故障时的兜底档。
- `environments.<环境名>.tiers`：映射层，每个 agent 环境一份。
  - `thinking` 三种写法：`null` = 该档模型不支持思考；对象 `{low, high}` = 按思考深度
    （Jev 的 thinking Score，1~3）映射到该环境的档位叫法；字符串 = 固定档位。
- 环境名 = 承载该 skill 的 agent 目录：`zcode` / `codex` / `claude` / 其他。

## 项目级覆盖（可选）

项目根 `.typesafe-router.json`，结构相同，`routing` 与 `environments` 按 key 浅合并进全局配置。
只放**这个项目确实不同**的策略（比如测试项目兜底档用 balanced），没有就不建这个文件。

## 环境映射文件的 onboarding 输入格式

`setup.py --file` 接受的 JSON，两种形态均可：

```json
{ "tiers": { "fast_small": {...}, "balanced": {...}, "reasoning": {...} } }
```
或直接就是 tiers 对象。
