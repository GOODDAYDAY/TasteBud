# Batch Analysis — Technical Design

| Field       | Value      |
|-------------|------------|
| Requirement | REQ-004    |
| Status      | 🔵 NEW     |
| Created     | 2026-03-08 |
| Updated     | 2026-03-08 |

## 1. Overview

两个核心变更：

1. **窗口机制从 per-target 改为 per-pipeline**：一轮采集结束后，汇总本轮所有新评论数与历史 pending 数，达到阈值触发分析。分析时加载所有
   target 的 pending 评论，合并为一个大批次。
2. **支持 GitHub Copilot provider**：本质上是 OpenAI 兼容 API，base_url 为 `https://api.githubcopilot.com`，需在
   `_call_llm` 中正确路由。

### 当前问题根因

```
runner.run() 流程:
  for batch in batches:          # 逐个 target 检查
    if should_analyze(target):   # 单个 target pending >= 100?
      analyze(target)            # 几乎永远不触发
```

搜索 20 个视频，每个视频 10-50 条评论，单个视频永远达不到 100。

### 改后流程

```
runner.run() 流程:
  collect all batches
  total_pending = sum of all pending across all targets
  if total_pending >= window_size:
    all_comments = load pending from ALL targets
    analyze(all_comments)         # 跨视频合并分析
    reset ALL targets' pending
```

## 2. Architecture Changes

### 2.1 Data Model Changes

无新数据模型。`pending_count.json` 机制保持不变（仍按 target 存储），但 runner 改为汇总所有 target 的 pending 做判断。

分析结果保存路径从 `{platform}/video/{bvid}/analysis/` 改为 `{platform}/analysis/`（pipeline 级别）。

### 2.2 API Changes

无。

### 2.3 Service Layer Changes

**runner.py** — 核心改动：

```python
# Before: per-target window check
for batch in batches:
    if should_analyze(platform_dir, batch.target_type, batch.target_id, threshold):
        ...

# After: pipeline-level window check
total_pending = sum(
    get_pending_count(platform_dir, b.target_type, b.target_id)
    for b in batches
)
if total_pending >= threshold:
    all_pending = []
    for batch in batches:
        all_pending.extend(self._load_pending_comments(...))
    result = await self._analyze(config, all_pending, ...)
    for batch in batches:
        reset_pending(...)
```

**analyzer.py** — 新增 `github-copilot` provider 路由（复用 `_call_openai_compatible`）。

## 3. Detailed Design

### 3.1 Step 1: Runner 窗口逻辑改为 pipeline 级别汇总

改动 `runner.py` 的 step 3（分析触发判断）：

- 采集完成后，遍历所有参与的 batch，汇总 pending 总数
- 如果总数 >= window_size，加载所有 target 的 pending 评论
- 合并分析，分析结果保存在 `{platform}/analysis/` 下
- 重置所有参与 target 的 pending 计数

### 3.2 Step 2: 支持 GitHub Copilot provider

在 `CommentAnalyzer._call_llm()` 中添加 `github-copilot` 分支，复用 `_call_openai_compatible()`，base_url 默认指向
`https://api.githubcopilot.com`。

### 3.3 Step 3: 分析结果路径调整

分析结果从 per-target 路径移到 pipeline 级别：

- Before: `{platform}/video/{bvid}/analysis/result_{ts}.json`
- After: `{platform}/analysis/result_{ts}.json`

## 4. File Change List

| File                                       | Action | Description                     |
|--------------------------------------------|--------|---------------------------------|
| `backend/src/pipeline/runner.py`           | Modify | 窗口逻辑改为 pipeline 级别汇总；分析结果保存路径调整 |
| `backend/src/analyzer/comment/analyzer.py` | Modify | 新增 `github-copilot` provider 路由 |
| `pipelines/bilibili-search.yaml`           | Modify | 添加 Copilot 配置示例                 |
| `pipelines/bilibili-user.yaml`             | Modify | 添加 Copilot 配置示例                 |

## 5. Testing Strategy

- [ ] Unit tests: pipeline 级别 pending 汇总逻辑
- [ ] Unit tests: `github-copilot` provider 路由到 openai-compatible
- [ ] Integration tests: 手动验证 Copilot token 能成功调用分析

## 6. Migration & Rollback

无数据库迁移。旧的 per-target analysis 文件保留，新的写入 pipeline 级别目录。

## 7. Risks & Mitigations

| Risk                 | Impact | Mitigation             |
|----------------------|--------|------------------------|
| Copilot API token 限流 | 分析失败   | 重试 + 不重置 pending（下轮继续） |
| 合并评论量过大超 token 限制    | LLM 报错 | 已有 max_comments 采样机制   |
| 跨视频合并后上下文混乱          | 分析质量下降 | prompt 中保留每条评论的视频来源信息  |
