# Проєкт для портфоліо

## 1. AI Content Intelligence та Telegram pipeline

**Задача:** зменшити ручний пошук, перевірку та підготовку технологічних новин для Telegram.

**Рішення:** побудований n8n pipeline, який читає RSS, нормалізує items, резервує нові URL через ORM, завантажує повний текст статті, передає матеріал у AI, застосовує quality gate і відправляє кандидата на Telegram-модерацію.

**Технології:** n8n, Python/FastAPI, PostgreSQL, SQLAlchemy, REST API, webhooks, Telegram Bot API, Local AI Gateway.

**Практичний результат:** редактор отримує вже підготовлений і структурований матеріал, але зберігає контроль над approve/reject; у системі є дедуплікація, контроль статусів, structured output, retry/recovery та захист від подвійної публікації.

## 2. Client Review Agent

**Задача:** прогнозувати можливі правки конкретного клієнта ще до відправлення матеріалу.

**Рішення:** окремий агент приймає `client_id`, title і text, завантажує історію попередніх правок та відхилень, передає контекст у LLM і повертає risk level, confidence, likely edits та risk flags у строгому JSON.

**Технології:** n8n, Python/FastAPI, PostgreSQL, REST, webhook, локальний AI gateway.

**Практичний результат:** можна поступово накопичувати client-specific style context і переводити повторювані редакторські зауваження в автоматичну pre-flight перевірку.

## 3. Наступний модуль — Ads KPI Monitor

Наступний логічний етап цього ж підходу — підключення Meta Ads API та Google Ads API, збереження щоденних KPI snapshot, виявлення аномалій у CPL/CPA/CTR/бюджетах і надсилання AI-пояснень у Telegram.

Цей модуль позначений у roadmap як наступна фаза, а не як уже завершена production-функція.
