# Creating a Tag

<div align="center" style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); border-radius: 15px; padding: 3em 2em; margin: 2em 0; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">

<h2 style="color: #1976d2; font-size: 2.5em; margin-bottom: 0.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.1);">
  ➕ Create Your First Tag
</h2>

<p style="color: #1565c0; font-size: 1.4em; margin-top: 1em; font-weight: 300;">
  The creation of a new tag involves defining its identity, physical properties, and communication settings. Follow the steps below to configure a new tag in the PyAutomation dashboard.
</p>

</div>

## 🚪 Opening the Create Tag Dialog

<div style="background: #f8f9fa; border-left: 5px solid #2196f3; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<p style="font-size: 1.1em; color: #2d3748; margin-bottom: 1em;">
  To begin creating a new tag:
</p>

</div>

1. Navigate to the **Tags** module from the main menu
2. Click the **Create Tag** button (green button with plus icon) located in the top-right corner of the Tags Dashboard
3. The "Create New Tag" dialog will open, presenting all configuration options

![Create Tag Form](../images/CreateTagForm.png)

## Step-by-Step Configuration

### 1. Assign a Name

The **Name** is the unique identifier for the tag within the system.

- **Requirement**: Must be unique across the entire project.
- **Action**: Enter a descriptive name (e.g., `FIT-101`, `Tank_Level`).

![Name Field](../images/CreateTagForm_Name.png)

![Name Field Filled](../images/CreateTagForm_NameFilled.png)

### 2. Variable Type

Select the physical phenomenon that this tag represents. This selection filters the available Engineering Units.

- **Examples**: Pressure, Mass Flow, Temperature, Density.

![Variable Dropdown](../images/CreateTagForm_VariableDropdown.png)

![Variable Selected](../images/CreateTagForm_VariableSelected.png)

### 3. Engineering Units

Choose the unit of measurement for the tag. The list is populated based on the selected **Variable Type**.

- **Example**: If "Temperature" is selected, options might include `°C`, `°F`, `K`.

![Unit Dropdown](../images/CreateTagForm_UnitDropdown.png)

![Unit Selected](../images/CreateTagForm_UnitSelected.png)

### 4. Data Type

Specify the computer data format for the tag's value.

- **Options**: `Float`, `Integer`, `Boolean`, `String`.

![Data Type Dropdown](../images/CreateTagForm_DataTypeDropdown.png)

![Data Type Selected](../images/CreateTagForm_DataTypeSelected.png)

### 5. Description (Optional)

Provide a human-readable description to add context to the tag.

- **Usage**: "Feedwater Inlet Temperature".

![Description Field](../images/CreateTagForma_Description.png)

### 6. Display Name (Optional)

Set a friendly name for visualization purposes on dashboards, which can differ from the unique system ID.

![Display Name Field](../images/CreateTagForm_DisplayName.png)

### 7. OPC UA Configuration (Optional)

If this tag interacts with an OPC UA server, configure the connection details.

- **OPC UA Client**: Select the configured OPC UA client connection.

  ![OPC UA Client Dropdown](../images/CreateTagForm_OPCUAClient.png)

- **Node Namespace**: Select the specific node identifier from the OPC UA server's address space (e.g., `ns=2;i=2`, `FI_02`).

  ![Node Namespace Dropdown](../images/CreateTagForm_NodeNamespaceDropdown.png)

  ![Node Namespace Selected](../images/CreateTagForm_NodeNamespaceSelected.png)

### 8. Scan Time

Define the frequency at which the system reads or updates the tag value (in milliseconds).

- **Usage**: Lower values provide higher resolution but increase system load.

![Scan Time Configuration](../images/CreateTagForm_ScanTimeWithPolling1000ms.png)

### 9. Deadband

Set a threshold for value changes. Updates are only processed if the value changes by more than this amount.

- **Benefit**: Reduces database noise and network traffic.
- **Note**: The unit matches the **Engineering Unit** selected in Step 3.

![Deadband Configuration](../images/CreateTagForm_Deadband.png)

### 🔧 10. Advanced Configuration (Optional)

<div style="background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #ff9800;">

<h4 style="color: #e65100; font-size: 1.5em; margin-bottom: 1em;">
  ⚙️ Powerful Tools for Data Quality
</h4>

<p style="font-size: 1.1em; color: #d84315; margin-bottom: 1.5em;">
  The Advanced Configuration section provides powerful tools for improving data quality, detecting anomalies, and organizing tags within your industrial system. These features help ensure reliable data collection and early detection of potential issues.
</p>

</div>

![Advanced Configuration Options](../images/CreateTagPollingAndFilterConfiguration.png)

#### 10.1. Wavelet Filter (Real-Time)

The **Wavelet RT filter** applies discrete wavelet transform (DWT) denoising off the acquisition hot path. Raw samples stay on the source tag; filtered values are published on a derived tag `{name}.f` at the state machine `sample_interval`.

**How it works:**
- OPC acquisition writes raw values O(1) into a ring buffer (no DWT on the hot path)
- A dedicated `WaveletWorker` runs DWT + soft threshold + inverse DWT on a sliding window
- State machines subscribed to a filtered tag automatically consume `{name}.f`
- Bad OPC quality or non-finite values trigger **hold**: the `.f` tag keeps the last good value with **UNCERTAIN** quality

**Configuration Parameters:**
- **filter_enabled**: Master switch
- **filter_wavelet** (default: `db4`): PyWavelets family (`db4`, `db6`, `sym4`, …)
- **filter_level** (default: 4): DWT decomposition levels (1–6)
- **filter_threshold_factor** (default: 3.0): Soft-threshold multiplier (higher = smoother)
- **filter_persist**: When enabled, the `.f` tag is registered in the historian (SAF)

**Use Cases:**
- Noisy analog sensors used by state machines or control logic
- Signals requiring smoothing without delaying raw acquisition trends
- Process tags where operators need visibility into filter health (hold / UNCERTAIN quality)

**Example:** Tag `Line1.Pressure` with wavelet enabled publishes filtered values on `Line1.Pressure.f`. If the source goes BAD, the HMI shows hold + UNCERTAIN on the filtered tag while preserving the last good reading.

> **Note:** Legacy Gaussian (Kalman) and process filters were removed in 2026-08-19. Use wavelet RT only.

![Filter Configuration](../images/CreateTagForm_FilterConfiguration.png)

#### 10.2. Anomaly Detection

Anomaly detection features automatically identify unusual patterns in tag data that may indicate sensor failures, communication issues, or process problems. When anomalies are detected, the system can trigger alarms to alert operators.

##### Frozen Data Detection

**Frozen Data Detection** identifies when a sensor appears to be "stuck" or not updating, which typically indicates:
- Sensor failure or disconnection
- Communication loss with the sensor
- Sensor calibration issues
- Mechanical binding or obstruction

**How it works:**
- The system maintains a rolling buffer of recent tag values
- It calculates the standard deviation of values in the buffer
- If the standard deviation is less than 0.001 (indicating virtually no variation), an anomaly alarm is triggered
- The alarm description is set to "Frozen data anomaly"

**Use Cases:**
- Detecting when a flow meter stops responding
- Identifying temperature sensors that have failed
- Monitoring for communication interruptions with remote sensors
- Early warning of sensor maintenance needs

**Example:** If a pressure sensor reads 150.0 psi, 150.0 psi, 150.0 psi, 150.0 psi over several scan cycles, frozen data detection will flag this as anomalous since real process values should show at least minor variations.

##### Outlier Detection

**Outlier Detection** identifies individual data points that deviate significantly from expected values. This feature helps detect:
- Sudden spikes or drops in sensor readings
- Measurement errors
- Transient electrical interference
- Sensor calibration drift

**How it works:**
- The system maintains a buffer of recent measurements
- Statistical analysis is performed on the buffer to establish expected value ranges
- Values that fall outside these ranges are flagged as outliers

**Status:** This feature is currently in active development and will provide configurable thresholds for outlier identification.

##### Out of Range Detection

**Out of Range Detection** monitors whether tag values fall within acceptable operational limits. This helps identify:
- Process excursions beyond safe operating parameters
- Sensor readings that exceed physical limits
- Configuration errors in sensor scaling

**How it works:**
- Similar to outlier detection, this feature uses statistical analysis of historical data
- It can be configured with specific min/max limits for each tag
- Alarms are triggered when values consistently fall outside acceptable ranges

**Status:** This feature is currently in active development and will provide configurable range limits.

![Anomalies Detection Configuration](../images/CreateTagForm_AnomaliesDetectionConfiguration.png)

#### 10.3. Additional Information: Segment and Manufacturer

The **Segment** and **Manufacturer** fields provide organizational metadata that helps categorize and manage tags within large industrial systems.

##### Segment

A **Segment** represents a logical grouping of tags that belong to a specific area, system, or process unit within your plant. Segments help organize tags for:
- **Reporting and Analysis**: Group related tags together for trend analysis
- **Maintenance Planning**: Identify all sensors in a particular area that may need maintenance
- **System Architecture**: Map tags to physical locations or process units
- **Access Control**: Apply permissions or visibility rules by segment

**Examples:**
- "Boiler Unit 1", "Distillation Column A", "Cooling Water System"
- "North Wing", "Production Line 2", "Quality Control Lab"

##### Manufacturer

The **Manufacturer** field identifies the company or brand that produced the sensor or device associated with the tag. This information is useful for:
- **Maintenance Records**: Track which manufacturer's equipment needs service
- **Spare Parts Management**: Identify compatible replacement parts
- **Warranty Tracking**: Manage equipment warranties by manufacturer
- **Performance Analysis**: Compare performance across different manufacturers
- **Technical Support**: Contact the correct manufacturer for technical assistance

**Relationship:**
- Each Segment is associated with a Manufacturer
- Multiple Segments can share the same Manufacturer
- This relationship helps organize equipment by both location (segment) and supplier (manufacturer)

**Example Use Case:**
- Segment: "Reactor Vessel 3"
- Manufacturer: "Siemens"
- This indicates that all tags in Reactor Vessel 3 use Siemens equipment, making it easier to coordinate maintenance, order parts, and access technical documentation.

![Additional Information - Segment and Manufacturer](../images/CreateTagForm_AditionalInformationSegmentAndManufacturer.png)

#### Best Practices for Advanced Configuration

1. **Filtering**: Enable Gaussian Filter for sensors known to have noise issues. Start with default parameters and adjust based on observed behavior.

2. **Anomaly Detection**: Enable Frozen Data Detection for critical sensors where communication loss could indicate serious problems.

3. **Organization**: Use consistent naming conventions for Segments (e.g., "Unit-01", "Unit-02") and ensure Manufacturer names match exactly across your system.

4. **Performance**: Be aware that enabling multiple filters and detection algorithms increases computational load. Monitor system performance when enabling these features on many tags simultaneously.

### 11. Finalize Creation

Review all configured fields. Click the **Create Tag** button to save the new tag.

![Create and Cancel Buttons](../images/CreateTagForm_CreateAndCancelButton.png)

Upon successful creation, the tag will appear in the main Tags Dashboard.

![Tags Dashboard After Creation](../images/TagsCreated.png)

## Exporting Tag List

You can export the current list of tags to a CSV file for external documentation or backup purposes by clicking the **Export CSV** button.

![Export CSV Button](../images/CreateTag_ExportCSVButton.png)

![Export CSV Result](../images/CreateTag_ExportCSVResult.png)
