from flask_restx import Namespace, Resource, fields
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
from ....models import IntegerType, FloatType, StringType, BooleanType


ns = Namespace('Machines', description='State Machines')
app = PyAutomation()

put_attr_value_model = api.model("put_attr_value_model",{
    'value':  fields.String(required=True)
})


@ns.route('/')
class MachinesCollection(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self):
        """
        Get Machines
        """
        return app.machine_manager.serialize_machines(), 200
    

@ns.route('/attr/<machine_name>/<attr>')
class MachineAttrResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self,machine_name:str, attr:str):
        """
        Get Machine Attr
        """
        machine = app.get_machine(name=StringType(machine_name))
        if not machine:

            return f"{machine_name} is not defined", 400
        
        if not hasattr(machine, attr):

            return f"{machine_name} has not attribute: {attr}", 404 
        
        attrs = machine.get_serilized_models()
        if attr not in attrs:

            return f"{attr} is not allowed", 403
         
        return app.machine_manager.serialize_machines(), 200
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(put_attr_value_model)
    def put(self, machine_name:str, attr:str):
        """
        Put Machine Attr
        """
        user = Api.get_current_user()
        machine = app.get_machine(name=StringType(machine_name))
        if not machine:

            return f"{machine_name} is not defined", 400
        
        if not hasattr(machine, attr):

            return f"{machine_name} has not attribute: {attr}", 404 
        
        if attr in ("name", "state"):

            if attr=="machine_interval" and machine.classification.lower()=="data acquisition system":

                return "You can not change daq machine interval from this way", 403

            return f"{attr} is not allowed", 403
        
        
        attrs = machine.get_serialized_models()
        if attr not in attrs:

            return f"{attr} is not allowed", 403
        
        machine_attr = getattr(machine, attr)

        try:
            
            if isinstance(machine_attr, (FloatType, float)):

                value = FloatType(float(api.payload["value"]))

            elif isinstance(machine_attr, (IntegerType, int)):

                value = IntegerType(int(api.payload["value"]))

            elif isinstance(machine_attr, (BooleanType, bool)):

                value = BooleanType(bool(api.payload["value"]))

            else:

                value = StringType(api.payload["value"])

        except Exception as err:

            return f"{err}", 400
        
        machine.put_attr(attr_name=attr, value=value, user=user)

        return f"{attr} updated successfully to {value.value}", 200
    

@ns.route('/action/<machine_name>/<action>')
class MachineActionResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def put(self,machine_name:str, action:str):
        """
        Post Machine transition
        """
        user = Api.get_current_user()
        machine = app.get_machine(name=StringType(machine_name))
        if not machine:

            return f"{machine_name} is not defined", 400
        
        machine, message = machine.transition(to=action, user=user)

        if machine:

            return machine.serialize(), 200
        
        return message, 403
    

@ns.route('/subscribe/<machine_name>/to/<tag_name>')
class SubscribeResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def post(self, machine_name:str, tag_name:str):
        """
        Subscribe Machine to Tags
        """
        machine = app.get_machine(name=StringType(machine_name))
        tag = app.get_tag_by_name(name=tag_name)

        if not machine:

            return f"{machine_name} is not defined", 400

        if not tag:

            return f"{tag_name} is not defined", 400
        
        if machine.subscribe_to(tag=tag):

            return f"{tag_name} subscribe to {machine_name} successfully", 200

        return f"{tag_name} is already subscribed to {machine_name}", 403


@ns.route('/unsubscribe/<machine_name>/to/<tag_name>')
class UnsubscribeResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def post(self, machine_name:str, tag_name:str):
        """
        Unsubscribe Tag in Machine
        """
        machine = app.get_machine(name=StringType(machine_name))
        tag = app.get_tag_by_name(name=tag_name)

        if not machine:

            return f"{machine_name} is not defined", 400

        if not tag:

            return f"{tag_name} is not defined", 400
        
        if machine.unsubscribe_to(tag=tag):

            return f"{tag_name} unsubscribed to {machine_name} successfully", 200
        
        return f"{tag_name} is not subscribed to {machine_name}", 403
