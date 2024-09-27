from automation.state_machine import AutomationStateMachine, Machine

class StateMachine1(AutomationStateMachine):

    def __init__(self, name:str):

        super(StateMachine1, self).__init__(name=name)

    def while_starting(self):

        self.send('start_to_wait')

    def while_waiting(self):

        self.send('wait_to_run')

    def while_running(self):

        # for i in range(80000000):
        #     a = i
        self.send('run_to_reset')

class StateMachine2(AutomationStateMachine):

    def __init__(self, name:str):

        super(StateMachine2, self).__init__(name=name)

    def while_starting(self):

        self.send('start_to_wait')

    def while_waiting(self):

        # for i in range(800000000):
        #     a = i
        self.send('wait_to_run')

automation_state_machine = StateMachine1(name="Test")
automation_state_machine2 = StateMachine2(name="Test2")

machine = Machine()
machine.append_machine(machine=automation_state_machine, interval=1, mode='async')
machine.append_machine(machine=automation_state_machine2, interval=0.0001, mode='async')
machine.start()