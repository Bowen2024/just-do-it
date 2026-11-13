# UI 第 5 步 · 批次 1（S5-00＋5A）开发自验报告

- schema_version：1
- contract_version：ui-tools-v1
- 阶段：step5_gate1_S5-00_5A_read_only（基线/夹具/账本＋固定依赖、只读 stdio 三工具）
- 生成时间：2026-11-03（Asia/Shanghai）
- 执行环境：Python 3.13.3（/Library/Frameworks/Python.framework/Versions/3.13/bin/python3），macOS 26.6.2 arm64；git 2.52.0；HEAD f33f9e6
- 证据：`workflows/UI/verification/step5-gate1-test-output.txt`、`step5-test-results.json`

> 本文件是开发自验，不是 Honey 的独立验收结论。门 1 结论只可能由 Honey 独立下；开发状态为 `DEV_READY_FOR_REVIEW`。

## 1. 范围与交付物

门 1 严格只读：`ui_read_context`、`ui_inspect(current|transaction)`、`ui_read_history` 三个只读工具；写工具名被识别并拒绝。`--allow-write` 六工具、候选准备/导入/检查、接收/版本/回执/恢复及完整写主线全部留到门 2（5B/5C），本批未实现、未占位空响应。

正式源码（`workflows/UI/`，标准库 only）：

| 文件 | sha256 |
| --- | --- |
| mcp_server.py | ef42d38d220b918e405b4f5619a0621f225d8552df3d5b0d21d03acf2b29543d |
| shared_loader.py | c15d0f1e1203482694e2775859b405258bbe0553fd49010f4be5e1b56c24ffaf |
| file_tools/__init__.py | 9e6cba607facbb991a58c766371388385481f70d61929240fc37f1ef15a5cba7 |
| file_tools/context.py | 3797758f34e0e4b753d54db9734e4533061a74387c0f17351a2541ff07c33611 |
| file_tools/versions.py | 3aa3a9f39dad941377d24fba3d629a509830c5f0d3def2a513985a0d0b6ff853 |
| file_tools/transactions.py | ae03763b1bf3b2651877fd3d1c0a0c59d0785be3ec5251c36388fbf407bce191 |

测试（`fusion-runtime/tests/`）与辅助：

| 文件 | 函数数 | sha256 |
| --- | --- | --- |
| ui_test_support.py（辅助：临时夹具/受控加载/子进程/静态 H/静态事务） | — | 9461ddf556dd61c9f6e7fe652de5ed17b72fad461287b9214efc0350e1b25bef |
| test_ui_fixtures.py | 13 | 1b8ff2c3699781f06597612c896f249f3fe531e4ec78d6a11a8216ecfa586b37 |
| test_ui_context.py | 25 | 79aaf2a391e2050f049b0446d663dd9a7d61d8710bb533bda1f9debc8461326d |
| test_ui_history.py | 9 | 7f5add29150bc7439acbaaed26b6bb13c2c4fcea2958c1167b228b9e182e127d |
| test_ui_transactions.py | 12 | bcc1b5d2c0842154864ee8722aa157cee2de310e6b585f961082c96ed1db79a3 |
| test_ui_stdio.py | 10 | 96c14d85ba88f2c0f03797246aba4f1432193f490705cf8a7c2f177906c0456e |
| test_ui_isolation.py | 2 | e3b6bd2cc543384f92737de2c8bae91d3a3c4cb5cc5188afca2eaec402f1b673 |

## 2. 真实命令与结果（当轮实测）

```sh
# 工作区根：.../vibe- coding
python3 -B -m unittest discover -s fusion-runtime/tests -p 'test_ui_*.py'
# Ran 71 tests … OK，进程退出码 0；重复运行与模块逆序结果一致，sys.modules 注入残留 0
```

- 发现/执行：发现即执行 **71/71**（13+25+9+12+10+2），无跳过、无零发现。
- 固定依赖探针：`verification/verify_runtime_dependencies.py --output <tmp>`，22 项检查全过，含净化 `-I -S -B` 子进程 normal/missing-module 两场景，退出码 0。
- 真实子进程：`test_ui_stdio.py`（普通 `-B` 新进程）、`test_ui_isolation.py`（`-I -S -B` 净化新进程）均解析真实 JSON-RPC 响应，非函数直调。
- 完整原始输出见 `step5-gate1-test-output.txt`。

## 3. 门 1 验收项对照

- AC5-00：可运行实现＋正式测试＋运行环境齐备；标准入口 71/71、退出码 0；来源/闭包探针 22 项通过。
- AC5-01 只读侧：真实 stdio 握手（新协议 2026-07-28＋旧协议）→ `tools/list` 恰为三工具 → 只读调用成功；直接构造 `ui_prepare_revision/ui_accept_revision/ui_recover_revision` 均 `tool_not_enabled`、`write_outcome=not_written` 且项目树零新增；未握手/坏协议/未知方法/坏 JSON/>1 MiB 分别返回协议级错误码。
- 凭证：两个独立新进程签发的 `read_id` 互不相同，项目/状态目录中无令牌落盘，重启后旧令牌不复用（内存、按进程、不跨进程）；写侧消费/过期留门 2。
- AC5-02：空项目 `state=empty/current.kind=none` 发 read_id；完整闭包、读取中途变化 unstable/read_id=null、非法 UTF-8 不可读不伪装 missing；legacy/不支持布局/未托管目标、路径/软链/NFD/大小写折叠拒绝；只读前后整树一致（目录/锁/缓存/字节码零新增）。
- read_history：仅用静态 H 夹具，列表排序（时间降序、SHA 升序）、游标/分页、packet+成员+清单摘要核验、损坏/缺失 `history_invalid/history_not_found`；**静态 H 不是保存成功证据**。
- 事务只读检查：静态事务夹具覆盖 not_activated/staged/applying/interrupted/committed 分类、before/after 证据、活动指针、坏计划/身份不符/非法 id；只读零副作用，不执行 resume/rollback。
- AC5-14 已实现路径：`-I -S -B` 净化新进程中于 PYTHONPATH 放置同名 `shared_loader.py`、`file_tools/` 与 `sitecustomize.py` 诱导（命中即落标记并抛错），读主线仍成功且标记文件不存在；UI 安装副本与受信 foundation 均无 `__pycache__/.pyc`；未授权 import root 在净化进程中 `path_not_allowed`。

UI-T 主编号门 1 汇总（逐项测试函数映射见 `step5-test-results.json`）：**完整通过 10（T01/T03/T04/T06/T08/T26/T27/T45/T46/T47），部分覆盖 10（T02/T05/T07/T09/T11/T12/T16/T17/T43/T44），未运行 27（写侧/恢复 T10/T13–15/T18–25/T28–42），失败 0**。部分项均写明门 1 已验子场景与门 2 待验项，未以部分记整项通过；AC5-13 系统故障矩阵留第 6 步。

## 4. 本轮修复（在既有 5A 实现上）

1. 历史并列时间戳分页测试修正：实现按契约（`created_at` 降序、SHA 升序，见实施说明 §5.7）正确，测试第二页误用变量 `second` 而非并列 SHA 的较后者；已改为按契约计算，属测试修正，未改实现。
2. 测试夹具 `sys.modules` 跨用例污染：原别名用 `id(self)`，TestCase 回收后 id 复用且 teardown 不清理，导致从已删临时目录重载 `project_init`。改为进程内唯一 token + teardown 清理注入模块；现重复/逆序运行稳定，注入残留 0。
3. 净化启动：`python -I`（隐含 `-P`）不把脚本目录加入 `sys.path`，致 `from shared_loader import ...` 失败。`mcp_server.py` 在导入前显式前置**本文件真实安装目录**（受控路径，非 cwd/PYTHONPATH 回退），并同步 `SOURCES.json` 的 `runtime_sources.mcp_server.py` 采用摘要。

## 5. 写范围与未触碰

- 仅改 `workflows/UI/` 与 `fusion-runtime/tests/test_ui_*.py`、`ui_test_support.py`，及本模块 verification 证据；所有写入/损坏/恢复实验均在系统临时项目。
- 未改共享九模块、Develop_Helper、上游锁、真实业务材料、外部候选、真实客户端/全局配置；未做任何 git mutation；未安装依赖、未启动其他 Agent。

## 6. 已知失败（与本批无关，超出写范围，未修改）

全量 `discover -p 'test_*.py'`（268 项）有 **7 项失败，全部在 requirements 模块的 `test_requirements_localization.py`**：
- 该模块**零 UI import**；**单独运行同样 7 失败**（23 项），与 UI 改动无关。
- 触发物为预存迁移残留 `workflows/requirements/config/migration-backups/20261102T062029639617Z`，目录 mtime 为 **2026-11-02 14:20（本批 UI 工作之前）**，真实树守卫要求其不存在。
- 该目录属于共享 requirements 树（§1.2 禁止区），我未删除、未修复；请 Bowen 决定是否另开任务清理/复验。

## 7. 下一任务（门 2，待授权推进）

5B 候选准备/五文件导入/候选检查；5C 接收/版本/回执/基本恢复/完整六工具主线（含 `--allow-write` 重启六工具、read_id 消费与跨进程/来源变化拒绝、T33–T42 最低保护集），完成后按门 2 全量回归与 UI-T01—T47 账本再送 Honey。
