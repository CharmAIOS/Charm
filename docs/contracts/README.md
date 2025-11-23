## Basic Concepts
Charm adopts a Contract-First Architecture, meaning the system is structured around a set of stable, versioned, and framework-agnostic contracts.

A contract in Charm is not a data model, class, or internal struct. It is a formal interoperability specification that defines:
- what information must be preserved,
- how agent definitions can be represented neutrally,
- and how different runtimes can exchange tasks, states, errors, and metadata.

Charm Contracts define neutral agent representations, envelopes, mapping rules, and error semantics, ensuring that Charm can bridge heterogeneous ecosystems.

### Only the Unified Agent Contract is active in v0.1.0
