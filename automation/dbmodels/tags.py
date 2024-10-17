from peewee import CharField, BooleanField, FloatField, ForeignKeyField, IntegerField, fn, TimestampField, BooleanField
from .core import BaseModel
from datetime import datetime


class Manufacturer(BaseModel):

    name = CharField(unique=True)

    @classmethod
    def create(cls, name:str)-> dict:
        r"""

        """
        if not cls.name_exist(name):

            query = cls(name=name)
            query.save()
            
            return query

    @classmethod
    def read_by_name(cls, name:str)->bool:
        r"""
        Get instance by its a name

        **Parameters**

        * **name:** (str) Variable name

        **Returns**

        * **bool:** If True, name exist into database 
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return query
        
        return None

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""
        Verify is a name exist into database

        **Parameters**

        * **name:** (str) Variable name

        **Returns**

        * **bool:** If True, name exist into database 
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False

    def serialize(self)-> dict:
        r"""
        Serialize database record to a jsonable object
        """

        return {
            "id": self.id,
            "name": self.name
        }
    

class Segment(BaseModel):

    name = CharField(unique=True)
    manufacturer= ForeignKeyField(Manufacturer, backref='segments', on_delete='CASCADE')

    @classmethod
    def create(cls, name:str, manufacturer:str)-> dict:
        r"""
        """
        if not cls.name_exist(name):

            if Manufacturer.name_exist(name=manufacturer):
                
                manufacturer_obj = Manufacturer.read_by_name(name=manufacturer)
            
            else:
                
                manufacturer_obj = Manufacturer.create(name=manufacturer)
            
            query = cls(name=name, manufacturer=manufacturer_obj)
            query.save()
            
            return query

    @classmethod
    def read_by_name(cls, name:str)->bool:
        r"""
 
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return query
        
        return None

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""

        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False

    def serialize(self)-> dict:
        r"""
        Serialize database record to a jsonable object
        """

        return {
            "id": self.id,
            "name": self.name,
            "manufacturer": self.manufacturer.serialize()
        }


class Variables(BaseModel):

    name = CharField(unique=True)

    @classmethod
    def create(cls, name:str)-> dict:
        r"""
        You can use Model.create() to create a new model instance. This method accepts keyword arguments, where the keys correspond 
        to the names of the model's fields. A new instance is returned and a row is added to the table.

        ```python
        >>> Variables.create(name='Pressure')
        {
            'message': (str)
            'data': (dict) {
                'name': 'pressure'
            }
        }
        ```
        
        This will INSERT a new row into the database. The primary key will automatically be retrieved and stored on the model instance.

        **Parameters**

        * **name:** (str), Industrial protocol name

        **Returns**

        * **result:** (dict) --> {'message': (str), 'data': (dict) row serialized}

        """
        result = dict()
        data = dict()

        if not cls.name_exist(name):

            query = cls(name=name)
            query.save()
            
            message = f"{name} variable created successfully"
            data.update(query.serialize())

            result.update(
                {
                    'message': message, 
                    'data': data
                }
            )
            return result

        message = f"{name} variable is already into database"
        result.update(
            {
                'message': message, 
                'data': data
            }
        )
        return result

    @classmethod
    def read_by_name(cls, name:str)->bool:
        r"""
        Get instance by its a name

        **Parameters**

        * **name:** (str) Variable name

        **Returns**

        * **bool:** If True, name exist into database 
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return query
        
        return None

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""
        Verify is a name exist into database

        **Parameters**

        * **name:** (str) Variable name

        **Returns**

        * **bool:** If True, name exist into database 
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False

    def serialize(self)-> dict:
        r"""
        Serialize database record to a jsonable object
        """

        return {
            "id": self.id,
            "name": self.name
        }


class Units(BaseModel):

    name = CharField(unique=True)
    unit = CharField(unique=True)
    variable_id = ForeignKeyField(Variables, backref='units', on_delete='CASCADE')

    @classmethod
    def create(cls, name:str, unit:str, variable:str)-> dict:
        r"""
        You can use Model.create() to create a new model instance. This method accepts keyword arguments, where the keys correspond 
        to the names of the model's fields. A new instance is returned and a row is added to the table.

        ```python
        >>> Variables.create(name='Pa', variable='Pressure')
        {
            'message': (str)
            'data': (dict) {
                'id': 1,
                'name': 'Pa',
                'variable': 'pressure'
            }
        }
        ```
        
        This will INSERT a new row into the database. The primary key will automatically be retrieved and stored on the model instance.

        **Parameters**

        * **name:** (str), Industrial protocol name

        **Returns**

        * **result:** (dict) --> {'message': (str), 'data': (dict) row serialized}

        """
        result = dict()
        data = dict()
        name = name

        if not cls.name_exist(name):

            query_variable = Variables.read_by_name(variable)
            
            if query_variable is not None:

                variable_id = query_variable

                query = cls(name=name, unit=unit, variable_id=variable_id)
                query.save()
                
                message = f"{name} unit created successfully"
                data.update(query.serialize())

                result.update(
                    {
                        'message': message, 
                        'data': data
                    }
                )
                return result


            message = f"{variable} variable not exist into database"

            result.update(
                {
                    'message': message, 
                    'data': data
                }
            )
            return result

        message = f"{name} unit is already into database"
        result.update(
            {
                'message': message, 
                'data': data
            }
        )
        return result

    @classmethod
    def read_by_name(cls, name:str)->bool:
        r"""
        Get instance by its a name

        **Parameters**

        * **name:** (str) Variable name

        **Returns**

        * **bool:** If True, name exist into database 
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return query.serialize()
        
        return None

    @classmethod
    def read_by_unit(cls, unit:str)->bool:
        r"""
        Get instance by its a name

        **Parameters**

        * **name:** (str) Variable name

        **Returns**

        * **bool:** If True, name exist into database 
        """
        query = cls.get_or_none(unit=unit)
        
        if query is not None:

            return query
        
        return None
    
    @classmethod
    def read_by_unit(cls, unit:str)->bool:
        r"""
        Get instance by its a name

        **Parameters**

        * **name:** (str) Variable name

        **Returns**

        * **bool:** If True, name exist into database 
        """
        query = cls.get_or_none(unit=unit)
        
        if query is not None:

            return query
        
        return None

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""
        Verify is a name exist into database

        **Parameters**

        * **name:** (str) Variable name

        **Returns**

        * **bool:** If True, name exist into database 
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False

    def serialize(self)-> dict:
        r"""
        Serialize database record to a jsonable object
        """

        return {
            "id": self.id,
            "name": self.name,
            "variable": self.variable_id.name,
            "unit": self.unit
        }


class DataTypes(BaseModel):

    name = CharField(unique=True)

    @classmethod
    def create(cls, name:str)-> dict:
        r"""
        You can use Model.create() to create a new model instance. This method accepts keyword arguments, where the keys correspond 
        to the names of the model's fields. A new instance is returned and a row is added to the table.

        ```python
        >>> Variables.create(name='Pressure')
        {
            'message': (str)
            'data': (dict) {
                'name': 'pressure'
            }
        }
        ```
        
        This will INSERT a new row into the database. The primary key will automatically be retrieved and stored on the model instance.

        **Parameters**

        * **name:** (str), Industrial protocol name

        **Returns**

        * **result:** (dict) --> {'message': (str), 'data': (dict) row serialized}

        """
        result = dict()
        data = dict()

        if not cls.name_exist(name):

            query = cls(name=name)
            query.save()
            
            message = f"{name} DataType created successfully"
            data.update(query.serialize())

            result.update(
                {
                    'message': message, 
                    'data': data
                }
            )
            return result

        message = f"{name} DataType is already into database"
        result.update(
            {
                'message': message, 
                'data': data
            }
        )
        return result

    @classmethod
    def read_by_name(cls, name:str)->bool:
        r"""
        Get instance by its a name

        **Parameters**

        * **name:** (str) Variable name

        **Returns**

        * **bool:** If True, name exist into database 
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return query
        
        return None

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""
        Verify is a name exist into database

        **Parameters**

        * **name:** (str) Variable name

        **Returns**

        * **bool:** If True, name exist into database 
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False

    def serialize(self)-> dict:
        r"""
        Serialize database record to a jsonable object
        """

        return {
            "id": self.id,
            "name": self.name
        }


class Tags(BaseModel):

    identifier = CharField(unique=True)
    name = CharField(unique=True)
    unit = ForeignKeyField(Units, backref='tags')
    data_type = ForeignKeyField(DataTypes, backref='tags')
    segment = ForeignKeyField(Segment, backref='tags', null=True)
    description = CharField(null=True, max_length=256)
    display_name = CharField(unique=True)
    display_unit = ForeignKeyField(Units)
    opcua_address = CharField(null=True)
    node_namespace = CharField(null=True)
    scan_time = IntegerField(null=True)
    dead_band = FloatField(null=True)
    active = BooleanField(default=True)
    process_filter = BooleanField(default=False)
    gaussian_filter = BooleanField(default=False)
    out_of_range_detection = BooleanField(default=False)
    outlier_detection = BooleanField(default=False)
    frozen_data_detection = BooleanField(default=False)

    @classmethod
    def create(
        cls, 
        id:str,
        name:str, 
        unit:str,
        data_type:str,
        description:str,
        display_name:str,
        display_unit:str,
        opcua_address:str="",
        node_namespace:str="",
        segment:str="",
        manufacturer:str="",
        scan_time:int=0,
        dead_band:float=0.0,
        active:bool=True,
        process_filter:bool=False,
        gaussian_filter:bool=False,
        out_of_range_detection:bool=False,
        outlier_detection:bool=False,
        frozen_data_detection:bool=False
        ):
        r"""
        Documentation here
        """
        result = dict()
        message = f"{name} already exist into database"
        data = dict()
        _unit = Units.read_by_unit(unit=unit)
        _display_unit = Units.read_by_unit(unit=display_unit)
        _data_type = DataTypes.read_by_name(name=data_type)
        
        if not cls.name_exist(name):

            if not cls.display_name_exist(name):
                
                if _unit is not None and _display_unit is not None:

                    if _data_type is not None:

                        if segment and manufacturer:

                            if Segment.name_exist(name=segment):

                                segment_obj = Segment.read_by_name(name=segment)
                            
                            else:

                                segment_obj = Segment.create(name=segment, manufacturer=manufacturer)
                            
                            query = cls(
                                identifier=id,
                                name=name, 
                                unit=_unit,
                                data_type=_data_type,
                                description=description,
                                display_name=display_name,
                                display_unit=_display_unit,
                                opcua_address=opcua_address,
                                node_namespace=node_namespace,
                                scan_time=scan_time,
                                dead_band=dead_band,
                                active=active,
                                process_filter=process_filter,
                                gaussian_filter=gaussian_filter,
                                out_of_range_detection=out_of_range_detection,
                                outlier_detection=outlier_detection,
                                frozen_data_detection=frozen_data_detection,
                                segment=segment_obj
                                )
                        else:
                            query = cls(
                                identifier=id,
                                name=name, 
                                unit=_unit,
                                data_type=_data_type,
                                description=description,
                                display_name=display_name,
                                display_unit=_display_unit,
                                opcua_address=opcua_address,
                                node_namespace=node_namespace,
                                scan_time=scan_time,
                                dead_band=dead_band,
                                active=active,
                                process_filter=process_filter,
                                gaussian_filter=gaussian_filter,
                                out_of_range_detection=out_of_range_detection,
                                outlier_detection=outlier_detection,
                                frozen_data_detection=frozen_data_detection
                                )
                        query.save()
                        message = f"{name} tag created successfully"
                        
                        data.update(query.serialize())

                        result.update(
                            {
                                'message': message, 
                                'data': data
                            }
                        )
                        
                        return result

                    message = f"{data_type} data type not exist into database"
                    result.update(
                        {
                            'message': message, 
                            'data': data
                        }
                    )
                    return result

                message = f"{unit} unit not exist into database"
                result.update(
                    {
                        'message': message, 
                        'data': data
                    }
                )
                return result
        
        else:

            if _unit is not None and _display_unit is not None:

                    if _data_type is not None:
                        tag, _ = cls.get_or_create(name=name)
                        payload = {
                            "unit":_unit,
                            "data_type":_data_type,
                            "description":description,
                            "display_name":display_name,
                            "display_unit":_display_unit,
                            "opcua_address":opcua_address,
                            "node_namespace":node_namespace,
                            "scan_time":scan_time,
                            "dead_band":dead_band,
                            "active": True
                        }
                        cls.put(id=tag.id, **payload)

                    message = f"{data_type} data type not exist into database"
                    result.update(
                        {
                            'message': message, 
                            'data': data
                        }
                    )
                    return result
            
            message = f"{unit} unit not exist into database"
            result.update(
                {
                    'message': message, 
                    'data': data
                }
            )
            return result

        result.update(
            {
                'message': message, 
                'data': data
            }
        )
        return result

    @classmethod
    def put(cls, id:int, **fields)-> dict:
        r""""
        Update a single record

        Once a model instance has a primary key, you UPDATE a field by its id. 
        The model's primary key will not change:
        """ 
             
        if cls.id_exists(id):
            
            if "unit" in fields:

                unit = fields["unit"]
                if isinstance(unit, str):
                    query = Units.read_by_unit(unit=unit)
                    if query:

                        fields["unit"] = query

            if "display_unit" in fields:

                display_unit = fields["display_unit"]
                if isinstance(display_unit, str):
                    query = Units.read_by_unit(unit=display_unit)
                    if query:

                        fields["display_unit"] = query

            if "data_type" in fields:

                data_type = fields["data_type"]
                if isinstance(data_type, str):
                    query = DataTypes.read_by_name(name=data_type)
                    if query:

                        fields["data_type"] = query

            query = cls.update(**fields).where(cls.id == id)
            query.execute()
            return query

    @classmethod
    def read_by_name(cls, name):
        r"""
        Documentation here
        """
        return cls.get_or_none(name=name)

    @classmethod
    def read_by_names(cls, names):
        r"""
        Documentation here
        """
        query = cls.select().where(cls.name in names)
        return query

    @classmethod
    def name_exist(cls, name):
        r"""
        Documentation here
        """
        tag = cls.get_or_none(name=name)
        if tag is not None:

            return True
        
        return False
    
    @classmethod
    def display_name_exist(cls, name):
        r"""
        Documentation here
        """
        tag = cls.get_or_none(name=name)
        if tag is not None:

            return True
        
        return False

    def get_machines(self):

        return self.machines

    def serialize(self):
        r"""
        Documentation here
        """
        segment = ""
        manufacturer = ""
        if self.segment:

            segment = self.segment.serialize()
            manufacturer = segment["manufacturer"]["name"]
            segment = segment["name"]

        return {
            'id': self.identifier,
            'name': self.name,
            'unit': self.unit.unit,
            'data_type': self.data_type.name,
            'description': self.description,
            'display_name': self.display_name,
            'display_unit': self.display_unit.unit,
            'opcua_address': self.opcua_address,
            'node_namespace': self.node_namespace,
            'scan_time': self.scan_time,
            'dead_band': self.dead_band,
            'variable': self.unit.variable_id.name,
            'active': self.active,
            'process_filter': self.process_filter,
            'gaussian_filter': self.gaussian_filter,
            'out_of_range_detection': self.out_of_range_detection,
            'frozen_data_detection': self.frozen_data_detection,
            'outlier_detection': self.outlier_detection,
            'segment': segment,
            "manufacturer": manufacturer
        }


class TagValue(BaseModel):

    tag = ForeignKeyField(Tags, backref='values')
    unit = ForeignKeyField(Units, backref='values')
    value = FloatField()
    timestamp = TimestampField(utc=True)

    @classmethod
    def create(
        cls, 
        tag:Tags,
        value:float,
        timestamp:datetime,
        unit=Units):
        r"""
        Documentation here
        """
        query = cls(
            tag=tag,
            value=value, 
            timestamp=timestamp,
            unit=unit
            )
        query.save()