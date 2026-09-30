## Purpose

Allow callers to replace constructed dependencies while continuing to use the production dependency container and its normal construction, caching, and context behavior.

## ADDED Requirements

### Requirement: Optional dependency interception

The dependency container SHALL accept an optional interceptor for non-null dependency construction. Production DI SHALL use only this explicit argument and SHALL NOT consult an ambient context-local interceptor. Resolution SHALL use the declared return type and SHALL make the current container, provider identity, and invocation arguments available to the interceptor. A handled request SHALL bypass ordinary construction. Unrelated operations and nullable context lookups SHALL retain their existing behavior.

#### Scenario: Registered replacement
- **WHEN** a dependency is requested and its interceptor supplies a replacement
- **THEN** the caller receives that replacement without executing the ordinary constructor

#### Scenario: Arguments reach a replacement factory
- **WHEN** a parameterized dependency is requested with positional or keyword arguments
- **THEN** its replacement factory can observe equivalent bound argument values and the requesting container's current context

#### Scenario: Context access remains ordinary
- **WHEN** the caller reads an absent optional chat context or changes the invoker context
- **THEN** the existing context behavior executes without treating that operation as dependency replacement

### Requirement: Unhandled requests and failures are distinct

An interceptor result of `None` SHALL mean the request was unhandled and resolution SHALL continue to the next resolver or ordinary construction. Every other result SHALL count as handled, including false-valued objects. An interceptor exception SHALL propagate without attempting fallback construction.

#### Scenario: No replacement
- **WHEN** there is no interceptor or all configured resolvers return `None`
- **THEN** the dependency is constructed through the existing production path

#### Scenario: Replacement factory fails
- **WHEN** an interceptor or replacement factory raises an exception
- **THEN** that exception propagates from dependency resolution and ordinary construction does not run

#### Scenario: False-valued replacement
- **WHEN** an interceptor supplies a valid replacement whose truth value is false
- **THEN** the replacement is returned and is not mistaken for an unhandled request

### Requirement: Stable declared type identity

Interception SHALL consistently identify a dependency from its declared return type, including declarations represented as forward references or import aliases. Distinct qualified types SHALL NOT collide solely because their short names match. A fake's concrete type SHALL NOT change the identity used to request its production dependency.

#### Scenario: Forward reference registration
- **WHEN** a registered dependency is declared through a forward reference or alias
- **THEN** it resolves to the same registration as its canonical type without requiring construction of the production dependency

#### Scenario: Equal short names
- **WHEN** two dependency types have the same short name in different modules
- **THEN** registering one does not replace the other

### Requirement: Existing dependency lifetimes are preserved

Previously cached dependencies SHALL remain stable within their existing cache scope, including intercepted replacements. Previously transient factories SHALL continue to resolve each invocation with its current arguments. Registering a replacement SHALL NOT silently turn all invocations of a type into a global singleton.

#### Scenario: Repeated cached access
- **WHEN** a cached dependency is accessed twice on the same container
- **THEN** the same instance is returned and its replacement factory executes only for initial resolution

#### Scenario: Repeated parameterized access
- **WHEN** a transient factory is invoked twice with different inputs
- **THEN** both requests are resolved with their respective inputs

### Requirement: Clones retain replacement policy and rebuild contextual dependencies

A cloned container SHALL retain its parent's interceptor while resolving context-bound dependencies against the clone's session and invoker context. Cached services and repositories from the parent SHALL NOT be copied into the clone. Explicitly shared external fake state SHALL remain available within the same test environment.

#### Scenario: Clone uses another session
- **WHEN** a container with resolved repositories and services is cloned with another session
- **THEN** the clone creates its own repositories and services using that session and retains the same replacement policy

#### Scenario: Shared external observations
- **WHEN** a clone sends a message through a deliberately shared external fake
- **THEN** the test can observe that message through the test environment's fake state without sharing the parent's context-bound service instance

### Requirement: Session adapter preserves SQL ownership

`DI.new_session()` SHALL be an uncached intercepted provider adjacent to the existing session access and rollback functions. Without interception it SHALL return the existing SQL module's detached-session context manager. The SQL module's creation and cleanup functions SHALL remain unchanged. Chat ingress, claim, processing, and finalization SHALL keep their existing independent session scopes; quiet-period waiting SHALL retain only a sessionless contextual DI.

#### Scenario: Normal detached session
- **WHEN** production code enters the DI session scope without a replacement
- **THEN** the existing SQL context manager creates and closes the session through its unchanged lifecycle

### Requirement: Initial session injection preserves session binding

`DI.inject_db_session(db)` SHALL attach a session only when the container has none. It SHALL remain adjacent to the other session functions and SHALL NOT be intercepted. The caller SHALL retain responsibility for session cleanup. Subsequent injection SHALL raise `InternalError` with `DI_DEPENDENCY_NOT_MET`, preserving the existing session and cached dependencies. Callers needing a different session SHALL use a clone. Each responder SHALL use one ingress DI, attach its session before ingestion, and inject the resolved invoker and chat afterward. Delayed burst coordination SHALL retain its separate sessionless container.

#### Scenario: Initial attachment
- **WHEN** ingress opens a session through a fresh DI's session adapter
- **THEN** it attaches that session to the same DI and resolves the inbound service through it
- **AND** the SQL context manager remains responsible for closing the session

#### Scenario: Session replacement is rejected
- **WHEN** a container that already has a session receives another session injection
- **THEN** injection fails without changing the original session or its cached repositories
