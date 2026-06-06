from pydantic import BaseModel
from typing import List, Optional

class Repo(BaseModel):
    name: str
    desc: Optional[str] = ""
    dependencies: List[str]
    raw_desc: str = ""