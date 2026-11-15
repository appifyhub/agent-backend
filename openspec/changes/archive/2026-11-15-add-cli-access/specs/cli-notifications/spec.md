# Spec Delta

## Purpose

Let a command-line user send plain-text notifications to their own private chats or to chats they administer, with the same onboarding rules, authorization, billing, and delivery guarantees as other outbound agent messages.

## ADDED Requirements

### Requirement: Notifications require an onboarded owner
Both notification routes SHALL apply the agent's EULA and waitlist rules to the owner before doing anything else. An owner who is invited to start but has not accepted the policies, or who is off the waitlist and has not accepted the policies, SHALL be rejected with HTTP 403 and error code WAITLIST_INVITED_POLICIES_REQUIRED. Any other owner on the waitlist SHALL be rejected with HTTP 403 and error code WAITLIST_ACCOUNT_NOT_ACTIVE.

#### Scenario: Onboarded owner
- **WHEN** an owner who is off the waitlist and has accepted the policies sends a notification
- **THEN** the request proceeds to message validation and delivery

#### Scenario: Waitlisted owner who is not invited
- **WHEN** an owner on the waitlist who is not invited to start sends a notification
- **THEN** the response is 403 with error code WAITLIST_ACCOUNT_NOT_ACTIVE and nothing is looked up, sent, or charged

#### Scenario: Invited owner without accepted policies
- **WHEN** an owner on the waitlist who is invited to start but has not accepted the policies sends a notification
- **THEN** the response is 403 with error code WAITLIST_INVITED_POLICIES_REQUIRED

#### Scenario: Off the waitlist without accepted policies
- **WHEN** an owner who is off the waitlist but has not accepted the policies sends a notification
- **THEN** the response is 403 with error code WAITLIST_INVITED_POLICIES_REQUIRED

#### Scenario: Contradictory onboarding state
- **WHEN** an owner is on the waitlist, invited to start, and has accepted the policies
- **THEN** the response is 403 with error code WAITLIST_ACCOUNT_NOT_ACTIVE

#### Scenario: Gate comes first
- **WHEN** a not-onboarded owner sends a blank message or an unsupported platform
- **THEN** the response is the 403 onboarding error and not a validation error

#### Scenario: Both routes are gated
- **WHEN** a not-onboarded owner notifies a chat by id
- **THEN** the same 403 onboarding error is returned

### Requirement: Messages are validated before any chat lookup or delivery
A notification message SHALL be trimmed of surrounding whitespace and SHALL contain between 1 and 4096 characters after trimming. Violations SHALL be rejected with HTTP 422 and error code INVALID_NOTIFICATION_MESSAGE before any chat lookup, charge, or delivery.

#### Scenario: Trimmed message
- **WHEN** the message is `  Build finished  ` and the target is valid
- **THEN** the delivered text is `Build finished`

#### Scenario: Blank message
- **WHEN** the message is empty or contains only whitespace
- **THEN** the response is 422 with error code INVALID_NOTIFICATION_MESSAGE and nothing is sent or charged

#### Scenario: Length limits
- **WHEN** the message has exactly 4096 characters after trimming, and in another request 4097
- **THEN** the first is accepted and the second is rejected with 422 and error code INVALID_NOTIFICATION_MESSAGE

#### Scenario: Interior formatting is kept
- **WHEN** the message contains line breaks between non-blank text
- **THEN** the line breaks are delivered unchanged

### Requirement: Notifying the owner's private chat on a chosen platform
When a platform is given, the system SHALL deliver to the owner's private chat on that platform. Only `telegram` and `whatsapp` are valid platforms. If the owner has no private chat on the platform, the request SHALL fail with HTTP 403 and error code NO_PRIVATE_CHAT, with nothing sent or charged.

#### Scenario: Telegram
- **WHEN** the owner has a private Telegram chat and requests platform `telegram`
- **THEN** the message is delivered to that chat

#### Scenario: WhatsApp is attempted even outside the window heuristic
- **WHEN** the owner has a private WhatsApp chat and requests platform `whatsapp`
- **THEN** delivery is attempted and the platform's answer decides the outcome

#### Scenario: No chat on the platform
- **WHEN** the owner has no private chat on the requested platform
- **THEN** the response is 403 with error code NO_PRIVATE_CHAT

#### Scenario: Group chats do not count
- **WHEN** the only chat the owner has on the requested platform is a group
- **THEN** the response is 403 with error code NO_PRIVATE_CHAT

#### Scenario: Unsupported platform
- **WHEN** the requested platform is anything other than `telegram`, `whatsapp`, or null
- **THEN** the response is 422 with error code INVALID_PLATFORM

### Requirement: Default target is the owner's best private chat
When no platform is given, the system SHALL deliver to the owner's best private chat by the rule already used for other agent notifications: a Telegram private chat is always eligible, a WhatsApp private chat only when the owner wrote there within the last 24 hours, and when both are eligible the one the owner wrote in most recently wins. When none is eligible, the request SHALL fail without sending.

#### Scenario: Telegram only
- **WHEN** the owner has only a private Telegram chat
- **THEN** the message is delivered there

#### Scenario: Both qualify
- **WHEN** both chats qualify and the owner wrote most recently on WhatsApp
- **THEN** the message is delivered on WhatsApp

#### Scenario: Stale WhatsApp window
- **WHEN** the owner has a private Telegram chat and a WhatsApp chat last written to more than 24 hours ago
- **THEN** the message is delivered on Telegram

#### Scenario: Only a stale WhatsApp chat
- **WHEN** the owner's only private chat is a WhatsApp chat last written to more than 24 hours ago
- **THEN** the response is 403 with error code NO_PRIVATE_CHAT

#### Scenario: No private chat at all
- **WHEN** the owner has no private chat on any platform
- **THEN** the response is 403 with error code NO_PRIVATE_CHAT

#### Scenario: Null platform equals omitted platform
- **WHEN** the platform is explicitly null
- **THEN** the behavior is the same as when it is omitted

### Requirement: Notifying a chat requires admin rights
A notification addressed to a specific chat SHALL be accepted only when the platform reports the owner as owner or administrator of that chat, which includes the owner's own private chat. The system SHALL respond 404 with error code CHAT_NOT_FOUND for an unknown chat id, 422 with MALFORMED_CHAT_ID for a malformed one, 403 with NOT_CHAT_MEMBER for a non-member, and 403 with NOT_CHAT_ADMIN for a member who is not an administrator.

#### Scenario: Group administrator
- **WHEN** the owner administers a Telegram group and notifies it
- **THEN** the message is delivered to the group

#### Scenario: Own private chat by id
- **WHEN** the owner notifies their own private chat by chat id
- **THEN** the message is delivered

#### Scenario: Member but not administrator
- **WHEN** the owner is a plain member of the group
- **THEN** the response is 403 with error code NOT_CHAT_ADMIN and nothing is sent

#### Scenario: Not a member
- **WHEN** the owner has no relationship to the chat
- **THEN** the response is 403 with error code NOT_CHAT_MEMBER and nothing is sent

#### Scenario: Another user's private chat
- **WHEN** the owner notifies another user's private chat by id
- **THEN** the response is 403 with error code NOT_CHAT_MEMBER or NOT_CHAT_ADMIN and nothing is sent

#### Scenario: Unknown or malformed chat id
- **WHEN** the chat id is unknown, and in another request not a valid identifier
- **THEN** the responses are 404 with CHAT_NOT_FOUND and 422 with MALFORMED_CHAT_ID

### Requirement: Message prefix
Every notification SHALL start with `🖥️ `, so that it is recognizable as coming from a command-line client. A message delivered to a non-private chat SHALL continue with `[<identity>@<hostname>] `, naming the owner by their handle on the chat's platform (otherwise their numeric id there) and the host from the token, never from the request. A private chat gets no identity or hostname.

#### Scenario: Telegram username
- **WHEN** an owner with username `mark_johnson` and token hostname `laptop` notifies a Telegram group with `Build finished`
- **THEN** the delivered text is `🖥️ [mark_johnson@laptop] Build finished`

#### Scenario: No Telegram username
- **WHEN** the owner has no Telegram username and notifies a Telegram group
- **THEN** the prefix is `🖥️ ` followed by the numeric Telegram user id as `[<id>@laptop] `

#### Scenario: Private chat
- **WHEN** the target is a private chat
- **THEN** the delivered text is `🖥️ ` followed by the message, with no identity or hostname

#### Scenario: Forged prefix inside the message
- **WHEN** the message itself starts with a bracketed identity such as `[someone_else@host]`
- **THEN** it is delivered unchanged after the real prefix, which starts with `🖥️ `

### Requirement: Tail truncation keeps the prefix and ends with an ellipsis
When the prefixed message exceeds the platform's text limit, measured the way other agent messages are measured on that platform, the system SHALL cut the end of the message, append the ellipsis `…`, and keep the complete prefix, so that the final text fits within the limit.

#### Scenario: Fits as is
- **WHEN** prefix plus message is within the limit
- **THEN** the message is delivered unchanged and without an ellipsis

#### Scenario: Exactly at the limit
- **WHEN** prefix plus message is exactly as long as the limit
- **THEN** the message is delivered unchanged and without an ellipsis

#### Scenario: Group message at the maximum length
- **WHEN** a 4096-character message is sent to a group
- **THEN** the delivered text starts with the complete prefix, keeps the start of the message, ends with `…`, and is no longer than 4096 characters

#### Scenario: Truncated text ends with an ellipsis
- **WHEN** a message is truncated
- **THEN** the delivered text ends with `…` immediately after the last kept character of the message, with no whitespace before it

#### Scenario: Private chat at the maximum length
- **WHEN** a 4096-character message is sent to a private chat
- **THEN** it is delivered with the `🖥️ ` prefix, cut at the end with `…`, and fits within the limit

### Requirement: Delivery is billed like other outbound messages
Before delivery the owner SHALL have enough credits for one complete message to the target chat; otherwise the request SHALL fail with HTTP 422 and error code INSUFFICIENT_CREDITS, with nothing sent or stored. After the platform accepts the message the owner SHALL be charged per recipient exactly as for other agent messages. A rejected delivery SHALL NOT be charged.

#### Scenario: Paid delivery
- **WHEN** the owner has enough credits and notifies a private WhatsApp chat
- **THEN** the message is delivered and the owner is charged the configured delivery price with a usage record

#### Scenario: Insufficient credits
- **WHEN** the owner cannot fund one complete message
- **THEN** the response is 422 with error code INSUFFICIENT_CREDITS, nothing is sent, and the balance is unchanged

#### Scenario: Free delivery
- **WHEN** the platform's configured delivery price is zero
- **THEN** the message is delivered and the balance is unchanged

#### Scenario: Group recipients are covered
- **WHEN** the target is a group with several members
- **THEN** the credit check covers every non-agent member as for other group messages

#### Scenario: Rejected delivery
- **WHEN** the platform rejects the message
- **THEN** the owner is not charged and no message is recorded

### Requirement: Delivery failures are reported
The system SHALL report any platform failure while delivering (a refusal, an outage, or a timeout) as HTTP 502 with error code NOTIFICATION_DELIVERY_FAILED.

#### Scenario: Platform refusal, outage, or timeout
- **WHEN** the platform refuses the delivery, fails with a server error, or the request times out
- **THEN** the response is 502 with error code NOTIFICATION_DELIVERY_FAILED

#### Scenario: Failures leave no trace
- **WHEN** any delivery failure occurs
- **THEN** no message is recorded in the chat and the owner is not charged

### Requirement: Success identifies the chat, reports the balance, and is recorded
A successful notification SHALL respond with the chat that received the message as chat id (32-character hex), platform, title (possibly null), and private flag, plus the owner's credit balance after charging. The delivered message SHALL appear in that chat as a message from the agent and SHALL be recorded in the chat's history like other agent messages.

#### Scenario: Explicit target
- **WHEN** a notification to a chat succeeds
- **THEN** the response is 200 with that chat's `chat_id`, `platform`, `title`, and `is_private`, and the owner's `credit_balance`

#### Scenario: Resolved target
- **WHEN** a notification without a platform succeeds
- **THEN** the response identifies the chat that was actually chosen

#### Scenario: Balance after a paid delivery
- **WHEN** a paid delivery succeeds
- **THEN** `credit_balance` equals the owner's balance before the request minus the delivery charge

#### Scenario: Balance after a free delivery
- **WHEN** a delivery with a zero price succeeds
- **THEN** `credit_balance` equals the owner's balance before the request

#### Scenario: History
- **WHEN** a notification is delivered
- **THEN** the chat history contains it as an agent-authored message
