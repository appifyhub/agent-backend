## ADDED Requirements

### Requirement: Attachments are stored in service-owned storage
The system SHALL store new retained attachments in service-owned attachment storage before using them for retained chat state, attachment processing, or outbound delivery.

#### Scenario: Inbound platform attachment is normalized
- **WHEN** a Telegram or WhatsApp message contains an attachment that the service will retain
- **THEN** the system downloads the platform media once
- **THEN** the system stores the bytes in service-owned attachment storage
- **THEN** the persisted attachment metadata can be used to derive the storage object key

#### Scenario: Generated or local outbound attachment is normalized
- **WHEN** the service is about to send or retain media from local disk, generated output, or Replicate output
- **THEN** the system stores the bytes in service-owned attachment storage before producing a delivery URL or sending it externally

#### Scenario: URL-supplied attachment is normalized
- **WHEN** the service receives a URL-supplied attachment that it will retain or process
- **AND** the caller supplies attachment metadata with the target chat ID
- **THEN** the system downloads the URL bytes once
- **THEN** the download can use either a caller-supplied downloader that returns attachment content metadata or the default web headers
- **THEN** the system resolves only supported attachment MIME/extension metadata from the response MIME, URI, and bytes
- **THEN** the system generates a local attachment ID instead of deriving the ID from the URL
- **THEN** the system stores the bytes in service-owned attachment storage before returning the attachment for processing

#### Scenario: Internal URL-supplied attachment resolves existing attachment
- **WHEN** the service receives an own public attachment URL, own private attachment URL, or own storage URI without replacement bytes
- **THEN** the system resolves the referenced existing attachment
- **THEN** the system does not create a duplicate attachment row
- **THEN** the system does not write duplicate bytes to storage

#### Scenario: Existing attachment argument is accepted
- **WHEN** an attachment service function receives a `ChatAttachment` instance
- **THEN** the system uses that instance directly
- **AND** when an attachment service function receives an attachment ID
- **THEN** the system resolves the attachment through the repository

#### Scenario: Temporary message is excluded from history
- **WHEN** the system persists a temporary outgoing message row for outbound attachment delivery
- **THEN** the row records that it is temporary
- **THEN** normal latest-by-chat history excludes the row by default

### Requirement: Storage object identity is derived from chat attachment metadata
The system SHALL derive the storage object location from the configured bucket, the attachment's chat ID, and the attachment's stable local ID.

#### Scenario: Derive storage object key
- **WHEN** an attachment has chat ID `chat-id` and attachment ID `attachment-id`
- **THEN** the system derives the object key `chats/chat-id/attachments/attachment-id`
- **THEN** no separate object-key database column is required

#### Scenario: Derive storage object key with extension
- **WHEN** an attachment has chat ID `chat-id`, attachment ID `attachment-id`, and extension `png`
- **THEN** the system derives the object key `chats/chat-id/attachments/attachment-id.png`
- **THEN** the attachment extension is treated as finalized for storage identity before upload

#### Scenario: Attachment row can exist without message ownership
- **WHEN** an attachment belongs to chat `chat-id`
- **THEN** the attachment may have no message ID
- **THEN** the storage object identity remains stable

#### Scenario: Attachment ID exists before upload
- **WHEN** the system uploads bytes for a new attachment
- **THEN** the attachment ID exists before storage writes the object
- **THEN** the same upload metadata can derive the object key for the storage write

#### Scenario: Inbound platform attachment ID is deterministic
- **WHEN** the system receives an inbound platform attachment with external ID `external-id`
- **THEN** it derives the local attachment ID deterministically from `external-id`
- **THEN** repeated platform updates resolve to the same local attachment row

#### Scenario: External attachment identity is chat-scoped
- **WHEN** the system persists a platform-backed attachment with external ID `external-id`
- **THEN** the database enforces that `external-id` is unique within the attachment's chat
- **THEN** another chat may use the same `external-id` without violating attachment metadata uniqueness

#### Scenario: Attachment uploader is retained
- **WHEN** the system persists an attachment row
- **THEN** the row records the internal user ID that created or uploaded the attachment
- **THEN** attachment persistence fails before storage if no uploader can be resolved

### Requirement: Production storage uses configured S3-compatible storage
The system SHALL use configured S3-compatible storage for production attachment storage.

#### Scenario: S3 configuration is loaded
- **WHEN** the service starts in production mode
- **THEN** it loads S3 access key, secret key, base URL, region, and bucket configuration
- **THEN** the default bucket is `the-agent`
- **THEN** the default region is an EU region

#### Scenario: Configured bucket exists
- **WHEN** the production storage adapter starts or first uses storage
- **THEN** it ensures the single configured bucket exists idempotently
- **THEN** it does not create buckets per chat

#### Scenario: Cluster SeaweedFS endpoint is configured
- **WHEN** the cluster environment provides the S3 base URL
- **THEN** the service connects to the configured endpoint without exposing SeaweedFS directly to public clients

### Requirement: Non-S3 environments use configured fallback storage
The system SHALL support local development and non-S3 runs without requiring Docker-managed S3 startup from `main.py`.

#### Scenario: Uploadcare fallback is configured
- **WHEN** S3 configuration is absent
- **AND** Uploadcare configuration is present
- **THEN** the system uses Uploadcare-backed attachment storage
- **THEN** retained attachment reads and deletes use the same storage interface as production

#### Scenario: Dev run stores attachments locally
- **WHEN** the service runs without S3 configuration
- **AND** Uploadcare configuration is absent
- **THEN** the system uses a local attachment storage adapter
- **THEN** attachment reads and deletes use the same storage interface as production

#### Scenario: Local cleanup deletes local files
- **WHEN** cleanup deletes old retained attachments in local development
- **THEN** the system deletes the corresponding local files before deleting attachment rows

### Requirement: Private attachment endpoint enforces chat membership
The system SHALL expose `GET /attachments/private/{id}` for authenticated attachment reads.

#### Scenario: Chat member reads attachment privately
- **WHEN** a request to `/attachments/private/{id}` includes a valid bearer JWT for a user who belongs to the attachment's chat
- **THEN** the system streams the attachment bytes from storage
- **THEN** the response uses the attachment MIME type when available

#### Scenario: Non-member cannot read attachment privately
- **WHEN** a request to `/attachments/private/{id}` includes a valid bearer JWT for a user who does not belong to the attachment's chat
- **THEN** the system rejects the request without returning attachment bytes

#### Scenario: Unauthenticated private request is rejected
- **WHEN** a request to `/attachments/private/{id}` does not include a valid bearer JWT
- **THEN** the system rejects the request without returning attachment bytes

### Requirement: Public attachment endpoint uses short-lived tokens
The system SHALL expose `GET /attachments/public/{token}` for short-lived unauthenticated attachment reads.

#### Scenario: Valid public token reads attachment
- **WHEN** a request to `/attachments/public/{token}` includes a valid attachment token that has not expired
- **THEN** the system streams the referenced attachment bytes from storage

#### Scenario: Expired public token is rejected
- **WHEN** a request to `/attachments/public/{token}` includes an expired attachment-read token
- **THEN** the system rejects the request without returning attachment bytes

#### Scenario: Public token TTL uses configured value
- **WHEN** the system creates a public attachment token
- **THEN** the token expiration uses the configured public attachment token TTL

#### Scenario: Public token keeps chat context for debugging
- **WHEN** the system creates a public attachment token
- **THEN** the token includes the attachment chat ID for debugging context
- **THEN** public attachment reads resolve the attachment by the signed attachment ID

### Requirement: External consumers receive public attachment URLs
The system SHALL provide short-lived public attachment URLs for consumers that cannot send authorization headers.

#### Scenario: HTML image rendering uses public URL
- **WHEN** the frontend needs to render an attachment in an HTML image element without custom headers
- **THEN** the system supplies a `/attachments/public/{token}` URL

#### Scenario: External service receives public URL
- **WHEN** Telegram, WhatsApp, Replicate, or another external service requires a URL to fetch an attachment
- **THEN** the system supplies a `/attachments/public/{token}` URL using the configured public attachment token TTL

### Requirement: Attachment processors read from service-owned storage
The system SHALL process retained attachments from service-owned storage rather than platform refresh URLs.

#### Scenario: Chat attachment processor reads storage bytes
- **WHEN** the chat attachment processor needs attachment bytes
- **THEN** it reads the attachment from service-owned storage using the derived object key

#### Scenario: URL attachment processor uses normalized storage
- **WHEN** the chat attachment processor receives a URL-supplied attachment input
- **THEN** it obtains a storage-backed attachment from the attachment service before processing
- **THEN** it does not process retained URL attachments directly from the original external URL

#### Scenario: Image edit flow uses storage-backed access
- **WHEN** the image edit flow needs image attachment inputs
- **THEN** it uses storage-backed bytes or short-lived public attachment URLs generated by the service

### Requirement: Cleanup deletes attachment objects and rows with retry tolerance
The system SHALL clean up attachment object bytes, attachment rows, and message rows independently while allowing later cleanup runs to remove anything left behind by a partial failure.

#### Scenario: Old attachment cleanup succeeds
- **WHEN** cleanup finds attachments whose parent messages are older than the message retention cutoff
- **THEN** it deletes the corresponding storage objects
- **THEN** it deletes the attachment rows
- **THEN** it deletes the old parent message rows

#### Scenario: Missing object does not block cleanup
- **WHEN** cleanup tries to delete an old attachment object that is already missing
- **THEN** it logs the missing object
- **THEN** it continues deleting the attachment row

#### Scenario: Storage delete failure is retryable
- **WHEN** cleanup fails to delete an old attachment object because storage is unavailable or returns an unexpected error
- **THEN** it logs the failure
- **THEN** a later cleanup run can retry deleting either the object or any remaining rows

#### Scenario: Obsolete attachment cleanup is explicit
- **WHEN** cleanup has an explicit rule for an obsolete attachment row
- **THEN** its storage object and row can be deleted independently
- **THEN** partial cleanup success does not prevent later cleanup from deleting the remaining object or row

#### Scenario: Orphaned storage object cleanup succeeds
- **WHEN** cleanup finds an attachment storage object whose attachment row is missing
- **THEN** it deletes the orphaned object

### Requirement: Existing attachment rows are removed by migration
The system SHALL remove existing attachment rows during deployment migration instead of preserving legacy external URLs.

#### Scenario: Migration removes legacy attachments
- **WHEN** the migration for this change runs
- **THEN** existing rows in `chat_attachments` are deleted
- **THEN** the service does not need to refresh or preserve legacy Uploadcare, ImgBB, Telegram, or WhatsApp attachment URLs

### Requirement: New logs avoid full attachment delivery URLs
The system SHALL avoid logging full private or public attachment delivery URLs.

#### Scenario: Public URL is generated
- **WHEN** the system generates a public attachment URL
- **THEN** logs do not include the full URL or token
- **THEN** logs can include shortened identifiers such as attachment ID, chat ID, or final path segments

#### Scenario: Storage operation is logged
- **WHEN** the system logs an attachment storage operation
- **THEN** logs identify the object without printing a full public delivery URL
