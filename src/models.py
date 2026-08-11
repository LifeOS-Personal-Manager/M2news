from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "yclid", "mc_cid", "mc_eid"}

REGIONS = ("international", "domestic")
CATEGORIES = (
    "politics",
    "economy_finance",
    "society_welfare",
    "industry",
    "culture_sports",
)


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query_pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lower_key = key.lower()
        if lower_key in TRACKING_QUERY_KEYS:
            continue
        if any(lower_key.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES):
            continue
        query_pairs.append((key, value))
    query = urlencode(sorted(query_pairs), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def make_url_hash(url: str) -> str:
    return sha256(normalize_url(url).encode("utf-8")).hexdigest()[:32]


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class RawNewsItem:
    title: str
    source: str
    url: str
    region: str
    summary: str = ""
    published_at: str | None = None
    hash: str = ""
    collected_at: str = ""

    @classmethod
    def create(
        cls,
        *,
        title: str,
        source: str,
        url: str,
        region: str,
        summary: str = "",
        published_at: str | None = None,
        collected_at: str | None = None,
    ) -> "RawNewsItem":
        return cls(
            title=title.strip(),
            source=source.strip(),
            url=url.strip(),
            region=region,
            summary=summary.strip(),
            published_at=published_at,
            hash=make_url_hash(url),
            collected_at=collected_at or utc_now_iso(),
        )

    @property
    def link(self) -> str:
        return self.url

    @property
    def date(self) -> str:
        return (self.published_at or self.collected_at)[:10]

    @property
    def created_at(self) -> str:
        return self.collected_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "link": self.url,
            "region": self.region,
            "summary": self.summary,
            "published_at": self.published_at,
            "hash": self.hash,
            "collected_at": self.collected_at,
        }

    @classmethod
    def from_row(cls, row: Any) -> "RawNewsItem":
        return cls(
            title=row["title"],
            source=row["source"],
            url=row["link"],
            region=row["region"] if "region" in row.keys() else "domestic",
            summary=row["summary"] or "",
            published_at=row["published_at"],
            hash=row["hash"],
            collected_at=row["created_at"],
        )


@dataclass(frozen=True)
class DigestArticle:
    title: str
    source: str
    url: str
    published_at: str | None
    category: str
    region: str
    summary: str
    impact: str
    why_it_matters: str
    confidence: float
    hash: str
    references: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "published_at": self.published_at,
            "category": self.category,
            "region": self.region,
            "summary": self.summary,
            "impact": self.impact,
            "why_it_matters": self.why_it_matters,
            "confidence": self.confidence,
            "hash": self.hash,
            "references": self.references,
        }


@dataclass(frozen=True)
class DailyDigest:
    date: str
    period: dict[str, str]
    sections: dict[str, dict[str, list[dict[str, Any]]]]
    top_highlights: list[str]
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "period": self.period,
            "sections": self.sections,
            "top_highlights": self.top_highlights,
            "generated_at": self.generated_at,
        }


def empty_sections() -> dict[str, dict[str, list[dict[str, Any]]]]:
    return {region: {category: [] for category in CATEGORIES} for region in REGIONS}


NewsItem = RawNewsItem
