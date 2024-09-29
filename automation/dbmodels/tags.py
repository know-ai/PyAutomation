from peewee import CharField, DateTimeField, FloatField, ForeignKeyField, IntegerField, fn
from .core import BaseModel
from datetime import datetime


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

            return query.serialize()
        
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

                variable_id = query_variable['id']

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

            return query.serialize()
        
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

            return query.serialize()
        
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
    description = CharField(null=True, max_length=256)
    display_name = CharField()
    display_unit = ForeignKeyField(Units)
    opcua_address = CharField(null=True)
    node_namespace = CharField(null=True)
    scan_time = IntegerField(null=True)
    dead_band = FloatField(null=True)

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
        scan_time:int=0,
        dead_band:float=0.0
        ):
        r"""
        Documentation here
        """
        result = dict()
        message = f"{name} already exist into database"
        data = dict()
        
        if not cls.name_exist(name):

            _unit = Units.read_by_unit(unit=unit)
            _display_unit = Units.read_by_unit(unit=display_unit)
            _data_type = DataTypes.read_by_name(name=data_type)
            
            if _unit is not None and _display_unit is not None:

                if _data_type is not None:
            
                    query = cls(
                        identifier=id,
                        name=name, 
                        unit=_unit['id'],
                        data_type=_data_type['id'],
                        description=description,
                        display_name=display_name,
                        display_unit=_display_unit['id'],
                        opcua_address=opcua_address,
                        node_namespace=node_namespace,
                        scan_time=scan_time,
                        dead_band=dead_band
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
                query = Units.read_by_unit(unit=unit)
                if query:

                    fields["unit"] = query["id"]

            if "display_unit" in fields:

                display_unit = fields["display_unit"]
                query = Units.read_by_unit(unit=display_unit)
                if query:

                    fields["display_unit"] = query["id"]

            if "data_type" in fields:

                data_type = fields["data_type"]
                query = DataTypes.read_by_name(name=data_type)
                if query:

                    fields["data_type"] = query["id"]

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

    def serialize(self):
        r"""
        Documentation here
        """
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
            'variable': self.unit.variable_id.name
        }


class TagValue(BaseModel):

    tag = ForeignKeyField(Tags, backref='values')
    value = FloatField()
    timestamp = DateTimeField()

    @classmethod
    def create(
        cls, 
        tag:str,
        value:float,
        timestamp:datetime):
        r"""
        Documentation here
        """
        query = cls(
            tag=tag,
            value=value, 
            timestamp=timestamp
            )
        query.save()