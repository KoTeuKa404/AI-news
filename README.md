# n8n Content Automation

An n8n-based content pipeline with a small FastAPI service and PostgreSQL storage.

The repository contains workflows for:

- reading RSS feeds;
- normalizing and deduplicating articles;
- fetching article text before analysis;
- sending structured content to an LLM;
- checking quality and language rules;
- sending candidates to Telegram for review;
- publishing approved candidates to a Telegram channel;
- predicting likely client edits from previous moderation history.

The LLM is one step in the workflow. Candidate state, deduplication, validation, publishing and recovery are handled by the application code and the n8n workflow logic.

## Architecture

```text
RSS feeds ──▶ n8n content workflow ──▶ content-store ──▶ PostgreSQL
                                      │
                                      ├─▶ AI API
                                      └─▶ Telegram Bot API

External draft ──▶ n8n client review webhook
                         │
                         ├─▶ content-store style context
                         └─▶ AI API
```

### Services

| Service | Purpose |
| --- | --- |
| n8n | Schedules, webhooks, workflow execution and integrations |
| `content-store` | FastAPI service for candidates, source fetching, moderation and history |
| PostgreSQL | Candidate data, deduplication, state transitions and moderation events |
| AI API | OpenAI-compatible endpoint used by the n8n AI nodes |
| Telegram Bot API | Review messages and channel publishing |

## Workflows

| File | Description |
| --- | --- |
| `workflows/01-telegram-content-pipeline-orm.json` | RSS ingestion, article processing, AI analysis and moderation delivery |
| `workflows/02-telegram-moderation-publish-orm.json` | Approve, reject, edit, release and publish operations |
| `workflows/03-client-review-agent.json` | Predicts likely client edits for a draft received through a webhook |
| `workflows/01-telegram-content-pipeline.json` | Older SQL-based version of the content workflow |
| `workflows/02-telegram-moderation-publish.json` | Older SQL-based version of the moderation workflow |

The ORM workflows use the `content-store` API instead of connecting to PostgreSQL directly from n8n.

## Content flow

```text
RSS
  → normalize item
  → reserve URL / deduplicate
  → validate URL
  → fetch full article text
  → analyze with LLM
  → validate structured result
  → apply quality gate
  → send to Telegram review
  → approve and publish
```

Candidate states are managed as:

```text
processing → pending_review → publishing → published
processing → filtered
pending_review → rejected
publishing → pending_review  # recovery when publishing is confirmed incomplete
```

The publish path stores the Telegram message ID and uses an atomic state transition to prevent a second publish when the approve action is repeated.

## Requirements

- Docker Desktop with Docker Compose;
- an OpenAI-compatible local AI Gateway;
- a Telegram bot with access to the review chat and target channel;
- PowerShell, Bash or another shell for local commands.

## Local setup

### 1. Create the environment file

```bash
cp .env.example .env
```

PowerShell:

```powershell
Copy-Item .env.example .env
```

Set the values for the database, AI Gateway and Telegram bot in `.env`. At minimum, configure:

```dotenv
POSTGRES_PASSWORD=
N8N_ENCRYPTION_KEY=
AI_GATEWAY_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_REVIEW_CHAT_ID=
TELEGRAM_TARGET_CHANNEL_ID=
TELEGRAM_MODERATOR_IDS=
```

Do not commit `.env`.

### 2. Start the services

```bash
docker compose up -d --build
```

Local endpoints:

- n8n: <http://localhost:5678>
- n8n healthcheck: <http://localhost:5678/healthz>
- content-store: <http://localhost:18090>
- content-store healthcheck: <http://localhost:18090/health>
- content-store API docs: <http://localhost:18090/docs>

### 3. Configure n8n

Import the required JSON files from `workflows/` and attach credentials to the nodes that call the AI Gateway and Telegram Bot API.

The main AI node uses the `Local AI Gateway MAIN` credential. The client review workflow is separate from the RSS content workflow and is inactive until it is explicitly enabled.

## Client review webhook

The `03-client-review-agent.json` workflow accepts a draft and a stable client ID. The request body is:

```json
{
  "client_id": "telegram-default",
  "title": "New developer tool",
  "text": "A short draft to review.",
  "candidate_id": 123
}
```

The workflow loads the client context from:

```text
GET /v1/clients/{client_id}/style-context
```

The response contains a risk level, confidence score, likely edits, risk flags and a short summary:

```json
{
  "ok": true,
  "client_id": "telegram-default",
  "candidate_id": 123,
  "risk_level": "low",
  "confidence": 0.62,
  "likely_edits": [],
  "risk_flags": [],
  "summary": "No strong pattern was found in the available history."
}
```

## content-store API

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/health` | Service healthcheck |
| `POST` | `/v1/candidates/reserve` | Reserve a candidate and perform deduplication |
| `POST` | `/v1/source/fetch` | Fetch article text with URL and size limits |
| `PATCH` | `/v1/candidates/{id}/analysis` | Store AI analysis and quality gate result |
| `POST` | `/v1/candidates/{id}/fail` | Mark processing as failed |
| `GET` | `/v1/candidates/{id}` | Get candidate details |
| `GET` | `/v1/clients/{client_id}/style-context` | Get client style context |
| `POST` | `/v1/candidates/{id}/style-review` | Store a style review prediction |
| `POST` | `/v1/candidates/{id}/approve` | Atomically approve a candidate |
| `POST` | `/v1/candidates/{id}/publish` | Store Telegram publish result |
| `POST` | `/v1/candidates/{id}/release` | Release a publishing lock for recovery |
| `POST` | `/v1/candidates/{id}/reject` | Reject a candidate |
| `PATCH` | `/v1/candidates/{id}/edit` | Store a manual edit |
| `POST` | `/v1/errors` | Store an execution error |
| `GET` | `/v1/metrics/summary` | Get service metrics |

Interactive OpenAPI documentation is available at `http://localhost:18090/docs` when the stack is running.

## Configuration

The available settings are documented in `.env.example`. Important groups include:

- database connection settings;
- AI Gateway URL, key and model;
- content-store quality thresholds;
- source fetch timeout, response size and host allowlist;
- processing retry limits;
- Telegram IDs and moderation settings;
- timezone and RSS feed URL.

The Docker setup uses `host.docker.internal` to access an AI Gateway running on the host machine. Change `AI_GATEWAY_BASE_URL` if the gateway runs elsewhere.

## Security and failure handling

- `.env` is ignored by Git;
- source fetching only allows `http` and `https`;
- localhost, loopback and private IP ranges are blocked;
- source requests have a timeout and maximum response size;
- LLM output is checked for required fields and value ranges;
- failed processing is stored as `failed` instead of remaining in `processing` indefinitely;
- approval uses an atomic `pending_review` check;
- Telegram message IDs are stored for publish recovery;
- workflow JSON files contain credential references, not secret values.

## Repository layout

```text
.
├── workflows/                  # n8n workflow exports
├── services/content-store/     # FastAPI and SQLAlchemy service
├── sql/                        # database initialization
├── docs/                       # architecture, roadmap and project notes
├── tools/                      # maintenance scripts
├── docker-compose.yml
├── .env.example
└── README.md
```

## Roadmap

- Meta Ads and Google Ads API integrations;
- daily campaign KPI snapshots;
- CPL, CPA, CTR and budget anomaly detection;
- AI-generated campaign explanations and recommendations;
- separate error workflow with backoff;
- execution logs and notifications;
- prompt and model versioning;
- persistent client profiles and RAG-based style rules.

## License

No license has been selected for this repository yet.
