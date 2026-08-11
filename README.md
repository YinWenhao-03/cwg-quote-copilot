# CWG Quote Copilot

一个可本地运行的企业询价与报价审批原型。项目使用完全模拟的数据，演示从客户邮件、RAG 检索和确定性定价，到经理审批、PDF 固化与审计追踪的完整流程。

## 快速开始

环境要求：macOS/Linux、Python 3.12+、Node.js 20+、`uv`、`pnpm` 与 Ollama。LLM 默认使用 Mock，不需要 API Key；Dense 检索使用本地 Ollama 模型。

```bash
make setup
ollama pull nomic-embed-text
make seed
make dev
```

打开 [http://localhost:3000](http://localhost:3000)。后端 API 文档位于 [http://localhost:8000/docs](http://localhost:8000/docs)。

| 身份 | 账号 | 密码 |
|---|---|---|
| 销售 | `sales@cwg.local` | `SalesDemo!2026` |
| 采购 | `procurement@cwg.local` | `ProcDemo!2026` |
| 经理 | `manager@cwg.local` | `ManagerDemo!2026` |

## 已实现能力

- 121 个 PDF、DOCX、XLSX、EML 模拟文件，109 个逻辑文档及完整版本关系。
- 模拟收件箱、询价结构化提取、缺字段暂停与人工补全。
- `jieba + BM25` 与 `nomic-embed-text + Qdrant` 真实语义召回并行，使用 RRF 融合和启发式重排。
- 知识库页面支持融合、Dense、BM25 三种模式对照，并显示两路排名与 RRF 分数。
- 文档密级、客户 ACL、批准状态和有效期在检索前过滤。
- 产品、当前成本、物流、汇率、客户政策和历史报价采用结构化表；精确价格不从向量文本读取。
- `Decimal` 定价、硬底价阻断、例外报价理由、经理审批与最终 PDF。
- 销售、采购、经理三类权限，敏感字段在模型调用前删除。
- 100 条固定 RAG 评测集、审计日志和 1k/10k/50k Chunk 压测器。

## 核心流程

```mermaid
flowchart LR
    A[模拟邮件] --> B[LLM 结构化提取]
    B --> C{字段完整且 SKU 唯一?}
    C -- 否 --> D[人工补全]
    D --> C
    C -- 是 --> E[RAG 产品与历史资料]
    E --> F[成本/物流/汇率 API]
    F --> G[Decimal 规则定价]
    G --> H{硬底价检查}
    H -- 低于硬底价 --> I[系统阻断]
    H -- 可提交 --> J[报价草稿]
    J --> K[经理审批]
    K -- 批准 --> L[固化版本并生成 PDF]
```

LLM 只处理自然语言提取和客户可见草稿；SKU、成本、物流、汇率、公式、权限和审批均由确定性代码或数据库完成。缺少客户、目的地、贸易条款、币种、SKU、数量或包装时，流程停在检查点。

## 定价规则

```text
landed_cost = 当前有效成本 + 包装 + 单位物流 + 税费
standard_minimum = landed_cost / (1 - 标准毛利率)
hard_floor = max(管理层底价, landed_cost / (1 - 硬毛利底线))
```

低于 `hard_floor` 时 API 直接返回 422；介于硬底价和标准最低价之间时，经理必须填写例外理由。历史报价只用于比较，不参与当前最低价计算。

## RAG 评测指标

- `Recall@K`：每个问题标注若干正确 Chunk，检查前 K 条结果找回了多少。例如 2 个正确 Chunk 在前 10 条都出现，`Recall@10 = 2/2 = 1`。
- `Hit@K`：前 K 条只要出现至少一个正确 Chunk 就记 1，适合精确 SKU 查询。
- `MRR`：第一个正确结果排名的倒数；排第 1 得 1，排第 4 得 0.25。
- `nDCG@K`：同时考虑相关程度和排序位置，产品主文档可比辅助质量文档拥有更高相关等级。
- `引用准确率`：返回证据是否同时具备真实 Chunk、文档、标题和版本。
- `过期资料率/越权暴露率`：结果中已失效或超出当前角色权限的比例，门槛均为 0。

运行评测：

```bash
make test
make benchmark
```

验收门槛为 `Recall@10 >= 0.90`、精确 SKU `Hit@5 >= 0.95`、越权暴露率 0、过期资料率 0，且所有定价测试通过。

## 配置真实模型

复制 `.env.example` 为 `.env`，配置任意 OpenAI 兼容接口：

```dotenv
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://your-endpoint.example/v1
LLM_API_KEY=replace-me
LLM_MODEL=your-model
```

定价和权限结果不受模型切换影响。安装 `make setup-full` 后，可设置 `EMBEDDING_PROVIDER=sentence_transformers`、`DOCUMENT_PARSER=docling`，使用 BGE 与 Docling；首次运行会下载模型。

当前本地融合检索配置：

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text:latest
EMBEDDING_QUERY_PREFIX=search_query:
EMBEDDING_DOCUMENT_PREFIX=search_document:
ANSWER_PROVIDER=ollama
ANSWER_MODEL=deepseek-r1:1.5b
```

知识问答使用融合检索取得权限内、有效版本的证据，再由本机 `deepseek-r1:1.5b`
生成分条答案。后端会校验每条结论的证据编号和新增数字；无法通过校验时退回原文抽取式答案。
原始文档片段只作为可展开的引用依据。价格、成本和底价问题不会交给模型回答，而是转入
结构化报价流程。

更换 Embedding 模型后执行 `make reindex`。该命令会重新生成 Dense 向量并同时重建 BM25 索引。

## 本地与生产适配

默认使用 SQLite 和 Qdrant 本地持久化。生产环境可设置：

```dotenv
DATABASE_URL=postgresql+psycopg://cwg:password@postgres:5432/cwg
QDRANT_URL=http://qdrant:6333
```

`docker-compose.yml` 提供 PostgreSQL 与 Qdrant 服务端。Alembic 配置位于 `backend/alembic.ini`。当前版本的收件箱只读取内置 EML、粘贴文本和上传附件，不连接或发送真实邮件。

## 目录

```text
backend/app/       FastAPI、LangGraph、检索、定价、权限、PDF
backend/tests/     单元与端到端安全测试
frontend/app/      Next.js 中文工作台
data/generated/    可重复生成的模拟企业文件
storage/           SQLite、Qdrant、本地对象和报价 PDF
scripts/dev.py     前后端统一启动器
```

所有客户、供应商、价格与品牌内容均为模拟数据，不代表任何真实企业信息。

## 云端演示

`Dockerfile` 和 `render.yaml` 可将完整应用部署到 Render。免费演示模式使用
Hugging Face Inference Providers：`DeepSeek-R1-Distill-Qwen-1.5B` 负责证据约束回答，
`BAAI/bge-small-zh-v1.5` 负责中文 Dense 检索。Render 中只需将具有
Inference Providers 权限的 Hugging Face Token 填入 `LLM_API_KEY`，不要把 Token 写入代码。

免费实例使用临时磁盘，休眠或重启后会从模拟资料自动重建 SQLite、BM25 和 Qdrant 索引；
因此上传的新文件不会永久保存。该限制不影响内置询价、报价、审批和知识问答演示。
