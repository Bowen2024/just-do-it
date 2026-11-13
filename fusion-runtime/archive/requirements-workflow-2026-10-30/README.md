# 需求程序 Workflow 退役记录

日期：2026-10-30。用户明确选择需求能力只保留 Agent＋MCP，并授权完整退役原程序 Workflow，清理兼容导出、调用方、测试和说明，保留必要历史证据。

## 当前入口

用户指定[需求主文档](../../workflows/requirements/requirements.md)，由当前 Agent 读取 A／按需 R、组织讨论和候选，并按请求调用 [MCP](../../workflows/requirements/cursor_mcp.py)及 file_tools。七项工具、固定成果路径、读取凭证、版本检查、历史、Draft 与只读恢复机制保留。

`run_turn`、`WorkflowDependencies`、`RequirementsTools`、`Progress`、`Action` 等原根包导出已移除；`hardcode/` 不再是可调用模块。此次仅退役需求目录的程序编排，不拆除 fusion-runtime-lab、Buzz 或其他角色的 Runtime。

## 归档内容

[snapshot.tar.gz](snapshot.tar.gz) 是退役前的离线快照，包含 17 个文件。[manifest.json](manifest.json) 记录每个原路径、SHA-256、角色和测试方法数，以及压缩包摘要。归档不在运行路径或测试发现路径内，不解包成另一份现役程序，也不作为兼容回退入口。

| 原位置（相对工作区） | 处理 |
| --- | --- |
| fusion-runtime/workflows/requirements/hardcode/__init__.py | 归档后删除 |
| fusion-runtime/workflows/requirements/hardcode/contracts.py | 归档后删除 |
| fusion-runtime/workflows/requirements/hardcode/tools.py | 归档后删除 |
| fusion-runtime/workflows/requirements/hardcode/workflow.py | 归档后删除 |
| fusion-runtime/tests/test_requirements_workflow_candidate.py | 程序候选链测试退役 |
| fusion-runtime/tests/test_requirements_workflow_contracts.py | 程序结果／状态协议测试退役 |
| fusion-runtime/tests/test_requirements_workflow_dialogue.py | 程序逐轮对话测试退役 |
| fusion-runtime/tests/test_requirements_workflow_lightweight.py | 程序轻量保存编排测试退役 |
| fusion-runtime/tests/test_requirements_workflow_methods.py | 程序方法正文注入测试退役 |
| fusion-runtime/tests/test_requirements_workflow_project_binding.py | 程序映射保存测试退役 |
| fusion-runtime/tests/test_requirements_workflow_research.py | 程序调研回调测试退役 |
| fusion-runtime/tests/test_requirements_workflow_save.py | 程序 PRD 保存编排测试退役 |
| fusion-runtime/tests/fixtures/requirements_case.json | 只被退役测试使用的程序夹具归档 |
| fusion-runtime/tests/test_requirements_workflow_file_tools.py | 原版留快照；8 项文件内核测试保留并改名为 test_requirements_file_tools.py |
| fusion-runtime/workflows/requirements/__init__.py | 原兼容导出快照；现为普通包标记 |
| fusion-runtime/workflows/requirements/README.md | 退役前使用说明快照 |
| fusion-runtime/workflows/requirements/requirements-workflow-plan.md | 退役前建设计划快照 |

## 历史验收与当前验证

八份退役测试共 152 个测试方法，覆盖的是原程序接口及编排。原文件内核 8 项保留；MCP、共用目录、PRD、项目信息与恢复另有 106 项，现行相关回归共 114 项。测试数量下降来自受测接口退役，不代表 266 项全部仍在运行，也不宣称 Agent 已继承程序替身测试证明过的全部行为。

原 S1—S7、149／151／159／195／232／266 等验收记录仍按当时版本保留在[建设计划历史章节](../../workflows/requirements/requirements-workflow-plan.md#7-当前状态与后续建设顺序)和[原始日志目录](../../tests/logs/)中，不改写原日志或为退役重新判为失败。原始源码及测试可通过本快照核对；当前代码不再提供相应程序入口。

退役后的回归及检查结果统一记录在[建设计划第 7.17 节](../../workflows/requirements/requirements-workflow-plan.md#717-需求程序-workflow-完整退役与-agentmcp-保留2026-10-30)。真实 A → R → A → PRD 的剩余业务质量／证据缺口继续见第 7.16 节，不因此次退役自动完成。
