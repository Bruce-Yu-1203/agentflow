"""Load scoped business instructions without expanding tool permissions."""

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: str
    keywords: tuple[str, ...]
    agents: tuple[str, ...]
    enabled: bool
    content: str

    def info(self) -> dict:
        return {"name": self.name, "description": self.description, "path": self.path, "keywords": list(self.keywords), "agents": list(self.agents), "enabled": self.enabled, "content_chars": len(self.content)}


class SkillManager:
    def __init__(self, directory: str):
        self.directory = Path(directory)
        self.skills: list[Skill] = []
        self.errors: list[str] = []
        self.reload()

    def reload(self) -> dict:
        loaded: list[Skill] = []
        errors: list[str] = []
        for path in sorted(self.directory.glob("**/*")):
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".json"}:
                continue
            try:
                raw = path.read_text(encoding="utf-8")
                meta: dict[str, str] = {}
                content = raw
                if raw.startswith("---\n"):
                    _, header, content = raw.split("---", 2)
                    for line in header.strip().splitlines():
                        if ":" in line:
                            key, value = line.split(":", 1)
                            meta[key.strip().lower()] = value.strip()
                if not content.strip():
                    raise ValueError("Empty Skill content")
                agents = tuple(part.strip().lower() for part in meta.get("agents", "general,technical,billing,escalation").split(",") if part.strip())
                if not agents or any(agent not in {"general", "technical", "billing", "escalation"} for agent in agents):
                    raise ValueError("Invalid Skill agents")
                loaded.append(Skill(meta.get("name", path.stem), meta.get("description", ""), str(path), tuple(part.strip().lower() for part in meta.get("keywords", "").split(",") if part.strip()), agents, meta.get("enabled", "true").lower() == "true", content.strip()[:3200]))
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
        self.skills, self.errors = loaded, errors
        return self.list()

    def list(self) -> dict:
        return {"count": len(self.skills), "skills": [skill.info() for skill in self.skills], "errors": list(self.errors)}

    def matching(self, role: str, message: str) -> str:
        lowered = message.lower()
        selected = [skill.content for skill in self.skills if skill.enabled and role in skill.agents and (not skill.keywords or any(re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", lowered) for word in skill.keywords))]
        return "\n\n".join(selected)[:5000]
