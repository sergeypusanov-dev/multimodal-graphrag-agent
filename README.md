# Multimodal Temporal GraphRAG Agent

Локальная AI-платформа с оркестратором специализированных агентов, базой знаний GraphRAG и поддержкой MCP-инструментов. Работает полностью через **Ollama** — без платных API-ключей.

## Архитектура

```
┌─────────────┐     ┌──────────────────────────────────┐
│  Web UI     │     │  Admin Panel (6 вкладок)          │
│  Chat+Voice │     │  Overview│KB│Agent│MCP│Activity│Sys│
│  :3100      │     │  :3100/admin.html                 │
└──────┬──────┘     └──────────────┬────────────────────┘
       │         nginx reverse proxy
       ▼
┌──────────────────────────────────────────┐
│  FastAPI + LangGraph StateGraph          │
│  ┌────────────────────────────────────┐  │
│  │         Orchestrator               │  │
│  │  Analytics│Pricing│Stock│Content│Fin│  │
│  └────────────────────────────────────┘  │
└───┬──────────┬──────────┬────────────────┘
    ▼          ▼          ▼
┌────────┐ ┌──────┐ ┌──────────┐ ┌───────────┐
│ Ollama │ │Qdrant│ │PostgreSQL│ │MCP Servers│
│ 4 LLM  │ │vector│ │ GraphRAG │ │(WB 59tool)│
└────────┘ └──────┘ └──────────┘ └───────────┘
```

## Оркестратор — 5 специалистов

| Специалист | Tools | Область |
|-----------|-------|---------|
| WB Analytics | 6 | Воронки продаж, поисковые запросы, тренды |
| WB Pricing | 7 | Цены, скидки, карантин |
| WB Stock & Logistics | 28 | Склад, заказы FBS, поставки |
| WB Content | 12 | Карточки товаров, категории, теги |
| WB Finance | 6 | Баланс, реализация, документы |

Запросы автоматически маршрутизируются нужному специалисту по ключевым словам.

## Технологический стек

| Компонент | Технология |
|-----------|-----------|
| Оркестрация | LangGraph (StateGraph + PostgresSaver) |
| База знаний | Temporal GraphRAG (PostgreSQL + bi-temporal schema) |
| Векторный поиск | Qdrant |
| Эмбеддинги | snowflake-arctic-embed2 (1024d, мультиязычные) |
| LLM | Ollama / qwen2.5:14b + tool calling |
| Vision | Ollama / llama3.2-vision |
| Транскрипция | faster-whisper (локально) |
| MCP Tools | SSE транспорт, auto-discover |
| Фоновые задачи | Celery + Redis |
| API | FastAPI + Prometheus метрики |
| Межагентность | A2A Protocol v0.2 |
| Web UI | nginx + vanilla HTML/JS |

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
# Автоматический (определит GPU/CPU, скачает модели)
./start.sh

# Или вручную:
make up-cpu          # CPU-режим
make pull-models     # Скачать модели (~22GB)
```

### 4. Открыть в браузере

- **Chat UI:** http://localhost:3100
- **Admin Panel:** http://localhost:3100/admin.html

При первом входе введите API-ключ из `.env` (`A2A_API_KEY`).

## MCP Tools

Подключение внешних инструментов через Model Context Protocol:

```
"Какой баланс на WB?" → Orchestrator → WB Finance → wb_get_balance
→ {"currency":"RUB","current":70424.19} → "Ваш баланс 70 424.19 руб"
```

Добавление MCP-сервера: Admin Panel → MCP Tools → Add & Discover.

## Web UI

### Chat (http://localhost:3100)
- Текстовый чат с RAG из базы знаний
- Голосовой ввод (Web Speech API)
- Загрузка файлов (изображения, аудио, видео, документы)
- История сессий с удалением

### Admin Panel (http://localhost:3100/admin.html)

| Вкладка | Функции |
|---------|---------|
| Overview | KB статистика, health, circuit breakers, Prometheus метрики |
| Knowledge Base | Drag-and-drop загрузка, sync, indexed files, entity browser |
| Agent | Specialist cards, routing tester, prompt preview, system prompt, behavior rules |
| MCP Tools | Добавление серверов, auto-discover, per-tool enable/disable |
| Activity | Timeline взаимодействий: route → tool_call → answer |
| System | API key, конфигурация |

## API

| Метод | Путь | Описание |
|-------|------|----------|
| POST | /chat | Текстовый чат с RAG |
| POST | /chat/multimodal | Чат с файлами |
| GET | /health | Статус + circuit breakers |
| GET | /kb/stats | Статистика базы знаний |
| GET | /kb/files | Список индексированных файлов |
| POST | /kb/upload | Загрузка документов |
| POST | /kb/sync | Ручная синхронизация |
| GET | /kb/entities | Поиск сущностей |
| GET | /metrics | Prometheus-метрики |
| GET | /.well-known/agent.json | A2A Agent Card |
| POST | /a2a/tasks/send | A2A отправка задач |
| GET | /admin/specialists | Список специалистов |
| POST | /admin/specialists/test | Тест маршрутизации |
| GET | /admin/activity | Лог активности |
| GET/PUT | /admin/agent/settings | Настройки агента |
| CRUD | /admin/agent/rules | Правила поведения |
| CRUD | /admin/mcp/servers | MCP-серверы |

## Docker-сервисы (8)

| Сервис | Порт | Описание |
|--------|------|----------|
| agent-web | 3100 | nginx + Web UI |
| agent-api | 8100 | FastAPI + LangGraph |
| ollama | 11434 | Локальные LLM-модели |
| qdrant | 6333 | Векторная БД |
| postgres | 5432 | PostgreSQL + pgvector |
| redis | 6379 | Кэш + очередь задач |
| celery-worker | — | Обработка документов |
| celery-beat | — | Периодическая синхронизация |

## Ollama-модели

| Модель | Назначение | Размер |
|--------|-----------|--------|
| qwen2.5:14b | Основная LLM + tool calling | ~9 GB |
| qwen2.5:7b | Batch-обработка, роутинг | ~4.7 GB |
| llama3.2-vision | Анализ изображений и видео | ~7.8 GB |
| snowflake-arctic-embed2 | Мультиязычные эмбеддинги (1024d) | ~670 MB |

## Makefile-команды

```bash
make up / make up-cpu    # Запуск (GPU / CPU)
make down                # Остановка
make pull-models         # Скачать модели
make sync                # Синхронизация KB
make logs                # Логи всех сервисов
make ps                  # Статус контейнеров
make validate            # Проверка конфигурации
make restart             # Перезапуск агента
make shell               # Bash в контейнере
```

## Структура проекта

```
multimodal-graphrag-agent/
├── agent/              # LangGraph StateGraph + tools + orchestrator
├── a2a/                # A2A Protocol (card, server, client)
├── api/                # FastAPI + Prometheus + admin endpoints
├── cache/              # Семантический/embedding/graph кэш
├── embeddings/         # Мульти-провайдерный адаптер эмбеддингов
├── graph/              # GraphRAG: indexer, query, temporal, community
├── llm/                # Мульти-провайдерный LLM адаптер
├── mcp/                # MCP client (SSE transport, tool execution)
├── media/              # Обработка текста/изображений/аудио/видео
├── security/           # Auth, rate limiting, circuit breakers
├── tasks/              # Celery + WSL2 file watcher
├── utils/              # WSL2 path utilities
├── vector_store/       # Мульти-провайдерный vector store адаптер
├── web/                # nginx + HTML/JS (chat + admin panel)
├── docs/               # USER_GUIDE.md
├── config.yaml         # Конфигурация
├── schema.sql          # DB schema (GraphRAG + activity_log + MCP + rules)
├── docker-compose.yml
└── start.sh
```

## Документация

Подробное руководство: **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)**

## Лицензия

MIT
