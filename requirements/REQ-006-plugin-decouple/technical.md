# plugin-decouple — Technical Design

| Field       | Value          |
|-------------|----------------|
| Requirement | REQ-006        |
| Status      | 🟡 IN PROGRESS |
| Created     | 2026-03-09     |
| Updated     | 2026-03-09     |

## 1. Overview

将 bilibili 专属逻辑从核心层剥离，使插件架构真正可扩展。核心改动 4 处：

1. CollectorConfig 瘦身 → 平台配置放 `plugin_config: dict`
2. config.py 不再解析平台字段 → collector 段原样传给插件
3. Comment.id / author_id / parent_id 改 str → 兼容所有平台
4. BasePlugin 新增 `parse_config()` → 插件自己解析配置

## 2. Architecture Changes

### 2.1 Data Model Changes

**CollectorConfig** 瘦身：

```python
@dataclass
class CollectorConfig:
    type: str = "bilibili"
    plugin_config: dict = field(default_factory=dict)  # 原样传给插件
```

移除: mode, target, max_videos, include_replies, cookie_path, search_order

**Comment** ID 泛化：

```python
@dataclass
class Comment:
    id: str              # was int
    author_id: str       # was int
    parent_id: str | None = None  # was int | None
```

### 2.2 API Changes

无

### 2.3 Service Layer Changes

**BasePlugin** 新增方法：

```python
def parse_config(self, raw: dict) -> None:
    """Parse plugin-specific config from YAML collector section."""
```

**config.py**：collector 段只提取 type，其余原样存入 plugin_config。

**runner.py**：调用 `plugin.parse_config(config.collector.plugin_config)` 后再 collect。

**bilibili plugin.py**：从 plugin_config 中读取 mode/target/cookie_path 等。

## 3. Detailed Design

### 3.1 Step 1: Comment ID 改 str

改 core/comment.py 中 id, author_id, parent_id 类型。
更新 bilibili collector 中所有 int 比较改为 str 比较（cursor 用 int 转换比较大小）。

### 3.2 Step 2: CollectorConfig 瘦身

只保留 type + plugin_config。

### 3.3 Step 3: config.py 通用化

collector 段除 type 外全部放入 plugin_config dict。

### 3.4 Step 4: BasePlugin.parse_config()

新增方法，bilibili plugin 实现从 dict 中提取自己的字段。

### 3.5 Step 5: runner.py 适配

collect 前调用 parse_config。plugin.collect() 签名从接收 PipelineConfig 改为不再依赖 collector 内的平台字段。

### 3.6 Step 6: bilibili plugin 适配

BilibiliPlugin 内部存储解析后的配置，collect/ensure_auth 从内部状态读取。

## 4. File Change List

| File                             | Action | Description                  |
|----------------------------------|--------|------------------------------|
| src/core/comment.py              | Modify | id/author_id/parent_id 改 str |
| src/pipeline/models.py           | Modify | CollectorConfig 瘦身           |
| src/pipeline/config.py           | Modify | collector 段通用化解析             |
| src/pipeline/base.py             | Modify | BasePlugin 新增 parse_config() |
| src/pipeline/runner.py           | Modify | collect 前调用 parse_config     |
| src/plugin/bilibili/plugin.py    | Modify | 实现 parse_config，适配新接口        |
| src/plugin/bilibili/collector.py | Modify | cursor 比较适配 str id           |
| src/plugin/bilibili/models.py    | Modify | Cursor.last_rpid 比较逻辑        |
| src/analyzer/comment/analyzer.py | Modify | 适配 str id（影响极小）              |

## 5. Testing Strategy

- 手动运行现有 bilibili pipeline 验证功能不变
- 代码审查：确认核心层无任何 bilibili 专属引用

## 6. Migration & Rollback

无数据库。已存储的 JSON 文件中 id 为 int，反序列化时转 str 即可兼容。

## 7. Risks & Mitigations

| Risk                    | Impact    | Mitigation                  |
|-------------------------|-----------|-----------------------------|
| cursor 比较逻辑改变           | 增量采集可能重复  | bilibili cursor 内部仍用 int 比较 |
| 旧 batch JSON 中 id 为 int | 反序列化类型不匹配 | deserialize 时统一 str() 转换    |
