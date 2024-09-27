from automation.opcua import Client
from time import sleep
from automation import PyAutomation

app = PyAutomation()

servers = app.find_opcua_servers()
