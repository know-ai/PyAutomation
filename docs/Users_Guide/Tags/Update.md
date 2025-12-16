# Updating a Tag

PyAutomation allows for the seamless modification of tag properties through an edit form. This ensures that all tag configurations can be updated in a structured and organized manner.

## Editing Procedure

1.  **Locate the Tag**: Navigate to the Tags Dashboard and find the row corresponding to the tag you wish to modify.

![Tags Dashboard with Tags](../images/TagsCreated.png)

2.  **Open Edit Form**: Click the **edit icon** (✏️) located in the **Actions** column of the tag's row to open the edit form.

![Edit Button](../images/TagsCreated_DeleteAndEditTagButton.png)

<!-- TODO: Add image EditTag_EditButtonHighlighted.png - Screenshot highlighting the edit icon button in the Actions column for a specific tag row -->

3.  **Edit Tag Properties**: The edit form will open, displaying all tag configuration fields. Modify the desired properties:
    *   **Name**: Change the unique identifier (must remain unique)
    *   **Description**: Update the tag description
    *   **Display Name**: Modify the friendly name for visualization
    *   **Scan Time**: Adjust the polling frequency
    *   **Deadband**: Update the change threshold
    *   **OPC UA Configuration**: Modify client or node namespace
    *   **Advanced Configuration**: Update filters, anomaly detection, or segment/manufacturer information
    *   **Note**: All fields can be modified except the tag's unique identifier (ID).

![Edit Tag Form](../images/EditTagForm.png)

<!-- TODO: Add image EditTagForm_NameField.png - Screenshot showing the Name field in the edit form with a value being modified -->
<!-- TODO: Add image EditTagForm_DescriptionField.png - Screenshot showing the Description field in the edit form -->
<!-- TODO: Add image EditTagForm_ScanTimeField.png - Screenshot showing the Scan Time field being edited in the edit form -->
<!-- TODO: Add image EditTagForm_DeadbandField.png - Screenshot showing the Deadband field in the edit form -->
<!-- TODO: Add image EditTagForm_OPCUAConfiguration.png - Screenshot showing the OPC UA Configuration section in the edit form -->
<!-- TODO: Add image EditTagForm_AdvancedConfiguration.png - Screenshot showing the Advanced Configuration section (filters, anomaly detection) in the edit form -->

4.  **Save Changes**: Click the **Save** or **Update** button at the bottom of the form to apply the changes.

<!-- TODO: Add image EditTagForm_SaveButton.png - Screenshot highlighting the Save/Update button at the bottom of the edit form -->
<!-- TODO: Add image EditTagForm_ConfirmationDialog.png - Screenshot of the confirmation dialog (if any) asking to confirm the tag update -->

5.  **Verification**: The dashboard will refresh to reflect the updated tag properties. The modified fields will be displayed with their new values in the Tags Dashboard.

![Final Result After Update](../images/TagsCreated.png)

<!-- TODO: Add image EditTag_UpdatedFieldInTable.png - Screenshot showing a specific updated field (e.g., Name, Description, Scan Time) displayed in the Tags Dashboard table after the update -->
<!-- TODO: Add image EditTag_ComparisonBeforeAfter.png - Screenshot showing a side-by-side comparison or highlighting the changed value in the table (optional, if useful) -->
