import dash
import dash_bootstrap_components as dbc
from automation.models import StringType, IntegerType, FloatType
from ..components.machines import MachinesComponents
from ...variables import *

def init_callback(app:dash.Dash):

    @app.callback(
        dash.Output('machines_detailed_tabs', 'children'),
        dash.Output('machines_detailed_tabs', 'active_tab'),
        dash.Output("machine_detailed_content", "children"),
        dash.Input('machines_detailed_page', 'pathname'),
        prevent_initial_call=True
        )
    def display_page(pathname):
        r"""
        Documentation here
        """
        tabs = list()
        active_tab = None
        machine_tab_content = dash.html.P("This shouldn't ever be displayed...")
        if pathname=="/machines-detailed":
            for machine, _, _ in app.automation.get_machines():

                if hasattr(machine, "classification"):

                    if machine.classification.value.lower()=="opc ua server":

                        continue

                    elif machine.classification.value.lower()=="data acquisition system":

                        continue

                    internal_variables = machine.get_internal_process_type_variables()
                    if internal_variables:

                        tabs.append(dbc.Tab(label=f"{machine.name.value}", tab_id=f"tab-{machine.name.value}"))
                        if not active_tab:

                            active_tab = f"tab-{machine.name.value}"
                            machine_tab_content = MachinesComponents.machine_tab_content(app=app.automation, machine_name=machine.name.value)
        
        return tabs, active_tab, machine_tab_content
    
    @app.callback(
        dash.Output('machines_detailed_datatable', 'data', allow_duplicate=True),
        dash.Input('timestamp-interval', 'n_intervals'),
        dash.State('machines_detailed_tabs', 'active_tab'),
        prevent_initial_call=False
    )
    def update_table( n_intervals, active_tab:str):
        machine_name = active_tab.split("-")[-1]
        def flatten_dict(d, parent_key='', sep='.'): 
            items = [] 
            for k, v in d.items(): 
                
                new_key = f"{parent_key}{sep}{k}" if parent_key else k 
                if isinstance(v, dict): 
                    items.extend(flatten_dict(v, new_key, sep=sep).items()) 
                else: 
                    items.append((new_key, v)) 
                    
            return dict(items)

        machine = app.automation.get_machine(name=StringType(machine_name))
        data = list()
        serialized_data = machine.serialize()
        flattened_data = flatten_dict(serialized_data)
        for key, value in flattened_data.items():

            if isinstance(value, (bool, int, str, float)):

                data.append({"name": key, "value": value})

        return data
    
    @app.callback(
        dash.Output('subscribed_tag_machine_input', 'options', allow_duplicate=True),
        dash.Output('field_tag_input', 'options', allow_duplicate=True),
        dash.Output('internal_tag_input', 'options', allow_duplicate=True),
        dash.Input('machines_detailed_tabs', 'active_tab'),
        prevent_initial_call=False
    )
    def update_subscription_form(active_tab:str):
        machine_name = active_tab.split("-")[-1]
        machine = app.automation.get_machine(name=StringType(machine_name))
        internal_variables = machine.get_read_only_process_type_variables()
        subscribed_tags_machine = [{"label": "", "value": ""}]
        not_subscribed = [{"label": "", "value": ""}]
        available_tags = [{"label": "", "value": ""}]
        tags = app.automation.cvt._cvt.get_cuasi_field_tags_names()
        for _tag_name, value in internal_variables.items():
            
            if value.tag:
                subscribed_tags_machine.append({
                    "label": f"{value.tag.name}->{_tag_name}", "value": value.tag.name
                    })
                if value.tag.name in tags:
                    tags.remove(value.tag.name)
                
            else:

                not_subscribed.append({
                    "label": _tag_name, "value": _tag_name
                })

        for tag in tags:

            available_tags.append({
                "label": tag, "value": tag
            })
        return subscribed_tags_machine, available_tags, not_subscribed
    
    @app.callback(
        dash.Output("machine_threshold_input", "placeholder", allow_duplicate=True),
        dash.Output("machine_threshold_input", "disabled", allow_duplicate=True),
        dash.Output("threshold_input_text", 'children', allow_duplicate=True),
        dash.Output("machine_interval_input", 'placeholder', allow_duplicate=True),
        dash.Output("buffer_size_input", 'placeholder', allow_duplicate=True),
        dash.Output("buffer_size_input", 'disabled', allow_duplicate=True),
        dash.Output("on_delay_input", 'placeholder', allow_duplicate=True),
        dash.Output("machine_threshold_input", "value", allow_duplicate=True),
        dash.Output("machine_interval_input", 'value', allow_duplicate=True),
        dash.Output("buffer_size_input", 'value', allow_duplicate=True),
        dash.Output("on_delay_input", 'value', allow_duplicate=True),
        dash.Input('machines_detailed_tabs', 'active_tab'),
        prevent_initial_call=False
    )
    def update_attributes_form(active_tab:str):
        machine_name = active_tab.split("-")[-1]
        machine = app.automation.get_machine(name=StringType(machine_name))
        machine_interval = machine.get_interval()
        threshold = machine.threshold
        on_delay = machine.on_delay
        machine_threshold_place = f"Current threshold {threshold.value}"
        machine_interval = f"Current machine interval {machine_interval}"
        threshold_input_text = threshold.unit
        buffer_size = f"Buffer Size"
        disable = True
        if hasattr(machine, "buffer_size"):
            disable = False
            buffer_size = machine.buffer_size
            buffer_size = f"Current buffer size: {buffer_size.value}"
        if "pfm" in machine_name.lower():
            disable = True
        elif "observer" in  machine_name.lower():
            disable = True
        on_delay = f"Current on delay: {on_delay.value}"
        
        return machine_threshold_place, disable, threshold_input_text, machine_interval, buffer_size, disable, on_delay, "", "", "", ""
    
    @app.callback(
        dash.Output('machine_state_input', 'children'),
        dash.Input('timestamp-interval', 'n_intervals'),
        dash.State('machines_detailed_tabs', 'active_tab'),
        dash.State('machine_state_input', 'children'),
        prevent_initial_call=False
    )
    def update_state( n_intervals, active_tab:str, previous_machine_state):
        r"""
        Documentation here
        """
        machine_name = active_tab.split("-")[-1]
        machine = app.automation.get_machine(name=StringType(machine_name))
        state = machine.current_state.value

        if state!=previous_machine_state:
            actions = [{"label": "", "value": ""}]
            for action in machine.get_allowed_actions():
                actions.append({"label": action, "value": action})
            dash.set_props("machine_actions_input", {
                'options': actions
                })

            return state

        return previous_machine_state
    
    @app.callback(
        dash.Input("field_tag_input", "value"),
        dash.Input("internal_tag_input", "value"),
        )
    def enable_subscribe_button(
        field_tag:str, 
        internal_tag:str
        )->str:
        r"""
        Documentation here
        """
        if field_tag and internal_tag:

            dash.set_props("subscribe_tag_machine_button", {'disabled': False})

        else:
            
            dash.set_props("subscribe_tag_machine_button", {'disabled': True})

    @app.callback(
        dash.Input("subscribed_tag_machine_input", "value")
        )
    def enable_unsubscribe_button(
        tag_machine:str
        )->str:
        r"""
        Documentation here
        """
        if tag_machine:

            dash.set_props("unsubscribe_tag_machine_button", {'disabled': False})

        else:
            
            dash.set_props("unsubscribe_tag_machine_button", {'disabled': True})

    @app.callback(
        dash.Output("field_tag_input", "value", allow_duplicate=True),
        dash.Output("internal_tag_input", "value", allow_duplicate=True),
        dash.Output('subscribed_tag_machine_input', 'value', allow_duplicate=True),
        dash.Output("field_tag_input", "options", allow_duplicate=True),
        dash.Output("internal_tag_input", "options", allow_duplicate=True),
        dash.Output('subscribed_tag_machine_input', 'options'),
        dash.Input('subscribe_tag_machine_button', 'n_clicks'),
        dash.State("field_tag_input", "value"),
        dash.State("internal_tag_input", "value"),
        dash.State('machines_detailed_tabs', 'active_tab'),
        dash.State('subscribed_tag_machine_input', 'options'),
        dash.State("field_tag_input", "options"),
        dash.State("internal_tag_input", "options"),
        prevent_initial_call=True
    )
    def subscribed_on_click(
        btn1, 
        field_tag_input:str,
        internal_tag_input:str,
        active_tab:str,
        tags_machine_options:list,
        field_tag_options:list,
        internal_tag_options:list,
        ):
        r"""
        Documentation here
        """
        if "subscribe_tag_machine_button" == dash.ctx.triggered_id:

            machine_name = active_tab.split("-")[-1]
            machine = app.automation.get_machine(name=StringType(machine_name))
            field_tag = app.automation.cvt._cvt.get_tag_by_name(name=field_tag_input)

            subscribed, message = machine.subscribe_to(tag=field_tag, default_tag_name=internal_tag_input)

            if subscribed:

                tags_machine_options.append({
                    "label": f"{field_tag_input}->{internal_tag_input}", "value": internal_tag_input
                })
                field_tag_options.remove({
                    "label": field_tag_input, "value": field_tag_input
                })
                internal_tag_options.remove({
                    "label": internal_tag_input, "value": internal_tag_input
                })

            return "", "", "", field_tag_options, internal_tag_options, tags_machine_options

    @app.callback(
        dash.Output('subscribed_tag_machine_input', 'value', allow_duplicate=True),
        dash.Output('subscribed_tag_machine_input', 'options', allow_duplicate=True),
        dash.Output("field_tag_input", "options", allow_duplicate=True),
        dash.Output("internal_tag_input", "options", allow_duplicate=True),
        dash.Input('unsubscribe_tag_machine_button', 'n_clicks'),
        dash.State('subscribed_tag_machine_input', 'value'),
        dash.State('machines_detailed_tabs', 'active_tab'),
        dash.State('subscribed_tag_machine_input', 'options'),
        dash.State("field_tag_input", "options"),
        dash.State("internal_tag_input", "options"),
        prevent_initial_call=True
    )
    def unsubscribed_on_click(
        btn1,
        tag_name:str,
        active_tab:str,
        tags_machine_options:list,
        field_tags_options:list,
        internal_tags_options:list
        ):
        r"""
        Documentation here
        """
        if "unsubscribe_tag_machine_button" == dash.ctx.triggered_id:

            machine_name = active_tab.split("-")[-1]
            machine = app.automation.get_machine(name=StringType(machine_name))
            tag = app.automation.get_tag_by_name(name=tag_name)
            if machine.unsubscribe_to(tag=tag):

                for tag_machine in tags_machine_options:
                    _tag_machine = tag_machine["label"].split("->")
                    _tag_name = _tag_machine[0]
                    _internal_tag = _tag_machine[-1]
                    if _tag_name==tag_name:
                        
                        break
                
                tags_machine_options.remove(tag_machine)
                field_tags_options.append({"label": _tag_name, "value": _tag_name})
                internal_tags_options.append({ "label": _internal_tag, "value": _internal_tag})

            return "", tags_machine_options, field_tags_options, internal_tags_options

    @app.callback(
        dash.Input('machine_actions_input', 'value'),
        dash.State('machines_detailed_tabs', 'active_tab'),
        prevent_initial_call=True
    )
    def dropdown_actions(action:str, active_tab:str,):
        r"""
        documentation here
        """
        if action:

            machine_name = active_tab.split("-")[-1]
            message = f'are you sure you want to {action} {machine_name} state machine?'
            dash.set_props("modal-question-body-action-machine", {"children": message})
            dash.set_props("modal-question-action-machine", {'is_open': True})

    @app.callback(
        dash.Output("modal-error-subscription", "is_open"),
        dash.Input("close-modal-error-button-subscription", "n_clicks"),
        [dash.State("modal-error-subscription", "is_open")],
    )
    def close_error_button(n, is_open):
        r"""
        Documentation here
        """
        if n:

            return not is_open
        
        return is_open
    
    @app.callback(
        dash.Output("modal-question-action-machine", "is_open"), 
        dash.Output("question-action-machine-yes", "n_clicks"),
        dash.Output("question-action-machine-no", "n_clicks"),
        dash.Input("question-action-machine-yes", "n_clicks"), 
        dash.Input("question-action-machine-no", "n_clicks"),
        dash.Input('machine_actions_input', 'value'),
        dash.State('machines_detailed_tabs', 'active_tab'),
        dash.State("modal-question-action-machine", "is_open"),
        prevent_initial_call=True
    )
    def question_action_machine_yes_or_no(yes_n, no_n, action:str, active_tab:str, is_open):
        r"""
        Documentation here
        """
        if action:

            if yes_n:

                machine_name = active_tab.split("-")[-1]
                machine = app.automation.get_machine(name=StringType(machine_name))

                if action=="confirm_restart":
                    machine.transition(to='wait')
                elif action=="confirm_reset":
                    machine.transition(to='start')
                elif action=="deny_restart":
                    machine.transition(to=machine.last_state)
                elif action=="deny_reset":
                    machine.transition(to=machine.last_state)
                else:
                    machine.transition(to=action)

                return not is_open, 0, 0

            elif no_n:

                return not is_open, 0, 0
            
            else:

                return True, 0, 0
        
        else:

            return False, 0, 0
        
    @app.callback(
        dash.Output('machine_threshold_input', "n_submit"),
        dash.Input('machine_threshold_input', "n_submit"),
        dash.State('machine_threshold_input', 'value'),
        dash.State('machines_detailed_tabs', 'active_tab'),
        prevent_initial_call=True
    )
    def update_threshold(n, threshold:float, active_tab:str):
        r"""
        Documentation here
        """
        try:
            threshold = float(threshold)
        except Exception as err:
            return 0
        machine_name = active_tab.split("-")[-1]
        machine = app.automation.get_machine(name=StringType(machine_name))
        machine_threshold = machine.threshold.value
        if hasattr(machine_threshold, "value"):

            machine_threshold = machine_threshold.value

        if threshold != machine_threshold:

            message = f'Do you want to change machine {machine_name} threshold from [{machine_threshold}] to: {threshold}?'
            dash.set_props("modal-update-body-attr-machine", {"children": message})
            dash.set_props("modal-update-attr-machine", {'is_open': True})

        return 0

    @app.callback(
        dash.Output('machine_interval_input', "n_submit"),
        dash.Input('machine_interval_input', "n_submit"),
        dash.State('machine_interval_input', 'value'),
        dash.State('machines_detailed_tabs', 'active_tab'),
        prevent_initial_call=True
    )
    def update_machine_interval(n, interval:float, active_tab:str):
        r"""
        Documentation here
        """
        try:
            interval = float(interval)
        except Exception as err:
            return 0
        machine_name = active_tab.split("-")[-1]
        machine = app.automation.get_machine(name=StringType(machine_name))

        if interval != machine.get_interval():

            message = f'Do you want to change machine {machine_name} interval from [{machine.get_interval()}] to: {interval}?'
            dash.set_props("modal-update-body-attr-machine", {"children": message})
            dash.set_props("modal-update-attr-machine", {'is_open': True})

        return 0

    @app.callback(
        dash.Output('buffer_size_input', "n_submit"),
        dash.Input('buffer_size_input', "n_submit"),
        dash.State('buffer_size_input', 'value'),
        dash.State('machines_detailed_tabs', 'active_tab'),
        prevent_initial_call=True
    )
    def update_buffer_size(n, buffer_size:int, active_tab:str):
        r"""
        Documentation here
        """
        try:
            buffer_size = int(buffer_size)
        except Exception as err:
            return 0
        machine_name = active_tab.split("-")[-1]
        machine = app.automation.get_machine(name=StringType(machine_name))

        if buffer_size != machine.buffer_size.value:

            message = f'Do you want to change machine {machine_name} buffer size from [{machine.buffer_size.value}] to: {buffer_size}?'
            dash.set_props("modal-update-body-attr-machine", {"children": message})
            dash.set_props("modal-update-attr-machine", {'is_open': True})

        return 0

    @app.callback(
        dash.Output('on_delay_input', "n_submit"),
        dash.Input('on_delay_input', "n_submit"),
        dash.State('on_delay_input', 'value'),
        dash.State('machines_detailed_tabs', 'active_tab'),
        prevent_initial_call=True
    )
    def update_on_delay(n, on_delay:int, active_tab:str):
        r"""
        Documentation here
        """
        try:
            on_delay = int(on_delay)
        except Exception as err:
            return 0
        machine_name = active_tab.split("-")[-1]
        machine = app.automation.get_machine(name=StringType(machine_name))

        if on_delay != machine.on_delay.value:

            message = f'Do you want to change machine {machine_name} on delay from [{machine.on_delay.value}] to: {on_delay}?'
            dash.set_props("modal-update-body-attr-machine", {"children": message})
            dash.set_props("modal-update-attr-machine", {'is_open': True})

        return 0
    
    @app.callback(
        dash.Output("modal-update-attr-machine", "is_open"), 
        dash.Output("update-attr-machine-yes", "n_clicks"),
        dash.Output("update-attr-machine-no", "n_clicks"),
        dash.Output('machine_threshold_input', "value"),
        dash.Output('machine_interval_input', "value"),
        dash.Output('buffer_size_input', "value"),
        dash.Output('on_delay_input', "value"),
        dash.Input("update-attr-machine-yes", "n_clicks"), 
        dash.Input("update-attr-machine-no", "n_clicks"),
        dash.State('machines_detailed_tabs', 'active_tab'),
        dash.State("modal-update-attr-machine", "is_open"),
        dash.State('machine_threshold_input', 'value'),
        dash.State('machine_interval_input', 'value'),
        dash.State('buffer_size_input', 'value'),
        dash.State('on_delay_input', 'value'),
        prevent_initial_call=True
    )
    def update_attr_machine_yes_or_no(
        yes_n, 
        no_n, 
        active_tab:str, 
        is_open, 
        threshold:float=None, 
        interval:int=None, 
        buffer_size:int=None, 
        on_delay:int=None
    ):
        r"""
        Documentation here
        """
        machine_name = active_tab.split("-")[-1]
        machine = app.automation.get_machine(name=StringType(machine_name))
        if yes_n:
            
            if threshold:
                
                if "leak detection" in machine.classification.value.lower():

                    if machine_name.lower()=="npw":

                        if threshold > 100:

                            threshold = 100

                        elif threshold < 0:

                            threshold = 0

                        machine.wavelet.threshold_iqr = threshold

                machine.threshold.value.value = threshold
                # UPDATE DB
                if app.automation.is_db_connected():
                    app.automation.machines_engine.put(name=StringType(machine_name), threshold=FloatType(threshold))
                dash.set_props("machine_threshold_input", {"placeholder": f"Current threshold {machine.threshold.value.value}"})

            elif interval:

                machine.set_interval(interval=IntegerType(interval))
                # UPDATE DB
                if app.automation.is_db_connected():
                    app.automation.machines_engine.put(name=StringType(machine_name), machine_interval=IntegerType(interval))
                dash.set_props("machine_interval_input", {"placeholder": f"Current machine interval {machine.get_interval()}"})
                
            elif buffer_size:

                machine.set_buffer_size(size=buffer_size)
                machine.transition(to="restart")
                if app.automation.is_db_connected():
                    app.automation.machines_engine.put(name=StringType(machine_name), buffer_size=IntegerType(buffer_size))
                machine.transition(to="wait")
                # UPDATE DB
                dash.set_props("buffer_size_input", {"placeholder": f"Current buffer size {machine.buffer_size.value}"})

            elif on_delay:

                machine.on_delay.value = on_delay
                if app.automation.is_db_connected():
                    app.automation.machines_engine.put(name=StringType(machine_name), on_delay=IntegerType(on_delay))
                # UPDATE DB
                dash.set_props("on_delay_input", {"placeholder": f"Current on delay {machine.on_delay.value}"})
            
        return not is_open, 0, 0, "", "", "", ""