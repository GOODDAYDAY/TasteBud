# rate-limit-429 — Technical Design

| Field       | Value          |
|-------------|----------------|
| Requirement | REQ-005        |
| Status      | 🟡 IN PROGRESS |
| Created     | 2026-03-09     |
| Updated     | 2026-03-09     |

## 1. Overview

在 BilibiliClient._get() 和 LLM analyzer 的 HTTP 调用层添加 429 检测与自动重试。收到 429 后暂停可配置时长（默认 60
秒），打印日志，然后重试，最多重试 3 次。

## 2. Architecture Changes

### 2.1 Data Model Changes

无

### 2.2 API Changes

无

### 2.3 Service Layer Changes

- BilibiliClient._get() / _get_wbi(): 捕获 429，暂停后重试
- CommentAnalyzer（LLM 调用）: 捕获 429，暂停后重试

## 3. Detailed Design

### 3.1 BilibiliClient 429 处理

在 `_get()` 方法中，检查 response status code。如果是 429，sleep 配置时长后重试，最多 3 次。

### 3.2 LLM API 429 处理

在 `analyzer.py` 的 `_call_openai_compatible()` 中同样处理 429。

## 4. File Change List

| File                             | Action | Description        |
|----------------------------------|--------|--------------------|
| src/plugin/bilibili/client.py    | Modify | _get() 添加 429 重试逻辑 |
| src/analyzer/comment/analyzer.py | Modify | LLM 调用添加 429 重试逻辑  |

## 5. Testing Strategy

- 手动测试：高频请求触发 429 后观察自动暂停与恢复

## 6. Migration & Rollback

无

## 7. Risks & Mitigations

| Risk          | Impact | Mitigation     |
|---------------|--------|----------------|
| 暂停时间不够长仍然 429 | 继续失败   | 最多重试 3 次，超过则跳过 |
