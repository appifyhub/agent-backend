## 1. Dependencies & Constants

- [x] 1.1 Add `python-docx` to `Pipfile` and run `pipenv lock`
- [x] 1.2 Extend `KNOWN_DOCS_FORMATS` in `src/features/chat/supported_files.py` with all new plain-text and source-code extensions and `.docx`
- [x] 1.3 Add a brief inline comment next to `.ts` noting the MPEG-TS MIME collision and that routing is extension-first

## 2. PlainTextLoader

- [x] 2.1 Create `src/features/documents/plain_text_loader.py` with a class that takes `document_url` (or bytes) and `job_id`
- [x] 2.2 Implement size guard: if `len(bytes) > 10 * 1024 * 1024`, raise `ExternalServiceError("File too large for processing (>10MB)", ATTACHMENT_PROCESSING_FAILED)`
- [x] 2.3 Implement UTF-8 decode with `errors="replace"` fallback on `UnicodeDecodeError`
- [x] 2.4 Return a single `langchain_core.documents.Document` containing the full text and basic metadata (e.g., `{"chunk": 0}`)
- [x] 2.5 Wrap unexpected loader-level exceptions and re-raise as `ExternalServiceError(..., DOCUMENT_SEARCH_FAILED) from e`

## 3. DOCX loader

- [x] 3.1 Create `src/features/documents/docx_loader.py` using `python-docx` directly, wrapped behind the same interface as `PlainTextLoader`
- [x] 3.2 Apply the same 10 MB size guard before invoking the underlying loader
- [x] 3.3 Wrap `python-docx` exceptions (e.g., `BadZipFile`, `PackageNotFoundError`) and re-raise as `ExternalServiceError(..., DOCUMENT_SEARCH_FAILED) from e`

## 4. Refactor DocumentSearch

- [x] 4.1 Change `DocumentSearch.__init__` signature: remove `document_url`, accept `documents: list[Document]`
- [x] 4.2 Remove the inline `PyMuPDFLoader(document_url).load()` call from `__init__`
- [x] 4.3 Bump `SEARCH_RESULT_PAGES` from 2 to 3
- [x] 4.4 Update the DI factory `di.document_search(...)` to match the new signature
- [x] 4.5 Replace the silent `except Exception` block in `execute()` with one that re-raises as `ExternalServiceError(..., DOCUMENT_SEARCH_FAILED) from e` so the processor's caller can catch and record it (verify this aligns with existing `__process_single` catch behavior)

## 5. Strategy selector in ChatAttachmentProcessor

- [x] 5.1 Introduce a constant `RAW_STRATEGY_TOKEN_THRESHOLD = 15_000` (or similar) in `chat_attachment_processor.py`
- [x] 5.2 Add an extraction step that picks a loader from extension/MIME:
  - plain-text/source extensions → `PlainTextLoader`
  - `.docx` → docx loader
  - `.pdf` → `PdfLoader` (new wrapper class, not called inside `DocumentSearch`)
- [x] 5.3 After extraction, join document text and compute `tokens_estimate = len(joined) // 3`
- [x] 5.4 If text is empty/whitespace-only, return a fixed "no extractable text" message and skip search
- [x] 5.5 If `tokens_estimate <= 15_000`, return the joined text directly (raw strategy)
- [x] 5.6 Otherwise, call `DocumentSearch(documents=...)` and return its result (search strategy)

## 6. Cache key update

- [x] 6.1 Update the cache key construction in `__process_single` to include a `strategy` segment: `{prefix}-{attachment_id}-{strategy}-{additional_context_hash}`
- [x] 6.2 Ensure the strategy is determined before the cache lookup so reads and writes share the same key

## 7. Wiring

- [x] 7.1 Wire `PlainTextLoader` and the docx loader into `src/di/di.py` if they need DI; otherwise import directly in the processor
- [x] 7.2 Verify `KNOWN_FILE_FORMATS` union still composes correctly across image/audio/docs

## 8. Tests

- [x] 8.1 Add `test/features/documents/test_plain_text_loader.py`: UTF-8 happy path, Windows-1252 fallback, empty file, size cap (>10 MB), corrupt-stream exception path
- [x] 8.2 Extend `test/features/chat/test_chat_attachment_processor.py` (or create if missing) with:
  - raw strategy used for small text input
  - search strategy used for large text input
  - boundary case at exactly 15,000 token estimate
  - empty extraction short-circuit (no `DocumentSearch` invocation)
  - corrupt-attachment failure stored in `errors[i]`, other attachments still succeed
  - cache key includes strategy segment (verify two strategies do not collide)
- [x] 8.3 Update existing `DocumentSearch` tests (or add new) to:
  - construct with `list[Document]` instead of a URL
  - assert `SEARCH_RESULT_PAGES == 3` via behavior (top-3 chunks)
  - (Note: DocumentSearch has no tests by design — "Not tested as it's just a proxy"; new signature validated via processor tests)
- [x] 8.4 Add a docx loader test using a tiny fixture (real or stubbed): happy path + corrupt-zip failure path

## 9. Verification

- [x] 9.1 Run `pipenv run pre-commit run --all-files --show-diff-on-failure`
- [x] 9.2 Run the full test suite via the project's test runner script
- [x] 9.3 Manual sanity check: send a `.md`, a `.docx`, and a `.pdf` through the running bot in dev mode and confirm correct strategy + content reach the chat LLM
- [x] 9.4 Update API/feature documentation in `docs/` to mention the broader file-type support
  - (N/A: docs cover REST endpoints only; file attachment behavior is internal to the bot and not documented in open-api-docs.yaml)
