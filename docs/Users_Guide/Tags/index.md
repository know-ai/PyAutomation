# Tags Module

The **Tags Module** is the foundational component of PyAutomation, serving as the central hub for defining, managing, and monitoring process variables. A **Tag** is a digital representation that connects real-world physical measurements, control outputs, or calculated values to the automation system, enabling data acquisition, processing, storage, and visualization.

## What is a Tag?

A Tag in PyAutomation is a named entity that represents:

*   **Physical Inputs**: Sensor readings from the field (temperature, pressure, flow rate, level, etc.)
*   **Physical Outputs**: Control signals sent to actuators (valves, pumps, motors, etc.)
*   **Calculated Values**: Derived measurements or internal process variables
*   **Status Indicators**: Boolean states representing equipment or process conditions

Each tag contains metadata including its data type, engineering units, source location (OPC UA node), sampling rate, and filtering options. This metadata enables PyAutomation to correctly interpret, process, and display the data throughout the system.

## Why Tags are Essential

Tags are the fundamental building blocks that enable:

*   **Data Acquisition**: Real-time reading of values from OPC UA servers and other data sources
*   **Data Logging**: Historical storage of tag values in the database for analysis and reporting
*   **Alarm Management**: Definition of alarm conditions based on tag values and thresholds
*   **Visualization**: Display of current values, trends, and dashboards in the user interface
*   **Process Control**: Execution of control logic based on tag states and values
*   **Integration**: Seamless data exchange between the DAQ layer, database, UI, and external systems

## Module Overview

The Tags Module interface consists of a comprehensive management dashboard where you can view, create, modify, and delete tags. The interface provides real-time visibility into tag values, their sources, and configuration parameters.

![Tags Dashboard - Empty State](../images/TagsDefinitionEmptyPage.png)

When you first access the Tags Module, you'll see an empty state indicating no tags have been created yet. This is the starting point for building your tag database.

![Tags Dashboard with Tags Created](../images/TagsCreated.png)

Once tags are created, the dashboard displays them in a comprehensive table showing all relevant information including current values, units, OPC UA connections, and configuration parameters.

## Key Features

### Tag Management

*   **Create Tags**: Define new tags with comprehensive configuration options including name, variable type, units, data type, and OPC UA mapping
*   **Update Tags**: Modify tag properties directly from the dashboard using inline editing or edit dialogs
*   **Delete Tags**: Remove tags that are no longer needed from the system
*   **Export Tags**: Export the tag list to CSV format for documentation, backup, or external analysis

### Variable Types and Engineering Units

*   **Variable Types**: Support for various physical phenomena including:
    *   Mass Flow (e.g., kg/sec, kg/min, lb/min)
    *   Pressure (e.g., psi, bar, Pa, kPa)
    *   Temperature (e.g., °C, °F, K)
    *   Density (e.g., kg/m³, lb/ft³)
    *   Level, Volume, Velocity, and more
*   **Unit Conversion**: Automatic handling of engineering unit conversions and display formatting

### Data Type Support

Tags support multiple data types to match the nature of the data source:

*   **Float**: Floating-point numbers for continuous analog measurements (e.g., 29.008, 838.696)
*   **Integer**: Whole numbers for discrete counts or digital values
*   **Boolean**: True/false states for digital inputs, alarms, or status indicators
*   **String**: Text values for descriptive information or alphanumeric identifiers

### OPC UA Integration

*   **Client Selection**: Associate tags with specific OPC UA client connections
*   **Node Mapping**: Map tags directly to OPC UA nodes using namespace identifiers (e.g., `ns=2;i=2`)
*   **Automatic Discovery**: Browse and select OPC UA nodes from connected servers
*   **Real-time Updates**: Continuous synchronization of tag values from OPC UA sources

### Polling and Performance Optimization

*   **Scan Time Configuration**: Define the frequency at which each tag is read from its source (in milliseconds)
*   **Dead Band Filtering**: Configure threshold values to reduce database writes and network traffic by ignoring insignificant changes
*   **Process Filters**: Apply filtering algorithms to smooth data (Process Filter, Gaussian Filter)
*   **Data Quality Detection**: Enable detection of outliers, out-of-range values, and frozen data conditions

### Trending and Visualization

*   **Real-time Trends**: Visualize tag behavior over time with interactive graphs
*   **Historical Analysis**: Access historical data stored in the database for any tag
*   **Multi-tag Comparison**: Display multiple tags on the same graph for correlation analysis
*   **Time Range Selection**: View trends for different time periods (last hour, last 24 hours, custom ranges)

![Trends Interface](../images/TrendsLastHour.png)

## Tags Dashboard Interface

The Tags Dashboard provides a comprehensive view of all configured tags with the following information:

### Table Columns

*   **Name**: The unique identifier of the tag (e.g., `FI_01`, `PI_02`, `TI_01`)
*   **Variable**: The type of physical phenomenon represented (e.g., MassFlow, Pressure, Temperature)
*   **Value**: The current real-time value of the tag
*   **Display Unit**: The engineering unit in which the value is displayed (e.g., kg/sec, psi, °C)
*   **OPC UA Address**: The OPC UA client connection identifier (e.g., "Simulator")
*   **Node Namespace**: The OPC UA node identifier (e.g., `FI_02`, `ns=2;i=2`)
*   **Scan Time (ms)**: The polling interval configured for this tag
*   **Dead Band**: The threshold value that must be exceeded before a new value is logged
*   **Actions**: Edit (pencil icon) and Delete (trash icon) buttons for each tag

### Dashboard Actions

*   **Create Tag** (Green button with plus icon): Opens the tag creation dialog to define a new tag
*   **Export CSV**: Exports the current tag list to a CSV file for external use
*   **Pagination Controls**: Navigate through multiple pages when many tags are configured
*   **Items per Page**: Adjust the number of tags displayed per page (default: 20)

## Tag Creation Process

Creating a tag involves configuring multiple aspects of its definition. The creation dialog is organized into logical sections for clarity:

### Basic Information

![Create Tag Form - Basic Configuration](../images/CreateTagForm.png)

The basic configuration includes:

*   **Name** (Required): Unique identifier for the tag within PyAutomation
*   **Variable** (Required): Type of physical phenomenon (MassFlow, Pressure, Temperature, etc.)
*   **Unit** (Required): Engineering unit of measurement (populated based on Variable selection)
*   **Data Type**: Computer representation format (float, integer, boolean, string)
*   **Display Name** (Optional): Friendly name for UI display (can differ from the technical name)
*   **Description** (Optional): Human-readable description providing context and documentation

### OPC UA Configuration

*   **OPC UA Client** (Required for OPC UA tags): Select the configured OPC UA client connection
*   **Node Namespace** (Required for OPC UA tags): Select the specific node from the OPC UA server's address space

![Create Tag - Polling and Advanced Configuration](../images/CreateTagPollingAndFilterConfiguration.png)

### Advanced Configuration

The advanced configuration section includes:

*   **Polling Configuration**:
    *   **Scan Time (ms)**: Frequency of reading the tag value from its source
    *   **Dead Band**: Minimum change threshold required to trigger value updates
*   **Filters**:
    *   **Process Filter**: Apply smoothing to reduce noise in analog signals
    *   **Gaussian Filter**: Apply Gaussian smoothing algorithm for data filtering
*   **Detection**:
    *   **Outlier Detection**: Identify and flag values that deviate significantly from expected ranges
    *   **Out of Range Detection**: Monitor for values outside acceptable limits
    *   **Frozen Data Detection**: Detect when tag values remain unchanged for extended periods
*   **Additional Information**:
    *   **Segment**: Categorize tags by process segment or area
    *   **Manufacturer**: Specify equipment manufacturer information

For detailed step-by-step instructions, see the [Creating a Tag](Create.md) guide.

## Tag Management Operations

### Viewing Tags

The Tags Dashboard provides a real-time view of all configured tags, displaying their current values and configuration. Tags are updated continuously based on their configured scan times.

### Updating Tags

Tags can be modified directly from the dashboard using inline editing or through the edit dialog. Most properties can be changed without recreating the tag, allowing for flexible configuration adjustments.

See the [Updating a Tag](Update.md) guide for detailed instructions.

### Deleting Tags

When a tag is no longer needed, it can be permanently removed from the system. Deletion removes the tag configuration and stops data acquisition, but historical data remains in the database for reporting purposes.

See the [Deleting a Tag](Delete.md) guide for detailed instructions.

### Exporting Tags

The tag list can be exported to CSV format for:
*   Documentation and specification sheets
*   Backup purposes
*   Import into other systems
*   External analysis and reporting

## Trending and Visualization

The Trends feature allows you to visualize tag values over time, providing insights into process behavior, identifying anomalies, and verifying system performance.

Key capabilities include:

*   **Tag Selection**: Choose one or multiple tags to display on the same graph
*   **Time Range Selection**: View trends for different time periods (Last Hour, Last 24 Hours, custom ranges)
*   **Interactive Graphs**: Zoom, pan, and navigate through historical data
*   **Export Capabilities**: Capture graphs as images for reports

See the [Trending and Visualization](Trends.md) guide for detailed instructions.

## Best Practices

### Tag Naming Conventions

*   Use descriptive, consistent naming conventions (e.g., `FI_01` for Flow Indicator 01, `PI_02` for Pressure Indicator 02)
*   Include prefixes or suffixes to indicate tag type or location
*   Avoid special characters that may cause issues in expressions or external systems
*   Keep names concise but meaningful

### Scan Time Configuration

*   **High-Frequency Tags**: Use lower scan times (100-500ms) for critical process variables requiring rapid response
*   **Standard Monitoring**: Use moderate scan times (1000-5000ms) for routine process monitoring
*   **Slow-Changing Variables**: Use higher scan times (10000ms+) for variables that change slowly (levels, temperatures in large vessels)
*   Consider system load when configuring many tags with low scan times

### Dead Band Configuration

*   Set dead bands based on measurement resolution and process noise
*   Use smaller dead bands for critical measurements requiring high precision
*   Use larger dead bands for noisy signals or variables with acceptable tolerance ranges
*   Match dead band units to the tag's engineering unit

### OPC UA Configuration

*   Ensure OPC UA clients are configured and connected before creating tags
*   Verify node identifiers are correct by browsing the OPC UA server address space
*   Group related tags from the same OPC UA client for easier management
*   Test connectivity before deploying tags to production

### Data Quality

*   Enable appropriate detection features (outlier, out-of-range, frozen data) based on process requirements
*   Configure filters judiciously to balance noise reduction with response time
*   Monitor tag quality indicators in alarm conditions

## Common Use Cases

### Process Monitoring

Create tags for all critical process variables to enable real-time monitoring, historical logging, and alarm generation.

### Equipment Integration

Map OPC UA nodes from PLCs, RTUs, or other automation equipment to PyAutomation tags for centralized data collection.

### Data Logging

Configure tags with appropriate scan times and dead bands to efficiently log process data to the database for historical analysis.

### Alarm Management

Define tags that will be used as alarm sources, ensuring proper configuration of data types, units, and scan frequencies.

### Reporting and Analysis

Export tag lists and use trending capabilities to analyze process performance, identify optimization opportunities, and generate operational reports.

## Navigation to Related Modules

Tags integrate with other PyAutomation modules:

*   **Communications (OPC UA Clients)**: Configure OPC UA client connections that tags will use for data acquisition
*   **Alarms**: Create alarms based on tag values and thresholds
*   **Database**: Tag values are automatically logged to the database based on configured parameters
*   **Real Time Trends**: Visualize tag values over time using the trending interface
*   **Machines**: Associate tags with equipment and machine definitions

## Getting Started

To begin working with tags:

1.   **Ensure Prerequisites**: 
     *   Database connection is configured (see [Database Configuration](../Database/index.md))
     *   OPC UA clients are configured if using OPC UA tags (see [OPC UA Clients](../Communications/index.md))

2.   **Access the Tags Module**: 
     *   Navigate to **Tags** from the main menu

3.   **Create Your First Tag**: 
     *   Click the **Create Tag** button
     *   Follow the step-by-step guide in [Creating a Tag](Create.md)

4.   **Verify Tag Functionality**: 
     *   Confirm tags are receiving values from their sources
     *   Check that values are updating according to configured scan times
     *   Verify data logging to the database (if configured)

5.   **Explore Advanced Features**: 
     *   Configure polling and filtering options
     *   Set up trending visualization
     *   Create alarms based on tag values

For detailed instructions on specific operations, refer to the following guides:

*   [Creating a Tag](Create.md) - Complete guide to tag creation and configuration
*   [Updating a Tag](Update.md) - How to modify existing tag properties
*   [Deleting a Tag](Delete.md) - Removing tags from the system
*   [Trending and Visualization](Trends.md) - Visualizing tag data over time
