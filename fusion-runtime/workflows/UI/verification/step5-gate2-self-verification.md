# UI 第 5 步 · 门 2（S5-C1—C5）开发自验报告

- schema_version：1
- contract_version：ui-tools-v1
- 阶段：step5_gate2_accept_versions_receipts_recovery_complete_mainline
- 生成时间：2026-11-03（Asia/Shanghai）
- 执行环境：Python 3.13.3，macOS 26.6.2 arm64；git HEAD f33f9e6
- 实测输出：`fusion-runtime/workflows/UI/verification/step5-gate2-test-output.txt`
- 逐项账本：`fusion-runtime/workflows/UI/verification/step5-test-results.json`
- 主线证据：`fusion-runtime/workflows/UI/verification/step5-smoke-evidence.json`

> 本文件只记录开发自验，不是 Honey 的独立验收结论。门 1 与 5B 中间检查点已分别获 Honey REVIEW_ACCEPTED；门 2 仍需独立验收。文件接收不证明浏览器、视觉、业务、正式确认、真实客户端或工程放行通过。

## 1. 最终目标、本阶段交付与停点

最终目标是让隔离临时项目实际完成“读取 → 准备候选 → 普通编辑 → 检查 → 受控接收 → 复读 → 历史”，并对越界、来源／候选／目标变化、未登记覆盖、重复请求及中断状态提供可核验保护。

本阶段已完成步骤 5 的实现与开发自验范围：六工具 stdio、不可变版本、逐文件接收、持久回执、显式恢复、完整临时项目主线和真实新进程隔离证据均已落地。完成后停在门 2 送验，不进入第 6 步系统故障矩阵、第 8 步独立验证身份或第 9 步真实客户端试点。

## 2. 实际交付

- `ui_accept_revision`：公共锁内先核对持久回执，再复核 inspection_id、完整候选、来源、目标、登记引用、未知文件与精确 delete_paths；首次／后续／legacy 接收、增删改、unchanged、saved、请求回放及并发目标冲突均按契约处理。
- 不可变版本：规范 packet 将成果与来源共同纳入内容身份，时间不进摘要；完整版本 tree 包含成员与公共清单快照；旧 managed 版本完整保留，合法无指针 legacy 在首次接收前归档。
- 事务与恢复：固定 plan.json、逐目标 before/after 字节和摘要，活动日志后才允许公共写入；成员 → 清单 → 指针逐文件原子替换；复读 document_set/manifest/pointer/history/inputs/unknown_files 六项；显式 resume/rollback，不自动回滚、删锁或覆盖 other。
- 回执：prepare/accept/recover 共用 request_id 绑定与持久终态／未完成记录；相同准确请求 replay 不重复写，改参／换操作 request_reused，坏回执 receipt_invalid；真实进程重启后 accept 回执仍可回放并独立报告实际 current_revision。
- `mcp_server.py`：只读恰三工具，`--allow-write` 恰六工具；accept/recover schema、条件字段、类型、request_id 和业务错误封装已接通；无 force/fail_after/inspection_ok/确认布尔后门。故障注入仅为进程内测试 failpoint。
- 测试与证据：新增 `test_ui_accept.py` 21 项、`test_ui_recovery.py` 12 项；扩充 workspace/stdio/isolation/inspect 及公共测试辅助；完整主线、写范围、恢复、重启回放和 `-I -S -B` 证据均可复跑。

## 3. 本轮实修问题

- 已接收工作区因公共目标按预期前进而误报 target_changed；现 candidate_closed 只读关闭且不签新 inspection_id，开放候选仍严格复核来源和目标。
- 预激活失败错误缺少 transaction_id；现返回请求、候选和事务引用，可 inspect 后显式关闭私有记录。
- 首次创建 rollback 将缺失公共清单误判失败；现空集合前像按 missing 核验。
- 已有集合部分写入后，恢复前的来源复读误把混合公共状态当普通 current；现来源闭包与事务目标分类分开，known before/after 才能 resume/rollback。
- 中断错误补齐 request_id/revision_id/transaction_id；重启测试遗留子进程已正常关闭。

## 4. 送验源码摘要

| 文件 | SHA-256 |
| --- | --- |
| `fusion-runtime/workflows/UI/mcp_server.py` | f7f238f7e23fefe8a648b85f785004762b234586a709c4e4db4000140689b7b3 |
| `fusion-runtime/workflows/UI/shared_loader.py` | c15d0f1e1203482694e2775859b405258bbe0553fd49010f4be5e1b56c24ffaf |
| `fusion-runtime/workflows/UI/file_tools/__init__.py` | 9e6cba607facbb991a58c766371388385481f70d61929240fc37f1ef15a5cba7 |
| `fusion-runtime/workflows/UI/file_tools/context.py` | 1302955037294fcf16f073d4c76b2f6e7a8abd36785adf32320c3ce624199383 |
| `fusion-runtime/workflows/UI/file_tools/workspace.py` | c22e462c1dcd39cfa489d0df346bf3e760f9e7d4261f984b2241bf300cd04b7f |
| `fusion-runtime/workflows/UI/file_tools/versions.py` | 8e52b3ce630e300a7657251aa41457da4535aeb0e6c2fe2a226c6e2986a071ed |
| `fusion-runtime/workflows/UI/file_tools/transactions.py` | 191d059cfaf5cb9c67d8bd00a6494759332ce49ef1ea6113d384d6a76803e1f1 |

上述摘要与 SOURCES `runtime_sources` 逐项一致；账本使用仓库相对路径。标准库 only，无新增依赖。

## 5. 当轮真实命令与退出码

```sh
python3 -B -m unittest discover -s fusion-runtime/tests -p 'test_ui_*.py'
# Ran 153 tests；OK；退出码 0；跳过 0、失败 0、错误 0

python3 fusion-runtime/workflows/UI/verification/verify_runtime_dependencies.py --output <tmp>
# checks=22，passed=true，failed_checks=[]；退出码 0

python3 -B -m unittest discover -s fusion-runtime/tests -p 'test_*.py'
# Ran 350 tests；FAILED (failures=7)；真实退出码 1
```

UI 测试分解：fixtures 13、context 25、history 9、transactions 12、workspace 21、inspect 21、accept 21、recovery 12、stdio 15、isolation 4，共 153。

全量 7 个失败全部位于 `test_requirements_localization.py`，与门 1／5B 相同；触发物 `workflows/requirements/config/migration-backups` mtime 为 2026-11-02 14:20:29，早于本任务授权。该模块零 UI import，属禁止修改区，本轮未清理或修复，是否另开任务仍由 Bowen 决定。

## 6. 主线、恢复与隔离证据

- `step5-smoke-evidence.json` 来自系统临时中文项目的真实调用：empty prepare → 普通编辑 → candidate inspect → saved accept → current/history 复读 → unchanged → V2 修改删除 → 旧回执 replay；含实际 revision、changes、verification、清单／指针／版本目录和保护树快照比较。
- 另一组真实接收覆盖 current/history/import、legacy 归档、登记直接／间接引用、固定快照、锁与 Main 根事务；所有测试项目、导入源和损坏注入均在系统临时目录。
- AC5-12 最低集已执行：pre_activation、partial_resume、partial rollback（首次与已有集合）、source_changed、third_party_other、saved_receipt、invalid_plan/evidence；另覆盖 saved_unverified、incomplete replay 与 recover receipt replay。
- 真实 stdio 子进程验证六工具和重启回执；`-I -S -B` 净化进程在 PYTHONPATH 同名 workspace/transactions 诱导下完成接收及中断 resume，无诱导加载、无字节码。

## 7. UI-T 主编号账本

- passed：33。
- partial：14（T02、T05、T07、T33—T43）。
- not_run：0；failed：0。
- T33—T42 的 partial 是第 6 步完整系统矩阵未跑，不冒充整项通过；本步要求的最低保护集均已通过。T43 的最终全面文档校准仍按第 7 步执行。T02/T05/T07 保留原清单中未全覆盖的组合分支。

## 8. 写范围、远端状态与未验证边界

- 修改仅限 `fusion-runtime/workflows/UI/`、`fusion-runtime/tests/test_ui_*.py` 与已申报的 `fusion-runtime/tests/ui_test_support.py`；未改共享九模块、Develop_Helper、上游锁、真实业务材料、外部候选、真实客户端或全局配置。
- 无 git mutation、无提交／推送、无依赖安装、无其他 Agent 启动。远端没有由本任务产生的新状态；可复验证据为上述本地源码摘要、测试输出、账本和真实主线 JSON。
- 未验证：第 6 步完整故障矩阵、页面浏览器／视觉／业务结论、正式登记／确认／交接、真实客户端安装与端到端试点。门 2 结论只能由 Honey 独立验收后给出。
