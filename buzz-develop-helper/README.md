# Buzz × Develop Helper 融合基础

阶段：融合基础、本地项目初始化、轻量需求、A 阶段 PRD、七层方案、成果索引、当前会话确认、固定快照、交接/回执内核，以及宿主事件信封验签与角色工具裁剪已实现；新单元设计门禁检查器已加入，当前融合层全量 116 项测试通过。A 阶段 PRD 和方案新工具已进入 Buzz ACP/MCP 源码，release 构建已通过；solution-mate 已完成角色绑定、线程项目重启恢复与宿主 Channel 回复主路径验收，需求 Agent 新工具和方案 Draft 工具链的真实验收仍未完成。Buzz 当前生产实例中 first-mate 仍是 `just-start` 的 Main。`just-start` v0.3 仍未正式批准，未生成 PRD，业务索引也未修改。

## 目录

- `config/local.json`：本机路径配置，不提交；其他机器根据示例配置真实路径。
- `upstream/develop-helper`：本地软链，只作显式引用，不自动注册上游入口。
- `upstream-lock.json`：本次上游文件内容及链接指纹。记录版本漂移，不提供不可变快照或安全签名。
- `scripts/check_foundation.py`：Python 标准库只读检查工具，无网络、无上游脚本执行、无文件写入。
- `scripts/check_design_contract.py`：进入实现前检查单元设计是否包含上游原文、继承/适配/新增边界、确认状态和来源追踪表；只检查结构，不替代语义评审或用户确认。
- `scripts/project_init.py`：本地项目预览、创建、检查和独立 Git 初始化；写入必须显式指定 `--apply`，不提交、不推送、不调用 GitHub API。
- `scripts/requirements.py`：需求背景读取、轻量 Draft 保存、完整 PRD Draft 保存/历史与结构检查；不执行正式确认。
- `scripts/solution.py`：方案上下文、PRD 用途确认与固定 SHA 核验、`tech-spec` Draft 保存/历史，以及 REQ/AC 引用和覆盖表结构检查；不验证语义正确或真实运行。
- 方案契约与模板：`capabilities/solution.md`、`capabilities/solution-tech-spec-template.md`；本地工具存在不表示 Buzz 角色已经可用。
- `scripts/artifacts.py`：成果索引完整性核对与登记预览；无 `--apply`，不写项目、不读取确认事件、不启动下游。
- `scripts/project_state.py`：需求保存、Git 初始化元数据和成果登记共用的项目状态锁、原子文件替换与持久事务日志辅助。
- `scripts/main_artifacts.py`：无 CLI 的 Main-only 成果登记与恢复内核；校验项目授权 capability、预览摘要前提和中断日志，不确认、不交接、不执行 Git。
- `scripts/collaboration.py`：只读核对确认记录、固定快照、registry 引用和交接状态，不发送或启动下游。
- `scripts/main_collaboration.py`：无 CLI 的当前会话确认、快照、交接准备、发送依据、接收回执与事务恢复内核。
- `scripts/trusted_context.py`：验证 Buzz 宿主签发的短期事件信封，并把 live turn 固定为不可变上下文；不提供生产签名入口。
- `scripts/host_tools.py`：按宿主角色裁剪工具面，把可信上下文接到现有登记、确认、交接和回执内核；身份字段不来自工具请求。
- `scripts/collab_invoke.py`：仅由 `buzz-acp collab-mcp` 调用；从宿主 turn 文件和进程私有 env 验签后分派工具，不接受模型传入的身份字段。
- `adapters/`、`capabilities/`：接入与能力边界说明；用户已据此人工创建需求角色，但文件本身不负责自动安装或证明完整运行通过。

需求 Agent 接入见 [人工配置卡](adapters/requirements-buzz.md)，权威方法见 [需求角色规则](capabilities/requirements.md)。用户选择复用 Buzz 现有设置；已观察 Honey 为 Codex + gpt-5.6-sol，配置卡不修改原开发角色，不复制凭据。完整设计及实测边界见 `../fusion-design/02-需求能力.md`。
方案能力的当前规则见 [方案角色契约](capabilities/solution.md)、[统一模板](capabilities/solution-tech-spec-template.md)和 [Buzz 接入边界](adapters/solution-buzz.md)。本地受控工具、宿主接收端与 Buzz MCP 源码注册已实现；solution-mate 已验证角色绑定、线程恢复与普通回复发布，但方案 Draft 保存、恢复、冲突和工具裁剪仍待真实运行验收，因此尚不能称方案能力生产可用；完整设计见 `../fusion-design/03-方案能力.md`。
成果登记 schema 与命令见 [成果索引规则](capabilities/artifact-registry.md)，确认和交接状态见 [确认交接规则](capabilities/confirmation-handoff.md)，Main 身份及依据边界见 [接入说明](adapters/main-artifact-registry.md)，信封格式和 Buzz 最小补丁见 [宿主上下文接入](adapters/buzz-host-context.md)。完整设计见 `../fusion-design/05-项目成果索引与确认交接.md`。
- `tests/`：在临时目录中验证正常、断链、漂移、配置异常、成果登记、并发冲突和中断恢复；不修改真实业务项目。

## 检查

在本目录运行（Python 3.10+）：

```sh
python3 -B scripts/check_foundation.py check
python3 -B scripts/check_design_contract.py check ../fusion-design/03-方案能力.md
python3 -B -m unittest discover -s tests -v
python3 -B scripts/artifacts.py inspect <PROJECT_ID>
python3 -B scripts/collaboration.py <PROJECT_ID>
python3 -B scripts/requirements.py inspect-prd <PROJECT_ID>
python3 -B scripts/solution.py inspect <PROJECT_ID>
```

检查通过只表示路径、项目父目录和锁定内容匹配，不表示 Agent 已共享背景、Git 已同步或上游只读沙箱已部署。工具失败返回非零状态，不会修复链接或刷新锁文件。

成果 `inspect` 和 `preview-register` 同样只读。预览中的 Main 身份与写入时间是必填占位，不能保存为正式登记。写入/恢复内核没有 CLI，只接受绑定 principal、authority 和项目授权的 Main capability。融合层已经能从短期宿主签名信封验签并签发内部 capability，不能依靠 CLI `--role`、环境变量或消息自述；first-mate 已绑定 `just-start` Main，合法只读调用、保留字段、角色工具面及项目/线程批次围栏均已有运行证据。登记不会验证确认事件，也不会改变 Draft、交接或启动下游。

`project.json` 与 README 写入前同时校验预览取得的 SHA-256，并在公共项目锁内重新生成变更。两文件之间的持久事务日志支持中断后前滚；恢复只处理仍与事务前/后摘要匹配的文件，遇到外部编辑即停止并保留日志。需求保存与 Git 初始化元数据更新也使用同一公共锁，未知锁不会自动删除。该内核限制的是工具调用面；拥有通用 shell 或编辑权限的 Agent 仍需由宿主沙箱另行限制。

当前会话确认把用户身份、会话/消息、成果版本、内容 SHA 和允许用途绑定到 `docs/decisions.md`，并创建内容寻址快照。单文件确认后 registry 版本改指向固定快照，原工作文件可继续形成下一版；确认不会改写 Draft。交接依次记录 `prepared / sent / received-verified`，每一步都需要相应运行时依据；所有返回都保持 `downstream_started=false`。

`snapshot <目录>` 子命令只输出指纹 JSON，用于经审查建立基线。它不写锁文件。正常运行不自动接受新指纹；升级需审查上游差异后单独更新基线。

## 本机配置与迁移

路径由 `config/local.json` 指定，字段见 `config/local.example.json`。配置文件中的示例占位符不能直接运行。软链目标必须与配置的上游路径解析结果一致；项目父目录必须存在且不得与融合层或上游互相包含。

Git 不会打包软链目标。本机链接与路径配置被忽略；其他机器需准备匹配的上游副本、配置真实路径并建立链接，再运行检查。不自动下载上游，不自动升级或覆盖用户文件。

## 上游保护与当前限制

指纹覆盖上游源码树中的普通文件、目录与软链，包括隐藏文件；不跟随软链读取目标。排除任何层级的 `.git`、`.DS_Store`、`__pycache__`、`Projects_Repo`、`node_modules`、`.venv`、`venv` 和 `.pyc` 文件，不扫描既有业务项目或依赖。检查会报告范围内的内容变化；不检查权限、所有者、扩展属性或 Git 内部状态，不提供恶意篡改防护或并发快照保证。锁文件只保存整体摘要与条目数量，不包含上游原文。

本工具不会写入上游；但能访问终端或通用编辑工具的 Agent 仍可能写入软链目标。接入前必须配置按真实路径限制的运行时权限，并验证拒绝写入；目前未运行此验证，不改原目录权限。不得把本目录作为已完成的安全隔离方案。

本地融合目录处于已有父 Git 仓库内。当前没有建立嵌套仓库、提交或远端；独立版本管理方式需明确后执行。

业务项目初始化约定见 `../fusion-design/01-项目初始化与共享资料.md`。本地初始化工具不调用原 `sdd_project.py`，不预建未指定的业务项目。`just-start` 已完成真实本地初始化并关联既有远端；通用远端建仓实现、远端历史整合、Buzz 映射和跨角色共享仍待完成。

## 本地项目初始化（0.2.0）

以下 `demo-project` 仅为使用示例，不是已确定的真实项目。先获得具体名称、用途和执行授权再替换运行：

```sh
# 只读预览；new 不带 --apply 也只预览
python3 -B scripts/project_init.py plan demo-project --name "演示项目" --purpose "验证协作"
# 仅创建三个基础文件，不创建 Git、需求、方案、UI 或任务清单
python3 -B scripts/project_init.py new demo-project --name "演示项目" --purpose "验证协作" --apply
# 只读检查真实文件与 Git 状态
python3 -B scripts/project_init.py inspect demo-project
# 仅在已获该项目 Git 初始化授权后执行；不 add、commit、push 或配置远端
python3 -B scripts/project_init.py init-git demo-project --apply
```

- 项目 ID、直接子目录、上游基线和父仓库边界检查通过后才创建。已有同名对象一律拒绝覆盖，包括断链；用 inspect 查看，不把重复 new 当作恢复操作。
- 自动生成根 `project.json`、`README.md`、`.gitignore`。原始 `materials/`、密钥、环境配置、依赖和运行数据默认忽略；忽略规则不代替提交前内容检查。
- 本地文件和 Git 是独立步骤；元信息分别保留 GitHub、远端关联、提交、推送、Buzz 和共享验证的 pending 状态，不伪造完成。
- init-git 可在已有独立仓库且元信息匹配时核对并更新记录；不重建已有历史。执行失败保留文件，Git 返回失败会记为 failed；进程中断可能留下 pending 状态或锁，须结合 inspect 与实际文件核对，不能自动删锁。
- 基础文件写入失败保留部分目录，不自动填补或覆盖。根目录并发创建采用排他创建，Git 元信息更新使用项目锁和临时文件替换；不提供对恶意并发路径替换的安全防护。
- `gh_cli_available` 只表示本机能找到 gh 命令，未检查登录、权限、组织策略或仓库占用。GitHub 建仓/关联与跨 Agent 读取尚未实现，需后续建设。
- 当前测试在临时目录进行。配置中的 `my_mind` 不在本会话默认可写范围内；真实创建时需取得该目标目录的环境写入许可，不绕过权限。
