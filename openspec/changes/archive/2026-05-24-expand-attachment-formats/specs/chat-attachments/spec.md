## ADDED Requirements

### Requirement: Recognize broad set of text-bearing file formats as documents

The system SHALL recognize the following extensions as document attachments eligible for content extraction:

- Plain-text formats: `.txt`, `.md`, `.log`, `.csv`, `.json`, `.xml`, `.yaml`, `.yml`
- Source-code formats: `.js`, `.ts`, `.jsx`, `.tsx`, `.py`, `.java`, `.c`, `.h`, `.cpp`, `.hpp`, `.go`, `.rs`, `.rb`, `.php`, `.sh`, `.bash`, `.zsh`, `.swift`, `.kt`, `.html`, `.css`, `.scss`
- Binary document formats: `.docx`, `.pdf`

The system MUST NOT recognize `.doc` or `.rtf` as supported document formats.

Extension-based recognition MUST take precedence over MIME-type matching to handle cases where platforms report ambiguous or generic MIME types (e.g., `application/octet-stream` for `.log` files, `video/mp2t` for `.ts` source files).

#### Scenario: User attaches a Markdown file

- **WHEN** a user sends an attachment with extension `.md`
- **THEN** the system identifies it as a supported document and proceeds with content extraction

#### Scenario: User attaches a DOCX file

- **WHEN** a user sends an attachment with extension `.docx` or MIME `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- **THEN** the system identifies it as a supported document and proceeds with content extraction

#### Scenario: User attaches a legacy DOC file

- **WHEN** a user sends an attachment with extension `.doc`
- **THEN** the system reports the file as unsupported and does not attempt extraction

#### Scenario: Ambiguous MIME for a source file

- **WHEN** a user sends an attachment with extension `.ts` and an unrelated MIME (e.g., `video/mp2t`)
- **THEN** the system identifies it as a TypeScript source file based on extension and proceeds with text extraction

### Requirement: Extract content via format-appropriate loader

The system SHALL extract textual content from supported documents using a loader chosen by extension:

- Plain-text and source-code extensions: a unified loader that decodes the file bytes as UTF-8.
- `.docx`: a Word document loader (e.g., `python-docx` / `Docx2txtLoader`).
- `.pdf`: a PDF page loader (`PyMuPDFLoader`).

All loaders MUST return a list of one or more `Document` objects suitable for downstream processing.

#### Scenario: UTF-8 plain-text file

- **WHEN** the plain-text loader reads a valid UTF-8 file
- **THEN** the file is decoded losslessly and returned as a single `Document`

#### Scenario: Non-UTF-8 plain-text file

- **WHEN** the plain-text loader encounters a `UnicodeDecodeError` (e.g., Windows-1252 or Latin-1 bytes)
- **THEN** the loader retries the decode with `errors="replace"` and returns the resulting text without raising

#### Scenario: Multi-page PDF

- **WHEN** the PDF loader processes a multi-page document
- **THEN** it returns one `Document` per page

### Requirement: Choose extraction strategy by size

After extraction, the system SHALL count the joined extracted text length and select a strategy:

- If the estimated token count (`len(text) // 3`) is at most 15,000, the system SHALL return the full joined text directly (raw strategy).
- If the estimated token count exceeds 15,000, the system SHALL invoke the semantic-search pipeline (`DocumentSearch`) with the extracted documents and return the resulting summary (search strategy).

#### Scenario: Small file uses raw strategy

- **WHEN** an attachment's extracted text is below the token threshold
- **THEN** the full joined text is returned to the caller without embedding or similarity search

#### Scenario: Large file uses search strategy

- **WHEN** an attachment's extracted text exceeds the token threshold
- **THEN** the documents are passed to the semantic-search pipeline and the copywriter-generated summary is returned

### Requirement: Cap attachment file size at 10 MB

The system SHALL refuse to process attachment payloads larger than 10 MB.

#### Scenario: Oversized file via URL attachment

- **WHEN** an attachment's downloaded byte length exceeds 10 MB
- **THEN** the system raises a structured error with code `ATTACHMENT_PROCESSING_FAILED` and the failure is recorded for that attachment only

#### Scenario: Within-limit file

- **WHEN** an attachment is 10 MB or smaller
- **THEN** the system processes the attachment normally

### Requirement: Short-circuit empty extractions

The system SHALL detect when extraction yields no meaningful text and SHALL skip the semantic-search pipeline for that attachment.

#### Scenario: Image-only PDF

- **WHEN** the PDF loader returns documents whose combined non-whitespace content is empty
- **THEN** the system returns a fixed message indicating the document contains no extractable text and does not invoke `DocumentSearch`

#### Scenario: DOCX with only images

- **WHEN** the DOCX loader returns documents whose combined non-whitespace content is empty
- **THEN** the system returns the same "no extractable text" message and does not invoke `DocumentSearch`

### Requirement: Report extraction errors per attachment without aborting

The system SHALL handle extraction failures gracefully on a per-attachment basis:

- Loader-level failures (corrupt files, decode failures that cannot be recovered, dependency errors) MUST raise `ExternalServiceError` with code `DOCUMENT_SEARCH_FAILED`.
- Size-limit violations MUST raise `ExternalServiceError` with code `ATTACHMENT_PROCESSING_FAILED`.
- Each raise MUST chain the underlying cause via `raise ... from e` so the formatted error string contains `# Caused by: ...`.
- A failure on one attachment MUST NOT prevent other attachments in the same tool call from being processed.

#### Scenario: Corrupt DOCX file

- **WHEN** the Word loader raises an exception while parsing a corrupt `.docx`
- **THEN** the system records a formatted error string for that attachment using code `DOCUMENT_SEARCH_FAILED` and continues processing the remaining attachments

#### Scenario: One bad file among several

- **WHEN** a tool call includes one unreadable file and one valid file
- **THEN** the unreadable file's error is recorded in its `errors[i]` slot and the valid file's `text_content` is populated successfully

### Requirement: Cache extracted content per strategy

The system SHALL cache extracted document content with a cache key that includes the strategy used (`raw` or `search`).

The cache key SHALL have the shape: `{prefix}-{attachment_id}-{strategy}-{additional_context_hash}`.

#### Scenario: Cache hit for repeated request

- **WHEN** the same attachment is requested twice with the same additional context and same resulting strategy
- **THEN** the second request returns the cached content without re-running extraction or search

#### Scenario: Strategy switch does not collide

- **WHEN** an attachment's extraction strategy differs between two requests (e.g., due to a change in cached content size or future configuration)
- **THEN** the two cached values are stored under distinct keys and do not overwrite each other

### Requirement: Generalize document search to accept pre-loaded documents

`DocumentSearch` SHALL accept a pre-loaded `list[Document]` instead of loading documents itself from a URL. The caller is responsible for selecting and invoking the appropriate loader.

The search top-K (`SEARCH_RESULT_PAGES`) SHALL be 3.

#### Scenario: Constructor accepts documents directly

- **WHEN** a caller constructs `DocumentSearch` with a `list[Document]`
- **THEN** the search executes against those documents without re-downloading or re-loading from a URL

#### Scenario: Top-K returns three chunks

- **WHEN** the semantic search has enough indexed content
- **THEN** the system retrieves the top 3 chunks for the copywriter step

### Requirement: Add python-docx dependency

The project SHALL include `python-docx` as a runtime dependency to enable `.docx` extraction.

#### Scenario: Dependency available at runtime

- **WHEN** the application starts
- **THEN** `python-docx` (or `Docx2txtLoader`'s underlying module) is importable and usable for DOCX extraction
