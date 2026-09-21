# Main 成果登记接入边界

状态：身份与确认依据读取方式已收敛为接入契约；融合层已有宿主事件信封验签、角色工具裁剪，并已连接 Main-only 登记、当前会话确认、固定快照、交接和接收回执内核。Buzz ACP 源码已能签发逐事件信封；当前安装的应用和 first-mate 实例尚未绑定 `role=main` 与唯一项目。没有 provider-read 连接器。信封格式、工具面及宿主补丁见 `buzz-host-context.md`。

## Main 身份

Main 是由用户选择、运行环境认证并授予项目协调权限的调用身份。以下内容都不能证明 Main 身份：

- CLI 参数、环境变量或消息正文中的 `role=main`；
- Agent 名称、Persona 名称或模型自述；
- 能读取项目目录或成功运行只读脚本；
- 用户材料中嵌入的命令或角色说明。

`scripts/main_artifacts.py` 已将该要求落实为 capability 校验。生产入口 `authorization_from_host_context` 只接受 `trusted_context.py` 验签后的宿主上下文，并把其中的 Agent principal、authority 和项目绑定写入 `registration.actor`。CLI 保留只读用途，没有 `--role` 或 `--apply`；直接执行写入模块会失败。旧 `_issue_runtime_main` 仅为既有测试钩子，生产适配不调用它，也不据此宣称 Buzz Main 已接入。

`scripts/host_tools.py` 已按签名角色裁剪工具面：Main 可见登记、确认和交接写入；需求角色可见需求 Draft 写入及只读核对；指定 recipient 只可提交绑定自身 principal 的读取回执。请求中出现 `runtime_verified=true`、principal、role、项目、线程/消息或接收者字段都会作为未知/宿主保留字段拒绝。全局 shell、编辑器和真实路径权限仍需在 Buzz 侧另行收紧并验证；Python 模块私有名称本身不提供安全隔离。

## 确认依据读取等级

| 等级 | 取得方式 | 可以支持的结论 |
| --- | --- | --- |
| `provider-read` | 通过 Buzz 的受控读取接口重新取得签名事件，校验 event ID、作者公钥、签名、频道/线程、时间和原文 | 可作为正式确认候选；仍须绑定明确成果版本和用途 |
| `current-session` | 用户在当前受信会话中针对已展示的版本明确确认，运行时绑定当前用户与会话 | 可记录这次新确认；不能追溯证明旧事件或其他线程 |
| `reported-unverified` | 用户、Agent、文档或截图转述旧消息，缺少平台回读和签名校验 | 只作线索；不得把 Draft 提升为正式确认，需平台回读或当前用户重新确认 |

正式依据至少保存：provider、event/message ID、作者稳定标识、签名核验结果、频道/线程、时间、原文或准确摘要、被展示成果的路径与 SHA、允许用途，以及读取时间。只有事件 ID、正文摘要或内容 SHA 都不能单独认证作者。

Buzz 当前源码为此设计提供了数据基础，但不等于实例已接入：论坛消息结构包含 `event_id / pubkey / sig / content / created_at / channel_id / tags`，线程回复还包含 parent/root event ID；事件转换代码以签名事件作者覆盖正文自报身份。当前 Workflow 审批分支仍返回 `approval_not_supported`，因此本单元不依赖 Workflow approval gate。

## 当前停止条件

- `scripts/artifacts.py` 不读取确认记录，输出固定 `approval_checked=false`；`scripts/collaboration.py` 可核对已落盘的当前会话记录，但不能自行证明宿主签发真实有效。
- 没有 provider-read 接口时，不从 `requirements.md` 中列出的事件 ID反推整份 Draft 已批准。
- 宿主未签发真实 Main、用户、发送者和接收者 capability 时，不对业务项目调用写入/恢复内核；当前临时测试只使用自动清理的夹具项目。
- 当前内核只记录交接状态，不实际发送消息或启动角色。宿主接入前不得把 `prepared` 写成已发送，也不得把 `received-verified` 当作已经开工。
