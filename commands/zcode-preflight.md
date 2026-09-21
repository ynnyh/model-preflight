---
description: 航前检查：判断本任务该用什么模型、思考强度、完成后是否需要测试
---

对任务「$ARGUMENTS」执行 model-router 航前检查，严格按 `~/.zcode/skills/model-router/SKILL.md` 的流程：

1. **补齐**：任务描述缺「任务」或「完成标准」时，按 SKILL.md 的模板一轮问齐（不挤牙膏）；用户说"你定"才按假设判断并列出假设。信息不足不做判断。
2. **判断**：跑 `python ~/.zcode/skills/model-router/scripts/route.py --text "<任务描述>" --env zcode --human`。
3. **告知并停等**：把三行答案（模型/思考强度/是否需测试）告诉我，若非 Jev 判断要标注「（降级判断）」；**本轮随即停住**，等我切换模型和思考强度后回复"开始"，再正式开工。
4. 当前模型已是建议档位时，说明"无需切换"并直接开始。
