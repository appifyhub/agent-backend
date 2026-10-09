## Purpose

Make delivery affordability and accepted outbound costs visible in existing credit balances and usage while using the reviewed sequential recipient reconciliation model.

## ADDED Requirements

### Requirement: One-message delivery preflight
Before model work or a direct outbound provider submission, the system SHALL require the payer to have enough credits for one complete outbound message. The required amount SHALL be the sum of configured prices for every non-agent chat member, including the payer when the payer is an outbound recipient. The check SHALL run independently of model payment and before any BYOK early return.

#### Scenario: Funded private WhatsApp execution
- **WHEN** a private-chat payer has at least the configured price for their WhatsApp destination
- **THEN** delivery preflight passes and model or command processing may continue

#### Scenario: Unfunded BYOK WhatsApp execution
- **WHEN** a BYOK user cannot fund one complete WhatsApp message and the request is not an eligible known command
- **THEN** no model call and no paid WhatsApp message submission occurs
- **AND** the system reacts to the triggering message with `👎`

#### Scenario: Group preflight uses every recipient
- **WHEN** a group contains the payer, two other non-agent users, and the agent
- **THEN** preflight requires the sum of the three human-recipient delivery prices
- **AND** the agent contributes no delivery price

#### Scenario: Free Telegram execution
- **WHEN** an otherwise-authorized Telegram user has a negative credit balance
- **THEN** zero-price delivery does not block the execution

### Requirement: Retained-history command recovery
When delivery preflight rejects a user-requested response, the system SHALL use the existing known-command detector and retained inbound message history to decide whether command processing may continue. It SHALL add no command-recovery state. An eligible command SHALL execute in the original invoker context, and each accepted response SHALL charge that invoker even when the resulting balance is negative. An ineligible command or non-command SHALL produce only a `👎` reaction to the triggering message.

#### Scenario: First retained command
- **WHEN** an unfunded user sends a known command and no prior known command from that invoker remains in retained history
- **THEN** command processing continues without another delivery preflight
- **AND** accepted command responses charge the invoker through normal delivery accounting

#### Scenario: Progressive command cooldown
- **WHEN** retained history contains one, two, or at least three prior known commands from the invoker
- **THEN** another unfunded command is eligible only after one day, seven days, or thirty days respectively since the latest prior command

#### Scenario: Filler messages do not reset command history
- **WHEN** non-command messages appear after a prior known command
- **THEN** history lookup continues until it finds enough prior commands to decide eligibility or reaches the retention boundary

#### Scenario: Command remains in cooldown
- **WHEN** an unfunded known command is not yet eligible
- **THEN** the system sends no text and reacts to the triggering message with `👎`

#### Scenario: Retained history expires
- **WHEN** prior commands cross the configured message-retention boundary
- **THEN** they no longer restrict command eligibility

### Requirement: Stateless execution-owner preflight
Delivery preflight SHALL hold no approval state. Each execution owner that can produce a paid outbound message SHALL invoke the check once before command, model, generation, or notification work begins. Nested SDK sends SHALL NOT recheck affordability after paid work has occurred. Independent commands or jobs SHALL invoke independent checks.

#### Scenario: Full group affordability check
- **WHEN** one group message will cost 0.4, 0.7, and 0.9 credits for its three non-agent recipients
- **THEN** the payer must have at least 2.0 credits for preflight to pass
- **AND** passing preflight creates no debit or usage record

#### Scenario: Multiple accepted responses
- **WHEN** one preflighted execution emits several provider-accepted outbound messages
- **THEN** each message is charged by the existing SDK success path
- **AND** nested SDK sends do not perform another affordability decision

#### Scenario: Independent sequential commands
- **WHEN** one command completes and a second command begins afterward
- **THEN** the second command performs its own current-balance preflight before command work

#### Scenario: Rechecking the same payer and chat
- **WHEN** another execution checks the same payer and chat after the payer's balance changes
- **THEN** the stateless preflight uses the current balance rather than cached approval

#### Scenario: Late chat execution error
- **WHEN** a preflighted chat execution later fails after work has begun
- **THEN** private error routing uses the original owner-level admission and sends at most one paid error message containing the `/settings` recovery command
- **AND** it sends no separate settings-link message and performs no paid fallback retry
- **AND** a successful or failed private routing attempt returns a `👎` reaction response, while an unavailable private destination preserves the existing inline error formatting

#### Scenario: No outbound response
- **WHEN** a preflighted execution submits no outbound message
- **THEN** it creates no delivery debit, usage record, or release operation

#### Scenario: Optional fanout notification cannot be funded
- **WHEN** an asset, developer, or release notification payer cannot fund one complete outbound message
- **THEN** the notification owner warns and skips that target without model work or provider submission
- **AND** the remaining targets continue

#### Scenario: Critical operation notification cannot be funded
- **WHEN** a purchase, transfer, or background media operation has already completed but its notification cannot be funded
- **THEN** the completed business operation is not reversed or reported as failed
- **AND** purchase and media notification failures remain operational errors while transfer notification failure remains non-fatal

### Requirement: Accepted outbound accounting
After an outbound provider call succeeds and the message is stored, the system SHALL atomically debit the payer and create one delivery usage record per positive-cost non-agent recipient. Each record SHALL identify the payer, chat, recipient counterpart, platform delivery tool, and charged amount. Zero-price recipients SHALL create neither a debit nor a delivery usage record.

#### Scenario: Private reply
- **WHEN** the agent sends a paid private reply to the invoking user
- **THEN** the usage record has the invoking user as both payer and recipient counterpart
- **AND** the agent has no delivery usage record

#### Scenario: Group reply
- **WHEN** user A invokes a group reply delivered to users A, B, and C
- **THEN** user A pays one recorded charge for each of A, B, and C
- **AND** the agent is excluded

#### Scenario: Telegram reply
- **WHEN** Telegram accepts a zero-price outbound message
- **THEN** the message is stored without changing the payer balance or creating delivery usage

### Requirement: Sequential WhatsApp sent reconciliation
The system SHALL process monetary reconciliation only from WhatsApp `sent` statuses that contain a recognized pricing type. Statuses SHALL be applied sequentially to the latest unreconciled delivery for the resolved chat and recipient. `regular` pricing SHALL preserve the recorded amount and mark it reconciled. `free_customer_service` and `free_entry_point` SHALL set the delivery amount to zero, refund the payer by the same delta, retain the usage row, and mark it reconciled.

#### Scenario: Paid sent status
- **WHEN** a `sent` status reports `regular` pricing for a pending recipient delivery
- **THEN** its recorded amount and payer balance remain unchanged
- **AND** the delivery becomes reconciled

#### Scenario: Free sent status
- **WHEN** a `sent` status reports a recognized free pricing type
- **THEN** the latest pending recipient delivery becomes zero-cost and reconciled
- **AND** its payer receives exactly the recorded delivery amount as a refund
- **AND** the usage row remains present

#### Scenario: Group participant status
- **WHEN** a group `sent` status identifies one participant
- **THEN** only that participant's latest pending delivery is reconciled

#### Scenario: Unsupported or unmatched status
- **WHEN** pricing is missing or unknown, the status is not `sent`, or no pending chat-recipient delivery exists
- **THEN** no usage amount, reconciliation flag, or payer balance changes

### Requirement: Delivery usage lifecycle
Delivery usage SHALL store delivery cost in `api_call_cost_credits` and `total_cost_credits`, with model, runtime, and maintenance components at zero. It SHALL expose whether delivery reconciliation is complete and SHALL follow ordinary usage retention without a separate callback store, exceptional retention, refund-on-cleanup, or balance mutation during cleanup.

#### Scenario: Pending usage visibility
- **WHEN** an accepted paid delivery has no processed `sent` pricing status
- **THEN** usage includes the charged amount with delivery reconciliation incomplete

#### Scenario: Ordinary retention
- **WHEN** a delivery usage row passes the normal usage-retention cutoff
- **THEN** ordinary cleanup may remove it without changing any account balance
