class Agent:
    def __init__(self, role="", goal="", tools=None, verbose=False, name=None, backstory=None):
        self.role = role
        self.goal = goal
        self.tools = tools or []
        self.verbose = verbose
        self.name = name
        self.backstory = backstory

    def __repr__(self):
        return f"<Agent role={self.role}>"

class Task:
    def __init__(self, description="", expected_output="", agent=None):
        self.description = description
        self.expected_output = expected_output
        self.agent = agent

class Crew:
    def __init__(self, agents=None, tasks=None):
        self.agents = agents or []
        self.tasks = tasks or []

  --
class Agent:
    def __init__(self, role=None, goal=None, tools=None, verbose=None):
        self.role = role
        self.goal = goal
        self.tools = tools or []
        self.verbose = verbose

class Task:
    def __init__(self, description=None, expected_output=None, agent=None):
        self.description = description
        self.expected_output = expected_output
        self.agent = agent

class Crew:
    def __init__(self, agents=None, tasks=None):
        self.agents = agents or []
        self.tasks = tasks or []
