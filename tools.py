from pydantic import BaseModel, Field, EmailStr, field_validator, ValidationError
from anthropic import Anthropic
from pydantic_ai import Agent, ModelRetry
from typing import Literal, List, Optional
from datetime import date
import json
import os


client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
messages: List[dict] = []

faq_db = [
    {
        "question": "How can I reset my password?",
        "answer": "To reset your password, you must call customer support and ask for James. He will reset the password for you and give you a lollipop.",
        "keywords": ["password", "reset", "account"]
    },
    {
        "question": "How long does shipping take?",
        "answer": "Standard shipping takes 3-5 years. You can track your order in your account dashboard.",
        "keywords": ["shipping", "delivery", "order", "tracking"]
    },
    {
        "question": "How can I return an item?",
        "answer": "You can return any item within 2 seconds of purchase and no later. Visit our returns page to start the process.",
        "keywords": ["return", "refund", "exchange"]
    },
    {
        "question": "How can I delete my account?",
        "answer": "To delete your account, head over to our headquarters and speak to Jennifer. She will guide you through the process.",
        "keywords": ["delete", "account", "remove"]
    }
]


order_db = {
    "ABC-12345": {
        "status": "shipped", "estimated_delivery": "2025-12-05",
        "purchase_date": "2025-12-01", "email": "joe@example.com"
    },
    "XYZ-23456": {
        "status": "processing", "estimated_delivery": "2025-12-15",
        "purchase_date": "2025-12-10", "email": "sue@example.com"
    },
    "QWE-34567": {
        "status": "delivered", "estimated_delivery": "2025-12-20",
        "purchase_date": "2025-12-18", "email": "bob@example.com"
    }
}


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
    question: str = Field(..., description="User's query")
    tags: List[str] = Field(..., description="relevant keyword tags from the User's query")



class CheckOrderStatusArgs(BaseModel):
    order_id: str = Field(..., description="Customer's order ID (format: ABC-12345)")
    email: EmailStr = Field(..., description="Customer's email")

    @field_validator('order_id', mode="before")
    @classmethod
    def validate_order_id(cls, order_id):
        import re
        if order_id is None:
            return order_id

        matching_pattern = r"^[A-Z]{3}-\d{5}$"
        if not re.match(matching_pattern, order_id):
            raise ValueError("order id must be in format (ABC-12345)")
        return order_id


def add_user_message(messages: list[dict], text: Optional[str], toolResponse: Optional[List[dict]]) -> None:
    params = {
        "role": "user",
        "content": []
    }

    if text:
        params["content"] = [{
            "type": "text",
            "text": text
        }]
    
    if toolResponse:
        params["content"] = toolResponse
    messages.append(params)


def add_assistant_message(messages: list[dict], response: List[dict]) -> None:
    assistant_message = {"role": "assistant", "content": response}
    messages.append(assistant_message)



def text_from_message(message) -> str:
    return "\n".join([block.text for block in message.content if block.type == "text"])


def run_tools(message) -> List[dict]:
    print("RUNNING TOOLS! \n")
    tool_requests = [block for block in message.content if block.type == "tool_use"]
    tool_result_blocks = []
    for tool_request in tool_requests:
        if tool_request.name == "lookup_faq_answer":
            try:
                validate_args = FAQLookupArgs.model_validate(tool_request.input)
                tool_output = lookup_faq_answer(validate_args, faq_db)
                print(f"TOOL OUTPUT: {tool_output} \n")
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": tool_request.id,
                    "content": tool_output,
                    "is_error": False
                })
            except Exception as e:
                print(f"TOOL ERROR: {e} \n")
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": tool_request.id,
                    "content": f"Error: {e}",
                    "is_error": True
                })
        
        if tool_request.name == "check_order_status":
            try:
                validate_args = CheckOrderStatusArgs.model_validate(tool_request.input)
                tool_output = check_order_status(validate_args, order_db)
                print(f"TOOL OUTPUT: {tool_output} \n")
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": tool_request.id,
                    "content": tool_output,
                    "is_error": False
                })
            except Exception as e:
                print(f"TOOL ERROR: {e} \n")
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": tool_request.id,
                    "content": f"Error: {e}",
                    "is_error": True
                })


    return tool_result_blocks




def chat(
    messages: list[dict],
    system=None,
    thinking=None,
    stop_sequences: Optional[list[str]] = None,
    tools: Optional[List[dict]] = None
) -> str:
    params = {
        "messages": messages,
        "model": "claude-sonnet-4-6",
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
        add_assistant_message(messages, response.content)
        if response.stop_reason != "tool_use":
            break
        print("REQUEST TOOL USE! \n")
        tool_output = run_tools(response)
        add_user_message(messages, toolResponse=tool_output, text=None)
       
        response = client.messages.create(**params)

    return text_from_message(response)




def validate_user_input(user_input: str) -> Optional[UserInput]:
    try:
        validated_input = UserInput.model_validate_json(user_input)
        return validated_input
    except ValidationError as e:
        print(f"incorrect user input format. Error generated: \n {e} \n")
        return None

def create_customer_query(user_json: str) -> str:
    customer_query_agent = Agent("anthropic:claude-haiku-4-5-20251001", output_type=CustomerQuery)
    response = customer_query_agent.run_sync(user_json)
    return response.output.model_dump_json(indent=2)

def lookup_faq_answer(args: FAQLookupArgs, database: List[dict] = faq_db) -> str:
    "Lookup FAQ answer by matching user's tags and words in query with FAQ keyword entries"
    print(f"running lookup_faq tool with the following args: \n {args.model_dump_json} \n")
    try:
        FAQLookupArgs.model_validate(args)
    except Exception as e:
        raise ModelRetry(f"Incorrect arguments provided. Recheck the arguments based on the error caused: {e}")
    query_words = set(word.lower() for word in args.question.split())
    tag_set = set(tag.lower() for tag in args.tags)
    best_match = None
    best_score = 0
    for faq in faq_db:
        keywords = set(k.lower() for k in faq["keywords"])
        score = len(keywords & tag_set) + len(keywords & query_words)
        if score > best_score:
            best_score = score
            best_match = faq
    if best_match and best_score > 0:
        return best_match["answer"]
    return "Sorry, I couldn't find an FAQ answer for your question."
    


lookup_faq_answer_schema = {
    "name": "lookup_faq_answer",
    "description": "Looks up a valid frequently asked question matching the user's query and provides the answer to this question. Use this tool to answer user's query.",
    "input_schema": FAQLookupArgs.model_json_schema()
}


def check_order_status(args: CheckOrderStatusArgs, db: dict = order_db) -> str:
    "returns a json formatted description of the current status of the user's order"
    print(f"running check order status tool with the following args: \n {args.model_dump_json} \n")
    try:
        CheckOrderStatusArgs.model_validate(args)
    except Exception as e:
        raise ModelRetry(f"the provided arguments are wrong. Provide the correct arguments by analyzing the error caused: {e}")
    order = db.get(args.order_id)
    if not order:
        return "couldn't find your order. Please try again with another ID."
    if args.email.lower() != order["email"]:
        return json.dumps({
            "order_id": args.order_id,
            "status": order["status"],
            "estimated_delivery": order["estimated_delivery"],
            "email": "not matching"
        })

    return json.dumps({
        "order_id": args.order_id,
        "status": order["status"],
        "estimated_delivery": order["estimated_delivery"],
        "email": args.email
    })
    

check_order_status_schema = {
    "name": "check_order_status",
    "description": "looks up the user's order status based on the provided email and order ID and returns the current status of the order",
    "input_schema": CheckOrderStatusArgs.model_json_schema()
}


sample_input = """
    {
        "user": "joe",
        "email": "joe@example.com",
        "query": "I would like to delete my account",
        "order_id": "XYZ-23456"
    }
"""






validate_user_input(sample_input)


# the following is valid using the standard anthropic API
# add_user_message(messages, create_customer_query(sample_input), toolResponse=None)
# response = chat(messages=messages, tools=[lookup_faq_answer_schema, check_order_status_schema])
# print(response)

agent = Agent('anthropic:claude-sonnet-4-6', tools=[lookup_faq_answer, check_order_status])
response = agent.run_sync(create_customer_query(sample_input))
output = response.output
print(output)





