from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SocialMediaKind(StrEnum):

    IMAGE = "image"
    VIDEO = "video"
    GIF = "gif"
    UNKNOWN = "unknown"


@dataclass
class SocialPlatformBrand:
    platform_id: str
    display_name: str
    logo_light_key: str
    logo_dark_key: str


@dataclass
class SocialAuthor:
    display_name: str | None
    handle: str
    avatar_url: str | None = None
    profile_url: str | None = None
    bio: str | None = None


@dataclass
class SocialMediaItem:
    kind: SocialMediaKind
    url: str | None = None
    preview_url: str | None = None
    alt_text: str | None = None


@dataclass
class SocialLinkPreview:
    expanded_url: str
    domain: str
    title: str | None = None
    description: str | None = None
    image_url: str | None = None


@dataclass
class SocialPost:
    platform: SocialPlatformBrand
    author: SocialAuthor
    text: str
    source_url: str
    language: str | None = None
    created_at: str | None = None
    media: list[SocialMediaItem] = field(default_factory = list)
    link_previews: list[SocialLinkPreview] = field(default_factory = list)
    embedded_post: SocialPost | None = None


@dataclass
class SocialMediaAsset:
    media: SocialMediaItem
    content: bytes


@dataclass
class SocialLinkPreviewAsset:
    link_preview: SocialLinkPreview
    og_image_bytes: bytes | None = None
    favicon_bytes: bytes | None = None
    short_url: str | None = None


@dataclass
class SocialPostRenderAssets:
    avatar_bytes: bytes | None = None
    media: list[SocialMediaAsset] = field(default_factory = list)
    link_previews: list[SocialLinkPreviewAsset] = field(default_factory = list)
    embedded_post: SocialPostRenderAssets | None = None
