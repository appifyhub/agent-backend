from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.vectorstores import InMemoryVectorStore

from di.di import DI
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.integrations import prompt_resolvers
from util import log
from util.error_codes import DOCUMENT_SEARCH_FAILED, LLM_UNEXPECTED_RESPONSE
from util.errors import ExternalServiceError

DEFAULT_QUESTION = "What is this document about?"
SEARCH_RESULT_PAGES = 3


# Not tested as it's just a proxy
class DocumentSearch:

    EMBEDDING_TOOL_TYPE: ToolType = ToolType.embedding
    COPYWRITER_TOOL_TYPE: ToolType = ToolType.copywriting

    __job_id: str
    __embeddings: Embeddings
    __documents: list[Document]
    __additional_context: str
    __copywriter: BaseChatModel
    __di: DI

    def __init__(
        self,
        job_id: str,
        documents: list[Document],
        embedding_tool: ConfiguredTool,
        copywriter_tool: ConfiguredTool,
        di: DI,
        additional_context: str | None = None,
    ):
        self.__job_id = job_id
        self.__documents = documents
        log.t(f"DocumentSearch initialized with {len(documents)} document(s)")
        self.__additional_context = additional_context or DEFAULT_QUESTION
        self.__embeddings = di.openai_embeddings(embedding_tool)
        self.__copywriter = di.chat_langchain_model(copywriter_tool)
        self.__di = di

    def execute(self) -> str:
        log.d(f"Starting document search for job '{self.__job_id}'")
        try:
            # run the raw search first
            document_index = InMemoryVectorStore(self.__embeddings)
            document_index.add_documents(self.__documents)
            results = document_index.similarity_search(query = self.__additional_context, k = SEARCH_RESULT_PAGES)
            log.t(f"Document search returned {len(results)} similarity search results")
            search_results: str = "[Raw Document Search Results]\n\n"
            found_content = False
            if results:
                for result in results:
                    page_number = result.metadata.get("page", "Unknown") or "Unknown"
                    content = result.page_content or "<No result>"
                    search_results += f"[Chunk {page_number}]\n{content}\n\n---\n\n"
                    found_content = True
                search_results = search_results.strip()
            if not found_content:
                search_results = "<No results>"

            log.t("Invoking copywriter on search results")
            system_prompt = prompt_resolvers.document_search_and_response(self.__additional_context, self.__di.invoker_chat)
            copywriter_messages = [SystemMessage(system_prompt), HumanMessage(search_results)]
            answer = self.__copywriter.invoke(copywriter_messages)
            if not isinstance(answer, AIMessage):
                raise ExternalServiceError(f"Received a non-AI message from the model: {answer}", LLM_UNEXPECTED_RESPONSE)
            if not answer.content or not isinstance(answer.content, str):
                raise ExternalServiceError(f"Received an unexpected content from the model: {answer}", LLM_UNEXPECTED_RESPONSE)
            return f"Document Search Results:\n\n```\n{str(answer.content)}\n```"
        except ExternalServiceError:
            raise
        except Exception as e:
            raise ExternalServiceError(
                f"Document search failed for job '{self.__job_id}'",
                DOCUMENT_SEARCH_FAILED,
            ) from e
