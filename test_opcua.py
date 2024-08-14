from automation.opcua import Client

servers = Client.find_servers('localhost', 4840)
url = servers[0]['DiscoveryUrls'][0]
print(f"Url: {url}")
client = Client(url=url)
client.connect()

print(f"Tree: {client.get_opc_ua_tree()}")