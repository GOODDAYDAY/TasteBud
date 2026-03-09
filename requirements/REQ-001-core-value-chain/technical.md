# Core Value Chain — Technical Design

| Field       | Value      |
|-------------|------------|
| Requirement | REQ-001    |
| Status      | ✅ DONE     |
| Created     | 2026-03-08 |
| Updated     | 2026-03-08 |

## 1. Overview

TasteBud 核心价值链的技术实现，采用模块化架构，以文件系统为存储层，全链路 async，支持可选组件的优雅降级。

```
Collect ──→ Analyze ──→ Score ──→ Feedback ──→ Learn
  │            │          │          │            │
  ▼            ▼          ▼          ▼            ▼
RawContent  Analysis   ScoredItem   Rating    Preferences
             Result                             (updated)
```

## 2. Architecture

### 2.1 模块依赖关系

```
core/
  ├── config.py          Settings (pydantic-settings, .env)
  ├── exceptions.py      Exception hierarchy
  └── logging.py         Structlog setup

collector/
  ├── base.py            BaseCollector, RawContent, TagResult (ABC)
  ├── storage.py         File I/O for all data artifacts
  └── {source}/          Per-source collector implementations

analyzer/
  ├── base.py            BaseAnalyzer, AnalysisResult (ABC)
  ├── source_tag/        Tag-only analyzer (zero dependencies)
  ├── clip/              CLIP embedding analyzer (optional: sentence-transformers)
  └── vlm/               VLM analyzer via Ollama (optional: Ollama server)

engine/
  ├── scorer.py          TagScorer — tag weight × confidence
  ├── preference.py      Preference read/write
  ├── feedback.py        Feedback submission + preference learning
  ├── schema.py          Category evaluation dimension schemas
  └── sieve.py           Three-layer filtering pipeline
```

**依赖方向**: `core ← collector ← analyzer ← engine`（单向依赖，无循环）

### 2.2 Storage Layout

```
downloads/{category}/
  schema.json                 评价维度定义
  preferences.json            标签权重偏好
  feedback_log.jsonl          追加式反馈日志（数据源头）
  clip_baseline.json          CLIP 口味基线向量（可选）
  {source}/{source_id}/
    data.json                 采集元数据
    tags.txt                  人可读标签
    download.json             下载完成标记
    analysis.json             分析结果
    feedback.json             单项评价
    sieve.json                三层筛选结果
    images/                   下载的图片
```

### 2.3 配置管理

通过 `core/config.py` 的 `Settings` 类集中管理，使用 pydantic-settings 从环境变量 / `.env` 加载：

| Key                      | Default                    | Description  |
|--------------------------|----------------------------|--------------|
| `download_dir`           | `{project_root}/downloads` | 内容存储根目录      |
| `sieve_layer1_threshold` | 0.3                        | Layer 1 快筛阈值 |
| `sieve_layer2_threshold` | 0.2                        | Layer 2 深筛阈值 |
| `clip_model`             | `clip-ViT-B-32`            | CLIP 模型      |
| `ollama_base_url`        | `http://localhost:11434`   | Ollama 服务地址  |
| `ollama_model`           | `moondream`                | VLM 模型名      |

## 3. Detailed Design

### 3.1 Collect — 内容采集

```python
class BaseCollector(ABC):
    category: str  # e.g. "manga"
    source: str  # e.g. "ehentai"

    async def collect(**kwargs) -> list[RawContent]

        def parse_tags(raw, **kwargs) -> list[TagResult]
```

- `RawContent`: 统一数据结构，包含 source, source_id, title, url, thumbnail_url, tags, metadata
- `TagResult`: name + category + confidence (default 1.0)
- `storage.save_metadata()`: 写入 `data.json`（JSON 序列化）+ `tags.txt`（人可读分组）

### 3.2 Analyze — 内容分析

**三种分析器，渐进增强：**

| Analyzer            | 依赖                    | 输入     | 核心逻辑                                |
|---------------------|-----------------------|--------|-------------------------------------|
| `SourceTagAnalyzer` | 无                     | tags   | 规则映射：标签 → style/theme/mood/warnings |
| `CLIPAnalyzer`      | sentence-transformers | images | 图像嵌入 → 与基线余弦相似度                     |
| `VLMAnalyzer`       | Ollama server         | images | 发送图片到 VLM → 结构化 JSON 分析             |

**SourceTagAnalyzer 映射规则**:

- theme: 从 parody/character 类标签提取
- mood: 匹配预定义集合 {dark, comedy, horror, romance, ...}
- style: 匹配预定义集合 {watercolor, sketch, digital, ...}
- warnings: 匹配预定义集合 {gore, violence, ...}
- quality: 从 metadata 中的 rating 归一化 (0-5 → 0-1)

**VLMAnalyzer 流程**:

1. 从 images/ 目录等间距选取 4 张样本图
2. 逐张发送到 Ollama API，要求返回 JSON
3. 合并多图结果：取最常见 style、平均 quality、去重 mood/warnings

### 3.3 Score — 评分引擎

```python
class TagScorer:
    def score(preferences, content_tags) -> tuple[float, list[str]]:
        raw = sum(pref[tag.name] * tag.confidence for tag in tags if tag.name in pref)
        return raw, matched_tags
```

Sigmoid 归一化：`normalized = 1 / (1 + exp(-raw))`，将任意范围映射到 (0, 1)。

### 3.4 Feedback — 反馈系统

**数据流**:

```
用户评价 (like/dislike)
    ├──→ feedback_log.jsonl   (追加写入，永不覆盖)
    ├──→ feedback.json        (单项最新评价)
    └──→ preferences.json    (实时更新权重)
```

**学习算法**:

```
for tag in item.tags:
    preferences[tag] += LEARN_RATE if rating == "like" else -LEARN_RATE
```

- `LEARN_RATE = 0.5`
- Replay: 清空偏好 → 按日志顺序重新应用所有反馈 → 幂等

### 3.5 Sieve — 三层筛选管道

```
Layer 1 (Quick Sieve)          Layer 2 (Deep Scan)         Layer 3 (User Eval)
──────────────────────        ──────────────────────       ──────────────────
Input: tags + thumbnail       Input: downloaded images     Input: human rating
Method: TagScorer + CLIP      Method: VLM via Ollama       Method: like / dislike
Score: 0.5×tag + 0.5×clip     Score: quality × penalty     Score: 1.0 or 0.0
Threshold: configurable       Threshold: configurable      Threshold: N/A
Cost: Low (ms)                Cost: High (seconds)         Cost: Human time
```

**Layer 1 详细流程**:

1. `TagScorer.score()` → raw → sigmoid → tag_score
2. 如有 CLIP baseline: 下载 thumbnail → 计算嵌入 → 余弦相似度 → clip_score
3. combined = 0.5 × tag_score + 0.5 × clip_score（无 CLIP 则仅用 tag_score）
4. passed = combined ≥ threshold

**Layer 2 详细流程**:

1. 调用 `VLMAnalyzer.analyze()` 获取 AnalysisResult
2. score = analysis.quality
3. 如有 content_warnings: score *= 0.7
4. Ollama 不可用时优雅跳过（passed=True, score=0.0）

## 4. File Change List

| File                                          | Action  | Description                          |
|-----------------------------------------------|---------|--------------------------------------|
| `backend/src/core/config.py`                  | Created | 全局配置（pydantic-settings）              |
| `backend/src/core/exceptions.py`              | Created | 领域异常层次结构                             |
| `backend/src/core/logging.py`                 | Created | Structlog 配置                         |
| `backend/src/collector/base.py`               | Created | BaseCollector, RawContent, TagResult |
| `backend/src/collector/storage.py`            | Created | 文件存储所有数据工件                           |
| `backend/src/analyzer/base.py`                | Created | BaseAnalyzer, AnalysisResult         |
| `backend/src/analyzer/source_tag/analyzer.py` | Created | 纯标签分析器                               |
| `backend/src/analyzer/clip/analyzer.py`       | Created | CLIP 嵌入分析器                           |
| `backend/src/analyzer/vlm/analyzer.py`        | Created | VLM 视觉分析器                            |
| `backend/src/engine/scorer.py`                | Created | 标签评分引擎                               |
| `backend/src/engine/preference.py`            | Created | 偏好读写                                 |
| `backend/src/engine/feedback.py`              | Created | 反馈提交 + 学习                            |
| `backend/src/engine/schema.py`                | Created | 分类评价维度管理                             |
| `backend/src/engine/sieve.py`                 | Created | 三层筛选管道                               |
| `scripts/main.py`                             | Created | 交互式 CLI 入口                           |

## 5. Testing Strategy

- [x] Unit tests: `test_scorer.py` — TagScorer 评分逻辑（6 tests）
- [x] Unit tests: `test_analyzer.py` — SourceTagAnalyzer 标签映射（8 tests）
- [x] Unit tests: `test_feedback.py` — 偏好学习 + 反馈日志（14 tests）
- [x] Unit tests: `test_sieve.py` — 三层筛选管道（19 tests）
- [x] Unit tests: `test_storage_sieve.py` — 筛选结果存储（6 tests）
- [x] 总计: 53+ tests，覆盖核心逻辑

## 6. Migration & Rollback

当前为文件系统存储，无数据库迁移需求。

未来迁移到 SQLAlchemy + SQLite 时需要：

1. 设计 ORM 模型对应当前 dataclass
2. 编写数据迁移脚本（JSON → SQLite）
3. 实现 Repository 层替换直接文件 I/O

## 7. Risks & Mitigations

| Risk          | Impact     | Mitigation                     |
|---------------|------------|--------------------------------|
| 文件系统存储不支持并发写入 | 数据损坏       | 单用户 CLI 模式，无并发风险；迁移 DB 后解决     |
| Ollama 服务不可用  | Layer 2 失效 | 优雅降级：跳过 Layer 2，标记 passed=True |
| CLIP 依赖未安装    | Layer 1 降级 | 仅用标签评分，无 CLIP 加成               |
| 学习率固定（0.5）    | 偏好收敛速度不可调  | 支持 replay 重建，未来可调参             |
| 单一内容源         | 扩展性受限      | BaseCollector 抽象接口，新源只需实现子类    |
