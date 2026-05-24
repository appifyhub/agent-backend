## Context

The attachment-processing pipeline today handles three media families:

- **Images** → `ComputerVisionAnalyzer` (batched)
- **Audio** → `AudioTranscriber`
- **Documents** → `DocumentSearch` (PDF only)

The document path is the narrowest: only `.pdf` is recognized, and the only strategy is "load via `PyMuPDFLoader`, embed into an in-memory vector store, semantic-search the top-K chunks, run a copywriter LLM over them, return summary." This works well for large PDFs but is overkill — and unnecessarily costly — for short text files.

The pipeline already provides the surrounding machinery we need: download via URL, 13-week TTL cache, per-attachment graceful failure (`__process_single` catches `Exception`, stores formatted `str(e)` into `errors[i]`), and a structured per-attachment result dict consumed by the LLM tool layer.

Recent commits (`414e4a5` and adjacent) added user-configurable `max_output_tokens` per chat membership, but that constrains LLM **output** — not the **input** context size we control here. There is no user-facing knob for input context; this design keeps it that way.

## Goals / Non-Goals

**Goals:**
- Extend the document attachment path to recognize and extract content from a broad range of plain-text formats (text, markup, configs, source code) plus `.docx`.
- Choose between "raw dump" and "semantic search" per attachment based on size, transparently to the caller.
- Bound memory exposure for URL-attached files via a hard size cap.
- Surface extraction failures as structured, per-attachment errors using existing error codes; do not abort the tool call when one attachment fails.
- Keep the LLM tool-call result shape (`list[dict[str, str]]`) backwards-compatible.

**Non-Goals:**
- No support for `.doc` (legacy binary Word) or `.rtf` (low demand, extra dep).
- No OCR for image-only PDFs/DOCX — we report "no extractable text" and stop.
- No user-configurable token threshold or strategy override (would require frontend changes; not justified for V1).
- No richer per-attachment error dict (`to_llm_dict()`) — would change the result type signature. Deferred.
- No new error codes — reuse `DOCUMENT_SEARCH_FAILED` and `ATTACHMENT_PROCESSING_FAILED`.
- No changes to image or audio paths.

## Decisions

### D1: Two strategies, selected by size

**Decision**: After extracting text, estimate token count as `len(joined_text) // 3`. If ≤ 15,000 tokens, return the joined text directly; otherwise feed the documents into `DocumentSearch`.

**Rationale**:
- Embedding + similarity search on a small file is wasted spend and latency.
- Raw dump gives the LLM the full document, producing better answers for small inputs.
- 15K tokens is ~7-10% of a typical 200K-token context window, leaving ample room for chat history and other attachments.
- `len // 3` is conservative (assumes denser tokenization than `len // 4`), reducing the risk that a "raw" dump silently exceeds the context window for non-Latin scripts or code-heavy text.

**Alternatives considered**:
- Per-format thresholds (e.g., always search PDFs, always raw txt): rejected — surprising behavior at the boundary (a 100 KB `.md` searched but 100 KB `.pdf` not).
- Use `tiktoken` for accurate counts: rejected for V1 — adds startup cost and complexity for a decision boundary that doesn't need precision.

### D2: Unified `PlainTextLoader` for all decode-based formats

**Decision**: A single new class loads every plain-text extension. UTF-8 strict first; on `UnicodeDecodeError`, retry with `errors="replace"`. Returns a single `Document` with the full file contents and metadata `{"chunk": 0}`.

**Rationale**:
- Logic is identical for `.txt`, `.md`, `.log`, `.csv`, `.json`, `.xml`, `.yaml`, `.yml`, and all source-code extensions — splitting per format would be pure duplication.
- `errors="replace"` covers Windows-1252 / Latin-1 / mojibake files lossily but never crashes; matches the "graceful per-attachment failure" theme.

**Alternatives considered**:
- Use `chardet` for accurate encoding detection: rejected — heavy dep, marginal benefit, modern uploads are nearly all UTF-8.
- Use `langchain_community.document_loaders.TextLoader`: rejected — it takes a file path, not bytes/URL; would force a temp-file detour.

### D3: `DocumentSearch` becomes loader-agnostic

**Decision**: Move `PyMuPDFLoader(document_url).load()` out of `DocumentSearch.__init__`. The new constructor accepts a pre-loaded `list[Document]` plus the existing tools. The caller is responsible for choosing and invoking the right loader.

**Rationale**:
- Required to support `.docx` and (eventually) any other format through the same search path.
- Keeps `DocumentSearch` focused on its real job: embed → search → copywrite.
- Makes the class trivially unit-testable with hand-built `Document` lists.

**Alternatives considered**:
- Loader factory inside `DocumentSearch`: rejected — couples the class to every supported format.

### D4: 10MB hard cap at the loader level

**Decision**: Each loader checks `len(downloaded_bytes) > 10 * 1024 * 1024` first and raises `ExternalServiceError("File too large for processing (>10MB)", ATTACHMENT_PROCESSING_FAILED) from None`. Caught by `__process_single`, reported as an error string for that attachment.

**Rationale**:
- Telegram/WhatsApp already cap uploads (~20 MB / 16 MB respectively), so the cap mainly matters for URL-attached files where users could point at arbitrarily large resources.
- 10 MB comfortably covers any reasonable user document while bounding memory and download time.
- Reuses `ATTACHMENT_PROCESSING_FAILED` (currently defined-but-unused) — no frontend updates.

**Alternatives considered**:
- Streaming size check during download: rejected — over-engineered; the existing flow already loads the full bytes into memory.
- ValidationError + 422 status: rejected — would mismatch the code's 5xxx range; the HTTP status is irrelevant inside the per-attachment flow anyway.

### D5: Empty-extraction short-circuit

**Decision**: If extracted text is empty or whitespace-only after joining all documents, return a fixed message (`"Document contains no extractable text (possibly an image-only document)."`). Do not invoke `DocumentSearch`.

**Rationale**:
- Running semantic search on `""` produces noise and burns tokens for no gain.
- A clear message lets the chat LLM tell the user something useful ("looks like a scanned PDF — try sending the image instead").

### D6: Cache key includes strategy

**Decision**: Cache key becomes `{prefix}-{attachment_id}-{strategy}-{additional_context_hash}` where `strategy ∈ {"raw", "search"}`.

**Rationale**:
- The cached value differs in structure between strategies (raw text vs. copywriter summary). Conflating them under one key would return wrong content on the second access after a strategy switch.
- Strategy almost never changes for the same attachment (size is stable), so cache hit-rate is unaffected in practice.
- Existing cache entries become orphaned but harmless — they expire on the 13-week TTL.

### D7: Reuse existing error codes; raise as `ExternalServiceError`

**Decision**:
- `DOCUMENT_SEARCH_FAILED` (5010) for any extraction/parse failure: corrupt `.docx`, broken `.pdf`, unexpected loader exception.
- `ATTACHMENT_PROCESSING_FAILED` (5006) for size violations.
- Both raised as `ExternalServiceError(message, CODE) from e` (where `e` is the underlying cause). `ServiceError.__str__()` formats as `[E5010] 🌐 message # Caused by: ...`, which the existing `__process_single` catch path writes into `errors[i]`.

**Rationale**:
- Both codes exist but are unused — wiring them up does not require new frontend localization.
- 5xxx range matches `ExternalServiceError` convention.
- HTTP status (502) does not surface for this flow; the error path is purely the per-attachment string.

### D8: Increase `SEARCH_RESULT_PAGES` from 2 to 3

**Decision**: Bump the top-K from 2 to 3 chunks for the semantic-search path.

**Rationale**:
- Small change requested by user during exploration.
- Three chunks give the copywriter LLM more context to work with on large documents without significantly inflating the prompt.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| `.ts` extension collides with MPEG Transport Stream (`video/mp2t`). A platform might report TS video files as `application/typescript` (or vice versa) | Routing is extension-first; existing audio/video MIME detection in the bot SDKs runs before document routing. Document a code comment near the `.ts` entry flagging the collision. |
| Lossy decoding (`errors="replace"`) may produce garbled content for legacy-encoded files | Replacement characters are visible to the LLM, which can typically signal "file content looks corrupted" to the user. Real fix is `chardet` — defer until needed. |
| Empty docx/PDF check is a heuristic — a document with only formatting whitespace gets the "no text" message | Acceptable: such documents have nothing useful to chat about anyway. |
| `python-docx` is a new dependency | Maintained, widely used, MIT-licensed, ~1 MB install. Low risk. |
| Cache key change orphans existing PDF cache entries | Entries expire naturally on 13-week TTL. No correctness risk. |
| 10 MB cap is arbitrary | Configurable in code (single constant). Easy to bump if a real use case complains. |
| Source-code extensions are added speculatively (no proven user demand yet) | Same code path as `.txt`; the cost is dict entries plus one comment about `.ts`. Trivial to remove if it causes confusion. |

## Migration Plan

1. Add `python-docx` to `Pipfile` and lock it.
2. Implement new loaders and the strategy selector behind the existing tool-call API — no caller-side changes needed.
3. Deploy. Behavior changes are entirely additive (existing PDF flow now goes through the refactored `DocumentSearch`; result shape unchanged).
4. No rollback gymnastics needed — feature is internal to the attachment tool call. Reverting the commit fully restores prior behavior. Cached entries from the new flow become orphans on revert, expire on TTL.

## Open Questions

- None blocking. `.ts` MIME collision is documented and not actionable until/unless a real user case surfaces.
