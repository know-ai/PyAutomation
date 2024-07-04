# PyAutomation

The development intention of this framework is to provide the ability to develop industrial applications where processes need to be executed concurrently and field data need to be managed for monitoring, control, and supervision applications.



![Core](docs/img/PyAutomationCore.svg)

In the image above, you can generally see the architecture and interaction of the different modules that make up the framework.

For this, state machines are available that run in the background and concurrently to acquire data by query (DAQ), Acquire Data by Exception (DAS) and any other general purpose state machine.

It has a memory persistence module for real-time variables that we call (CVT, Current Value Table).

There is also an alarm management system

And finally, the disk persistence of the variables to provide functionalities for historical trends of the field variables.