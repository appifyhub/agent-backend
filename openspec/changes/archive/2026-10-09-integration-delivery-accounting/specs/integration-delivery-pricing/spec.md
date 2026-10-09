## Purpose

Provide explicit platform delivery prices in credits and stable delivery identities without conflating transport costs with model-provider charges.

## ADDED Requirements

### Requirement: Explicit supported-platform pricing
The system SHALL load delivery pricing from the configured catalog, SHALL explicitly cover Telegram and WhatsApp, and SHALL fail closed for missing platforms, markets, or categories rather than treating missing pricing as free.

#### Scenario: Telegram price
- **WHEN** Telegram delivery pricing is requested
- **THEN** the resolved delivery cost is zero credits

#### Scenario: Missing paid-platform pricing
- **WHEN** a WhatsApp destination cannot resolve a configured market or category
- **THEN** delivery pricing fails and the outbound provider request does not proceed

### Requirement: Recipient-aware rounded WhatsApp pricing
The system SHALL resolve WhatsApp prices by the recipient's most-specific configured phone prefix, fall back only to the explicit default market, and round configured credit costs upward to one decimal place without increasing exact tenths.

#### Scenario: Most-specific market
- **WHEN** multiple configured prefixes match a WhatsApp recipient
- **THEN** the market with the longest matching prefix supplies the price

#### Scenario: Upward rounding
- **WHEN** configured costs are 0.68, 0.7, and 0 credits
- **THEN** their resolved prices are 0.7, 0.7, and 0 credits respectively

### Requirement: Stable delivery usage identities
Delivery usage SHALL use purpose `message_delivery`, tool ID `telegram-message-delivery` with provider `telegram`, or tool ID `whatsapp-message-delivery` with provider `meta`. Delivery-only tools and providers SHALL be resolvable in usage history without becoming selectable model tools or user API-key providers.

#### Scenario: WhatsApp usage identity
- **WHEN** a WhatsApp delivery usage record is returned
- **THEN** its purpose is `message_delivery`, tool ID is `whatsapp-message-delivery`, and provider ID is `meta`

#### Scenario: Delivery providers are not model choices
- **WHEN** selectable model tools and API-key providers are returned
- **THEN** Telegram and Meta delivery-only identities are not offered as model configuration choices
