## Agent Portability Pipeline

Conceptually, Charm’s portability pipeline looks like this:

SDK  
→ Source Agent Input  
→ **Parser** → UAC  
→ **Renderer** → Target Profile  
→ **Loader** → Runnable StateGraph  

The pipeline is designed to support multiple source/target frameworks.

## Route
### 1st Reference Route
For v0.1.0, we are focusing on a single reference route: CrewAI → LangGraph

Therefore, the current pipeline is as follows:

CrewAI → (Parser) → UAC → (Renderer) → LangGraph Profile  
→ (Loader) → runnable LangGraph StateGraph

This is the first end-to-end route we will implement.  
Additional routes (other sources and targets) will be added incrementally once this path is stable.
