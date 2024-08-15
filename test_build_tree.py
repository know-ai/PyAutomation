import os
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from automation.opcua import Client
from automation import PyAutomation

app = PyAutomation()


def flatten(self, l):
        return [item for sublist in l for item in sublist]

def make_file(self, file_name):
    return dmc.Text(
        [DashIconify(icon="akar-icons:file"), " ", file_name],
        style={"paddingTop": '5px'}
    )

def make_folder(self, folder_name):
    return [DashIconify(icon="akar-icons:folder"), " ", folder_name]

def build_tree(self, objects:list):
    
    d = list()
    
    for obj in objects:
        
        if obj['children']:

            children = self.flatten([self.build_tree(os.path.join(path, x)) for x in os.listdir(path)])
            
            if isRoot:
                d.append(
                    dmc.AccordionItem(
                        children=children,
                        label=self.make_folder(os.path.basename(path))
                    )
                )
            
            else:

                d.append(
                    dmc.Accordion(
                        children=[
                            dmc.AccordionItem(
                                children=children,
                                label=self.make_folder(os.path.basename(path))
                            )
                        ],
                        multiple=True
                    )
                )
        
        else:

            d.append(make_file(obj['title']))

    return d

if __name__=='__main__':

    servers = app.find_opcua_servers()
    url = servers[0]['DiscoveryUrls'][0]
    client = Client(url=url)
    client.connect()
    tree = client.get_opc_ua_tree()
    print(tree)