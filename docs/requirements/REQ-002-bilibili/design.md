# Bilibili — Technical Design

| Field       | Value          |
|-------------|----------------|
| Requirement | REQ-002        |
| Status      | 🟡 IN PROGRESS |
| Created     | 2026-03-08     |
| Updated     | 2026-03-08     |

## 1. Overview

本需求引入三个架构级别的变化：

1. **BilibiliCommentCollector** — 继承 BaseCollector 的评论采集器，增量采集 + 登录态
2. **CommentAnalyzer** — 窗口触发的 AI 批量分析器，核心是痛点挖掘 + 技术可行性评估
3. **Notifier 层 + Pipeline 编排** — YAML 配置驱动的 Collect → Analyze → Notify 流水线

```
Pipeline Config (YAML)
    │
    ├── Collector: BilibiliCommentCollector
    │     ├── mode: user / video / article
    │     ├── target: UID / BV号 / CV号
    │     ├── auth: bilibili 库扫码 / Cookie
    │     └── cursor: last_rpid (增量)
    │
    ├── Window Buffer（评论缓冲区）
    │     └── 评论量达到阈值 → 触发分析
    │
    ├── Analyzer: CommentAnalyzer
    │     ├── LLM: Ollama / External API (API Token)
    │     ├── 痛点挖掘 + 技术可行性评估
    │     └── 输出: 结构化痛点报告（含原始评论上下文）
    │
    └── Notifier: EmailNotifier / WeChatNotifier
          ├── 每次分析完成 → 立即推送
          └── template rendering + retry
```

### 插件化架构

核心设计原则：**通用框架 + 平台插件**。所有平台特定代码（Bilibili API、模板渲染、数据模型）封装在 `plugin/{platform}/`
子包中，通用框架通过 `BasePlugin` 接口与插件交互。

```
BasePlugin (ABC)                      ← 插件接口
  ├── name: str                         插件名称
  ├── create_collector(config, base_dir) -> 采集器实例
  ├── render_notification(result) -> (title, body)   模板渲染
  └── get_prompt_template() -> str | None            自定义 prompt（可选）

BilibiliPlugin(BasePlugin)            ← Bilibili 具体实现
  ├── name = "bilibili"
  ├── create_collector() → BilibiliCommentCollector
  ├── render_notification() → Bilibili 专属模板
  └── 内部封装: client, auth, collector, models, cursor
```

新增平台只需：

1. 创建 `plugin/{platform}/` 子包
2. 实现 `BasePlugin` 接口
3. 在 Pipeline YAML 中配置 `collector.type: {platform}`
4. 无需修改 runner/notifier/analyzer 等通用代码

## 2. Architecture Changes

### 2.1 模块结构

```
backend/src/
  collector/
    base.py                           BaseCollector（已有，不动）
  analyzer/
    comment/
      analyzer.py                     CommentAnalyzer（通用 LLM 批量分析）
      models.py                       PainPoint, CommentAnalysisResult（通用）
      prompts.py                      默认 prompt 模板（通用）
      window.py                       分析窗口管理（通用）
  notifier/
    base.py                           BaseNotifier + Notification（通用接口）
    email.py                          EmailNotifier（通用渠道）
    wechat.py                         WeChatNotifier（通用渠道）
  pipeline/
    base.py                           BasePlugin 抽象接口
    config.py                         YAML 配置加载（通用）
    runner.py                         Pipeline 执行引擎（通用，通过 plugin 接口调用）
    models.py                         PipelineConfig, PipelineRun（通用）
  plugin/
    bilibili/                         ← Bilibili 插件（所有平台特定代码）
      client.py                         Bilibili API 客户端 + 限速
      auth.py                           Cookie 管理
      collector.py                      BilibiliCommentCollector
      models.py                         Comment, CommentBatch, VideoInfo, Cursor
      cursor.py                         增量游标
      template.py                       Bilibili 专属通知模板渲染
      plugin.py                         BilibiliPlugin（实现 BasePlugin）
```

**依赖方向**:

```
plugin/bilibili → pipeline/base (BasePlugin)
                → analyzer/comment (CommentAnalyzer, models)
                → notifier/base (Notification)

pipeline/runner → pipeline/base (BasePlugin)
               → analyzer/comment
               → notifier/*

通用框架 ← plugin （单向依赖，框架不依赖任何 plugin）
```

### 2.2 Data Model Changes

#### Comment（评论数据）

```python
@dataclass
class VideoInfo:
    """评论所属的视频/文章信息"""
    bvid: str                        # BV号
    avid: int                        # AV号
    title: str                       # 视频标题
    url: str                         # 视频链接
    up_mid: int                      # UP主 UID
    up_name: str                     # UP主名称

@dataclass
class Comment:
    rpid: int                        # 评论唯一 ID
    mid: int                         # 用户 UID
    uname: str                       # 用户名
    content: str                     # 评论正文
    ctime: datetime                  # 发布时间
    like: int                        # 点赞数
    reply_count: int                 # 回复数
    parent_rpid: int | None          # 父评论 ID（楼中楼，None=顶层评论）
    video: VideoInfo                 # 所属视频信息

@dataclass
class CommentBatch:
    source: str                      # "bilibili"
    target_type: str                 # "video" | "article" | "dynamic"
    target_id: str                   # BV号 / CV号 / 动态ID
    target_title: str                # 视频/文章标题
    comments: list[Comment]
    fetched_at: datetime
    cursor: str                      # 游标信息（下次增量起点）
```

#### PainPoint（痛点分析结果）

```python
@dataclass
class PainPoint:
    """AI 识别的单个用户痛点"""
    pain_description: str            # 痛点/难点描述
    feasibility: str                 # 技术可行性分析
    feasibility_level: str           # "high" | "medium" | "low" | "uncertain"
    source_comments: list[CommentContext]  # 支撑该痛点的原始评论列表

@dataclass
class CommentContext:
    """分析结果中引用的原始评论上下文"""
    content: str                     # 评论原始内容
    uname: str                       # 评论用户
    ctime: str                       # 评论时间
    video_title: str                 # 所属视频标题
    video_url: str                   # 视频链接
    rpid: int                        # 评论 ID

@dataclass
class CommentAnalysisResult:
    pipeline_name: str               # 所属 Pipeline
    target_id: str
    target_title: str
    total_comments_analyzed: int     # 本批次评论总数
    pain_points: list[PainPoint]     # 识别出的痛点列表
    raw_summary: str                 # AI 原始摘要文本
    analyzed_at: datetime
    llm_model: str                   # 使用的模型名称
```

#### Notification

```python
@dataclass
class Notification:
    channel: str  # "email" | "wechat"
    title: str
    body: str  # 渲染后的推送内容
    sent_at: datetime | None
    status: str  # "pending" | "sent" | "failed"
    retry_count: int
```

### 2.3 Storage Layout

```
downloads/bilibili-comments/
  pipelines/
    {pipeline_name}.yaml             Pipeline 配置
    {pipeline_name}.state.json       Pipeline 运行状态
  {target_type}/{target_id}/
    info.json                        视频/文章元信息
    comments/
      batch_{timestamp}.json         每次采集的评论批次
      cursor.json                    增量游标 {last_rpid, last_page}
      pending_count.json             待分析评论计数
    analysis/
      result_{timestamp}.json        每次 AI 分析结果
    notifications/
      log.jsonl                      推送历史记录
```

### 2.4 API Changes

本期不涉及 REST API，纯 CLI + YAML 配置驱动。

### 2.5 Service Layer Changes

无现有 Service 需要修改。所有新功能通过新模块实现。

## 3. Detailed Design

### 3.1 Step 1: Bilibili Auth — 登录态管理

优先查找是否有成熟的 bilibili 第三方库（如 `bilibili-api-python`），使用其扫码登录能力。

```python
class BilibiliAuth:
    """管理 Bilibili 登录态"""

    @staticmethod
    async def login_qr() -> dict[str, str]:
        """扫码登录，返回 cookie dict"""

    @staticmethod
    def load_cookie(path: Path) -> dict[str, str] | None:
        """从文件加载已保存的 cookie"""

    @staticmethod
    def save_cookie(cookie: dict[str, str], path: Path) -> None:
        """保存 cookie 到文件"""
```

- 首次运行：触发扫码登录 → 保存 Cookie 到本地
- 后续运行：加载已保存的 Cookie
- Cookie 过期：日志告警 + 推送通知用户重新登录

### 3.2 Step 2: Bilibili API Client — HTTP 封装

```python
class BilibiliClient:
    """Async HTTP client for Bilibili API with rate limiting."""

    def __init__(self, cookie: dict[str, str] | None = None):
        self._rate_limiter: float = 1.0  # 最小请求间隔（秒）

    async def get_user_videos(self, mid: int, page: int = 1) -> list[dict]:
        """获取 UP 主视频列表"""

    async def get_comments(
        self, oid: int, type_: int = 1, sort: int = 0, pn: int = 1
    ) -> dict:
        """获取评论列表（sort=0 按时间）"""

    async def get_comment_replies(
        self, oid: int, rpid: int, pn: int = 1
    ) -> dict:
        """获取楼中楼回复"""

    async def bv_to_av(self, bvid: str) -> int:
        """BV 号 → AV 号转换（本地算法）"""
```

Bilibili 评论 API：

- 评论列表: `GET https://api.bilibili.com/x/v2/reply`
    - `oid`: AV 号
    - `type`: 1=视频, 12=专栏, 17=动态
    - `sort`: 0=按时间, 2=按热度
    - `pn`/`ps`: 分页（ps 最大 20）
- 楼中楼: `GET https://api.bilibili.com/x/v2/reply/reply`
    - `root`: 根评论 rpid
- UP 主视频: `GET https://api.bilibili.com/x/space/wbi/arc/search`

限速实现：每次请求前 `await asyncio.sleep(self._rate_limiter)`。

### 3.3 Step 3: BilibiliCommentCollector — 增量采集

```python
class BilibiliCommentCollector(CommentCollector):
    category = "bilibili-comments"
    source = "bilibili"

    async def collect_by_video(self, bvid: str) -> CommentBatch:
        """采集单个视频的评论（增量）"""

    async def collect_by_user(
        self, mid: int, max_videos: int = 10
    ) -> list[CommentBatch]:
        """采集 UP 主最新 N 个视频的评论"""

    async def collect_by_article(self, cvid: int) -> CommentBatch:
        """采集专栏评论"""
```

增量采集流程：

1. 读取 `cursor.json` → `last_rpid`
2. 按时间排序（sort=0）采集评论
3. 逐页遍历，直到 `rpid <= last_rpid` → 停止
4. 每条评论附带 `VideoInfo` 上下文
5. 更新 `cursor.json` → 本次最大 rpid
6. 更新 `pending_count.json` → 待分析计数 +N
7. 返回 `CommentBatch`（仅含新评论）

### 3.4 Step 4: Analysis Window — 分析窗口

```python
class AnalysisWindow:
    """管理评论分析窗口，达到阈值触发分析"""

    def __init__(self, threshold: int = 100):
        self.threshold = threshold

    def should_analyze(self, target_id: str) -> bool:
        """检查该目标的待分析评论是否达到阈值"""

    def get_pending_comments(self, target_id: str) -> list[Comment]:
        """获取所有待分析评论"""

    def mark_analyzed(self, target_id: str) -> None:
        """标记已分析，重置计数器"""
```

触发逻辑：

```
采集完成 → pending_count += len(new_comments)
if pending_count >= window_threshold:
    batch = load all pending comments
    result = await analyzer.analyze(batch)
    save result
    reset pending_count
    notify(result)
```

### 3.5 Step 5: CommentAnalyzer — AI 痛点分析

```python
class CommentAnalyzer:
    """批量分析评论，挖掘用户痛点 + 技术可行性评估"""

    def __init__(self, llm_config: LLMConfig):
        """llm_config 包含 provider/model/api_token/base_url"""

    async def analyze(self, comments: list[Comment]) -> CommentAnalysisResult:
        """批量分析评论"""
```

LLM Prompt 设计（`prompts.py`）：

```
你是一个产品分析专家。以下是来自 Bilibili 视频评论区的用户评论。

请分析这些评论，完成以下任务：
1. 识别用户遇到的所有痛点、难点和未被满足的需求
2. 对每个痛点，评估当前技术是否能够解决（可行性为 high/medium/low/uncertain）
3. 对每个痛点，列出支撑该判断的原始评论

输出格式（JSON）：
{
  "pain_points": [
    {
      "description": "痛点描述",
      "feasibility": "技术可行性分析",
      "feasibility_level": "high|medium|low|uncertain",
      "source_comment_indices": [0, 3, 7]  // 引用的评论索引
    }
  ],
  "summary": "整体评论区概况"
}

评论列表：
[每条评论带编号 + 视频标题 + 用户名 + 时间 + 正文]
```

LLM 提供者配置：

```python
@dataclass
class LLMConfig:
    provider: str          # "ollama" | "openai" | "anthropic" | "custom"
    model: str             # 模型名
    api_token: str         # API Token（从环境变量读取）
    base_url: str          # API 地址（Ollama: localhost:11434）
    max_comments: int      # 单次最多发送评论数（避免超 token 限制）
```

评论过多时的采样策略：

- 如果超过 `max_comments`，取 top-N 高赞 + 最新 N 条 + 随机 N 条

### 3.6 Step 6: Notifier — 推送

```python
class BaseNotifier(ABC):
    async def send(self, notification: Notification) -> bool


class EmailNotifier(BaseNotifier):
    """SMTP 推送，支持 HTML 格式"""


class WeChatNotifier(BaseNotifier):
    """企业微信/PushPlus Webhook 推送，支持 Markdown"""
```

推送模板（`template.py`）：

```
[TasteBud] {pipeline_name} 评论分析报告

分析了 {total} 条新评论，发现 {count} 个用户痛点：

---
痛点 1: {description}
可行性: {feasibility_level} — {feasibility}
相关评论:
  - [{uname}] {video_title}: "{content}" ({ctime})
  - ...
---

痛点 2: ...
```

重试策略：失败后 1s → 2s → 4s 指数退避，最多 3 次。

### 3.7 Step 7: Pipeline 编排

Pipeline YAML 配置示例：

```yaml
name: monitor_tech_up
description: "监控某技术 UP 主的评论区痛点"
schedule: "*/30 * * * *"             # 每 30 分钟采集一次

collector:
  type: bilibili
  mode: user                         # user / video / article
  target: "12345678"                 # UP主 UID
  max_videos: 5                      # 最近 5 个视频
  include_replies: true              # 包含楼中楼
  auth:
    method: qr                       # qr (扫码) / cookie (手动)
    cookie_path: ~/.tastebud/bilibili_cookie.json

analyzer:
  window_size: 100                   # 100 条新评论触发一次分析
  llm:
    provider: ollama                 # ollama / openai / anthropic
    model: qwen2.5:14b
    base_url: http://localhost:11434
    api_token_env: LLM_API_TOKEN     # 环境变量名（外部 API 时使用）
    max_comments: 200                # 单次最多分析评论数

notifier:
  - type: wechat
    webhook_env: WECHAT_WEBHOOK      # Webhook URL 环境变量
  - type: email
    smtp_host: smtp.example.com
    smtp_port: 465
    smtp_user_env: SMTP_USER
    smtp_pass_env: SMTP_PASS
    to: "user@example.com"
```

Pipeline Runner 执行流程：

```python
class PipelineRunner:
    async def run(self, config: PipelineConfig) -> PipelineRun:
        # 1. 实例化 Collector + Auth
        collector = BilibiliCommentCollector(auth=config.auth)

        # 2. 增量采集
        batches = await collector.collect(config.collector)

        # 3. 合并新评论，更新待分析计数
        new_comments = flatten(batches)
        window.add(new_comments)

        # 4. 检查窗口阈值
        if not window.should_analyze():
            return PipelineRun(status="collected", new_comments=len(new_comments))

        # 5. 触发 AI 分析
        pending = window.get_pending_comments()
        result = await analyzer.analyze(pending)
        save_analysis(result)
        window.mark_analyzed()

        # 6. 推送
        for notifier in config.notifiers:
            notification = render_template(result)
            await notifier.send(notification)

        return PipelineRun(status="analyzed_and_notified", pain_points=len(result.pain_points))
```

## 4. File Change List

### 通用框架

| File                                       | Action | Description                            |
|--------------------------------------------|--------|----------------------------------------|
| `backend/src/analyzer/comment/analyzer.py` | Create | CommentAnalyzer（通用 LLM 批量分析）           |
| `backend/src/analyzer/comment/models.py`   | Create | PainPoint, CommentAnalysisResult（通用模型） |
| `backend/src/analyzer/comment/prompts.py`  | Create | 默认 prompt 模板（通用）                       |
| `backend/src/analyzer/comment/window.py`   | Create | 分析窗口管理（通用）                             |
| `backend/src/notifier/base.py`             | Create | BaseNotifier + Notification（通用接口）      |
| `backend/src/notifier/email.py`            | Create | EmailNotifier（通用 SMTP）                 |
| `backend/src/notifier/wechat.py`           | Create | WeChatNotifier（通用 Webhook）             |
| `backend/src/pipeline/base.py`             | Create | BasePlugin 抽象接口                        |
| `backend/src/pipeline/config.py`           | Create | YAML 配置加载（通用）                          |
| `backend/src/pipeline/runner.py`           | Create | Pipeline 执行引擎（通用，通过 plugin 接口）         |
| `backend/src/pipeline/models.py`           | Create | PipelineConfig, PipelineRun（通用）        |

### Bilibili 插件

| File                                       | Action | Description                              |
|--------------------------------------------|--------|------------------------------------------|
| `backend/src/plugin/bilibili/client.py`    | Create | Bilibili API 客户端 + 限速                    |
| `backend/src/plugin/bilibili/auth.py`      | Create | Cookie 管理                                |
| `backend/src/plugin/bilibili/collector.py` | Create | BilibiliCommentCollector                 |
| `backend/src/plugin/bilibili/models.py`    | Create | Comment, CommentBatch, VideoInfo, Cursor |
| `backend/src/plugin/bilibili/cursor.py`    | Create | 增量游标管理                                   |
| `backend/src/plugin/bilibili/template.py`  | Create | Bilibili 专属通知模板渲染                        |
| `backend/src/plugin/bilibili/plugin.py`    | Create | BilibiliPlugin（实现 BasePlugin）            |

### 配置 & 测试

| File                                     | Action | Description               |
|------------------------------------------|--------|---------------------------|
| `backend/pyproject.toml`                 | Modify | 新增依赖 (pyyaml)，新增 plugin 包 |
| `backend/tests/test_bilibili_client.py`  | Create | BV→AV 转换测试                |
| `backend/tests/test_bilibili_cursor.py`  | Create | 增量游标测试                    |
| `backend/tests/test_comment_analyzer.py` | Create | Prompt 构建 + 响应解析测试        |
| `backend/tests/test_analysis_window.py`  | Create | 窗口阈值测试                    |
| `backend/tests/test_notifier.py`         | Create | 模板渲染测试                    |
| `backend/tests/test_pipeline_config.py`  | Create | YAML 配置加载测试               |

## 5. Testing Strategy

- [ ] Unit tests: BilibiliClient API 响应解析（mock httpx）
- [ ] Unit tests: BV→AV 转换算法
- [ ] Unit tests: CommentCollector 增量逻辑（cursor 读写 + rpid 去重）
- [ ] Unit tests: AnalysisWindow 阈值判断 + 计数器重置
- [ ] Unit tests: CommentAnalyzer LLM prompt 构建 + 响应解析（mock LLM）
- [ ] Unit tests: Notifier 模板渲染（痛点格式化）
- [ ] Unit tests: Notifier 发送 + 重试逻辑（mock SMTP/Webhook）
- [ ] Unit tests: Pipeline YAML 配置加载 + Pydantic 校验
- [ ] Integration tests: Pipeline 端到端流程（全部 mock 外部服务）

## 6. Migration & Rollback

无数据库迁移。纯文件存储方案，新增目录结构即可。
回滚：删除 `downloads/bilibili-comments/` 目录及新增代码模块。

## 7. Risks & Mitigations

| Risk                | Impact    | Mitigation                         |
|---------------------|-----------|------------------------------------|
| Bilibili API 反爬/封禁  | 采集中断      | 请求限速 ≥ 1s，带登录态，User-Agent 伪装       |
| Bilibili API 变更     | Client 失效 | 优先用第三方库（维护成本转移），集中封装在 client.py    |
| Cookie 过期           | 采集失败      | 日志告警 + 推送通知用户重新扫码登录                |
| 评论量过大超 LLM token 限制 | 分析失败      | 采样策略（高赞 + 最新 + 随机），max_comments 可配 |
| LLM API 不可用         | 无分析结果     | 日志记录 + 保留 pending 评论，下次窗口触发时重试     |
| 推送渠道 API 限流         | 推送延迟      | 指数退避重试（1s→2s→4s），最多 3 次            |
| 第三方 bilibili 库停更    | 登录/API 失效 | 自建 client.py 作为 fallback，库仅用于登录    |
| 多 Pipeline 并发写同一目标  | 数据冲突      | Pipeline 按 target_id 隔离目录，避免交叉写入   |
