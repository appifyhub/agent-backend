## Why

Users can currently "chat with a PDF" but cannot send any other text-bearing file types. Real conversations involve `.txt`, `.md`, `.docx`, source code, configs, logs, and structured data. Today the bot rejects them all as unsupported. Closing this gap turns the bot from a PDF-only document assistant into a general "chat with any file" agent.

## What Changes

- Support new attachment extensions, all routed through the existing attachment-processing pipeline:
  - Plain-text formats: `.txt`, `.md`, `.log`, `.csv`, `.json`, `.xml`, `.yaml`, `.yml`
  - Source-code formats: `.js`, `.ts`, `.jsx`, `.tsx`, `.py`, `.java`, `.c`, `.h`, `.cpp`, `.hpp`, `.go`, `.rs`, `.rb`, `.php`, `.sh`, `.bash`, `.zsh`, `.swift`, `.kt`, `.html`, `.css`, `.scss`
  - Binary document format: `.docx`
- Add a size-based strategy selector: small files (≤ ~15K-token estimate) are loaded fully into the LLM's context as raw text; larger files continue to use the existing semantic-search pipeline.
- Add a 10MB hard cap at the loader level to prevent oversized URL-attached files from exhausting memory.
- Introduce graceful, per-attachment error reporting using existing-but-unused error codes (`DOCUMENT_SEARCH_FAILED` for extraction failures; `ATTACHMENT_PROCESSING_FAILED` for size violations); one corrupt attachment does not fail the whole tool call.
- Short-circuit empty extractions with a clear "no extractable text" message instead of running semantic search on nothing.
- **BREAKING (internal)**: `DocumentSearch.__init__` now accepts a pre-loaded `list[Document]` instead of a raw `document_url`. The PDF loader moves out of the class into the caller. No public-API impact.
- Increase `SEARCH_RESULT_PAGES` from 2 to 3 for slightly richer search results.
- Add `python-docx` as a new dependency for `.docx` extraction.
- Drop `.doc` and `.rtf` from scope (legacy formats with significant extraction cost and minimal user demand).

## Capabilities

### New Capabilities
- `chat-attachments`: End-to-end behavior for processing user-attached files in chat — extension/MIME recognition, content extraction, raw-vs-search strategy selection, caching, and per-attachment error reporting. Covers all attachment types (images, audio, documents) but this change focuses on extending the document path.

### Modified Capabilities
<!-- None: this is the first change in OpenSpec; there are no existing specs to modify. -->

## Impact

- **Code**:
  - `src/features/chat/supported_files.py` — expanded `KNOWN_DOCS_FORMATS`
  - `src/features/chat/chat_attachment_processor.py` — strategy selector, size guard, empty-extract short-circuit, updated cache key, structured error raises
  - `src/features/documents/document_search.py` — constructor signature change, `SEARCH_RESULT_PAGES` bump
  - `src/features/documents/plain_text_loader.py` — new (unified UTF-8 loader with `errors="replace"` fallback)
  - `src/features/documents/docx_loader.py` (or use `Docx2txtLoader` directly) — new
  - `src/di/di.py` — wire new loaders / updated `document_search` factory
- **API**: No public API or HTTP contract changes. Behavior changes are internal to the attachment-processing tool call.
- **Dependencies**: Add `python-docx` to `Pipfile`.
- **Error codes**: Reuse `DOCUMENT_SEARCH_FAILED` (5010) and `ATTACHMENT_PROCESSING_FAILED` (5006), both currently unused. No new codes added (avoids frontend updates).
- **Tests**: New unit tests for plain-text loading (encoding fallback, oversize), processor strategy selection (raw/search boundary, corrupt input, empty extract), and refactored `DocumentSearch`.
- **Caching**: Cache key gains a `strategy` segment (`raw` | `search`); previously cached entries remain valid as-is but will be invalidated when the key shape changes.
- **Performance**: Small files skip embedding + semantic search, reducing latency and embedding-API spend on common cases.
