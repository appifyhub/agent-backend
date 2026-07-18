## Why

Chat attachments currently depend on third-party public upload hosts and platform-specific URL refresh behavior. SeaweedFS S3 is now available in the cluster, so attachments should be normalized into service-owned durable storage, delivered through the API, and deleted with the same retention policy as chat messages.

## What Changes

- Replace primary Uploadcare file uploads and ImgBB image uploads with S3-compatible attachment storage backed by the `the-agent` bucket.
- Retain the Uploadcare file handler as an optional non-S3 storage fallback for local testing when S3 variables are not set but Uploadcare variables are set.
- Store new inbound, generated, local-disk, and outbound attachments in S3 before they are retained, processed, or sent to external services.
- Normalize URL-supplied attachment inputs into service-owned storage during the consumer migration, using generated local attachment IDs instead of deterministic URL hashes.
- Derive object locations from chat ID and stable attachment ID using a key pattern under the bucket, instead of adding an object-key column unless implementation proves derivation unsafe.
- Add authenticated attachment delivery at `/attachments/private/{id}` for users who belong to the attachment's chat.
- Add unauthenticated, short-lived public attachment delivery at `/attachments/public/{token}` for HTML rendering and external processors such as Telegram, WhatsApp, and Replicate.
- Reuse the existing JWT signing secret for public attachment tokens with attachment ID, chat ID, issuing-user claims, and a configurable token lifetime that defaults to 10 minutes.
- Add S3 and public API base URL configuration, with local development defaulting to `PUBLIC_API_BASE_URL=http://localhost:80`.
- Add fallback storage selection that uses S3 when configured, Uploadcare when S3 is absent and Uploadcare is configured, and local disk when neither external storage is configured.
- Change cleanup so attachment object bytes are deleted together with old chat-message attachment rows.
- Stop logging full generated attachment delivery URLs; log stable, shortened identifiers such as the final path segments.
- Consolidate inbound attachment resolution so data resolvers persist platform bytes directly through the attachment service, removing per-platform URL refresh, `has_stale_data`, `last_url_until`, and `_nearest_hour_epoch` (done, Section 7).
- As a second-to-last milestone, re-add Uploadcare as a selectable fallback storage backend (`UploadcareAttachmentStorage`) chosen when S3 is unset but Uploadcare keys are present; public delivery returns uploadcare's direct CDN URL (reachable without a public API host) while private delivery stays proxied through the API (Section 8).
- As the final milestone, rename the chat-message-attachment naming (modules, models, repository/service, DI properties, DB table) to chat-attachment now that attachments are chat-owned (Section 9).
- **BREAKING**: Delete existing attachment rows during migration rather than maintaining legacy Uploadcare, ImgBB, Telegram, or WhatsApp URL refresh compatibility.
- **BREAKING**: Production deployments require S3-compatible storage configuration.

## Capabilities

### New Capabilities
- `attachment-storage-delivery`: Service-owned attachment storage, authenticated/private delivery, short-lived public delivery, outbound normalization, and retention cleanup.

### Modified Capabilities

None.

## Impact

- Affected APIs: add `/attachments/private/{id}` and `/attachments/public/{token}`.
- Affected storage: introduce S3-compatible storage for production using SeaweedFS at the configured internal endpoint and bucket `the-agent`.
- Affected configuration: add S3 access key, secret key, base URL, region, bucket, public API base URL, and public attachment token TTL defaulting to 10 minutes.
- Affected dependencies: add an S3-compatible Python client library for production storage, retain Uploadcare only where needed for fallback storage, and add a lightweight local/test storage path.
- Affected data: existing attachment rows are removed by migration; new attachment rows derive their S3 object location from persisted chat ID and stable attachment ID.
- Affected cleanup: chat-message retention cleanup deletes attachment objects before deleting corresponding database rows and parent messages.
- Affected integrations: Telegram, WhatsApp, Replicate, image generation/editing, document processing, and LLM attachment consumption route through service-owned attachment storage.
- Affected implementation workflow: tasks include mandatory manual review checkpoints after each section before continuing.
