class Agent:
    def __init__(self, role="", goal="", tools=None, verbose=False, name=None, backstory=None):
        self.role = role
        self.goal = goal
        self.tools = tools or []
        self.verbose = verbose
        if name:
            self.name = name
        if backstory:
            self.backstory = backstory

    def __repr__(self):
        return f"<Agent role={self.role!r}>"


class Task:
    def __init__(self, description="", expected_output="", agent=None):
        self.description = description
        self.expected_output = expected_output
        self.agent = agent

    def __repr__(self):
        return f"<Task desc={self.description!r}>"


class Crew:
    def __init__(self, agents=None, tasks=None):
        self.agents = agents or []
        self.tasks = tasks or []

    def __repr__(self):
        return f"<Crew agents={len(self.agents)}>"
