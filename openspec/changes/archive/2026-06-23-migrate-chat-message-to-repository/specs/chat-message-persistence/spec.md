## ADDED Requirements

### Requirement: Message states distinguish remote data from complete domain state
The system SHALL represent pre-resolution platform message data separately from complete chat-message domain state.

#### Scenario: Platform mapper creates remote message data
- **WHEN** Telegram or WhatsApp maps an incoming platform message before chat and author resolution
- **THEN** it produces remote message data without internal chat or author IDs
- **THEN** it preserves the platform message ID, timestamp, and text

#### Scenario: Resolver creates complete domain state
- **WHEN** chat resolution supplies the internal chat UUID and user resolution optionally supplies an author UUID
- **THEN** the resolver produces a complete domain message with a required `chat_id`
- **THEN** only complete domain state is passed to repository persistence and post-resolution consumers

### Requirement: Omitted message timestamps use construction time
The system SHALL generate an omitted complete-domain message timestamp when each message object is constructed.

#### Scenario: Two messages omit their timestamps
- **WHEN** complete messages are constructed at different times without explicit `sent_at` values
- **THEN** each message receives its own construction-time timestamp
- **THEN** neither timestamp is derived from schema module import time

#### Scenario: Platform timestamp is explicit
- **WHEN** Telegram or WhatsApp maps a platform message
- **THEN** remote message data uses the timestamp supplied by that platform

### Requirement: Message repository uses composite identity and returns domain state
The system SHALL identify persisted messages by `(chat_id, message_id)` and return complete domain messages rather than SQLAlchemy rows.

#### Scenario: Fetch existing message
- **WHEN** a message exists for the supplied chat ID and message ID
- **THEN** repository lookup returns all persisted fields as complete domain state

#### Scenario: Fetch missing message
- **WHEN** no message exists for the supplied composite identity
- **THEN** repository lookup returns `None`

#### Scenario: Fetch all messages applies pagination
- **WHEN** a caller supplies skip and limit values
- **THEN** repository collection lookup returns the corresponding page of domain messages

#### Scenario: Fetch latest messages for one chat
- **WHEN** messages exist across multiple chats and timestamps
- **THEN** latest-message lookup returns only messages for the supplied chat
- **THEN** it orders them by descending `sent_at` and applies skip and limit

### Requirement: Message save preserves complete-state semantics
The system SHALL insert or update complete message domain state using its composite identity.

#### Scenario: Save inserts missing message
- **WHEN** repository save receives a complete message whose composite identity does not exist
- **THEN** it inserts chat ID, message ID, author ID, timestamp, and encrypted text
- **THEN** it returns the committed and refreshed domain snapshot

#### Scenario: Save replaces existing message state
- **WHEN** repository save receives a complete message whose composite identity exists
- **THEN** it preserves that composite identity
- **THEN** it replaces author ID, timestamp, and text with the supplied complete state

#### Scenario: Save replacement is verified independently
- **WHEN** replacement behavior is tested
- **THEN** pre-update values are captured independently from the mutable SQLAlchemy row
- **THEN** the test detects author, timestamp, or text changes rather than comparing one mutated object to itself

### Requirement: Persistence mappers own existing-row field application
The system SHALL apply complete domain state to existing tracked SQLAlchemy rows through feature persistence mappers rather than private repository field-copy helpers.

This requirement applies to chat messages, chat-message attachments, chat configurations, tools cache entries, sponsorships, and price alerts.

#### Scenario: Repository updates an existing row
- **WHEN** a repository locates an existing SQLAlchemy row for supplied complete domain state
- **THEN** it delegates mutable persisted-field application to `apply_to_db_model(domain_model, db_model)` in the corresponding mapper
- **THEN** the repository remains responsible for commit, refresh, and domain conversion

#### Scenario: Mapper preserves persistence identity
- **WHEN** domain state contains identity values that differ from the tracked row
- **THEN** `apply_to_db_model` preserves identity fields owned by that tracked row
- **THEN** it applies every mutable persisted field

#### Scenario: Mapper clears nullable state
- **WHEN** a nullable mutable domain field is explicitly `None`
- **THEN** `apply_to_db_model` assigns `None` to the corresponding database field

#### Scenario: New-row conversion remains separate
- **WHEN** a repository inserts domain state whose identity does not already exist
- **THEN** it uses `db(domain_model)` to construct a new SQLAlchemy row
- **THEN** existing-row updates do not replace the tracked row with a new transient SQLAlchemy object

#### Scenario: Mapper ownership is verified consistently
- **WHEN** mapper behavior is tested for each affected persistence feature
- **THEN** tests verify mutable-field application, nullable clearing where supported, and identity preservation

### Requirement: Remote message merging preserves identity and edit behavior
The system SHALL merge remote platform data into existing domain messages before repository persistence.

#### Scenario: Existing message preserves composite identity
- **WHEN** remote data matches an existing message by chat ID and message ID
- **THEN** the merge preserves the existing chat ID and message ID

#### Scenario: Resolved author updates message author
- **WHEN** an internal author UUID resolves for incoming remote data
- **THEN** that author UUID replaces the existing author value

#### Scenario: Missing resolved author preserves message author
- **WHEN** no internal author UUID resolves for incoming remote data
- **THEN** the existing non-null author UUID is preserved

#### Scenario: Edited platform message updates snapshot fields
- **WHEN** remote data for an existing message contains a platform timestamp and text
- **THEN** the incoming timestamp and text replace the existing values

### Requirement: Platform and chat consumers use complete domain messages
The system SHALL use complete message domain state across post-resolution chat and platform boundaries.

#### Scenario: Chat history uses repository results
- **WHEN** chat agent or integration logic reads recent messages
- **THEN** it receives domain messages ordered and paginated by the repository
- **THEN** no SQLAlchemy-to-Pydantic conversion occurs in the consumer

#### Scenario: Platform SDK returns stored domain message
- **WHEN** Telegram or WhatsApp successfully sends text, photo, document, or button content
- **THEN** the send path persists the resulting complete message through the repository
- **THEN** the SDK and shared platform SDK return complete domain state

#### Scenario: Reaction response is persisted
- **WHEN** a responder emits a reaction response
- **THEN** it saves a complete domain message with the current chat, agent author, reaction identity, timestamp, and formatted reaction text

#### Scenario: WhatsApp reply resolves stored text
- **WHEN** a WhatsApp message replies to a known stored message
- **THEN** the resolver reads that message through the repository
- **THEN** it preserves existing reply-quote formatting behavior

### Requirement: Message deletion and cleanup behavior is preserved
The system SHALL preserve targeted message deletion and retention cleanup through the repository.

#### Scenario: Delete existing message
- **WHEN** repository deletion targets an existing composite identity
- **THEN** it removes the row and returns the deleted domain snapshot

#### Scenario: Delete missing message
- **WHEN** repository deletion targets a missing composite identity
- **THEN** it returns `None`

#### Scenario: Delete messages older than cutoff
- **WHEN** cleanup uses a retention cutoff timestamp
- **THEN** it deletes messages whose `sent_at` is earlier than the cutoff
- **THEN** it keeps messages at or after the cutoff and returns the deleted-row count

#### Scenario: Cleanup preserves attachment ordering
- **WHEN** scheduled cleanup removes old chat data
- **THEN** it deletes old-message attachments before deleting their parent messages through the message repository

### Requirement: Legacy message persistence types are removed after migration
The system SHALL remove legacy message CRUD and persistence schemas only after every production and test consumer uses domain and repository types.

#### Scenario: Legacy references are absent
- **WHEN** migration is ready for legacy deletion
- **THEN** no production or test code references message CRUD access, `ChatMessageCRUD`, `ChatMessageSave`, the legacy message schema, or `ChatMessage.model_validate`

#### Scenario: Database representation remains intentional
- **WHEN** legacy persistence types are removed
- **THEN** `ChatMessageDB` remains referenced only by database model registration, message mapper/repository code, and focused persistence tests

#### Scenario: External behavior remains compatible
- **WHEN** the migration is complete
- **THEN** platform message IDs, text encryption, message edits, sends, replies, reactions, history ordering, pagination, attachments, retention counts, routes, and OpenAPI behavior remain compatible except for corrected omitted-timestamp initialization
