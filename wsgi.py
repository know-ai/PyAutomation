import gevent
import gevent.monkey
from automation import PyAutomation, server, opcua_server


gevent.monkey.patch_all()

app = PyAutomation()
app.append_machine(machine=opcua_server)
app.define_dash_app(server=server)
app.run(create_tables=True)