# Outbox Broker Worker — RC6

`daep_worker.worker` is a separate process. It does not start or control Agent Runtime processes.

Configure `DAEP_WORKER_TOKEN` as an independent random secret of at least 32 characters in both the API and worker environments. The worker uses this least-privilege credential only for `/internal/v1/outbox/*`; it must not receive `DAEP_ADMIN_TOKEN`. Rotate it by updating the secret in both services and restarting them.

Flow:

1. claim a durable outbox row with a lease;
2. POST the event payload to `DAEP_BROKER_WEBHOOK_URL`;
3. on success, complete the lease;
4. on failure, ask DAEP to schedule exponential retry;
5. after the retry threshold, DAEP marks the record `DEAD`.

The worker is transport-neutral. The configured HTTP endpoint can be an internal gateway that publishes to Kafka, RabbitMQ, Redis Streams, NATS or another enterprise broker. The downstream system should deduplicate by DAEP message ID because delivery is at-least-once. A crash after downstream publish but before completion can cause redelivery.
