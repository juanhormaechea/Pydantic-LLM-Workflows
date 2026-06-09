from pydantic import BaseModel, Field, EmailStr, field_validator, ValidationError
from anthropic import Anthropic
from pydantic_ai import Agent
from typing import Literal, List, Optional
from datetime import date
import json
import os
import instructor

client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
client_instructor = instructor.from_provider("anthropic/claude-haiku-4-5-20251001")
messages = []




class UserInput(BaseModel):
    user: str = Field(description="name of the user")
    email: EmailStr = Field(description="email address of the user")
    query: str = Field(description="user query")
    order_id: Optional[str] = Field(None, description="Order ID of the form (ABC-12345)")

    @field_validator('order_id', mode="before")
    @classmethod
    def validate_order_id(cls, id: str):
        import re
        if id is None:
            return id

        pattern = r"^[A-Z]{3}-\d{5}$"
        if not re.match(pattern, id):
            raise ValueError("order id must be in the format (ABC-12345)")

        return id
    purchase_date: Optional[date] = Field(None, description="date when item was purchased")



class CustomerQuery(UserInput):
    priority: str = Field(
        ..., description="Priority level: low, medium, high"
    )
    category: Literal[
        'refund_request', 'information_request', 'other'
    ] = Field(..., description="Query category")
    is_complaint: bool = Field(
        ..., description="Whether this is a complaint"
    )
    tags: List[str] = Field(..., description="Relevant keyword tags")


class FAQLookupArgs(BaseModel):




class CheckOrderStatusArgs(BaseModel):


def add_user_message(messages: list[dict], text: Optional[str], toolResult: Optional[List[dict]]) -> None:
    params = {
        "role": "user",
        "content": None
    }
    
    if toolResult:
        params["content"] = toolResult
    
    params["content"] = [{
        "type": "text",
        "content": text
    }]
    messages.append(params)


def add_assistant_message(messages: list[dict], response: List[dict]) -> None:
    assistant_message = {"role": "assistant", "content": response}
    messages.append(assistant_message)



def text_from_message(message) -> str:
    return "\n".join([block for block in message.content if block.type == "text"])


def run_tools(message) -> dict:
    tool_requests = [block for block in message.content if block.type == "tool_use"]

    for tool_request in tool_requests:
        try:
            if tool_request == "":


def chat(
    messages: list[dict],
    system=None,
    thinking=None,
    stop_sequences: Optional[list[str]] = None,
    tools: Optional[List[dict]] = None
) -> str:
    params = {
        "messages": messages,
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 2000,
        "stop_sequences": stop_sequences or []
    }

    if system:
        params["system"] = system
    
    if thinking:
        params["thinking"] = thinking
    
    if tools:
        params["tools"] = tools
    
    response = client.messages.create(**params)
    
    while True:
        if response.stop_reason != "tool_use":
            break
        
        add_assistant_message(messages, response.content)
        add_user_message(messages, toolResult=run_tools(response.content), text=None)
        response = client.messages.create(**params)

    return response


def chat_instructor(
    messages: list[dict],
    response_model: type[BaseModel],
    system=None,
    thinking=None,
    stop_sequences: Optional[list[str]] = None,
    tools: Optional[List[dict]] = None
) -> str:
    params = {
        "response_model": response_model,
        "messages": messages,
        "max_tokens": 2000,
        "stop_sequences": stop_sequences or [],
    }

    if system:
        params["system"] = system
    
    if thinking:
        params["thinking"] = thinking
    
    if tools:
        params["tools"] = tools

    message = client_instructor.messages.create(**params)
    if isinstance(message, BaseModel):
        return message.model_dump_json(indent=2)
    if isinstance(message, str):
        return message
    return json.dumps(message, indent=2, default=str)


def validate_user_input(user_input: str) -> Optional[UserInput]:
    try:
        validated_input = UserInput.model_validate_json(user_input)
        return validated_input
    except ValidationError as e:
        print(f"incorrect user input format. Error generated: \n {e} \n")
        return None



def lookup_faq_answer(args: FAQLookupArgs) -> str:






def check_order_status(args: CheckOrderStatusArgs):