# app 包：FastAPI 后端
# 依赖方向（技术方案 §3，不允许反向）：
#   api/ → services/ → rag/
#                   → models
# rag/ 不 import FastAPI，也不 import services/。
