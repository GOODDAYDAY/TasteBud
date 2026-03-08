# Core Value Chain — Requirement Document

| Field   | Value      |
|---------|------------|
| ID      | REQ-001    |
| Status  | ✅ DONE     |
| Created | 2026-03-08 |
| Updated | 2026-03-08 |

## 1. Background & Motivation

TasteBud 是一个多用户内容策展平台，核心目标是通过 **Collect → Analyze → Score → Feedback → Learn**
的价值链，帮助用户从海量内容中高效筛选出符合个人口味的内容。

用户面临的问题：

- 内容源数量庞大，人工浏览效率极低
- 个人偏好难以量化，无法系统性地筛选
- 缺乏一个"越用越懂你"的自动化推荐机制

## 2. Functional Requirements

### 2.1 Collect — 内容采集

- [x] FR-1: 定义统一的内容采集接口 (`BaseCollector`)，支持多源扩展
- [x] FR-2: 采集结果标准化为 `RawContent` 数据结构（source, source_id, title, url, thumbnail_url, tags, metadata）
- [x] FR-3: 标签提取标准化为 `TagResult`（name, category, confidence）
- [x] FR-4: 采集内容持久化到本地文件系统（`data.json` + `tags.txt`）
- [x] FR-5: 支持图片下载与完成标记（`download.json`）
- [x] FR-6: 按分类（category）隔离存储目录

### 2.2 Analyze — 内容分析

- [x] FR-7: 定义统一分析接口 (`BaseAnalyzer`)，输出 `AnalysisResult`（style, theme, quality, mood, target_audience,
  content_warnings, visual_complexity, description, enriched_tags）
- [x] FR-8: 基于源标签的基线分析器 (`SourceTagAnalyzer`)，无需模型即可运行
- [x] FR-9: 基于 CLIP 的图像嵌入分析器（可选依赖），计算图像与口味基线的相似度
- [x] FR-10: 基于 VLM（Ollama）的深度视觉分析器，对图片进行结构化描述
- [x] FR-11: 分析结果持久化为 `analysis.json`
- [x] FR-12: 优雅降级 — CLIP 和 Ollama 不可用时系统仍正常工作

### 2.3 Score — 内容评分

- [x] FR-13: 基于标签权重的评分引擎 (`TagScorer`)，计算公式 `sum(preference_weight × tag_confidence)`
- [x] FR-14: Sigmoid 归一化，将原始分数映射到 0-1 区间

### 2.4 Feedback — 用户反馈

- [x] FR-15: 支持 like / dislike 两种评价
- [x] FR-16: 反馈追加写入 `feedback_log.jsonl`（append-only，数据源头）
- [x] FR-17: 单项反馈记录持久化为 `feedback.json`
- [x] FR-18: dislike 时自动删除图片释放磁盘空间

### 2.5 Learn — 偏好学习

- [x] FR-19: 每次反馈实时更新标签权重（学习率 0.5，like +0.5 / dislike -0.5）
- [x] FR-20: 偏好数据持久化为 `preferences.json`
- [x] FR-21: 支持从反馈日志完整重放（`replay`），幂等生成偏好
- [x] FR-22: CLIP 基线随评价自动更新（liked items 均值向量）

### 2.6 Sieve — 三层筛选管道

- [x] FR-23: Layer 1（快筛）— 标签评分 + 可选 CLIP 相似度，阈值可配置
- [x] FR-24: Layer 2（深筛）— VLM 视觉质量评估，含 content_warnings 惩罚
- [x] FR-25: Layer 3（人工）— 用户最终评价（like/dislike），记录到反馈系统
- [x] FR-26: 筛选结果持久化为 `sieve.json`，支持按层 + 通过/未通过查询

### 2.7 Category Schema — 分类评价维度

- [x] FR-27: 每个分类有独立的评价维度定义（`schema.json`）
- [x] FR-28: 内置 manga / news 两种预定义 schema
- [x] FR-29: 支持自定义 schema 扩展新分类

### 2.8 交互式 CLI

- [x] FR-30: 提供交互式菜单（Search, Download, Browse, Rate, Prefs, Replay, Log, Quit）
- [x] FR-31: 后台异步任务管理（搜索/筛选、下载不阻塞菜单）
- [x] FR-32: 进度日志系统（`download.log`）

## 3. Non-Functional Requirements

- [x] NFR-1: 全链路 async/await，I/O 不阻塞
- [x] NFR-2: 文件系统存储，无需外部数据库即可运行
- [x] NFR-3: 可选依赖优雅降级（CLIP、Ollama）
- [x] NFR-4: 按分类完全隔离（目录、偏好、反馈、schema）
- [x] NFR-5: Structlog 结构化日志
- [x] NFR-6: 严格类型检查（mypy strict + pydantic）

## 4. User Stories / Use Cases

- As a user, I want to search content from sources, so that I can discover new items.
- As a user, I want the system to automatically filter content based on my taste, so that I don't waste time on
  uninteresting items.
- As a user, I want to rate items (like/dislike), so that the system learns my preferences over time.
- As a user, I want to browse filtered results sorted by relevance, so that I see the best matches first.
- As a user, I want to view my current preference weights, so that I understand what the system thinks I like.
- As a user, I want to replay my feedback history, so that I can reset and regenerate my preference profile.

## 5. Acceptance Criteria

- [x] AC-1: Collector 能采集内容并标准化为 RawContent
- [x] AC-2: SourceTagAnalyzer 能从标签推导分析结果
- [x] AC-3: TagScorer 能基于偏好权重计算分数
- [x] AC-4: 反馈能正确更新标签权重
- [x] AC-5: Replay 能从日志幂等重建偏好
- [x] AC-6: 三层筛选管道完整运行
- [x] AC-7: 测试覆盖核心模块（53+ tests）

## 6. Out of Scope

- Web API（FastAPI routes）— 未实现
- 数据库持久化（SQLAlchemy ORM）— 未实现
- 前端 UI — 仅 React 脚手架
- 多用户支持 — 当前为单用户模式
- 用户认证与权限

## 7. Open Questions

- Q1: 何时从文件存储迁移到 SQLite 数据库？
- Q2: 学习率（0.5）是否需要动态调整？
- Q3: CLIP 与标签评分的混合权重（各 0.5）是否需要可配置？
- Q4: 是否需要支持内容源的增量更新 / 去重？
