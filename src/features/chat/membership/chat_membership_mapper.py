from db.model.chat_membership import ChatMembershipDB
from features.chat.membership.chat_membership import ChatMembership


def domain(db_model: ChatMembershipDB | None) -> ChatMembership | None:
    if db_model is None:
        return None

    return ChatMembership(
        user_id = db_model.user_id,
        chat_id = db_model.chat_id,
        is_admin = db_model.is_admin,
        use_about_me = db_model.use_about_me,
        use_custom_prompt = db_model.use_custom_prompt,
        max_output_tokens = db_model.max_output_tokens,
        max_chat_history_depth = db_model.max_chat_history_depth,
        max_iterations = db_model.max_iterations,
    )


def db(domain_model: ChatMembership | None) -> ChatMembershipDB | None:
    if domain_model is None:
        return None

    return ChatMembershipDB(
        user_id = domain_model.user_id,
        chat_id = domain_model.chat_id,
        is_admin = domain_model.is_admin,
        use_about_me = domain_model.use_about_me,
        use_custom_prompt = domain_model.use_custom_prompt,
        max_output_tokens = domain_model.max_output_tokens,
        max_chat_history_depth = domain_model.max_chat_history_depth,
        max_iterations = domain_model.max_iterations,
    )
