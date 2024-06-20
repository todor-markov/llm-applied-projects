from copy import deepcopy
from datetime import datetime
import os
import json
import uuid
import anthropic
from pydantic import BaseModel, Field


class Note(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    note: str
    created: str
    tags: list[str] = Field(default_factory=list)


class Memory:
    def __init__(self, user: str, fpath: str):
        self.user = user
        self.fpath = fpath
        if os.path.exists(fpath):
            with open(fpath) as f:
                stored_memory = json.load(f)
            assert self.user == stored_memory["user"]
            assert self.fpath == stored_memory["fpath"]
            self.notes = [Note.model_validate(nt) for nt in stored_memory["notes"]]
            self.last_updated = stored_memory["last_updated"]
        else:
            self.notes = []
            self.last_updated = None
    
    def save_note(self, note: str, tags: list[str] = []):
        now = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.last_updated = now
        self.notes.append(Note(note=note, tags=tags, created=now))

    def save_memory(self):
        data = {
            "user": self.user,
            "fpath": self.fpath,
            "last_updated": self.last_updated,
            "notes": [n.model_dump() for n in self.notes]
        }
        with open(self.fpath, "w") as f:
            json.dump(data, f)

    def retrieve_all_notes(self) -> str:
        return json.dumps([n.model_dump() for n in self.notes])

    def retrieve_notes_with_tags(self, tags: list[str], retrieval_rule: str):
        assert retrieval_rule in ["any", "all"]
        choice_fn = any if retrieval_rule == "any" else all
        return json.dumps([n.model_dump() for n in self.notes if choice_fn([t in n.tags for t in tags])])
    
    def delete_note(self, note_id: uuid.UUID):
        self.notes = [n for n in self.notes if n.id != note_id]
        now = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.last_updated = now


MEMORY_TOOL_SCHEMAS = [
    {
        "name": "save_note",
        "description": "Saves a note in the memory system",
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "The note to be saved in memory",
                },
                "tags": {
                    "type": "array",
                    "description": "A list of tags for this note",
                    "items": {"type": "string"},
                },
            },
            "required": ["note"],
        },
    },
    {
        "name": "retrieve_all_notes",
        "description": "Retrieves all notes from memory",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "retrieve_notes_with_tags",
        "description": "Retrieve all notes tagged with the specified tags from memory",
        "input_schema": {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "description": "The list of tags for which to retrieve notes",
                    "items": {"type": "string"},
                },
                "retrieval_rule": {
                    "type": "string",
                    "enum": ["any", "all"],
                    "description": "Whether the function should return notes that have at least one of the tags, or all of the tags",
                }
            },
            "required": ["tags", "retrieval_rule"],
        },
    },
    {
        "name": "delete_note",
        "description": "Deletes a note from memory",
        "input_schema": {
            "type": "object",
            "properties": {"note_id": {"type": "string", "description": "The ID of the note to be deleted"}},
            "required": ["note_id"],
        },
    },
]


def sanitize_message(message) -> dict:
    message_dict = message.to_dict()
    for k in ["id", "model", "stop_reason", "stop_sequence", "type", "usage"]:
        del message_dict[k]
    return message_dict


def sample_with_tools(tool_map: dict, **claude_kwargs) -> list[dict]:
    messages = deepcopy(claude_kwargs["messages"])
    curr_res = client.messages.create(**claude_kwargs)
    while curr_res.stop_reason == "tool_use":
        tool_blocks = [c for c in curr_res.content if isinstance(c, anthropic.types.tool_use_block.ToolUseBlock)]
        tool_message = {"role": "user", "content": []}
        messages.append(sanitize_message(curr_res))
        for tb in tool_blocks:
            try:
                tool_output = tool_map[tb.name](**tb.input)
            except Exception as e:
                print(e)
                breakpoint()
            tool_message["content"].append(
                {
                    "type": "tool_result",
                    "tool_use_id": tb.id,
                    "content": tool_output,
                }
            )
        messages.append(tool_message)
        claude_kwargs["messages"] = messages
        try:
            curr_res = client.messages.create(**claude_kwargs)
        except Exception as e:
            print(e)
            breakpoint()
    messages.append(sanitize_message(curr_res))
    return messages


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


def start_user_chat(tool_map: dict, use_user_facing_xml_tags: bool = True):
    system_prompt = (
        "You are a helpful chatbot.\n"
        "You have access to a set of memory tools that allow you to save and retrieve notes about the user.\n"
        "You can access your memory through the following functions:\n"
        ":save_note: saves a note to your memory for future reference\n"
        ":retrieve_all_notes: retrieves all notes from your memory\n"
        ":retrieve_notes_with_tags: retrieves all notes with the specified tags from your memory\n"
        ":delete_note: deletes the specified note from your memory\n"
        "Help the user to the best of your ability\n"
        "If you need more information to help the user, always check your notes first before asking for the additional information\n"
        "If you can directly help the user with what they need without consulting your memory or asking for more information, do so."
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
            tool_map=tool_map,
            model="claude-3-opus-20240229",
            system=system_prompt,
            messages=message_history,
            max_tokens=300,
            tools=MEMORY_TOOL_SCHEMAS,
        )
        print_assistant_messages(updated_messages[len(message_history):])
        message_history=updated_messages



if __name__ == "__main__":
    user = "todor"
    mem = Memory(user="todor", fpath=f"{user}_memory.json")
    client = anthropic.Anthropic()
    TOOL_MAP = {
        "save_note": mem.save_note,
        "retrieve_all_notes": mem.retrieve_all_notes,
        "retrieve_notes_with_tags": mem.retrieve_notes_with_tags,
        "delete_note": mem.delete_note,
    }
    start_user_chat(tool_map=TOOL_MAP)
    mem.save_memory()
