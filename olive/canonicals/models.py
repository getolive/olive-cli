from pydantic import BaseModel

class Canonical(BaseModel):
    name: str
    installed: bool = False
    message: str = ""
