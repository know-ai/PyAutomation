from automation import PyAutomation

app = PyAutomation()
app.run(debug=True, create_tables=True, alarm_worker=True)