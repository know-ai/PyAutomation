# Creating a Tag

The creation of a new tag involves defining its identity, physical properties, and communication settings. Follow the steps below to configure a new tag in the PyAutomation dashboard.

## Step-by-Step Configuration

### 1. Assign a Name

The **Name** is the unique identifier for the tag within the system.

- **Requirement**: Must be unique across the entire project.
- **Action**: Enter a descriptive name (e.g., `FIT-101`, `Tank_Level`).

![Tag Name Entry](images/image-1.png)
![Tag Name Filled](images/image-2.png)

### 2. Variable Type

Select the physical phenomenon that this tag represents. This selection filters the available Engineering Units.

- **Examples**: Pressure, Mass Flow, Temperature, Density.

![Variable Type Selection](images/image-3.png)
![Variable Type Selected](images/image-4.png)

### 3. Engineering Units

Choose the unit of measurement for the tag. The list is populated based on the selected **Variable Type**.

- **Example**: If "Temperature" is selected, options might include `°C`, `°F`, `K`.

![Unit Selection](images/image-5.png)
![Unit Selected](images/image-6.png)

### 4. Data Type

Specify the computer data format for the tag's value.

- **Options**: `Float`, `Integer`, `Boolean`, `String`.

![Data Type Selection](images/image-7.png)
![Data Type Selected](images/image-8.png)

### 5. Description (Optional)

Provide a human-readable description to add context to the tag.

- **Usage**: "Feedwater Inlet Temperature".

![Description Entry](images/image-9.png)

### 6. Display Name (Optional)

Set a friendly name for visualization purposes on dashboards, which can differ from the unique system ID.

![Display Name Entry](images/image-10.png)

### 7. OPC UA Configuration (Optional)

If this tag interacts with an OPC UA server, configure the connection details.

- **OPC UA Address**: The endpoint URL of the OPC UA server.
  ![OPC Configuration](images/image-11.png)

- **Node ID**: The specific node identifier within the OPC UA address space (e.g., `ns=2;s=Device1.Temperature`).
  ![Node ID Configuration](images/image-25.png)

### 8. Scan Time

Define the frequency at which the system reads or updates the tag value (in milliseconds).

- **Usage**: Lower values provide higher resolution but increase system load.

![Scan Time Configuration](images/image-26.png)

### 9. Deadband

Set a threshold for value changes. Updates are only processed if the value changes by more than this amount.

- **Benefit**: Reduces database noise and network traffic.
- **Note**: The unit matches the **Engineering Unit** selected in Step 3.

![Deadband Configuration](images/image-27.png)

### 10. Finalize Creation

Review all configured fields. Click the **Create** button to save the new tag.

![Create Button](images/image-12.png)

Upon successful creation, the tag will appear in the main Tags Dashboard.

![Tags Dashboard](images/image-13.png)

## Exporting Tag List

You can export the current list of tags to an Excel file for external documentation or backup purposes by clicking the **Export** button.

![Export Button](images/image-14.png)
![Export Process](images/image-15.png)
![Export Result](images/image-16.png)
