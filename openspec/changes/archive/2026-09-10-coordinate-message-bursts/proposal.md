## Why

Concurrent webhook handlers currently make independent timing and history decisions for messages that may belong to one logical user burst. Across multiple service instances, this can drop the intended final response, answer an earlier fragment, or process incomplete photo-and-prompt context.

## What Changes

- Group non-command messages into bursts per chat and author using a 1 second quiet period.
- Persist the active burst deadline and message count in the shared database so all service instances make one coordinated processing decision.
- Schedule non-blocking asynchronous wake-ups without retaining a database session or transaction during the quiet period.
- Atomically allow only the wake-up matching the current settled message count to claim processing.
- In group chats, reply once when any message in the settled burst addressed the bot; bursts from different authors remain independent.
- In private chats, treat every settled burst as addressed to the bot and reply once using all messages through the burst cutoff.
- Keep commands outside burst processing so they receive an immediate response.
- Remove the existing per-message sleep-and-supersession behavior.

## Capabilities

### New Capabilities

- `message-burst-processing`: Defines quiet-period burst formation, cross-instance claiming, command bypass, reply eligibility, context boundaries, and resource-release behavior.

### Modified Capabilities

None.

## Impact

- Affects Telegram and WhatsApp inbound message handling, chat-agent invocation, chat-history loading, dependency injection, configuration, and database models/repositories.
- Requires a database migration for shared burst coordination and deterministic message cutoff data.
- Changes non-command reply timing to begin after 1 second without a message from the same author in the same chat.
- Does not add automatic retry or continuous recovery processing; outstanding work remains visible in the database.
