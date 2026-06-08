from pydantic import BaseModel, Field, EmailStr, field_validator
from anthropic import Anthropic
from pydantic_ai import Agent
from typing import Literal, List, Optional
from datetime import date
import json
import instructor

class UserInput(BaseModel):
    user: str
    email: EmailStr
    query: str
    