from sqlalchemy.orm import Session

from db.crud.user import UserCRUD
from db.sql import initialize_db
from features.accounting.purchases.purchase_record_repo import PurchaseRecordRepository
from features.accounting.usage.usage_record_repo import UsageRecordRepository
from features.chat.attachment.chat_message_attachment_repo import ChatMessageAttachmentRepository
from features.chat.config.chat_config_repo import ChatConfigRepository
from features.chat.membership.chat_membership_repo import ChatMembershipRepository
from features.chat.message.chat_message_repo import ChatMessageRepository
from features.currencies.price_alert_repo import PriceAlertRepository
from features.sponsorships.sponsorship_repo import SponsorshipRepository
from features.tools_cache.tools_cache_repo import ToolsCacheRepository
from features.users.user_repo import UserRepository


class SQLUtil:

    __session: Session
    __is_session_active: bool

    def __init__(self):
        self.__is_session_active = False
        self.start_session()
        self.__is_session_active = True

    def start_session(self) -> Session:
        # noinspection PyPep8Naming
        engine, LocalSession = initialize_db("sqlite:///:memory:", multi_connection_setup = False)

        if self.__is_session_active:
            self.end_session()

        self.__session = LocalSession()
        self.__is_session_active = True

        return self.__session

    def get_session(self):
        return self.__session

    def end_session(self):
        self.__session.close()
        self.__is_session_active = False

    def chat_config_repo(self) -> ChatConfigRepository:
        if not self.__is_session_active:
            self.start_session()
        return ChatConfigRepository(self.__session)

    def chat_membership_repo(self) -> ChatMembershipRepository:
        if not self.__is_session_active:
            self.start_session()
        return ChatMembershipRepository(self.__session)

    def chat_message_repo(self) -> ChatMessageRepository:
        if not self.__is_session_active:
            self.start_session()
        return ChatMessageRepository(self.__session)

    def chat_message_attachment_repo(self) -> ChatMessageAttachmentRepository:
        if not self.__is_session_active:
            self.start_session()
        return ChatMessageAttachmentRepository(self.__session)

    def sponsorship_repo(self) -> SponsorshipRepository:
        if not self.__is_session_active:
            self.start_session()
        return SponsorshipRepository(self.__session)

    def tools_cache_repo(self) -> ToolsCacheRepository:
        if not self.__is_session_active:
            self.start_session()
        return ToolsCacheRepository(self.__session)

    def user_crud(self) -> UserCRUD:
        if not self.__is_session_active:
            self.start_session()
        return UserCRUD(self.__session)

    def user_repo(self) -> UserRepository:
        if not self.__is_session_active:
            self.start_session()
        return UserRepository(self.__session)

    def price_alert_repo(self) -> PriceAlertRepository:
        if not self.__is_session_active:
            self.start_session()
        return PriceAlertRepository(self.__session)

    def usage_record_repo(self) -> UsageRecordRepository:
        if not self.__is_session_active:
            self.start_session()
        return UsageRecordRepository(self.__session)

    def purchase_record_repo(self) -> PurchaseRecordRepository:
        if not self.__is_session_active:
            self.start_session()
        return PurchaseRecordRepository(self.__session)
