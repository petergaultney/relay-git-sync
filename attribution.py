#!/usr/bin/env python3
"""Resolve the git author for a file change using the relay server's
attributed-content endpoint (per-span authorship of the doc's current text).

The dominant author of the *changed* characters gets the commit and any other
contributors become co-authors; deletion-only changes and unattributable
content fall back to the default (bot) identity.
"""

import difflib
import logging
import re
import traceback
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GitAuthor:
    name: str
    email: str


_AUTHOR_RE = re.compile(r"^\s*(?P<name>[^<>]+?)\s*<(?P<email>[^<>@\s]+@[^<>\s]+)>\s*$")


def parse_author(value: str) -> Optional[GitAuthor]:
    """Parse a '"Name <email>"' config value."""
    match = _AUTHOR_RE.match(value)
    if not match:
        return None

    return GitAuthor(name=match.group("name"), email=match.group("email"))


def parse_authors(table: Dict[str, str]) -> Dict[str, GitAuthor]:
    """Parse the [authors] config table (relay user id -> 'Name <email>')."""
    authors = {}
    for user_id, value in table.items():
        author = parse_author(value)
        if author:
            authors[user_id] = author
        else:
            logger.error(f"Ignoring malformed author for {user_id!r}: {value!r}")
    return authors


def _changed_ranges(old: str, new: str) -> List[Tuple[int, int]]:
    """Character ranges of `new` that differ from `old` (inserts + replacements)."""
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    return [
        (j1, j2)
        for tag, _i1, _i2, j1, j2 in matcher.get_opcodes()
        if tag in ("insert", "replace") and j2 > j1
    ]


def _changed_chars_by_user(
    spans: List[dict], ranges: List[Tuple[int, int]]
) -> Dict[Optional[str], int]:
    counts: Dict[Optional[str], int] = {}
    offset = 0
    for span in spans:
        span_start, span_end = offset, offset + len(span.get("text", ""))
        offset = span_end
        overlap = sum(
            min(span_end, r_end) - max(span_start, r_start)
            for r_start, r_end in ranges
            if min(span_end, r_end) > max(span_start, r_start)
        )
        if overlap:
            user = span.get("user")
            counts[user] = counts.get(user, 0) + overlap
    return counts


def attributing_users(old: str, new: str, spans: List[dict]) -> List[str]:
    """Relay users who authored the changed characters, most-changed first.

    Empty means "no attributable author": deletion-only change, spans that
    don't reconstruct `new` (the doc moved on since materialization), or
    changed content whose authors are all unmapped in PUD.
    """
    if "".join(span.get("text", "") for span in spans) != new:
        logger.debug("Attributed spans do not reconstruct file content; skipping attribution")
        return []

    counts = _changed_chars_by_user(spans, _changed_ranges(old, new))
    counts.pop(None, None)
    return sorted(counts, key=lambda user: (-counts[user], user))


class AuthorResolver:
    """Fetches attributed spans for a doc and resolves the change's git author.

    fetch_spans is relay_client.fetch_attributed_spans (or equivalent):
    given an S3RN document resource, return the span list or None.
    """

    def __init__(
        self,
        fetch_spans: Callable[[object], Optional[List[dict]]],
        authors: Dict[str, GitAuthor],
    ):
        self.fetch_spans = fetch_spans
        self.authors = authors

    def resolve(self, resource: object, old: str, new: str) -> List[GitAuthor]:
        """Git authors of the change, dominant first. Empty = unattributable."""
        if not self.authors:
            return []

        try:
            spans = self.fetch_spans(resource)
        except Exception as e:
            logger.warning(f"Attribution fetch failed for {resource}: {e}")
            logger.debug(traceback.format_exc())
            return []
        if not spans:
            return []

        authors = []
        for user in attributing_users(old, new, spans):
            author = self.authors.get(user)
            if author is None:
                logger.info(f"No git author configured for relay user {user}")
            elif author not in authors:
                authors.append(author)
        return authors
