# Solution Designer 工程方案能力

更新日期：2026-11-02。角色规则、文件操作约定、本地方法入口、工程模板和来源记录已建立。步骤 5 的独立 stdio 方案文件工具、Draft 保存内核与 Cursor JSON 配置辅助已通过 Honey 独立代码验收；步骤 6 文档校准（6-A 角色规则、6-B README／模板口径）与步骤 7（净化环境隔离运行、Lite／Standard 走查）均已通过 Honey 独立验收（REVIEW_ACCEPTED），7-A 隔离不变量已固化为正式回归测试 `test_solution_isolation.py`。Codex 当前会话真实读取／检查已验证；真实受信确认来源和业务项目保存完整链仍未验证（步骤 8），不将离线夹具等同于正式链路通过。

## 从哪里开始

日常方案工作以 [solution-design.md](solution-design.md) 为唯一角色入口。用户可说明项目、目标和范围，例如“使用方案角色，基于这个项目的 PRD 讨论工程实现”或“继续已有方案，只调整失败恢复部分”。Agent 按主文档读取实际适用材料，不要求用户逐项提供方法路径或内部版本字段。

操作业务项目文件时读取 [agent-file-workflow.md](agent-file-workflow.md)。讨论如何建设这项能力、继续实施或核对进度时读取[建设方案](solution-designer-construction-plan.md)的适用部分；日常设计无需每轮读取完整建设记录。

## 当前文件与维护归属

| 文件／入口 | 用途与归属 |
| --- | --- |
| [solution-design.md](solution-design.md) | 角色、输入分流、设计推进、证据、交付和停止规则 |
| [agent-file-workflow.md](agent-file-workflow.md) | 读取基线、保存、检查、历史、冲突和失败恢复的操作约定 |
| [solution-tools-implementation-plan.md](solution-tools-implementation-plan.md) | 工具契约、参数、返回、准确修改范围、5A／5B／5C 与目标测试命令；步骤 5 按本文实施 |
| [solution-tools-test-checklist.md](solution-tools-test-checklist.md) | Fizz 自验与 Honey 独立验收共用的 26 项详细清单；含临时夹具、操作、返回和文件判定 |
| `mcp_server.py` | 独立 stdio MCP；默认开放读取和检查，`--allow-save` 时开放 Draft 保存 |
| `shared_loader.py` | 受控加载固定 requirements foundation，校验来源摘要、配置、锁和双方法入口 |
| `file_tools/dependencies.py` | 项目绑定、保护依赖集合、规范文件集、登记／快照闭包和事务状态 |
| `file_tools/solution.py` | 上下文读取、方案结构检查、read_id、双锁保存、历史、写后复读和结果分类 |
| `configure_client.py` | 只处理 Cursor JSON：预览、应用、备份和精确回退；不自动搜索真实客户端配置 |
| [templates/tech-spec-template.md](templates/tech-spec-template.md) | 本角色唯一维护的工程模板，Lite／Standard／AI 共用 |
| methods/develop-helper | 直接软链指向原始 Develop_Helper；方法正文只在上游维护 |
| [templates/research-template.md](templates/research-template.md) | 经本地 methods 入口读取同一份上游调研模板，不维护副本 |
| [SOURCES.json](SOURCES.json) | 模板复制摘要、软链目标、来源内容基线与计划共享依赖 |
| [solution-designer-construction-plan.md](solution-designer-construction-plan.md) | 分步建设顺序、退出条件与各步骤状态、证据（含步骤 1—4 记录及步骤 5—8 状态） |

七层方法从本地入口读取[原文](methods/develop-helper/harness-core/skills/solution-design/SKILL.md)，处理逻辑按需读取[接口体验分析](methods/develop-helper/harness-core/skills/solution-design/references/interface-experience-review.md)，产品参考按需读取 [R](methods/develop-helper/harness-core/skills/sdd-product-design/phase-R.md)。保留上游相邻文件的相对关系不表示加载其 Router、整套流程或自动派发；独立角色适配以主文档为准。

## 工程模板怎样使用

模板从既有融合工程模板逐字节复制，当前未改章节或业务内容；本地文件成为本角色维护位置，旧模板继续服务其他使用方。来源路径仅用于追溯，不是正常设计的必读入口。以后修改本地模板需记录原因和实际摘要，不自动覆盖或同步旧模板／上游。

统一使用 0—12 编号，七层正文保持 1—7，覆盖表保持 REQ、AC、实现设计／API、成功路径、失败路径、验证方式、状态七列。Lite 简写但保留结构并解释不适用，Standard 展开系统契约，AI 增加适用的模型、工具、评估与回退设计。具体内容和覆盖含义按主文档，不以模板填满代替方案正确。

模板顶部 YAML 仅展示工具元数据格式，候选正文不提交该部分；状态、输入摘要与确认引用由保存内核统一渲染。模板中的 Main 用途建议在独立使用时不构成 Main 前置条件。设计取舍与正式确认、PRD 确认门槛与方案 Draft 未决项分别处理。

## 当前可以使用到什么程度

可以显式加载角色并讨论或审阅材料、形成对话中的候选；步骤 5 后可在隔离或已正确安装的 foundation 上通过独立 stdio 服务读取、检查并保存 `docs/tech-spec.md` Draft。保存成功只表示目标文件、历史和写后核对完成，不是方案正式确认、成果登记、交接或下游启动；真实业务项目仍需步骤 8 的受信确认与客户端链路。

工程保存需要当前 PRD 有有效的“形成技术方案”用途确认及实际开放的受控方案工具。文档存在、用户对某项设计表示同意或模板写着 Draft，都不能代替正式确认核验。离线测试中的确认记录是明确标注的临时夹具，不代表真实用户确认。

显式目录模式下，每次调用以完整 `project_path` 复用项目 `project.json` 的持久身份，旧根或旧映射不限制位置；缺省及 `legacy_rooted` 仍保留旧根直接子目录规则。方案与需求、UI 使用同一共享绑定，读取引用同时受路径、目录身份和运行基线约束。

## 运行依赖与下一步

首版显式复用兄弟 requirements 的项目定位、读取、锁、PRD 检查及只读记录校验，以其目录作为共享 foundation；方法和工程模板归本目录。受控加载使用专用模块别名，只加载固定十项文件（包入口加九个模块），不从业务目录、旧 scripts 或当前工作目录补齐导入。服务不依赖需求对话或需求服务在线，但不能脱离受信 requirements 目录独立分发。

**当前依赖边界（据步骤 7 后实际实现核对）**

- **可独立启动，但运行时复用 requirements 共享基础**：方案服务可单独以 `mcp_server.py --foundation <requirements>` 启动；运行时通过受控别名加载 requirements 目录的固定十个共享模块，以及其 `config/local.json`、`upstream-lock.json`，不重复实现项目初始化、PRD 检查、公共锁与只读记录校验。
- **不要求需求 Agent／需求 MCP 在线，但不能只复制本目录分发**：方案直接导入本地代码，无网络或需求服务依赖；但仅复制 `Solution Designer/` 而没有受信 requirements foundation（九模块＋配置＋锁＋双方法软链）会在启动时具体失败，不能脱离该目录独立运行或分发。
- **Develop_Helper 是方案方法上游，不依赖旧 buzz-develop-helper 运行代码**：设计方法经 `methods/develop-helper` 软链读取原始 Develop_Helper；隔离目标是运行代码不导入、不执行旧 buzz-develop-helper（`docs/decisions.md` 中同名确认区段标记只沿用其文本格式，属于被解析的数据，不是运行依赖）。
- **共享抽取是后续方向，本次不迁移**：通用基础将来可抽到独立共享目录；本版只如实记录这层耦合与方向，不实施抽取或目录迁移。

只读启动：

```sh
python3 -B mcp_server.py --foundation /absolute/fusion-runtime/workflows/requirements
```

保存启动追加 `--allow-save`；工具数相应为 2 或 3。Cursor 配置先预览，应用必须携带预览返回的配置摘要：

```sh
python3 -B configure_client.py --client cursor --config-path /absolute/.cursor/mcp.json \
  --foundation /absolute/fusion-runtime/workflows/requirements --python-executable "$(command -v python3)"
```

首版配置辅助只支持 Cursor JSON；Codex 已采用原生 CLI 注册 TOML 配置并在用户重启后完成真实读取／检查。服务代码共用，客户端配置方式分别处理，其他客户端仍按实际格式核对。

2026-11-02 步骤 8 已按用户选择准备真实 requirements/config/local.json，保留旧本机路径与项目映射，250 项上游基线校验通过；Codex 原生 mcp add 已注册 solution-designer，已用真实目录完成直接 stdio 读取／检查。用户已重启，当前 Codex 会话已发现三工具并成功读取／检查真实项目；真实确认与保存完整链仍待验，详情见[Codex 接入记录](step8-codex-verification.md)。步骤 5／7 的临时测试证据范围仍按原记录，不改写成真实接入通过。

步骤 5 自验命令从工作区根目录执行：

```sh
python3 -B -m unittest discover -s fusion-runtime/tests -p 'test_solution_*.py'
```

本次聚合结果为 60 tests、exit 0；分组为 context 22、inspect 8、save 17、client/stdio 10、isolation 3；另复用回归 requirements 137 项 exit 0。该证据只覆盖标准库实现、临时文件副作用、独立新进程 stdio 与隔离不变量，不覆盖真实 Cursor UI、模型效果、真实受信写入口或业务数据。

步骤 3 的输入、真实选择、候选修订和未验范围见建设计划第 17.4 节；步骤 5—7 的实现与验收证据见第 17.8 节，均已获 Honey REVIEW_ACCEPTED。[Fizz](../../../fusion-design/agent-rule/FIZZ_DEVELOPMENT_RUNBOOK.md)／[Honey](../../../fusion-design/agent-rule/HONEY_VERIFICATION_RUNBOOK.md) 手册保持角色入口。步骤 8 进行中：Codex 重启后已发现三工具，当前会话真实读取／检查成功；PRD 缺用途确认，尚未保存业务方案。后续按[接入记录](step8-codex-verification.md)继续，不用夹具冒充真实链。
