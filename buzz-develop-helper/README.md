# Buzz × Develop Helper 融合基础

阶段：融合基础、本地项目初始化及需求草案工具已实现并通过 39 项测试。单元 02 需求能力已完成范围内建设与 Buzz 回归：角色自动管理 A/R 并隐藏内部保存参数，保存工具校验来源 SHA，`just-start` 已验证三版 Draft、历史保留和文件恢复。当前 v0.3 仍未正式批准；项目成果索引、正式确认、跨角色共享与运行时全局权限属于后续建设。

## 目录

- `config/local.json`：本机路径配置，不提交；其他机器根据示例配置真实路径。
- `upstream/develop-helper`：本地软链，只作显式引用，不自动注册上游入口。
- `upstream-lock.json`：本次上游文件内容及链接指纹。记录版本漂移，不提供不可变快照或安全签名。
- `scripts/check_foundation.py`：Python 标准库只读检查工具，无网络、无上游脚本执行、无文件写入。
- `scripts/project_init.py`：本地项目预览、创建、检查和独立 Git 初始化；写入必须显式指定 `--apply`，不提交、不推送、不调用 GitHub API。
- `scripts/requirements.py`：需求背景读取、带摘要校验的 Draft 保存及旧稿保留，不执行模型调用或正式确认。
- `adapters/`、`capabilities/`：接入与能力边界说明；用户已据此人工创建需求角色，但文件本身不负责自动安装或证明完整运行通过。

需求 Agent 接入见 [人工配置卡](adapters/requirements-buzz.md)，权威方法见 [需求角色规则](capabilities/requirements.md)。用户选择复用 Buzz 现有设置；已观察 Honey 为 Codex + gpt-5.6-sol，配置卡不修改原开发角色，不复制凭据。完整设计及实测边界见 `../fusion-design/02-需求能力.md`。
- `tests/`：在临时目录中验证正常、断链、漂移和配置异常。

## 检查

在本目录运行（Python 3.10+）：

```sh
python3 -B scripts/check_foundation.py check
python3 -B -m unittest discover -s tests -v
```

检查通过只表示路径、项目父目录和锁定内容匹配，不表示 Agent 已共享背景、Git 已同步或上游只读沙箱已部署。工具失败返回非零状态，不会修复链接或刷新锁文件。

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
