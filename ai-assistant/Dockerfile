# POC 运行镜像：复用 import-api 镜像的 Python 依赖（fastapi/uvicorn/psycopg/pydantic），
# 避免在无外网环境重新安装依赖。升级依赖时需同步 import-api/requirements.txt。
FROM campus-import-api:0.1.0

# 以非 root 用户运行（基础镜像已创建 appuser）
COPY --chown=appuser:appuser app /app/ai_assistant

USER appuser
EXPOSE 8100

CMD ["python", "-m", "uvicorn", "ai_assistant.main:app", "--host", "0.0.0.0", "--port", "8100", "--no-access-log"]
