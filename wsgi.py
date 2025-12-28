import gevent
import gevent.monkey
from automation import PyAutomation, opcua_server, server



gevent.monkey.patch_all()

app = PyAutomation()
app.run(server=server, create_tables=True, machines=(opcua_server,))