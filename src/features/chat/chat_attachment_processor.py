import base64
from datetime import datetime, timedelta
from enum import Enum

import requests
from langchain_core.documents import Document

from db.schema.chat_message_attachment import ChatMessageAttachment
from di.di import DI
from features.audio.audio_transcriber import AudioTranscriber
from features.chat.chat_attachment_utils import resolve_all_attachments
from features.chat.supported_files import KNOWN_AUDIO_FORMATS, KNOWN_DOCS_FORMATS, KNOWN_IMAGE_FORMATS
from features.documents.document_search import DocumentSearch
from features.external_tools.intelligence_presets import default_tool_for
from features.images.computer_vision_analyzer import ComputerVisionAnalyzer
from features.tools_cache.tools_cache import ToolsCache
from features.web_browsing.web_fetcher import DEFAULT_HEADERS
from util import log
from util.functions import digest_md5

CACHE_PREFIX = "attachments-analyzer"
CACHE_TTL = timedelta(weeks = 13)
SEARCH_THRESHOLD_TOKENS = 15_000


class ChatAttachmentProcessor:

    class Result(Enum):
        failed = "Failed"
        partial = "Partial"
        success = "Success"

    # the following two lists are in sync
    __attachments: list[ChatMessageAttachment]
    __contents: list[str | None]
    __errors: list[str | None]

    __additional_context: str | None
    __di: DI

    def __init__(
        self,
        additional_context: str | None,
        attachment_ids: list[str] | None,
        urls: list[str] | None,
        di: DI,
    ):
        self.__attachments = []
        self.__contents = []
        self.__errors = []
        self.__additional_context = additional_context
        self.__di = di
        log.d(
            f"Validating {len(attachment_ids or [])} attachment IDs "
            f"and {len(urls or [])} URLs in chat '{self.__di.invoker_chat_id}'",
        )
        self.__attachments = resolve_all_attachments(attachment_ids, urls, self.__di)

    @property
    def __resolution_status(self) -> Result:
        if not self.__attachments:
            return ChatAttachmentProcessor.Result.failed
        contents_match_attachments = len(self.__attachments) == len(self.__contents)
        # failure -> attachments don't match contents (system error)
        if not contents_match_attachments:
            return ChatAttachmentProcessor.Result.failed
        successful_contents = sum(1 for content in self.__contents if content is not None)
        # failure -> 0% success (no content resolved)
        if successful_contents == 0:
            return ChatAttachmentProcessor.Result.failed
        # success -> 100% success (all content resolved)
        if successful_contents == len(self.__attachments):
            return ChatAttachmentProcessor.Result.success
        # partial -> some content resolved, some failed
        return ChatAttachmentProcessor.Result.partial

    @property
    def result(self) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for attachment, content, error in zip(self.__attachments, self.__contents, self.__errors):
            attachment_data = {
                "id": attachment.id,
                "text_content": content if content is not None else "<unresolved>",
                "type": attachment.mime_type if attachment.mime_type else "<unknown>",
                "error": error if error else "<none>",
            }
            result.append(attachment_data)
        return result

    def execute(self) -> Result:
        log.d("Resolving attachments content")

        self.__contents = [None] * len(self.__attachments)
        self.__errors = [None] * len(self.__attachments)

        # separate image attachments from non-image ones for batched CV analysis
        image_indices = [
            i for i, a in enumerate(self.__attachments)
            if a.mime_type in KNOWN_IMAGE_FORMATS.values() or a.extension in KNOWN_IMAGE_FORMATS.keys()
        ]
        non_image_indices = [i for i in range(len(self.__attachments)) if i not in image_indices]

        if image_indices:
            self.__process_images([self.__attachments[i] for i in image_indices], image_indices)
        for i in non_image_indices:
            self.__process_single(self.__attachments[i], i)

        result = self.__resolution_status
        log.i(f"Resolution result: {result}")
        return result

    def __process_images(self, image_attachments: list[ChatMessageAttachment], indices: list[int]):
        # use a group cache key based on sorted attachment IDs + context
        sorted_ids = ",".join(sorted(a.id for a in image_attachments))
        additional_content_hash = digest_md5(self.__additional_context) if self.__additional_context else "*"
        cache_key = ToolsCache.create_key(CACHE_PREFIX, f"{sorted_ids}-{additional_content_hash}")
        cache_entry = self.__di.tools_cache_repo.get(cache_key)
        if cache_entry:
            if not cache_entry.is_expired():
                log.t(f"Cache hit for image group '{cache_key}'")
                for i in indices:
                    self.__contents[i] = cache_entry.value
                return
            log.t(f"Cache expired for image group '{cache_key}'")
        log.t(f"Cache miss for image group '{cache_key}'")
        try:
            image_b64s: list[str] = []
            image_mime_types: list[str] = []
            for attachment in image_attachments:
                contents = requests.get(str(attachment.last_url), headers = DEFAULT_HEADERS).content
                image_b64s.append(base64.b64encode(contents).decode("utf-8"))
                image_mime_types.append(str(attachment.mime_type))
            configured_tool = self.__di.tool_choice_resolver.require_tool(
                ComputerVisionAnalyzer.TOOL_TYPE,
                default_tool_for(ComputerVisionAnalyzer.TOOL_TYPE),
            )
            content = self.__di.computer_vision_analyzer(
                job_id = sorted_ids,
                image_mime_types = image_mime_types,
                configured_tool = configured_tool,
                image_b64s = image_b64s,
                additional_context = self.__additional_context,
            ).execute()
            if content is not None:
                self.__di.tools_cache_repo.save(
                    ToolsCache(
                        key = cache_key,
                        value = content,
                        expires_at = datetime.now() + CACHE_TTL,
                    ),
                )
            for i in indices:
                self.__contents[i] = content
        except Exception as e:
            log.w(f"Error resolving contents for image group '{sorted_ids}'", e)
            for i in indices:
                self.__errors[i] = f"Error resolving contents for image group '{sorted_ids}': {str(e)}"

    def __process_single(self, attachment: ChatMessageAttachment, index: int):
        is_document = (
            attachment.mime_type in KNOWN_DOCS_FORMATS.values()
            or attachment.extension in KNOWN_DOCS_FORMATS.keys()
        )
        additional_content_hash = digest_md5(self.__additional_context) if self.__additional_context else "*"

        if is_document:
            # processing strategy is determined during extraction, so we probe both possible cache keys
            for strategy in ("raw", "search"):
                cache_key = ToolsCache.create_key(
                    CACHE_PREFIX,
                    f"{attachment.id}-{strategy}-{additional_content_hash}",
                )
                cache_entry = self.__di.tools_cache_repo.get(cache_key)
                if cache_entry:
                    if not cache_entry.is_expired():
                        log.t(f"Cache hit for '{cache_key}'")
                        self.__contents[index] = cache_entry.value
                        return
                    log.t(f"Cache expired for '{cache_key}'")
            log.t(f"Cache miss for document attachment '{attachment.id}'")

            # fetch and cache the content based on the fetch strategy
            try:
                strategy, content = self.__fetch_document_content(attachment)
                if content is not None:
                    cache_key = ToolsCache.create_key(
                        CACHE_PREFIX,
                        f"{attachment.id}-{strategy}-{additional_content_hash}",
                    )
                    self.__di.tools_cache_repo.save(
                        ToolsCache(
                            key = cache_key,
                            value = content,
                            expires_at = datetime.now() + CACHE_TTL,
                        ),
                    )
                self.__contents[index] = content
            except Exception as e:
                log.w(f"Error resolving contents for '{attachment.id}'", e)
                self.__errors[index] = f"Error resolving contents for '{attachment.id}': {str(e)}"
        else:
            # non-document attachment - let's try cache again
            unique_identifier = f"{attachment.id}-{additional_content_hash}"
            cache_key = ToolsCache.create_key(CACHE_PREFIX, unique_identifier)
            cache_entry = self.__di.tools_cache_repo.get(cache_key)
            if cache_entry:
                if not cache_entry.is_expired():
                    log.t(f"Cache hit for '{cache_key}'")
                    self.__contents[index] = cache_entry.value
                    return
                log.t(f"Cache expired for '{cache_key}'")
            log.t(f"Cache miss for '{cache_key}'")

            # resolve the attachment to text content and cache it
            try:
                content = self.fetch_text_content(attachment)
                if content is not None:
                    self.__di.tools_cache_repo.save(
                        ToolsCache(
                            key = cache_key,
                            value = content,
                            expires_at = datetime.now() + CACHE_TTL,
                        ),
                    )
                self.__contents[index] = content
            except Exception as e:
                log.w(f"Error resolving contents for '{attachment.id}'", e)
                self.__errors[index] = f"Error resolving contents for '{attachment.id}': {str(e)}"

    def __fetch_document_content(self, attachment: ChatMessageAttachment) -> tuple[str, str | None]:
        log.t(f"Extracting document content for attachment '{attachment.id}'")
        documents = self.__load_documents(attachment)
        joined_text = "\n\n".join(doc.page_content for doc in documents)

        if not joined_text.strip():
            message = f"Document '{attachment.id}' contains no extractable text (possibly image-only)."
            log.w(message)
            return "raw", message

        tokens_estimate = len(joined_text) // 3
        log.t(f"Estimated {tokens_estimate} tokens for attachment '{attachment.id}'")

        if tokens_estimate <= SEARCH_THRESHOLD_TOKENS:
            log.d(f"Using raw strategy for attachment '{attachment.id}'")
            return "raw", f"Document Content:\n\n```\n{joined_text}\n```"

        log.d(f"Using search strategy for attachment '{attachment.id}'")
        embedding_tool = self.__di.tool_choice_resolver.require_tool(
            DocumentSearch.EMBEDDING_TOOL_TYPE,
            default_tool_for(DocumentSearch.EMBEDDING_TOOL_TYPE),
        )
        copywriter_tool = self.__di.tool_choice_resolver.require_tool(
            DocumentSearch.COPYWRITER_TOOL_TYPE,
            default_tool_for(DocumentSearch.COPYWRITER_TOOL_TYPE),
        )
        content = self.__di.document_search(
            job_id = attachment.id,
            documents = documents,
            embedding_tool = embedding_tool,
            copywriter_tool = copywriter_tool,
            additional_context = self.__additional_context,
        ).execute()
        return "search", content

    def __load_documents(self, attachment: ChatMessageAttachment) -> list[Document]:
        ext = (attachment.extension or "").lower()
        url = str(attachment.last_url)
        if ext == "pdf" or attachment.mime_type == "application/pdf":
            return self.__di.pdf_loader(job_id = attachment.id, document_url = url).load()
        if ext == "docx":
            return self.__di.docx_loader(job_id = attachment.id, document_url = url).load()
        return self.__di.plain_text_loader(job_id = attachment.id, document_url = url).load()

    def fetch_text_content(self, attachment: ChatMessageAttachment) -> str | None:
        log.t(f"Resolving text content for attachment '{attachment.id}'")

        # fetching binary contents will also validate the URL
        contents = requests.get(str(attachment.last_url), headers = DEFAULT_HEADERS).content

        # handle audio
        if attachment.mime_type in KNOWN_AUDIO_FORMATS.values() or attachment.extension in KNOWN_AUDIO_FORMATS.keys():
            transcriber_tool = self.__di.tool_choice_resolver.require_tool(
                AudioTranscriber.TRANSCRIBER_TOOL_TYPE,
                default_tool_for(AudioTranscriber.TRANSCRIBER_TOOL_TYPE),
            )
            copywriter_tool = self.__di.tool_choice_resolver.require_tool(
                AudioTranscriber.COPYWRITER_TOOL_TYPE,
                default_tool_for(AudioTranscriber.COPYWRITER_TOOL_TYPE),
            )
            return self.__di.audio_transcriber(
                job_id = attachment.id,
                audio_url = str(attachment.last_url),
                transcriber_tool = transcriber_tool,
                copywriter_tool = copywriter_tool,
                def_extension = attachment.extension,
                audio_content = contents,
            ).execute()

        log.w(f"Unsupported attachment '{attachment.id}': {attachment.mime_type}; '.{attachment.extension}'")
        return None
