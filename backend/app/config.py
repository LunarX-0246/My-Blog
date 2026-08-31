"""全局配置（技术方案 §2.2 / §9）。

职责：
- 严格按 `.env.example` 的键名读取环境变量，代码里不另起名字。
- 把所有可调参数集中在此，业务代码不硬编码阈值 / 批量大小 / top-k / 模型名。

为什么用 pydantic-settings：
- 自动把 env 键（如 ``DEEPSEEK_API_KEY``）映射到 snake_case 字段，且带类型校验。
- 显式指定 ``env_file`` 指向项目根目录的 ``.env``，避免依赖启动时的 cwd。

容易踩坑：``.env`` 在仓库根目录，而本机是 ``cd backend`` 后启动 uvicorn，
若用默认的 ``env_file=".env"`` 会找不到（cwd 在 backend/）。因此这里用
``__file__`` 上溯到根目录，与 cwd 无关。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 仓库根目录：backend/app/config.py → 上溯两级。
#   parents[0] = backend/app
#   parents[1] = backend
#   parents[2] = <repo root>（含 .env 与五份文档）
ROOT_DIR = Path(__file__).resolve().parents[2]
# backend 目录：本地运行时的数据根（backend/data/，对应 .gitignore）
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """所有环境变量配置的单一入口。字段名与 .env.example 的键一一对应。"""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # 容器内可能注入额外环境变量（如 PATH），忽略即可
    )

    # ── 数据库 ────────────────────────────────────────────
    # 本机开发端口 5433（5432 被本机 PG18 占用），容器/生产仍是 5432。
    database_url: str = "postgresql+psycopg://blog:dev@127.0.0.1:5433/blog"

    # ── 认证（单一博主账号，系统内不提供注册）─────────────
    admin_username: str = ""
    admin_password_hash: str = ""
    session_secret: str = ""
    session_max_age: int = 604800          # 登录有效期（秒），默认 7 天
    login_max_attempts: int = 5            # 登录失败锁定次数
    login_lockout_seconds: int = 900       # 锁定时长（秒），默认 15 分钟

    # ── 大语言模型（DeepSeek）─────────────────────────────
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    llm_fallback_model: str = ""           # 主模型失败时的降级目标，空则不降级

    # ── 文本向量化（千问 text-embedding）──────────────────
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_model: str = "text-embedding-v3"
    embedding_dim: int = 1024              # 必须与建索引时一致，启动自检校验（FR-IDX-10）

    # ── 向量存储后端 ──────────────────────────────────────
    vector_backend: str = "pgvector"       # pgvector=生产；numpy=对比实验

    # ── RAG 参数 ─────────────────────────────────────────
    chunk_max_chars: int = 800             # 单块最大字符数，超出按段落二次切分
    embed_batch_size: int = 20             # 向量化批量大小
    retrieve_top_k: int = 10               # 每路检索的召回数量
    context_top_k: int = 5                 # 最终送入 Prompt 的块数
    rrf_k: int = 60                        # RRF 融合常数
    memory_keep_full_turns: int = 2        # 多轮对话中完整保留的最近轮数

    # ── 限流与成本控制（FR-ASK-19 ~ 22）──────────────────
    ask_rate_limit_per_hour: int = 10      # 单 IP 每小时次数
    ask_max_question_chars: int = 1000     # 单次提问长度上限
    ask_daily_total_limit: int = 200       # 全站每日调用总量熔断

    # ── 文件存储 ─────────────────────────────────────────
    data_dir: str = "./data"               # 运行时数据根，其下 uploads/ images/ vectors/
    upload_max_mb: int = 50                # 单文件大小上限

    # ── 服务地址 ─────────────────────────────────────────
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # 供 Next.js SSR 调用后端使用（本机 http://127.0.0.1:8000，容器内 http://api:8000）
    internal_api_base: str = "http://127.0.0.1:8000"

    # ── 派生路径 ─────────────────────────────────────────

    @property
    def data_dir_path(self) -> Path:
        """数据根目录的绝对路径。

        相对路径（如 ``./data``）相对于 backend/ 解析，而非 cwd ——
        这样无论从哪里启动 uvicorn，落点都在 ``backend/data/``（与 .gitignore 一致）。
        生产容器里 DATA_DIR 是绝对路径 ``/app/data``，原样使用。
        """
        p = Path(self.data_dir)
        return p if p.is_absolute() else (BACKEND_DIR / p).resolve()

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir_path / "uploads"

    @property
    def images_dir(self) -> Path:
        return self.data_dir_path / "images"


@lru_cache
def get_settings() -> Settings:
    """全局唯一的配置实例（进程内缓存，避免重复读取 .env）。"""
    return Settings()


settings = get_settings()
