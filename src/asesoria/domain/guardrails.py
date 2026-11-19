from pydantic import BaseModel


class RelevanceVerdict(BaseModel):
    on_topic: bool
    reason: str
