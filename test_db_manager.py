from automation.managers import DBManager
from automation.dbmodels.core import SQLITE, POSTGRESQL

configs = {
    'name': 'app_db',
    'user': 'postgres',
    'password': 'postgres',
    'port': 5433,
    'host': '127.0.0.1'
}
db_manager = DBManager()
db_manager.init_database(dbtype=POSTGRESQL, **configs)