"""Record dataclass for one duty clause of the SWM Rules."""
from dataclasses import dataclass, asdict
from typing import Optional

REQUIRED_FIELDS = ("rule_reference", "stakeholder", "obligation", "timeline",
                   "rules_version", "source_url")


@dataclass(frozen=True)
class Record:
    id: int
    rule_reference: str
    stakeholder: str
    category: str
    obligation: str
    timeline: str
    rules_version: str
    source_url: str
    rule_2016_match: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Record":
        """Build a Record from a raw dict. Raises ValueError/KeyError on bad rows."""
        missing = [k for k in REQUIRED_FIELDS if not str(d.get(k) or "").strip()]
        if missing:
            raise ValueError(f"missing or empty field(s): {', '.join(missing)}")
        if not str(d["source_url"]).startswith(("http://", "https://")):
            raise ValueError(f"source_url is not a URL: {d['source_url']!r}")
        match = d.get("rule_2016_match")
        return cls(
            id=int(d["id"]),
            rule_reference=str(d["rule_reference"]).strip(),
            stakeholder=str(d["stakeholder"]).strip(),
            category=str(d.get("category") or "General").strip(),
            obligation=str(d["obligation"]).strip(),
            timeline=str(d["timeline"]).strip(),
            rules_version=str(d["rules_version"]).strip(),
            source_url=str(d["source_url"]).strip(),
            rule_2016_match=str(match).strip() if match else None,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def matches(self, keyword: str) -> bool:
        kw = keyword.lower()
        return any(kw in str(v).lower() for v in self.to_dict().values() if v is not None)
