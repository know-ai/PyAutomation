# Communications Module (OPC UA Clients)

<div align="center" style="background: linear-gradient(135deg, #f3e5f5 0%, #e1bee7 100%); border-radius: 15px; padding: 3em 2em; margin: 2em 0; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">

<h2 style="color: #4a148c; font-size: 2.5em; margin-bottom: 0.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.1); font-weight: 700;">
  🔌 Connect to Industrial Systems
</h2>

<p style="color: #38006b; font-size: 1.4em; margin-top: 1em; font-weight: 500;">
  The <strong>Communications Module</strong> focuses on the configuration and management of <strong>OPC UA Clients</strong> that connect to external OPC UA servers. OPC UA (Open Platform Communications Unified Architecture) is the industry standard for secure and reliable data exchange in industrial automation.
</p>

<p style="color: #38006b; font-size: 1.2em; margin-top: 1em; font-weight: 500;">
  This module allows PyAutomation to act as an OPC UA client, connecting to remote OPC UA servers to browse their address spaces, select variables, and monitor real-time data from industrial equipment, SCADA systems, and other automation devices.
</p>

</div>

## Overview

<div style="background: #f8f9fa; border-left: 5px solid #9c27b0; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
The OPC UA Clients interface is divided into two main sections:
</p>

<ol style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Client Configuration and Tag Monitoring</strong>: Manage OPC UA client connections and view monitored tags</li>
<li><strong>OPC UA Explorer</strong>: Browse the address space of connected OPC UA servers</li>
</ol>

</div>

![OPC UA Clients Interface](../images/OPCUAClientScreen.png)

---

## Creating an OPC UA Client

<div style="background: #f3e5f5; border-radius: 8px; padding: 1.5em; margin: 2em 0; border: 2px solid #9c27b0;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0; font-weight: 500;">
To establish a connection to an external OPC UA server, you need to create a new client configuration.
</p>

</div>

### 1. Access the Client Configuration

Navigate to **Communications** → **OPC UA Clients** from the main menu. The client configuration section is located at the top of the interface.

![Client Configuration Section](../images/OPCUAClientsConnections.png)

### 2. Configure Client Parameters

<div style="background: #f3e5f5; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #9c27b0;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
In the <strong>Selected client</strong> section, provide the following information:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Name</strong>: A descriptive name for the client connection (e.g., "Simulator", "PLC_Production_Line_1")</li>
<li><strong>Server Address</strong>: The IP address or hostname of the OPC UA server (e.g., <code>192.168.1.108</code>, <code>127.0.0.1</code>)</li>
<li><strong>Port</strong>: The network port where the OPC UA server is listening (default: <code>4840</code>)</li>
</ul>

</div>

### 3. Create the Client

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<ol style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Fill in the Name, Server Address, and Port fields with valid values</li>
<li>Click the <strong>Create</strong> button (blue button) to establish the client connection</li>
<li>The client will appear in the dropdown menu under <strong>Selected client</strong></li>
</ol>

</div>

### 4. Select Existing Client

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
To work with an existing client:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Click on the <strong>Selected client</strong> dropdown</li>
<li>Choose the desired client from the list</li>
<li>The client's configuration will be loaded and displayed in the input fields</li>
</ul>

</div>

### 5. Remove a Client

<div style="background: #ffebee; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #f44336;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
To delete a client configuration:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Select the client from the dropdown</li>
<li>Click the <strong>Remove</strong> button (red button)</li>
<li>Confirm the removal when prompted</li>
</ul>

</div>

---

## Exploring OPC UA Server Address Space

<div style="background: #f8f9fa; border-left: 5px solid #9c27b0; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0; font-weight: 500;">
The <strong>OPC UA Explorer</strong> section allows you to browse the complete address space of the connected OPC UA server, including all objects, variables, and their hierarchical structure.
</p>

</div>

### Accessing the Explorer

Once a client is selected and connected, the OPC UA Explorer will display the server's address space in a tree structure below the client configuration area.

![OPC UA Explorer](../images/OPCUAExplorer.png)

### Navigating the Tree

<div style="background: #f3e5f5; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #9c27b0;">

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Expand/Collapse Nodes</strong>: Click on folder icons or expand arrows to navigate through the hierarchical structure</li>
<li><strong>Node Information</strong>: Each node displays:
    <ul style="margin-top: 0.5em; margin-bottom: 0.5em;">
    <li>A checkbox for selection</li>
    <li>An icon indicating the node type (variables typically show colored circles)</li>
    <li>The Display Name of the node</li>
    <li>The Node ID in the format <code>ns=&lt;namespace&gt;;i=&lt;identifier&gt;</code> (e.g., <code>ns=2;i=2</code>)</li>
    </ul>
</li>
</ul>

</div>

### Selecting Variables for Monitoring

#### Single Selection

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
To select a single variable:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Click on the checkbox next to the variable name</li>
<li>The selected variable will be highlighted</li>
</ul>

</div>

#### Multiple Selection

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
To select multiple variables:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Hold <strong>Ctrl</strong> (or <strong>Cmd</strong> on Mac) and click on the checkboxes of the variables you want to monitor</li>
<li>Selected variables will be highlighted with a different background color</li>
<li>The selection count is displayed next to the "Clear selection" button</li>
</ul>

</div>

![Multiple Selection](../images/OPCUAExplorerMultiSelection.png)

#### Clear Selection

<div style="background: #fff3e0; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #ff9800;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
To deselect all selected variables:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Click the <strong>Clear selection</strong> button (showing the count of selected items)</li>
<li>All checkboxes will be unchecked</li>
</ul>

</div>

---

## Monitoring Selected Tags

<div style="background: #f8f9fa; border-left: 5px solid #9c27b0; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0; font-weight: 500;">
Once you have selected variables from the OPC UA Explorer, they appear in the <strong>Selected tags</strong> section for real-time monitoring.
</p>

</div>

### Adding Tags to Monitor

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Method 1: Drag and Drop</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1.5em 0; padding-left: 1.5em; font-weight: 400;">
<li>Drag nodes from the OPC UA Explorer tree to the Selected tags area</li>
<li>Dropped variables will automatically appear in the monitoring table</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Method 2: Checkbox Selection</strong> (if implemented)
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Check variables in the explorer and use an "Add to Monitor" action</li>
</ul>

</div>

### Tag Monitoring Table

<div style="background: #f3e5f5; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #9c27b0;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
The Selected tags table displays the following information for each monitored tag:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Namespace</strong>: The Node ID namespace and identifier (e.g., <code>ns=2;i=2</code>)</li>
<li><strong>Display Name</strong>: The friendly name of the variable (e.g., <code>FI_01</code>, <code>PI_01</code>)</li>
<li><strong>Value</strong>: The current value of the variable (updated in real-time)</li>
<li><strong>Timestamp</strong>: The last update time in format <code>DD/MM/YYYY, HH:MM:SS</code></li>
<li><strong>Status</strong>:
    <ul style="margin-top: 0.5em; margin-bottom: 0.5em;">
    <li>Green "Good" indicator when the connection and value are valid</li>
    <li>Error indicators if the connection fails or value is invalid</li>
    </ul>
</li>
<li><strong>Actions</strong>: Red "Remove" button to stop monitoring a specific tag</li>
</ul>

</div>

### Polling Configuration

<div style="background: #e1f5fe; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #03a9f4;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
Below the tag monitoring table, you can configure the polling frequency:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Polling every Xs</strong>: Check this option and adjust the interval (default: 1 second)</li>
<li>When enabled, the client will periodically read values from the OPC UA server at the specified interval</li>
<li>Uncheck to disable automatic polling</li>
</ul>

</div>

### Clearing Monitored Tags

<div style="background: #ffebee; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #f44336;">

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Click the <strong>Clear</strong> button (red button) to remove all tags from the monitoring table</li>
<li>This action stops monitoring all currently selected tags but does not disconnect the client</li>
</ul>

</div>

---

## Best Practices

<div style="background: #f8f9fa; border-left: 5px solid #9c27b0; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Connection Management</strong>: Ensure the OPC UA server is accessible on the network before creating a client</li>
<li><strong>Network Configuration</strong>: Verify firewall settings allow connections on the specified port</li>
<li><strong>Tag Selection</strong>: Select only the tags you need to monitor to optimize performance and network bandwidth</li>
<li><strong>Polling Frequency</strong>: Adjust polling intervals based on your data update requirements and network capacity</li>
<li><strong>Naming Conventions</strong>: Use descriptive names for clients to easily identify different server connections</li>
</ul>

</div>

---

## Security Notes

<div style="background: #fff3e0; border-left: 5px solid #ff9800; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; font-weight: 500;">
<strong>Note</strong>: Currently, OPC UA client connections do not support security policies and authentication. All connections are established in unsecured mode. Security features will be available in future releases.
</p>

</div>
