# Bilibili Search — Requirement Document

| Field   | Value      |
|---------|------------|
| ID      | REQ-003    |
| Status  | ✅ DONE     |
| Created | 2026-03-08 |
| Updated | 2026-03-08 |

## 1. Background & Motivation

REQ-002 实现了对固定目标（单个视频/UP主/专栏）的评论采集与分析。但用户希望围绕一个**主题**（如"AI"）去发散采集，不局限于某个固定视频。

同时，现有 `schedule` 字段（cron 表达式）对当前 CLI 使用场景没有实际意义——用户希望程序启动后**持续运行**，循环执行所有
pipeline，直到用户主动退出（Ctrl+C）。

## 2. Functional Requirements

### 2.1 搜索模式

- [x] FR-1: 新增 `mode: search` 采集模式，通过关键词搜索 Bilibili 视频
- [x] FR-2: 支持配置搜索排序方式：`pubdate`（最新）/ `click`（播放量）/ `scores`（综合）
- [x] FR-3: 支持配置 `max_videos` 限制每次搜索取前 N 个视频
- [x] FR-4: 搜索到的每个视频走已有的增量评论采集逻辑（cursor 去重）
- [x] FR-5: 搜索结果中的视频如果之前已采集过，通过 cursor 机制自动跳过已有评论

### 2.2 持续运行

- [x] FR-6: 移除 `schedule` 字段，程序启动后持续循环运行所有 enabled pipeline
- [x] FR-7: 每轮执行完所有 pipeline 后，等待一个可配置的间隔（如 30 分钟）再开始下一轮
- [x] FR-8: 支持 Ctrl+C 优雅退出
- [x] FR-9: 每轮开始时打印轮次编号和时间

## 3. Non-Functional Requirements

- [x] NFR-1: 搜索 API 同样遵守限速（≥1s/次）
- [x] NFR-2: 持续运行模式下内存不应持续增长

## 4. User Stories / Use Cases

- As a user, I want to configure a pipeline with `mode: search` and `target: "AI"`, so that the system automatically
  finds and monitors AI-related videos' comment sections.
- As a user, I want the pipeline runner to keep running in a loop until I press Ctrl+C, so I don't need to set up
  external cron jobs.

## 5. Acceptance Criteria

- [x] AC-1: `mode: search` + `target: "AI"` 能搜索到视频并采集评论
- [x] AC-2: 搜索结果中的视频走增量采集（第二次运行不重复采集）
- [x] AC-3: 程序启动后持续循环运行，Ctrl+C 优雅退出
- [x] AC-4: YAML 配置中不再需要 `schedule` 字段

## 6. Out of Scope

- 搜索结果的去重/合并（不同 pipeline 搜同一关键词）
- 搜索过滤条件（时间范围、视频时长等）
- 搜索关键词的动态更新

## 7. Open Questions

| #  | 问题              | 决策                            |
|----|-----------------|-------------------------------|
| Q1 | 循环间隔多久？         | YAML 配置 `interval` 字段，默认 1 分钟 |
| Q2 | 搜索 API 是否需要登录态？ | 不需要，先不做登录态支持                  |
| Q3 | 搜索结果分页如何处理？     | 只取前 N 个视频，不做分页                |
