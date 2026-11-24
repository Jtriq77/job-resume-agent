---
name: resume-section-extractor
description: 从一段口语化中文自我介绍中抽取简历四段（教育背景、实习经历、校园与项目经历、技能特长），只改写不编造；输出严格 JSON，供模板渲染。
version: 0.1.0
license: MIT
---

# 四段式简历抽取 Skill

## 用途

输入：用户一段语无伦次的中文自我介绍。
输出：严格四段 JSON + 基础信息；缺失字段留空，不猜测、不补造。

## 四个板块（只能这四个）

1. `educations` 教育背景：学校、专业、学历、起止时间、GPA/排名、课程、奖学金。
2. `internships` 实习经历：公司、部门、岗位、起止时间、工作内容/结果（最多 3 条 bullet）。
3. `campus` 校园与项目经历：项目、竞赛、社团、学生会、荣誉（最多 3 条 bullet）。
4. `skills` 技能特长：语言、工具、证书；工具名归一（SQL、Python、Tableau）。

## 铁律

- 不新增原文没有的公司、时间、数字、职责、奖项。
- 原文没有的数字不要补；缺失的日期留空，由 Agent 追问。
- 竞赛/比赛/社团/荣誉放第三段，不要塞进教育背景。
- 奖学金可以放教育背景。
- bullet 用简历语言：去“然后/就是/其实/我”，动作开头，保留数字。
- 每段最多 3 条 bullet；多段经历用数组。
- 输出只含 JSON，不含解释。

## 输出 Schema

见 `schema.json`。基础字段：`name, age, political_status, phone, email, city, target_cities, job_intent, availability`。

## 失败处理

- JSON 解析失败 → 重试一次；仍失败 → 回退规则抽取 + 追问。
- 数字/公司/学校在原文找不到 → 写入 `_warnings`，让用户核对，不静默采用。
- 四段中某段为空 → 保留空数组，由 Agent 追问，不硬填。

## 来源与适配

思路参考 `Chasen-Liao/resume-skills` v0.11.0（MIT）的“事实契约 / 不编造 / ATS-safe”做法；本项目将其适配为中文四段式 JSON，未直接复制其代码。候选人事实与展示分离的设计也来自该 skill 的思路。
