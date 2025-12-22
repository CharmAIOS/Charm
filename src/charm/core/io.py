import sys
import json
from typing import Any, Dict

EVENT_PREFIX = "__CHARM_EVENT__"

class CharmEmitter:
    
    @staticmethod
    def _write(event_type: str, payload: Dict[str, Any]):
        data = {
            "type": event_type,
            **payload
        }
        json_str = json.dumps(data, ensure_ascii=False)
        sys.__stdout__.write(f"{EVENT_PREFIX}{json_str}\n")
        sys.__stdout__.flush()

    @staticmethod
    def emit_status(message: str):
        CharmEmitter._write("status", {"content": message})

    @staticmethod
    def emit_thinking(content: str):
        CharmEmitter._write("thinking", {"content": content})
    
    @staticmethod
    def emit_delta(content: str):
        CharmEmitter._write("delta", {"content": content})

    @staticmethod
    def emit_final(content: str, format: str = "markdown"):
        CharmEmitter._write("final", {"content": content, "format": format})

    @staticmethod
    def emit_error(message: str):
        CharmEmitter._write("error", {"content": message})
        
    @staticmethod
    def emit_artifact(name: str, url: str, mime: str):
        CharmEmitter._write("artifact", {"content": {"name": name, "url": url, "mime": mime}})

class StdoutInterceptor:
    def __init__(self):
        self.terminal = sys.__stdout__
        self.buffer = ""

    def write(self, message):
        if not message: return
        
        if message.startswith(EVENT_PREFIX):
            self.terminal.write(message)
            self.terminal.flush()
            return
            
        self.buffer += message
        if "\n" in self.buffer:
            lines = self.buffer.split("\n")
            for line in lines[:-1]:
                if line.strip():
                    payload = {"type": "thinking", "content": line + "\n"}
                    json_str = json.dumps(payload, ensure_ascii=False)
                    self.terminal.write(f'{EVENT_PREFIX}{json_str}\n')
            
            self.terminal.flush()
            self.buffer = lines[-1]

    def flush(self):
        if self.buffer.strip():
            payload = {"type": "thinking", "content": self.buffer + "\n"}
            json_str = json.dumps(payload, ensure_ascii=False)
            self.terminal.write(f'{EVENT_PREFIX}{json_str}\n')
            self.buffer = ""
        self.terminal.flush()