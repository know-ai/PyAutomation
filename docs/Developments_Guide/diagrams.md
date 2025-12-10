# Creating Diagrams with Mermaid

PyAutomation documentation supports **Mermaid diagrams**, which allow you to create professional diagrams using simple text-based syntax. No screenshots or external image editors needed!

## Supported Diagram Types

Mermaid supports many diagram types that are useful for technical documentation:

- **Flowcharts**: Process flows, decision trees
- **Sequence Diagrams**: Interactions between components over time
- **State Diagrams**: State machine visualizations
- **Class Diagrams**: Object-oriented relationships
- **Entity Relationship Diagrams**: Database schemas
- **Gantt Charts**: Project timelines
- **Git Graphs**: Version control history

## Basic Syntax

To add a Mermaid diagram to any Markdown file, use a code block with the `mermaid` language identifier:

````markdown
``` mermaid
graph TD
    A[Start] --> B{Decision}
    B -->|Yes| C[Action 1]
    B -->|No| D[Action 2]
    C --> E[End]
    D --> E
```
````

## Common Examples

### Flowchart

``` mermaid
flowchart LR
    A[Input] -->|Process| B[Output]
    B --> C{Check}
    C -->|Pass| D[Success]
    C -->|Fail| E[Error]
```

**Code:**
````markdown
``` mermaid
flowchart LR
    A[Input] -->|Process| B[Output]
    B --> C{Check}
    C -->|Pass| D[Success]
    C -->|Fail| E[Error]
```
````

### Sequence Diagram

``` mermaid
sequenceDiagram
    participant A as Client
    participant B as Server
    participant C as Database
    
    A->>B: Request
    B->>C: Query
    C-->>B: Response
    B-->>A: Result
```

**Code:**
````markdown
``` mermaid
sequenceDiagram
    participant A as Client
    participant B as Server
    participant C as Database
    
    A->>B: Request
    B->>C: Query
    C-->>B: Response
    B-->>A: Result
```
````

### State Diagram

``` mermaid
stateDiagram-v2
    [*] --> State1
    State1 --> State2: Transition
    State2 --> [*]
```

**Code:**
````markdown
``` mermaid
stateDiagram-v2
    [*] --> State1
    State1 --> State2: Transition
    State2 --> [*]
```
````

### Graph with Subgraphs

``` mermaid
graph TB
    subgraph "System A"
        A1[Component 1]
        A2[Component 2]
    end
    
    subgraph "System B"
        B1[Component 3]
    end
    
    A1 --> B1
    A2 --> B1
```

**Code:**
````markdown
``` mermaid
graph TB
    subgraph "System A"
        A1[Component 1]
        A2[Component 2]
    end
    
    subgraph "System B"
        B1[Component 3]
    end
    
    A1 --> B1
    A2 --> B1
```
````

## Best Practices

1. **Keep diagrams simple**: Focus on the key concepts, avoid clutter
2. **Use descriptive labels**: Make node and edge labels clear and meaningful
3. **Maintain consistency**: Use similar styles across related diagrams
4. **Test locally**: Use `mkdocs serve` to preview diagrams before committing
5. **Version control friendly**: Mermaid diagrams are text-based, so they work great with Git

## Resources

- [Mermaid Live Editor](https://mermaid.live/): Online tool to create and test diagrams
- [Mermaid Documentation](https://mermaid.js.org/): Complete syntax reference
- [Mermaid Examples](https://mermaid.js.org/ecosystem/tutorials.html): Tutorials and examples

## Tips

- Use `flowchart` for modern flowcharts (recommended over `graph`)
- Use `stateDiagram-v2` for state machines (more features than v1)
- Add `note` annotations to explain complex transitions
- Use `subgraph` to group related components
- Use different arrow styles (`-->`, `-->>`, `-.->`) to show different types of relationships

