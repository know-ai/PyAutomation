Alarm
===================

.. raw:: html
    <div style="text-align: justify;">

    The following diagram illustrates the various states of an alarm system and the transitions between these states.

    <li>Normal State (A): The system is in a normal operating condition with no active alarms. </li>
    <li>Unacknowledged Alarm (B): An abnormal condition has been detected, and the alarm is active but has not yet been acknowledged by an operator.</li>
    <li>Acknowledged Alarm (C): The abnormal condition persists, but the alarm has been acknowledged.</li>
    <li>RTN (Return to Normal) Unacknowledged (D): The system has returned to a normal state, but the previous alarm has not yet been acknowledged.</li>
    <li>Shelved (E): The alarm has been temporarily disabled by an operator.</li>
    <li>Suppressed by Design (F): The alarm is intentionally suppressed as part of the design of the system.</li>
    <li>Out of Service (G): The alarm is deactivated, typically for maintenance or service purposes.</li>

    Each transition between states is triggered by specific conditions, such as acknowledging the alarm, the system returning to normal, or reactivating a shelved or suppressed alarm. Understanding this flow helps ensure that alarms are appropriately managed and that abnormal conditions are properly acknowledged and resolved, in accordance with the ANSI/ISA-182 standard.
    </div>

.. graphviz::
    
   digraph AlarmStates {
       node [shape=circle, style=filled, color=lightblue2, fontname="Arial", fontsize=12];  // Estilo general de los nodos
       edge [fontname="Arial", fontsize=12, color=black];  // Estilo general de los bordes

       A [label="A\nNormal\nProcess: Normal\nAlarm: Not Active\nAck: Acknowledged"];
       B [label="B\nUnacknowledged alarm\nProcess: Abnormal\nAlarm: Active\nAck: Unacknowledged"];
       C [label="C\nAcknowledged alarm\nProcess: Abnormal\nAlarm: Active\nAck: Acknowledged"];
       D [label="D\nRTN unacknowledged\nProcess: Normal\nAlarm: Not Active\nAck: Unacknowledged"];
       E [label="E\nShelved\nProcess: N/A\nAlarm: N/A\nAck: N/A"];
       F [label="F\nSuppressed by design\nProcess: N/A\nAlarm: N/A\nAck: N/A"];
       G [label="G\nOut of service\nProcess: N/A\nAlarm: N/A\nAck: N/A"];

       // Transitions
       A -> B [label="Abnormal condition", color="red", style="dashed"];
       B -> C [label="Acknowledge", color="green"];
       B -> D [label="Return to normal condition", color="green"];
       C -> A [label="Return to normal condition", color="blue"];
       C -> B [label="Re-alarm", color="red", style="dotted"];
       D -> A [label="Acknowledge", color="blue"];

       // Additional states
       A -> E [label="Shelve", color="orange"];
       B -> E [label="Shelve", color="orange"];
       C -> E [label="Shelve", color="orange"];
       D -> E [label="Shelve", color="orange"];
       E -> A [label="Un-shelve", color="orange"];
       E -> B [label="Un-shelve", color="orange"];
       A -> F [label="Designed suppression", color="gray"];
       B -> F [label="Designed suppression", color="gray"];
       C -> F [label="Designed suppression", color="gray"];
       D -> F [label="Designed suppression", color="gray"];
       F -> A [label="Designed un-suppression", color="gray"];
       F -> B [label="Designed un-suppression", color="gray"];
       A -> G [label="Remove from service", color="brown"];
       B -> G [label="Remove from service", color="brown"];
       C -> G [label="Remove from service", color="brown"];
       D -> G [label="Remove from service", color="brown"];
       G -> A [label="Return to service", color="brown"];
       G -> B [label="Return to service", color="brown"];

   }


