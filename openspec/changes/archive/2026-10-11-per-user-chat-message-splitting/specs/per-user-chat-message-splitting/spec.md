## Purpose

Allow each user to choose whether replies in a particular chat are split into separate paragraph messages, reducing unnecessary billable deliveries while preserving text and provider limits.

## ADDED Requirements

### Requirement: Durable user–chat preference

The system SHALL persist a boolean `split_messages` preference independently for each user–chat membership. Saving or refreshing unrelated membership settings SHALL preserve the stored preference.

#### Scenario: Persist an explicit disabled choice
- **WHEN** a user disables splitting in a chat and the settings are subsequently reloaded
- **THEN** the preference is false for that membership

#### Scenario: Persist an explicit enabled choice
- **WHEN** a user enables splitting in a chat and the settings are subsequently reloaded
- **THEN** the preference is true for that membership

#### Scenario: Membership isolation
- **WHEN** a user changes splitting in one chat
- **THEN** that user's preferences in other chats and other users' preferences in the same chat remain unchanged

#### Scenario: Administrative status changes
- **WHEN** membership synchronization changes the user's admin status
- **THEN** the stored splitting preference remains unchanged

### Requirement: Platform defaults

The system SHALL default splitting to true for new Telegram memberships and false for new WhatsApp, GitHub, and background memberships. Integration default changes SHALL NOT overwrite existing memberships or alter the original migration backfill. Subsequent membership refreshes SHALL NOT replace an explicit stored choice with a platform default.

#### Scenario: New WhatsApp membership
- **WHEN** a WhatsApp user–chat membership is created without an explicit choice
- **THEN** splitting is false

#### Scenario: New Telegram membership
- **WHEN** a Telegram user–chat membership is created without an explicit choice
- **THEN** splitting is true

#### Scenario: New GitHub or background membership
- **WHEN** a GitHub or background user–chat membership is created without an explicit choice
- **THEN** splitting is false

#### Scenario: Original migration backfill
- **WHEN** the reviewed introduction migration is applied to existing memberships
- **THEN** existing WhatsApp memberships have false and other memberships have true

#### Scenario: No membership is available during delivery
- **WHEN** a reply is delivered without a stored preference for the triggering user and chat
- **THEN** the same platform default applies without introducing a new user setting

### Requirement: Per-chat settings API

The existing per-chat user-settings API SHALL return `split_messages` as a boolean and accept it as a required boolean in user-chat settings saves. An authorized member SHALL be able to edit their own preference without chat-admin rights, under the existing authorization rules.

#### Scenario: Read saved preference
- **WHEN** an authorized member fetches their settings for a chat
- **THEN** the response includes their persisted splitting preference

#### Scenario: Non-admin member saves preference
- **WHEN** an authorized non-admin member submits a valid per-chat user-settings payload with splitting disabled
- **THEN** their preference is saved without modifying chat-wide settings or another member's preference

#### Scenario: Invalid or missing preference
- **WHEN** a user-chat settings payload omits the required splitting preference or supplies a value rejected by the existing boolean validation rules
- **THEN** the API rejects the payload through its normal validation response

### Requirement: Preference controls reply paragraph splitting

The system SHALL use the triggering user's preference for normal text replies, command text replies, and burst-level error text replies in that chat. When enabled, blank-line delimiter splitting SHALL retain the current code-block and consecutive-list preservation behavior. When disabled, blank lines SHALL remain paragraph formatting inside one logical text message. Emoji-reaction replies and independently sent media or notifications SHALL retain their existing behavior.

#### Scenario: Enabled paragraph splitting
- **WHEN** splitting is enabled and a reply contains three ordinary paragraphs separated by blank lines, each within provider limits
- **THEN** the reply is sent as three text messages in paragraph order

#### Scenario: Disabled paragraph splitting
- **WHEN** splitting is disabled and the same reply fits within the provider limit
- **THEN** it is sent as one text message containing all three paragraphs and their blank lines

#### Scenario: Formatting remains intact
- **WHEN** a reply contains a code block or consecutive list items separated by blank lines and fits within applicable limits
- **THEN** disabling splitting preserves the full formatted text and enabling splitting does not split inside those preserved blocks

#### Scenario: Group reply ownership
- **WHEN** members of a group have different splitting preferences and one member triggers a reply
- **THEN** that reply uses the triggering member's preference

#### Scenario: Command and error replies
- **WHEN** a command reply or a burst-level error reply contains blank-line-separated text
- **THEN** the triggering user's splitting preference determines optional paragraph splitting

### Requirement: Provider size limits remain mandatory

Both preference values SHALL respect the text-size limit of the destination provider. The system SHALL split oversized text only as needed to meet that limit, preserve content order without truncation, and retain valid code-fence formatting across required splits.

#### Scenario: Disabled splitting at the limit
- **WHEN** splitting is disabled and the full reply is exactly at the provider's text limit
- **THEN** it is sent as one text message

#### Scenario: Disabled splitting exceeds the limit
- **WHEN** splitting is disabled and the full reply exceeds the provider's text limit
- **THEN** it is sent in the required number of size-bounded messages without discarding text

#### Scenario: One oversized block
- **WHEN** a single paragraph, code block, or uninterrupted span exceeds the provider limit
- **THEN** it is divided into valid size-bounded messages with its visible content preserved in order

#### Scenario: Unicode and formatting boundaries
- **WHEN** a reply near the provider limit contains Unicode characters or formatting markup
- **THEN** each outgoing message conforms to that provider's counting/formatting rules without corrupting characters

### Requirement: Settings checkbox

The settings frontend SHALL show a per-user/per-chat checkbox labelled “Natural chat flow”, initialized from the backend's saved value. Saving and reloading SHALL preserve the selected value. Its helper text SHALL explain that, when enabled, the agent will send several shorter messages in quick succession instead of one long reply and that this may increase delivery costs on platforms that charge per message.

#### Scenario: Load WhatsApp settings
- **WHEN** a user opens settings for a WhatsApp membership with its initial default
- **THEN** the checkbox is unchecked

#### Scenario: Load Telegram settings
- **WHEN** a user opens settings for a Telegram membership with its initial default
- **THEN** the checkbox is checked

#### Scenario: Save the checkbox
- **WHEN** an authorized member changes the checkbox and saves their settings
- **THEN** dirty-state detection and the displayed value follow the same save behavior as existing per-chat user settings
