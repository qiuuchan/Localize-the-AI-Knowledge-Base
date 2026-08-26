# tests/eval · RAG 检索回归评测(黄金问答集)

> 2026-07-17 新增(G3)。对标 RAGAS / RAGFlow 的评测思路,轻量本地化:**只评测检索质量,不调 LLM**。

## 为什么

`tests/test_*.ps1` 是 mock 静态断言(证明"形式合规"),`tests/unit/` 是模块单测(证明"函数正确"),
但都不能回答:**"我的知识库真的能被问题召回吗?"** —— 黄金问答集补这一层。

## 怎么用

```bash
# 1. 准备数据集:复制模板,按实际知识库内容填写(一行为一条用例)
cp tests/eval/golden-qa.example.jsonl tests/eval/golden-qa.jsonl

# 2. 启动后端 + Qdrant(start.bat 或 scripts/start-backend.ps1)

# 3. 跑评测
backend/.venv/Scripts/python tests/eval/run_eval.py
```

- 前提:后端已启动、知识库已入库
- 成本:每问仅 1 次 embedding 调用,无 LLM 费用
- 退出码:0 全过;1 有失败;2 后端不可达

## 数据集格式(jsonl)

```json
{"question": "招牌菜有哪些?", "expect_source": "menu.md", "expect_keywords": ["招牌"]}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `question` | ✅ | 用户问题 |
| `expect_source` | ✅ | 期望召回的文档名(子串匹配) |
| `expect_keywords` | 可选 | 期望出现在召回文本中的关键词,全部命中才算过 |

## v1.2 扩展字段

v1.2 黄金集覆盖 `xlsx`、`short`、`long`、`year` 四类检索问题,每类至少 10 条。未填写 `category` 的旧用例仍可运行,并归入 `uncategorized`。

| 字段 | 必填 | 说明 |
|---|---|---|
| `category` | 可选 | 用例分类:`xlsx`、`short`、`long` 或 `year` |
| `expect_year` | 可选 | 只在命中 `expect_source` 的 hit 中检查 `year_mentions` 是否包含该年份 |
| `expect_chunk_type` | 可选 | 只在命中 `expect_source` 的 hit 中检查 `chunk_type`,如 `xlsx_row_group` |
| `max_retrieval_ms` | 可选 | 单条检索耗时上限(毫秒);超限时该用例失败 |

完整评测前先执行一次 warm-up 请求,触发 cross-encoder 加载,避免首次模型加载 RTT 被计入 p95:

```bash
curl "http://127.0.0.1:8000/api/debug/retrieval?question=warm-up&top_k=5"
backend/.venv/Scripts/python tests/eval/run_eval.py --dataset tests/eval/golden-qa.jsonl --top-k 5
```

`latency_ms` 只统计 `category=long` 的用例,输出实际样本数 `count` 以及 `p50`、`p95`、`max`;长问题检索阶段目标为 warm-up 后 `p95 <= 3000ms`。样本不足时应报告实际 `count`,不能将不稳定的 p95 视为达标结论。

## 建议

- 黄金集至少 **40 条**,四类各至少 **10 条**;每次**大改动后 + 版本发布前**跑一遍
- `golden-qa.jsonl` 建议入 git(它是测试资产);`.example` 是模板
- 用例失败时,先用 `GET /api/debug/retrieval?q=...` 看全链路定位是哪一环丢了召回
