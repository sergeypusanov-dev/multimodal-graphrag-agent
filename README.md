# Multimodal Temporal GraphRAG Agent

Интеллектуальный мультимодальный ассистент с собственной базой знаний на основе **Temporal GraphRAG**. Принимает и анализирует текст, изображения, аудио и видео. Полностью работает локально через **Ollama** — без платных API-ключей.

## Архитектура

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  FastAPI     │────▶│  LangGraph   │────▶│  Ollama     │
│  :8100       │     │  StateGraph  │     │  LLM/Vision │
└──────┬──────┘     └──────┬───────┘     └─────────────┘
       │                   │
       │            ┌──────┴───────┐
       │            │              │
  ┌────▼────┐  ┌────▼────┐  ┌─────▼──────┐
  │ Qdrant  │  │PostgreSQL│  │   Redis    │
  │ Vectors │  │ GraphRAG │  │ Cache/Queue│
  └─────────┘  └──────────┘  └────────────┘
```

**LangGraph StateGraph** — 7 нод:
`ingest` → `router` → `retrieval` / `temporal` / `media_context` / `index` → `synthesize`

## Технологический стек

| Компонент | Технология |
|-----------|-----------|
| Оркестрация | LangGraph (StateGraph + PostgresSaver) |
| База знаний | Temporal GraphRAG (PostgreSQL + bi-temporal schema) |
| Векторный поиск | Qdrant |
| Эмбеддинги | Ollama / nomic-embed-text (768d) |
| LLM | Ollama / qwen2.5:14b, qwen2.5:7b |
| Vision | Ollama / llama3.2-vision |
| Транскрипция | faster-whisper (локально) |
| Фоновые задачи | Celery + Redis |
| API | FastAPI + Prometheus метрики |
| Межагентность | A2A Protocol v0.2 |
| Платформа | Windows 11 + WSL2 + Docker Desktop |

## Быстрый старт

### 1. Клонирование

```bash
git clone https://github.com/sergeypusanov-dev/multimodal-graphrag-agent.git
cd multimodal-graphrag-agent
```

### 2. Настройка

```bash
cp .env.example .env
# Отредактируйте .env — установите POSTGRES_PASSWORD
```

### 3. Запуск

```bash
# Автоматический запуск (определит GPU/CPU, скачает модели)
./start.sh

# Или вручную:
make up-cpu          # CPU-режим (без NVIDIA GPU)
make up              # GPU-режим (с NVIDIA GPU)
make pull-models     # Скачать Ollama-модели (~22GB)
```

### 4. Проверка

```bash
# Health check
curl http://localhost:8100/health

# Статистика базы знаний
curl http://localhost:8100/kb/stats

# Тестовый запрос
curl -X POST http://localhost:8100/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer a2a-secret-key-change-me" \
  -d '{"message": "Привет! Что ты умеешь?", "session_id": "test-1"}'
```

## API

### POST /chat
Текстовый чат с агентом.
```json
{"message": "Ваш вопрос", "session_id": "optional-session-id"}
```

### POST /chat/multimodal
Чат с загрузкой файлов (form-data).
```bash
curl -X POST http://localhost:8100/chat/multimodal \
  -H "Authorization: Bearer a2a-secret-key-change-me" \
  -F "message=Опиши что на изображении" \
  -F "files=@photo.jpg"
```

### GET /health
Статус системы и circuit breakers.

### GET /kb/stats
Статистика базы знаний (сущности, связи, чанки, файлы).

### GET /metrics
Prometheus-метрики (токены, latency, стоимость, размер графа).

### GET /.well-known/agent.json
A2A Agent Card для межагентного взаимодействия.

### POST /a2a/tasks/send
A2A Protocol — отправка задач от других агентов.

## Ollama-модели

| Модель | Назначение | Размер |
|--------|-----------|--------|
| `qwen2.5:14b` | Основная LLM | ~9 GB |
| `qwen2.5:7b` | Batch-обработка, роутинг | ~4.7 GB |
| `llama3.2-vision` | Анализ изображений и видео | ~7.8 GB |
| `nomic-embed-text` | Эмбеддинги документов | ~274 MB |

Модели скачиваются автоматически при `./start.sh` или вручную:
```bash
make pull-models
```

## Docker-сервисы

| Сервис | Порт | Описание |
|--------|------|----------|
| agent-api | 8100 | FastAPI + LangGraph агент |
| ollama | 11434 | Локальные LLM-модели |
| qdrant | 6333, 6334 | Векторная БД |
| postgres | 5432 | PostgreSQL + pgvector (GraphRAG) |
| redis | 6379 | Кэш + очередь задач |
| celery-worker | — | Обработка документов |
| celery-beat | — | Периодическая синхронизация |

## База знаний

Помещайте файлы в `~/data/knowledge` — они будут автоматически проиндексированы.

**Поддерживаемые форматы:**
- Текст: `.txt`, `.md`, `.rst`, `.html`, `.pdf`, `.docx`, `.csv`, `.json`
- Изображения: `.jpg`, `.png`, `.gif`, `.webp`, `.bmp`, `.svg`
- Аудио: `.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.aac`
- Видео: `.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`, `.m4v`

Синхронизация происходит автоматически каждые 2 часа (Celery Beat) и при изменении файлов (Watchdog). Ручной запуск:
```bash
make sync
```

## Makefile-команды

```bash
make up             # Запуск (GPU)
make up-cpu         # Запуск (CPU)
make down           # Остановка
make restart        # Перезапуск agent + celery
make logs           # Логи всех сервисов
make ollama-logs    # Логи Ollama
make shell          # Bash в контейнере агента
make validate       # Валидация конфигурации
make sync           # Ручная синхронизация базы знаний
make pull-models    # Скачать Ollama-модели
make ps             # Статус контейнеров
```

## Конфигурация

Вся конфигурация в `config.yaml`. Поддерживаемые провайдеры:

- **LLM:** Ollama, Anthropic, OpenAI, Gemini
- **Embeddings:** Ollama, Gemini, OpenAI, Cohere, Voyage, local (sentence-transformers)
- **Vector Store:** Qdrant, pgvector, Pinecone, Weaviate, Chroma, Milvus

Для переключения на облачные провайдеры отредактируйте `config.yaml` и добавьте API-ключи в `.env`.

## Структура проекта

```
multimodal-graphrag-agent/
├── agent/          # LangGraph StateGraph + tools
├── a2a/            # A2A Protocol (card, server, client)
├── api/            # FastAPI + Prometheus
├── cache/          # Семантический/embedding/graph кэш
├── embeddings/     # Мульти-провайдерный адаптер эмбеддингов
├── graph/          # GraphRAG: indexer, query, temporal, community
├── llm/            # Мульти-провайдерный LLM адаптер
├── media/          # Обработка текста/изображений/аудио/видео
├── security/       # Auth, rate limiting, circuit breakers
├── tasks/          # Celery + WSL2 file watcher
├── utils/          # WSL2 path utilities
├── vector_store/   # Мульти-провайдерный адаптер vector store
├── config.yaml     # Единый файл конфигурации
├── schema.sql      # Bi-temporal GraphRAG схема
├── docker-compose.yml
├── docker-compose.cpu.yml  # CPU-only override
├── Dockerfile
├── Makefile
└── start.sh        # Автоматический запуск с pull моделей
```

## Лицензия

MIT
