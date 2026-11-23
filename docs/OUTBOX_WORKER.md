# Transactional Outbox Worker Contract — RC6

DAEP writes each collaboration message and its `outbox` event in one database transaction. This prevents the platform from committing a message without also recording the downstream delivery work.

## Worker loop

1. Poll `POST /internal/v1/outbox/claim` with a unique worker ID. Each claimed item includes a one-time random `lease_token`; keep batches small enough to finish within the lease.
2. Publish each payload to the chosen broker/webhook with the outbox `id` as the idempotency key.
3. After the downstream system confirms durable acceptance, call `/complete` with both `worker_id` and that item's `lease_token`.
4. On transient failure, call `/fail` with the same lease fields; DAEP applies exponential backoff. Expired or superseded lease tokens are rejected. After eight attempts, the record becomes `DEAD` and requires operator intervention.
5. If a worker crashes, its lease expires and another worker may reclaim the item.

## Delivery semantics

The contract is **at-least-once**, not exactly-once. A crash after downstream publish but before `/complete` can cause a duplicate. Consumers must deduplicate by outbox ID. The member inbox remains authoritative and must be used for recovery; WebSocket notifications are best-effort only. Reconnect with `after=<last processed message seq>` to resume the live stream from a client-maintained cursor; the inbox endpoint remains the durable recovery path. Message acknowledgements are idempotent when the same terminal status is repeated.

## Security

- Configure a unique `DAEP_WORKER_TOKEN` (at least 32 characters) in both API and worker environments.
- The worker credential must differ from `DAEP_ADMIN_TOKEN`; internal outbox endpoints reject the administrator token.
- The worker does not receive or require platform administrator credentials.
- The worker also requires a separate `DAEP_BROKER_WEBHOOK_TOKEN` (at least 32 characters) when HTTP gateway delivery is enabled. It is sent as a Bearer credential and must be validated by the gateway.
- Each HTTP delivery includes `X-DAEP-Outbox-ID` as a stable idempotency key and `X-DAEP-Delivery-Attempt`; gateways should persist deduplication by outbox ID.
- Rotate the credential in the secret manager and restart both services together.
- Monitor pending/in-flight and dead-letter counts; `/health` exposes pending/in-flight counts. Platform administrators can inspect dead letters through `GET /api/v1/admin/outbox/dead` and replay an item with `POST /api/v1/admin/outbox/{id}/replay`, supplying a mandatory reason. Replay resets the delivery attempt counter and records an `outbox.dead.replayed` audit event. A graphical operator UI remains future work.

## Current limitations

The bundled worker delivers to an authenticated HTTP gateway; it does not itself implement a Kafka/RabbitMQ/Redis Streams/NATS client. Configure the gateway to publish into the chosen broker. PostgreSQL live integration and end-to-end broker verification remain deployment tasks.
