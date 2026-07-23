from datetime import datetime, timedelta

from di.di import DI
from features.chat.attachment.chat_attachment import ChatAttachment
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.social_cards import card_renderer
from features.social_cards.domain import SocialLinkPreviewAsset, SocialMediaAsset, SocialPost, SocialPostRenderAssets
from features.social_cards.link_preview import fetch_favicon, fetch_og_image_url
from features.social_cards.providers.social_post_provider import SocialPostProvider
from features.social_cards.theme import pick_theme
from features.web_browsing.photo_downloader import PhotoDownloader
from util import log
from util.error_codes import IMAGE_GENERATION_FAILED, TOOL_NOT_FOUND, WEB_FETCH_FAILED
from util.errors import ExternalServiceError, NotFoundError, ValidationError


class SocialCardOrchestrator:

    VISION_TOOL_TYPE: ToolType = ToolType.vision

    __api_tools: list[ConfiguredTool]
    __vision_tool: ConfiguredTool
    __di: DI

    def __init__(self, api_tools: list[ConfiguredTool], vision_tool: ConfiguredTool, di: DI):
        self.__api_tools = api_tools
        self.__vision_tool = vision_tool
        self.__di = di

    def execute(self, url: str) -> str:
        provider = self.__require_provider_for(url)
        post = provider.fetch(url)
        downloader = self.__di.photo_downloader()
        assets = self.__resolve_assets(post, downloader)
        media_bytes = [asset.content for asset in assets.media]
        theme = pick_theme(assets.avatar_bytes, media_bytes)
        short_url = self.__shorten_url(post.source_url)

        try:
            png_bytes = card_renderer.render(
                post = post,
                theme = theme,
                assets = assets,
                short_url = short_url,
            )
        except Exception as e:
            raise ExternalServiceError("Card rendering failed", IMAGE_GENERATION_FAILED) from e
        log.t("Social card generated successfully")

        chat = self.__di.require_invoker_chat()
        attachment = self.__di.chat_attachment_service.save(
            attachment = ChatAttachment(chat_id = chat.chat_id, uploader_user_id = self.__di.invoker.id),
            content = png_bytes,
        )
        return self.__di.chat_attachment_service.create_public_url(attachment).url

    def __require_provider_for(self, url: str) -> SocialPostProvider:
        for provider_class in self.__di.social_post_provider_classes():
            if provider_class.can_handle(url):
                api_tool = self.__api_tool_for(provider_class.tool_type)
                if api_tool:
                    return self.__di.social_post_provider(provider_class, api_tool, self.__vision_tool)
                raise NotFoundError(f"Social cards require an API tool for '{provider_class.tool_type.value}'", TOOL_NOT_FOUND)
        raise ValidationError(f"Unsupported social post URL: {url}", WEB_FETCH_FAILED)

    def __api_tool_for(self, tool_type: ToolType) -> ConfiguredTool | None:
        for api_tool in self.__api_tools:
            if api_tool.purpose == tool_type:
                return api_tool
        return None

    def __resolve_assets(self, post: SocialPost, downloader: PhotoDownloader) -> SocialPostRenderAssets:
        avatar_bytes = downloader.download(post.author.avatar_url) if post.author.avatar_url else None
        media_assets = self.__resolve_media_assets(post, downloader)
        link_preview_assets = self.__resolve_link_preview_assets(post, downloader, has_post_media = bool(media_assets))
        embedded_assets = self.__resolve_assets(post.embedded_post, downloader) if post.embedded_post else None
        return SocialPostRenderAssets(
            avatar_bytes = avatar_bytes,
            media = media_assets,
            link_previews = link_preview_assets,
            embedded_post = embedded_assets,
        )

    @staticmethod
    def __resolve_media_assets(post: SocialPost, downloader: PhotoDownloader) -> list[SocialMediaAsset]:
        media_assets: list[SocialMediaAsset] = []
        for media in post.media:
            media_url = media.url or media.preview_url
            if not media_url:
                continue
            content = downloader.download(media_url)
            if content:
                media_assets.append(SocialMediaAsset(media = media, content = content))
        return media_assets

    def __resolve_link_preview_assets(
        self,
        post: SocialPost,
        downloader: PhotoDownloader,
        has_post_media: bool,
    ) -> list[SocialLinkPreviewAsset]:
        link_preview_assets: list[SocialLinkPreviewAsset] = []
        for link_preview in post.link_previews:
            og_image_bytes: bytes | None = None
            if not has_post_media:
                if link_preview.image_url:
                    og_image_bytes = downloader.download(link_preview.image_url)
                if not og_image_bytes:
                    fallback_url = fetch_og_image_url(link_preview.expanded_url)
                    if fallback_url:
                        og_image_bytes = downloader.download(fallback_url)
            favicon_bytes = fetch_favicon(link_preview.domain, expanded_url = link_preview.expanded_url)
            link_preview_assets.append(
                SocialLinkPreviewAsset(
                    link_preview = link_preview,
                    og_image_bytes = og_image_bytes,
                    favicon_bytes = favicon_bytes,
                    short_url = self.__shorten_url(link_preview.expanded_url),
                ),
            )
        return link_preview_assets

    def __shorten_url(self, url: str) -> str:
        try:
            valid_until = datetime.now() + timedelta(days = 365)
            return self.__di.url_shortener(url, valid_until = valid_until).execute()
        except Exception as e:
            log.w("URL shortening failed, using original URL", e)
            return url
