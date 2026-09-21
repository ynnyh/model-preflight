# model-preflight

一个极简的 AI 编码助手技能（Agent Skill）：**新任务开工前做一次判断，回答三件事——用什么模型、什么思考强度、完成后是否需要测试**。

基于 [TypeSafe](https://docs.typesafe.ai) 的 System One 模型（Jev）实现：Jev 返回类型化判断与校准概率，而不是生成文本。本 skill 让 agent 在动手前先对齐任务、给出模型建议，把"选错模型返工"的浪费掐在源头。

## 特性

- **一次判断，三个答案**：模型档位 / 思考强度 / 是否需要测试复盘
- **先补齐后判断**：任务描述缺关键信息时不做判断，一轮追问补齐（信息不足的判断只是浪费）
- **停等协议**：给出建议后 agent 停住，由你手动切换模型后说"开始"——绝不中途切换运行中会话的主模型（丢上下文、费 token）
- **跨 agent 通用**：同一份 skill 在 ZCode / Codex / Claude Code 等主流编码 agent 中行为一致
- **无 key 也能跑**：未配置 TypeSafe key 时自动降级为会话模型按文档标准自行判断（明确标注"降级判断"）

## 安装

方式一（skills CLI）：

```bash
npx skills add <your-github-name>/model-preflight --skill model-router --agent <你的agent> --global
```

方式二（手动）：把 `skills/model-router/` 整个目录拷入 agent 的 skills 目录：

| Agent | 目录 |
| --- | --- |
| ZCode | `~/.zcode/skills/model-router/` |
| Codex | `~/.codex/skills/model-router/` |
| Claude Code | `~/.claude/skills/model-router/` |

## 前置条件

- Python 3.8+
- `pip install typesafe-sdk`（判断用）
- `TYPESAFE_API_KEY` 环境变量（在 [console.typesafe.ai](https://console.typesafe.ai/settings/keys) 创建；**可选**，未配置时自动降级为会话模型判断）

## 使用

在任意 agent 会话里直接说任务，按三行格式描述最准：

```
任务：<要做什么，一句话>
完成标准：<怎样算做完>（必填）
背景：<哪个项目/模块>（可省略）
```

agent 会：补齐描述 → 跑判断 → 给出三行建议（如"建议 GLM-5.3 + 最高思考；完成后需要测试验证"）→ 停住等你切换模型 → 你回复"开始"后开工 → 完成后按判断决定是否测试。

## 配置

首次使用某个 agent 环境时，判断结果需要一份「环境映射」（你的模型清单和支持的思考档位）。skill 检测到缺失会引导你补齐，也可手动：

```bash
python <skills目录>/model-router/scripts/setup.py --env zcode --interactive
```

配置存在用户级 `~/.config/model-router/config.json`，所有项目共享，换 agent 只补一份映射。

## 可选增强（默认不用）

`scripts/optional/` 下有两个增强脚本，按需启用：

- `call.py`：子任务按判断结果换模型执行（额外需要执行方的 API key）
- `review.py`：多维复盘（完成度/风险等打分）

## 起手式（可选）：/preflight

把 `commands/` 下对应你 agent 的文件拷贝到位，即可用 `/preflight <任务描述>` 直接触发航前检查：

| Agent | 拷贝源 | 拷贝到 |
| --- | --- | --- |
| ZCode | `commands/zcode-preflight.md` | `~/.zcode/commands/preflight.md` |
| Claude Code | `commands/claude-preflight.md` | `~/.claude/commands/preflight.md` |
| Codex | `commands/codex-preflight.md` | `~/.codex/prompts/preflight.md` |

效果：补齐任务描述 → 一次判断（模型/思考强度/是否需测试）→ 停等你切换模型 → 回复"开始"后开工。新会话生效。

## License

MIT
