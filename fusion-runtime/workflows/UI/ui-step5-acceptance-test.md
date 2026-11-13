# 步骤 5：UI 工具开发结果验收执行文档

日期：2026-11-02（Asia/Shanghai）。文档版本：v1.0。适用契约：`ui-tools-v1`。

文档状态：待执行的验收规程。本轮仅编写文档，UI 工具和正式测试尚未实现；下文没有任何预填的运行通过结论。

## 1. 用途、依据和验收范围

将本文交给测试 Agent，可在开发交付后核对实现、运行现有测试，并在独立临时项目中复验完整主线和关键保护。开发者也可据本文做自验；自验与独立验收分别注明执行者和结论，不能混称。

| 文档 | 用途 |
| --- | --- |
| [工具实施说明](ui-tools-implementation-plan.md) | 准确参数、返回、限额、错误、版本及恢复语义的权威契约 |
| [详细测试清单](ui-tools-test-checklist.md) | UI-T01—T47 完整场景；编号和标准保持不变 |
| [逐步开发方案](ui-step5-development-plan.md) | S5-00、5A／5B／5C 的实施范围及完成条件 |
| 本文 | 开发完成后的实际验收次序、关键用例、证据和报告格式 |

本文 AC5 编号是执行分组，不新增一套工具标准，也不替代 UI-T01—T47。某分组只覆盖原用例部分分支时必须记 partial；所有剩余分支仍逐项列出。发现文档冲突时报告具体条款，不自行修改契约或测试标准。

本次验收目标：临时项目完成“读取 → 候选编辑 → 检查 → 接收 → 复读 → 历史”，并实际拒绝冲突、越界和未经许可的覆盖。第 6 步完整故障矩阵、第 3 步页面体验、第 8 步独立验收身份和第 9 步真实客户端配置各自单独判定，不因本测试通过自动完成。

## 2. 测试权限和文件边界

1. 只读正式源码、测试、规则和 SOURCES；运行与破坏试验使用系统临时副本。测试结果可写本模块 `verification/acceptance-runs/<run_id>/`，只新增本轮报告，不覆盖已有证据。
2. 不修复正式实现或正式测试来取得通过。发现失败写 finding，交回开发者；修复后按新源码摘要复验受影响场景。
3. 不使用真实采购业务项目、真实外部候选或真实客户端配置；不启动无关服务，不登记、不确认、不交接、不部署。
4. 故障注入使用交付的内部测试钩子／测试替身或临时子进程，不给 MCP 增加 force、fail_after、跳过摘要等参数。没有必要测试设施时记未验或阻塞，不能假造执行。
5. 只结束本轮启动的进程。遗留锁仅在临时项目确认持有进程已死亡后，由测试操作者记录并清理；不将清理计作工具自动能力。
6. 临时副本除必要配置和方法链接映射外保持正式源码原始字节；记录映射差异，不改 adopted 源码摘要或刷新上游锁来绕过检查。

## 3. 执行前检查和临时环境

### 3.1 AC5-00：确认有可验收实现

读取开发报告，检查实际源码、正式测试和运行说明存在。核对六工具、启动开关、采用源码清单及依赖摘要；内部文件名可依实际拆分变化，但必须能定位职责。

若只有本文、开发方案或 test checklist，没有 MCP 运行实现：报告 `NOT_READY`，其余运行项记 blocked；不能运行空测试发现后写通过。本次文档交付时即处于未实现状态。

记录代码／测试文件路径与 SHA-256、Python／Git 版本、平台、协议支持集、测试执行者身份及采用契约。不要只引用开发者声称的通过数量。

### 3.2 临时目录与固定数据

使用系统临时目录建立本轮唯一 RUN_ROOT。以下名称为测试内符号，由测试 Agent 实际创建后填入绝对路径；不能把符号字符串当真实路径传给工具。

| 符号 | 准备内容 |
| --- | --- |
| UI_COPY | 本 UI 模块与实际运行源码副本，保留来源记录 |
| FOUNDATION | 九文件基础、必要配置与上游锁的副本 |
| UPSTREAM | 原采用的上游完整副本，保持快照；双方法软链都指向这里 |
| PROJECTS | 临时业务父目录，位于 Git 仓库之外，与基础／工具／上游分离 |
| P1、P2 | 使用公共初始化能力建立的两个中文项目，含合法持久 ID 与映射；不建远端 |
| IMPORT_PARENT／I1 | 单独授权的临时导入父目录／虚构五文件案例 |
| EVIDENCE | 本轮执行日志、调用与文件快照；不放入候选 tree 或公共演示成员中 |

临时配置 projects_root 只指向 PROJECTS。其他基础配置结构沿用实际共享契约；不能只手写 project.json 冒充已初始化项目。若公共初始化能力缺失，先报告前置阻塞。

P1 初始具有虚构 requirements、Draft PRD，可缺 tech-spec／decisions；无 UI 清单、指针、设计说明和公共页面目标。P2 用于跨项目凭证测试。初始根 README／project.json 等受保护文件保存原始字节摘要。

完整候选固定使用：

| 项目相对成员 | 初版 V1 内容约束 |
| --- | --- |
| docs/prototypes/demo/index.html | 本地 .html 入口，相对引用 assets/app.js 与 assets/styles.css |
| docs/prototypes/demo/assets/app.js | 可识别的虚构标记 V1，不调用外网 |
| docs/prototypes/demo/assets/styles.css | 本地样式 |
| docs/prototypes/demo/assets/old.bin | 明确的原始二进制字节，用于摘要和删除验证 |
| docs/prototypes/demo/README.md | 说明静态打开方式、模拟范围及未做浏览器验收 |
| docs/ui-style.md | Draft 设计说明，保留待决／未验项，不写 Confirmed |

I1 使用 index.html、assets/app.js、assets/styles.css、README.md、docs/ui-style.md 五个虚构文件。导入前保存全树快照；不得拷贝真实候选作为必要条件。

### 3.3 快照与证据要求

每次调用前后记录相关树：相对路径、类型、原始字节 SHA-256，目录也记录；软链记录原始目标。区分“测试主动注入的改动”和“工具产生的改动”，在注入后再取一次调用前基线。

| 区域 | 核对标准 |
| --- | --- |
| 只读调用的项目／基础／工具树 | 不新增目录、锁、回执、缓存或文件，不改任何字节 |
| prepare | 只允许本项目候选和对应私有回执等契约状态变化；公共成果不变 |
| accept／recover | 只允许计划公共成员、公共清单、UI 私有状态和正常公共锁生命周期变化 |
| 永久保护区 | 基础／上游／原导入树、其他项目、根 README／project.json、业务输入及正式记录保持原样；人为故障注入另记 |

每项保存准确请求、原始响应、isError、状态、write_outcome、error.code、verification、凭证／事务／版本引用和文件对比。测试令牌可在受控本地日志保留以便核对，但不复制无关凭据或业务正文。

## 4. 先运行开发者交付的自动测试

在临时工作区副本中保留实际测试所需的目录关系，使用开发交付的真实入口运行。标准入口从临时工作区根执行：

```sh
python3 -B -m unittest discover -s fusion-runtime/tests -p 'test_ui_*.py'
```

记录命令、工作目录、测试发现数、执行数、跳过数、失败数和退出码。零发现、全部跳过、夹具导入失败都不算通过。对比 UI-T 映射，找出未覆盖分支；不能只写“退出码 0”。

自动测试结果是验收输入，以下主线仍须在新的临时项目中复验。独立执行者可在自己的临时测试脚本中补充观察，不改正式测试；记录新脚本及摘要，不把自写替身响应当成实际服务返回。

## 5. 六工具真实调用与主线验收

所有 read_id、revision_id、inspection_id、request_id、transaction_id 和 SHA 都使用本次真实值；新写操作生成新的标准小写 UUID。重放测试才复用完全相同请求。每次参数按实施说明第 5 节构造，禁止增加测试后门。

### AC5-01：服务启动、工具发现与只读开关

映射：UI-T01—T03、T44 的相关分支。

1. 从 UI_COPY 启动只读服务，必填 foundation 指向 FOUNDATION；完成真实握手、initialized 通知、tools/list 和只读 tools/call，协议细节按实际支持集。
2. 核对仅列 read_context／inspect／read_history 三项；直接构造 prepare 调用，预期 tool_not_enabled，无私有或公共文件新增。
3. 停止本轮服务，以 allow-write 重启，核对六项工具；只读启动得到的内存凭证不带到新进程使用。
4. 分别验证缺必填、未知字段、错误类型、条件字段冲突、非法模式、过大消息及未握手调用；协议错误与业务错误分开。

通过依据：原始协议响应、准确工具列表和树快照。仅看到列表不代表角色已读取主文档，也不代表写工具可以运行。

启动形态如下；尖括号内容必须替换为本轮真实绝对路径，不能直接照抄占位符：

```text
python3 -B <UI_COPY>/mcp_server.py --foundation <FOUNDATION>
python3 -B <UI_COPY>/mcp_server.py --foundation <FOUNDATION> --allow-write --import-root <IMPORT_PARENT>
```

### AC5-02：读取空项目和完整输入闭包

映射：UI-T04、T06、T08、T09、T16。

调用 ui_read_context：project_path=P1，source_paths=[]。预期 state=empty、current.kind=none，准确内部 ID、完整来源／缺失／目标／目录描述及 read_id；Draft 或可选文档缺失不要求正式确认。

独立重算基线相关摘要，并在另一个夹具中于读取中途改 PRD，预期 unstable、read_id=null。不可读或损坏不能伪装 missing。只读前后整树不变。

### AC5-03：首次候选、检查、接收和复读

映射：UI-T10、T13、T15、T21、T47。

1. 使用 AC5-02 有效 read_id 调 prepare，mode=empty。记录工作区、准备回执和 editable_paths，确认公共文件不变。
2. 对不完整候选 inspect，预期无 inspection_id；按第 3.2 节补齐六个成员和 candidate.json，只编辑允许候选位置。
3. inspect(target=candidate, revision_id=返回值)，预期 candidate_ready、inspection_id、准确 added 集合、空 removed，proposed_revision_sha256 可重算。
4. accept 传准确项目、revision_id、inspection_id、新 request_id 和 delete_paths=[]。
5. 预期 saved。独立读取公共成员、清单、current.json、完整版本、请求回执，逐字节核对；无旧版本不伪造 v0，活动日志已结束。
6. 调 read_context、inspect(current)、read_history，再按返回 SHA 读取单版本。准确当前版本、清单与快照一致。

通过依据：实际工具接收产生 V1；清单成员对象只有 path／sha256，清单不包含自己，binary 未损坏。verification 六项均有文件证据；未验浏览器仍明确未验。

### AC5-04：修改、增加、删除及未知文件保护

映射：UI-T22—T25、T26。

1. 在 artifact_root 放一个未受管 user-note.txt，再重新 read，prepare(current)；未知文件不成为受管成员。
2. 候选 app.js 改为 V2，增加 new.bin，删除 old.bin，更新候选声明；设计／入口／README 保留。
3. inspect 核对 added／modified／removed；先用不匹配 delete_paths 接收，应 invalid_arguments 或 inspection_invalid（按实际失败环节），公共树不变。
4. 用精确 removed、新请求 ID 正常接收；因前置拒绝未消费且候选未变，可用原有效检查凭证；若实际已失效按契约核对后重新检查。
5. 预期当前 V2、旧素材删除、新素材字节正确、user-note 保留；V1 的 old.bin 仍可完整读取。
6. 在独立分支让候选试图写 user-note.txt，预期 unmanaged_target_exists，不覆盖。公共成员被外部改坏后的正常读取应 collection_invalid，不自动纳管。

### AC5-05：请求重放、相同内容和历史恢复

映射：UI-T22、T26—T28、T30—T31。

1. 完全原样重放一次已成功 accept 的请求；预期 receipt_replay=true，不二次写成员、不新增版本，返回可核对的原结果及独立 current_revision。
2. 同 request_id 改参数／operation，预期 request_reused。损坏回执的测试使用独立副本，预期 receipt_invalid，原回执不被自动改写。
3. 新 prepare(current)，不改内容和来源，inspect 后以新请求 accept；预期 unchanged，不新增内容目录或重写公共字节。
4. 读取 V1、V2；分页验证可用 limit=1，按实际 next_after_revision 取下页，无重复遗漏。旧快照缺文件／摘要损坏时 history_invalid，不修补。
5. 在独立分支改变当前业务输入，再 read→prepare，参数 mode=history、history_revision=V1 的实际摘要。核对基线采用新输入，restored_from=V1，并依据新输入明确更新候选设计，再 inspect→accept。
6. 核对新当前版本绑定新来源、中间历史完整；不能把历史原内容直接说成已经适配新输入。先完成 unchanged 测试再改输入，避免混淆结果。

### AC5-06：外部五文件导入

映射：UI-T11—T12、T46。

在新的空项目 P_IMPORT 中，用获准 I1 构造 import_source，完整列出五文件和准确入口／设计／README。read→prepare(import)→inspect→accept，独立核对映射：页面和 assets 进 demo，README 进 demo/README.md，设计进项目 docs/ui-style.md。

对未授权根、漏列入口、重复目标、.env 文件、read 后导入 JS 变化分别复验，预期 path_not_allowed／invalid_arguments／mapping_conflict／source_changed（按实际环节）。每个失败使用独立请求和夹具；I1 与项目根 README 前后完全不变。

## 6. 必须拒绝的冲突与边界

### AC5-07：读取／检查后发生变化

映射：UI-T06、T24—T25。

每行用独立合法基线；注入之后先快照，再调用并核对“不覆盖”事实。

| 注入点和实际动作 | 预期判定 |
| --- | --- |
| read 后改 PRD，再 prepare | source_changed，不建立成功候选 |
| inspect 后改候选 JS，再 accept | candidate_changed 或 inspection_invalid，不接收新字节 |
| inspect 后改业务输入，再 accept | source_changed，不用新 read_id 替换旧候选基线绕过 |
| inspect 后改公共成员，再 accept | target_changed／collection_invalid，不覆盖用户改动 |
| inspect 后在计划新目标放用户文件，再 accept | target_changed／unmanaged_target_exists，不覆盖 |
| 已读取的登记引用清单／成员改变，再 accept | 重新校验保护闭包后拒绝，不只核对 project.json |

错误按契约实际阶段判定，不能泛化成“任意异常均通过”；响应和证据必须证明检测到了所注入的变化。

### AC5-08：项目、路径、未受管内容和准确写范围

映射：UI-T04—T05、T09、T14、T46。

1. project_path 指向 projects_root、未初始化目录、错误 ID 映射、软链目录，逐项核对身份／路径拒绝，无自动初始化或搬迁。
2. 在候选、source_paths、artifact_root 和导入路径分别试 ..、绝对成员、反斜线、大小写／非 NFC 冲突、软链／硬链接；逐项路径拒绝，不越界读写。
3. 测首次无清单却预存 docs/ui-style.md 或目标文件，预期 unmanaged_target_exists；不支持旧布局报告 unsupported_layout。合法 legacy 另按原清单验证读取和接收前归档。
4. 按测试清单补充特殊文件、父目录替换竞态；不能因普通 .. 用例通过就把 T05 全项通过。
5. 比较所有保护区，包含根 README／project.json、需求、PRD、原导入、基础、上游、其他项目及正式记录；未经计划的工具写入属于失败。

### AC5-09：已登记引用、公共锁和 Main 事务

映射：UI-T29、T32。

按真实登记结构构造临时 Q：分别直接引用拟修改成员、引用固定历史快照、包含损坏引用清单。前者 registered_path_in_use；后者不因不相关引用阻塞；损坏应 registry_unreadable，不跳过保护。

模拟项目公共锁被占用，写操作 lock_busy 且不自动删锁。在独立夹具放 Main 根事务日志，预期 main_transaction_pending，UI 不修复或覆盖该日志。两个临时服务对同项目并发写入，核对互斥及实际文件，不只看先后返回。

### AC5-10：凭证、关闭候选、重启和配额

映射：UI-T17—T20、T30—T31。

使用 P1 凭证操作 P2、R1 检查凭证操作 R2、伪造令牌、额外 force／inspection_ok 字段，逐项拒绝。用可控时间验证 15 分钟过期和 128 个凭证容量，消费时机按契约核对。

prepare 后编辑候选，停止本轮服务并重启：旧内存令牌失效，原工作区和基线可核对，重新 inspect 成功；来源变了则拒绝，不刷新 base.json。已接收工作区再编辑也不发新检查凭证。

prepared 回执重放允许候选已合法编辑；未完成请求返回 operation_incomplete，不开始第二笔。8 个未结束候选后第 9 个 workspace_limit；准备失败残留计入配额且不自动删除。逐分支记录，未测容量或消费边界的编号保持 partial。

### AC5-11：限额、完整性和只读副作用

映射：UI-T07、T13—T16。

按原清单逐项构造：源文档／追加源／保护描述／消息／响应预算上限，成员数量、单文件、集合、候选声明及清单大小上限。具体数值以契约第 4.3 节为准，至少记录临界合法与超限结果，不通过缩小闭包发凭证。

未列普通文件应 unlisted_file，缺必要成员不发 inspection_id；输入不可读不是 missing。二进制原始字节摘要正确，正文省略有 content_omitted；文件错误不自动修复。

对 read_context、read_history 和 inspect 的三种 target 分别快照：只读操作不产生目录、锁、回执、历史、字节码；不把通用编辑器的主动编辑算成工具副作用。

## 7. 第 5 步基本恢复必测与第 6 步扩展

### AC5-12：基本恢复及拒绝分支

映射：UI-T33—T42 的指定子场景、T47；以下为步骤 5 必测最低集合，不等于 T33—T42 全部完成。

每行独立临时项目／事务，先记录故障点和事务证据，再 inspect(transaction)，最后显式选择恢复动作。调用 `ui_recover_revision` 必填 project_path、transaction_id、新 request_id、action=resume 或 rollback。

| 子场景 | 操作与预期 |
| --- | --- |
| basic.pre_activation | 活动日志落盘前中断，目标仍全 before；指定事务检查 not_activated。符合契约时显式 rollback 只关闭私有记录，not_written，公共字节不变 |
| basic.partial_resume | 部分公共成员写成 after 后中断；检查逐目标 before／after。来源未变时 resume 得到完整新集合及可复读回执 |
| basic.rollback | 独立部分写入事务，无 saved 终态；rollback 完整恢复 before。首次创建的 missing 目标被撤除，current_revision=null；不删未知文件 |
| basic.source_changed | 中断后改输入；resume 拒绝并保留事务。显式 rollback 仅恢复已知公共写入，不改已经变化的输入 |
| basic.third_party_other | 中断后把一个目标改为既非 before 也非 after；resume 和 rollback 都 recovery_conflict，第三方字节保留 |
| basic.saved_receipt | saved 回执落盘后、清理活动日志前中断；rollback 返回 already_committed，resume 核验并关闭遗留日志，不重复接收 |
| basic.invalid_plan | 损坏计划／before／after／摘要或制造证据不足；明确拒绝，不从不可信记录生成覆盖动作 |

进程异常遗留锁的人工核对与临时清理记录在独立字段；工具实际返回的 unknown／saved_unverified 与文件状态相符，不能将异常捕获后统一报 not_written。

### AC5-13：完整故障矩阵的后续账本

依原 UI-T33—T42 列出全部场景的执行状态，包括活动日志之后首写之前、成员中途、清单之后指针之前、指针后复读失败、saved 回执后清理之前、真实退出重启、来源变化、回滚、第三方状态、磁盘／日志／锁故障。

本轮若未全跑，标为第 6 步待验，原编号按 partial 或 not_run 记录；不可删除这些行。AC5-12 任一必需子场景失败或无证据，则步骤 5 不能判通过，不能全部推给第 6 步。

## 8. 隔离、来源及实际结果报告

### AC5-14：净化新进程与无回退加载

映射：UI-T01—T03、T45—T46。

用 `-I -S -B` 在临时副本执行完整主线，清除 PYTHONPATH／用户 site 影响，并设置同名诱导模块。通过审计／受控环境验证实际加载路径，不回读真实旧 scripts、方案服务或工作区源码。

缺一个共享文件、改变采用源码、断方法链接、配置不合法分别拒绝，不换源或刷新锁。服务运行后改变临时运行基线，再调用适用工具，runtime_baseline_changed 且不写公共成果；启动前摘要不匹配与运行中变化按各自错误层级记录。

### AC5-15：契约和证据一致性

映射：UI-T43、T47。

对照实际 schema、说明、来源、六工具数、限额、错误及摘要；区分历史文档记录和当前运行基线。分别核对 prepared、saved、unchanged、not_written、unknown、saved_unverified，以及 rollback 的实际响应。

即使缺浏览器记录或设计有待决项，合法保存也不能返回 approved／ready_for_development。未运行的 verification 不填 true。旧回执重放的 current_revision 必须是实际当前，不把旧操作结果冒充最新状态。

## 9. 报告格式与结论

### 9.1 本轮证据文件

验收时新建 `verification/acceptance-runs/<run_id>/`，至少保存：

| 文件 | 内容 |
| --- | --- |
| report.md | 本轮范围、执行者、源码版本、结论、失败、未验与继续动作 |
| results.json | AC5 分组／子场景及 UI-T01—T47 对应状态和证据引用 |
| calls.jsonl | 准确工具请求和原始响应，按调用序号关联场景 |
| snapshots.json | 允许／禁止区前后摘要、实际版本／回执／事务核验 |
| test-output.txt | 自动测试、新进程协议测试和净化环境执行的命令、退出码与输出 |

这些是未来执行时生成的结果，不在编写本文时创建空报告或预填成功。失败场景如需保留临时目录，记录位置和用途；删除临时目录前先保存足够复现证据，不将临时路径当永久证据链接。

### 9.2 场景记录模板

每个 AC5 子场景记录：编号、映射 UI-T、执行者、源码摘要、临时项目 ID、前置条件、准确请求、预期、实际响应、文件差异、证据路径、状态、未验／阻塞原因、finding 引用。

状态采用 passed／failed／partial／not_run／blocked。原 UI-T 主编号仅在其全部规定分支有证据且符合预期时 passed；部分覆盖必须 partial。单独统计测试函数数、AC5 执行分组数和 47 个 UI-T 主编号状态，不能将三者相加或互代。

### 9.3 结论判定

| 结论 | 判定 |
| --- | --- |
| NOT_READY | 没有可运行实现、测试或必要环境，无法进入有效运行验收 |
| FAILED | 必需功能／保护行为与契约不符，或出现越界／覆盖等实际失败 |
| INCOMPLETE | 缺少本步主线或必需保护证据，存在 blocked／not_run 等缺口 |
| STEP5_SCOPE_PASSED | AC5-00—12、AC5-14—15 中本步必需场景有实际证据且通过；AC5-13 的剩余系统矩阵逐项列明，第 5 步开发方案第 10 节完成条件满足 |

若部分原 UI-T 留到第 6 步，允许在准确范围内判 STEP5_SCOPE_PASSED，但必须同时列出 partial／not_run 编号和未测分支；不写“47 项全通过”。若必需项失败，优先 FAILED；纯环境或证据不足按 NOT_READY／INCOMPLETE 说明，不能省略失败。

独立验收报告注明独立执行者及范围；开发者执行只标开发自验。无论哪种结论，均不能据此宣称页面业务／视觉通过、真实客户端已接通或正式成果已确认。

### 9.4 Finding 模板和复验

每个 finding 包含：稳定编号、严重程度、关联 AC5／UI-T、源码摘要、前置、最短复现、预期、实际返回、实际文件变化、证据、影响范围。避免只写“有问题”或笼统要求重构。

开发者修复后记录新摘要，复验失败及受影响分支；已有同版本稳定证据可复用。测试执行者不擅自修改实现或降低断言，不自动启动其他 Agent。

## 10. 给测试 Agent 的执行入口

读取本文、工具实施说明、详细测试清单和逐步开发方案，先执行 AC5-00 判断是否具备实现。具备后在系统临时副本按序执行，真实调用六工具，检查返回和完整文件副作用；逐项维护 UI-T01—T47 覆盖账本，交付第 9 节报告。正式源码／测试／规则只读，发现失败只报告，不代修、不改标准；未执行项明确记录，不从开发报告推断通过。
