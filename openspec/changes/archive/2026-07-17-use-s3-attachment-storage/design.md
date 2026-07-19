## Context

The service currently stores attachment metadata in `chat_attachments` and treats `last_url` as the fetchable object location. New file uploads go through Uploadcare, new image uploads go through ImgBB, Telegram attachments are refreshed into Telegram file URLs, and WhatsApp media can be downloaded and reuploaded to permanent storage. Attachment processors and image-editing flows often consume `attachment.last_url` directly.

SeaweedFS S3 is now deployed in the cluster as an internal S3-compatible endpoint. The service needs to own attachment bytes, expose them through authenticated API endpoints, and make short-lived public links when HTML or external processors cannot attach authorization headers.

## Goals / Non-Goals

**Goals:**

- Make service-owned attachment storage the default for new inbound, generated, local, and outbound attachments.
- Remove Uploadcare and ImgBB from primary new upload paths, while retaining Uploadcare as an optional fallback storage adapter when S3 is not configured.
- Deliver attachment bytes through `/attachments/private/{id}` and `/attachments/public/{token}`.
- Authorize private attachment reads using existing web JWTs and chat membership.
- Support unauthenticated public attachment reads with a configurable lifetime defaulting to 10 minutes.
- Delete S3/local object bytes as part of existing chat-message retention cleanup.
- Keep local development simple without starting Docker from `main.py`.
- Delete existing attachment rows during migration instead of preserving legacy URL refresh behavior.

**Non-Goals:**

- Migrating old Uploadcare, ImgBB, Telegram, or WhatsApp attachment URLs into S3.
- Making SeaweedFS directly public.
- Adding per-chat buckets.
- Adding browser support for custom `Authorization` headers on plain `<img src>` tags.
- Reworking unrelated chat, message, or membership persistence.

## Decisions

### 1. Use One Bucket With Stable Chat-Scoped Object Keys

Use one bucket named `the-agent`. Derive object keys from immutable attachment identity:

```text
chats/{chat_id}/attachments/{attachment_id}
```

When an extension is known before upload, append it to the object filename:

```text
chats/{chat_id}/attachments/{attachment_id}.{extension}
```

The attachment ID remains the stable local object identity. Inbound platform attachments derive that local ID deterministically from the platform `external_id` so repeated updates resolve to the same local attachment. Generated, local, and outbound attachments use generated local IDs. Platform attachment or media IDs are still stored in `external_id`; they must not replace the local attachment ID semantically. Object keys do not include message ID, so an attachment can survive outbound temporary-message replacement and can remain addressable through the same storage object after the platform returns a real message ID. File metadata used for the key is finalized before upload and must not be changed afterward.

The chosen storage URI is persisted in `last_url` for new rows. `last_url` is no longer a short-lived public URL for service-owned attachments. Short-lived public URLs are generated on demand from attachment metadata and are not persisted. A separate object-key column is still avoided unless endpoint implementation proves `last_url` is not enough to preserve the uploaded location.

Attachments belong to chats. `chat_attachments.message_id` becomes nullable, and the attachment-to-message foreign key is removed. The row keeps `message_id` as optional provenance when a platform message ID exists. Add `created_at` for attachment-centered cleanup and `uploader_user_id` as a required foreign key to `simulants.id` for audit and future ownership-related features.

For platform-backed attachments, `external_id` is unique only within an attachment's chat. Enforce that with a `(chat_id, external_id)` uniqueness rule instead of a bare `external_id` index. Attachments with no `external_id` are generated/local/service-owned rows and remain valid under the same table.

Alternatives considered:

- **Per-chat buckets**: easier conceptual deletion, but bucket creation becomes runtime infrastructure management and SeaweedFS maps buckets to collections, making many buckets a bad fit.
- **Store object key in a new column**: flexible, but unnecessary if the chosen delivery URL preserves the uploaded path.
- **Include message ID in key**: readable for retained inbound messages, but breaks outbound flows where the final message ID is only known after the platform send call.
- **Never include extension in key**: avoids relying on finalized file metadata, but makes stored paths less useful and loses a simple fallback for consumers that inspect file names.

### 2. Normalize Attachments Before Retention, Processing, Or Sending

Introduce an attachment storage/ingestion service used by platform inbound flows, generated media flows, local file flows, and outbound send flows. The invariant is:

```text
any attachment we retain, process, or send externally is uploaded to service-owned storage first
```

For inbound Telegram/WhatsApp media, the service downloads platform media once, uploads it to attachment storage, and stores the attachment metadata. For generated/local output, the service uploads local bytes before producing URLs or sending to platforms. For outbound sends, the send path first ensures the file is S3-backed, then either sends bytes directly if the platform accepts binary upload or sends a short-lived public URL if the platform requires a URL.

For outbound platform sends that require a URL before the platform returns its real outgoing message ID, create a stable local attachment row under the chat and generate the public URL from that attachment. Because the storage object key does not include message ID, the object remains valid when the real outgoing message arrives. Outbound temporary messages are not required for storage identity; if a caller still creates one for context, it must be marked with the persisted `is_temporary` field so normal chat history excludes it without relying on message ID prefixes.

Existing external URL attachments are separate: they are in-memory resolver objects today, not retained DB rows. Review them after outbound normalization so the codebase has one clear story for non-platform temporary attachment identity.

URL-supplied attachments should move into the attachment service during the Section 5 consumer migration, after direct `last_url` fetch consumers are replaced. The service `save(...)` entry point should accept either a `ChatAttachment` instance or attachment ID. When supplied an attachment ID, `save(...)` resolves the existing attachment through `get(...)`; when supplied an attachment instance, `get(...)` returns that same instance. `save(...)` should also accept optional `remote_url` and `remote_url_fetcher` arguments. The fetcher returns `RemoteAttachmentContent`, carrying bytes plus optional response MIME metadata; callers with custom platform download logic should raise a structured error if they cannot fetch bytes. If bytes are supplied directly, they win and are stored under the supplied attachment identity. If no bytes are supplied and the URL is an own public attachment URL, own private attachment URL, or own storage URI, the service resolves and returns the existing attachment instead of creating a duplicate row or copying bytes. If no bytes are supplied and the URL is external, the service downloads URL bytes once using either a caller-supplied fetcher or default web headers, resolves only supported MIME/extension metadata from the available response MIME, URI, and bytes, stores the bytes in service-owned storage, and returns a storage-backed attachment. Until the consumer migration is complete, the current virtual URL resolver remains temporary compatibility code for call sites that still expect `last_url` to be directly fetchable.

Alternatives considered:

- **Keep refresh-on-demand for platform media**: preserves old behavior but keeps platform URLs and bot tokens in hot paths.
- **Only upload inbound media**: leaves generated/local outbound media dependent on temp files or third-party URLs.
- **Upload only when the frontend requests the file**: delays failures and does not help external processors.

### 3. Keep Attachment Metadata Columns And Use `last_url` As The Storage Pointer

Do not add a storage-key column in this change. For new rows, storage writes choose an object path from `chat_id` and the local attachment `id`. Existing `last_url` and `last_url_until` columns remain during the first implementation pass, but service-owned rows store a durable storage URI in `last_url` and do not use `last_url_until`.

The implementation should remove or bypass platform refresh logic for new attachments because existing rows will be deleted and all new rows are storage-backed.

Alternatives considered:

- **Persist short-lived public URLs in `last_url`**: works briefly, but reintroduces expiry handling and makes retained metadata stale by design.
- **Drop `last_url` immediately**: clean, but broadens migration and mapper/test churn. It can happen later after references are gone.

### 4. Use API Delivery Endpoints

Add two delivery surfaces:

- `GET /attachments/private/{id}`: requires `Authorization: Bearer <jwt>`, resolves the user through existing JWT auth, loads the attachment, checks that the user belongs to the attachment's chat, and streams bytes from storage.
- `GET /attachments/public/{token}`: does not require auth headers, verifies a short-lived token, loads the attachment, and streams bytes from storage.

Both endpoints set content type from attachment metadata when available. The implementation can add `Content-Disposition` where needed for document downloads.

Alternatives considered:

- **Direct SeaweedFS presigned URLs**: exposes internal storage topology and does not work while SeaweedFS is cluster-only.
- **JWT header only**: good for API clients but not enough for browser `<img src>` or external processors.
- **Cookie-only auth**: possible for the frontend but not useful for Telegram, WhatsApp, Replicate, or other external services.

### 5. Reuse Existing JWT Secret For Short-Lived Public Tokens

Public attachment links use the existing JWT signing secret with strict claims:

- attachment ID
- chat ID
- issuer user ID
- issued-at
- expiration

The chat ID claim is retained for debugging context. Public attachment reads resolve the attachment by signed attachment ID and still enforce membership for the issuing user.

The public token TTL is configurable. The default is 600 seconds, and an explicitly configured environment value decides the actual lifetime.

Alternatives considered:

- **Separate token secret**: provides isolation but adds operational config with little immediate benefit.
- **Hard-capped public token TTL**: stronger as a security invariant, but surprising for normal configuration because the environment variable would not fully decide behavior.
- **Query parameters on the private endpoint**: works technically, but separating public and private routes keeps authorization behavior obvious.
- **Purpose claim**: useful for generic public-resource tokens, but unnecessary when the token is attachment-specific and includes attachment and chat identity.

### 6. Use `boto3`/`botocore` For Production S3

Use `boto3`/`botocore` for the production storage adapter. Configure:

- `S3_BASE_URL=http://seaweedfs-s3.storage.svc.cluster.local:8333` in the cluster
- `S3_REGION=eu-central-1` by default
- `S3_BUCKET=the-agent`
- access key and secret key from `S3_ACCESS_KEY` and `S3_SECRET_KEY`

`boto3` is the AWS-supported SDK, supports endpoint overrides and path-style addressing, and targets the S3 API SeaweedFS implements. Path-style addressing is an adapter constant, not environment configuration: requests should look like `http://endpoint/bucket/key`, which fits the Kubernetes service DNS endpoint better than virtual-host style `http://bucket.endpoint/key`.

The production adapter should ensure the single configured bucket exists idempotently during startup or first use. It should not create buckets per chat.

Alternatives considered:

- **MinIO Python SDK**: clean API and S3-compatible, but vendor-specific and less standard for generic S3 integrations.
- **aioboto3**: useful for async services, but this codebase already uses synchronous external I/O in these paths.
- **s3fs**: useful for data tooling, not a good fit for explicit service storage operations.
- **LocalStack**: too heavy for local S3-only development.

### 7. Use Uploadcare Fallback Or Local File Storage Outside S3

Do not start Docker from `main.py`. Storage selection should be:

1. use S3 storage when S3 variables are configured.
2. use Uploadcare-backed storage when S3 variables are not configured and Uploadcare variables are configured.
3. use local disk storage under the project-local `.local/s3` directory when neither external storage backend is configured.

The local path is an implementation constant, not environment configuration. The selected backend must implement the same storage interface as S3: put, read/stream, and delete by derived key or stored pointer. Cleanup deletes local files through the same object-deletion path used for S3. Uploadcare should be retained only as a fallback storage implementation, not as the primary production upload path.

Tests should primarily use this local adapter or mocks. Add focused tests for storage selection order so S3 wins when configured, Uploadcare is selected only when S3 is absent and Uploadcare config is present, and local disk is selected when neither external backend is configured. Moto can be introduced only for targeted S3 adapter tests where boto3 behavior itself needs coverage.

Alternatives considered:

- **Auto-start MinIO from `main.py --dev`**: hides infrastructure behind application startup and creates Docker lifecycle, port, and first-pull issues.
- **Require developers to run MinIO manually**: closer to production, but violates the desired simple local run path.
- **Use Moto for all local runs**: closer to boto3 semantics than files, but still adds an in-process service and is unnecessary for most development.
- **Delete Uploadcare entirely**: simpler dependency cleanup, but removes a useful cloud-backed local fallback when S3 is intentionally unavailable.

### 8. Cleanup Owns Object And Row Retention

Extend cleanup so object bytes, attachment rows, and message rows are independently eligible for deletion. Cleanup should prefer deleting storage objects before deleting rows where it already has both identities, but it must tolerate either side being deleted first. If storage deletion fails, log the error and leave any remaining rows for a later cleanup run. If a row was already deleted, orphan-object cleanup can delete the object later.

Storage-object cleanup covers:

- objects whose attachment rows are already missing.
- objects whose attachment rows are about to be deleted by normal message-retention cleanup.

Attachment-row cleanup covers:

- attachment rows deleted by normal message-retention cleanup.

Message-row cleanup covers:

- message rows deleted by normal message-retention cleanup.

Existing `external-*` and `outgoing-*` attachment identity should be reviewed separately. They should not be included in generic obsolete-attachment cleanup by default unless implementation proves those persisted rows still exist under the new chat-scoped attachment model.

Do not rely on SeaweedFS bucket TTL as the primary retention mechanism. App cleanup already owns message retention and must keep database rows and object bytes in sync.

Alternatives considered:

- **Bucket TTL only**: can create dangling database rows.
- **Strict all-or-nothing cleanup**: reduces temporary inconsistencies but overcomplicates a retryable low-volume cleanup path.

### 9. Logging Uses Short Attachment Identifiers

New logs must avoid full private or public attachment delivery URLs. When a URL-like value is useful, log the final route/key segments or the attachment id and chat id. Signed public URLs are public for the configured token lifetime, so logs should not print them in full.

Alternatives considered:

- **Generic secret redaction only**: does not catch signed URLs because token values are generated dynamically.
- **Never log attachment identifiers**: safer but makes debugging storage and delivery failures harder.

## Risks / Trade-offs

- Existing attachments disappear after migration -> acceptable because user count is low and messages age out; rollback needs a database backup if old rows are required.
- Derived keys require stable attachment IDs before upload -> ingestion must generate or persist the attachment ID before storing bytes.
- Storage upload can succeed while DB save fails -> retry-safe overwrite semantics and cleanup of unreferenced failed uploads should be considered in implementation; low-volume orphan risk is acceptable for the first pass.
- Public tokens can leak through external service logs -> keep the default expiry at 10 minutes, keep production values short, and avoid logging full public URLs internally.
- API proxying adds service load for large files -> stream responses rather than loading whole files into memory where practical.
- S3 outage blocks attachment cleanup and delivery -> log failures and leave rows for retry; chat text cleanup should not silently delete rows whose objects were not deleted.
- Local file storage differs from SeaweedFS behavior -> keep the storage interface small and add targeted S3 adapter tests for endpoint/path-style configuration.

## Migration Plan

1. Add storage configuration and dependency support.
2. Add the storage adapter interface, S3 adapter, local adapter, and DI wiring.
3. Add attachment key derivation and public token creation/verification helpers.
4. Add private and public attachment delivery endpoints and OpenAPI docs.
5. Replace Uploadcare and ImgBB uploader paths with attachment storage-backed flows.
6. Normalize inbound Telegram/WhatsApp media into storage at ingestion.
7. Normalize generated/local outbound media into storage before sending or processing.
8. Replace direct `last_url` fetch consumers with storage reads or generated public URLs.
9. Update cleanup to delete storage objects before attachment/message rows.
10. Generate a migration that deletes existing attachment rows.
11. Remove unused ImgBB configuration and Uploadcare direct-upload paths, while preserving Uploadcare pieces required for optional fallback storage.

Rollback is code-level only unless a database backup restores deleted attachment rows. Object bytes created by the new version can be left for cleanup or deleted by prefix if rollback is immediate.

## Open Questions

- Should the implementation remove `last_url` and `last_url_until` columns in this change after consumers are migrated, or leave them for a later cleanup change?
- Should failed post-upload DB saves immediately try to delete the just-uploaded object, or rely on periodic cleanup/orphan handling?

