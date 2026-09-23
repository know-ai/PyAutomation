import gevent
import gevent.monkey
from automation import PyAutomation, embedded_opcua_server as opcua_server, server



gevent.monkey.patch_all()

app = PyAutomation()
app.run(server=server, create_tables=True, machines=(opcua_server,))