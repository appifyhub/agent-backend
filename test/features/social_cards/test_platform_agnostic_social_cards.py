import pytest

from features.social_cards import card_renderer, card_template
from features.social_cards.domain import (
    SocialAuthor,
    SocialLinkPreview,
    SocialLinkPreviewAsset,
    SocialMediaAsset,
    SocialMediaItem,
    SocialMediaKind,
    SocialPlatformBrand,
    SocialPost,
    SocialPostRenderAssets,
)
from features.social_cards.theme import ThemeColors


def _brand() -> SocialPlatformBrand:
    return SocialPlatformBrand(
        platform_id = "x",
        display_name = "X",
        logo_light_key = "x_logo_light",
        logo_dark_key = "x_logo_dark",
    )


def _post() -> SocialPost:
    return SocialPost(
        platform = _brand(),
        author = SocialAuthor(display_name = "Milos", handle = "milos"),
        text = "hello world",
        source_url = "https://x.com/milos/status/1",
    )


def _theme() -> ThemeColors:
    return ThemeColors(
        gradient_start = "#251A3D",
        gradient_end = "#040b19",
        text_color = "#ffffff",
    )


def test_social_post_domain_holds_platform_neutral_rendering_data() -> None:
    media = SocialMediaItem(
        kind = SocialMediaKind.IMAGE,
        url = "https://example.com/image.jpg",
    )
    link_preview = SocialLinkPreview(
        expanded_url = "https://example.com/article",
        domain = "example.com",
        title = "Example",
    )
    embedded_post = SocialPost(
        platform = _brand(),
        author = SocialAuthor(display_name = "Other", handle = "other"),
        text = "embedded",
        source_url = "https://x.com/other/status/2",
    )

    post = SocialPost(
        platform = _brand(),
        author = SocialAuthor(display_name = "Milos", handle = "milos", avatar_url = "https://example.com/avatar.jpg"),
        text = "hello world",
        source_url = "https://x.com/milos/status/1",
        media = [media],
        link_previews = [link_preview],
        embedded_post = embedded_post,
    )
    assets = SocialPostRenderAssets(
        avatar_bytes = b"avatar",
        media = [SocialMediaAsset(media = media, content = b"media")],
        link_previews = [SocialLinkPreviewAsset(link_preview = link_preview, favicon_bytes = b"favicon")],
        embedded_post = SocialPostRenderAssets(avatar_bytes = b"embedded-avatar"),
    )

    assert post.author.handle == "milos"
    assert post.media[0].kind == SocialMediaKind.IMAGE
    assert post.link_previews[0].domain == "example.com"
    assert post.embedded_post is embedded_post
    assert assets.media[0].media is media
    assert assets.link_previews[0].link_preview is link_preview
    assert assets.embedded_post is not None


def test_card_renderer_consumes_neutral_social_post(monkeypatch: pytest.MonkeyPatch) -> None:
    post = _post()
    assets = SocialPostRenderAssets()
    captured: dict[str, object] = {}

    def fake_build_svg(**kwargs: object) -> str:
        captured.update(kwargs)
        return "<svg></svg>"

    monkeypatch.setattr(card_renderer, "build_svg", fake_build_svg)
    monkeypatch.setattr(card_renderer.resvg_py, "svg_to_bytes", lambda **kwargs: b"png")

    result = card_renderer.render(post = post, theme = _theme(), assets = assets, short_url = post.source_url)

    assert result == b"png"
    assert captured["post"] is post
    assert captured["assets"] is assets


def test_card_template_consumes_neutral_social_post(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(card_template, "_fetch_logo", lambda key: b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    post = _post()

    svg = card_template.build_svg(
        post = post,
        theme = _theme(),
        card_width = 800,
        assets = SocialPostRenderAssets(),
        short_url = post.source_url,
    )

    assert "hello world" in svg
    assert "x.com/milos/status/1" in svg
