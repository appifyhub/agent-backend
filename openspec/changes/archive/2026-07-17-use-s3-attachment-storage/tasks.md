## 1. Configuration And Dependencies

- [x] 1.1 Add the selected S3 client dependency through `pipenv` and update the lockfile.
- [x] 1.2 Add config fields and config tests for `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BASE_URL`, `S3_REGION`, `S3_BUCKET`, `PUBLIC_API_BASE_URL`, and public attachment token TTL.
- [x] 1.3 Default `S3_REGION` to an EU region, `S3_BUCKET` to `the-agent`, `PUBLIC_API_BASE_URL` to `http://localhost:80`, and public token TTL to 600 seconds while letting the env var decide when set.
- [x] 1.4 Record local storage as the `.local/s3` implementation constant and ignore that path.
- [x] 1.5 Run lint/spacing checks on changed config files and run the config test subset.
- [x] 1.6 Mandatory manual review checkpoint: stop after Section 1 and wait for user approval before starting Section 2.

## 2. Attachment Storage Core

- [x] 2.1 Add a small attachment storage interface for put, read/stream, delete, and existence/bucket setup behavior.
- [x] 2.2 Add deterministic key derivation for `chats/{chat_id}/attachments/{attachment_id}` without changing the attachment ID.
- [x] 2.3 Add the production S3 storage adapter using configured endpoint, credentials, bucket, region, and hard-coded path-style addressing.
- [x] 2.4 Ensure the configured bucket exists idempotently without creating per-chat buckets.
- [x] 2.5 Add the local file storage adapter for development and tests using the `.local/s3` implementation constant.
- [x] 2.6 Wire storage selection through DI so production uses S3 and local development can run without Docker.
- [x] 2.7 Add focused tests for key derivation, local storage read/write/delete, S3 adapter configuration, bucket setup behavior, and DI selection.
- [x] 2.8 Run lint/spacing checks and the storage-related test subset.
- [x] 2.9 Mandatory manual review checkpoint: stop after Section 2 and wait for user approval before starting Section 3.

## 3. Attachment Delivery API

- [x] 3.1 Add public attachment token creation and verification helpers using the existing JWT secret, attachment/chat/issuer claims, and the configured public token TTL.
- [x] 3.2 Add `GET /attachments/private/{id}` with existing bearer JWT auth and chat-membership authorization.
- [x] 3.3 Add `GET /attachments/public/{token}` with token verification and no auth-header requirement.
- [x] 3.4 Stream attachment bytes from storage and set response content type from attachment metadata when available.
- [x] 3.5 Add or update OpenAPI docs for both attachment endpoints.
- [x] 3.6 Add tests for private success, private unauthenticated rejection, private non-member rejection, public success, expired public token rejection, debug chat-token context, and missing attachment behavior.
- [x] 3.7 Run lint/spacing checks and the attachment API test subset.
- [x] 3.8 Mandatory manual review checkpoint: stop after Section 3 and wait for user approval before starting Section 4.

## 4. Ingestion And Outbound Normalization

- [x] 4.1 Replace Uploadcare file upload behavior with service-owned attachment storage and delivery URL generation.
- [x] 4.2 Replace ImgBB image upload behavior with service-owned attachment storage and delivery URL generation.
- [x] 4.3 Normalize inbound Telegram attachments by downloading platform bytes once, storing them, persisting storage-backed attachment metadata, and using the copied `supported_files.detect_image_format` helper when byte-level image detection is still needed.
- [x] 4.4 Normalize inbound WhatsApp attachments by downloading platform bytes once, storing them, persisting storage-backed attachment metadata, and using the copied `supported_files.detect_image_format` helper when byte-level image detection is still needed.
- [x] 4.5 Add public repository constants for temporary attachment prefixes (`outgoing-*`, `external-*`) and use `is_temporary` for any temporary message rows.
- [x] 4.6 Update outbound platform send flows so local disk, generated, and Replicate-originated files are uploaded to temporary message / `outgoing-*` rows before sending.
- [x] 4.7 Exclude persisted temporary messages from normal latest-by-chat history by default, with an explicit opt-in for callers that need them.
- [x] 4.8 Use short-lived public attachment URLs generated from those temporary outgoing attachments when an external platform requires a fetchable URL.
- [x] 4.9 Remove or bypass stale platform URL refresh behavior for new attachments now that legacy attachment rows are deleted.
- [x] 4.10 Update tests around Telegram, WhatsApp, image generation/editing, social cards, and platform outbound sends.
- [x] 4.11 Run lint/spacing checks and the affected integration/unit test subsets.
- [x] 4.12 Mandatory manual review checkpoint: stop after Section 4 and wait for user approval before starting Section 5.
- [x] 4.13 Course-correct attachment identity so storage keys use `chats/{chat_id}/attachments/{attachment_id}`, `last_url` stores the durable storage URI, and short-lived public URLs are generated only on demand.
- [x] 4.14 Make attachment rows chat-owned by allowing nullable `message_id`, removing the attachment-message FK, adding `created_at`, and adding required `uploader_user_id` with a `simulants.id` FK.
- [x] 4.15 Drop public attachment token purpose claims, include attachment ID, chat ID, issuer user ID, `iat`, and `exp`, and treat token chat ID as debugging context while public reads resolve by attachment ID.
- [x] 4.16 Run lint/spacing checks and the affected identity/token/storage test subset.

## 5. Consumers, Cleanup, And Logging

- [x] 5.1 Replace direct `requests.get(attachment.last_url)` attachment consumers with storage reads or generated public URLs as appropriate.
- [x] 5.2 Update chat attachment processing to read retained bytes from attachment storage.
- [x] 5.3 Update image-edit and LLM attachment flows to use storage-backed bytes or short-lived public URLs.
- [x] 5.4 Move URL-supplied attachment normalization into the attachment service together with the consumer migration: allow service functions to accept `ChatAttachment | str`, merge URL normalization into `save(..., remote_url=..., remote_url_fetcher=...)`, return existing attachments for own public/private/storage URLs, download external URL bytes once with either a caller-supplied downloader returning `RemoteAttachmentContent` or default web headers, resolve only supported MIME/extension metadata from header MIME, URI, and bytes, generate a local attachment ID instead of using a deterministic URL hash, persist bytes in service-owned storage, and return storage-backed attachments.
- [x] 5.5 Update cleanup to delete storage objects for old-message attachments before or alongside normal row cleanup, while tolerating objects and rows being deleted by separate cleanup runs.
- [x] 5.6 Treat missing storage objects as already deleted during cleanup and log unexpected storage delete failures for retry.
- [x] 5.7 Add storage-object cleanup for orphaned objects and objects whose attachment rows are about to be deleted.
- [x] 5.8 Add attachment-row cleanup for normal message-retention attachment rows and any explicitly obsolete attachment rows discovered during review.
- [x] 5.9 Keep message-row cleanup focused on normal message-retention rows unless persisted temporary outgoing messages are still proven necessary.
- [x] 5.10 Review existing `external-*` and `outgoing-*` attachment identity and decide whether either still needs persisted cleanup under the chat-scoped attachment model.
- [x] 5.11 Stop logging full private or public attachment delivery URLs in new/changed paths; log attachment IDs, chat IDs, or shortened final path segments instead.
- [x] 5.12 Add tests for storage-backed consumers, URL-supplied attachment normalization, cleanup success, cleanup missing-object behavior, cleanup storage-failure retry behavior, temporary outgoing/virtual cleanup, orphan cleanup, and URL logging behavior.
- [x] 5.13 Run lint/spacing checks and the affected consumer/cleanup test subsets.
- [x] 5.14 Mandatory manual review checkpoint: stop after Section 5 and wait for user approval before starting Section 6.

## 6. Migration, Removal, And Verification

- [x] 6.1 Check that model imports in `src/db/alembic/env.py` are up to date before migration generation.
- [x] 6.2 Ask the user to run `./tools/db_generate_migration -y` so Alembic generates the migration.
- [x] 6.3 Review the generated migration and ensure it deletes existing `chat_attachments` rows, drops the attachment-message FK, makes attachment `message_id` nullable, adds attachment `created_at`, adds required attachment `uploader_user_id` with a `simulants.id` FK, replaces the bare attachment external-id index with `(chat_id, external_id)` uniqueness, and adds `chat_messages.is_temporary` defaulting to false.
- [x] 6.4 Add local disk storage fallback when neither S3 nor Uploadcare is configured (Uploadcare fallback backend deferred to Section 8).
- [x] 6.5 Remove now-unused ImgBB config, DI, uploader code, dependencies, duplicate util image/media-format detection helpers, Uploadcare direct-upload code not required by the fallback adapter, `has_stale_data`/`last_url_until` fields, platform SDK refresh branches below the `is_own_storage_uri` check, `UrlAttachmentResolver` file and its test, and the dead `expiration_s`/`message_text` parameters after reference searches are clean.
- [x] 6.6 Update docs and environment examples for S3, Uploadcare fallback, local disk fallback, and public API base URL configuration.
- [x] 6.7 Run targeted tests for changed modules, then run the broader offline test suite that is practical for this repo.
- [x] 6.8 Run lint/spacing checks on all changed Python files.
- [x] 6.9 Run strict OpenSpec validation for `use-s3-attachment-storage`.
- [x] 6.10 Record follow-up milestones: `consolidate-attachment-resolution` (immediate next) and `rename-chat-attachment` (after that). Both require manual review.
- [x] 6.11 Mandatory manual review checkpoint: stop after Section 6 and wait for user approval before starting the follow-up milestones (Sections 8–9).

## 7. Consolidate Attachment Resolution (done)

- [x] 7.1 Data resolvers persist inbound Telegram/WhatsApp bytes directly through the attachment service instead of per-SDK `refresh_attachment`.
- [x] 7.2 Replace the "refresh" concept with the service's own-storage short-circuit (`is_own_storage_uri` plus external-id dedupe) so stored attachments are never re-downloaded.
- [x] 7.3 Remove `has_stale_data`, `last_url_until`, and `_nearest_hour_epoch()` from the domain model and SDKs.
- [x] 7.4 Remove `refresh_attachments_by_ids` and `refresh_attachment_instances` from both platform SDKs (no external callers).
- [x] 7.5 Drop the `last_url_until` DB column via migration `6faaf160de6e` and clean up model, mapper, and remote-data references.
- [x] 7.6 Remove platform `last_url` reconstruction (Telegram file URL building, WhatsApp media URL caching); `last_url` is purely the storage URI set by the attachment service.
- [x] 7.7 Remove the `UrlAttachmentResolver` file and its test.

## 8. Uploadcare Fallback Storage Backend

- [x] 8.1 Restore `uploadcare_public_key`, `uploadcare_cdn_id`, and `uploadcare_private_key` config fields with config tests.
- [x] 8.2 Declare per-adapter capabilities through `can_be_used()` and `SERVES_PUBLIC_URLS` (bool). S3 requires base URL, access key, secret key, bucket, region; Uploadcare requires public key, private key, cdn id; local disk is always available. Only Uploadcare sets `SERVES_PUBLIC_URLS = True`.
- [x] 8.3 Add `public_attachment_for(metadata) -> PublicAttachment` on backends where `SERVES_PUBLIC_URLS` is true (Uploadcare returns its CDN URL, attachment ID, and own public URL TTL); it is never called on non-public backends.
- [x] 8.4 Branch `create_public_url` in the service: when `attachment_storage.SERVES_PUBLIC_URLS`, return `storage.public_attachment_for(attachment)` directly; otherwise mint the JWT token and build `{PUBLIC_API_BASE_URL}/attachments/public/{token}` as today. Token/auth logic stays entirely in the service; storage only exposes raw object addressability.
- [x] 8.5 Add `UploadcareAttachmentStorage` in `src/features/chat/attachment/storage/` implementing `ensure_ready`, `put`, `open`, `delete`, and `public_attachment_for` via the Uploadcare SDK; persist the uploadcare CDN URL in `last_url` and add an uploadcare arm to the service's `is_own_*` checks.
- [x] 8.6 Ensure `open()` fetches CDN bytes so private delivery (`/attachments/private/{id}`, always proxied) and byte consumers (LLM, image processing) work with the uploadcare backend.
- [x] 8.7 Drive DI storage selection through adapter `can_be_used()` checks in priority order (S3, Uploadcare, local disk); local disk is the guaranteed fallback. Partial config (e.g. only `S3_BASE_URL`) must not select that backend.
- [x] 8.8 Add tests for the adapter (`put`/`open`/`delete`/`public_attachment_for`), DI selection by full-config presence (partial config does not select a backend), and `create_public_url` direct-CDN vs token-endpoint branch.
- [x] 8.9 Keep the `pyuploadcare` dependency (already in Pipfile).
- [x] 8.10 Run lint/spacing checks and the storage-related test subset.
- [x] 8.11 Mandatory manual review checkpoint: stop after Section 8 and wait for user approval before starting Section 9.

## 9. Rename Chat-Message-Attachment To Chat-Attachment

- [x] 9.1 Rename module/file names `chat_message_attachment*` → `chat_attachment*`.
- [x] 9.2 Rename the domain model `ChatMessageAttachment` → `ChatAttachment`.
- [x] 9.3 Rename the DB model `ChatMessageAttachmentDB` → `ChatAttachmentDB`.
- [x] 9.4 Rename the repository `ChatMessageAttachmentRepository` → `ChatAttachmentRepository`.
- [x] 9.5 Rename the service `ChatMessageAttachmentService` → `ChatAttachmentService`.
- [x] 9.6 Rename DI properties `chat_message_attachment_repo`/`chat_message_attachment_service` → `chat_attachment_repo`/`chat_attachment_service`.
- [x] 9.7 Rename the DB table `chat_message_attachments` → `chat_attachments` via a table-rename migration (keep the `message_id` column, which still references a message when set).
- [x] 9.8 Update all test files and references; ensure the full suite passes before and after (pure rename, no behavioral change).
- [x] 9.9 Run lint/spacing checks on all changed Python files.
- [x] 9.10 Mandatory manual review checkpoint: stop after Section 9 and wait for user approval before marking the implementation complete.
