.PHONY: up up-cpu down restart logs shell validate sync ps wsl-check pull-models ollama-logs web

up: wsl-check
	@mkdir -p ~/data/knowledge
	docker compose up -d
	@echo "  Web UI:     http://localhost:3000"
	@echo "  Admin:      http://localhost:3000/admin.html"
	@echo "  Agent API:  http://localhost:8100"
	@echo "  Ollama:     http://localhost:11434"

up-cpu: wsl-check
	@mkdir -p ~/data/knowledge
	docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d
	@echo "  Started in CPU-only mode (no GPU)"
	@echo "  Web UI:  http://localhost:3000"
	@echo "  Admin:   http://localhost:3000/admin.html"

down:
	docker compose down

restart:
	docker compose restart agent celery-worker celery-beat

logs:
	docker compose logs -f --tail=100

ollama-logs:
	docker compose logs -f --tail=50 ollama

shell:
	docker compose exec agent bash

validate:
	docker compose exec agent python validate_config.py

sync:
	docker compose exec celery-worker celery -A tasks.watcher call tasks.watcher.sync_knowledge_folder

ps:
	docker compose ps

pull-models:
	@echo "Pulling Ollama models (this may take a while)..."
	docker compose exec ollama ollama pull qwen2.5:14b
	docker compose exec ollama ollama pull qwen2.5:7b
	docker compose exec ollama ollama pull llama3.2-vision
	docker compose exec ollama ollama pull nomic-embed-text
	@echo "All models pulled!"

wsl-check:
	@watches=$$(cat /proc/sys/fs/inotify/max_user_watches 2>/dev/null || echo 0); \
	if [ "$$watches" -lt 524288 ]; then \
	  echo "WARNING: inotify watches=$$watches — fix: sudo sysctl -w fs.inotify.max_user_watches=2097152"; fi
