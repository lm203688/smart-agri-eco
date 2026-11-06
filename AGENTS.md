# AGENTS.md

## 项目约定
- 用户沟通使用简体中文，回复用中文。
- 生产代码仅使用 Python 标准库（stdlib），禁止引入第三方运行时依赖；第三方库（如 MCP SDK）只允许用于测试，且不进入项目代码。
- 动作指令默认 shadow/dry_run，不真实执行；真实执行需人工确认 + 网关下发。技术验证必须诚实标注为「技术验证·非经济可行」。

## 验证命令
- 全量单测：`python -S -P -m unittest discover -s scripts`（用 `-S -P` 避开 pip mcp 遮蔽）
