# 后端镜像（FastAPI + RAG）
#
# 基础镜像用 slim：本项目依赖全部有 manylinux wheel（PyMuPDF 自带二进制、
# psycopg[binary] 自带 libpq、numpy/bcrypt 有预编译包），无需 apt 装编译工具，
# 镜像可以做得很小。若将来加了需要编译的依赖，再补 build-essential。

FROM python:3.12-slim

# 不写 .pyc、日志不缓冲（容器里日志要能实时看到）
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 依赖单独一层：requirements.txt 没变时这一层走缓存，改代码不必重装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码与迁移脚本
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

# 运行时数据目录（uploads / images / vectors）。
# 实际内容由 docker-compose 挂载宿主机的 ./data 进来，这里只保证目录存在。
RUN mkdir -p /app/data

# 非 root 运行
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# ★ 启动前先执行数据库迁移，再拉起服务。
#   单实例部署，不存在多副本并发迁移的竞争问题；迁移失败会直接退出，
#   不会出现「服务起来了但表结构是旧的」这种更难查的状态。
#
# ★★ --workers 1 是硬约束，不要改大。
#   BM25 索引缓存（retriever / search_service）与 numpy 向量后端都是**进程内**状态，
#   多 worker 会各持一份：一是内存翻倍（目标机器只有 2 GiB），
#   二是内容变更时 invalidate 只对当前进程生效，其余 worker 仍返回过期结果 —— 这是正确性问题。
#   并发能力靠 async 处理 IO 等待（模型 API 调用）即可，不靠多进程。
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
