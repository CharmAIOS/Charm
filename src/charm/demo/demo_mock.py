import time
from typing import Dict, Any, Optional

class MockCrewLibrary:
    class Crew:
        def kickoff(self, inputs: Dict[str, Any]):
            print(f"  [CrewAI Internal] Kickoff with inputs: {inputs}")
            topic = inputs.get('topic', 'Unknown')
            time.sleep(0.5)
            return type('CrewOutput', (object,), {"raw": f"Crew Report: Analysis of '{topic}' complete."})()

class MockLangChainLibrary:
    class Graph:
        def invoke(self, state: Dict[str, Any]):
            print(f"  [LangChain Internal] Graph invoked with state: {state}")
            user_msg = state.get('messages', [''])[0]
            time.sleep(0.5)
            return {"messages": ["System", f"LangChain Response: I received '{user_msg}'."]}

MOCK_FILE_SYSTEM = {
    "./projects/writer_agent": {
        "charm.yaml": {
            "persona": {"name": "ProWriter"},
            "runtime": {
                "adapter": {"type": "crewai", "entry_point": "src.main:crew"}
            }
        },
        "code_object": MockCrewLibrary.Crew()
    },
    "./projects/chat_bot": {
        "charm.yaml": {
            "persona": {"name": "HelpBot"},
            "runtime": {
                "adapter": {"type": "langchain", "entry_point": "src.graph:app"}
            }
        },
        "code_object": MockLangChainLibrary.Graph()
    }
}

class CharmAgent:
    def __init__(self, name: str, adapter):
        self.name = name
        self.adapter = adapter

    def invoke(self, standard_input: Dict[str, Any]) -> Dict[str, Any]:
        return self.adapter.invoke(standard_input)

class CharmLoader:
    @staticmethod
    def load(path: str) -> CharmAgent:
        print(f"[Charm Loader] Loading project from: {path}")
        
        project_data = MOCK_FILE_SYSTEM.get(path)
        if not project_data:
            raise FileNotFoundError(f"Project not found at {path}")
        
        config = project_data["charm.yaml"]
        agent_name = config["persona"]["name"]
        adapter_config = config["runtime"]["adapter"]
        
        raw_agent = project_data["code_object"]
        
        adapter_type = adapter_config["type"]
        print(f"[Charm Loader] Detected framework: {adapter_type}")
        
        if adapter_type == "crewai":
            adapter = CharmCrewAIAdapter(raw_agent)
        elif adapter_type == "langchain":
            adapter = CharmLangChainAdapter(raw_agent)
        else:
            raise ValueError(f"Unsupported adapter: {adapter_type}")
            
        return CharmAgent(name=agent_name, adapter=adapter)

class CharmCrewAIAdapter:
    def __init__(self, crew):
        self.crew = crew

    def invoke(self, std_input: Dict) -> Dict:
        val = std_input.get("input", "")
        native_input = {"topic": val}
        
        native_output = self.crew.kickoff(native_input)
        
        return {"output": native_output.raw, "status": "success"}

class CharmLangChainAdapter:
    def __init__(self, graph):
        self.graph = graph

    def invoke(self, std_input: Dict) -> Dict:
        val = std_input.get("input", "")
        native_input = {"messages": [val]}
        
        native_output = self.graph.invoke(native_input)
        
        last_msg = native_output["messages"][-1]
        return {"output": last_msg, "status": "success"}

def run_store_simulation():
    print("Charm v1 Store Runtime: Universal Launcher")
    print("-" * 50)

    agent_paths = [
        "./projects/writer_agent",
        "./projects/chat_bot"
    ]

    user_request = {"input": "Explain Quantum Computing"}

    for path in agent_paths:
        print(f"--- Bootstrapping Agent: {path} ---")
        
        try:
            agent = CharmLoader.load(path)
            print(f"[Charm Runtime] Agent '{agent.name}' ready.")

            print(f"[Charm Runtime] Sending standard input: {user_request}")
            result = agent.invoke(user_request)

            print(f"[Charm Runtime] Standardized Output: {result}\n")
            
        except Exception as e:
            print(f"[Charm Runtime] Error running agent: {e}")

    print("Demo Complete: Multi-Framework Interoperability Verified")

if __name__ == "__main__":
    run_store_simulation()
