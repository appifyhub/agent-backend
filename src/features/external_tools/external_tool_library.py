from features.external_tools.external_tool import CostEstimate, ExternalTool, ToolType
from features.external_tools.external_tool_provider_library import (
    ANTHROPIC,
    COINMARKETCAP,
    GOOGLE_AI,
    INTERNAL,
    OPEN_AI,
    PERPLEXITY,
    RAPID_API,
    REPLICATE,
    XAI,
    X,
)

# Tools arrays are at the end of the file

###  Open AI  ###

GPT_4_1 = ExternalTool(
    id = "gpt-4.1",
    name = "GPT 4.1",
    provider = OPEN_AI,
    types = [ToolType.chat, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 200,
        output_1m_tokens = 800,
    ),
)

GPT_4_1_MINI = ExternalTool(
    id = "gpt-4.1-mini",
    name = "GPT 4.1 Mini",
    provider = OPEN_AI,
    types = [ToolType.chat, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 40,
        output_1m_tokens = 160,
    ),
)

GPT_5 = ExternalTool(
    id = "gpt-5",
    name = "GPT 5",
    provider = OPEN_AI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 125,
        output_1m_tokens = 1000,
    ),
)

GPT_5_MINI = ExternalTool(
    id = "gpt-5-mini",
    name = "GPT 5 Mini",
    provider = OPEN_AI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 25,
        output_1m_tokens = 200,
    ),
)

GPT_5_NANO = ExternalTool(
    id = "gpt-5-nano",
    name = "GPT 5 Nano",
    provider = OPEN_AI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 5,
        output_1m_tokens = 40,
    ),
)

GPT_5_1 = ExternalTool(
    id = "gpt-5.1",
    name = "GPT 5.1",
    provider = OPEN_AI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 125,
        output_1m_tokens = 1000,
    ),
)

GPT_5_2 = ExternalTool(
    id = "gpt-5.2",
    name = "GPT 5.2",
    provider = OPEN_AI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 175,
        output_1m_tokens = 1400,
    ),
)

GPT_5_4 = ExternalTool(
    id = "gpt-5.4",
    name = "GPT 5.4",
    provider = OPEN_AI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 250,
        output_1m_tokens = 1500,
    ),
)

GPT_5_5 = ExternalTool(
    id = "gpt-5.5",
    name = "GPT 5.5",
    provider = OPEN_AI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 500,
        output_1m_tokens = 3000,
    ),
)

GPT_4O = ExternalTool(
    id = "gpt-4o",
    name = "GPT 4o",
    provider = OPEN_AI,
    types = [ToolType.chat, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 250,
        output_1m_tokens = 1000,
    ),
)

GPT_4O_MINI = ExternalTool(
    id = "gpt-4o-mini",
    name = "GPT 4o Mini",
    provider = OPEN_AI,
    types = [ToolType.chat, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 15,
        output_1m_tokens = 60,
    ),
)

GPT_4O_TRANSCRIBE = ExternalTool(
    id = "gpt-4o-transcribe",
    name = "GPT 4o Transcribe",
    provider = OPEN_AI,
    types = [ToolType.hearing],
    cost_estimate = CostEstimate(
        input_1m_tokens = 600,
        output_1m_tokens = 1000,
    ),
)

GPT_4O_MINI_TRANSCRIBE = ExternalTool(
    id = "gpt-4o-mini-transcribe",
    name = "GPT 4o Mini Transcribe",
    provider = OPEN_AI,
    types = [ToolType.hearing],
    cost_estimate = CostEstimate(
        input_1m_tokens = 300,
        output_1m_tokens = 500,
    ),
)

WHISPER_1 = ExternalTool(
    id = "whisper-1",
    name = "Whisper 1",
    provider = OPEN_AI,
    types = [ToolType.hearing],
    cost_estimate = CostEstimate(
        second_of_runtime = 0.01,
    ),
)

TEXT_EMBEDDING_3_SMALL = ExternalTool(
    id = "text-embedding-3-small",
    name = "Text Embedding 3 Small",
    provider = OPEN_AI,
    types = [ToolType.embedding],
    cost_estimate = CostEstimate(
        input_1m_tokens = 2,
        output_1m_tokens = 2,  # probably useless for embeddings
    ),
)

TEXT_EMBEDDING_5_LARGE = ExternalTool(
    id = "text-embedding-3-large",
    name = "Text Embedding 3 Large",
    provider = OPEN_AI,
    types = [ToolType.embedding],
    cost_estimate = CostEstimate(
        input_1m_tokens = 15,
        output_1m_tokens = 15,  # probably useless for embeddings
    ),
)

###  Anthropic  ###

CLAUDE_4_5_HAIKU = ExternalTool(
    id = "claude-haiku-4-5",
    name = "Claude 4.5 Haiku",
    provider = ANTHROPIC,
    types = [ToolType.chat, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 100,
        output_1m_tokens = 500,
        search_1m_tokens = 50,  # used with vision queries
    ),
)

CLAUDE_4_5_SONNET = ExternalTool(
    id = "claude-sonnet-4-5",
    name = "Claude 4.5 Sonnet",
    provider = ANTHROPIC,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 300,
        output_1m_tokens = 1500,
        search_1m_tokens = 150,  # used with vision queries
    ),
)

CLAUDE_4_5_OPUS = ExternalTool(
    id = "claude-opus-4-5",
    name = "Claude 4.5 Opus",
    provider = ANTHROPIC,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 500,
        output_1m_tokens = 2500,
        search_1m_tokens = 200,  # used with vision queries
    ),
)

CLAUDE_4_6_SONNET = ExternalTool(
    id = "claude-sonnet-4-6",
    name = "Claude 4.6 Sonnet",
    provider = ANTHROPIC,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 300,
        output_1m_tokens = 1500,
        search_1m_tokens = 150,  # used with vision queries
    ),
)

CLAUDE_4_6_OPUS = ExternalTool(
    id = "claude-opus-4-6",
    name = "Claude 4.6 Opus",
    provider = ANTHROPIC,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 500,
        output_1m_tokens = 2500,
        search_1m_tokens = 200,  # used with vision queries
    ),
)

CLAUDE_4_7_OPUS = ExternalTool(
    id = "claude-opus-4-7",
    name = "Claude 4.7 Opus",
    provider = ANTHROPIC,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 500,
        output_1m_tokens = 2500,
        search_1m_tokens = 200,  # used with vision queries
    ),
)

###  Google AI  ###

GEMINI_FLASH_LITE_LATEST = ExternalTool(
    id = "gemini-flash-lite-latest",
    name = "Gemini Flash Lite (Latest)",
    provider = GOOGLE_AI,
    types = [ToolType.chat, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 10,
        output_1m_tokens = 40,
        search_1m_tokens = 5,  # used with vision queries
    ),
)

GEMINI_FLASH_LATEST = ExternalTool(
    id = "gemini-flash-latest",
    name = "Gemini Flash (Latest)",
    provider = GOOGLE_AI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 150,
        output_1m_tokens = 900,
        search_1m_tokens = 75,  # used with vision queries
    ),
)

GEMINI_PRO_LATEST = ExternalTool(
    id = "gemini-pro-latest",
    name = "Gemini Pro (Latest)",
    provider = GOOGLE_AI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 300,
        output_1m_tokens = 1500,
        search_1m_tokens = 150,  # used with vision queries
    ),
)

NANO_BANANA = ExternalTool(
    id = "gemini-2.5-flash-image",
    name = "Nano Banana",
    provider = GOOGLE_AI,
    types = [ToolType.images_gen, ToolType.images_edit],
    cost_estimate = CostEstimate(
        input_1m_tokens = 50,
        output_1m_tokens = 300,
        output_image_1k = 4,
        output_image_2k = 4,
        output_image_4k = 4,
    ),
    max_input_images = 3,
)

NANO_BANANA_PRO = ExternalTool(
    id = "gemini-3-pro-image-preview",
    name = "Nano Banana Pro",
    provider = GOOGLE_AI,
    types = [ToolType.images_gen, ToolType.images_edit],
    cost_estimate = CostEstimate(
        input_1m_tokens = 200,
        output_1m_tokens = 12000,
        output_image_1k = 15,
        output_image_2k = 15,
        output_image_4k = 30,
    ),
    max_input_images = 5,
)

NANO_BANANA_2 = ExternalTool(
    id = "gemini-3.1-flash-image-preview",
    name = "Nano Banana 2",
    provider = GOOGLE_AI,
    types = [ToolType.images_gen, ToolType.images_edit],
    cost_estimate = CostEstimate(
        input_1m_tokens = 50,
        output_1m_tokens = 6000,
        output_image_1k = 7,
        output_image_2k = 11,
        output_image_4k = 16,
    ),
    max_input_images = 14,
)

###  xAI  ###

GROK_4_20_NON_REASONING = ExternalTool(
    id = "grok-4.20-non-reasoning",
    name = "Grok 4.20",
    provider = XAI,
    types = [ToolType.chat, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 200,
        output_1m_tokens = 600,
    ),
)

GROK_4_20_REASONING = ExternalTool(
    id = "grok-4.20-reasoning",
    name = "Grok 4.20 (Reasoning)",
    provider = XAI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 200,
        output_1m_tokens = 600,
    ),
)

GROK_4_3 = ExternalTool(
    id = "grok-4.3",
    name = "Grok 4.3",
    provider = XAI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 200,
        output_1m_tokens = 600,
    ),
)

IMAGE_GEN_GROK_IMAGINE = ExternalTool(
    id = "grok-imagine-image",
    name = "Grok Imagine Image",
    provider = XAI,
    types = [ToolType.images_gen, ToolType.images_edit],
    cost_estimate = CostEstimate(
        output_image_1k = 2,
        output_image_2k = 2,
        output_image_4k = 2,
        input_image_1k = 0.2,
        input_image_2k = 0.2,
        input_image_4k = 0.2,
        input_image_8k = 0.2,
        input_image_12k = 0.2,
    ),
    max_input_images = 5,
)

IMAGE_GEN_GROK_IMAGINE_QUALITY = ExternalTool(
    id = "grok-imagine-image-quality",
    name = "Grok Imagine Image (Quality)",
    provider = XAI,
    types = [ToolType.images_gen, ToolType.images_edit],
    cost_estimate = CostEstimate(
        output_image_1k = 5,
        output_image_2k = 7,
        output_image_4k = 7,
        input_image_1k = 0.2,
        input_image_2k = 0.2,
        input_image_4k = 0.2,
        input_image_8k = 0.2,
        input_image_12k = 0.2,
    ),
    max_input_images = 1,
)

###  Perplexity  ###

SONAR = ExternalTool(
    id = "sonar",
    name = "Sonar",
    provider = PERPLEXITY,
    types = [ToolType.chat, ToolType.copywriting, ToolType.search],
    cost_estimate = CostEstimate(
        input_1m_tokens = 100,
        output_1m_tokens = 100,
        search_1m_tokens = 300,
        api_call = 1,
    ),
)

SONAR_PRO = ExternalTool(
    id = "sonar-pro",
    name = "Sonar Pro",
    provider = PERPLEXITY,
    types = [ToolType.chat, ToolType.copywriting, ToolType.search],
    cost_estimate = CostEstimate(
        input_1m_tokens = 300,
        output_1m_tokens = 1500,
        search_1m_tokens = 300,
        api_call = 1,
    ),
)

SONAR_REASONING_PRO = ExternalTool(
    id = "sonar-reasoning-pro",
    name = "Sonar Pro (Reasoning)",
    provider = PERPLEXITY,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.search],
    cost_estimate = CostEstimate(
        input_1m_tokens = 200,
        output_1m_tokens = 800,
        search_1m_tokens = 300,
        api_call = 1,
    ),
)

SONAR_DEEP_RESEARCH = ExternalTool(
    id = "sonar-deep-research",
    name = "Sonar Deep Research",
    provider = PERPLEXITY,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.search],
    cost_estimate = CostEstimate(
        input_1m_tokens = 200,
        output_1m_tokens = 800,
        search_1m_tokens = 300,
        api_call = 5,
    ),
)

###  Replicate  ###

IMAGE_GEN_FLUX_1_1 = ExternalTool(
    id = "black-forest-labs/flux-1.1-pro",
    name = "Black Forest Labs: Flux 1.1 Pro",
    provider = REPLICATE,
    types = [ToolType.images_gen],
    cost_estimate = CostEstimate(
        output_image_1k = 4,
        output_image_2k = 4,
        output_image_4k = 4,
    ),
)

IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO = ExternalTool(
    id = "black-forest-labs/flux-kontext-pro",
    name = "Black Forest Labs: Flux Kontext Pro",
    provider = REPLICATE,
    types = [ToolType.images_gen, ToolType.images_edit],
    cost_estimate = CostEstimate(
        output_image_1k = 4,
        output_image_2k = 4,
        output_image_4k = 4,
    ),
    max_input_images = 1,
)

IMAGE_GEN_EDIT_FLUX_2_PRO = ExternalTool(
    id = "black-forest-labs/flux-2-pro",
    name = "Black Forest Labs: Flux 2 Pro",
    provider = REPLICATE,
    types = [ToolType.images_gen, ToolType.images_edit],
    cost_estimate = CostEstimate(
        output_image_1k = 2,
        output_image_2k = 3,
        output_image_4k = 6,
        input_image_1k = 2,
        input_image_2k = 3,
        input_image_4k = 6,
        input_image_8k = 12,
        input_image_12k = 18,
        api_call = 2,
    ),
    max_input_images = 8,
)

IMAGE_GEN_EDIT_FLUX_2_MAX = ExternalTool(
    id = "black-forest-labs/flux-2-max",
    name = "Black Forest Labs: Flux 2 Max",
    provider = REPLICATE,
    types = [ToolType.images_gen, ToolType.images_edit],
    cost_estimate = CostEstimate(
        output_image_1k = 3,
        output_image_2k = 6,
        output_image_4k = 12,
        input_image_1k = 3,
        input_image_2k = 6,
        input_image_4k = 12,
        input_image_8k = 24,
        input_image_12k = 36,
        api_call = 4,
    ),
    max_input_images = 8,
)

IMAGE_GEN_EDIT_GPT_IMAGE_1_5 = ExternalTool(
    id = "openai/gpt-image-1.5",
    name = "OpenAI: GPT Image 1.5",
    provider = REPLICATE,
    types = [ToolType.images_gen, ToolType.images_edit],
    cost_estimate = CostEstimate(
        output_image_1k = 14,
        output_image_2k = 14,
        output_image_4k = 14,
    ),
    max_input_images = 16,
)

IMAGE_GEN_EDIT_GPT_IMAGE_2 = ExternalTool(
    id = "openai/gpt-image-2",
    name = "OpenAI: GPT Image 2",
    provider = REPLICATE,
    types = [ToolType.images_gen, ToolType.images_edit],
    cost_estimate = CostEstimate(
        output_image_1k = 13,
        output_image_2k = 13,
        output_image_4k = 13,
    ),
    max_input_images = 16,
)


IMAGE_GEN_EDIT_SEEDREAM_4 = ExternalTool(
    id = "bytedance/seedream-4",
    name = "ByteDance: SeeDream 4",
    provider = REPLICATE,
    types = [ToolType.images_gen, ToolType.images_edit],
    cost_estimate = CostEstimate(
        output_image_1k = 3,
        output_image_2k = 3,
        output_image_4k = 3,
    ),
    max_input_images = 10,
)

IMAGE_GEN_EDIT_SEEDREAM_4_5 = ExternalTool(
    id = "bytedance/seedream-4.5",
    name = "ByteDance: SeeDream 4.5",
    provider = REPLICATE,
    types = [ToolType.images_gen, ToolType.images_edit],
    cost_estimate = CostEstimate(
        output_image_1k = 4,
        output_image_2k = 4,
        output_image_4k = 4,
    ),
    max_input_images = 14,
)

IMAGE_GEN_EDIT_GOOGLE_NANO_BANANA = ExternalTool(
    id = "google/nano-banana",
    name = "Google: Nano Banana",
    provider = REPLICATE,
    types = [ToolType.images_gen, ToolType.images_edit],
    cost_estimate = CostEstimate(
        output_image_1k = 4,
        output_image_2k = 4,
        output_image_4k = 4,
    ),
    max_input_images = 3,
)

IMAGE_GEN_EDIT_GOOGLE_NANO_BANANA_PRO = ExternalTool(
    id = "google/nano-banana-pro",
    name = "Google: Nano Banana Pro",
    provider = REPLICATE,
    types = [ToolType.images_gen, ToolType.images_edit],
    cost_estimate = CostEstimate(
        output_image_1k = 15,
        output_image_2k = 15,
        output_image_4k = 30,
    ),
    max_input_images = 5,
)

IMAGE_GEN_EDIT_GOOGLE_NANO_BANANA_2 = ExternalTool(
    id = "google/nano-banana-2",
    name = "Google: Nano Banana 2",
    provider = REPLICATE,
    types = [ToolType.images_gen, ToolType.images_edit],
    cost_estimate = CostEstimate(
        output_image_1k = 7,
        output_image_2k = 11,
        output_image_4k = 16,
    ),
    max_input_images = 14,
)

###  API Integrations  ###

FIAT_CURRENCY_EXCHANGE = ExternalTool(
    id = "currency-converter5.p.rapidapi.com",
    name = "RapidAPI's Fiat Converter",
    provider = RAPID_API,
    types = [ToolType.api_fiat_exchange],
    cost_estimate = CostEstimate(
        api_call = 0,
    ),
)

X_READ_POST = ExternalTool(
    id = "x.api-v2-post.read",  # made-up ID, not an actual API path
    name = "Post Reader for X",
    provider = X,
    types = [ToolType.api_twitter],
    cost_estimate = CostEstimate(
        api_call = 0.5,
    ),
)

CRYPTO_CURRENCY_EXCHANGE = ExternalTool(
    id = "v1.cryptocurrency.quotes.latest",
    name = "CoinMarketCap's Crypto Converter",
    provider = COINMARKETCAP,
    types = [ToolType.api_crypto_exchange],
    cost_estimate = CostEstimate(
        api_call = 0,
    ),
)

###  Internal  ###

TRANSFER_TOOL = ExternalTool(
    id = "credit_transfer",
    name = "Internal Credit Transfer",
    provider = INTERNAL,
    types = [ToolType.credit_transfer],
    cost_estimate = CostEstimate(),
)

###  All External Tools  ###

ALL_EXTERNAL_TOOLS = [
    # Open AI
    GPT_4_1,
    GPT_4_1_MINI,
    GPT_5,
    GPT_5_MINI,
    GPT_5_NANO,
    GPT_5_1,
    GPT_5_2,
    GPT_5_4,
    GPT_5_5,
    GPT_4O,
    GPT_4O_MINI,
    GPT_4O_TRANSCRIBE,
    GPT_4O_MINI_TRANSCRIBE,
    WHISPER_1,
    TEXT_EMBEDDING_3_SMALL,
    TEXT_EMBEDDING_5_LARGE,
    # Anthropic
    CLAUDE_4_5_HAIKU,
    CLAUDE_4_5_SONNET,
    CLAUDE_4_5_OPUS,
    CLAUDE_4_6_SONNET,
    CLAUDE_4_6_OPUS,
    CLAUDE_4_7_OPUS,
    # Google AI
    GEMINI_FLASH_LITE_LATEST,
    GEMINI_FLASH_LATEST,
    GEMINI_PRO_LATEST,
    NANO_BANANA,
    NANO_BANANA_PRO,
    NANO_BANANA_2,
    # xAI
    GROK_4_20_NON_REASONING,
    GROK_4_20_REASONING,
    GROK_4_3,
    IMAGE_GEN_GROK_IMAGINE,
    IMAGE_GEN_GROK_IMAGINE_QUALITY,
    # Perplexity
    SONAR,
    SONAR_PRO,
    SONAR_REASONING_PRO,
    SONAR_DEEP_RESEARCH,
    # Replicate
    IMAGE_GEN_FLUX_1_1,
    IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO,
    IMAGE_GEN_EDIT_FLUX_2_PRO,
    IMAGE_GEN_EDIT_FLUX_2_MAX,
    IMAGE_GEN_EDIT_GPT_IMAGE_1_5,
    IMAGE_GEN_EDIT_GPT_IMAGE_2,
    IMAGE_GEN_EDIT_SEEDREAM_4,
    IMAGE_GEN_EDIT_SEEDREAM_4_5,
    IMAGE_GEN_EDIT_GOOGLE_NANO_BANANA,
    IMAGE_GEN_EDIT_GOOGLE_NANO_BANANA_PRO,
    IMAGE_GEN_EDIT_GOOGLE_NANO_BANANA_2,
    # API Integrations
    FIAT_CURRENCY_EXCHANGE,
    X_READ_POST,
    CRYPTO_CURRENCY_EXCHANGE,
    # Internal
    TRANSFER_TOOL,
]
