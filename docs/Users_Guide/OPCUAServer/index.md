# OPC UA Server Module

<div align="center" style="background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%); border-radius: 15px; padding: 3em 2em; margin: 2em 0; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">

<h2 style="color: #e65100; font-size: 2.5em; margin-bottom: 0.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.1);">
  🌐 Expose Your Data
</h2>

<p style="color: #d84315; font-size: 1.4em; margin-top: 1em; font-weight: 300;">
  The <strong>OPC UA Server Module</strong> manages PyAutomation's embedded OPC UA Server, which exposes your automation data (tags, alarms, and state machines) to external OPC UA clients such as SCADA systems, HMIs, and other industrial automation applications.
</p>

</div>

## What is an OPC UA Server?

An **OPC UA Server** in PyAutomation is an embedded server that makes your process data available to external systems through the OPC UA (Open Platform Communications Unified Architecture) protocol. This enables seamless integration with third-party applications that need to read tag values, monitor alarm states, or access machine information.

### Key Features

*   **Embedded Server**: Runs as a state machine within PyAutomation, automatically updating exposed data
*   **Three Main Folders**: Organizes data into CVT (Current Value Table), Alarms, and Engines (State Machines)
*   **Real-Time Updates**: Continuously publishes current values, alarm states, and machine statuses
*   **Access Control**: Configure read/write permissions for each exposed variable
*   **Standard Protocol**: Uses industry-standard OPC UA for maximum compatibility

## Module Overview

The OPC UA Server Module provides a user interface to:

*   View all exposed variables and their current values
*   Configure access permissions (Read, Write, ReadWrite) for each variable
*   Monitor server status and connection information
*   Manage the server's address space structure

<!-- TODO: Add image OPCUAServer_Dashboard.png - Screenshot of the OPC UA Server dashboard showing the list of exposed attributes -->

## Understanding the Address Space

PyAutomation's OPC UA Server organizes data into three main folders:

### CVT Folder

Contains all tags from the Current Value Table (CVT), representing process variables, sensor readings, and control parameters.

*   **Structure**: Each tag is exposed as a variable node
*   **Updates**: Values update in real-time as tags change
*   **Namespace Format**: Tags are organized by their namespace identifiers

<!-- TODO: Add image OPCUAServer_CVTFolder.png - Screenshot showing the CVT folder structure in an OPC UA client browser -->

### Alarms Folder

Contains all active alarms and their current states.

*   **Structure**: Each alarm is exposed as a variable node
*   **Updates**: Alarm states update automatically when alarms transition
*   **Information**: Includes alarm name, state, and associated tag information

<!-- TODO: Add image OPCUAServer_AlarmsFolder.png - Screenshot showing the Alarms folder structure -->

### Engines Folder

Contains all state machines (engines) running in the system.

*   **Structure**: Each machine is exposed with its current state
*   **Updates**: Machine states update as state transitions occur
*   **Information**: Includes machine name, current state, and execution interval

<!-- TODO: Add image OPCUAServer_EnginesFolder.png - Screenshot showing the Engines folder structure -->

## Accessing the OPC UA Server Module

1. Navigate to **OPC UA Server** from the main menu
2. The dashboard displays all exposed attributes in a paginated table
3. Each row shows an attribute's namespace, name, current value, and access type

<!-- TODO: Add image OPCUAServer_EmptyState.png - Screenshot of the OPC UA Server page when no attributes are exposed yet -->

## Viewing Exposed Attributes

The main table displays all variables exposed by the OPC UA Server:

### Table Columns

*   **Namespace**: The OPC UA Node ID in format `ns=<namespace>;i=<identifier>` or `ns=<namespace>;s=<string>`
*   **Name**: The display name of the variable (tag name, alarm name, or machine name)
*   **Value**: The current value of the variable (updated in real-time)
*   **Access Type**: Current permission level (Read, Write, or ReadWrite)
*   **Actions**: Dropdown menu to change the access type

<!-- TODO: Add image OPCUAServer_AttributesTable.png - Screenshot of the attributes table with multiple entries showing namespace, name, value, and access type -->

## Configuring Access Types

Access types determine what operations external OPC UA clients can perform on each variable:

### Read

*   **Permission**: External clients can only read the variable value
*   **Use Case**: For tags and alarms that should be monitored but not modified externally
*   **Security**: Prevents accidental or unauthorized changes to process variables

### Write

*   **Permission**: External clients can only write to the variable (typically not used for tags)
*   **Use Case**: For control parameters that external systems need to set
*   **Note**: Write-only access is rarely used in practice

### ReadWrite

*   **Permission**: External clients can both read and write the variable
*   **Use Case**: For setpoints, control parameters, or configuration values that external systems need to read and modify
*   **Security Consideration**: Use with caution; ensure proper access control in external systems

### Changing Access Type

To modify the access type for a variable:

1. Locate the variable in the attributes table
2. Click on the **Access Type** dropdown in the Actions column
3. Select the desired access type (Read, Write, or ReadWrite)
4. A confirmation dialog will appear showing:
   *   Variable name
   *   Current access type
   *   New access type
5. Click **Confirm** to apply the change
6. The change takes effect immediately

<!-- TODO: Add image OPCUAServer_AccessTypeDropdown.png - Screenshot showing the access type dropdown menu opened -->
<!-- TODO: Add image OPCUAServer_AccessTypeChangeConfirmation.png - Screenshot of the confirmation dialog when changing access type -->
<!-- TODO: Add image OPCUAServer_AccessTypeUpdated.png - Screenshot showing the updated access type in the table -->

## Server Configuration

### Endpoint Information

The OPC UA Server runs on a configurable endpoint:

*   **Default Endpoint**: `opc.tcp://0.0.0.0:53530/OPCUAServer/`
*   **Port**: Configurable via environment variable `OPCUA_SERVER_PORT` (default: 53530)
*   **Network Interface**: `0.0.0.0` means the server listens on all network interfaces

### Connecting External Clients

To connect an external OPC UA client to PyAutomation's server:

1. **Obtain Server Address**: Use the IP address or hostname of the machine running PyAutomation
2. **Use Correct Port**: Ensure the port matches your configuration (default: 53530)
3. **Endpoint URL**: Use format `opc.tcp://<server_address>:<port>/OPCUAServer/`
4. **Example**: `opc.tcp://192.168.1.100:53530/OPCUAServer/`

<!-- TODO: Add image OPCUAServer_EndpointConfiguration.png - Screenshot showing server endpoint information or configuration -->

## Pagination

When many attributes are exposed, the table uses pagination:

*   **Items Per Page**: 10 attributes per page (default)
*   **Navigation**: Use Previous/Next buttons or page numbers to navigate
*   **Current Page Indicator**: Shows current page and total pages

<!-- TODO: Add image OPCUAServer_Pagination.png - Screenshot showing pagination controls -->

## Real-Time Updates

The OPC UA Server continuously updates exposed values:

*   **Tag Values**: Update as tags receive new data from OPC UA clients or internal processes
*   **Alarm States**: Update when alarms transition between states
*   **Machine States**: Update when state machines change states
*   **Update Frequency**: Matches the execution interval of the OPCUAServer state machine

## Best Practices

### Access Type Configuration

*   **Default to Read**: Most tags and alarms should be Read-only to prevent unauthorized modifications
*   **Use ReadWrite Sparingly**: Only enable ReadWrite for variables that external systems legitimately need to modify
*   **Document Changes**: Keep records of access type changes for audit purposes
*   **Review Regularly**: Periodically review access types to ensure they match current requirements

### Security Considerations

*   **Network Security**: Ensure the OPC UA Server port is protected by firewall rules
*   **Access Control**: Use Read-only access for most variables to prevent unauthorized changes
*   **Monitoring**: Monitor access type changes through the Events module
*   **Documentation**: Document which external systems require write access and why

### Performance

*   **Limit Exposed Variables**: Only expose variables that external systems actually need
*   **Update Frequency**: The server updates at its configured interval; adjust if needed
*   **Network Bandwidth**: Consider network capacity when exposing many variables

## Troubleshooting

### External Client Cannot Connect

If an external OPC UA client cannot connect to the server:

*   **Verify Server Status**: Check that the OPCUAServer state machine is running
*   **Check Network**: Ensure the server machine is accessible on the network
*   **Verify Port**: Confirm the port number matches your configuration
*   **Firewall**: Check that firewall rules allow connections on the OPC UA port
*   **Endpoint URL**: Verify the endpoint URL format is correct

### Values Not Updating

If exposed values are not updating:

*   **Check State Machine**: Verify the OPCUAServer state machine is in "Running" state
*   **Verify Source Data**: Ensure tags/alarms/machines are active and updating
*   **Check Interval**: Review the OPCUAServer execution interval in the Machines module

### Access Type Changes Not Applied

If access type changes don't take effect:

*   **Refresh Page**: Reload the OPC UA Server page
*   **Check Permissions**: Verify you have permission to modify server configuration
*   **Review Events**: Check the Events module for error messages

## Integration with Other Modules

The OPC UA Server integrates with:

*   **Tags Module**: Exposes all CVT tags to external clients
*   **Alarms Module**: Exposes alarm states and information
*   **Machines Module**: The OPCUAServer itself is a state machine that can be monitored
*   **Events Module**: Access type changes are logged as events

## Getting Started

To begin using the OPC UA Server:

1.   **Verify Server Status**: 
     *   Navigate to the **Machines** module
     *   Confirm the "OPCUAServer" machine is in "Running" state

2.   **Access the Module**: 
     *   Navigate to **OPC UA Server** from the main menu
     *   Review the list of exposed attributes

3.   **Configure Access Types**: 
     *   Review each attribute's access type
     *   Modify access types as needed for your integration requirements

4.   **Connect External Clients**: 
     *   Use the endpoint URL to connect external OPC UA clients
     *   Browse the CVT, Alarms, and Engines folders
     *   Subscribe to or read variables as needed

5.   **Monitor and Maintain**: 
     *   Regularly review exposed attributes
     *   Monitor access type changes through Events
     *   Ensure server remains in Running state

