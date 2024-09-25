from automation import PyAutomation
from automation import CreateApp

flask_server = CreateApp()
server = flask_server()                                                 # Flask App
app = PyAutomation()
app.run(debug=True, create_tables=True, alarm_worker=True, server=server)