# replicate-generation Specification

## Purpose
Defines how Replicate-backed image and video generation behaves for callers: tolerating provider response quirks, extracting results, bounding video waits, and charging users exactly once for successful work.

## Requirements

### Requirement: Creation tolerates a missing model version
The system SHALL accept a prediction-create response whose version is null or hidden and continue waiting for the prediction instead of failing the generation.

#### Scenario: Create response has a null version
- **WHEN** Replicate accepts a create request and returns a prediction with `version: null`
- **THEN** the generation proceeds to wait for that prediction by its id
- **AND** no error is reported to the caller for the missing version

### Requirement: Results come from the terminal prediction
The system SHALL extract the generated media URL from the prediction state observed after waiting finishes, not from the creation response.

#### Scenario: Output appears only after completion
- **WHEN** the create response has no output and the finished prediction has an output URL
- **THEN** the caller receives the finished prediction's URL

### Requirement: Balance is checked before any provider request
The system SHALL validate the payer's credit balance for the requested image or video sizes and duration before sending a create request, and SHALL send no request when the balance is insufficient.

#### Scenario: Insufficient credits
- **WHEN** the payer cannot afford the requested generation
- **THEN** an insufficient-credits error is raised and no prediction is created

### Requirement: Successful generations are charged exactly once
The system SHALL record one usage record and deduct its cost once when a prediction succeeds, using the finished prediction's reported remote runtime when it is numeric and the locally measured runtime otherwise.

#### Scenario: Successful image prediction
- **WHEN** an image prediction finishes successfully with `predict_time` metrics
- **THEN** one usage record stores that remote runtime and the payer is debited once
- **AND** waiting again does not create another record or deduction

#### Scenario: Metrics missing or non-numeric
- **WHEN** the finished prediction has no metrics or a non-numeric `predict_time`
- **THEN** the usage record has no remote runtime and is still charged once

### Requirement: Failed generations are recorded without charge
The system SHALL record a failed usage record and SHALL NOT deduct credits when waiting raises, a video prediction ends in a non-success state, or a video prediction exceeds its time limit.

#### Scenario: Wait raises
- **WHEN** waiting for a prediction raises an error
- **THEN** one failed usage record exists, no credits are deducted, and later waits re-raise the same error without new records

#### Scenario: Video ends failed or canceled
- **WHEN** a video prediction reaches `failed` or `canceled`
- **THEN** a video-generation error with the provider detail is raised and one failed record is stored without deduction

#### Scenario: Video exceeds the time limit
- **WHEN** a video prediction is still running after the time limit
- **THEN** the system requests cancellation, raises a timeout error, and stores one failed record without deduction
