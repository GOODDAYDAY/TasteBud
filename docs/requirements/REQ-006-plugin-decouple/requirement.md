# plugin-decouple — Requirement Document

| Field   | Value          |
|---------|----------------|
| ID      | REQ-006        |
| Status  | 🟡 IN PROGRESS |
| Created | 2026-03-09     |
| Updated | 2026-03-09     |

## 1. Background & Motivation

当前插件架构存在多处耦合：CollectorConfig 里硬编码了 bilibili 专属字段（cookie_path、search_order），config.py 解析器也写死了
bilibili 的解析逻辑，Comment.id 强制 int 不兼容其他平台，分析 prompt 只适用于 bilibili 场景。

目标：新增平台（如 YouTube、Twitter、小红书）只需新建 `plugin/<name>/` 目录，实现 BasePlugin 接口，加一个 YAML
配置文件，零修改核心代码即可自动集成。

## 2. Functional Requirements

- [ ] FR-1: CollectorConfig 只保留通用字段（type, target），平台特有配置统一放入 `plugin_config: dict`，由插件自行解析
- [ ] FR-2: 插件通过 `parse_collector_config(raw: dict)` 方法解析自身专属配置
- [ ] FR-3: config.py 解析器不再硬编码任何平台特有字段
- [ ] FR-4: Comment.id 改为 str 类型，兼容所有平台的 ID 格式
- [ ] FR-5: 插件可通过 `get_prompt_template()` 自定义分析 prompt
- [ ] FR-6: 现有 bilibili 插件功能不受影响（向后兼容）

## 3. Non-Functional Requirements

- 新增插件不需要修改 pipeline/、core/、analyzer/ 下任何文件
- YAML 配置格式保持直观易读

## 4. User Stories / Use Cases

作为开发者，我想新增一个 YouTube 插件，只需要：

1. 创建 `plugin/youtube/plugin.py` 实现 BasePlugin
2. 创建 `pipelines/youtube-channel.yaml` 配置文件
3. 运行，完成

## 5. Acceptance Criteria

- [ ] AC-1: CollectorConfig 中无任何 bilibili 专属字段
- [ ] AC-2: 新增一个 mock 插件不需要修改核心代码（可通过代码审查验证）
- [ ] AC-3: 现有 bilibili pipeline 正常运行
- [ ] AC-4: Comment.id 为 str 类型

## 6. Out of Scope

- 实际新增 YouTube/Twitter 等插件（只做架构准备）
- 前端界面改动
- 数据库 schema 改动

## 7. Open Questions

无
