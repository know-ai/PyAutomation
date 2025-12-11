import gevent
import gevent.monkey
from automation import PyAutomation, server, opcua_server


gevent.monkey.patch_all()

app = PyAutomation()
app.define_dash_app(server=server)
setattr(app, "server", server)
app.run(create_tables=True, machines=(opcua_server,))