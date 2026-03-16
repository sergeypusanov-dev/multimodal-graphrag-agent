#!/bin/bash
set -euo pipefail

echo "╔══════════════════════════════════════════════════════╗"
echo "║   Multimodal Temporal GraphRAG Agent v1.0            ║"
echo "║   Platform: Windows + WSL2 + Docker Desktop          ║"
echo "║   Mode: Local (Ollama)                               ║"
echo "╚══════════════════════════════════════════════════════╝"

# Определяем compose-файлы (CPU или GPU)
COMPOSE_FILES="-f docker-compose.yml"
if ! command -v nvidia-smi &>/dev/null || ! nvidia-smi &>/dev/null; then
    echo "[!] NVIDIA GPU not detected — running in CPU-only mode"
    COMPOSE_FILES="-f docker-compose.yml -f docker-compose.cpu.yml"
fi

echo "[1/8] Checking WSL2 environment..."
WATCHES=$(cat /proc/sys/fs/inotify/max_user_watches 2>/dev/null || echo 0)
if [ "$WATCHES" -lt 524288 ]; then
    sudo sysctl -w fs.inotify.max_user_watches=2097152
    sudo sysctl -w fs.inotify.max_user_instances=8192
fi

echo "[2/8] Checking data locations..."
mkdir -p ~/data/knowledge

echo "[3/8] Starting infrastructure..."
docker compose $COMPOSE_FILES up -d postgres redis qdrant ollama
until docker compose exec -T postgres pg_isready -U agent -d agent_db &>/dev/null; do sleep 2; done
until docker compose exec -T redis redis-cli ping &>/dev/null; do sleep 1; done
echo "  DB services healthy, waiting for Ollama..."
until docker compose exec -T ollama curl -sf http://localhost:11434/api/tags &>/dev/null; do sleep 3; done
echo "  All services healthy"

echo "[4/8] Pulling Ollama models (skip if already present)..."
MODELS="${OLLAMA_MODELS:-qwen2.5:14b,qwen2.5:7b,llama3.2-vision,nomic-embed-text}"
IFS=',' read -ra MODEL_LIST <<< "$MODELS"
for model in "${MODEL_LIST[@]}"; do
    model=$(echo "$model" | xargs)  # trim whitespace
    echo "  Pulling $model..."
    docker compose exec -T ollama ollama pull "$model"
done
echo "  Models ready"

echo "[5/8] Validating configuration..."
docker compose $COMPOSE_FILES run --rm agent python validate_config.py

echo "[6/8] Initial knowledge base sync..."
docker compose $COMPOSE_FILES run --rm celery-worker \
    celery -A tasks.watcher call tasks.watcher.sync_knowledge_folder

echo "[7/8] Starting Celery workers..."
docker compose $COMPOSE_FILES up -d celery-worker celery-beat

echo "[8/8] Starting agent API..."
docker compose $COMPOSE_FILES up -d agent

echo ""
echo "✓ System started (local mode, no API keys needed)!"
echo "  Chat API:   http://localhost:8000/chat"
echo "  Multimodal: http://localhost:8000/chat/multimodal"
echo "  A2A Tasks:  http://localhost:8000/a2a/tasks/send"
echo "  Health:     http://localhost:8000/health"
echo "  KB Stats:   http://localhost:8000/kb/stats"
echo "  Ollama:     http://localhost:11434"
