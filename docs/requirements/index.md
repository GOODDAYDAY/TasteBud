# TasteBud — Requirement Index

| # | ID      | Name             | Status | Created    | Updated    | Description                                                |
|---|---------|------------------|--------|------------|------------|------------------------------------------------------------|
| 1 | REQ-001 | core-value-chain | ✅ DONE | 2026-03-08 | 2026-03-08 | 核心价值链：Collect → Analyze → Score → Feedback → Learn，含三层筛选管道 |
| 2 | REQ-002 | bilibili         | ✅ DONE | 2026-03-08 | 2026-03-08 | Bilibili 评论采集 → AI 痛点分析 → 推送                               |
| 3 | REQ-003 | bilibili-search  | ✅ DONE | 2026-03-08 | 2026-03-08 | Bilibili 关键词搜索采集 + 移除 schedule 改为持续运行                      |
| 4 | REQ-004 | batch-analysis   | ✅ DONE | 2026-03-08 | 2026-03-08 | 跨视频汇总分析 + GitHub Copilot token 支持 + 批量处理                   |
| 5 | REQ-005 | rate-limit-429   | ✅ DONE | 2026-03-09 | 2026-03-09 | 遇到 429 限流时自动暂停请求一段时间再恢复                                    |
| 6 | REQ-006 | plugin-decouple  | ✅ DONE | 2026-03-09 | 2026-03-09 | 插件架构解耦：新增平台只需加插件目录，零修改核心代码                                 |
