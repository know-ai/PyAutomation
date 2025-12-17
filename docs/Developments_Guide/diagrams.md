# Creating Diagrams with Mermaid

<div align="center" style="background: linear-gradient(135deg, #e1f5fe 0%, #b3e5fc 100%); border-radius: 15px; padding: 3em 2em; margin: 2em 0; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">

<h2 style="color: #01579b; font-size: 2.5em; margin-bottom: 0.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.1); font-weight: 700;">
  📊 Visual Documentation Made Easy
</h2>

<p style="color: #003d5c; font-size: 1.4em; margin-top: 1em; font-weight: 500;">
  PyAutomation documentation supports <strong>Mermaid diagrams</strong>, which allow you to create professional diagrams using simple text-based syntax. No screenshots or external image editors needed!
</p>

</div>

## Supported Diagram Types

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 2em 0; border: 2px solid #2196f3;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
Mermaid supports many diagram types that are useful for technical documentation:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Flowcharts</strong>: Process flows, decision trees</li>
<li><strong>Sequence Diagrams</strong>: Interactions between components over time</li>
<li><strong>State Diagrams</strong>: State machine visualizations</li>
<li><strong>Class Diagrams</strong>: Object-oriented relationships</li>
<li><strong>Entity Relationship Diagrams</strong>: Database schemas</li>
<li><strong>Gantt Charts</strong>: Project timelines</li>
<li><strong>Git Graphs</strong>: Version control history</li>
</ul>

</div>

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

---

## Best Practices

<div style="background: #f8f9fa; border-left: 5px solid #03a9f4; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<ol style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Keep diagrams simple</strong>: Focus on the key concepts, avoid clutter</li>
<li><strong>Use descriptive labels</strong>: Make node and edge labels clear and meaningful</li>
<li><strong>Maintain consistency</strong>: Use similar styles across related diagrams</li>
<li><strong>Test locally</strong>: Use <code>mkdocs serve</code> to preview diagrams before committing</li>
<li><strong>Version control friendly</strong>: Mermaid diagrams are text-based, so they work great with Git</li>
</ol>

</div>

## Resources

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 2em 0; border: 2px solid #4caf50;">

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><a href="https://mermaid.live/" style="color: #2e7d32; font-weight: 600;">Mermaid Live Editor</a>: Online tool to create and test diagrams</li>
<li><a href="https://mermaid.js.org/" style="color: #2e7d32; font-weight: 600;">Mermaid Documentation</a>: Complete syntax reference</li>
<li><a href="https://mermaid.js.org/ecosystem/tutorials.html" style="color: #2e7d32; font-weight: 600;">Mermaid Examples</a>: Tutorials and examples</li>
</ul>

</div>

---

## Tips

<div style="background: #fff3e0; border-radius: 8px; padding: 1.5em; margin: 2em 0; border: 2px solid #ff9800;">

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Use <code>flowchart</code> for modern flowcharts (recommended over <code>graph</code>)</li>
<li>Use <code>stateDiagram-v2</code> for state machines (more features than v1)</li>
<li>Add <code>note</code> annotations to explain complex transitions</li>
<li>Use <code>subgraph</code> to group related components</li>
<li>Use different arrow styles (<code>--&gt;</code>, <code>--&gt;&gt;</code>, <code>-.&gt;</code>) to show different types of relationships</li>
</ul>

</div>

