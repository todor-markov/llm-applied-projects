from copy import deepcopy
import json

import anthropic
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic()
TOOL_MAP = {}


def sanitize_message(message) -> dict:
    message_dict = message.to_dict()
    for k in ["id", "model", "stop_reason", "stop_sequence", "type", "usage"]:
        del message_dict[k]
    return message_dict


def sample_with_tools(**claude_kwargs) -> list[dict]:
    messages = deepcopy(claude_kwargs["messages"])
    curr_res = client.messages.create(**claude_kwargs)
    while curr_res.stop_reason == "tool_use":
        tool_blocks = [c for c in curr_res.content if isinstance(c, anthropic.types.tool_use_block.ToolUseBlock)]
        tool_message = {"role": "user", "content": []}
        messages.append(sanitize_message(curr_res))
        for tb in tool_blocks:
            tool_output = TOOL_MAP[tb.name](**tb.input)
            tool_message["content"].append(
                {
                    "type": "tool_result",
                    "tool_use_id": tb.id,
                    "content": tool_output,
                }
            )
        messages.append(tool_message)
        claude_kwargs["messages"] = messages
        curr_res = client.messages.create(**claude_kwargs)
    messages.append(sanitize_message(curr_res))
    return messages


class FakeDatabase:
    def __init__(self):
        self.customers = [
            {"id": "1213210", "name": "John Doe", "email": "john@gmail.com", "phone": "123-456-7890", "username": "johndoe"},
            {"id": "2837622", "name": "Priya Patel", "email": "priya@candy.com", "phone": "987-654-3210", "username": "priya123"},
            {"id": "3924156", "name": "Liam Nguyen", "email": "lnguyen@yahoo.com", "phone": "555-123-4567", "username": "liamn"},
            {"id": "4782901", "name": "Aaliyah Davis", "email": "aaliyahd@hotmail.com", "phone": "111-222-3333", "username": "adavis"},
            {"id": "5190753", "name": "Hiroshi Nakamura", "email": "hiroshi@gmail.com", "phone": "444-555-6666", "username": "hiroshin"},
            {"id": "6824095", "name": "Fatima Ahmed", "email": "fatimaa@outlook.com", "phone": "777-888-9999", "username": "fatimaahmed"},
            {"id": "7135680", "name": "Alejandro Rodriguez", "email": "arodriguez@protonmail.com", "phone": "222-333-4444", "username": "alexr"},
            {"id": "8259147", "name": "Megan Anderson", "email": "megana@gmail.com", "phone": "666-777-8888", "username": "manderson"},
            {"id": "9603481", "name": "Kwame Osei", "email": "kwameo@yahoo.com", "phone": "999-000-1111", "username": "kwameo"},
            {"id": "1057426", "name": "Mei Lin", "email": "meilin@gmail.com", "phone": "333-444-5555", "username": "mlin"}
        ]

        self.orders = [
            {"id": "24601", "customer_id": "1213210", "product": "Wireless Headphones", "quantity": 1, "price": 79.99, "status": "Shipped"},
            {"id": "13579", "customer_id": "1213210", "product": "Smartphone Case", "quantity": 2, "price": 19.99, "status": "Processing"},
            {"id": "97531", "customer_id": "2837622", "product": "Bluetooth Speaker", "quantity": 1, "price": "49.99", "status": "Shipped"}, 
            {"id": "86420", "customer_id": "3924156", "product": "Fitness Tracker", "quantity": 1, "price": 129.99, "status": "Delivered"},
            {"id": "54321", "customer_id": "4782901", "product": "Laptop Sleeve", "quantity": 3, "price": 24.99, "status": "Shipped"},
            {"id": "19283", "customer_id": "5190753", "product": "Wireless Mouse", "quantity": 1, "price": 34.99, "status": "Processing"},
            {"id": "74651", "customer_id": "6824095", "product": "Gaming Keyboard", "quantity": 1, "price": 89.99, "status": "Delivered"},
            {"id": "30298", "customer_id": "7135680", "product": "Portable Charger", "quantity": 2, "price": 29.99, "status": "Shipped"},
            {"id": "47652", "customer_id": "8259147", "product": "Smartwatch", "quantity": 1, "price": 199.99, "status": "Processing"},
            {"id": "61984", "customer_id": "9603481", "product": "Noise-Cancelling Headphones", "quantity": 1, "price": 149.99, "status": "Shipped"},
            {"id": "58243", "customer_id": "1057426", "product": "Wireless Earbuds", "quantity": 2, "price": 99.99, "status": "Delivered"},
            {"id": "90357", "customer_id": "1213210", "product": "Smartphone Case", "quantity": 1, "price": 19.99, "status": "Shipped"},
            {"id": "28164", "customer_id": "2837622", "product": "Wireless Headphones", "quantity": 2, "price": 79.99, "status": "Processing"}
        ]

    def get_user(self, key, value):
        if key in {"email", "phone", "username"}:
            for customer in self.customers:
                if customer[key] == value:
                    return customer
            return f"Couldn't find a user with {key} of {value}"
        else:
            raise ValueError(f"Invalid key: {key}")
        
        return None

    def get_order_by_id(self, order_id):
        for order in self.orders:
            if order["id"] == order_id:
                return order
        return None
    
    def get_customer_orders(self, customer_id):
        return [order for order in self.orders if order["customer_id"] == customer_id]

    def cancel_order(self, order_id):
        order = self.get_order_by_id(order_id)
        if order:
            if order["status"] == "Processing":
                order["status"] = "Cancelled"
                return "Cancelled the order"
            else:
                return "Order has already shipped.  Can't cancel it."
        return "Can't find that order!"


DB = FakeDatabase()


DB_TOOL_SCHEMAS = [
    {
        "name": "get_user",
        "description": "Get the full user information based on their email, phone or username",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "enum": ["email", "phone", "username"],
                    "description": "The specific key field - email, phone or username - being used to retrieve the full user information"
                },
                "value": {
                    "type": "string",
                    "description": "The value of the key field for the user whose information is being retrieved."
                }
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "get_order_by_id",
        "description": "Retrieves the information for a customer order based on the order id",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "description": "The order ID"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "get_customer_orders",
        "description": "Get all orders from a given customer",
        "input_schema": {
            "type": "object",
            "properties": {"customer_id": {"type": "string", "description": "The customer ID for the customer whose orders are being retrieved"}},
            "required": ["customer_id"],
        },
    },
    {
        "name": "cancel_order",
        "description": "Cancels the specified order",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "description": "The order ID"}},
            "required": ["order_id"],
        },
    }
]
TOOL_MAP["get_user"] = lambda key, value: json.dumps(DB.get_user(key, value))
TOOL_MAP["get_order_by_id"] = lambda order_id: json.dumps(DB.get_order_by_id(order_id))
TOOL_MAP["get_customer_orders"] = lambda customer_id: json.dumps(DB.get_customer_orders(customer_id))
TOOL_MAP["cancel_order"] = DB.cancel_order


def print_assistant_messages(messages):
    for m in messages:
        print(m["role"].upper())
        for c in m["content"]:
            if c["type"] == "text":
                print(c["text"])
            elif c["type"] == "tool_use":
                print(f"Tool requested: {c['name']}")
                print(f"Tool request ID: {c['id']}")
                print(f"Tool input: {c['input']}")
            elif c["type"] == "tool_result":
                print(f"Tool request ID: {c['tool_use_id']}")
                print(f"Tool output: {c['content']}")


def start_user_chat(use_user_facing_xml_tags: bool = True):
    system_prompt = (
    "You are a helpful customer service chatbot.\n"
    "Your job is to help users look up their account, orders, and cancel orders.\n"
    "Be helpful and brief in your responses.\n"
    "You have access to a database with customer information. The database exposes the following functions: get_user; get_order_by_id; get_customer_orders; cancel_order. Only use the database functions when needed. If you do not have enough information to use a function correctly, ask a user follow up questions to get the required inputs. Do not call a function unless you have the required data from a user.\n"
    )
    if use_user_facing_xml_tags:
        system_prompt += "\nWhen answering the user, think about what you want to do first - including if you want to use any tools - and only answer the user afterwards.\n Wrap the part of your response intended for the user in <reply></reply> XML tags."
    message_history = []
    while True:
        user_message = input("USER: ")
        if user_message == "exit":
            return
        message_history.append({"role": "user", "content": user_message})
        updated_messages = sample_with_tools(
            model="claude-3-opus-20240229",
            system=system_prompt,
            messages=message_history,
            max_tokens=200,
            tools=DB_TOOL_SCHEMAS,
        )
        print_assistant_messages(updated_messages[len(message_history):])
        message_history=updated_messages
    

if __name__ == "__main__":
    start_user_chat()