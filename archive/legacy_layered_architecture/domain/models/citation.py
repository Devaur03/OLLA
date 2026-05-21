from dataclasses import dataclass, field
from datetime import date


@dataclass
class Citation:
    rank: int
    title: str
    url: str
    score: float
    retrieved_date: str = ""

    def __post_init__(self):
        if not self.retrieved_date:
            self.retrieved_date = date.today().isoformat()

    def to_apa(self) -> str:
        today = date.today().strftime("%Y, %B %d")
        return f"{self.title}. (n.d.). Retrieved {today}, from {self.url}"

    def to_markdown_link(self) -> str:
        return f"[{self.title}]({self.url})"
