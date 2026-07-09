# approval-service

Простой backend-сервис для согласования контента перед публикацией.

Что умеет сервис:

- создать заявку на согласование;
- получить список заявок в workspace;
- получить одну заявку по `id`;
- принять решение: `approve`, `reject` или `cancel`.

## Быстрый старт (локально)

Требования: Python 3.12+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

После запуска сервис доступен по адресу: `http://127.0.0.1:8000`.

Проверка:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

## Запуск в Docker

```bash
docker compose up --build
```

Сервис будет доступен на `http://localhost:8000`.

## Заглушка авторизации (обязательно)

Для всех бизнес-методов (`/api/v1/...`) нужно передавать заголовки:

- `X-Auth-Workspace-Id` - workspace пользователя;
- `X-Auth-User-Id` - id пользователя;
- `X-Auth-Actions` - права через запятую.

Поддерживаемые права:

- `approval:read` - чтение заявок;
- `approval:create` - создание заявки;
- `approval:decide` - `approve`/`reject`;
- `approval:cancel` - `cancel`.

Для `create` можно передать:

- `X-Idempotency-Key` - ключ идемпотентности (повтор с тем же телом вернет ту же заявку, без дубля).

## Примеры запросов

### 1) Создать заявку

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/workspaces/ws_1/approval-requests" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Workspace-Id: ws_1" \
  -H "X-Auth-User-Id: usr_admin" \
  -H "X-Auth-Actions: approval:create,approval:read,approval:decide,approval:cancel" \
  -H "X-Idempotency-Key: req-001" \
  -d '{
    "sourceType": "publication",
    "sourceId": "pub_123",
    "title": "Instagram reel draft",
    "description": "Needs final approval",
    "reviewerUserIds": ["usr_1", "usr_2"]
  }'
```

### 2) Получить список заявок

```bash
curl "http://127.0.0.1:8000/api/v1/workspaces/ws_1/approval-requests" \
  -H "X-Auth-Workspace-Id: ws_1" \
  -H "X-Auth-User-Id: usr_reader" \
  -H "X-Auth-Actions: approval:read"
```

### 3) Подтвердить заявку

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/workspaces/ws_1/approval-requests/<request_id>/approve" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Workspace-Id: ws_1" \
  -H "X-Auth-User-Id: usr_reviewer" \
  -H "X-Auth-Actions: approval:decide" \
  -d '{"comment":"Approved"}'
```

## Тесты

```bash
pytest
```

## Коротко про поведение

- Данные строго изолированы по `workspace_id`.
- Повторный `create` с тем же `X-Idempotency-Key` не создает дубликат.
- После финального статуса (`approved`/`rejected`/`canceled`) изменить решение нельзя.
- Каждое успешное изменение пишется в аудит и в outbox-события.
