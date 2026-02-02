import json
import os
import re
import subprocess
import threading
from typing import Any, Dict, List, Optional

from ..contracts.uac import CharmConfig
from ..core.io import CharmEmitter
from ..core.logger import logger
from .base import BaseAdapter


class CharmOpenClawAdapter(BaseAdapter):
    """
    Adapter for the OpenClaw Host (MCP Client).
    It manages the lifecycle of the OpenClaw process, translates Charm Skills into
    MCP Server configurations, and bridges the I/O between Charm and OpenClaw.
    """

    def __init__(self, config: CharmConfig):
        # OpenClaw is config-driven, so we initialize BaseAdapter with None for agent_instance
        super().__init__(None)
        self.config = config
        self.work_dir = os.getcwd()

        # [Config] OpenClaw Workspace Paths
        # 我們將 Workspace 指向容器內的持久化路徑或當前目錄的子目錄
        # 確保與 Dockerfile 中的 ENV OPENCLAW_WORKSPACE 一致
        self.openclaw_home = os.getenv("OPENCLAW_HOME", os.path.expanduser("~/.openclaw"))
        self.workspace_dir = os.getenv(
            "OPENCLAW_WORKSPACE", os.path.join(self.openclaw_home, "workspace")
        )

        # [Memory] Standard OpenClaw memory file
        self.memory_file = os.path.join(self.workspace_dir, "MEMORY.md")

    def _inject_memory(self, history: List[Dict[str, Any]]):
        """
        將 Charm 的用戶 Profile 和對話歷史注入到 OpenClaw 的長期記憶檔案中。
        """
        try:
            if not os.path.exists(self.workspace_dir):
                os.makedirs(self.workspace_dir, exist_ok=True)

            # 1. 獲取全域用戶設定 (User Profile)
            # 這通常由 Runner 從 DB 獲取並注入到環境變數中
            user_profile = os.getenv(
                "CHARM_USER_PROFILE", "User prefers concise and accurate answers."
            )

            # 2. 構建記憶內容
            # OpenClaw 啟動時會讀取這個檔案作為 Context
            content = []
            content.append(f"# User Profile\n{user_profile}\n")

            if history:
                content.append("# Recent Context\n")
                # 取最近 10 輪對話，避免 Context Window 爆炸
                for msg in history[-10:]:
                    role = msg.get("role", "unknown").upper()
                    text = msg.get("content", "")
                    content.append(f"- **{role}**: {text}")

            final_memory = "\n".join(content)

            with open(self.memory_file, "w", encoding="utf-8") as f:
                f.write(final_memory)

            logger.info(f"Injected memory context into: {self.memory_file}")

        except Exception as e:
            logger.warning(f"Failed to inject memory: {e}")

    def _generate_openclaw_config(self) -> str:
        """
        將 charm.yaml 中的 'runtime.skills' 轉換為標準 MCP Servers 設定檔 (JSON)。
        """
        mcp_servers = {}

        if self.config.runtime.skills:
            for skill in self.config.runtime.skills:
                server_config = {}

                # --- A. Smithery / NPM Skills ---
                if skill.source.startswith("smithery:") or skill.source.startswith("npm:"):
                    pkg_name = skill.source.replace("smithery:", "").replace("npm:", "")
                    # 使用 npx 執行 (確保 @smithery/cli 已安裝或即時下載)
                    server_config = {
                        "command": "npx",
                        "args": [
                            "-y",
                            "@smithery/cli",
                            "run",
                            pkg_name,
                            "--config",
                            json.dumps(skill.config),
                        ],
                    }

                # --- B. Python / PyPI Skills ---
                elif skill.source.startswith("pip:") or skill.source.startswith("pypi:"):
                    pkg_name = skill.source.replace("pip:", "").replace("pypi:", "")
                    # 使用 uvx (uv tool run) 執行，這是最快且隔離最好的方式
                    server_config = {"command": "uvx", "args": [pkg_name]}

                # --- C. Local Skills (Repositories) ---
                elif skill.source.startswith("local:"):
                    # Executor 在 Phase 3 會將 skill 連結到當前目錄
                    # 路徑範例: local:./skills/browser-use -> ./skills/browser-use
                    rel_path = skill.source.replace("local:", "")
                    abs_path = os.path.abspath(rel_path)

                    if not os.path.exists(abs_path):
                        logger.warning(f"Skill path not found: {abs_path}")
                        continue

                    # 自動偵測啟動方式
                    if os.path.isfile(abs_path):
                        # 如果指向單一檔案
                        if abs_path.endswith(".py"):
                            server_config = {"command": "python", "args": [abs_path]}
                        elif abs_path.endswith(".js"):
                            server_config = {"command": "node", "args": [abs_path]}
                    else:
                        # 如果指向目錄，檢查常見入口
                        if os.path.exists(os.path.join(abs_path, "pyproject.toml")):
                            # Python 專案，使用 uv run
                            server_config = {
                                "command": "uv",
                                "args": [
                                    "run",
                                    "python",
                                    "-m",
                                    "server",
                                ],  # 假設 module 名為 server
                                "cwd": abs_path,  # 設定工作目錄
                            }
                        elif os.path.exists(os.path.join(abs_path, "package.json")):
                            # Node 專案
                            server_config = {"command": "npm", "args": ["start"], "cwd": abs_path}
                        else:
                            # Fallback: 嘗試執行 server.py
                            server_config = {
                                "command": "python",
                                "args": [os.path.join(abs_path, "server.py")],
                            }

                # --- Auth & Env Injection ---
                # 將 charm.yaml 定義的 config 轉為環境變數
                env_vars = skill.config.copy() if skill.config else {}

                # 自動注入全域 API Keys (如果環境變數有)
                for key in [
                    "OPENAI_API_KEY",
                    "ANTHROPIC_API_KEY",
                    "TAVILY_API_KEY",
                    "GOOGLE_API_KEY",
                ]:
                    if key not in env_vars and os.environ.get(key):
                        env_vars[key] = os.environ[key]

                if env_vars:
                    server_config["env"] = env_vars

                mcp_servers[skill.name] = server_config

        # 構建完整設定
        full_config = {
            "mcpServers": mcp_servers,
            "workspace": self.workspace_dir,
            # 可以根據 charm.yaml 擴充這裡，例如指定模型
            # "llm": { "model": "claude-3-5-sonnet-latest" }
        }

        config_path = os.path.join(self.work_dir, "openclaw_runtime_config.json")
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(full_config, f, indent=2)
            logger.info(f"Generated OpenClaw Config: {config_path}")
        except Exception as e:
            logger.error(f"Failed to write config: {e}")
            raise e

        return config_path

    def _parse_log(self, line: str):
        """
        解析 OpenClaw 的 stdout/stderr，轉為 Charm 的 UI 事件。
        Regex 需根據 OpenClaw 實際輸出調整。
        """
        clean_line = line.strip()
        if not clean_line:
            return

        # [Log Type 1] Thinking / Planning
        # OpenClaw 輸出範例: "Thought: I need to use google-search..."
        if re.match(r"^(Thought|Plan|Reasoning):", clean_line, re.IGNORECASE):
            content = clean_line.split(":", 1)[1].strip()
            CharmEmitter.emit_thinking(content)

        # [Log Type 2] Tool Execution
        # OpenClaw 輸出範例: "Calling tool 'google-search' with args..."
        elif re.match(r"^(Calling|Executing|Tool):", clean_line, re.IGNORECASE):
            CharmEmitter.emit_thinking(f"🛠️ {clean_line}")

        # [Log Type 3] Artifact Generation
        # 假設 OpenClaw 輸出: "Created artifact: /path/to/file.pdf"
        elif "Created artifact:" in clean_line:
            match = re.search(r"Created artifact:\s*(.+)", clean_line)
            if match:
                path = match.group(1).strip()
                name = os.path.basename(path)
                # 使用 mime="auto" 讓 Runner 自動判斷
                CharmEmitter.emit_artifact(name=name, url=path, mime="auto")

        # [Log Type 4] Errors
        elif "Error:" in clean_line or "Exception" in clean_line:
            # 過濾掉噪音警告
            if "DeprecationWarning" not in clean_line:
                CharmEmitter.emit_error(clean_line)

        else:
            # 其他訊息作為 debug log
            logger.debug(f"[OpenClaw] {clean_line}")

    def invoke(
        self, inputs: Dict[str, Any], callbacks: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        logger.info(" Booting OpenClaw Adapter...")

        # 1. 記憶注入
        self._inject_memory(inputs.get("__charm_history__", []))

        # 2. 設定檔生成
        config_path = self._generate_openclaw_config()

        # 3. 準備用戶輸入
        user_input = inputs.get("input", "")
        # 如果有特定變數注入，拼接到 Prompt
        for k, v in inputs.items():
            if k not in ["input", "__charm_history__"]:
                user_input += f"\n\n[{k}]: {v}"

        # 4. 啟動 OpenClaw CLI
        # 使用 npm install -g 安裝後的 'openclaw' 指令
        # 模式: 單次執行 (exec / run)
        cmd = ["openclaw", "run", "--config", config_path, "--prompt", user_input]

        logger.info(f"Executing Command: {' '.join(cmd)}")

        # 複製環境變數，確保 API Keys 傳遞
        env = os.environ.copy()
        # 強制指定 HOME，避免找不到 .openclaw 目錄
        env["HOME"] = "/root"

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                env=env,
            )
        except FileNotFoundError:
            return {
                "status": "error",
                "message": "OpenClaw binary not found. Is it installed in the Docker image?",
            }

        stdout_lines = []
        final_output = ""

        # 定義 Stream Reader
        def read_stream(stream, is_stderr):
            nonlocal final_output
            for line in stream:
                # 只有 stdout 才包含結果，stderr 通常是 log
                if not is_stderr:
                    # 簡單啟發式：如果包含 "Final Answer:" 則提取後面的內容
                    if "Final Answer:" in line:
                        final_output = line.split("Final Answer:", 1)[1].strip()
                    else:
                        stdout_lines.append(line)

                # 統一解析 Log 並 Emit 事件
                self._parse_log(line)

        # 雙線程讀取，避免 Buffer 塞滿導致 Deadlock
        t_out = threading.Thread(target=read_stream, args=(process.stdout, False))
        t_err = threading.Thread(target=read_stream, args=(process.stderr, True))

        t_out.start()
        t_err.start()

        process.wait()
        t_out.join()
        t_err.join()

        if process.returncode != 0:
            return {"status": "error", "message": f"OpenClaw exited with code {process.returncode}"}

        # 如果沒抓到 "Final Answer:" 標籤，嘗試使用 stdout 最後一段作為結果
        if not final_output and stdout_lines:
            # 過濾掉明顯的 Log 行
            clean_output = [
                l for l in stdout_lines if not l.startswith("[") and "Thought:" not in l
            ]
            if clean_output:
                final_output = "\n".join(clean_output[-10:])  # 取最後 10 行

        return {
            "status": "success",
            "output": final_output or "Task completed successfully (check artifacts).",
            "charm_state": "",  # 暫無 State Snapshot
        }

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_tools(self, tools: List[Any]) -> None:
        pass
