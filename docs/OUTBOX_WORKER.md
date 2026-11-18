# Transactional Outbox Worker Contract — RC6

DAEP writes each collaboration message and its `outbox` event in one database transaction. This prevents the platform from committing a message without also recording the downstream delivery work.

## Worker loop

1. Poll `POST /internal/v1/outbox/claim` with a unique worker ID. Keep batches small enough to finish within the lease.
2. Publish each payload to the chosen broker/webhook with the outbox `id` as the idempotency key.
3. After the downstream system confirms durable acceptance, call `/complete`.
4. On transient failure, call `/fail`; DAEP applies exponential backoff. After eight attempts, the record becomes `DEAD` and requires operator intervention.
5. If a worker crashes, its lease expires and another worker may reclaim the item.

## Delivery semantics

The contract is **at-least-once**, not exactly-once. A crash after downstream publish but before `/complete` can cause a duplicate. Consumers must deduplicate by outbox ID. The member inbox remains authoritative and must be used for recovery; WebSocket notifications are best-effort only.

## Security

- Configure a unique `DAEP_WORKER_TOKEN` (at least 32 characters) in both API and worker environments.
- The worker credential must differ from `DAEP_ADMIN_TOKEN`; internal outbox endpoints reject the administrator token.
- The worker does not receive or require platform administrator credentials.
- Rotate the credential in the secret manager and restart both services together.
- Monitor pending/in-flight and dead-letter counts; `/health` exposes pending/in-flight counts. Dead-letter inspection and operator replay UI remain future work.

## Current limitations

The bundled worker delivers to an HTTP gateway; it does not itself implement a Kafka/RabbitMQ/Redis Streams/NATS client. Configure the gateway to publish into the chosen broker. PostgreSQL live integration and end-to-end broker verification remain deployment tasks.
