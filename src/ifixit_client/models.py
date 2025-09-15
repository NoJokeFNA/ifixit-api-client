from pydantic import BaseModel, HttpUrl
from typing import Optional


class Image(BaseModel):
    """Image model for iFixit resources."""

    id: int
    guid: str
    mini: HttpUrl
    thumbnail: HttpUrl
    standard: HttpUrl
    medium: HttpUrl
    large: HttpUrl
    huge: HttpUrl
    original: HttpUrl


class Guide(BaseModel):
    """Guide model from iFixit API."""

    guideid: int
    title: str
    category: str
    difficulty: str
    conclusion_raw: str
    conclusion_rendered: str
    image: Optional[Image] = None
    revisionid: int
    modified_date: float
    prereq_modified_date: float
    public: bool
    url: HttpUrl
    userid: int
    username: str


class User(BaseModel):
    """User model from iFixit API."""

    userid: int
    username: str
    unique_username: Optional[str] = None
    join_date: float
    image: Optional[Image] = None
    reputation: int
    url: HttpUrl
    teams: list[int]


class Wiki(BaseModel):
    """Wiki model from iFixit API."""

    wikiid: int
    title: str
    namespace: str
    revisionid: int
    modified_date: float
    contents_raw: str
    contents_rendered: str
    url: HttpUrl