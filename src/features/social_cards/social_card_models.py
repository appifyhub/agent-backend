from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class SocialMediaKind(StrEnum):

    IMAGE = "image"
    VIDEO = "video"
    GIF = "gif"
    UNKNOWN = "unknown"


class SocialCardMode(StrEnum):

    IMAGE = "image"
    VIDEO = "video"


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
class SocialDynamicMedia:
    playback_url: str
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None


@dataclass
class SocialMediaItem:
    kind: SocialMediaKind
    url: str | None = None
    preview_url: str | None = None
    alt_text: str | None = None
    dynamic_media: SocialDynamicMedia | None = None


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
    path: Path


@dataclass
class SocialLinkPreviewAsset:
    link_preview: SocialLinkPreview
    og_image_path: Path | None = None
    favicon_path: Path | None = None
    short_url: str | None = None


@dataclass
class SocialPostRenderAssets:
    avatar_path: Path | None = None
    media: list[SocialMediaAsset] = field(default_factory = list)
    link_previews: list[SocialLinkPreviewAsset] = field(default_factory = list)
    embedded_post: SocialPostRenderAssets | None = None


@dataclass
class SocialMediaPlacement:
    media: SocialMediaItem
    x: int
    y: int
    width: int
    height: int
    top_left_radius: int
    top_right_radius: int
    bottom_right_radius: int
    bottom_left_radius: int


@dataclass(frozen = True)
class SocialCardVideoInput:
    media_path: Path
    placement: SocialMediaPlacement


@dataclass(frozen = True)
class SocialCardTimelineSegment:
    source_index: int
    start_seconds: float
    duration_seconds: float

    @property
    def end_seconds(self) -> float:
        return self.start_seconds + self.duration_seconds


@dataclass
class SocialCardTemplateResult:
    svg: str
    width: int
    height: int
    media_placements: list[SocialMediaPlacement] = field(default_factory = list)


@dataclass
class SocialCardRenderResult:
    public_url: str
    mode: SocialCardMode
