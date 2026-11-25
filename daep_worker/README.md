# DAEP Outbox Worker

This process is deliberately outside the Agent Runtime. It claims durable outbox records from DAEP and delivers them to an HTTP broker gateway, then acknowledges the outbox lease. Failed delivery is returned to DAEP for exponential retry; after the configured terminal threshold the record becomes `DEAD`.

Required environment:

- `DAEP_API_URL`
- `DAEP_WORKER_TOKEN` (at least 32 characters; separate from `DAEP_ADMIN_TOKEN`)
- `DAEP_BROKER_WEBHOOK_URL`

The worker uses only the dedicated worker credential for `/internal/v1/outbox/*`. It must not be given the platform administrator token.

This is **at-least-once** delivery. The downstream broker/gateway must deduplicate using the DAEP outbox ID or message ID because a crash after publish and before acknowledgement can cause redelivery.


## Production Compose deployment

The worker is intentionally opt-in behind the `broker` Compose profile. A plain
`docker compose -f compose.production.yaml up -d` does **not** start it.

For production Outbox delivery and periodic CollaborationGrant reminder/expiry
processing, configure both `DAEP_BROKER_WEBHOOK_URL` and an independent
`DAEP_BROKER_WEBHOOK_TOKEN` (at least 32 characters), then start it explicitly:

```bash
docker compose -f compose.production.yaml --profile broker up -d daep-worker
docker compose -f compose.production.yaml ps
```

The broker/gateway must deduplicate deliveries by DAEP Outbox ID or message ID:
delivery is at-least-once. Without a running worker, Outbox events remain
unprocessed and scheduled grant reminders/expiry materialization do not run.
