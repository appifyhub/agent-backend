from typing import Sequence

from features.social_cards.social_card_models import SocialCardTimelineSegment


def plan_timeline(
    source_durations_seconds: Sequence[float],
    max_duration_seconds: float,
) -> tuple[SocialCardTimelineSegment, ...]:
    segments: list[SocialCardTimelineSegment] = []
    elapsed_seconds = 0.0
    for source_index, source_duration_seconds in enumerate(source_durations_seconds):
        remaining_seconds = max_duration_seconds - elapsed_seconds
        if remaining_seconds <= 0:
            break
        effective_duration_seconds = min(source_duration_seconds, remaining_seconds)
        if effective_duration_seconds <= 0:
            continue
        segments.append(
            SocialCardTimelineSegment(
                source_index = source_index,
                start_seconds = elapsed_seconds,
                duration_seconds = effective_duration_seconds,
            ),
        )
        elapsed_seconds += effective_duration_seconds
    return tuple(segments)
