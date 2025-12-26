import os
from pathlib import Path

import PyPDF2
from crewai import Agent, Crew, Process, Task
from crewai_tools import (
    EXASearchTool,
    FileWriterTool,
    GithubSearchTool,
    LinkupSearchTool,
    SerperDevTool,
)
from dotenv import load_dotenv

_ = load_dotenv()

# Set environment variables for custom API endpoint
os.environ["OPENAI_API_BASE"] = "https://api.aimlapi.com/v1"
os.environ["OPENAI_API_KEY"] = os.getenv("AIML_API_KEY", "<YOUR_API_KEY>")

# Create dedicated output folders
output_folder = Path("project_analysis_output")
output_folder.mkdir(exist_ok=True)

resource_folder = Path("resource_output")
resource_folder.mkdir(exist_ok=True)

code_folder = Path("code_output")
code_folder.mkdir(exist_ok=True)

# Configure LLM for CrewAI
llm_config = "openai/gpt-5-chat-latest"

# Initialize tools
file_writer = FileWriterTool()
serper_tool = SerperDevTool()
github_search_tool = GithubSearchTool(
    gh_token=os.getenv("GITHUB_TOKEN"),
    content_types=["code", "issue"],  # Options: code, repo, pr, issue
    max_results=500,  # Limit to 500 results to control token usage
)
linkup_tool = LinkupSearchTool(api_key=os.getenv("LINKUP_API_KEY"))
exascience_tool = EXASearchTool(api_key=os.getenv("EXA_API_KEY"))


# Function to read PDF content
def read_pdf_content(pdf_path: str) -> str:
    """Read and extract text content from PDF"""
    try:
        with open(pdf_path, "rb") as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text_content = ""

            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text_content += page.extract_text() + "\n"

            return text_content
    except Exception as e:
        return f"Error reading PDF: {str(e)}"


# Read the PDF content first
pdf_content = read_pdf_content("my saas project (1).pdf")

# Define the Project Analysis Agent
project_analyst = Agent(
    role="Project Analyst",
    goal="Analyze project documents to identify risks, strengths, and opportunities.",
    backstory=(
        "You are a skilled project analyst who can read project documents and "
        "extract meaningful insights, risks, and opportunities. "
        "You have access to the full project document content and can research "
        "similar projects on the web to provide comprehensive market analysis."
    ),
    tools=[file_writer, serper_tool],
    verbose=True,
    memory=True,
    llm=llm_config,
    allow_code_execution=False,
)

# Define the Resource Search Agent
resource_search_agent = Agent(
    role="Resource Search Specialist",
    goal="Efficiently locate and curate the most relevant, high-quality resources from multiple platforms to accelerate development and research.",
    backstory=(
        "A specialized research librarian with deep knowledge of developer communities, "
        "academic databases, and open-source ecosystems. Expert at evaluating resource quality, "
        "licensing compatibility, and relevance scoring."
    ),
    allow_code_execution=False,
    tools=[file_writer, serper_tool, github_search_tool, linkup_tool],
    verbose=True,
    memory=True,
    llm=llm_config,
)

# Define the Coding Agent with code execution capabilities
# This agent can write, execute, and debug Python code using the built-in CodeInterpreterTool
# The allow_code_execution=True parameter enables the agent to run code and handle errors
coding_agent = Agent(
    role="Senior Full-Stack Developer & Code Architect",
    goal="Generate production-ready, modular code that accelerates development while maintaining best practices and extensibility.",
    backstory=(
        "A senior full-stack developer and architect with expertise across multiple programming languages, "
        "frameworks, and design patterns. Specializes in rapid prototyping while maintaining code quality and scalability. "
        "Expert in Python, JavaScript/TypeScript, React, Node.js, and modern development practices. "
        "Can write, execute, and debug code to solve complex problems. "
        "Has access to code execution tools to test and validate generated code in real-time."
    ),
    tools=[file_writer],
    verbose=True,
    memory=True,
    allow_code_execution=False,  # Enable code execution capability
    llm=llm_config,
)

# Define the task for analyzing the PDF
analysis_task = Task(
    description=(
        f"Analyze the following project document content and identify key project goals, risks, challenges, and potential improvements. "
        f"Your final answer MUST be structured as a Markdown report with sections for Summary, Risks, Strengths, and Opportunities.\n\n"
        f"Project Document Content:\n{pdf_content}..."
    ),
    expected_output="A structured Markdown analysis report of the project.",
    agent=project_analyst,
)

# Define the Project Context Analysis task with web research
project_context_task = Task(
    description=(
        f"CRITICAL: You MUST read the PDF content from the input context and extract REAL information.\n\n"
        f"SPECIFIC INSTRUCTIONS:\n"
        f"1. Look at the 'full_content' field in the input\n"
        f"2. Extract the actual project name from the 'project_name' field\n"
        f"3. Find real requirements mentioned in the PDF content\n"
        f"4. Identify actual technology stack mentioned in the 'technology_stack' field\n"
        f"5. Extract real project objectives and scope from the PDF text\n"
        f"6. Find actual constraints and limitations mentioned\n"
        f"7. Identify real dependencies and relationships\n"
        f"8. Extract actual risks and mitigation strategies\n"
        f"9. Find real timeline and milestones from the 'timeline_info' field\n"
        f"10. Extract actual team information and roles from the 'team_info' field\n"
        f"11. Find real budget and resource information from the 'budget_info' field\n\n"
        f"WEB RESEARCH: Use SerperDevTool to search for similar AI-powered social media marketing platforms and analyze:\n"
        f"- Current market leaders (Hootsuite, Buffer, Sprout Social, Later)\n"
        f"- Their key features and pricing\n"
        f"- Market gaps and opportunities\n"
        f"- Recent funding and acquisition news\n\n"
        f"USE FileWriterTool to write this to '{output_folder}/project_analysis.md'\n"
        f"DO NOT use placeholders like [Detail] or [Project Name] - use REAL data from the PDF!\n\n"
        f"Project Document Content:\n{pdf_content}"
    ),
    expected_output=(
        f"A REAL project analysis report saved as '{output_folder}/project_analysis.md' containing:\n"
        "- ACTUAL project name from the PDF (not [Project Name])\n"
        "- REAL requirements extracted from the PDF content (not [Detail])\n"
        "- ACTUAL technology stack mentioned in the PDF (not [Technology 1])\n"
        "- REAL project objectives and scope from the PDF content\n"
        "- ACTUAL constraints and limitations found in the PDF\n"
        "- REAL dependencies and relationships identified\n"
        "- ACTUAL risks and mitigation strategies\n"
        "- REAL timeline and milestones from the PDF\n"
        "- ACTUAL team information and roles\n"
        "- REAL budget and resource information\n"
        "- WEB RESEARCH: Market analysis of similar platforms, competitors, and opportunities\n\n"
        "Use FileWriterTool to save this with real data extracted from the PDF content and web research."
    ),
    agent=project_analyst,
)

# Define the Objective Clarification task with market research
objective_task = Task(
    description=(
        f"CRITICAL: Based on the ACTUAL PDF content in the input, break down real project goals into specific objectives.\n\n"
        f"SPECIFIC INSTRUCTIONS:\n"
        f"1. Read the 'full_content' field in the input\n"
        f"2. Extract the actual project goals mentioned in the PDF\n"
        f"3. Identify real secondary goals from the PDF content\n"
        f"4. Find specific acceptance criteria mentioned in the PDF\n"
        f"5. Determine recommended project phases based on the real scope\n\n"
        f"WEB RESEARCH: Use SerperDevTool to research:\n"
        f"- Successful social media marketing platform launches\n"
        f"- Market validation strategies for AI tools\n"
        f"- User acquisition patterns in the social media space\n"
        f"- Industry benchmarks for engagement and ROI metrics\n\n"
        f"USE FileWriterTool to write this to '{output_folder}/project_objectives.md'\n"
        f"DO NOT use placeholders - use REAL data from the PDF!\n\n"
        f"Project Document Content:\n{pdf_content}"
    ),
    expected_output=(
        f"A REAL objectives document saved as '{output_folder}/project_objectives.md' containing:\n"
        "- ACTUAL primary goals extracted from the PDF content (not [Objective 1])\n"
        "- REAL secondary goals identified in the project (not [Goal 1])\n"
        "- SPECIFIC acceptance criteria based on the actual requirements (not [Criterion 1])\n"
        "- RECOMMENDED project phases based on the real project scope (not [Phase 1])\n"
        "- WEB RESEARCH: Market validation insights and industry benchmarks\n\n"
        "Use FileWriterTool to save this with real data, not placeholders."
    ),
    agent=project_analyst,
)

# Define the Technical Feasibility Assessment task with technology research
technical_task = Task(
    description=(
        f"CRITICAL: Evaluate the technical complexity of the ACTUAL project described in the PDF content.\n\n"
        f"SPECIFIC INSTRUCTIONS:\n"
        f"1. Read the 'full_content' field in the input\n"
        f"2. Analyze the real technology stack mentioned in the 'technology_stack' field\n"
        f"3. Assess the actual project complexity based on real requirements\n"
        f"4. Identify real prerequisite skills needed for the specific technologies\n"
        f"5. Recommend project-specific fallback solutions based on real constraints\n\n"
        f"WEB RESEARCH: Use SerperDevTool to research:\n"
        f"- Latest AI/ML technologies for social media content generation\n"
        f"- Social media API limitations and best practices\n"
        f"- Successful tech stacks used by similar platforms\n"
        f"- Development timeframes for AI-powered marketing tools\n"
        f"- Technical challenges in social media automation\n\n"
        f"USE FileWriterTool to write this to '{output_folder}/technical_assessment.md'\n"
        f"DO NOT use placeholders - use REAL data from the PDF!\n\n"
        f"Project Document Content:\n{pdf_content}"
    ),
    expected_output=(
        f"A REAL technical assessment saved as '{output_folder}/technical_assessment.md' containing:\n"
        "- ACTUAL project complexity rating based on the real requirements (not generic ratings)\n"
        "- REAL prerequisite skills analysis for the specific technologies mentioned (not [Language 1])\n"
        "- PROJECT-SPECIFIC fallback solution recommendations based on real constraints (not generic solutions)\n"
        "- WEB RESEARCH: Latest AI/ML technologies, API limitations, and technical challenges\n\n"
        "Use FileWriterTool to save this with real data, not placeholders."
    ),
    agent=project_analyst,
)

# Define the Resource Requirements Planning task with market insights
resource_task = Task(
    description=(
        f"CRITICAL: Based on the ACTUAL project requirements from the PDF, determine what real resources are needed.\n\n"
        f"SPECIFIC INSTRUCTIONS:\n"
        f"1. Read the 'full_content' field in the input\n"
        f"2. Analyze the actual technology stack mentioned in the 'technology_stack' field\n"
        f"3. Identify real datasets needed for the specific project\n"
        f"4. Determine actual documentation requirements based on the real scope\n"
        f"5. Find real resources and tools needed for the specific technologies\n"
        f"6. Identify actual APIs and services required for the project\n\n"
        f"WEB RESEARCH: Use SerperDevTool to research:\n"
        f"- Current costs for AI/ML development services\n"
        f"- Social media API pricing and rate limits\n"
        f"- Market rates for social media marketing developers\n"
        f"- Required infrastructure and hosting costs\n"
        f"- Legal and compliance costs for social media tools\n\n"
        f"USE FileWriterTool to write this to '{output_folder}/resource_planning.md'\n"
        f"DO NOT use placeholders - use REAL data from the PDF!\n\n"
        f"Project Document Content:\n{pdf_content}"
    ),
    expected_output=(
        f"A REAL resource plan saved as '{output_folder}/resource_planning.md' containing:\n"
        "- ACTUAL datasets needed for the specific project (not generic datasets)\n"
        "- REAL documentation requirements based on the project scope (not generic docs)\n"
        "- ACTUAL resources and tools needed for the specific technologies (not generic tools)\n"
        "- REAL APIs and services required for the project (not generic APIs)\n"
        "- WEB RESEARCH: Current market costs, developer rates, and infrastructure pricing\n\n"
        "Use FileWriterTool to save this with real data, not placeholders."
    ),
    agent=project_analyst,
)

# Define Resource Search Tasks (Second Agent)
# Task 1: Multi-platform resource discovery
multi_platform_discovery_task = Task(
    description=(
        f"Based on the project analysis files created by the first agent, search across GitHub, Kaggle, ArXiv, StackOverflow, and documentation sites using "
        f"intelligent query expansion and semantic matching.\n\n"
        f"SPECIFIC INSTRUCTIONS:\n"
        f"1. Read the analysis files from '{output_folder}/' to understand the project requirements\n"
        f"2. Use SerperDevTool to search for relevant resources based on the technology stack and requirements identified\n"
        f"3. Focus on AI/ML tools, social media APIs, and development frameworks mentioned in the project\n"
        f"4. Search across multiple platforms for comprehensive coverage\n"
        f"5. CRITICAL: You MUST find and document AT LEAST 10 different resources across all platforms\n"
        f"6. Use multiple search queries to ensure comprehensive coverage\n"
        f"7. Search for: AI marketing tools, social media automation, content generation APIs, analytics platforms\n\n"
        f"USE FileWriterTool to write this to '{resource_folder}/multi_platform_resources.md'\n"
    ),
    expected_output=(
        f"A comprehensive resource discovery report saved as '{resource_folder}/multi_platform_resources.md' containing:\n"
        "- AT LEAST 10 different resources with relevance scores\n"
        "- Platform source for each resource\n"
        "- Brief descriptions and use cases\n"
        "- Direct links to the resources\n"
        "- Categorized by platform (GitHub, Kaggle, ArXiv, StackOverflow, Documentation)\n\n"
        "Use FileWriterTool to save this with real search results. Ensure you have at least 10 resources total."
    ),
    agent=resource_search_agent,
)

# Task 2: Code repository analysis and filtering
code_repository_analysis_task = Task(
    description=(
        f"Based on the project analysis, analyze GitHub repositories for code quality, maintenance status, licensing, and "
        f"compatibility with project requirements.\n\n"
        f"SPECIFIC INSTRUCTIONS:\n"
        f"1. Read the analysis files from '{output_folder}/' to understand the project scope\n"
        f"2. Use SerperDevTool AND GithubSearchTool to find relevant GitHub repositories\n"
        f"3. Evaluate repositories for quality, maintenance, and licensing compatibility\n"
        f"4. Focus on repositories related to AI/ML, social media tools, and the specific technologies mentioned\n"
        f"5. CRITICAL: You MUST find and analyze AT LEAST 10 different GitHub repositories\n"
        f"6. Search for: social media marketing tools, AI content generation, marketing automation, analytics platforms\n"
        f"7. Use multiple search terms and filters to ensure comprehensive coverage\n\n"
        f"USE FileWriterTool to write this to '{resource_folder}/code_repositories.md'\n"
    ),
    expected_output=(
        f"A curated repository analysis saved as '{resource_folder}/code_repositories.md' containing:\n"
        "- AT LEAST 10 different GitHub repositories with quality metrics\n"
        "- License compatibility flags\n"
        "- Integration difficulty assessments\n"
        "- Maintenance status and community activity\n"
        "- Direct links to each repository\n"
        "- Star count, last updated, and language information\n\n"
        "Use FileWriterTool to save this with real repository analysis. Ensure you have at least 10 repositories."
    ),
    agent=resource_search_agent,
)

# Task 3: Dataset discovery and validation
dataset_discovery_task = Task(
    description=(
        f"Based on the project requirements, find relevant datasets on Kaggle, academic repositories, and government data portals, "
        f"validating data quality and format compatibility.\n\n"
        f"SPECIFIC INSTRUCTIONS:\n"
        f"1. Read the analysis files from '{output_folder}/' to understand data needs\n"
        f"2. Use SerperDevTool to search for relevant datasets\n"
        f"3. Focus on social media data, AI/ML training datasets, and marketing analytics data\n"
        f"4. Evaluate data quality, format, and licensing\n"
        f"5. CRITICAL: You MUST find and document AT LEAST 10 different datasets\n"
        f"6. Search for: social media engagement data, marketing campaign data, user behavior datasets, content performance data\n"
        f"7. Include datasets from: Kaggle, UCI ML Repository, Google Dataset Search, AWS Open Data, academic sources\n"
        f"8. Use multiple search queries to ensure comprehensive coverage\n\n"
        f"USE FileWriterTool to write this to '{resource_folder}/datasets.md'\n"
    ),
    expected_output=(
        f"A dataset catalog saved as '{resource_folder}/datasets.md' containing:\n"
        "- AT LEAST 10 different datasets with size metrics\n"
        "- Format specifications and quality indicators\n"
        "- Usage examples and integration notes\n"
        "- Licensing and access information\n"
        "- Direct links to download/access each dataset\n"
        "- Source platform and last updated information\n\n"
        "Use FileWriterTool to save this with real dataset findings. Ensure you have at least 10 datasets."
    ),
    agent=resource_search_agent,
)

# Task 4: Academic paper and documentation retrieval
academic_paper_task = Task(
    description=(
        f"Based on the project scope, search ArXiv, research databases, and technical documentation for relevant papers, "
        f"tutorials, and implementation guides.\n\n"
        f"SPECIFIC INSTRUCTIONS:\n"
        f"1. Read the analysis files from '{output_folder}/' to understand research needs\n"
        f"2. Use SerperDevTool to search academic and technical sources\n"
        f"3. Focus on AI/ML research, social media analytics, and marketing automation papers\n"
        f"4. Look for implementation guides and best practices\n"
        f"5. CRITICAL: You MUST find and document AT LEAST 10 different academic resources\n"
        f"6. Search for: social media marketing research, AI content generation papers, marketing automation studies, analytics methodologies\n"
        f"7. Include sources from: ArXiv, Google Scholar, ResearchGate, IEEE Xplore, ACM Digital Library, arXiv.org\n"
        f"8. Use multiple search queries and keywords to ensure comprehensive coverage\n\n"
        f"USE FileWriterTool to write this to '{resource_folder}/academic_resources.md'\n"
    ),
    expected_output=(
        f"An annotated bibliography saved as '{resource_folder}/academic_resources.md' containing:\n"
        "- AT LEAST 10 different academic resources with paper summaries\n"
        "- Implementation difficulty ratings\n"
        "- Code availability indicators\n"
        "- Relevance to project requirements\n"
        "- Direct links to papers and documentation\n"
        "- Publication date and author information\n\n"
        "Use FileWriterTool to save this with real academic research findings. Ensure you have at least 10 resources."
    ),
    agent=resource_search_agent,
)

# Task 5: Real-time resource monitoring
realtime_monitoring_task = Task(
    description=(
        f"Based on the project timeline and requirements, continuously monitor for new releases, updates, or trending resources "
        f"related to the project domain.\n\n"
        f"SPECIFIC INSTRUCTIONS:\n"
        f"1. Read the analysis files from '{output_folder}/' to understand monitoring priorities\n"
        f"2. Use SerperDevTool to search for recent developments and trends\n"
        f"3. Focus on AI/ML tools, social media platforms, and marketing technology updates\n"
        f"4. Identify emerging tools and libraries that could benefit the project\n"
        f"5. CRITICAL: You MUST find and document AT LEAST 10 different recent/trending resources\n"
        f"6. Search for: latest AI marketing tools, new social media APIs, emerging marketing technologies, recent platform updates\n"
        f"7. Include sources from: tech blogs, GitHub trending, product hunt, tech news sites, developer blogs\n"
        f"8. Focus on resources published/updated in the last 6 months\n"
        f"9. Use multiple search queries to ensure comprehensive coverage\n\n"
        f"USE FileWriterTool to write this to '{resource_folder}/realtime_updates.md'\n"
    ),
    expected_output=(
        f"A live resource update feed saved as '{resource_folder}/realtime_updates.md' containing:\n"
        "- AT LEAST 10 different recent/trending resources\n"
        "- Change impact analysis\n"
        "- Integration recommendations\n"
        "- Trend analysis and future predictions\n"
        "- Direct links to each resource\n"
        "- Publication/update dates\n\n"
        "Use FileWriterTool to save this with real-time findings. Ensure you have at least 10 resources."
    ),
    agent=resource_search_agent,
)

# Define Coding Agent Tasks (Third Agent)
# Task 1: Project Architecture Design
architecture_design_task = Task(
    description=(
        f"Based on the project analysis files from '{output_folder}/', design the overall system architecture "
        f"for the AI-powered social media marketing platform.\n\n"
        f"SPECIFIC INSTRUCTIONS:\n"
        f"1. Read the analysis files to understand project requirements and technology stack\n"
        f"2. Design a scalable, modular architecture using modern best practices\n"
        f"3. Define clear module boundaries and data flow\n"
        f"4. Create folder structure templates and coding conventions\n"
        f"5. Consider microservices vs monolithic architecture based on project scope\n"
        f"6. Include API design patterns and database schema considerations\n"
        f"7. Address security, scalability, and maintainability concerns\n\n"
        f"USE FileWriterTool to write this to '{code_folder}/architecture_design.md'\n"
        f"Also generate a Python script that creates the basic folder structure."
    ),
    expected_output=(
        f"Complete architecture design saved as '{code_folder}/architecture_design.md' containing:\n"
        "- System architecture diagrams and descriptions\n"
        "- Module boundaries and responsibilities\n"
        "- Technology stack recommendations\n"
        "- Folder structure templates\n"
        "- Coding conventions and standards\n"
        "- Security and scalability considerations\n"
        "- Python script for creating project structure\n\n"
        "Use FileWriterTool to save this with detailed architectural guidance."
    ),
    agent=coding_agent,
)

# Task 2: Starter Template Generation
starter_template_task = Task(
    description=(
        f"Based on the architecture design and project requirements, generate a complete project scaffolding "
        f"with boilerplate code, configuration files, and basic functionality implementations.\n\n"
        f"SPECIFIC INSTRUCTIONS:\n"
        f"1. Read the architecture design and project analysis files\n"
        f"2. Create a fully functional project template with proper structure\n"
        f"3. Include dependency management (requirements.txt, pyproject.toml)\n"
        f"4. Generate basic configuration files (.env.example, config.py)\n"
        f"5. Create starter API endpoints and basic functionality\n"
        f"6. Include database models and connection setup\n"
        f"7. Add authentication and basic security features\n"
        f"8. Create comprehensive setup instructions\n\n"
        f"USE FileWriterTool to write setup instructions to '{code_folder}/setup_instructions.md'\n"
        f"Generate all necessary Python files in the '{code_folder}/project_template/' directory."
    ),
    expected_output=(
        f"Complete project template saved in '{code_folder}/project_template/' containing:\n"
        "- Fully functional project structure\n"
        "- All necessary Python files with basic implementations\n"
        "- Configuration and dependency files\n"
        "- Basic API endpoints and functionality\n"
        "- Database models and setup\n"
        "- Authentication and security features\n"
        "- Comprehensive setup instructions\n\n"
        "Use FileWriterTool to save setup instructions and generate all code files."
    ),
    agent=coding_agent,
)

# Task 3: Custom Function and Component Creation
custom_components_task = Task(
    description=(
        f"Based on the project requirements, generate specific functions, classes, and components "
        f"for the AI-powered social media marketing platform.\n\n"
        f"SPECIFIC INSTRUCTIONS:\n"
        f"1. Read the project analysis to understand specific feature requirements\n"
        f"2. Create core business logic functions for social media management\n"
        f"3. Generate AI content generation and analysis components\n"
        f"4. Build user management and authentication systems\n"
        f"5. Create analytics and reporting modules\n"
        f"6. Include proper error handling, logging, and documentation\n"
        f"7. Add unit tests for critical functions\n"
        f"8. Ensure code follows best practices and is production-ready\n\n"
        f"USE FileWriterTool to write this to '{code_folder}/custom_components.md'\n"
        f"Generate all Python files with well-documented, tested code modules."
    ),
    expected_output=(
        f"Custom components and functions saved in '{code_folder}/components/' containing:\n"
        "- Core business logic functions\n"
        "- AI content generation components\n"
        "- User management systems\n"
        "- Analytics and reporting modules\n"
        "- Comprehensive error handling and logging\n"
        "- Unit tests for critical functions\n"
        "- Usage examples and integration guidelines\n\n"
        "Use FileWriterTool to save documentation and generate all code files."
    ),
    agent=coding_agent,
)

# Task 4: API Integration Code Generation
api_integration_task = Task(
    description=(
        f"Create wrapper functions and integration code for external APIs, databases, and third-party services "
        f"required for the social media marketing platform.\n\n"
        f"SPECIFIC INSTRUCTIONS:\n"
        f"1. Read the project requirements to identify needed integrations\n"
        f"2. Create API clients for social media platforms (Twitter, Facebook, Instagram, LinkedIn)\n"
        f"3. Build database connection and ORM implementations\n"
        f"4. Generate authentication and rate limiting handlers\n"
        f"5. Create webhook handlers for real-time updates\n"
        f"6. Include comprehensive error handling and retry logic\n"
        f"7. Add logging and monitoring capabilities\n"
        f"8. Ensure security best practices for API keys and tokens\n\n"
        f"USE FileWriterTool to write this to '{code_folder}/api_integrations.md'\n"
        f"Generate all Python files with complete API client implementations."
    ),
    expected_output=(
        f"API integration code saved in '{code_folder}/integrations/' containing:\n"
        "- Social media platform API clients\n"
        "- Database connection and ORM implementations\n"
        "- Authentication and rate limiting handlers\n"
        "- Webhook handlers for real-time updates\n"
        "- Comprehensive error handling and retry logic\n"
        "- Logging and monitoring capabilities\n"
        "- Security best practices implementation\n\n"
        "Use FileWriterTool to save documentation and generate all code files."
    ),
    agent=coding_agent,
)

# Task 5: Testing and Validation Code Creation
testing_validation_task = Task(
    description=(
        f"Generate comprehensive unit tests, integration tests, and validation scripts "
        f"to ensure code reliability and performance for the social media marketing platform.\n\n"
        f"SPECIFIC INSTRUCTIONS:\n"
        f"1. Read the generated code components to understand what needs testing\n"
        f"2. Create unit tests for all critical functions and classes\n"
        f"3. Generate integration tests for API endpoints and database operations\n"
        f"4. Build performance testing scripts for load testing\n"
        f"5. Create validation scripts for data integrity and business rules\n"
        f"6. Include test data generators and mock objects\n"
        f"7. Set up automated testing configurations\n"
        f"8. Add coverage reporting and quality metrics\n\n"
        f"USE FileWriterTool to write this to '{code_folder}/testing_framework.md'\n"
        f"Generate all test files with comprehensive test suites."
    ),
    expected_output=(
        f"Testing framework saved in '{code_folder}/tests/' containing:\n"
        "- Unit tests for all critical functions\n"
        "- Integration tests for APIs and databases\n"
        "- Performance testing scripts\n"
        "- Data validation scripts\n"
        "- Test data generators and mocks\n"
        "- Automated testing configurations\n"
        "- Coverage reporting setup\n\n"
        "Use FileWriterTool to save documentation and generate all test files."
    ),
    agent=coding_agent,
)

# Build the Crew with both agents and all tasks
crew = Crew(
    agents=[project_analyst, resource_search_agent, coding_agent],
    tasks=[
        # First agent tasks (project analysis)
        project_context_task,
        objective_task,
        technical_task,
        resource_task,
        # Second agent tasks (resource search)
        multi_platform_discovery_task,
        code_repository_analysis_task,
        dataset_discovery_task,
        academic_paper_task,
        realtime_monitoring_task,
        # Third agent tasks (coding and development)
        architecture_design_task,
        starter_template_task,
        custom_components_task,
        api_integration_task,
        testing_validation_task,
    ],
    process=Process.sequential,
)

# Run the analysis
print("Starting comprehensive project analysis, resource discovery, and code generation...")
print(f"Project analysis files will be saved to: {output_folder}")
print(f"Resource discovery files will be saved to: {resource_folder}")
print(f"Generated code and documentation will be saved to: {code_folder}")
result = crew.kickoff()
print("\n" + "=" * 50)
print("ANALYSIS, RESOURCE DISCOVERY, AND CODE GENERATION COMPLETE!")
print("=" * 50)
print(f"Project analysis files saved to: {output_folder}")
print(f"Resource discovery files saved to: {resource_folder}")
print(f"Generated code and documentation saved to: {code_folder}")
print(result)
