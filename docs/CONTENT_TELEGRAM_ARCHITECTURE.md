# Content and Telegram automation

## Мета

Зменшити ручний пошук і підготовку новин для Telegram приблизно на 80%, залишивши редактору контроль перед публікацією.

## Межа відповідальності

### n8n

- читає визначені RSS/API-джерела;
- викликає ORM API для reserve/dedupe до AI;
- передає матеріал у `Local-AI-Gateway`;
- перевіряє relevance/confidence/quality;
- передає результат у `content-store`, а не виконує SQL напряму;
- надсилає кандидат на модерацію;
- після `/approve ID` публікує в канал.

### `tg_content_bot`

Існуючий бот уже має ручну генерацію, контент-план, schedule і publish. Його не потрібно дублювати всередині n8n. Його можна залишити окремим редакторським інструментом або пізніше підключити через внутрішній API.

## Статуси кандидата

```text
processing → pending_review → publishing → published
processing → filtered
pending_review → rejected
publishing → pending_review   (recovery після помилки Telegram)
```

Дублікати визначаються за `dedupe_key` до AI. Статуси, quality gate, блокування подвійної публікації та транзакції обробляє SQLAlchemy ORM у сервісі `content-store`.

## Поточні workflow

1. `01-telegram-content-pipeline-orm.json` — ingestion, reserve/dedupe, AI-аналіз, language fallback і відправка на модерацію через ORM API.
2. `02-telegram-moderation-publish-orm.json` — `/approve ID`, `/reject ID` і публікація через ORM API.
3. Старі JSON — попередня SQL-версія для історії та порівняння.

## Важливий Telegram-момент

Не підключати один і той самий bot token одночасно до long polling у `tg_content_bot` і до Telegram Trigger у n8n. Для MVP використовувати окремого moderation bot або пізніше перейти на єдиний webhook-розподілювач.

## Наступні покращення

- 3–5 джерел із whitelist;
- HTTP fetch повної статті після RSS;
- robots.txt/rate-limit/cache;
- inline-кнопки замість команд;
- retry/error workflow;
- RAG із brand voice і правилами каналу;
- автоматична публікація лише для високого quality score.
