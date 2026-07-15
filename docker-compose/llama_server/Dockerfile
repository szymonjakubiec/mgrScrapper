#FROM ubuntu:latest
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04
LABEL authors="Szymon"

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install llama-cpp-python[server] \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121

ENTRYPOINT ["python3", "-m", "llama_cpp.server"]