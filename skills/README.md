# Skills 清单与选型

## 本项目使用的 Skill

### `resume-section-extractor`（自建，MIT）

- 路径：`skills/resume-section-extractor/`
- 输入：一段口语化中文自我介绍
- 输出：严格四段 JSON（教育背景 / 实习经历 / 校园与项目经历 / 技能特长）+ 基础信息
- 规则：只改写不编造；竞赛归第三段；缺失字段留空并追问
- 代码：`src/agent/profile_extract.py` 读取 `prompt.md`，文本模型 API 返回 JSON 后做规范化与数字核对
- 版本：0.1.0

**适配来源**：思路参考 `Chasen-Liao/resume-skills` v0.11.0（MIT）的“事实契约 / 先确认事实再写 / 不编造 / ATS-safe”做法；本项目改为中文四段式 JSON，未直接复制其代码。

### `resume-direction-tailor`（自建，MIT）

- 路径：`skills/resume-direction-tailor/`
- 输入：四段画像 + 用户选择的方向
- 输出：按方向整理的四段 JSON；每段经历 1 段连续文字（背景/职责/技术/结果）
- 规则：不新增公司/时间/数字/技术栈；缺具体结果时用定性描述写完整，不写占位符；方向只改表述与排序
- 代码：`src/agent/tailor.py` 读取 `prompt.md`，模型调用失败时回退已有整理结果

## 候选评估（为什么没直接用）

| 候选 | 许可 | 适配度 | 结论 |
|---|---|---|---|
| `Chasen-Liao/resume-skills` v0.11.0 | MIT | 高：中文、事实驱动、ATS-safe；但输出 HTML 简历，不是四段 JSON | **借鉴思路，自建四段 Skill** |
| `theresumeparser/resume-parser-api` | AGPL-3.0 | 高：Pydantic 校验、重试降级；但是 FastAPI 服务，不是 skill | 只借鉴校验设计，不复制代码 |
| `sangowu/job-matcher-skill` | 未确认 | 中：CV 抽取 + 岗位检索，体量大 | 不集成，避免许可证/范围风险 |
| `bhaskrreddy/Resume-Parser` | 待核对 | 中：规则 vs LLM 对比，适合做评估基线 | 仅参考评估思路 |

## 为什么不直接找一个“通用简历解析 Skill”

通用解析器通常输出 `personal_info / experience / education / skills` 等英文或平台自定义 schema，和我们的四段式（尤其“校园与项目经历”合并）不一致；直接接会引入字段映射和许可证双重成本。自建一个窄 Skill，更容易做：
- 严格 JSON Schema；
- 四段归类规则；
- 数字/公司回查；
- 规则兜底与追问；
- 消融实验（规则 vs LLM vs LLM+Skill+校验）。
