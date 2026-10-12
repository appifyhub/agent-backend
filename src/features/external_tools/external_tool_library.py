from features.external_tools.external_tool import CostEstimate, ExternalTool, ToolType
from features.external_tools.external_tool_provider_library import (
    ANTHROPIC,
    COINMARKETCAP,
    GOOGLE_AI,
    INTERNAL,
    META,
    OPEN_AI,
    PERPLEXITY,
    RAPID_API,
    REPLICATE,
    TELEGRAM,
    TWELVE_DATA,
    XAI,
    X,
)

# Tools arrays are at the end of the file

###  Open AI  ###

GPT_5_6_LUNA = ExternalTool(
    id = "gpt-5.6-luna",
    name = "GPT 5.6 Luna",
    provider = OPEN_AI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 20,
        output_1m_tokens = 120,
    ),
)

GPT_5_6_TERRA = ExternalTool(
    id = "gpt-5.6-terra",
    name = "GPT 5.6 Terra",
    provider = OPEN_AI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 200,
        output_1m_tokens = 1200,
    ),
)

GPT_5_6_SOL = ExternalTool(
    id = "gpt-5.6-sol",
    name = "GPT 5.6 Sol",
    provider = OPEN_AI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 400,
        output_1m_tokens = 2000,
    ),
)

GPT_6_LUNA = ExternalTool(
    id = "gpt-6-luna",
    name = "GPT 6 Luna",
    provider = OPEN_AI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 10,
        output_1m_tokens = 50,
    ),
)

GPT_TRANSCRIBE = ExternalTool(
    id = "gpt-transcribe",
    name = "GPT Transcribe",
    provider = OPEN_AI,
    types = [ToolType.hearing],
    cost_estimate = CostEstimate(
        second_of_runtime = 0.0075,
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

CLAUDE_4_6_SONNET = ExternalTool(
    id = "claude-sonnet-4-6",
    name = "Claude Sonnet 4.6",
    provider = ANTHROPIC,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 300,
        output_1m_tokens = 1500,
        search_1m_tokens = 150,  # used with vision queries
    ),
)

CLAUDE_4_8_OPUS = ExternalTool(
    id = "claude-opus-4-8",
    name = "Claude Opus 4.8",
    provider = ANTHROPIC,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 500,
        output_1m_tokens = 2500,
        search_1m_tokens = 200,  # used with vision queries
    ),
)

CLAUDE_5_5_HAIKU = ExternalTool(
    id = "claude-haiku-5-5",
    name = "Claude Haiku 5.5",
    provider = ANTHROPIC,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 15,
        output_1m_tokens = 55,
        search_1m_tokens = 10,  # used with vision queries
    ),
)

CLAUDE_5_5_SONNET = ExternalTool(
    id = "claude-sonnet-5-5",
    name = "Claude Sonnet 5.5",
    provider = ANTHROPIC,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 200,
        output_1m_tokens = 1000,
        search_1m_tokens = 100,  # used with vision queries
    ),
)

CLAUDE_5_5_OPUS = ExternalTool(
    id = "claude-opus-5-5",
    name = "Claude Opus 5.5",
    provider = ANTHROPIC,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 400,
        output_1m_tokens = 2000,
        search_1m_tokens = 200,  # used with vision queries
    ),
)

CLAUDE_5_1_FABLE = ExternalTool(
    id = "claude-fable-5-1",
    name = "Claude Fable 5.1",
    provider = ANTHROPIC,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 1000,
        output_1m_tokens = 5000,
        search_1m_tokens = 500,  # used with vision queries
    ),
)

###  Google AI  ###

GEMINI_FLASH_LITE_LATEST = ExternalTool(
    id = "gemini-flash-lite-latest",
    name = "Gemini Flash Lite (Latest)",
    provider = GOOGLE_AI,
    types = [ToolType.chat, ToolType.copywriting, ToolType.vision],
    cost_estimate = CostEstimate(
        input_1m_tokens = 30,
        output_1m_tokens = 250,
        search_1m_tokens = 7,  # used with vision queries
    ),
)

GEMINI_FLASH_LATEST = ExternalTool(
    id = "gemini-flash-latest",
    name = "Gemini Flash (Latest)",
    provider = GOOGLE_AI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision, ToolType.search],
    cost_estimate = CostEstimate(
        input_1m_tokens = 150,
        output_1m_tokens = 750,
        search_1m_tokens = 100,  # used with vision queries
        web_search_query = 1.4,
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

NANO_BANANA_2_LITE = ExternalTool(
    id = "gemini-3.1-flash-lite-image",
    name = "Nano Banana 2 (Lite)",
    provider = GOOGLE_AI,
    types = [ToolType.images_gen],
    cost_estimate = CostEstimate(
        input_1m_tokens = 25,
        output_1m_tokens = 3000,
        output_image_1k = 4,
        output_image_2k = 4,
        output_image_4k = 4,
    ),
    max_input_images = 6,
)

NANO_BANANA_2_1 = ExternalTool(
    id = "gemini-nano-banana-2.1",
    name = "Nano Banana 2.1",
    provider = GOOGLE_AI,
    types = [ToolType.images_gen],
    cost_estimate = CostEstimate(
        input_1m_tokens = 150,
        output_1m_tokens = 3000,
        output_image_1k = 4,
        output_image_2k = 6,
        output_image_4k = 12,
    ),
    max_input_images = 14,
)

NANO_BANANA_PRO = ExternalTool(
    id = "gemini-3-pro-image",
    name = "Nano Banana Pro",
    provider = GOOGLE_AI,
    types = [ToolType.images_gen],
    cost_estimate = CostEstimate(
        input_1m_tokens = 200,
        output_1m_tokens = 12000,
        output_image_1k = 15,
        output_image_2k = 15,
        output_image_4k = 30,
    ),
    max_input_images = 14,
)

###  xAI  ###

GROK_4_3 = ExternalTool(
    id = "grok-4.3",
    name = "Grok 4.3",
    provider = XAI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision, ToolType.search],
    cost_estimate = CostEstimate(
        input_1m_tokens = 125,
        output_1m_tokens = 250,
        web_search_query = 0.5,
    ),
)

GROK_4_7 = ExternalTool(
    id = "grok-4.7",
    name = "Grok 4.7",
    provider = XAI,
    types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision, ToolType.search],
    cost_estimate = CostEstimate(
        input_1m_tokens = 200,
        output_1m_tokens = 600,
        web_search_query = 0.5,
    ),
)

IMAGE_GROK_IMAGINE = ExternalTool(
    id = "grok-imagine-image",
    name = "Grok Imagine Image",
    provider = XAI,
    types = [ToolType.images_gen],
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

IMAGE_GROK_IMAGINE_2 = ExternalTool(
    id = "grok-imagine-image-2.0",
    name = "Grok Imagine Image 2.0",
    provider = XAI,
    types = [ToolType.images_gen],
    cost_estimate = CostEstimate(
        output_image_1k = 6,
        output_image_2k = 8,
        input_image_1k = 1,
        input_image_2k = 1,
        input_image_4k = 1,
        input_image_8k = 1,
        input_image_12k = 1,
    ),
    max_input_images = 5,
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

IMAGE_FLUX_2_PRO = ExternalTool(
    id = "black-forest-labs/flux-2-pro",
    name = "Black Forest Labs: Flux 2 Pro",
    provider = REPLICATE,
    types = [ToolType.images_gen],
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

IMAGE_FLUX_2_MAX = ExternalTool(
    id = "black-forest-labs/flux-2-max",
    name = "Black Forest Labs: Flux 2 Max",
    provider = REPLICATE,
    types = [ToolType.images_gen],
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

IMAGE_FLUX_3 = ExternalTool(
    id = "black-forest-labs/flux-3-image",
    name = "Black Forest Labs: Flux 3 Image",
    provider = REPLICATE,
    types = [ToolType.images_gen],
    cost_estimate = CostEstimate(
        output_image_1k = 3,
        output_image_2k = 5,
        output_image_4k = 32,
    ),
    max_input_images = 10,
)

IMAGE_GPT_IMAGE_2_5_FLARE = ExternalTool(
    id = "openai/gpt-image-2.5-flare",
    name = "OpenAI: Image 2.5 Flare",
    provider = REPLICATE,
    types = [ToolType.images_gen],
    cost_estimate = CostEstimate(
        output_image_1k = 30,
        output_image_2k = 30,
        output_image_4k = 30,
    ),
    max_input_images = 10,
)

IMAGE_GPT_IMAGE_2_5_SUNBURST = ExternalTool(
    id = "openai/gpt-image-2.5-sunburst",
    name = "OpenAI: Image 2.5 Sunburst",
    provider = REPLICATE,
    types = [ToolType.images_gen],
    cost_estimate = CostEstimate(
        output_image_1k = 50,
        output_image_2k = 50,
        output_image_4k = 50,
    ),
    max_input_images = 10,
)

IMAGE_SEEDREAM_4 = ExternalTool(
    id = "bytedance/seedream-4",
    name = "ByteDance: SeeDream 4",
    provider = REPLICATE,
    types = [ToolType.images_gen],
    cost_estimate = CostEstimate(
        output_image_1k = 3,
        output_image_2k = 3,
        output_image_4k = 3,
    ),
    max_input_images = 10,
)

IMAGE_SEEDREAM_4_5 = ExternalTool(
    id = "bytedance/seedream-4.5",
    name = "ByteDance: SeeDream 4.5",
    provider = REPLICATE,
    types = [ToolType.images_gen],
    cost_estimate = CostEstimate(
        output_image_1k = 4,
        output_image_2k = 4,
        output_image_4k = 4,
    ),
    max_input_images = 14,
)

IMAGE_SEEDREAM_5_PRO = ExternalTool(
    id = "bytedance/seedream-5-pro",
    name = "ByteDance: SeeDream 5 Pro",
    provider = REPLICATE,
    types = [ToolType.images_gen],
    cost_estimate = CostEstimate(
        output_image_1k = 4.5,
        output_image_2k = 9,
        output_image_4k = 9,
    ),
    max_input_images = 10,
)

IMAGE_GOOGLE_NANO_BANANA_2_1 = ExternalTool(
    id = "google/nano-banana-2.1",
    name = "Google: Nano Banana 2.1",
    provider = REPLICATE,
    types = [ToolType.images_gen],
    cost_estimate = CostEstimate(
        output_image_1k = 4,
        output_image_2k = 6,
        output_image_4k = 12,
    ),
    max_input_images = 14,
)

IMAGE_GOOGLE_NANO_BANANA_PRO = ExternalTool(
    id = "google/nano-banana-pro",
    name = "Google: Nano Banana Pro",
    provider = REPLICATE,
    types = [ToolType.images_gen],
    cost_estimate = CostEstimate(
        output_image_1k = 15,
        output_image_2k = 15,
        output_image_4k = 30,
    ),
    max_input_images = 5,
)

VIDEO_GEN_P_VIDEO = ExternalTool(
    id = "prunaai/p-video",
    name = "Pruna AI: P-Video",
    provider = REPLICATE,
    types = [ToolType.videos_gen],
    cost_estimate = CostEstimate(
        output_video_1k_second = 2,
        output_video_2k_second = 4,
        output_video_4k_second = 4,
    ),
    max_input_images = 1,
)

VIDEO_GEN_RAY_3_2 = ExternalTool(
    id = "luma/ray-3.2",
    name = "Luma: Ray 3.2",
    provider = REPLICATE,
    types = [ToolType.videos_gen],
    cost_estimate = CostEstimate(
        output_video_1k_second = 8,
        output_video_2k_second = 30,
        output_video_4k_second = 30,
    ),
    max_input_images = 1,
)

VIDEO_GEN_SEEDANCE_2_0_FAST = ExternalTool(
    id = "bytedance/seedance-2.0-fast",
    name = "ByteDance: Seedance 2.0 Fast",
    provider = REPLICATE,
    types = [ToolType.videos_gen],
    cost_estimate = CostEstimate(
        output_video_1k_second = 15,
        output_video_2k_second = 15,
        output_video_4k_second = 15,
    ),
    max_input_images = 9,
)

VIDEO_GEN_VEO_3_1_FAST = ExternalTool(
    id = "google/veo-3.1-fast",
    name = "Google: Veo 3.1 Fast",
    provider = REPLICATE,
    types = [ToolType.videos_gen],
    cost_estimate = CostEstimate(
        output_video_1k_second = 15,
        output_video_2k_second = 15,
        output_video_4k_second = 15,
    ),
    max_input_images = 1,
)

VIDEO_GEN_GEMINI_OMNI_1_1 = ExternalTool(
    id = "google/gemini-omni-1.1",
    name = "Google: Gemini Omni 1.1 Flash",
    provider = REPLICATE,
    types = [ToolType.videos_gen],
    cost_estimate = CostEstimate(
        output_video_1k_second = 15,
        output_video_2k_second = 25,
        output_video_4k_second = 45,
    ),
    max_input_images = 1,
)

VIDEO_GEN_SEEDANCE_2_5 = ExternalTool(
    id = "bytedance/seedance-2.5",
    name = "ByteDance: Seedance 2.5",
    provider = REPLICATE,
    types = [ToolType.videos_gen],
    cost_estimate = CostEstimate(
        output_video_1k_second = 25,
        output_video_2k_second = 25,
        output_video_4k_second = 25,
    ),
    max_input_images = 30,
)

VIDEO_GEN_VEO_3_1 = ExternalTool(
    id = "google/veo-3.1",
    name = "Google: Veo 3.1",
    provider = REPLICATE,
    types = [ToolType.videos_gen],
    cost_estimate = CostEstimate(
        output_video_1k_second = 40,
        output_video_2k_second = 40,
        output_video_4k_second = 40,
    ),
    max_input_images = 3,
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

TWELVE_DATA_STOCK_QUOTE = ExternalTool(
    id = "quote",
    name = "Twelve Data's Stock Quote",
    provider = TWELVE_DATA,
    types = [ToolType.api_stock_quote],
    cost_estimate = CostEstimate(
        api_call = 0,
    ),
)

###  Messaging Platform Integrations  ###

TELEGRAM_MESSAGE_DELIVERY = ExternalTool(
    id = "telegram-message-delivery",
    name = "Telegram message delivery",
    provider = TELEGRAM,
    types = [ToolType.message_delivery],
    cost_estimate = CostEstimate(api_call = 0),
)

###  Meta  ###

WHATSAPP_MESSAGE_DELIVERY = ExternalTool(
    id = "whatsapp-message-delivery",
    name = "WhatsApp message delivery",
    provider = META,
    types = [ToolType.message_delivery],
    cost_estimate = CostEstimate(api_call = 0),
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
    GPT_5_6_LUNA,
    GPT_5_6_TERRA,
    GPT_5_6_SOL,
    GPT_6_LUNA,
    GPT_TRANSCRIBE,
    TEXT_EMBEDDING_3_SMALL,
    TEXT_EMBEDDING_5_LARGE,
    # Anthropic
    CLAUDE_4_6_SONNET,
    CLAUDE_4_8_OPUS,
    CLAUDE_5_5_HAIKU,
    CLAUDE_5_5_SONNET,
    CLAUDE_5_5_OPUS,
    CLAUDE_5_1_FABLE,
    # Google AI
    GEMINI_FLASH_LITE_LATEST,
    GEMINI_FLASH_LATEST,
    GEMINI_PRO_LATEST,
    NANO_BANANA_2_LITE,
    NANO_BANANA_2_1,
    NANO_BANANA_PRO,
    # xAI
    GROK_4_3,
    GROK_4_7,
    IMAGE_GROK_IMAGINE,
    IMAGE_GROK_IMAGINE_2,
    # Perplexity
    SONAR,
    SONAR_PRO,
    SONAR_REASONING_PRO,
    SONAR_DEEP_RESEARCH,
    # Replicate
    IMAGE_FLUX_2_PRO,
    IMAGE_FLUX_2_MAX,
    IMAGE_FLUX_3,
    IMAGE_GPT_IMAGE_2_5_FLARE,
    IMAGE_GPT_IMAGE_2_5_SUNBURST,
    IMAGE_SEEDREAM_4,
    IMAGE_SEEDREAM_4_5,
    IMAGE_SEEDREAM_5_PRO,
    IMAGE_GOOGLE_NANO_BANANA_2_1,
    IMAGE_GOOGLE_NANO_BANANA_PRO,
    VIDEO_GEN_P_VIDEO,
    VIDEO_GEN_RAY_3_2,
    VIDEO_GEN_SEEDANCE_2_0_FAST,
    VIDEO_GEN_VEO_3_1_FAST,
    VIDEO_GEN_GEMINI_OMNI_1_1,
    VIDEO_GEN_SEEDANCE_2_5,
    VIDEO_GEN_VEO_3_1,
    # API Integrations
    FIAT_CURRENCY_EXCHANGE,
    X_READ_POST,
    CRYPTO_CURRENCY_EXCHANGE,
    TWELVE_DATA_STOCK_QUOTE,
    #  Messaging Platform Integrations
    TELEGRAM_MESSAGE_DELIVERY,
    WHATSAPP_MESSAGE_DELIVERY,
    # Internal
    TRANSFER_TOOL,
]
