import { createSlice, PayloadAction } from "@reduxjs/toolkit";
import type { Machine } from "../../services/machines";

interface MachinesState {
  // Map of machine name -> latest machine data
  machines: Record<string, Machine>;
}

const initialState: MachinesState = {
  machines: {},
};

const machinesSlice = createSlice({
  name: "machines",
  initialState,
  reducers: {
    updateMachine: (state, action: PayloadAction<Machine>) => {
      const machine = action.payload;
      if (machine.name) {
        state.machines[machine.name] = machine;
      }
    },
    updateMachinesBatch: (state, action: PayloadAction<Machine[]>) => {
      action.payload.forEach((machine) => {
        if (machine.name) {
          state.machines[machine.name] = machine;
        }
      });
    },
    clearMachines: (state) => {
      state.machines = {};
    },
    loadAllMachines: (state, action: PayloadAction<Machine[]>) => {
      // Replace all machines with the new list
      state.machines = {};
      action.payload.forEach((machine) => {
        if (machine.name) {
          state.machines[machine.name] = machine;
        }
      });
    },
  },
});

export const { updateMachine, updateMachinesBatch, clearMachines, loadAllMachines } = machinesSlice.actions;
export default machinesSlice.reducer;

