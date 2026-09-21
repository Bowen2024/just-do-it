# 当前会话确认、固定快照与交接

状态：本地 Main-only 内核、只读核对、宿主信封验签和角色工具裁剪已实现；真实 Buzz/Codex 协作信封已接入，保留字段和角色工具面拒绝已实测。混合批次仍只按最后事件建立 claim，逐事件项目/线程边界未通过；实际交接消息及业务项目验收尚未接入。

## 独立动作

以下动作互不替代，也不自动串联：

1. 成果登记证明某个路径和版本存在。
2. 当前会话确认记录用户针对已展示版本允许的具体用途。
3. 交接准备固定接收者、输入、用途、允许动作和预期输出。
4. 发送记录只证明受信消息提供方报告已发送。
5. 接收核验要求指定接收身份回报实际读取的确认 ID 与内容 SHA。
6. 开始执行仍是独立授权和调度动作；本能力不启动下游。

## 当前会话确认

`scripts/main_collaboration.py` 的确认入口同时要求：

- 绑定项目的 Main capability；
- 宿主签发的当前会话确认依据，包含用户 principal、provider/authority、会话和消息 ID、时间、原话、成果 ID、版本、展示内容 SHA、允许用途、确认范围、非授权事项和阻塞未决项；
- `project.json`、README 和 `docs/decisions.md` 的乐观摘要前提。

有阻塞未决项时拒绝正式确认。成功后：

- 在 `docs/decisions.md` 的受管 JSON 块中追加确定性确认 ID；相同消息、成果、版本和用途重复调用不重复记录。
- 在 `docs/confirmations/snapshots/` 创建内容寻址快照。单文件登记版本改指向固定快照，原工作文件可继续形成下一版；文件集合保存原清单和每个成员的固定副本。
- `project.json.artifact_registry` 对应版本只追加确认 ID，README 投影同步显示；成果正文的 `Draft` 和 `approval_verified=false` 保持不变。
- 多文件事务使用公共项目锁和持久日志，中断后只前滚仍与事务前/后摘要匹配的文件。

当前只实现 `current-session` 依据。`provider-read` 的 Buzz 签名事件回读仍待接入；转述、截图或 Agent 自述属于 `reported-unverified`，不能调用正式确认入口。

## 交接记录与接收回执

交接输入首版只接受已存在且用途完全匹配的有效确认 ID，不接受任意路径或“最新版本”描述。记录保存在 `docs/handoffs/<handoff-id>.json`：

- `prepared`：用户当前会话已授权准备交接，记录指定接收 principal/authority、确认快照、用途、允许动作、预期输出及是否授权执行；未发送、未启动。
- `sent`：受信发送提供方绑定消息 ID、时间和实际目标；仍不等于接收成功。
- `received-verified`：指定接收身份回报每个确认 ID 和实际内容 SHA，并复述目标、范围和未决项；错误身份、旧版本或摘要不符均拒绝。

即使交接记录中的 `execution_authorized=true`，本内核也只记录授权事实，返回 `downstream_started=false`。实际消息发送、角色启动、重试和工程状态由后续宿主/Main 调度能力负责。

## 工具边界

- `scripts/collaboration.py <PROJECT_ID>` 是只读核对入口，验证确认引用、快照和交接记录，不发送消息。
- `scripts/main_collaboration.py` 没有写入 CLI。生产适配使用 `*_from_host_context` 从已验签上下文构造依据；`_issue_*` 方法只保留给既有临时测试。模型、普通 Agent、CLI 参数、环境变量或文档不能自行签发可信依据。
- Python 私有名称不是操作系统隔离。上线前仍需由宿主只向认证 Main 暴露写入入口，并只向指定接收者签发回执身份，同时限制通用 shell/编辑器绕过。
- 当前自动化测试只使用临时项目；不得据此把 `just-start` v0.3 写成已确认或已交接。
