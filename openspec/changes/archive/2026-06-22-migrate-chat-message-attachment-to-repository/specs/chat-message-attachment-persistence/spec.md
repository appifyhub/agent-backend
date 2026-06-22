## ADDED Requirements

### Requirement: Attachment states distinguish remote data from complete domain state
The system SHALL represent pre-resolution platform attachment data separately from complete chat-message attachment domain state.

#### Scenario: Platform mapper creates remote attachment data
- **WHEN** Telegram or WhatsApp maps an attachment before the chat configuration is persisted or resolved
- **THEN** it produces remote attachment data without internal attachment or chat IDs
- **THEN** it preserves the external ID, message ID, and available metadata

#### Scenario: Resolver creates complete domain state
- **WHEN** chat resolution provides the internal chat UUID for new remote attachment data
- **THEN** the resolver produces a complete domain attachment with a required `chat_id`
- **THEN** only complete domain state is passed to platform refresh and repository persistence

#### Scenario: Complete domain state reports stale cache data
- **WHEN** an attachment has no cached URL or its URL expiration is at or before the current timestamp
- **THEN** its stale-data property evaluates to true
- **WHEN** it has a URL whose expiration is after the current timestamp
- **THEN** its stale-data property evaluates to false

### Requirement: Attachment identity follows ChatConfig-style persistence ownership
The system SHALL allow unsaved complete domain attachments to omit their internal ID and SHALL populate the ID during persistence using the existing short-ID generator.

#### Scenario: Repository generates omitted attachment ID
- **WHEN** a complete domain attachment with `id = None` is inserted
- **THEN** the SQLAlchemy model generates a short attachment ID through its Python-side default
- **THEN** the repository returns the persisted domain attachment with that generated ID

#### Scenario: Platform deterministic ID is preserved
- **WHEN** platform remote data supplies an external ID
- **THEN** conversion derives the deterministic internal attachment ID from that external ID
- **THEN** message-text formatting and persistence use the same derived ID

#### Scenario: Existing ID identifies an update
- **WHEN** repository save receives a complete attachment whose non-null ID already exists
- **THEN** it updates that row rather than generating another identity

### Requirement: Attachment repository returns domain state
The system SHALL expose attachment persistence operations through a repository that returns complete domain attachments rather than SQLAlchemy rows.

#### Scenario: Fetch existing attachment by ID
- **WHEN** an attachment exists for the supplied internal ID
- **THEN** repository lookup returns all persisted fields as complete domain state

#### Scenario: Fetch missing attachment by ID
- **WHEN** no attachment exists for the supplied internal ID
- **THEN** repository lookup returns `None`

#### Scenario: Fetch by external ID preserves first-match behavior
- **WHEN** repository lookup uses an external platform ID
- **THEN** it returns the first matching attachment or `None`
- **THEN** it does not introduce a uniqueness requirement

#### Scenario: Fetch attachments for a message
- **WHEN** attachments exist for multiple chat-message pairs
- **THEN** message-scoped lookup returns only attachments matching the supplied chat ID and message ID

#### Scenario: Fetch all attachments applies pagination
- **WHEN** a caller supplies skip and limit values
- **THEN** repository collection lookup returns the corresponding page of domain attachments

### Requirement: Attachment save preserves complete-state semantics
The system SHALL insert or update complete attachment domain state by internal attachment ID.

#### Scenario: Save inserts missing attachment
- **WHEN** repository save receives an attachment whose supplied ID does not exist, or whose ID is omitted
- **THEN** it inserts every complete domain field
- **THEN** it returns the committed and refreshed domain snapshot

#### Scenario: Save replaces existing attachment state
- **WHEN** repository save receives an attachment whose non-null ID exists
- **THEN** it preserves the existing internal ID
- **THEN** it replaces external ID, chat ID, message ID, size, URL, URL expiration, extension, and MIME type with supplied state

### Requirement: Remote attachment merging preserves existing identity and cached metadata
The system SHALL merge platform remote data into existing domain attachments using the current resolver behavior.

#### Scenario: Existing attachment preserves internal identity
- **WHEN** remote data matches an existing attachment by external ID
- **THEN** the merge preserves the existing attachment ID and chat ID
- **THEN** it applies the incoming external ID and message ID

#### Scenario: Truthy remote metadata updates existing state
- **WHEN** incoming size, URL, URL expiration, extension, or MIME type is truthy
- **THEN** that incoming value replaces the corresponding existing value

#### Scenario: Empty remote metadata preserves existing state
- **WHEN** incoming size, URL, URL expiration, extension, or MIME type is absent or otherwise falsey
- **THEN** the corresponding existing value remains unchanged

### Requirement: Platform refresh operates on complete domain attachments
The system SHALL refresh Telegram and WhatsApp attachment metadata using complete domain attachments and persist refreshed snapshots through the repository.

#### Scenario: Fresh attachment avoids remote metadata fetch
- **WHEN** a complete attachment has non-stale URL data
- **THEN** platform refresh preserves the data and saves the complete attachment without fetching remote metadata

#### Scenario: Stale attachment refreshes available metadata
- **WHEN** attachment URL data is stale and an external ID is present
- **THEN** the platform SDK fetches remote metadata
- **THEN** it updates only metadata learned from the platform or media content
- **THEN** it saves and returns complete domain state

#### Scenario: Stale attachment lacks external ID
- **WHEN** stale attachment data has no external ID
- **THEN** platform refresh raises the existing structured missing-external-ID error

#### Scenario: WhatsApp re-upload persists permanent URL state
- **WHEN** WhatsApp media is downloaded and successfully re-uploaded
- **THEN** the complete attachment receives the uploaded URL and expiration
- **THEN** repository persistence returns the updated domain state

### Requirement: Attachment deletion and cleanup behavior is preserved
The system SHALL preserve targeted attachment deletion and old-message attachment cleanup through the repository.

#### Scenario: Delete existing attachment
- **WHEN** repository deletion targets an existing attachment ID
- **THEN** it removes the row and returns the deleted domain snapshot

#### Scenario: Delete missing attachment
- **WHEN** repository deletion targets a missing attachment ID
- **THEN** it returns `None`

#### Scenario: Delete attachments for old messages
- **WHEN** cleanup uses a message cutoff timestamp
- **THEN** it deletes attachments belonging to messages whose `sent_at` is earlier than the cutoff
- **THEN** it keeps attachments for messages at or after the cutoff
- **THEN** it returns the number of deleted rows

#### Scenario: Cleanup preserves phase ordering
- **WHEN** scheduled cleanup removes old chat data
- **THEN** it deletes old-message attachments before deleting their parent messages

### Requirement: Production attachment consumers use domain and repository types
The system SHALL migrate attachment consumers from legacy CRUD/schema types without changing externally visible behavior.

#### Scenario: Chat and platform consumers use domain attachments
- **WHEN** chat history, attachment processing, image editing, URL resolution, platform integration, Telegram, or WhatsApp handles attachments
- **THEN** complete attachments cross those boundaries as feature-level domain objects
- **THEN** SQLAlchemy rows and legacy Pydantic persistence schemas do not escape persistence

#### Scenario: Legacy persistence types are removed after migration
- **WHEN** no production or test code references attachment CRUD access, `ChatMessageAttachmentCRUD`, `ChatMessageAttachmentSave`, or the legacy attachment schema
- **THEN** the legacy DI access, CRUD/schema files, SQL helper, and obsolete tests are removed

#### Scenario: External behavior remains unchanged
- **WHEN** the migration is complete
- **THEN** attachment IDs, platform mapping, URL refresh, media detection, LLM-tool inputs, media processing, cleanup counts, and API/OpenAPI behavior remain compatible
