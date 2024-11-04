from automation import PyAutomation, server, opcua_server

app = PyAutomation()
app.append_machine(machine=opcua_server)
app.define_dash_app(server=server)
app.run(debug=True, create_tables=True)