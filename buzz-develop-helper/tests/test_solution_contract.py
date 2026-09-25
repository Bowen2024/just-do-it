from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SolutionContractTests(unittest.TestCase):
    def test_role_preserves_traceability_and_separation(self):
        role = (ROOT / "capabilities/solution.md").read_text(encoding="utf-8")
        self.assertIn("用户结果 → REQ → AC → API/技术设计 → UI → Feature → Task → Tester 证据", role)
        self.assertIn("不能写 artifact registry", role)
        self.assertIn("不提前拆 Feature/Task", role)
        self.assertIn("不自动生成第二套流程", role)

    def test_profiles_are_not_workflow_stages(self):
        role = (ROOT / "capabilities/solution.md").read_text(encoding="utf-8")
        for profile in ("`Lite`", "`Standard`", "`AI`"):
            self.assertIn(profile, role)
        self.assertIn("不是先后阶段", role)

    def test_template_has_single_seven_layer_contract_and_coverage(self):
        template = (ROOT / "capabilities/solution-tech-spec-template.md").read_text(encoding="utf-8")
        for number in range(1, 8):
            self.assertIn(f"## {number}.", template)
        self.assertIn("## 11. REQ/AC 覆盖表", template)
        self.assertIn("covered/not_applicable/open/blocked", template)
        self.assertIn("approval_verified: false", template)

    def test_adapter_keeps_production_readiness_boundary(self):
        adapter = (ROOT / "adapters/solution-buzz.md").read_text(encoding="utf-8")
        self.assertIn("方案 Agent 尚不可视为生产可用", adapter)
        self.assertIn("宿主 Channel 回复主路径验证", adapter)
        self.assertIn("`solution.context`", adapter)
        self.assertIn("未实现", adapter)
        self.assertIn("无法登记、确认、交接、自行选择发送目标或启动下游", adapter)

    def test_customer_solution_is_only_an_expression_view(self):
        role = (ROOT / "capabilities/solution.md").read_text(encoding="utf-8")
        self.assertIn("`solution.md` 是表达视图", role)
        self.assertIn("不替代 `tech-spec`", role)


if __name__ == "__main__":
    unittest.main()
