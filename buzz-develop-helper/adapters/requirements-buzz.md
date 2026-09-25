# Buzz 需求角色接入卡（人工配置）

状态：原有轻量需求角色已在 `just-start` 完成范围内验收。新增的 A 阶段 PRD 模板、`requirements.inspect-prd` 和 `requirements.save-prd-draft` 已在融合层及 Buzz ACP/MCP 源码实现，但尚未重启生产需求 Agent 并做真实验收。不把旧版运行证据当成新 PRD 能力已上线。

本文件是人工配置与测试说明，不是 Buzz 中已经自动安装的 Agent。`capabilities/requirements.md` 是需求角色的核心规则；只有用户将薄入口配置到角色、运行环境实际能读取该路径后才会生效。两者都不属于 Developer 规则，不能用来配置 Honey 或其他开发角色。

## 复用已观察到的配置

用户选择沿用 Buzz 现有模型/凭据。2026-09-13 只读查看 Honey：运行时为 Codex，自定义模型 ID 为 `gpt-5.6-sol`。界面同时提示无法加载实时模型列表；这不是模型调用成功的证据。未查看、复制或更改任何密钥。

这与最初候选 `buzz-agent + GPT API` 不同。首版候选调整为 Buzz 独立需求角色 → 现有 Codex 运行环境 → 已配置 GPT；不改变 Honey 的开发职责。若用户仍要求原生 buzz-agent，需另行配置和验证，不能把两条认证链混为一谈。

## 由用户完成的界面步骤

1. 若 Honey 的编辑窗口仍开着，点 Cancel，保留原配置。新建独立 Agent，建议命名「需求澄清」；不要把 Honey 改成需求角色。
2. 选择与 Honey 一致的 Codex 运行时和 `gpt-5.6-sol` 模型，沿用已有登录/凭据，不重新粘贴密钥。
3. Agent instructions 填写以下通用薄入口，核心规则只有一个来源。这里不写具体项目名、项目 ID 或项目目录：

```text
你是可服务多个业务项目的独立需求澄清 Agent。
先读取并遵循 /Users/bowen/Desktop/博文的career/vibe- coding/buzz-develop-helper/capabilities/requirements.md。
融合层：/Users/bowen/Desktop/博文的career/vibe- coding/buzz-develop-helper
业务项目父目录和项目路径由融合工具依据本机配置与本次明确传入的 project_id 解析，不接受模型自行拼接的绝对路径。
每个新项目使用独立顶层线程；首条任务消息必须包含 project_id。本线程未绑定项目时只请求 project_id，不枚举或猜测项目。
绑定后先运行融合层 scripts/requirements.py context <本次 project_id>，核对返回的 project_id、project_path 和项目背景，再开始提问。
一个线程只绑定一个项目；如需切换项目，要求新开顶层线程，不能在原线程覆盖绑定。
仅做需求澄清和草案保存；不开发、不派发其他角色、不提交或推送。
不要加载 Develop Helper 的原根入口或全流程 Skill。
```

4. 运行环境工作目录绑定到融合层，而不是某个业务项目；项目读写必须经过 project_id 解析和项目范围工具。仅允许读取融合方法、必要项目资料及写入当前需求成果。不要为了通过接入而启用 unrestricted/trusted/bypass 模式。具体控件和能力取决于实际安装版本，缺少入口时先反馈，不猜测配置。
5. 在普通频道的专用需求线程中测试，不使用私信验证隔离。必须采用 `BUZZ_ACP_SESSION_POLICY=thread`、桌面端 `Thread Scoped ACP Sessions` 实验开关或经实测等价的线程隔离；实验开关只对 Agent 下次启动生效，私信始终保持 conversation scope。若当前实例只能按频道共享会话，则一个频道只放一个项目；在隔离能力未验证前，不让同一 Agent 在同一会话讨论多个项目。未验证连续回复触发前，每轮显式 @需求角色。

不要直接复制完整的既有 MCP/工具权限；复用模型和凭据不等于复用所有开发工具权限。具备通用终端的 Codex 仍可能写其他目录，提示词和本地脚本并非全局沙箱；需要实际权限核验后再宣称隔离。

## 最小测试消息

每个新项目的首条消息按以下任务槽位填写；尖括号只是文档模板，不直接保存到 Buzz 角色提示词中：

```text
任务类型：需求澄清
project_id：<PROJECT_ID>
本轮目标：<GOAL>
允许读取的初始材料：<RELATIVE_PATHS 或 无>
本轮写入：先不写 / 允许保存需求草案
下一步：仅澄清后结束，不自动进入方案或开发
```

以下 `just-start` 消息只用于已完成的基础读取冒烟检查，不是业务需求模板，也不应继续扩写成需求草案：

```text
任务类型：需求澄清
project_id：just-start
本轮目标：只读取项目背景，告诉我项目用途和缺少的信息。
允许读取的初始材料：无
本轮写入：先不写
下一步：仅澄清后结束，不开发、不调用其他角色。
```

真实业务试点必须另行提供与融合系统测试无关的业务场景。读取成功后，需求 Agent 围绕该业务完成多轮澄清，再按用户明确要求保存草案。融合能力的测试步骤与结果记录在 `../fusion-design/02-需求能力.md` 和 `tests/`，不写入业务项目需求。Developer/Main 融合入口尚未建设；接收角色准备完成后，再验证完整共享闭环。

用户不需要发送工具命令、项目绝对路径、SHA 或历史目录。结束澄清和保存可以只表达业务意图：

```text
现在结束澄清。请基于本线程已经确认的内容整理第一版草案；自行补全的内容标记为假设或 Agent 建议默认值。
我授权保存本次需求草案。保存完成后结束，不进入后续阶段。
```

需求变更同样只描述变更并授权保存；Agent 应自行读取当前版本、校验摘要、保留旧稿和报告结果。A 与 R 的切换由角色根据用户的外部参考请求或关键决策缺口自动管理，不要求用户输入阶段口令。

## 本地工具

在融合层目录运行 `python3 -B scripts/requirements.py context <PROJECT_ID>` 可只读检查。保存时以 `save-draft <PROJECT_ID> --expected-sha <实际摘要或首次 missing> --apply` 调用，正文通过标准输入传入。`PROJECT_ID` 已经是命令参数槽位；工具从 `config/local.json` 的 `projects_root` 解析真实目录，无需在 Persona 里保存绝对项目路径。

草案会保留上一版到 docs/requirements-history，重试须先核对新摘要。工具不修改 project.json/README 索引、不认证确认消息、不发送 Buzz 消息；索引和用途确认由 Main 通过独立工具执行。

用户明确要进入方案时，角色使用 `capabilities/requirements-prd-template.md` 整理 `docs/PRD.md`，内部调用 `save-prd-draft` 并在写后调用 `inspect-prd`。PRD 结构通过仍不等于用户确认；须将该 SHA 作为 requirements 类成果交给 Main 登记，并以用途“形成技术方案”建立当前会话确认。

## 项目槽位的实现边界

- 当前 Buzz Persona 正文按静态文本保存；已检查的代码与规范没有证明 Agent instructions 支持 `${PROJECT_ID}` 一类运行时模板替换。Persona Pack 规范明确说明 MCP 环境变量插值仍是计划能力，因此不能把类似字符串当成现成功能。
- 当前采用“消息槽位”：Main 或用户在新线程首条消息传入 project_id，Agent 将该线程绑定到项目；工具负责从受控父目录解析路径。将来 Buzz 若提供经过验证的实例变量，可把同一字段从消息搬到结构化参数，角色规则无需重写。
- `AGENT_CWD` 是运行实例的工作目录，不适合作为频繁切换的项目槽位：它在会话创建时确定，并影响技能发现。首版把它固定到融合层，项目由工具参数选择。
- 这减少的是重复配置，不代表所有项目共享同一对话记忆。项目上下文必须按线程隔离；缺少线程隔离时使用“一项目一频道”，最保守的兜底才是“一项目一 Agent”。
