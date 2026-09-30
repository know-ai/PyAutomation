from flask import request
from flask_restx import Namespace, Resource, fields, reqparse
from werkzeug.datastructures import FileStorage
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
from ..csv_profile import MAX_CSV_BYTES, GeospatialCsvError, GeospatialCsvProfile


ns = Namespace('Linear Referencing Geospatial', description='Linear referencing geospatial CRUD and interpolation')
app = PyAutomation()


create_point_model = api.model("create_linear_referencing_geospatial_model", {
    'segment_name': fields.String(required=True, description='Pipeline segment name'),
    'kp': fields.Float(required=True, description='Kilometer Post'),
    'latitude': fields.Float(required=True, description='Latitude (WGS84, Y)'),
    'longitude': fields.Float(required=True, description='Longitude (WGS84, X)'),
    'elevation': fields.Float(required=False, description='Elevation (meters above sea level)')
})

update_point_model = api.model("update_linear_referencing_geospatial_model", {
    'segment_name': fields.String(required=False, description='Pipeline segment name'),
    'kp': fields.Float(required=False, description='Kilometer Post'),
    'latitude': fields.Float(required=False, description='Latitude (WGS84, Y)'),
    'longitude': fields.Float(required=False, description='Longitude (WGS84, X)'),
    'elevation': fields.Float(required=False, description='Elevation (meters above sea level)')
})

interpolate_model = api.model("interpolate_linear_referencing_geospatial_model", {
    'segment_name': fields.String(required=True, description='Pipeline segment name'),
    'kp': fields.Float(required=True, description='Requested KP')
})


@ns.route('/')
class LinearReferencingCollection(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('segment_name', type=str, location='args', help='Optional segment name filter')

    @api.doc(security='apikey', description="Retrieves all points or points by segment.")
    @api.response(200, "Success")
    @Api.token_required(auth=True)
    @ns.expect(parser)
    def get(self):
        args = self.parser.parse_args()
        segment_name = args.get("segment_name")
        if segment_name:
            data = app.get_linear_referencing_geospatial_points_by_segment(segment_name=segment_name)
            return {"data": data}, 200
        return {"data": app.get_linear_referencing_geospatial_points()}, 200


@ns.route('/<int:point_id>')
@api.param('point_id', 'Linear referencing geospatial point ID')
class LinearReferencingPointResource(Resource):

    @api.doc(security='apikey', description="Retrieves one geospatial point by ID.")
    @api.response(200, "Success")
    @api.response(404, "Point not found")
    @Api.token_required(auth=True)
    def get(self, point_id:int):
        point = app.get_linear_referencing_geospatial_point(id=point_id)
        if point is None:
            return {"message": f"Linear referencing geospatial point {point_id} not found"}, 404
        return {"data": point}, 200

    @api.doc(security='apikey', description="Updates one geospatial point by ID.")
    @api.response(200, "Updated")
    @api.response(400, "Invalid payload")
    @api.response(404, "Point not found")
    @Api.token_required(auth=True)
    @ns.expect(update_point_model)
    def put(self, point_id:int):
        payload = api.payload or {}
        if not payload:
            return {"message": "No fields to update provided"}, 400
        data, message = app.update_linear_referencing_geospatial_point(id=point_id, **payload)
        if data is None:
            if "not found" in message.lower():
                return {"message": message}, 404
            return {"message": message}, 400
        return {"message": message, "data": data}, 200

    @api.doc(security='apikey', description="Deletes one geospatial point by ID.")
    @api.response(200, "Deleted")
    @api.response(404, "Point not found")
    @Api.token_required(auth=True)
    def delete(self, point_id:int):
        success, message = app.delete_linear_referencing_geospatial_point(id=point_id)
        if not success:
            if "not found" in message.lower():
                return {"message": message}, 404
            return {"message": message}, 400
        return {"message": message}, 200


@ns.route('/add')
class LinearReferencingCreateResource(Resource):

    @api.doc(security='apikey', description="Creates a new geospatial linear-referencing point.")
    @api.response(200, "Created")
    @api.response(400, "Creation error")
    @Api.token_required(auth=True)
    @ns.expect(create_point_model)
    def post(self):
        payload = api.payload or {}
        point, message = app.create_linear_referencing_geospatial(
            segment_name=payload.get("segment_name"),
            kp=payload.get("kp"),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            elevation=payload.get("elevation")
        )
        if point is None:
            return {"message": message}, 400
        return {"message": message, "data": point}, 200


@ns.route('/interpolate')
class LinearReferencingInterpolateResource(Resource):

    @api.doc(security='apikey', description="Retrieves interpolated geospatial coordinates by segment and KP.")
    @api.response(200, "Success")
    @api.response(400, "Interpolation error")
    @Api.token_required(auth=True)
    @ns.expect(interpolate_model)
    def post(self):
        payload = api.payload or {}
        data, message = app.get_geospatial_by_segment_and_kp(
            segment_name=payload.get("segment_name"),
            kp=payload.get("kp")
        )
        if data is None:
            return {"message": message}, 400
        return {"message": message, "data": data}, 200


bulk_import_parser = reqparse.RequestParser()
bulk_import_parser.add_argument(
    'file',
    type=FileStorage,
    location='files',
    required=True,
    help='CSV file to import'
)
bulk_import_parser.add_argument(
    'segment_name',
    type=str,
    location='form',
    required=False,
    help='Default segment name (used when the file does not include a segment_name column)'
)
bulk_import_parser.add_argument(
    'update_existing',
    type=str,
    location='form',
    required=False,
    default='true',
    help='Update existing points if they already exist (true/false, default: true)'
)


@ns.route('/bulk_import')
class LinearReferencingBulkImportResource(Resource):

    @api.doc(
        security='apikey',
        description="Imports a full profile from a CSV file. "
                    "Header must be exactly segment_name,kp,latitude,longitude."
    )
    @api.response(200, "Import processed")
    @api.response(400, "Invalid file or payload")
    @Api.token_required(auth=True)
    @ns.expect(bulk_import_parser)
    def post(self):
        if "file" not in request.files:
            return {"message": "file is required (CSV)"}, 400

        upload = request.files["file"]
        filename = (upload.filename or "").strip()
        if not filename.lower().endswith(".csv"):
            return {"message": "Only .csv files are supported"}, 400

        default_segment_name = request.form.get("segment_name")
        update_existing_raw = (request.form.get("update_existing", "true") or "true").strip().lower()
        update_existing = update_existing_raw in ("1", "true", "yes", "y")

        raw = upload.stream.read(MAX_CSV_BYTES + 1)
        if len(raw) > MAX_CSV_BYTES:
            return {"message": "File exceeds 1 MB"}, 400

        try:
            rows = GeospatialCsvProfile().parse(raw)
        except GeospatialCsvError as err:
            return {"message": str(err)}, 400

        result = app.import_linear_referencing_profile(
            rows=rows,
            default_segment_name=default_segment_name,
            update_existing=update_existing
        )
        if not isinstance(result, dict) or not result.get("success"):
            errors = (result or {}).get("errors") if isinstance(result, dict) else None
            message = "; ".join(errors) if errors else "Import rejected"
            return {"message": message, "data": result}, 400
        return {"data": result}, 200
