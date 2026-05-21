from pydantic import BaseModel


class UserChatConfigPayload(BaseModel):
    use_about_me: bool
    use_custom_prompt: bool
    max_output_tokens: int
    max_chat_history_depth: int
    max_iterations: int
