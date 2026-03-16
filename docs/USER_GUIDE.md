# Руководство пользователя — Multimodal Temporal GraphRAG Agent

## Содержание

1. [Системные требования](#1-системные-требования)
2. [Развертывание](#2-развертывание)
3. [Управление системой](#3-управление-системой)
4. [База знаний](#4-база-знаний)
5. [Работа с агентом](#5-работа-с-агентом)
6. [Мониторинг](#6-мониторинг)
7. [Настройка LLM и эмбеддингов](#7-настройка-llm-и-эмбеддингов)
8. [Настройка безопасности](#8-настройка-безопасности)
9. [Настройка кэширования](#9-настройка-кэширования)
10. [A2A: межагентное взаимодействие](#10-a2a-межагентное-взаимодействие)
11. [Резервное копирование и восстановление](#11-резервное-копирование-и-восстановление)
12. [Устранение неполадок](#12-устранение-неполадок)

---

## 1. Системные требования

### Минимальные

| Параметр | Значение |
|----------|---------|
| ОС | Windows 10/11 + WSL2 или Linux |
| RAM | 16 GB |
| Диск | 50 GB свободного места |
| Docker | Docker Desktop 4.x или Docker Engine 24+ |

### Рекомендуемые

| Параметр | Значение |
|----------|---------|
| RAM | 32 GB |
| Диск | 100 GB (SSD) |
| GPU | NVIDIA с 8+ GB VRAM (для ускорения LLM) |
| CPU | 8+ ядер |

### Требования к диску для моделей Ollama

| Модель | Размер | Назначение |
|--------|--------|-----------|
| qwen2.5:14b | ~9 GB | Основная LLM |
| qwen2.5:7b | ~4.7 GB | Быстрая обработка, роутинг |
| llama3.2-vision | ~7.8 GB | Анализ изображений |
| nomic-embed-text | ~274 MB | Эмбеддинги документов |
| **Итого** | **~22 GB** | |

---

## 2. Развертывание

### 2.1. Клонирование и настройка

```bash
# Клонирование
git clone https://github.com/sergeypusanov-dev/multimodal-graphrag-agent.git
cd multimodal-graphrag-agent

# Создание файла конфигурации окружения
cp .env.example .env
```

Отредактируйте `.env`:

```bash
# Обязательно: установите пароль PostgreSQL
POSTGRES_PASSWORD=ваш_надежный_пароль

# Обязательно: установите ключ для API-авторизации
A2A_API_KEY=ваш_секретный_ключ

# Опционально: если есть облачные API-ключи
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-proj-...
```

### 2.2. Автоматический запуск

```bash
./start.sh
```

Скрипт автоматически:
1. Проверит настройки WSL2 (inotify watches)
2. Создаст папку для базы знаний
3. Запустит инфраструктуру (PostgreSQL, Redis, Qdrant, Ollama)
4. Дождётся healthcheck всех сервисов
5. Скачает модели Ollama (~22 GB при первом запуске)
6. Провалидирует конфигурацию
7. Запустит начальную синхронизацию базы знаний
8. Запустит Celery workers и API агента

### 2.3. Ручной запуск

```bash
# С NVIDIA GPU
make up

# Без GPU (CPU-only)
make up-cpu

# Скачивание моделей (при первом запуске)
make pull-models
```

### 2.4. Проверка развертывания

```bash
# Статус всех сервисов
make ps

# Health check
curl http://localhost:8100/health
# Ожидаемый ответ: {"status":"ok","circuits":{"llm":"closed","qdrant":"closed"}}

# Валидация конфигурации
make validate
```

### 2.5. Настройка WSL2 (только для Windows)

Для оптимальной работы file watcher добавьте в `%USERPROFILE%\.wslconfig`:

```ini
[wsl2]
memory=16GB
processors=8
swap=8GB
kernelCommandLine=sysctl.fs.inotify.max_user_watches=2097152
```

После изменения перезапустите WSL: `wsl --shutdown` из PowerShell.

---

## 3. Управление системой

### 3.1. Основные команды

| Команда | Описание |
|---------|----------|
| `make up` | Запуск всех сервисов (GPU) |
| `make up-cpu` | Запуск без GPU |
| `make down` | Полная остановка |
| `make restart` | Перезапуск агента и Celery |
| `make ps` | Статус контейнеров |
| `make logs` | Логи всех сервисов (follow) |
| `make ollama-logs` | Логи Ollama |
| `make shell` | Bash-сессия в контейнере агента |
| `make validate` | Проверка конфигурации |
| `make sync` | Ручная синхронизация базы знаний |
| `make pull-models` | Скачивание/обновление моделей |

### 3.2. Просмотр логов конкретного сервиса

```bash
docker compose logs -f agent         # API агента
docker compose logs -f celery-worker # Индексация документов
docker compose logs -f celery-beat   # Планировщик задач
docker compose logs -f ollama        # Ollama (LLM)
docker compose logs -f postgres      # PostgreSQL
docker compose logs -f qdrant        # Векторная БД
```

### 3.3. Обновление системы

```bash
git pull
make down
make up-cpu   # или make up для GPU
```

При обновлении модели данных (schema.sql) может потребоваться пересоздание БД:

```bash
make down
docker volume rm multimodal-graphrag-agent_pg_data
make up-cpu
```

---

## 4. База знаний

### 4.1. Добавление документов

Скопируйте файлы в Docker-volume через контейнер:

```bash
# Один файл
docker cp /путь/к/файлу.pdf agent-api:/data/knowledge/

# Папка с файлами
docker cp /путь/к/папке/. agent-api:/data/knowledge/

# Проверка
docker exec agent-api ls /data/knowledge/
```

### 4.2. Поддерживаемые форматы

| Тип | Форматы | Обработка |
|-----|---------|-----------|
| Текст | `.txt`, `.md`, `.rst`, `.html`, `.pdf`, `.docx`, `.csv`, `.json` | Извлечение текста, чанкинг, NER |
| Изображения | `.jpg`, `.png`, `.gif`, `.webp`, `.bmp`, `.svg` | Описание через vision LLM |
| Аудио | `.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.aac` | Транскрипция (faster-whisper) |
| Видео | `.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`, `.m4v` | Аудио + покадровый анализ |

Максимальный размер файла: **500 MB** (настраивается в `config.yaml`).

### 4.3. Запуск индексации

```bash
# Автоматическая: каждые 2 часа (Celery Beat)

# Ручная синхронизация
make sync

# Также срабатывает при изменении/добавлении файлов (Watchdog)
```

### 4.4. Проверка статуса индексации

```bash
# Общая статистика
curl -s http://localhost:8100/kb/stats \
  -H "Authorization: Bearer ваш_ключ"

# Ответ:
# {"entities":25,"relationships":21,"chunks":4,"indexed_files":1}
```

Через SQL (для детальной информации):

```bash
docker exec postgres psql -U agent -d agent_db -c \
  "SELECT file_path, status, entity_count, chunk_count, error_msg FROM kg_file_index;"
```

### 4.5. Пайплайн индексации

Для каждого файла система выполняет:

```
Файл → Обработка медиа → Чанкинг → LLM-извлечение сущностей →
→ Upsert в PostgreSQL (граф) → Upsert в Qdrant (векторы)
```

1. **Обработка медиа** — извлечение текста из PDF/DOCX, описание изображений, транскрипция аудио/видео
2. **Чанкинг** — разбиение текста на фрагменты (600 символов, overlap 150)
3. **Извлечение сущностей** — LLM находит entities, relationships, events
4. **Граф знаний** — сохранение в PostgreSQL (bi-temporal schema)
5. **Векторный поиск** — эмбеддинги чанков и сущностей в Qdrant

### 4.6. Настройка параметров индексации

В `config.yaml`:

```yaml
knowledge_base:
  chunk_size: 600         # Размер чанка (символов)
  chunk_overlap: 150      # Перекрытие между чанками
  max_file_size_mb: 500   # Максимальный размер файла
  sync_schedule: "0 */2 * * *"  # Расписание синхронизации (cron)
  community_detection: "leiden"  # Алгоритм: leiden или louvain
  graph_hop_depth: 2      # Глубина обхода графа при поиске
```

### 4.7. Удаление данных из базы знаний

```bash
# Удалить всё
docker exec postgres psql -U agent -d agent_db -c "
  DELETE FROM kg_file_index;
  DELETE FROM kg_events;
  DELETE FROM kg_chunks;
  DELETE FROM kg_relationships;
  DELETE FROM kg_entity_versions;
  DELETE FROM kg_entities;
  DELETE FROM kg_communities;
"

# Удалить конкретный файл
docker exec postgres psql -U agent -d agent_db -c \
  "DELETE FROM kg_file_index WHERE file_path='/data/knowledge/файл.pdf';"
# После этого: make sync — файл будет переиндексирован
```

---

## 5. Работа с агентом

### 5.1. Текстовый чат

```bash
curl -X POST http://localhost:8100/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ваш_ключ" \
  -d '{"message": "Ваш вопрос", "session_id": "user-123"}'
```

**Параметры:**
- `message` (обязательный) — текст запроса
- `session_id` (опциональный) — ID сессии для сохранения контекста беседы

**Ответ:**
```json
{
  "answer": "Ответ агента с [source: файл.pdf]",
  "session_id": "user-123",
  "latency_ms": 3140
}
```

### 5.2. Мультимодальный чат

```bash
# Отправка изображения
curl -X POST http://localhost:8100/chat/multimodal \
  -H "Authorization: Bearer ваш_ключ" \
  -F "message=Что изображено на фото?" \
  -F "files=@photo.jpg"

# Несколько файлов
curl -X POST http://localhost:8100/chat/multimodal \
  -H "Authorization: Bearer ваш_ключ" \
  -F "message=Сравни эти документы" \
  -F "files=@doc1.pdf" \
  -F "files=@doc2.pdf"
```

### 5.3. Типы запросов

Агент автоматически определяет тип запроса и выбирает стратегию:

| Тип | Пример | Стратегия |
|-----|--------|-----------|
| Q&A | "Кто основал TechCorp?" | Локальный поиск по графу + чанки |
| Research | "Расскажи обо всех партнёрствах" | Глобальный контекст (community summaries) |
| Temporal | "Что изменилось в 2023 году?" | Срез графа на дату |
| Compare | "Сравни 2021 и 2023" | Diff двух срезов графа |
| Index | "Проиндексируй файл X" | Постановка в очередь Celery |

### 5.4. Работа с сессиями

Сессии сохраняют контекст беседы в PostgreSQL:

```bash
# Первое сообщение
curl -X POST http://localhost:8100/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ваш_ключ" \
  -d '{"message": "Расскажи о TechCorp", "session_id": "session-1"}'

# Уточняющий вопрос (тот же session_id)
curl -X POST http://localhost:8100/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ваш_ключ" \
  -d '{"message": "А кто там CTO?", "session_id": "session-1"}'
```

---

## 6. Мониторинг

### 6.1. Health check

```bash
curl http://localhost:8100/health
```

Ответ включает состояние circuit breakers:
```json
{
  "status": "ok",
  "circuits": {
    "llm": "closed",       // closed=OK, open=недоступен, half_open=восстанавливается
    "qdrant": "closed"
  }
}
```

### 6.2. Prometheus-метрики

Доступны по адресу: `http://localhost:9190/metrics`

| Метрика | Описание |
|---------|----------|
| `llm_tokens_total` | Количество потреблённых токенов (по провайдерам) |
| `llm_latency_ms` | Задержка LLM-вызовов |
| `llm_cost_usd_total` | Оценочная стоимость (для облачных провайдеров) |
| `kg_entities_total` | Количество сущностей в графе |
| `kg_relationships_total` | Количество связей |
| `agent_tasks_total` | Количество выполненных задач (по intent и status) |

### 6.3. Интеграция с Grafana

Для подключения Grafana укажите data source:
- **Type:** Prometheus
- **URL:** `http://agent-api:9090` (из Docker-сети) или `http://localhost:9190` (с хоста)

### 6.4. Статистика базы знаний

```bash
curl -s http://localhost:8100/kb/stats -H "Authorization: Bearer ваш_ключ"
```

```json
{
  "entities": 25,          // Сущности (люди, организации, места...)
  "relationships": 21,     // Связи между сущностями
  "chunks": 4,             // Фрагменты документов
  "indexed_files": 1       // Проиндексированных файлов
}
```

### 6.5. Мониторинг Celery

```bash
# Логи обработки
docker compose logs -f celery-worker

# Статус очередей
docker exec celery-worker celery -A tasks.watcher inspect active
docker exec celery-worker celery -A tasks.watcher inspect reserved
```

### 6.6. Мониторинг Ollama

```bash
# Загруженные модели
docker exec ollama ollama list

# Модели в памяти (активные)
docker exec ollama ollama ps

# Использование ресурсов
docker stats ollama
```

---

## 7. Настройка LLM и эмбеддингов

Все настройки в `config.yaml`. После изменений — перезапуск: `make restart`.

### 7.1. Смена модели Ollama

```yaml
llm:
  main:
    provider: "ollama"
    model: "llama3.1:70b"          # Более мощная модель
    base_url: "http://ollama:11434/v1"
```

Не забудьте скачать модель:
```bash
docker exec ollama ollama pull llama3.1:70b
```

### 7.2. Переключение на облачного провайдера

Пример: Anthropic Claude для основной LLM:

```yaml
llm:
  main:
    provider: "anthropic"
    model: "claude-sonnet-4-5"
    api_key_env: "ANTHROPIC_API_KEY"
    max_tokens: 4096
    temperature: 0.1
```

Добавьте ключ в `.env`:
```
ANTHROPIC_API_KEY=sk-ant-api03-...
```

### 7.3. Гибридная конфигурация

Можно использовать разные провайдеры для разных задач:

```yaml
llm:
  main:
    provider: "anthropic"           # Облачный для ответов
    model: "claude-sonnet-4-5"
  batch:
    provider: "ollama"              # Локальный для извлечения сущностей
    model: "qwen2.5:7b"
  vision:
    provider: "ollama"              # Локальный для изображений
    model: "llama3.2-vision"
```

### 7.4. Настройка эмбеддингов

```yaml
embeddings:
  provider: "ollama"                # Сменить на "openai", "gemini" и т.д.
  ollama:
    model: "nomic-embed-text"
    dimensions: 768
```

> **Внимание:** При смене модели эмбеддингов необходимо переиндексировать всю базу знаний и пересоздать коллекцию Qdrant.

### 7.5. Настройка транскрипции аудио

```yaml
media_processing:
  transcription_provider: "local"   # "local" или "openai"
  whisper_model: "base"             # tiny|base|small|medium|large-v3
  whisper_device: "cpu"             # cpu|cuda
```

Модели whisper (размер / качество):
- `tiny` — 75 MB, быстро, базовое качество
- `base` — 140 MB, хороший баланс
- `small` — 460 MB, хорошее качество
- `medium` — 1.5 GB, высокое качество
- `large-v3` — 3 GB, максимальное качество

---

## 8. Настройка безопасности

### 8.1. API-авторизация

Все запросы требуют заголовок `Authorization: Bearer ваш_ключ`.

Ключ задаётся в `.env`:
```
A2A_API_KEY=ваш_секретный_ключ
```

Отключение авторизации (не рекомендуется):
```yaml
a2a:
  auth:
    enabled: false
```

### 8.2. Rate limiting

```yaml
security:
  rate_limit:
    enabled: true
    requests_per_minute: 60     # Лимит запросов в минуту
    burst: 20                   # Допустимый burst
```

### 8.3. Circuit breaker

Защита от каскадных сбоев при недоступности LLM или Qdrant:

```yaml
security:
  circuit_breaker:
    enabled: true
    failure_threshold: 5          # Количество ошибок для срабатывания
    recovery_timeout_sec: 60      # Время до повторной попытки
```

Состояния:
- `closed` — работает нормально
- `open` — сервис недоступен, запросы отклоняются
- `half_open` — пробная попытка восстановления

### 8.4. Защита от prompt injection

```yaml
security:
  input_sanitization:
    max_text_length: 50000        # Максимальная длина запроса
    strip_html: true              # Удаление HTML-тегов
```

Система автоматически логирует подозрительные паттерны.

---

## 9. Настройка кэширования

### 9.1. Семантический кэш

Кэширует ответы на похожие вопросы:

```yaml
cache:
  semantic_cache:
    enabled: true
    similarity_threshold: 0.95    # Порог схожести (0.0-1.0)
    ttl_sec: 3600                 # Время жизни (1 час)
```

Повышение `similarity_threshold` (например, 0.98) — меньше кэш-хитов, но точнее.
Понижение (например, 0.90) — больше кэш-хитов, но возможны неточные ответы.

### 9.2. Кэш эмбеддингов

Избегает повторного вычисления эмбеддингов для одинаковых текстов:

```yaml
cache:
  embedding_cache:
    enabled: true
    ttl_sec: 86400                # 24 часа
```

### 9.3. Кэш графовых запросов

Кэширует результаты обхода графа:

```yaml
cache:
  graph_traversal_cache:
    enabled: true
    ttl_sec: 300                  # 5 минут
```

### 9.4. Очистка кэша

```bash
# Полная очистка Redis
docker exec redis redis-cli FLUSHALL

# Очистка только семантического кэша
docker exec redis redis-cli --scan --pattern "sem_cache:*" | xargs docker exec -i redis redis-cli DEL

# Очистка кэша эмбеддингов
docker exec redis redis-cli --scan --pattern "emb:*" | xargs docker exec -i redis redis-cli DEL
```

---

## 10. A2A: межагентное взаимодействие

### 10.1. Agent Card

Другие агенты обнаруживают этот агент через стандартный эндпоинт:

```bash
curl http://localhost:8100/.well-known/agent.json
```

### 10.2. Отправка задач от другого агента

```bash
curl -X POST http://localhost:8100/a2a/tasks/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ваш_ключ" \
  -d '{
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "Найди информацию о TechCorp"}]
    }
  }'
```

### 10.3. Проверка статуса задачи

```bash
curl http://localhost:8100/a2a/tasks/{task_id} \
  -H "Authorization: Bearer ваш_ключ"
```

### 10.4. Streaming (SSE)

```bash
curl http://localhost:8100/a2a/tasks/{task_id}/stream \
  -H "Authorization: Bearer ваш_ключ"
```

### 10.5. Настройка peer-агентов

```yaml
a2a:
  registry:
    peer_agents:
      - url: "http://analytics-agent:8001"
        name: "DataAnalyst"
      - url: "http://translator-agent:8002"
        name: "Translator"
```

Агент может делегировать задачи peer-агентам, если запрос выходит за рамки его компетенций.

---

## 11. Резервное копирование и восстановление

### 11.1. Резервное копирование PostgreSQL

```bash
# Создание дампа
docker exec postgres pg_dump -U agent agent_db > backup_$(date +%Y%m%d).sql

# Восстановление
docker exec -i postgres psql -U agent agent_db < backup_20260316.sql
```

### 11.2. Резервное копирование Qdrant

```bash
# Snapshot коллекции
curl -X POST "http://localhost:6333/collections/knowledge_base/snapshots"

# Список snapshot'ов
curl "http://localhost:6333/collections/knowledge_base/snapshots"
```

### 11.3. Полный бэкап (Docker volumes)

```bash
# Остановка
make down

# Бэкап всех volumes
for vol in pg_data qdrant_data redis_data ollama_data knowledge_data; do
  docker run --rm -v "multimodal-graphrag-agent_${vol}:/data" \
    -v "$(pwd)/backups:/backup" alpine \
    tar czf "/backup/${vol}_$(date +%Y%m%d).tar.gz" -C /data .
done

# Запуск
make up-cpu
```

---

## 12. Устранение неполадок

### 12.1. Агент не запускается

```bash
# Проверьте логи
docker logs agent-api

# Частые причины:
# - Ollama не готов: подождите 30 сек после запуска
# - PostgreSQL не готов: проверьте docker compose ps
# - Неверный POSTGRES_PASSWORD в .env
```

### 12.2. Индексация не работает

```bash
# Проверьте логи Celery worker
docker compose logs -f celery-worker

# Убедитесь что файлы доступны
docker exec celery-worker ls /data/knowledge/

# Проверьте статус файлов в БД
docker exec postgres psql -U agent -d agent_db -c \
  "SELECT file_path, status, error_msg FROM kg_file_index;"

# Переиндексация файла (удалите запись и запустите sync)
docker exec postgres psql -U agent -d agent_db -c \
  "DELETE FROM kg_file_index WHERE file_path='/data/knowledge/файл.md';"
make sync
```

### 12.3. Ollama медленно отвечает

```bash
# Проверьте загрузку
docker stats ollama

# Модели в памяти
docker exec ollama ollama ps

# Используйте меньшую модель для batch-операций
# config.yaml -> llm.batch.model: "qwen2.5:3b"
```

### 12.4. Qdrant недоступен

```bash
# Проверьте статус
curl http://localhost:6333/readyz

# Логи
docker compose logs qdrant

# Перезапуск
docker compose restart qdrant
```

### 12.5. Ошибки Docker Desktop WSL2

```bash
# Bind mount errors при restart
# Решение: пересоздайте контейнер вместо restart
docker rm -f agent-api && docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d agent

# Медленный I/O
# Не храните данные на /mnt/c/ — используйте нативную FS WSL2 (~/...)
```

### 12.6. Нехватка памяти

Если система потребляет слишком много RAM:

1. Используйте меньшие модели: `qwen2.5:3b` вместо `qwen2.5:14b`
2. Уменьшите `max_connections` PostgreSQL в docker-compose.yml
3. Уменьшите `maxmemory` Redis (по умолчанию 2GB)
4. Ограничьте memory для Qdrant (по умолчанию 4GB)

### 12.7. Сброс системы

```bash
# Полный сброс (удаление всех данных)
make down
docker volume rm multimodal-graphrag-agent_pg_data \
  multimodal-graphrag-agent_qdrant_data \
  multimodal-graphrag-agent_redis_data \
  multimodal-graphrag-agent_knowledge_data
# Модели Ollama сохраняются в ollama_data
make up-cpu
```
