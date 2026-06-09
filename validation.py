from pydantic import BaseModel, ValidationError, Field, EmailStr, field_validator
from typing import Optional, Literal, List
from datetime import date
from anthropic import Anthropic
from pydantic_ai import Agent
import instructor
import json
import os


class UserInput(BaseModel):
    name: str = Field(description="name of the user")
    email: EmailStr = Field(description="email of the user")
    query: str
    order_id: Optional[int] = Field(None, description="5-digit order ID. Cannot start with 0", ge=10000, le=99999)
    purchase_date: Optional[date] = None

    

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


client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
client_instructor = instructor.from_provider("anthropic/claude-haiku-4-5-20251001")
agent = None
messages: list[dict] = []
num_tokens = 0

def add_user_message(messages: list[dict], text: str) -> None:
    user_message = {"role": "user", "content": text}
    messages.append(user_message)


def add_assistant_message(messages: list[dict], text: str) -> None:
    assistant_message = {"role": "assistant", "content": text}
    messages.append(assistant_message)


def chat(
    messages: list[dict],
    system=None,
    thinking=None,
    stop_sequences: Optional[list[str]] = None,
) -> str:
    params = {
        "model" : "claude-haiku-4-5-20251001",
        "messages": messages,
        "max_tokens": 2000,
        "stop_sequences": stop_sequences or []
    }

    if system:
        params["system"] = system
    
    if thinking:
        params["thinking"] = thinking
    
    message = client.messages.create(**params)
    response = message.content[0].text
    return response


def chat_instructor(
    messages: list[dict],
    response_model: type[BaseModel],
    system=None,
    thinking=None,
    stop_sequences: Optional[list[str]] = None,
) -> str:
    params = {
        "response_model": response_model,
        "messages": messages,
        "max_tokens": 2000,
        "stop_sequences": stop_sequences or []
    }

    if system:
        params["system"] = system
    
    if thinking:
        params["thinking"] = thinking
    
    message = client_instructor.create(**params)
    if isinstance(message, BaseModel):
        return message.model_dump_json(indent=2)
    if isinstance(message, str):
        return message
    return json.dumps(message, indent=2, default=str)




def validate_llm_response(data_model: type[BaseModel], prompt: str, num_tries: int = 5) -> str:
    add_user_message(messages, prompt)
    response = None
    validated_data = None
    for i in range(num_tries):
        try:
            response = chat(messages)
            add_assistant_message(messages, response)
            validated_data = data_model.model_validate_json(response)
            print("data validated! \n")
            break
        except ValidationError as e:
            print(f"validation error number {i}! \n")
            print(f"{response} \n")
            response = f""" 
            Your response generated the following validation error. Make sure to return a raw json object according to the provided schema.

            <validation_error>
            {e}
            </validation_error>


            <schema>
            {json.dumps(data_model.model_json_schema())}
            </schema>
            """
            add_user_message(messages, response)
    
    if validated_data is not None:
        return validated_data.model_dump_json(indent=2)
    return ""


def validate_llm_response_instructor(data_model: type[BaseModel], prompt: str, num_tries: int = 5) -> str:
    add_user_message(messages, prompt)
    response = None
    validated_data = None
    for i in range(num_tries):
        try:
            response = chat_instructor(messages, data_model)
            add_assistant_message(messages, response)
            validated_data = data_model.model_validate_json(response)
            print("data validated! \n")
            break
        except ValidationError as e:
            print(f"validation error number {i}! \n")
            response = f""" 
            Your response generated the following validation error. Make sure to return a raw json object according to the provided schema.

            <validation_error>
            {e}
            </validation_error>


            <schema>
            {json.dumps(data_model.model_json_schema())}
            </schema>
            """
            add_user_message(messages, response)
    
    if validated_data is not None:
        return validated_data.model_dump_json(indent=2)
    return ""




def validate_llm_response_agent(prompt: str, model: str, data_model: type[BaseModel], num_tries: int = 5) -> str:
    agent = Agent(model=model, output_type=data_model)
    response = agent.run_sync(prompt)
    output = response.output
    validated_data = None
    for i in range(num_tries):
        try:
            validated_data = data_model.model_validate(output)
            print("data has been validated! \n")
            break
        except ValidationError as e:
            print(f"validation error number {i}")
            error_response = f""" 
                Your response generated the following validation error. Make sure to return a raw json object according to the provided schema.

                <validation_error>
                {e}
                </validation_error>

                <schema>
                {json.dumps(data_model.model_json_schema())}
                </schema>
            """
            response = agent.run_sync(error_response)
            output = response.output

    if isinstance(validated_data, BaseModel):
        return validated_data.model_dump_json(indent=2)
    
    if isinstance(validated_data, str):
        return validated_data

    if validated_data is not None:
        return validated_data

    return ""

user_input_json = '''
    {
        "name": "Joe",
        "email": "joe@email.com",
        "query": "My computer arrived completely destroyed. Battery is fuming.",
        "order_id": 23546,
        "purchase_date": "2025-09-28"

    }
'''

user_input = UserInput.model_validate_json(user_input_json)


prompt = f"""Analyze the following customer query and provide a structured response according to the provided json schema.

        <query>
        {user_input}
        </query>

        <schema>
        {json.dumps(CustomerQuery.model_json_schema())}
        </schema>

        Provide a raw json response. Do not add markup or any other format.
 """



# validated_data = validate_llm_response(CustomerQuery, prompt)
validated_data = validate_llm_response_instructor(CustomerQuery, prompt)
# validated_data = validate_llm_response_agent(prompt, "anthropic:claude-haiku-4-5-20251001", CustomerQuery)
print(validated_data)
