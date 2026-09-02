FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/app/data/models
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir \
	https://github.com/Dao-AILab/flash-attention/releases/download/v2.7.4.post1/flash_attn-2.7.4.post1%2Bcu12torch2.5cxx11abiFALSE-cp311-cp311-linux_x86_64.whl
COPY app ./app
COPY tests ./tests
RUN mkdir -p /app/data/voices /app/data/references /app/data/generated /app/data/models
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
