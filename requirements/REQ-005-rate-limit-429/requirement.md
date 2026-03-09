# rate-limit-429 — Requirement Document

| Field   | Value          |
|---------|----------------|
| ID      | REQ-005        |
| Status  | 🟡 IN PROGRESS |
| Created | 2026-03-09     |
| Updated | 2026-03-09     |

## 1. Background & Motivation

采集评论和调用 AI 分析时，频繁请求会触发 429 Too Many Requests。当前没有任何处理，直接报错导致该视频跳过。需要一个通用的 429
处理机制，遇到限流自动暂停后重试。

## 2. Functional Requirements

- [x] FR-1: 任何 HTTP 请求收到 429 时，自动暂停一段时间后重试
- [x] FR-2: 暂停时长可配置，默认 1 分钟
- [x] FR-3: 通用机制，同时覆盖 Bilibili API 和 LLM API 请求

## 3. Non-Functional Requirements

- 暂停期间打印日志告知用户正在等待
- 不无限重试，设置最大重试次数

## 4. User Stories / Use Cases

作为用户，当 API 返回 429 时，我希望系统自动等待后重试，而不是直接跳过该视频。

## 5. Acceptance Criteria

- [x] AC-1: Bilibili API 返回 429 时暂停 1 分钟后重试
- [x] AC-2: LLM API 返回 429 时同样暂停后重试
- [x] AC-3: 暂停时长从配置读取

## 6. Out of Scope

- 指数退避策略（后续可优化）
- 按 API 维度独立限流

## 7. Open Questions

无
