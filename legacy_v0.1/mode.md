Charm supports two execution modes to accommodate different developer needs when working across multiple agent frameworks.

### Migration Mode
Migration Mode compiles an agent from the source framework into a fully native workflow on the target framework. Charm standardizes and transforms the agent’s definitions, configuration, and execution graph into the target framework’s schema so the entire flow can run directly in that environment. Developers can immediately continue development on the target side and use its native tools, execution engine, and ecosystem— without rewriting their original agent logic.

### Extension Mode
In Extension Mode, Charm does not migrate or rewrite the agent’s workflow into the target framework. Instead, Charm synchronizes the agent’s definition and execution state across frameworks, and inserts a bridge node on the target framework that serves as the entry point for extension. Developers can build new workflows, tools, or nodes natively in the target framework and stitch them back into the original flow. Charm ensures that context, state, and definitions remain consistent, allowing the combined flow to run as a single continuous multi-framework execution chain.
