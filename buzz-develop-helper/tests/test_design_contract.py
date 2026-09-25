"""Design-gate checks use only disposable files and never modify source documents."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_design_contract.py"
spec = importlib.util.spec_from_file_location("design_contract", SCRIPT)
design_contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(design_contract)


def valid_document():
    return """# 单元 99

## 设计门禁记录

### 上游来源

- 导航：`Develop_Helper_reading-guide/example.md`。
- 原文：`Develop_Helper/harness-core/skills/example/SKILL.md`。

### 原样继承

保留原有输入、输出和完成标准。

### Buzz 必要适配

只调整宿主身份和工具授权，不改变业务语义。

### 新增建议

- **待确认**：增加一个可选只读视图。
- **已否决**：增加第二份权威状态文件。

### 暂不建设

调度和部署由后续单元处理。

### 验收范围

覆盖文档、本地测试、宿主测试和运行态验收。

### 来源追踪表

| 设计结论 | 上游依据 | 处理方式 | 确认状态 | 验收证据 |
| --- | --- | --- | --- | --- |
| 保留输入 | `Develop_Helper/harness-core/skills/example/SKILL.md` | 原样继承 | 不适用 | 待实现 |
"""


class DesignContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="buzz-design-contract-test-")
        self.addCleanup(self.temp.cleanup)
        self.document = Path(self.temp.name) / "99-example.md"
        self.document.write_text(valid_document(), encoding="utf-8")

    def test_valid_contract_passes_without_writing(self):
        before = self.document.read_bytes()
        result = design_contract.check_document(self.document)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["new_suggestion_item_count"], 2)
        self.assertEqual(before, self.document.read_bytes())

    def test_missing_section_fails(self):
        self.document.write_text(valid_document().replace("### 暂不建设", "### 以后再说"),
                                 encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "缺少设计门禁章节.*暂不建设"):
            design_contract.check_document(self.document)

    def test_reading_guide_alone_is_not_authoritative(self):
        self.document.write_text(
            valid_document().replace(
                "`Develop_Helper/harness-core/skills/example/SKILL.md`",
                "`Develop_Helper_reading-guide/example.md`",
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "harness-core 原文"):
            design_contract.check_document(self.document)

    def test_each_new_suggestion_requires_state(self):
        self.document.write_text(
            valid_document().replace(
                "- **待确认**：增加一个可选只读视图。",
                "- 增加一个可选只读视图。",
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "每项新增建议"):
            design_contract.check_document(self.document)

    def test_trace_table_requires_all_columns(self):
        self.document.write_text(valid_document().replace(" | 验收证据", ""),
                                 encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "来源追踪表缺少列：验收证据"):
            design_contract.check_document(self.document)

    def test_symlink_document_is_rejected(self):
        link = Path(self.temp.name) / "linked.md"
        link.symlink_to(self.document)
        with self.assertRaisesRegex(ValueError, "普通文件"):
            design_contract.check_document(link)

    def test_cli_returns_nonzero_on_failure(self):
        self.document.write_text("# incomplete\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "check", str(self.document)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["status"], "fail")


if __name__ == "__main__":
    unittest.main()
