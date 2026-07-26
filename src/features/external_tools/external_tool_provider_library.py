from features.external_tools.external_tool import ExternalToolProvider

# All providers array is at the end of the file

OPEN_AI = ExternalToolProvider(
    id = "open-ai",
    name = "OpenAI",
    token_management_url = "https://platform.openai.com/api-keys",
    token_format = "sk-...abc123",
    tools = ["ChatGPT", "Whisper", "Embedding"],
)

ANTHROPIC = ExternalToolProvider(
    id = "anthropic",
    name = "Anthropic",
    token_management_url = "https://console.anthropic.com/settings/keys",
    token_format = "sk-ant-...abc123",
    tools = ["Claude"],
)

GOOGLE_AI = ExternalToolProvider(
    id = "google-ai",
    name = "Google AI",
    token_management_url = "https://aistudio.google.com/app/apikey",
    token_format = "AI...abc123",
    tools = ["Gemini"],
)

XAI = ExternalToolProvider(
    id = "x_ai",
    name = "xAI",
    token_management_url = "https://console.x.ai",
    token_format = "xai-...abc123",
    tools = ["Grok", "Grok Imagine"],
)

PERPLEXITY = ExternalToolProvider(
    id = "perplexity",
    name = "Perplexity",
    token_management_url = "https://www.perplexity.ai/account/api/keys",
    token_format = "pplx-...abc123",
    tools = ["Web Search", "Deep Research"],
)

REPLICATE = ExternalToolProvider(
    id = "replicate",
    name = "Replicate",
    token_management_url = "https://replicate.com/account/api-tokens",
    token_format = "r8_...abc123",
    tools = ["Image-Gen", "Image-Edit", "Video-Gen"],
)

RAPID_API = ExternalToolProvider(
    id = "rapid-api",
    name = "RapidAPI",
    token_management_url = "https://docs.rapidapi.com/docs/configuring-api-security",
    token_format = "abc...123",
    tools = ["Currency", "Weather"],
)

X = ExternalToolProvider(
    id = "x",
    name = "X / Twitter",
    token_management_url = "https://console.x.com",
    token_format = "AAAA...xyz",
    tools = ["Posts", "Users", "Trends"],
)

COINMARKETCAP = ExternalToolProvider(
    id = "coinmarketcap-api",
    name = "CoinMarketCap API",
    token_management_url = "https://pro.coinmarketcap.com/account",
    token_format = "abcd...-...-...1234",
    tools = ["Crypto"],
)

TWELVE_DATA = ExternalToolProvider(
    id = "twelve-data",
    name = "Twelve Data",
    token_management_url = "https://twelvedata.com/account/api-keys",
    token_format = "abc...123",
    tools = ["Stocks"],
)

INTERNAL = ExternalToolProvider(
    id = "internal",
    name = "Internal",
    token_management_url = "https://to.appifyhub.com/agent",
    token_format = "eyJ...abc123",
    tools = ["Credits"],
)


ALL_PROVIDERS = [
    OPEN_AI,
    ANTHROPIC,
    GOOGLE_AI,
    XAI,
    PERPLEXITY,
    REPLICATE,
    RAPID_API,
    X,
    COINMARKETCAP,
    TWELVE_DATA,
    INTERNAL,
]
