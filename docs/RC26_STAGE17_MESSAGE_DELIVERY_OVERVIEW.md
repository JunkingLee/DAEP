# RC26 Stage 17 — Message Delivery Operations Overview

Adds the platform-admin-only endpoint:

`GET /api/v1/admin/message-delivery?limit=200&offset=0&dispatch_status=DEAD&ack_status=PENDING`

The endpoint reports message delivery operational metadata while keeping broker dispatch and recipient acknowledgement as independent state dimensions.

Dispatch states: `NO_OUTBOX`, `DUPLICATE`, `PENDING`, `IN_FLIGHT`, `SENT`, and `DEAD`. ACK states remain `PENDING`, `ACKNOWLEDGED`, and `REJECTED`. Filters are validated; page size is bounded to 500. Each message includes its associated dispatch records, attempts, retry availability, lease metadata, last error, and sent timestamp. The response intentionally omits message title and body.

The response also includes dispatch/ACK counts and malformed outbox count observed during the scan. `SENT` is explicitly defined as broker dispatch completion, not recipient ACK. The endpoint is read-only and admin-only.

Automated coverage exercises PENDING/SENT/DEAD dispatch states against independent ACK states, filtering, invalid filters, authorization, and omission of message content. This is deterministic database-level coverage, not a live broker or production operations drill.
