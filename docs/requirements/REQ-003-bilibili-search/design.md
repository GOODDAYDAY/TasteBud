# Bilibili Search — Technical Design

| Field       | Value      |
|-------------|------------|
| Requirement | REQ-003    |
| Status      | ✅ DONE     |
| Created     | 2026-03-08 |
| Updated     | 2026-03-08 |

## 1. Overview

两个独立变更：

1. **搜索模式**：`BilibiliClient` 新增 `search_videos()` API，`BilibiliCommentCollector` 新增 `collect_by_search()` 方法，
   `BilibiliPlugin` 新增 `mode == "search"` 分支。
2. **持续运行**：`pipeline/main.py` 的 `run_all()` 改为循环执行，移除 `schedule` 字段。

## 2. Architecture Changes

### 2.1 Data Model Changes

`CollectorConfig` 新增 `search_order` 字段：

```python
@dataclass
class CollectorConfig:
    ...
    search_order: str = "pubdate"  # "pubdate" | "click" | "scores"
```

移除 `PipelineConfig.schedule` 字段。

### 2.2 API Changes

无 REST API 变更。新增 Bilibili 搜索 API 调用：

```
GET https://api.bilibili.com/x/web-interface/search/type
  ?search_type=video
  &keyword={keyword}
  &order={order}
  &page={page}
```

### 2.3 Service Layer Changes

无。

## 3. Detailed Design

### 3.1 BilibiliClient.search_videos()

```python
async def search_videos(
    self, keyword: str, order: str = "pubdate",
    page: int = 1, page_size: int = 20,
) -> dict:
    return await self._get(
        "https://api.bilibili.com/x/web-interface/search/type",
        params={
            "search_type": "video",
            "keyword": keyword,
            "order": order,
            "page": page,
            "pagesize": page_size,
        },
    )
```

### 3.2 BilibiliCommentCollector.collect_by_search()

```python
async def collect_by_search(
    self, keyword: str, order: str = "pubdate", max_videos: int = 20,
) -> list[CommentBatch]:
    resp = await self._client.search_videos(keyword, order=order)
    results = resp.get("data", {}).get("result", [])

    batches = []
    for item in results[:max_videos]:
        bvid = item.get("bvid", "")
        if not bvid:
            continue
        batch = await self.collect_by_video(bvid)
        if batch.comments:
            batches.append(batch)
    return batches
```

### 3.3 持续运行循环

```python
async def run_loop(pipelines_dir, data_dir, interval_minutes):
    round_num = 0
    while True:
        round_num += 1
        print(f"\n=== Round {round_num} | {datetime.now():%H:%M:%S} ===")
        await run_all(pipelines_dir, data_dir)
        print(f"  Next round in {interval_minutes} minutes. Ctrl+C to exit.")
        await asyncio.sleep(interval_minutes * 60)
```

## 4. File Change List

| File                                       | Action | Description                      |
|--------------------------------------------|--------|----------------------------------|
| `backend/src/plugin/bilibili/client.py`    | Modify | 新增 `search_videos()`             |
| `backend/src/plugin/bilibili/collector.py` | Modify | 新增 `collect_by_search()`         |
| `backend/src/plugin/bilibili/plugin.py`    | Modify | 新增 `mode == "search"` 分支         |
| `backend/src/pipeline/models.py`           | Modify | 新增 `search_order`，移除 `schedule`  |
| `backend/src/pipeline/config.py`           | Modify | 解析 `search_order`，移除 `schedule`  |
| `backend/src/pipeline/main.py`             | Modify | `run_all` 改循环，新增 `--interval` 参数 |
| `pipelines/bilibili.yaml`                  | Modify | 移除 `schedule`，改为 search 示例       |
| `backend/tests/test_pipeline_config.py`    | Modify | 更新测试                             |

## 5. Testing Strategy

- [x] Unit tests: `search_videos` API 参数构造
- [x] Unit tests: `collect_by_search` 从搜索结果采集评论
- [x] Unit tests: `CollectorConfig.search_order` 解析
- [x] Unit tests: `PipelineConfig` 不再有 `schedule`

## 6. Migration & Rollback

无数据库迁移。YAML 配置中 `schedule` 字段变为可选/忽略，向后兼容。

## 7. Risks & Mitigations

| Risk               | Impact | Mitigation      |
|--------------------|--------|-----------------|
| Bilibili 搜索 API 限流 | 搜索失败   | 复用已有限速机制（≥1s/次） |
| 搜索结果视频量大           | 采集耗时   | `max_videos` 限制 |
| 持续运行内存泄漏           | 进程膨胀   | 每轮独立执行，无累积状态    |
