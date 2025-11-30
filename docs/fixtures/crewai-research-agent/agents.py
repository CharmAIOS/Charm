from .mock.crewai import Agent, Task, Crew
from .mock.crewai_tools import FileWriterTool, SerperDevTool
import os

os.environ["OPENAI_API_KEY"] = "<your-key>"

file_writer = FileWriterTool()
serper_tool = SerperDevTool()

project_analyst = Agent(
    role="Project Analyst",
    goal="Analyze project documents to identify risks and opportunities",
    tools=[file_writer, serper_tool],
    verbose=True
)

analysis_task = Task(
    description="Analyze the given project PDF and extract key findings.",
    expected_output="Markdown report with risks, strengths, and opportunities.",
    agent=project_analyst
)

crew = Crew(agents=[project_analyst], tasks=[analysis_task])
