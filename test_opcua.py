from automation.opcua import Client
from time import sleep
from automation import PyAutomation

app = PyAutomation()

servers = app.find_opcua_servers()
print(f"Servers: {servers}")
# url = servers[0]['DiscoveryUrls'][0]
# print(f"Url: {url}")
# client = Client(url=url)
# client.connect()
# tree = client.get_opc_ua_tree()
# print(f"Tree: {tree}")
# # breakpoint()

# while True:
#     namespace = tree[0]['Objects'][0]['children'][0]['key']
#     value = client.get_nodes_values(namespaces=[namespace])
#     print(value)
#     sleep(1)