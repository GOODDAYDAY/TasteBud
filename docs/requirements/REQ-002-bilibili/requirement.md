# Bilibili — Requirement Document

| Field   | Value          |
|---------|----------------|
| ID      | REQ-002        |
| Status  | 🟡 IN PROGRESS |
| Created | 2026-03-08     |
| Updated | 2026-03-08     |

## 1. Background & Motivation

TasteBud 当前的价值链是 Collect → Analyze → Score → Feedback → Learn，面向的是"内容本身"的采集与筛选。本需求引入一个新场景：
**自动收集 Bilibili 评论区 → AI 分析用户痛点 → 推送分析结果**。

与现有架构的关系：

| 维度   | 现有架构（REQ-001）     | Bilibili 评论场景          |
|------|-------------------|------------------------|
| 采集对象 | 内容本身（标题/标签/图片）    | 评论区文本（隶属于视频/专栏）        |
| 分析方式 | 标签映射 / CLIP / VLM | LLM 批量分析（痛点挖掘 + 技术可行性） |
| 输出方式 | 本地浏览 + 评分         | 主动推送（邮件/微信）            |
| 更新模式 | 一次性采集             | 持续增量更新                 |
| 流程编排 | 固定管道              | 可配置 Pipeline（YAML）     |
| 分析触发 | 每条内容都分析           | 评论量达到窗口阈值时批量分析         |

核心诉求：

- 用户关注特定 UP 主 / 视频 / 专栏，想自动追踪评论区动态
- **核心分析目标：挖掘评论中用户的痛点/难点，评估当前技术是否可以解决这些问题**
- 分析不是实时的，而是评论积累到一定量（窗口阈值）时批量触发 AI 分析
- 分析结果需要推送到用户指定渠道
- 需要增量采集，不重复处理已见过的评论

这要求架构引入三个新概念：

1. **Pipeline 配置（YAML）** — 将 Collect → Analyze → Notify 编排为可配置的流水线
2. **Notifier（推送器）** — 新的输出层，支持多渠道推送
3. **分析窗口** — 评论量达到阈值才触发 AI 分析，而非逐条分析

## 2. Functional Requirements

### 2.1 Bilibili Collector — 评论区采集

- [ ] FR-1: 支持按 UP 主 UID 采集其所有视频的评论区
- [ ] FR-2: 支持按视频 BV 号/AV 号采集单个视频的评论区
- [ ] FR-3: 支持按专栏 CV 号采集单篇专栏的评论区
- [ ] FR-4: 采集内容标准化为统一数据结构（评论文本、用户、时间、点赞数、回复数、所属视频信息等）
- [ ] FR-5: 增量采集 — 记录已采集的最大评论 ID（rpid），仅采集新增评论
- [ ] FR-6: 支持评论分页遍历（按热度/时间排序）
- [ ] FR-7: 支持采集楼中楼回复（子评论）
- [ ] FR-8: 支持 Bilibili 登录态（优先使用第三方库扫码登录，备选手动配置 Cookie）
- [ ] FR-9: 请求限速 ≥ 1s/次，避免触发反爬

### 2.2 Comment Analyzer — 评论分析

**核心分析目标：从评论中挖掘用户痛点，评估技术可行性。**

- [ ] FR-10: 分析窗口机制 — 评论积累到配置阈值（如 50/100/200 条）时，批量触发一次 AI 分析
- [ ] FR-11: 痛点挖掘 — AI 识别评论中用户遇到的问题、困难、需求
- [ ] FR-12: 技术可行性评估 — AI 判断每个痛点是否可被当前技术解决，给出可行性分析
- [ ] FR-13: 结构化输出 — 每条分析结果需包含：原始评论内容、所属视频标题+链接、评论用户、评论时间、痛点描述、技术可行性分析
- [ ] FR-14: 全量评论丢给 AI，不做敏感词预过滤（避免误伤）
- [ ] FR-15: LLM 可配置 — 支持 Ollama 本地模型 / 外部 API（通过 API Token 配置）
- [ ] FR-16: 分析结果持久化，支持历史查看

### 2.3 Notifier — 推送系统

- [ ] FR-17: 定义统一的推送接口（BaseNotifier），支持多渠道扩展
- [ ] FR-18: 支持邮件推送（SMTP）
- [ ] FR-19: 支持企业微信/微信推送（Webhook）
- [ ] FR-20: 推送内容模板化（标题 + 痛点列表 + 可行性分析 + 原始评论链接）
- [ ] FR-21: 每次 AI 分析完成后立即推送结果
- [ ] FR-22: 推送记录持久化（避免重复推送）

### 2.4 Pipeline — 流水线编排

- [ ] FR-23: Pipeline 配置文件（YAML 格式）定义 Collect → Analyze → Notify 的完整流程
- [ ] FR-24: 每个 Pipeline 独立配置：采集源、分析窗口大小、LLM 配置、推送渠道
- [ ] FR-25: 支持定时执行（cron 表达式 或 间隔时间）
- [ ] FR-26: Pipeline 执行日志和状态追踪
- [ ] FR-27: 支持多个 Pipeline 并行运行，互不干扰

### 2.5 本地缓存与存储

- [ ] FR-28: 按 UP 主 / 视频 / 专栏隔离存储评论数据
- [ ] FR-29: 评论去重（基于 rpid）
- [ ] FR-30: 记录采集游标（last_rpid / last_page），支持断点续采
- [ ] FR-31: 未分析评论计数器（用于窗口阈值判断）
- [ ] FR-32: 评论数据可导出为 JSON/CSV

### 2.6 插件化架构

- [ ] FR-33: 通用框架（Pipeline、Notifier、Analyzer、Window）与平台特定逻辑分离
- [ ] FR-34: 平台特定代码以 Plugin 子包形式组织在 `plugin/{platform}/` 目录下
- [ ] FR-35: 每个 Plugin 需实现 `BasePlugin` 接口，提供：采集器工厂、通知模板渲染、自定义 prompt（可选）
- [ ] FR-36: Pipeline Runner 通过 Plugin 接口调用平台特定逻辑，自身不包含任何平台代码
- [ ] FR-37: 新增平台只需新建 `plugin/{platform}/` 子包并实现 Plugin 接口，无需修改通用框架代码

## 3. Non-Functional Requirements

- [ ] NFR-1: 全链路 async/await
- [ ] NFR-2: 遵守 Bilibili API 速率限制（请求间隔 ≥ 1s）
- [ ] NFR-3: 采集器支持登录态（优先第三方库扫码登录，备选手动 Cookie）
- [ ] NFR-4: 推送失败自动重试（最多 3 次，指数退避）
- [ ] NFR-5: Pipeline 配置变更无需重启服务
- [ ] NFR-6: 单个 Pipeline 失败不影响其他 Pipeline 运行
- [ ] NFR-7: LLM API Token 通过环境变量/配置文件管理，不硬编码

## 4. User Stories / Use Cases

- As a user, I want to monitor a specific UP主's comment sections, so that I can discover user pain points without
  manually reading every comment.
- As a user, I want the system to batch-analyze comments when they reach a threshold (e.g., 100 new comments), so that
  AI analysis is cost-effective.
- As a user, I want each analysis result to show: original comment, video title/link, commenter, timestamp, identified
  pain point, and technical feasibility, so that I have full context.
- As a user, I want to configure multiple pipelines (e.g., one per UP主 or per topic), each with its own analysis window
  and notification channel.
- As a user, I want incremental collection, so that the system doesn't re-process old comments.
- As a user, I want to receive analysis results via WeChat/email immediately after each AI analysis batch completes.

## 5. Acceptance Criteria

- [ ] AC-1: 能通过 UP 主 UID 采集其最新视频的评论区，增量采集不重复
- [ ] AC-2: 评论量达到窗口阈值时自动触发 AI 分析
- [ ] AC-3: AI 分析输出结构化结果（痛点列表 + 技术可行性 + 原始评论上下文）
- [ ] AC-4: 分析结果能通过至少一种渠道（邮件或微信）推送
- [ ] AC-5: Pipeline YAML 配置能正确编排 Collect → Analyze → Notify 流程
- [ ] AC-6: 连续运行 2 次，第 2 次仅采集增量评论
- [ ] AC-7: 测试覆盖 Collector、Analyzer、Notifier 核心逻辑

## 6. Out of Scope

- 弹幕采集（仅做评论区）
- 视频内容本身的分析（标题/封面/正文）
- Bilibili 用户画像分析
- 实时 WebSocket 监听（采用定时轮询）
- 前端 UI（本期仅 CLI + 配置文件）
- 多账号轮换采集（暂不需要）
- 敏感词过滤（全量丢给 AI 分析）

## 7. Open Questions（已决策）

| #  | 问题                    | 决策                                             |
|----|-----------------------|------------------------------------------------|
| Q1 | Bilibili API 认证方式？    | 优先第三方 bilibili 库扫码登录，备选手动 Cookie。默认带登录态        |
| Q2 | Pipeline 配置格式？        | YAML，支持注释和层级结构                                 |
| Q3 | BaseCollector 是否需要扩展？ | BaseCollector 保持通用，CommentCollector 继承扩展评论特有逻辑 |
| Q4 | LLM 选择？               | 可配置，通过 API Token 方式接入（Ollama / 外部 API），需在配置中指定 |
| Q5 | 推送频率策略？               | 每次 AI 分析完成后立即推送。触发分析的不是时间，而是评论量达到窗口阈值          |
| Q6 | 多账号轮换？                | 暂不需要                                           |
| Q7 | 敏感词过滤？                | 不做，全量丢给 AI 分析，避免误伤                             |
| Q8 | 具体分析什么？               | 挖掘用户痛点/难点 + 评估技术可行性。输出需带原始评论上下文（视频、用户、时间）      |
