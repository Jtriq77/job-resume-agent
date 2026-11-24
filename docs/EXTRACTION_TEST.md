# 四段抽取：真实调用记录（2026-11-23）

## 配置

- 端点：模型服务的 OpenAI 兼容接口
- 模型：文本模型（OpenAI 兼容接口）
- 凭证：本地 `.env` 的 `DEEPSEEK_API_KEY`（不提交）
- Skill：`skills/resume-section-extractor/`（prompt + schema + SKILL.md）
- 代码：`src/agent/profile_extract.py`

## 输入（口语化、故意混乱）

> 然后我叫王小明，22岁，团员，在上海。手机13800000000，邮箱wang@example.com。我是某211大学信息管理专业本科，2022.09-2026.06。然后我在字节跳动实习，就是做数据分析，主要用SQL取数，还做了AB测试，转化率提升了8%，其实还帮忙写周报。我还做了用户流失预测项目，用Python建模，AUC0.81，后来调了参数。还拿过数学建模省二。技能SQL、Python、Tableau，求职意向数据分析。

## 输出结构

| 板块 | 条数 | 内容摘要 |
|---|---:|---|
| 教育背景 | 1 | 某211大学 / 信息管理 / 本科 / 2022.09-2026.06 |
| 实习经历 | 1 | 字节跳动 / 数据分析；3 条 bullet |
| 校园与项目经历 | 2 | 用户流失预测项目；数学建模竞赛省二 |
| 技能特长 | 3 | SQL、Python、Tableau |

## 润色结果

- 实习：
  - 使用 SQL 取数，完成 A/B 测试，转化率提升 8%。
  - 协助撰写周报。
- 项目：
  - 使用 Python 建模，AUC 0.81。
  - 调整参数优化模型。
- 竞赛：获得省级二等奖。

## 观察

- 竞赛被正确归到“校园与项目经历”，没有塞进教育背景。
- 口语“然后/就是/其实/做了/帮忙”被去掉，动作化。
- `_warnings` 为空：数字、公司、学校都能在原文找到。
- 输入没有给实习/项目时间，输出日期为空；对话会追问。
- 这是单条冒烟测试，不是正式评估；需要 20–30 条样本统计分段准确率、字段准确率、编造率、人工修改率。

## 复现

```bash
# .env 中配置 DEEPSEEK_API_KEY，重启 App
streamlit run src/app/streamlit_app.py
```

或在 Python 中：

```python
from src.agent.profile_extract import llm_extract
p = llm_extract("……一段自我介绍……")
print(p["educations"], p["internships"], p["campus"], p["skills"])
```
