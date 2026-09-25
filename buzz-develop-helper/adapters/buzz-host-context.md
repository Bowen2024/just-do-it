# Buzz 宿主可信事件上下文接入

状态：融合层的验签、调用边界、角色工具裁剪及现有 capability 接入已经实现并通过临时夹具。Buzz ACP 生产实例已在 session 解析后签发协作信封，并挂载不含私钥的独立协作 MCP；Desktop 记录已有角色/项目/helper 字段且禁止用户 env 覆盖。2026-09-24 已修复首轮验收发现的混合批次隔离缺口并完成运行复验。2026-09-25 已完成线程根事件与 `project_id` 绑定的持久化、重启恢复，以及宿主最终回复发布器的源码、测试、release 构建和 Channel 主路径运行验收。

## 1. 信任边界

`scripts/trusted_context.py` 只验签，不签发。生产签名必须发生在 Buzz 已接纳并校验 Nostr 事件之后、构造模型 prompt 之前。模型正文、工具参数、Persona、自报角色、普通字典和 Agent 可修改的环境变量都不是声明来源。

宿主为每个已接纳事件签发最长 5 分钟的一次性信封。payload 固定包含：

- provider、authority；
- 项目 ID；
- 当前 Agent 的真实 principal、authority 和宿主角色；
- 触发用户 principal；
- channel、session、root event 和 event/message ID；
- 事件时间及原文；
- 指定接收者 principal/authority（没有则为 null）；
- 此角色在本轮实际可见的工具名；
- issued/expires、nonce。

工具宿主从独立秘密通道取得 HMAC-SHA256 验签密钥，在内存中验签并同时核对当前 live turn。调用时不再接受上述身份字段。信封签名有效但项目、Agent、会话、根事件、消息或指定接收者与 live turn 不同，同样拒绝。

HMAC 只是首版进程间认证格式，不代替 Buzz 原事件的 Schnorr 签名。Buzz 先验证原事件，随后为本地工具边界签发短期声明；两个验证层不能互相省略。验签密钥不得放进 prompt、工具参数或通用 shell 继承的环境。

## 2. 工具面

`scripts/host_tools.py` 为一个已验签 turn 建立固定工具面：

| 宿主角色 | 可见工具 |
| --- | --- |
| Main | 成果只读核对/预览、协作只读核对、成果登记、当前会话确认、交接准备、记录受信发送结果 |
| requirements | 需求背景读取、需求 Draft 保存、成果只读核对/预览、协作只读核对 |
| solution / ui | 当前只开放只读核对；其成果写入工具待单元 03/04 实现后再加入对应 ceiling |
| recipient | 成果与协作只读核对、提交指定交接的读取核验回执 |

工作者信封即使由测试签名，也不能包含 Main 工具；验签器会按角色 ceiling 拒绝。普通工作者不能从请求参数增加工具。接收者的回执入口不暴露 Main 工具：宿主在内部使用同项目 Main 协调 capability 落盘，接收者只能提交绑定自身 principal 的已读版本和摘要。

`main_artifacts.authorization_from_host_context`、`main_collaboration.*_from_host_context` 是生产适配入口。它们从已验签上下文取得身份，不调用 `_issue_runtime_main` 或 `_issue_*` 测试钩子。旧私有钩子只保留既有单元测试兼容。

## 3. 与现有内核的连接

- 登记：宿主工具自行预览并取得 project.json/README 乐观摘要，再调用 Main-only 写入。
- 当前会话确认：用户、session、message、provider/authority、时间和原文来自信封；模型只提交成果版本、SHA、用途和内容边界。
- 交接准备：指定接收者来自信封；请求参数不能传 principal 或 authority。
- 已发送：只接受宿主为实际发送结果签发的事件上下文，并绑定同一接收者。
- 接收回执：调用 Agent principal 必须等于交接指定接收者；实际输入版本仍由内核逐项核对。
- 所有返回继续保持 `downstream_started=false`；任何记录都不创建或启动角色。

## 4. Buzz 宿主实现与当前运行缺口

源码已有的可信材料位于：

- `crates/buzz-acp/src/queue.rs`：`QueuedEvent/BatchEvent` 保存完整 `nostr::Event`，可取得 event ID、签名作者 pubkey、channel 及 NIP-10 root/parent；
- `crates/buzz-acp/src/pool.rs`：`PromptContext` 和 turn dispatch 知道 Agent key、session scope、channel 与当前 batch；
- `crates/buzz-acp/src/lib.rs::build_mcp_servers`：目前只在 `session/new` 注入 Agent 自身 Buzz CLI 凭据；
- `crates/buzz-dev-mcp/src/lib.rs`：当前注册通用 shell/文件/todo/image 工具，没有可信上下文或融合工具；
- `desktop/src-tauri/src/managed_agents/runtime.rs`、`types.rs`、`reserved_env_keys.rs`：负责受控启动配置、持久字段和禁止用户环境覆盖的键。

最小 Rust 补丁进度：

1. 已完成：`run_prompt_task` 在 session 解析后从已接纳 `nostr::Event` 签发信封；顶层事件以自身 ID 为 root。协作实例现逐事件排队，签发端拒绝多事件或夹带取消事件的 turn，项目/线程拒绝立即隔离；2026-09-24 已完成混合批次运行复验。
2. 已完成：Desktop `collaboration_role` / `managed_project_ids` / `collab_helper_root` 进入 spawn snapshot 和重启差异。角色存在时允许 1 个或多个规范项目 ID，helper root 仍必填。不从 Persona 名称推断，不取名单第一项签发。
3. 部分完成：指定接收者来自单一其他 `p` tag；零个或多个 mention 时为 null，不猜测。专用 UI/CLI 选择仍待后续。
4. 已完成：host-owned broker 按 `(agent principal, ACP session)` 更新；heartbeat 清除 turn 文件，避免确认工具沿用旧事件。
5. 已完成：HMAC 只进入 `buzz-acp collab-mcp`。`buzz-dev-mcp` 仍可有 Agent 私钥，但不持有 HMAC。不要把 `BUZZ_PRIVATE_KEY` 注入 dsh，也不要用 `buzz-dev-mcp` 代替 Main 工具。
6. 已完成：工具 ceiling 由信封强制；`reserved_env_keys` 拒绝全部 `BUZZ_COLLAB_*` 用户覆盖。角色工具在 sidecar 中全部注册，调用时按信封拒绝越权。
7. 已完成 ACP seam tests（HMAC 向量、伪造角色、工作者 ceiling、会话复用替换、按线程选定允许名单内项目、名单第一项不自动签发、同线程换项目/名单外/多槽位拒绝、签发失败清 turn、collab MCP 不含私钥）。Desktop `collab_host` 3 项通过；Desktop 全量应用测试仍未作为本轮范围。
8. 已完成：ACP 按 NIP-10 root 绑定本轮 `project_id`。只认独立行 `project_id=…` / `project_id:…` / `project_id：…`，ID 格式与融合层一致。回复沿用根绑定；同线程换项目继续拒绝。线程根与项目绑定现使用版本化、限制数量和大小的宿主持久化记录，原子写入，启动时仅恢复当前 allowlist 内的严格有效记录；损坏、重复、越界或已移出 allowlist 的记录不会放宽授权。2026-09-25 定向测试 23 项、完整库测试 974 项通过且 1 项忽略，生命周期集成测试 9 项通过，release 构建成功。运行实例中，根事件 `72fe0d…b616d` 已绑定 `unit03-runtime-acceptance`；ACP 于 15:34 停止、15:36 重新启动后，15:37 的事件 `65ba62…ead4d` 带真实 NIP-10 `reply` 标签指向该根，正文没有重复 `project_id`，仍成功返回 `U03-BIND-RESTORE-OK`，且没有新的 `-32098`。由此完成重启恢复主路径的运行验收。
9. 已完成源码、测试与 release 构建：协作角色的宿主回复发布器只聚合当前 ACP turn 最后一条 `agent_message`，限制为 64 KiB，并从已接纳的单事件 batch 派生 channel、NIP-10 root 和触发作者；模型不能提供发送目标。宿主用 Agent key 签名一个 kind 9 回复，relay 必须返回匹配该事件 ID 的成功确认，或由精确 ID 回读证明已经落库。发送失败返回 `-32097` 且不重跑模型；空输出、多事件、取消、达到 token/turn 上限的截断输出均不会发布。普通非协作 Agent 仍保持原有发布路径。定向测试覆盖最终消息筛选、跨 session 隔离、大小上限、固定路由、单次消费、丢失确认、relay 拒绝、空输出、普通 Agent、取消/截断输出和 `run_prompt_task` 生产接缝；完整单元测试 985 项通过、1 项忽略，生命周期集成测试 9 项通过。

当前生产记录：Buzz 已重启加载本轮 release。solution-mate 在原 `unit03-runtime-acceptance` 绑定线程中接收不含 `project_id` 的 `U03-HOST-REPLY` 后，Channel 于 22:33 直接且仅显示一条 `U03-HOST-REPLY-OK`，没有 `-32097` 或 `-32098`，证明线程恢复与宿主回复主路径共同生效。first-mate 已绑定 `collaboration_role=main`、`managed_project_ids=[just-start]`、指向融合层的 `collab_helper_root` 和 `agent_command=/opt/homebrew/bin/dsh`；未向 dsh 注入 `BUZZ_PRIVATE_KEY`，也未把 `mcp_command` 改成 `buzz-dev-mcp`。编辑页尚未画出这些宿主字段。Buzz 源码本地存档为 `7ba21091c`，尚未推送。

2026-09-21 第一轮运行验收结果：合法 `artifact.inspect` / `collaboration.inspect` 成功；Main 调用 `requirements.context` 被拒绝；请求中伪造 `event_id` 与 `recipient_principal_id` 均被 `-32602` 拒绝。错误项目、多个项目和线程内换项目没有得到有效拒绝证据：三条事件与随后合法事件进入同一模型 turn，直接暴露了上述批次隔离缺口。下一步先修复批次边界、增加混合批次测试并重启复验；未获得用户对业务写入的另行明确授权前，不对 `just-start` 执行成果登记、当前会话确认或交接。

## 5. 已确认的 Channel 调用体验欠账

2026-09-25 用户确认记录此问题，后续逐步完善。当前一次 Channel 调用需要同时满足并理解多层独立状态：

- Agent 已加入 Channel，`@mention` 才能进入其订阅范围；
- Agent/ACP 实例正常运行；
- Agent 配置持有项目 allowlist，但 allowlist 本身不代表当前线程已经选择项目；
- 每个新顶层线程必须明确选择一个 `project_id`，真实回复才能继承该根绑定；
- 模型运行输出与真正发布到 Channel 的 Buzz 消息属于不同通路。

这些安全边界不能为了减少步骤而退化：不得自动取 allowlist 第一项签发，不得让新顶层线程静默继承其他线程授权，不得允许线程内切换项目，也不得把模型正文或自报路径当成可信项目选择。当前问题主要是产品层没有把必要选择结构化，导致手写槽位、顶层/回复差异和发布通路直接暴露给用户。

后续改善方向按增量处理，不在本次直接确定新单元或默认行为：

1. 在 Agent 配置界面明确展示协作角色、项目 allowlist 和实际生效状态。
2. 在新顶层消息入口提供宿主签发的结构化项目选择，不再要求用户手写 `project_id=…`；是否允许显式的 Channel 默认项目需另行设计和确认，不能从 allowlist 推断。
3. 在线程标题或输入区显示当前绑定项目，并明确提示“新顶层消息不会继承其他线程”。
4. 错误反馈展示本次消息是顶层还是回复、对应 root/event，以及失败发生在哪一层，避免相邻运行记录被误认为同一线程失败。
5. 已完成源码、测试、release 构建与主路径运行验收：受限协作角色的宿主回复发布器只从当前已认证 turn 取得 channel 与 reply root，聚合成功完成的 ACP 最终文本并签名发布一次；错误、取消、空输出、截断输出和确认丢失均有失败关闭或精确事件核验。模型不得提供发送目标，Agent 不持有私钥。真实 Channel 线程已直接且仅显示一条 `U03-HOST-REPLY-OK`。

其余 UX 欠账仍只记录方向。结构化项目选择、绑定可见性及顶层/回复提示在进入实现前必须按融合设计门禁核对依据、安全不变量和验收范围；不得因为宿主回复发布器已经实现，就把这些仍未建设的体验项写成已完成能力。
