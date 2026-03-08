# Batch Analysis — Requirement Document

| Field   | Value      |
|---------|------------|
| ID      | REQ-004    |
| Status  | 🔵 NEW     |
| Created | 2026-03-08 |
| Updated | 2026-03-08 |

## 1. Background & Motivation

REQ-002/003 实现了评论采集，但分析环节存在两个问题：

1. **分析从未触发**：当前窗口机制按单个 target（视频）计数，`window_size=100` 意味着一个视频要积累 100
   条新评论才触发分析。但搜索模式下会采集多个视频，每个视频可能只有几十条评论，单个视频永远达不到阈值。
2. **LLM 配置不灵活**：用户有 GitHub Copilot token（OpenAI 兼容 API），需要支持配置使用。当前只支持 Ollama 和
   OpenAI-compatible 两种 provider，但缺乏实际可用的 token 配置指引。

核心诉求：让分析真正跑起来——**跨视频汇总评论，按最大评论数或最大 token size 分批丢给 AI 处理**。

## 2. Functional Requirements

### 2.1 窗口机制改进

- [ ] FR-1: 窗口计数改为**跨 target 汇总**——一个 pipeline 内所有视频的新评论累加计数，达到阈值触发分析
- [ ] FR-2: 分析时加载该 pipeline 下所有 target 的 pending 评论，合并为一个大批次
- [ ] FR-3: 分析完成后重置所有参与分析的 target 的 pending 计数

### 2.2 批量处理策略

- [ ] FR-4: 支持按 `max_comments`（最大评论条数）分批——如果合并后评论数超过 max_comments，分多批调用 LLM
- [ ] FR-5: 每批分析独立生成 PainPoint 结果，最终合并去重
- [ ] FR-6: 保留现有采样策略（高赞 + 最新 + 随机）用于单批内的评论筛选

### 2.3 GitHub Copilot Token 支持

- [ ] FR-7: 支持 `provider: github-copilot`，使用 GitHub Copilot API（OpenAI 兼容格式）
- [ ] FR-8: API base_url 配置为 `https://api.githubcopilot.com`
- [ ] FR-9: Token 通过环境变量读取（`api_token_env: GITHUB_COPILOT_TOKEN`）

## 3. Non-Functional Requirements

- [ ] NFR-1: LLM 调用超时可配（默认 120s），Copilot API 可能较慢
- [ ] NFR-2: 分批处理时每批之间无需限速（LLM API 自有限流）
- [ ] NFR-3: 分析失败不应丢失 pending 评论（不重置计数器）

## 4. User Stories / Use Cases

- As a user, I want analysis to trigger when my pipeline has collected enough comments across all videos, not per-video.
- As a user, I want to use my GitHub Copilot token for analysis, so I don't need to run a local Ollama instance.
- As a user, I want large batches of comments to be automatically split and processed, so analysis doesn't fail due to
  token limits.

## 5. Acceptance Criteria

- [ ] AC-1: 搜索模式采集 20 个视频后，评论总数 ≥ window_size 时触发分析
- [ ] AC-2: 分析实际调用 LLM 并输出痛点结果
- [ ] AC-3: 使用 GitHub Copilot token 能成功调用分析
- [ ] AC-4: 超过 max_comments 的评论自动分批处理

## 6. Out of Scope

- 多 LLM provider 并行调用
- 分析结果的 UI 展示
- 痛点结果的跨轮次去重

## 7. Open Questions

| #  | 问题                                 | 决策                                                      |
|----|------------------------------------|---------------------------------------------------------|
| Q1 | GitHub Copilot API 的 base_url 是什么？ | `https://api.githubcopilot.com`，走 OpenAI 兼容格式           |
| Q2 | 跨视频汇总后，分析结果保存在哪？                   | 保存在 pipeline 级别目录（`pipeline-data/{platform}/analysis/`） |
| Q3 | pending 计数器粒度？                     | 改为 pipeline 级别汇总，不再按 target 隔离                          |
