"""User request/response schemas."""
from pydantic import BaseModel, EmailStr

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str
    name: str | None = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str


class UserMe(BaseModel):
    id: str
    email: str
    name: str | None = None
    avatar_url: str | None = None  
    class Config:
        from_attributes = True


class UserMeUpdate(BaseModel):
    name: str | None = None
