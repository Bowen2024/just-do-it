# 项目成果索引与登记预览

状态：首版 schema、只读核对、登记预览、Main-only 一致性写入内核，以及宿主验签上下文到 capability 的融合层适配已实现；当前会话确认与交接内核见 `confirmation-handoff.md`。下游启动未实现；Buzz Rust 宿主尚未产生逐事件上下文。

## 职责边界

- 需求、方案和 UI 角色维护各自成果，回报路径、版本、变化和未决项。
- Main 重新读取真实文件后维护 `project.json` 成果索引与 README 投影。来源角色不能自行登记、确认或启动下游。
- 登记只证明成果存在且版本可核对，不等于正式确认。确认、交接和启动是独立动作。
- `scripts/artifacts.py` 只有 `inspect` 和 `preview-register`，没有 `--apply`。`scripts/main_artifacts.py` 提供不带 CLI 的写入与恢复 API，只接受宿主签发并绑定项目的 Main capability。成果登记本身不读取确认事件、不发送消息、不启动角色，也不执行 Git；确认与交接由独立内核处理。

## project.json 首版兼容结构

保留初始化器已有的 `schema_version: 1` 和 `artifacts` 路径/null 字段，新增 `artifact_registry`。`artifacts` 继续为旧读取者提供当前入口；`artifact_registry` 保存可追溯版本。Main 写入内核按以下契约落盘：

```json
{
  "schema_version": 1,
  "artifacts": {
    "entry": "README.md",
    "requirements": "docs/requirements.md",
    "solution": null,
    "ui": null,
    "decisions": null
  },
  "artifact_registry": {
    "schema_version": 1,
    "confirmations_path": "docs/decisions.md",
    "handoffs_directory": "docs/handoffs",
    "entries": {
      "requirements": {
        "artifact_id": "requirements",
        "kind": "requirements",
        "current_version": "v0.3",
        "versions": [
          {
            "version": "v0.3",
            "content": {
              "type": "file",
              "path": "docs/requirements.md",
              "sha256": "<64位小写十六进制>",
              "size": 1234
            },
            "document_status": "Draft",
            "producer_role": "requirements",
            "purpose": "方案讨论",
            "summary": "本版变化的准确摘要",
            "open_items": [],
            "confirmation_ids": [],
            "availability": {
              "scope": "local-only",
              "git_commit": null
            },
            "registration": {
              "actor": {
                "role": "main",
                "principal_id": "<运行时绑定身份>",
                "authority": "<可信运行环境>"
              },
              "recorded_at": "2026-09-19T12:00:00Z"
            }
          }
        ]
      }
    }
  }
}
```

规则：

- `artifact_id` 使用小写字母、数字和连字符；`kind` 首版仅为 `requirements / solution / ui`。
- 同一成果的 `version` 唯一；同一版本标签不能指向不同摘要。旧版本可以登记但不自动成为 `current_version`，当前入口必须显式选择。
- `confirmation_ids` 为空表示没有正式用途确认。正文的 `Draft` 和 `approval_verified=false` 不因登记而改变。
- `availability.scope=local-only` 时 `git_commit` 必须为空；只有实际提交中的同一内容才可使用 `git-commit`，并记录完整提交 ID。
- `registration.actor` 必须由受控运行时绑定。预览中的占位值不可保存；`inspect` 会拒绝把占位预览冒充正式登记。当前内核具备 capability 校验，宿主签发适配尚未接通。
- README 仅是 `artifact_registry` 当前入口的投影。工具使用带标记的托管块，首次迁移只删除初始化器的固定“当前没有成果”占位句，保留其他手写内容。

## 多文件成果清单

UI 等集合成果通过项目内 UTF-8 JSON 清单固定成员：

```json
{
  "schema_version": 1,
  "entrypoint": "ui/index.html",
  "files": [
    {
      "path": "ui/index.html",
      "sha256": "<文件实际 SHA-256>"
    }
  ]
}
```

预览会校验清单、入口、成员路径和每个摘要；目录名、截图或清单自身存在都不能代替成员验证。首版单个元数据文件上限 128 KiB，单个成果文件上限 32 MiB；均拒绝绝对路径、越界路径、软链和多硬链接文件。

## 只读命令

```sh
python3 -B scripts/artifacts.py inspect <PROJECT_ID>

python3 -B scripts/artifacts.py preview-register <PROJECT_ID> \
  --artifact-id requirements \
  --kind requirements \
  --version v0.3 \
  --producer-role requirements \
  --purpose "方案讨论" \
  --summary "本版需求摘要" \
  --path docs/requirements.md \
  --set-current
```

`inspect` 核对已登记版本、默认候选成果和 README 投影。`preview-register` 输出成果摘要、旧兼容字段变更、拟议 registry、README 完整预览和 diff，以及写入必须满足的乐观摘要前提。用户不需要运行这些内部命令或提供 SHA；Main 负责取得并解释预览。

不带 `--set-current` 时只预览历史登记，不改变当前入口。没有面向 Agent 或用户的写入命令；宿主适配器取得预览摘要后，才可调用 Main 内核。

## Main-only 写入与恢复

`scripts/main_artifacts.py` 的 `apply_registration` 和 `recover_registration` 是宿主适配 API，不是 CLI：

- 调用者必须提交由受信宿主签发、绑定 Main principal、authority 和允许项目集合的 capability。字典、消息中的 `role=main`、环境变量及错误项目授权都会被拒绝。
- 写入前在同一把 `.project-state.lock` 内重新读取并校验 `project.json` 和 README 的预期 SHA-256，再重新生成预览。需求 Draft 保存和 Git 初始化元数据更新也使用该公共锁。
- `project.json` 与 README 分别使用同目录临时文件、`fsync` 和原子替换。写入前先持久化 `.project-state-transaction.json`，其中保存文件写入前后的字节快照与摘要；确认和交接事务复用同一日志入口。
- 进程在两文件之间中断时，Main 恢复 API 只接受仍等于事务前或事务后摘要的文件，并一律前滚到事务后状态。发现事务外编辑便停止，保留日志，不覆盖新内容；锁或日志来源未知时也不自动删除。
- 写入完成后重新运行 registry/README 一致性核对，成功才删除事务日志。重复应用同一登记返回 `unchanged`，不产生重复版本。
- 登记不会改变 Draft、创建确认、生成交接、启动下游或执行 Git；返回值明确标记 `approval_changed=false`、`handoff_started=false`。后续确认必须单独调用 `main_collaboration.py` 的宿主 API。

该 capability 是工具调用边界，不是操作系统安全边界。生产适配通过 `authorization_from_host_context` 使用已验签上下文；`_issue_runtime_main` 只保留为测试钩子。Buzz/Codex 尚未产生真实逐事件信封。拥有通用 shell 或文件编辑权限的 Agent 仍可绕过本模块，因此上线前还需配置运行时工具暴露与文件权限并做拒绝验证。
