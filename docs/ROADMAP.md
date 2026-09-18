# Roadmap під 3M Agency

## Phase 1 — Content Intelligence MVP

- [x] RSS джерело
- [x] Нормалізація item
- [x] AI relevance/noise filtering
- [x] Адаптація тексту під Telegram
- [x] Quality/confidence threshold
- [x] PostgreSQL deduplication
- [x] Telegram moderation delivery
- [x] Approve/reject commands
- [x] Автопублікація після approve
- [ ] Додаткові джерела та whitelist/blacklist

## Phase 2 — Ads KPI Monitor

- [ ] Meta Ads API credential
- [ ] Google Ads API credential
- [ ] Daily KPI snapshot
- [ ] CPL/CPA/CTR/budget anomaly rules
- [ ] AI explanation and recommendation
- [ ] Telegram alert and daily digest
- [ ] Persistent KPI history

## Phase 3 — Client Review Agent

- [x] Load previous edits and moderation history from content-store
- [x] Extract client style context per stable client id
- [x] Predict likely corrections before Telegram moderation
- [x] Return risk level, confidence, checklist and risk flags
- [x] Store style-review predictions for later evaluation
- [x] Webhook for an external draft and client id
- [ ] Store feedback from a real client review
- [ ] Build a durable client profile/RAG layer

## Phase 4 — Production hardening

- [ ] Separate error workflow
- [ ] Retries with backoff
- [ ] Idempotency keys for every external action
- [ ] Structured execution log
- [ ] Prompt/model versioning
- [ ] PII and secrets policy
- [ ] Healthcheck and incident notifications
