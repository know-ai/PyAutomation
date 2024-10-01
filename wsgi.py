from automation import PyAutomation, server

app = PyAutomation()
app.define_dash_app(server=server)
app.run(debug=True, create_tables=True, alarm_worker=True)