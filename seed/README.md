# seed —— 测试与演示用内容

本目录存放用于系统测试、演示的内容素材，**全部在本项目内自包含**，
不引用外部目录的文件。

```
seed/
├── posts/     Markdown 文章，用批量导入脚本灌入
└── docs/      知识库上传用文件（Markdown / txt / PDF）
```

## 内容主题

围绕 **AI Agent 与 RAG 的工程实践**，覆盖：
向量检索与 BM25 混合、切块策略、增量索引、工具调用、ReAct 循环、
上下文压缩、Embedding 基础、语言模型演进。

这些主题与本项目自身的技术选型高度重合 —— 好处是：
用它们做检索测试时，**能直接判断召回结果对不对**，而不是对着一堆
无关文本猜测「这条命中算不算准」。

## 用法

### 导入文章

```bash
cd backend
conda activate blog
python -m app.services.import_service --dir ../seed/posts --dry-run   # 先预览
python -m app.services.import_service --dir ../seed/posts             # 实际导入
```

### 上传知识库文档

通过管理页 `/admin/docs` 上传 `seed/docs/` 下的文件，
目录路径按文件所在子目录填写（如 `八斗学院/week10-RAG`）。

## 关于 PDF

`docs/` 下的 PDF 由 `make_pdf.py` 用 PyMuPDF 生成，**内容与同名 Markdown 一致**。
这样可以对照验证：同一份内容，PDF 路径（按页解析、引用跳页码）与
Markdown 路径（按标题切块、引用跳锚点）是否都工作正常。

```bash
cd seed
python make_pdf.py
```

### 设置分类 / 标签 / 精选

导入脚本只负责正文与索引，归类信息由管理端设置。
`taxonomy.json` 记下了这套演示内容的归属（3 个分类、14 个标签、3 篇精选），
按它在管理页逐篇设置即可复现，也可以直接调接口批量套用。

### 「关于」页

关于页的正文来自一篇 slug 为 `about` 的保留文章（FR-VIEW-24），
不在 `posts/` 里 —— 它由管理端新建，内容是博主自己的介绍。
这个 slug 已在 `post_service.RESERVED_SLUGS` 中登记，
不会出现在文章归档、上下篇与相关推荐里。
