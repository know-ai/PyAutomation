export const SHOW_INFRA_MACHINES_KEY = "pyautomation.showInfraMachines";

export type InfraMachineRef = {
  name?: string | null;
  classification?: string | null;
};

export function loadShowInfraMachines(): boolean {
  try {
    return localStorage.getItem(SHOW_INFRA_MACHINES_KEY) === "true";
  } catch (_e) {
    return false;
  }
}

export function persistShowInfraMachines(show: boolean) {
  try {
    localStorage.setItem(SHOW_INFRA_MACHINES_KEY, show ? "true" : "false");
  } catch (_e) {
    // ignore
  }
}

export function isInfrastructureMachine(machine: InfraMachineRef): boolean {
  const classification = String(machine.classification || "").trim().toLowerCase();
  if (
    classification === "data acquisition system" ||
    classification === "opc ua server" ||
    classification === "daq"
  ) {
    return true;
  }
  if (classification.includes("data acquisition")) return true;
  if (classification.includes("opc ua")) return true;
  const name = String(machine.name || "").trim();
  if (/^DAQ([_-]|$)/i.test(name)) return true;
  if (/^OPCUA/i.test(name)) return true;
  return false;
}

export function visibleMachineTabs<T extends InfraMachineRef>(machines: T[], showInfra: boolean): T[] {
  const named = machines.filter((machine) => Boolean(machine.name));
  const detection = named.filter((machine) => !isInfrastructureMachine(machine));
  if (!showInfra) return detection;
  const infra = named.filter((machine) => isInfrastructureMachine(machine));
  return [...infra, ...detection];
}
