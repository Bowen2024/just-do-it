# UI 第 5 步 · 5B（S5-B1＋B2）开发自验报告（中间检查点）

- schema_version：1
- contract_version：ui-tools-v1
- 阶段：step5_5b_candidate_workspace（候选准备/五文件导入/候选完整检查/检查凭证）
- 生成时间：2026-11-03（Asia/Shanghai）
- 执行环境：Python 3.13.11（miniconda，与 Honey 门 1 基线同版本），macOS 26.6.2 arm64；git HEAD f33f9e6
- 证据：`workflows/UI/verification/step5-gate5b-test-output.txt`、`step5-test-results.json`

> 本文件是开发自验，不是 Honey 的独立验收结论。5A/门 1 已经 Honey REVIEW_ACCEPTED（findings 0）；5B 按 Bowen 2026-11-03 02:29 UTC「不要一次性完成再汇报」的指示作为中间检查点送验。写侧接收/恢复（5C）尚未实现，本报告不代表第 5 步完成。

## 1. 范围与交付物

- B1：`ui_prepare_revision` 四模式（empty/current/import/history）。公共锁（复用 `project_state.project_state_lock`）内复核 read_id 基线、Main 根事务、UI 活动事务、请求回执与 8 个工作区配额；消费 read_id 后在 `ui/.ui-state/work/R-<32hex>/` 固定 `base.json`（来源/目标完整描述、目录清单、base_digest、运行基线、restored_from、import 视图）、可编辑 `candidate.json` 与 `tree/`；持久 prepared 回执，相同 request_id＋准确参数回放原工作区（receipt_replay，不消费令牌、不建第二工作区）；incomplete/损坏回执分别 operation_incomplete/receipt_invalid。公共成员、清单、指针全程不变。
- 导入：仅复制 read_id 已固定的明确文件，五行映射与契约 §5.2 一致；根授权、密钥/缓存件、映射冲突、read 后来源变化分别拒绝；原导入树前后字节不变。
- B2：`ui_inspect(target=candidate, revision_id=R-…)`。核对候选身份、不可编辑基线、实际 tree 对 candidate.json 声明（固定排除 .DS_Store），检查入口（本地 .html）、设计说明、演示 README、成员类型/限额（256/32MiB/64MiB/128KiB）、added/modified/removed，重算 base/sources/targets 并在准备后来源变化时 source_changed、当前成果变化时 target_changed；通过才签发进程内 inspection_id（绑定 revision、removed、base/candidate digest、运行基线，15 分钟有效）；浏览器证据固定 diagnostics 未验；终态接收回执存在时 candidate_closed、不签新凭证。
- `mcp_server.py`：新增 `--allow-write`（默认关闭）。只读启动仍恰三工具；allow-write 下列四工具（多 prepare），accept/recover 名仍 tool_not_enabled「5C 开放、无空响应占位」；prepare schema 与业务错误分层。
- 标准库 only；无 force/fail_after/确认布尔后门。

正式源码（`workflows/UI/`）：

| 文件 | sha256 | 门 1→5B |
| --- | --- | --- |
| mcp_server.py | 1dcab9670fc558183c98fd09c9daf35e18fc3cee478d691a8c61fab7f11bede0 | 改（开关/接线/schema） |
| shared_loader.py | c15d0f1e1203482694e2775859b405258bbe0553fd49010f4be5e1b56c24ffaf | 未变 |
| file_tools/__init__.py | 9e6cba607facbb991a58c766371388385481f70d61929240fc37f1ef15a5cba7 | 未变 |
| file_tools/context.py | ab30eea5a88be1e791a7ae8cdf8665ceab2bbba370e134addca0fc728a3825cd | 改（凭证扩展/委派） |
| file_tools/workspace.py | 8fe6fe7c8193c5613b0dbc82f1dfe492b353896259f7c595cce894da15981cfe | 新增 |
| file_tools/versions.py | 3aa3a9f39dad941377d24fba3d629a509830c5f0d3def2a513985a0d0b6ff853 | 未变 |
| file_tools/transactions.py | ae03763b1bf3b2651877fd3d1c0a0c59d0785be3ec5251c36388fbf407bce191 | 未变 |

测试（`fusion-runtime/tests/`）：新增 test_ui_workspace.py（20）、test_ui_inspect.py（21）；test_ui_stdio.py 10→13、test_ui_isolation.py 2→3；ui_test_support.py 加 allow-write 连接/进程与 prepare 辅助。

| 文件 | 函数数 | sha256 |
| --- | --- | --- |
| ui_test_support.py | —（辅助） | daa9dfa12f0a1a31bf2933eed279ab99cba27e0e433a5e02e513d117f1b1ebdd |
| test_ui_workspace.py | 20 | 1ae50043fc620bd84b9c009c2769461fc40d4f9391dd021d4e887b44fbe14a2c |
| test_ui_inspect.py | 21 | 2a955a4a96f7548619addead2f820912a6a7c13713c0b47eee2c9ab010e7f2ab |
| test_ui_stdio.py | 13 | de20596289feed883def6c3aabf4be6afb3a972e041247a523d80016238e76ca |
| test_ui_isolation.py | 3 | 35e67a74ccaaea268e7f32ea38d55b12473d48059d3b7b37f24e8f11a7bb848a |

## 2. 真实命令与结果（当轮实测）

```sh
# 工作区根：.../vibe- coding
python3 -B -m unittest discover -s fusion-runtime/tests -p 'test_ui_*.py'
# Ran 116 tests … OK，退出码 0；重复运行一致
# 13+25+9+12+13+3+20+21 = 116，无跳过、无零发现
python3 fusion-runtime/workflows/UI/verification/verify_runtime_dependencies.py --output <tmp>
# {"passed": true, "checks": 22, "failed_checks": []}
python3 -B -m unittest discover -s fusion-runtime/tests -p 'test_*.py'
# Ran 313 tests … FAILED (failures=7)，真实退出码 1
```

7 个失败仍全部在 `test_requirements_localization.py`（与门 1 同 7 项），该模块零 UI import、单跑 23 项同样 7 失败；触发物 migration-backups mtime 2026-11-02 14:20，早于本任务授权，属 §1.2 禁止区，未删除未修复。

净化新进程：`test_ui_isolation.py` 在 `-I -S -B` allow-write 子进程放同名 `file_tools/workspace.py` 诱导（命中即落标记并抛错），prepare(empty) 成功且标记文件不存在、安装副本无字节码。

## 3. UI-T 账本变化（主编号，逐项映射见 step5-test-results.json）

门 1：passed 10 / partial 10 / not_run 27 / failed 0。
5B 后：**passed 17（新增 T10、T11、T12、T13、T14、T16、T19）/ partial 15（新增 T15、T17、T18、T20、T25、T28、T30、T31、T32、T44；其中 T11/T12/T16 由 partial 转 passed）/ not_run 15（T21–24、T29、T33–42）/ failed 0**。

- T10：empty/current 准备、模式组合、history 条件字段、base/candidate 事实、公共零改动。
- T11：五文件五行映射、外部树字节不变、非软链。
- T12：未授权根/未列入口/.env/映射冲突/read 后改导入 JS 全部拒绝。
- T13：ready 稳定性、proposed_revision_sha256=规范 packet SHA、二进制身份、removed。
- T14：缺失/未列/缓存排除/32MiB/256 成员/128KiB 声明/64MiB 总量/损坏声明。
- T16：inspect 三 target 只读，多次检查整树快照一致。
- T19：子进程重启后旧 read_id 失效、按 revision_id 重检签新 inspection_id；终态回执后 candidate_closed；prepared 回放不因 tree 合法编辑误判损坏（回放返回准备时 candidate_digest）。
- 仍 partial 的写侧/接受分支（T15 完整走查、T17 accept 跨用、T18 accept 时消费与 128 上限、T20 复制中断注入、T25 accept 阶段、T28 历史真实接收、T30/T31 写侧回执、T32 accept 并发、T44 六工具全参数矩阵）留 5C；T33–T42 系统故障矩阵留第 6 步。

## 4. 写范围与未触碰

- 仅改 `workflows/UI/`（新增 workspace.py、context.py、mcp_server.py、SOURCES.json、README、开发方案任务表、verification 证据）与 `fusion-runtime/tests/test_ui_*.py`、`ui_test_support.py`；所有写/损坏试验在系统临时项目。
- 未改共享九模块、Develop_Helper、上游锁、真实业务材料、外部候选、真实客户端/全局配置；无 git mutation；未装依赖、未启动其他 Agent。
- SOURCES `runtime_sources.stage` 更新为 `step5_5b_candidate_workspace_implemented`，新增 workspace.py 采用摘要；七枚运行源码哈希与磁盘逐一对应。
- 真实 UI 树已清掉陈旧 `__pycache__`（保持门 1 零字节码不变量）。

## 5. 已知差距与下一任务

1. 5C 未实施：不可变版本写入、事务计划/before-after、`ui_accept_revision`（unchanged/saved/冲突/登记引用/删除集）、`ui_recover_revision`、请求终态回执与并发，完成后跑门 2 全量回归并再送 DEV_READY_FOR_REVIEW。
2. 全量回归 7 个既有 localization 失败仍等 Bowen 拍板是否另开清理任务（与门 1 结论一致，不阻塞 5B）。
