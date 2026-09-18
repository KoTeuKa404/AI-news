# 3M Agency — AI & Marketing Automation Lab

Практичний MVP інфраструктури для автоматизації контенту, Telegram-модерації та AI-процесів маркетингової агенції.

Проєкт демонструє не просто виклик LLM, а повний керований pipeline: отримання даних → нормалізація → дедуплікація → AI-аналіз → quality gate → модерація → публікація.

## Що реалізовано

### Telegram Content Intelligence

`RSS → Normalize → Reserve/Dedupe → Full Article Fetch → AI Analyze → Quality Gate → Telegram Review → Publish`

- обробка RSS items;
- нормалізація та дедуплікація URL;
- PostgreSQL-backed ORM для кандидатів і статусів;
- AI-аналіз релевантності, впевненості та якості;
- structured output і контроль поламаних відповідей;
- українська мовна перевірка з AI fallback;
- модерація та публікація через Telegram;
- atomic approve/reject і захист від повторної публікації;
- recovery для помилок під час Telegram publish;
- історія модерації та правок.

### Client Review Agent

Окремий n8n workflow, який отримує `client_id`, заголовок і текст матеріалу, завантажує історію правок клієнта та прогнозує потенційні зауваження до відправлення матеріалу.

Результат має стабільну структуру:

```json
{
  "ok": true,
  "risk_level": "medium",
  "confidence": 0.78,
  "likely_edits": ["додати конкретну дату"],
  "risk_flags": ["може знадобитися більше технічних деталей"],
  "summary": "Матеріал відповідає стилю, але варто уточнити деталі."
}
```

Контекст клієнта формується з реальної історії approved/rejected матеріалів і ручних правок, а не з абстрактного prompt-only профілю.

## Архітектура

```text
n8n
 ├─ Telegram Content Pipeline
 ├─ Telegram Moderation & Publish
 └─ Client Review Agent
        │
        ├─ Local AI Gateway
        └─ content-store API
                │
                └─ PostgreSQL
```

### Основні компоненти

- **n8n** — orchestration, webhooks, scheduled workflows та інтеграції;
- **Python / FastAPI** — content-store API та бізнес-правила;
- **PostgreSQL** — кандидати, дедуплікація, стани, moderation events і style context;
- **Local AI Gateway** — єдина точка доступу до локальних або зовнішніх моделей;
- **Telegram Bot API** — модерація та публікація.

## Запуск локально

1. Скопіювати `.env.example` у `.env`.
2. Заповнити локальні credentials у `.env`.
3. Запустити стек:

```bash
docker compose up -d --build
```

4. Відкрити n8n: `http://localhost:5678`.
5. Імпортувати workflow з `workflows/` або відкрити вже синхронізовані workflow у n8n.

Перевірки стану:

- n8n: `http://localhost:5678/healthz`;
- content-store: `http://localhost:18090/health`.

## Тест Client Review Agent

Workflow: `3M | Client Review Agent`.

Вхідний webhook очікує:

```json
{
  "client_id": "telegram-default",
  "title": "Нова функція OpenAI для розробників",
  "text": "OpenAI представила новий інструмент для автоматизації роботи розробників."
}
```

Приклад API контексту клієнта:

```text
GET /v1/clients/{client_id}/style-context
```

## Безпека та надійність

- секрети зберігаються тільки в `.env`, який не потрапляє в Git;
- source fetch дозволяє тільки HTTP/HTTPS і блокує localhost/private IP;
- для зовнішніх HTTP-запитів є timeout та обмеження розміру відповіді;
- approve проходить через атомарний перехід стану;
- retry не створює дублікати Telegram-постів;
- AI-відповіді перевіряються кодом, а не лише `JSON.parse()`;
- невдалі обробки переводяться у контрольований `failed`.

## Структура

```text
workflows/                  # n8n workflows
services/content-store/     # FastAPI + SQLAlchemy API
sql/                         # базова SQL-ініціалізація
docs/                        # архітектура, roadmap і матеріали портфоліо
tools/                       # локальні утиліти міграції/перевірки
```

## Статус

Це робочий локальний MVP, підготовлений як основа для production hardening: додавання Meta/Google Ads API, anomaly detection, observability, prompt/model versioning та durable client profile/RAG.
