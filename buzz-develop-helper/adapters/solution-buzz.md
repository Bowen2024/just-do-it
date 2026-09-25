# Buzz 方案角色接入边界

状态：角色契约、模板、本地 `solution.*` 内核、宿主验签后的角色工具面及 Buzz ACP/MCP 源码注册已实现。solution-mate 已完成临时角色绑定、线程项目持久化恢复和宿主 Channel 回复主路径验证；方案 Draft 保存、恢复、冲突与工具裁剪的完整运行验收仍未完成，因此方案 Agent 尚不可视为生产可用。

## 计划中的唯一规则入口

Buzz 方案角色最终只使用：

- `capabilities/solution.md`：角色职责与停止条件；
- `capabilities/solution-tech-spec-template.md`：统一实现契约结构；
- 宿主按可信角色裁剪后的 `solution.*` 和必要只读工具。

不得加载 Develop Helper 根 Router、自动开发循环或其他会自动派发下游的完整入口。上游 `solution-design` 只作为融合层已经提取的方法来源。

## 计划工具面

| 工具 | 作用 | 当前状态 |
| --- | --- | --- |
| `solution.context` | 读取项目入口及 PRD/方案版本；当前不把确认记录解析成已批准 | 本地、宿主接收端和 Buzz MCP 源码已实现 |
| `solution.save-tech-spec-draft` | 验证 Main 对当前 PRD SHA 的“形成技术方案”确认，再乐观并发保存 `docs/tech-spec.md` 并保留历史 | 本地、宿主接收端和 Buzz MCP 源码已实现 |
| `solution.save-customer-draft` | 用户明确需要时保存 `docs/solution.md` | 未实现 |
| `solution.inspect` | 只读检查 PRD 基线、配置、REQ/AC 引用和覆盖表 | 本地、宿主接收端和 Buzz MCP 源码已实现 |
| `artifact.inspect` / `collaboration.inspect` | 查看 registry、确认和交接事实 | 已有只读内核；尚未授予方案角色 |

方案角色不会获得 `artifact.register`、`confirmation.confirm-current`、`handoff.*` 或下游启动工具。身份、项目、线程和消息由 Buzz 签发信封提供，不出现在模型可控参数中。

## 计划配置原则

- 独立创建 Solution Designer，不改 first-mate/Main，也不复用需求或 Developer 角色身份。
- 绑定允许的项目列表和 `collaboration_role=solution`；一个频道顶层线程只绑定一个项目。
- 工作目录固定为融合层，业务项目路径只由宿主可信 `project_id` 解析。
- 不注入 Agent 私钥，不靠 `buzz messages send` 发送频道回复。
- 普通文字答复必须由 ACP 宿主取得本轮最终输出后，使用已认证的当前 channel 与 reply root 签名发布；模型不能提供、覆盖或沿用其他发送目标。发布失败必须形成用户可见错误，不能只把文本留在 Info。
- 不启用 unrestricted/trusted/bypass 作为接入捷径；通用 shell 必须被宿主文件权限限制。
- 模型可沿用用户选定的 Buzz 现有设置，但模型复用不代表工具权限复用。

## 上线前验收

至少完成以下验证才可改为可用：

1. 临时项目中的 Lite、Standard、AI Draft 保存与恢复；
2. 来源摘要、需求版本、确认用途和覆盖表检查；
3. 并发冲突、软链越界、项目公共锁和中断恢复；
4. 错误项目、同消息多个项目、线程换项目和伪造身份在模型/工具边界被拒绝；
5. 方案角色无法登记、确认、交接、自行选择发送目标或启动下游；普通文字答复由宿主固定发布回当前可信线程；
6. 真实业务项目只有在用户另行授权后才写入。

仅存在本文件、本地测试通过或模型在 Info 中产生最终文本，都不表示方案能力已上线；Channel 中必须能收到由宿主发布的真实回复事件。
