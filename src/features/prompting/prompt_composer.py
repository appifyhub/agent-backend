from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from util.error_codes import INVALID_PROMPT_TEMPLATE
from util.errors import ValidationError

SECTION_BODY_DIVIDER = "\n"
SECTIONS_DIVIDER = "\n\n"


class PromptSection(Enum):
    context = "Context"
    style = "Style"
    personality = "Personality"
    tone = "Tone"
    format = "Format"
    appendix = "Appendix"
    meta = "Metadata"


class PromptVar(Enum):
    agent_name = "agent_name"
    agent_username = "agent_username"
    agent_website = "agent_website"
    chat_title = "chat_title"
    author_name = "author_name"
    author_username = "author_username"
    author_role = "author_role"
    author_info = "author_info"
    custom_prompt = "custom_prompt"
    language_name = "language_name"
    language_iso = "language_iso"
    date_and_time = "date_and_time"
    personal_dictionary = "personal_dictionary"
    query = "query"
    support_request_type = "support_request_type"
    content_template = "content_template"
    reference_image_count = "reference_image_count"
    tools_list = "tools_list"
    allowed_reactions = "allowed_reactions"


@dataclass(frozen = True)
class PromptFragment:
    id: str
    content: str
    section: PromptSection


@dataclass(frozen = True)
class PromptComposer:
    fragments: tuple[PromptFragment, ...] = field(default_factory = tuple)
    variables: dict[str, str] = field(default_factory = dict)

    def add_fragments(self, *frags: PromptFragment) -> PromptComposer:
        return PromptComposer(self.fragments + tuple(frags), self.variables)

    def add_variables(self, *vars_tuples: tuple[PromptVar, str]) -> PromptComposer:
        normalized = {k.value: v for k, v in vars_tuples}
        return PromptComposer(self.fragments, {**self.variables, **normalized})

    def append(self, other: PromptComposer) -> PromptComposer:
        return PromptComposer(self.fragments + other.fragments, {**self.variables, **other.variables})

    @staticmethod
    def combine(*composers: PromptComposer) -> PromptComposer:
        merged_frags: list[PromptFragment] = []
        merged_vars: dict[str, str] = {}
        for c in composers:
            merged_frags.extend(c.fragments)
            merged_vars.update(c.variables)
        return PromptComposer(tuple(merged_frags), merged_vars)

    def render(self) -> str:
        def apply_vars(text: str) -> str:
            sanitized_vars = {k: v.replace("`", "") for k, v in self.variables.items()}
            try:
                return text.format_map(sanitized_vars).strip()
            except KeyError as e:
                missing = str(e).strip("'")
                raise ValidationError(f"Missing prompt variable: {missing}", INVALID_PROMPT_TEMPLATE) from e

        # group fragments by section
        section_to_bodies: dict[PromptSection, list[str]] = {}
        for f in self.fragments:
            if f.section not in section_to_bodies:
                section_to_bodies[f.section] = []
            section_to_bodies[f.section].append(apply_vars(f.content))

        # render sections in the order defined by the enum, but include only present sections
        rendered_sections: list[str] = []
        for section in [s for s in PromptSection if s in section_to_bodies]:
            bodies = section_to_bodies.get(section, [])
            body_block = SECTION_BODY_DIVIDER.join([b for b in bodies if b]).strip()
            rendered_sections.append(f"[{section.value}]{SECTION_BODY_DIVIDER}{body_block}")
        return SECTIONS_DIVIDER.join(rendered_sections).strip()


def build(*frags: PromptFragment) -> PromptComposer:
    return PromptComposer(tuple(frags))
