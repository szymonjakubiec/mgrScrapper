from pydantic import BaseModel
from typing import List, Optional

class Repo(BaseModel):
    name: str
    short_desc: Optional[str] = ""
    dependencies: List[str]