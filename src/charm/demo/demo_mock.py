import time
from typing import List, Dict, Any

class MockCrewLibrary:
    class Agent:
        def __init__(self, role: str, goal: str):
            self.role = role
            self.goal = goal
            self.tools = [] 

    class Crew:
        def __init__(self, agents: list):
            self.agents = agents

        def kickoff(self, inputs: Dict[str, Any]):
            print(f"\n[CrewAI Internal] Crew starting task with inputs: {inputs}")
            main_agent = self.agents[0]
            print(f"[CrewAI Internal] Agent '{main_agent.role}' is working...")
            
            if not main_agent.tools:
                print(f"[CrewAI Internal]  Warning: Agent has NO tools. Cannot search online.")
                return "Result: I don't know, I have no access to external info."
            else:
                print(f"[CrewAI Internal]  Agent found injected tools: {[t.name for t in main_agent.tools]}")

                search_tool = main_agent.tools[0]
                tool_result = search_tool.func("2025 AI Trends")
                return f"Result: Based on search '{tool_result}', Charm is the future."


def create_user_crew():

    writer = MockCrewLibrary.Agent(role="Tech Writer", goal="Write about AI")
    crew = MockCrewLibrary.Crew(agents=[writer])
    return crew


class CharmTool:

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
    
    def run(self, input_data: str) -> str:
        raise NotImplementedError("Tool must implement run method")

class BaseAdapter:
    def load(self, agent_instance): raise NotImplementedError
    def inject_tools(self, tools: List[CharmTool]): raise NotImplementedError
    def invoke(self, inputs: Dict) -> str: raise NotImplementedError
    def get_state(self) -> Dict: return {"status": "mock_state"}

class CharmCrewAIAdapter(BaseAdapter):

    def __init__(self, crew_instance):
        self.crew = crew_instance
        print(f"[Charm Adapter] Attached to CrewAI instance.")

    def inject_tools(self, charm_tools: List[CharmTool]):
        print(f"[Charm Adapter] Injecting {len(charm_tools)} system tools into CrewAI Agent...")
        
        
        native_tools = []
        for ct in charm_tools:

            class MockLangChainTool:
                name = ct.name
                description = ct.description
                func = ct.run
            native_tools.append(MockLangChainTool())
        

        for agent in self.crew.agents:
            agent.tools.extend(native_tools)
            print(f"[Charm Adapter]    -> Tool '{native_tools[0].name}' injected into Agent '{agent.role}'")

    def invoke(self, inputs: Dict) -> str:
        print(f"[Charm Adapter]  Forwarding execution to CrewAI...")
        return self.crew.kickoff(inputs)


class CharmWrapper:

    def __init__(self, agent, adapter_type: str, config: Dict):
        self.uac = config
        self.adapter = self._load_adapter(adapter_type, agent)
    
    def _load_adapter(self, type_name, agent):
        if type_name == "crewai":
            return CharmCrewAIAdapter(agent)
        raise ValueError("Unknown adapter")

    def set_tools(self, tools: List[CharmTool]):

        self.adapter.inject_tools(tools)

    def invoke(self, inputs: Dict):
        print(f"\n[Charm Runtime] Starting Execution via Wrapper...")

        print(f"[Charm Runtime]  Governance Check: Passed")
        return self.adapter.invoke(inputs)


def main():
    print("==================================================")
    print("   Charm v0.2.0 Demo: Wrapper & Injection Pattern")
    print("==================================================\n")


    print("--- Step 1: Loading User Agent (Source) ---")
    user_crew = create_user_crew()
    print("User agent loaded. (Note: It has NO tools inside)\n")


    print("--- Step 2: Reading UAC Contract ---")
    uac_config = {
        "persona": {"name": "WriterBot"},
        "runtime": {
            "adapter": {"type": "crewai"},
            "injections": {"tools": ["google-search"]}
        }
    }
    print(f"Contract loaded. Agent requires: {uac_config['runtime']['injections']['tools']}\n")

    print("--- Step 3: Initializing Charm Wrapper ---")
    wrapper = CharmWrapper(
        agent=user_crew, 
        adapter_type=uac_config['runtime']['adapter']['type'],
        config=uac_config
    )
    print("Wrapper initialized.\n")

    print("--- Step 4: Resolving Capabilities ---")
    class MockGoogleSearch(CharmTool):
        def run(self, query):
            return f"[Google Search Result for '{query}': AI is booming in 2025!]"
    
    system_tools = [MockGoogleSearch(name="google_search", description="Search the web")]
    print(f"System resolved tool: {system_tools[0].name}\n")


    print("--- Step 5: Dependency Injection ---")

    wrapper.set_tools(system_tools)
    print("Injection complete.\n")


    print("--- Step 6: Execution ---")
    result = wrapper.invoke({"topic": "AI Trends"})
    
    print("\n--------------------------------------------------")
    print(f"Final Output:\n{result}")
    print("==================================================")

if __name__ == "__main__":
    main()