import sys
import json
from typing import Any, Dict

EVENT_PREFIX = "__CHARM_EVENT__"

class CharmEmitter:
    """負責發送符合 Charm SSE 協議的結構化事件"""
    
    @staticmethod
    def _write(event_type: str, payload: Dict[str, Any]):
        """將事件包裝成協議格式寫入 stdout"""
        data = {
            "type": event_type,
            **payload
        }
        # 確保只有單一行，且立即 Flush
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
    def emit_final(content: str, format: str = "markdown"):
        CharmEmitter._write("final", {"content": content, "format": format})

    @staticmethod
    def emit_error(message: str):
        CharmEmitter._write("error", {"content": message})
        
    @staticmethod
    def emit_artifact(name: str, url: str, mime: str):
        CharmEmitter._write("artifact", {"content": {"name": name, "url": url, "mime": mime}})

class StdoutInterceptor:
    """攔截標準輸出，將其轉換為 Thinking 事件"""
    def __init__(self):
        self.terminal = sys.__stdout__
        self.buffer = ""

    def write(self, message):
        if not message: return
        
        # 如果是我們自己發出的協議字串，直接放行
        if message.startswith(EVENT_PREFIX):
            self.terminal.write(message)
            self.terminal.flush()
            return
            
        # 將所有攔截到的普通 print 視為 "thinking"
        self.buffer += message
        if "\n" in self.buffer:
            lines = self.buffer.split("\n")
            for line in lines[:-1]:
                if line.strip():
                    # [FIX] 修正 f-string 反斜線語法錯誤
                    # 先把 JSON 轉成字串變數，再放進 f-string
                    payload = {"type": "thinking", "content": line + "\n"}
                    json_str = json.dumps(payload, ensure_ascii=False)
                    self.terminal.write(f'{EVENT_PREFIX}{json_str}\n')
            
            self.terminal.flush()
            self.buffer = lines[-1]

    def flush(self):
        if self.buffer.strip():
            # [FIX] 同樣修正 flush 裡的語法
            payload = {"type": "thinking", "content": self.buffer + "\n"}
            json_str = json.dumps(payload, ensure_ascii=False)
            self.terminal.write(f'{EVENT_PREFIX}{json_str}\n')
            self.buffer = ""
        self.terminal.flush()