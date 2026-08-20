from peewee import CharField, BooleanField, FloatField, ForeignKeyField, IntegerField, TimestampField, BooleanField
from ..timebase import TAGVALUE_TIMESTAMP_RESOLUTION
from .core import BaseModel
from datetime import datetime


class Manufacturer(BaseModel):
    r"""
    Database model for Device Manufacturers.
    """
    
    name = CharField(unique=True)

    @classmethod
    def create(cls, name:str)-> dict:
        r"""
        Creates a new Manufacturer record.

        **Parameters:**

        * **name** (str): Manufacturer name.
        """
        if not cls.name_exist(name):

            query = cls(name=name)
            query.save()
            
            return query

    @classmethod
    def read_by_name(cls, name:str)->bool:
        r"""
        Retrieves a Manufacturer by name.
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return query
        
        return None

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""
        Checks if a manufacturer name exists.
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False

    def serialize(self)-> dict:
        r"""
        Serializes the record.
        """

        return {
            "id": self.id,
            "name": self.name
        }
    

class Segment(BaseModel):
    r"""
    Database model for Network/Plant Segments.
    """
    
    name = CharField()
    manufacturer = ForeignKeyField(Manufacturer, backref='segments')

    @classmethod
    def create(cls, name:str, manufacturer:str)-> dict:
        r"""
        Creates a new Segment record.

        **Parameters:**

        * **name** (str): Segment name.
        * **manufacturer** (str): Associated manufacturer name.
        """
        if Manufacturer.name_exist(name=manufacturer):
            
            manufacturer_obj = Manufacturer.read_by_name(name=manufacturer)
        
        else:
            
            manufacturer_obj = Manufacturer.create(name=manufacturer)

        segment_obj = Segment.select().where(Segment.name == name, Segment.manufacturer == manufacturer_obj).exists()
        
        if not segment_obj:
            query = cls(name=name, manufacturer=manufacturer_obj)
            query.save()  
            return query
        
        return Segment.read_by_name(name=name)

    @classmethod
    def read_by_name(cls, name:str)->bool:
        r"""
        Retrieves a Segment by name.
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return query
        
        return None

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""
        Checks if a segment name exists.
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False

    def serialize(self)-> dict:
        r"""
        Serializes the record.
        """

        return {
            "id": self.id,
            "name": self.name,
            "manufacturer": self.manufacturer.serialize()
        }


class Variables(BaseModel):
    r"""
    Database model for Physical Variables (e.g., Pressure, Temperature).
    """
    
    name = CharField(unique=True)

    @classmethod
    def create(cls, name:str)-> dict:
        r"""
        Creates a new Variable record.

        **Parameters:**

        * **name** (str): Variable name.
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
        Retrieves a Variable by name.
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return query
        
        return None

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""
        Checks if a variable name exists.
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False

    def serialize(self)-> dict:
        r"""
        Serializes the record.
        """

        return {
            "id": self.id,
            "name": self.name
        }


class Units(BaseModel):
    r"""
    Database model for Measurement Units.
    """
    
    name = CharField(unique=True)
    unit = CharField(unique=True)
    variable_id = ForeignKeyField(Variables, backref='units', on_delete='CASCADE')

    @classmethod
    def create(cls, name:str, unit:str, variable:str)-> dict:
        r"""
        Creates a new Unit record.

        **Parameters:**

        * **name** (str): Unit name (e.g., 'Pascal').
        * **unit** (str): Symbol (e.g., 'Pa').
        * **variable** (str): Associated variable name.
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
        Retrieves a Unit by name.
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return query.serialize()
        
        return None

    @classmethod
    def read_by_unit(cls, unit:str)->bool:
        r"""
        Retrieves a Unit by its symbol.
        """
        query = cls.get_or_none(unit=unit)
        
        if query is not None:

            return query
        
        return None

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""
        Checks if a unit name exists.
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False

    def serialize(self)-> dict:
        r"""
        Serializes the record.
        """

        return {
            "id": self.id,
            "name": self.name,
            "variable": self.variable_id.name,
            "unit": self.unit
        }


class DataTypes(BaseModel):
    r"""
    Database model for Data Types.
    """
    
    name = CharField(unique=True)

    @classmethod
    def create(cls, name:str)-> dict:
        r"""
        Creates a new Data Type record.

        **Parameters:**

        * **name** (str): Data type name (e.g., 'float').
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
        Retrieves a Data Type by name.
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return query
        
        return None

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""
        Checks if a data type name exists.
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False

    def serialize(self)-> dict:
        r"""
        Serializes the record.
        """

        return {
            "id": self.id,
            "name": self.name
        }


class Tags(BaseModel):
    r"""
    Database model for Process Tags.
    """
    
    identifier = CharField(unique=True)
    name = CharField(unique=True)
    area = CharField(max_length=64, null=True, index=True)
    owner_node = CharField(max_length=64, null=True, index=True)
    unit = ForeignKeyField(Units, backref='tags')
    data_type = ForeignKeyField(DataTypes, backref='tags')
    segment = ForeignKeyField(Segment, backref='tags', null=True)
    description = CharField(null=True, max_length=256)
    display_name = CharField(unique=True)
    display_unit = ForeignKeyField(Units)
    opcua_address = CharField(null=True)
    opcua_client_name = CharField(null=True)
    node_namespace = CharField(null=True)
    scan_time = IntegerField(null=True)
    dead_band = FloatField(null=True)
    kp = FloatField(null=True)
    active = BooleanField(default=True)
    out_of_range_detection = BooleanField(default=False)
    outlier_detection = BooleanField(default=False)
    frozen_data_detection = BooleanField(default=False)
    filter_enabled = BooleanField(default=False)
    filter_wavelet = CharField(max_length=16, default="db4")
    filter_level = IntegerField(default=4)
    filter_threshold_factor = FloatField(default=3.0)
    filter_persist = BooleanField(default=False)

    class Meta:
        indexes = (
            (("area", "name"), False),
            (("owner_node", "name"), False),
        )

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
        opcua_client_name:str=None,
        node_namespace:str="",
        segment:str="",
        manufacturer:str="",
        scan_time:int=0,
        dead_band:float=0.0,
        kp:float=None,
        active:bool=True,
        filter_enabled:bool=False,
        filter_wavelet:str="db4",
        filter_level:int=4,
        filter_threshold_factor:float=3.0,
        filter_persist:bool=False,
        out_of_range_detection:bool=False,
        outlier_detection:bool=False,
        frozen_data_detection:bool=False,
        area:str=None,
        owner_node:str=None
        ):
        r"""
        Creates a new Tag configuration record.

        **Parameters:**

        * **id** (str): Unique identifier.
        * **name** (str): Tag name.
        * **unit** (str): Engineering unit.
        * **data_type** (str): Data type.
        * **description** (str): Description.
        * **display_name** (str): Display alias.
        * **display_unit** (str): Display unit.
        * **opcua_address** (str, optional): OPC UA server address.
        * **node_namespace** (str, optional): OPC UA node ID.
        * **segment** (str, optional): Network segment.
        * **manufacturer** (str, optional): Device manufacturer.
        * **scan_time** (int, optional): Polling interval.
        * **dead_band** (float, optional): Deadband value.
        * **active** (bool, optional): Active status.
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

                            segment_obj = Segment.create(name=segment, manufacturer=manufacturer)

                            if not segment_obj:

                                result.update(
                                    {
                                        'message': f"Duplicated {manufacturer}->{segment}", 
                                        'data': data
                                    }
                                )

                                return result

                            
                            query = cls(
                                identifier=id,
                                name=name, 
                                unit=_unit,
                                data_type=_data_type,
                                description=description,
                                display_name=display_name,
                                display_unit=_display_unit,
                                opcua_address=opcua_address,
                                opcua_client_name=opcua_client_name,
                                node_namespace=node_namespace,
                                scan_time=scan_time,
                                dead_band=dead_band,
                                kp=kp,
                                active=active,
                                filter_enabled=filter_enabled,
                                filter_wavelet=filter_wavelet,
                                filter_level=filter_level,
                                filter_threshold_factor=filter_threshold_factor,
                                filter_persist=filter_persist,
                                out_of_range_detection=out_of_range_detection,
                                outlier_detection=outlier_detection,
                                frozen_data_detection=frozen_data_detection,
                                segment=segment_obj,
                                area=area,
                                owner_node=owner_node
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
                                opcua_client_name=opcua_client_name,
                                node_namespace=node_namespace,
                                scan_time=scan_time,
                                dead_band=dead_band,
                                kp=kp,
                                active=active,
                                filter_enabled=filter_enabled,
                                filter_wavelet=filter_wavelet,
                                filter_level=filter_level,
                                filter_threshold_factor=filter_threshold_factor,
                                filter_persist=filter_persist,
                                out_of_range_detection=out_of_range_detection,
                                outlier_detection=outlier_detection,
                                frozen_data_detection=frozen_data_detection,
                                area=area,
                                owner_node=owner_node
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
                            "opcua_client_name":opcua_client_name,
                            "node_namespace":node_namespace,
                            "scan_time":scan_time,
                            "dead_band":dead_band,
                            "kp":kp,
                            "active": True,
                            "area": area,
                            "owner_node": owner_node
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
        r"""
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

            if "segment" in fields:

                if "manufacturer" in fields:

                    segment = fields["segment"]
                    manufacturer = fields.pop("manufacturer")
                    if isinstance(segment, str) and isinstance(manufacturer, str):
                        manufacturer_obj = Manufacturer.get_or_none(name=manufacturer)
                        if manufacturer_obj:
                            query = Segment.get_or_none((Segment.name == segment) & (Segment.manufacturer == manufacturer_obj))

                            if query:
                                
                                fields["segment"] = query
            
            query = cls.update(**fields).where(cls.id == id)
            query.execute()
            return query

    @classmethod
    def read_by_name(cls, name):
        r"""
        Retrieves a Tag by name.
        """
        return cls.get_or_none(name=name)

    @classmethod
    def read_by_names(cls, names):
        r"""
        Retrieves multiple Tags by name.
        """
        query = cls.select().where(cls.name in names)
        return query

    @classmethod
    def name_exist(cls, name):
        r"""
        Checks if a tag name exists.
        """
        tag = cls.get_or_none(name=name)
        if tag is not None:

            return True
        
        return False
    
    @classmethod
    def display_name_exist(cls, name):
        r"""
        Checks if a display name exists.
        """
        tag = cls.get_or_none(name=name)
        if tag is not None:

            return True
        
        return False

    def get_machines(self):
        r"""
        Returns machines associated with this tag.
        """
        return self.machines

    def serialize(self):
        r"""
        Serializes the tag record.
        """
        segment = ""
        manufacturer = ""
        if self.segment:

            segment = self.segment.serialize()
            manufacturer = segment["manufacturer"]["name"]
            segment = segment["name"]

        # Resolver opcua_address desde opcua_client_name si está disponible
        resolved_opcua_address = self.opcua_address if hasattr(self, 'opcua_address') else None

        return {
            'id': self.identifier,
            'name': self.name,
            'unit': self.unit.unit,
            'data_type': self.data_type.name,
            'description': self.description,
            'display_name': self.display_name,
            'display_unit': self.display_unit.unit,
            'opcua_address': resolved_opcua_address,
            'opcua_client_name': self.opcua_client_name,
            'node_namespace': self.node_namespace,
            'scan_time': self.scan_time,
            'dead_band': self.dead_band,
            'kp': self.kp,
            'variable': self.unit.variable_id.name,
            'active': self.active,
            'filter_enabled': getattr(self, "filter_enabled", False),
            'filter_wavelet': getattr(self, "filter_wavelet", "db4"),
            'filter_level': getattr(self, "filter_level", 4),
            'filter_threshold_factor': getattr(self, "filter_threshold_factor", 3.0),
            'filter_persist': getattr(self, "filter_persist", False),
            'out_of_range_detection': self.out_of_range_detection,
            'frozen_data_detection': self.frozen_data_detection,
            'outlier_detection': self.outlier_detection,
            'area': self.area,
            'owner_node': self.owner_node,
            'segment': segment,
            "manufacturer": manufacturer
        }


class TagValue(BaseModel):
    r"""
    Database model for Historical Tag Values.
    """
    
    tag = ForeignKeyField(Tags, backref='values')
    unit = ForeignKeyField(Units, backref='values')
    value = FloatField()
    timestamp = TimestampField(utc=True, resolution=TAGVALUE_TIMESTAMP_RESOLUTION)
    area = CharField(max_length=64, null=True, index=True)
    sample_uuid = CharField(max_length=255, unique=True, null=True)

    class Meta:
        indexes = (
            (('timestamp',), False),
            (('area', 'timestamp'), False),
            # Exact-once: one sample per tag per millisecond instant
            (('tag', 'timestamp'), True),
        )

    @classmethod
    def create(
        cls, 
        tag:Tags,
        value:float,
        timestamp:datetime,
        unit=Units,
        area:str=None):
        r"""
        Creates a new historical value record.

        **Parameters:**

        * **tag** (Tags): Tag object.
        * **value** (float): Measured value.
        * **timestamp** (datetime): Time of measurement.
        * **unit** (Units): Measurement unit.
        """
        query = cls(
            tag=tag,
            value=value, 
            timestamp=timestamp,
            unit=unit,
            area=area
            )
        query.save()