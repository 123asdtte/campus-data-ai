FROM python:3.12-alpine

WORKDIR /app
COPY app.py ./
COPY data ./data
RUN mkdir -p /app/state

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"

CMD ["python", "-u", "app.py"]
