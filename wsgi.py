from sqlalchemy import inspect
from app import create_app
from app.extensions import db

app = create_app()
#with app.app_context():
#    inspector = inspect(db.engine)
#    print(inspector.get_table_names())
