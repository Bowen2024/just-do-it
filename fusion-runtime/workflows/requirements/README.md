# 需求角色与 MCP 文件工具

这里归集项目目录绑定／检查／初始化、需求读取、Draft 保存、版本校验、历史保留和复读代码。文件工具和 MCP 入口使用 Python 标准库。2026-10-30 已完成需求运行依赖本地化步骤 3—9 的代码与测试；真实 Cursor 配置切换属于步骤 10，尚未在本轮换中执行。用户明确只保留 Agent＋MCP，原程序 Workflow、兼容导出及专用测试已完整退役，见[退役归档](../../archive/requirements-workflow-2026-10-30/README.md)。

需求角色与 A／R 采用方式以 [requirements.md 主文档](requirements.md) 为准；本文说明代码、工具连接与验证边界，不另维护需求规则。当前 Agent 实际读取主文档及适用方法、组织讨论并按需调用 MCP／file_tools。需求目录不再提供 run_turn、AgentRunner 编排或原程序结果协议入口。旧 [角色路径](../../../buzz-develop-helper/roles/requirements.md) 现为兼容指针，[角色索引](../../../buzz-develop-helper/roles/README.md) 直接指向主文档。

## 目录与职责

| 文件 | 职责 |
| --- | --- |
| `requirements.md` | 需求主文档，统一维护角色、方法引用、工作顺序、工具使用和交付边界 |
| `file_tools/project_binding.py` | 统一显式／旧模式绑定、持久身份、目录与父路径重验、保护目录及运行基线指纹 |
| `file_tools/project_init.py` | 解析项目编号与目录映射，预览／创建项目，初始化已有空目录，检查项目身份 |
| `file_tools/requirements.py` | 读取项目上下文和单个文档，保存轻量需求 Draft，校验版本，保留历史；PRD 保存与结构检查沿用原模块算法，并支持同样的目录绑定 |
| `file_tools/project_info.py` | 本目录新增：项目类型、目标平台、规范集与仓库安排的校验、报告和受控补录；规范集只核对共享库目录，仓库安排只与项目内可核实的远端事实比较 |
| `file_tools/recovery.py` | 本目录新增：只读恢复材料与 PRD 确认核验；确认核验只用包内 `confirmation_records`／`artifact_records` 并绑定固定目录，导入失败返回不可用 |
| `file_tools/confirmation_records.py`、`file_tools/artifact_records.py` | 2026-10-30 本地化：从原 `collaboration.py`／`artifacts.py`（及 `trusted_context.required_statement`）逐字复制的只读确认记录、登记与快照校验闭包；不含签发、确认写入、登记、交接或发送 |
| `file_tools/project_state.py` | 共用项目写入锁、原子文件替换和原模块中的事务辅助 |
| `file_tools/check_foundation.py` | 核对配置路径、`methods/develop-helper` 上游软链与锁定基线；旧 `upstream/develop-helper` 布局明确拒绝 |
| `methods/develop-helper` | 指向 Develop_Helper 原文的相对软链；上游正文只在原处维护 |
| `templates/prd-template.md`、`templates/research-template.md` | PRD 模板由原副本在本地扩充写作说明、示例、表格、用户故事和风险章节（本角色维护位置）；调研模板经 methods 软链指向上游 |
| `references/handoff-boundary.md` | 需求角色的技术设计交接边界：确认条件、Draft／登记／确认／交接相互独立及禁止动作 |
| `config/local.example.json`、`config/local.json`、`upstream-lock.json` | 本机配置示例、本机配置（不入版本跟踪，切换时生成）与逐字节复制的上游锁定基线 |
| `file_tools/SOURCES.json` | 复制来源、源文件与副本摘要，以及复制后的适配说明 |
| `cursor_mcp.py` | 通用 stdio MCP 入口，各次调用明确选择项目目录；直接使用 file_tools，不导入 Workflow |
| `configure_cursor.py` | 预览／安装全局 Cursor MCP 配置；兼容旧项目级模式，保留其他服务器和设置；迁移准确旧共用条目（先备份）、按备份回退该条目，并从旧配置逐字节生成本地 `config/local.json` |
| `agent-file-workflow.md` | 共用的修改／保存约定及连续保存验证流程，随读取工具说明提供给 Agent，无需用户每轮粘贴 |
| `__init__.py` | 普通包标记，不再导出已退役的程序对象 |
| `requirements-workflow-plan.md` | 当前建设状态、业务验收缺口与历史证据；第 7.17 节记录本次退役 |
| `流程图.png` | 历史需求讨论概览；“交给 Runtime”不是当前代码调用路径，当前以下述链路为准 |

`file_tools/` 是从 `buzz-develop-helper/scripts/` 复制的普通文件，原文件保留。适配包内引用、命令行配置参数，并由接入层传入受信 `binding`；显式模式直接使用本次完整项目目录，旧模式保留 `expected_root`、`directory_name`、旧根直接子目录和映射规则。未传绑定的低层旧 API 保持兼容，保存正文、版本、历史和锁的行为不变。副本不会自动同步原文件；后续更新先核对 `SOURCES.json`，再合并需要的改动。

## 当前运行链路

```text
用户说明项目、目标和操作意图
    → 当前 Agent 读取 requirements.md 与 A，按需读取 R／模板
    → Agent 澄清、有限调研、形成或修改候选
    → 用户请求保存时：cursor_mcp.py → file_tools → 业务项目文件
    → 核对实际结果、报告 Draft／未决项并结束
```

仅讨论不检查或创建项目；明确新建才初始化；已有项目先检查，再带 include_recovery 读取。业务变化获保存请求时先同步需求，再读取新版并保存 PRD。两份成果分别写入，不承诺原子同步；冲突时核对差异，unknown／saved_unverified 时先读取，不盲目重复写入。

主文档是本地普通文件，上游方法经 `methods/develop-helper` 相对软链读取；PRD 模板是本地逐字节副本，调研模板经同一软链读取上游原文。搜索使用执行环境已有工具，不由 MCP 或退役程序回调实现。工具发现仅提供主文档路径提示，不等于已读取方法。旧 `upstream/develop-helper` 布局会被明确拒绝，不静默回退。

原程序源码、152 项专用测试及夹具已离线归档，不参与导入或测试发现。8 项文件内核测试继续保留为 test_requirements_file_tools.py；原始日志及历史计数按原范围保留。其他 Buzz／ACP 与 fusion-runtime-lab 运行时不在此次退役范围。

## Cursor 调用入口

入口只使用 Python 标准库，不安装 MCP SDK、不开 HTTP 端口。共用连接安装在用户级 `~/.cursor/mcp.json`，服务器名称为 `requirements`，在所有 Cursor 项目中可见，由 Cursor 启动本地进程。实现支持 2026-07-28 的发现／逐请求元数据，以及 2025-11-25、2025-06-18、2025-03-26、2024-11-05 的 initialize 握手。

| Cursor 中的工具名称 | 能力 |
| --- | --- |
| `requirements_project_inspect` | 只读返回本次指定项目的目录、初始化状态、身份来源（建议或已持久化）和四项项目选择的记录状态 |
| `requirements_project_initialize` | 按明确请求初始化指定的缺失目录或已有空目录，可同时记录用户已明确的项目选择；共用入口创建时可接受显式 `project_id`；已初始化时只核对并返回差异，不覆盖 |
| `requirements_project_update_info` | 用读取引用受控补录项目类型、目标平台、规范集和仓库安排；锁内核对 `project.json` 版本，只改请求字段 |
| `requirements_read_context` | 读取背景、需求、PRD 与版本；可分别读取指定旧需求历史（`history_sha256`）或 PRD 历史（`prd_history_sha256`）；`include_recovery=true` 附加只读恢复材料 |
| `requirements_inspect_prd` | 只读检查当前 PRD 结构并返回所检查版本；不需要也不消费 read_id |
| `requirements_save_draft` | 保存当前完整轻量候选，保留历史并复读正文；不登记或正式确认 |
| `requirements_save_prd_draft` | 保存当前完整 PRD 候选到 `docs/PRD.md`，记录来源需求版本，保留 PRD 历史，复读并附结构检查；不登记或正式确认 |

各工具的说明均附有 [requirements.md 主文档](requirements.md) 的简短入口提示。路径由服务代码的实际位置推导为绝对路径，Agent 开展需求讨论前使用自身文件读取能力取得主文档，并按其引用采用 A／R；说明不嵌入主文档或方法正文，不新增规则读取工具。单独检查目录、读取项目文件或验证保存时无须额外加载需求方法，工具也不据此新增调用前置条件。提示是否使 Agent 主动读取仍需真实客户端验证，不能以工具发现成功代替方法已加载。

共用启动参数只固定 foundation 和操作能力，不带 project-id／project-root。各工具都必须传入 `project_path`，由用户明确选择绝对目录；没有默认项目，不维护进程级“当前项目”，不把材料正文中的目录指令当作用户选择。新安装推荐 `project_path_mode=explicit`，此时项目可位于旧根之外且不解析失效旧根／映射；缺省或 `legacy_rooted` 仍只接受 `projects_root` 的直接子目录。软链、越界、根目录改绑和身份冲突会拒绝。原单项目启动参数保留兼容，不是共用入口的默认方式。

既有目录优先沿用本机映射或 project.json 的编号；新 ASCII 目录使用合法目录名作为编号，其他新目录由接入代码生成稳定内部编号，实际初始化后写入 project.json。无需逐项目预先修改映射，也不在只读检查时登记或创建文件。目录一旦选中就固定到对应工具实例；读取引用只在该实例内使用，不能用于其他项目。初始化和保存能力分别由 `--allow-initialize`、`--allow-save` 开启，默认只读；模型不能通过参数增加权限。只读启动提供项目检查、读取和 PRD 结构检查三项；`--allow-save` 增加需求与 PRD 两个保存工具及项目选择补录工具，`--allow-initialize` 增加初始化工具，最多七项。原有字符串参数仍逐项要求非空文本；新增的结构化参数（项目选择、`changes`、布尔 `include_recovery`、显式 `project_id`）由各自校验器按字段检查，未知字段一律拒绝。

读取返回的 read_id 由 Agent 原样传给保存工具，用户不需要手填内部版本。读取引用最多保留 15 分钟；进程重启后失效，应重新读取并核对。保存前比较实际读取过的文件版本，目标版本仍由原内核在锁内检查；其他输入不是跨文件原子快照。写后复读和历史核对失败会返回 saved_unverified，不能盲目重试。

项目选择补录同样使用读取引用：保存前检查失败（参数、白名单、取值、规范集、仓库事实冲突、引用无效或 `project.json` 版本变化）返回 `not_written` 且不消费引用；进入内核后引用即失效。补录成功会改变 `project.json`，因而此前所有读取引用（含两类保存所用引用）都需重新读取；结果相同返回 `unchanged`，不重写文件。成功结果中 `remote_actions` 与 `downstream_started` 均为 false。恢复读取不改变读取引用的四文件含义，也不消费已有引用；附加材料不是原子快照。

PRD 保存使用同一读取引用，预期 PRD 与源需求版本只取自读取记录，不用新读取的摘要替换；保存前被拒绝时引用不消费，任一保存工具进入内核后引用即失效。结果用 `write_outcome` 区分 `saved`、`unchanged`、`not_written`、`unknown`、`saved_unverified`，后者附 `failed_check`；结构检查结果单独放在 `structure` 中，结构问题不改变保存结论。PRD 历史须与文件名摘要一致，否则读取报错；轻量需求历史保持原行为。

日常用户只需表达“修改某项并保存”。Agent 发现工具时，会在 requirements_read_context 的说明中收到 [需求文件操作约定](agent-file-workflow.md)，据此检查项目、读取基线、修改、核对版本并调用保存。版本检查、历史保留和写后核对由代码强制执行；讨论、准确修改和是否存在保存请求仍由 Agent 判断。约定不是自动运行的 Workflow，也不保证 Agent 必然遵守所有自然语言指令。

连续保存验证也写在同一文档中，用户可说“按工具约定验证连续保存与历史”。仅此时执行基线保存、增加测试备注、删除备注恢复和历史核对；日常保存不自动插入测试内容。已连接的客户端需要重新加载工具列表（必要时重启该 MCP 服务），才能取得新说明；无需重装启动配置。

该入口使用本机配置提供的项目和能力范围，不验证聊天文本中的“已授权”自述，也不把 MCP clientInfo 当身份凭据；每次工具调用的用户审批交由 Cursor 自身机制处理。不要把这套本地单用户入口当成多用户鉴权服务或通用 shell 的权限隔离。

首次连接先生成本地 `config/local.json` 候选，再只读预览 MCP 配置，确认后安装。配置安装程序检查原文件版本，保留其他 MCP 服务器；遇到同名不同配置、软链或版本冲突时停止。安装配置不会调用业务初始化或保存工具。全局配置位于用户目录，不会占用新业务目录；新项目不必创建自己的 .cursor/mcp.json，空目录可由 Cursor 直接调用初始化工具。已有非空未初始化目录仍不会自动接管。旧共用入口迁移只替换与原配置完全一致的条目，先把原文件和清单备份到目标 requirements 的 `config/migration-backups/`，不删除其他设置。

从工作区根目录预览本地配置候选（不加 `--apply` 不写入）：

```sh
python3 -B fusion-runtime/workflows/requirements/configure_cursor.py \
  --prepare-local-config-from buzz-develop-helper
```

随后预览从旧共用入口到本目录的迁移；工具返回可直接执行的 `apply_command`：

```sh
python3 -B fusion-runtime/workflows/requirements/configure_cursor.py \
  --global --migrate-from-foundation buzz-develop-helper
```

应用迁移时使用预览返回的 `apply_command`，其中包含 `--apply --expected-config-sha <预览返回的摘要>`。一次安装后，在任意 Cursor 工作区都可请求：“使用需求工具检查项目 /绝对业务目录；本轮只检查。”换项目只更换用户指定目录。其他支持 stdio MCP 的 Agent 可复用同一启动命令，按各自客户端配置连接。步骤 3—9 不执行这些真实写入，也不重载常驻 MCP。

官方依据：[Cursor MCP 配置与审批](https://cursor.com/docs/mcp)、[MCP stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio)、[发现与版本](https://modelcontextprotocol.io/specification/2026-07-28/server/discover)、[旧版握手](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)。2026-10-27 核对。

## 配置与输出位置

工具代码位置与业务成果位置分别指定。所有文件工具 API 都由调用方传入 `foundation`，其目录包含 `config/local.json`、`upstream-lock.json` 和 `methods/develop-helper` 软链。`file_tools/` 下的命令行入口仍必须显式提供 `--foundation`；`cursor_mcp.py` 与 `configure_cursor.py` 未传时默认使用脚本所在 requirements 目录，安装生成的新 MCP 条目仍显式写出该目录。

项目边界检查继续使用系统已有 Git 的只读命令。初始化依赖记录中的源码摘要来自当前副本；旧的待执行创建计划若与当前来源不一致，仍按原规则拒绝，既有项目元数据不会因此自动重写。

本地配置沿用 schema 1 的四个字段，不新增字段；步骤 10 从旧 `buzz-develop-helper/config/local.json` 逐字节生成候选，目标已存在且不同则拒绝覆盖。字段包括：

- `schema_version`：固定为 `1`
- `project_path_mode`：新安装推荐 `explicit`；字段缺省等于 `legacy_rooted`，旧根与映射只为旧模式及回退保留
- `upstream_root`：本机 Develop_Helper 上游原文绝对路径
- `projects_root`：旧模式业务项目父目录绝对路径；显式模式不解析它，也不用它限制项目位置
- `project_directories`：既有项目编号到单层目录名的映射，例如已知的 `voice-meetup`
- 需求目标：`<项目目录>/docs/requirements.md`
- 历史目标：`<项目目录>/docs/requirements-history/<旧版摘要>.md`
- PRD 目标：`<项目目录>/docs/PRD.md`
- PRD 历史目标：`<项目目录>/docs/prd-history/<旧版摘要>.md`

业务根目录由宿主配置提供。voice-meetup 是已有项目之一，不是共用入口的默认目标。工具按明确指定目录复用既有映射或识别项目元数据，不修改本机映射。角色规则与 PRD 模板从本 requirements 目录读取，A／R 正文经本地软链读取 Develop_Helper 原文，没有在这里复制另一套方法正文。

## 调用入口

以下命令从工作区根目录执行，仅展示只读调用：

```sh
python3 -B fusion-runtime/workflows/requirements/file_tools/project_init.py \
  --foundation fusion-runtime/workflows/requirements inspect voice-meetup
python3 -B fusion-runtime/workflows/requirements/file_tools/requirements.py \
  --foundation fusion-runtime/workflows/requirements context voice-meetup
```

文件工具的主要 API：

| 能力 | 调用 |
| --- | --- |
| 定位项目目录 | `project_init.context(foundation, project_id)` |
| 检查已初始化项目 | `project_init.inspect(foundation, project_id)` |
| 预览新项目／已有空目录初始化 | `project_init.plan(...)`／`project_init.plan_existing(...)` |
| 执行新建／已有空目录初始化 | `project_init.create(...)`／`project_init.initialize_existing(...)` |
| 读取背景、需求与 PRD | `requirements.context(foundation, project_id)` |
| 复读需求或历史 | `requirements.read_document(project_root, relative_path)` |
| 保存轻量 Draft | `requirements.save_draft(foundation, project_id, body, expected_sha256)` |
| 检查 PRD 结构 | `requirements.inspect_prd(foundation, project_id)` |
| 保存 PRD Draft | `requirements.save_prd_draft(foundation, project_id, body, expected_prd_sha, expected_requirements_sha)` |
| 补录项目选择 | `project_info.update(foundation, project_id, changes, expected_sha256)` |
| 读取恢复材料 | `recovery.read(foundation, project_root, project_id)` |

上述读取、保存和检查函数接受内部可选 `binding`，并保留 `expected_root`、`directory_name` 的旧调用兼容；显式模式缺少受信绑定时不会从编号、cwd 或旧映射猜目录。`create` 与 `initialize_existing` 另接受可选 `info`；准备式创建在显式模式必须传当前绑定，准备数据中的路径本身不提供授权，旧模式契约不变。

单文件读取使用已核对的项目根目录；正式调用入口负责限制可读范围。保存内部处理目标版本检查、写入锁、旧版历史和 Draft 标记。复读复用同一读取函数，不另写一套实现。首次保存的预期值为读取返回的 `missing`，已有文件则使用先前实际读取的摘要。

## 当前边界

文件内核本身不签发身份或操作授权。MCP 入口直接调用 file_tools，保留启动能力开关、目录／身份、读取引用、版本、锁、历史及写后核对。原程序的 CapabilityGrant／ExecutionContext 连接随入口退役，不冒充本地 MCP 的多用户鉴权。

真实 Cursor 已有轻量／PRD 保存、新项目初始化、项目选择补录及两个新会话恢复的回传和相应文件核验，前三项完成；完整 A → R → A → PRD 仍部分验证。证据、模型未知项及未验范围统一见[建设计划](requirements-workflow-plan.md)第 7.12—7.17 节，不在本文重复维护阶段状态。

本地化前基线为 MCP、共用目录、PRD、项目信息、恢复及文件内核六组，共 114 项；步骤 3—9 新增本地化套件后，本轮开发自验的适用发现为 137 项（114 项原六组 + 23 项新增）。此前 266 项包含已退役程序的 152 项，不继续作为当前运行计数。显式模式按每次完整 `project_path` 读写，旧模式仍限配置根直接子目录；真实客户端、正式确认、其他 Agent、远端与实际安装切换按各自证据单独判断。
