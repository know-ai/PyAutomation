from automation import PyAutomation, server

app = PyAutomation()
app.run(debug=True, create_tables=True, alarm_worker=True, server=server)