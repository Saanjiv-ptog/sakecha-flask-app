# models.py
# models.py
from app import db # Assuming your db object is in app.py
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash # For password hashing
import datetime # Import for Date and Time types

class Franchisee(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False) # Store hashed passwords
    name = db.Column(db.String(120), nullable=False) # Added back from initial prompt
    location = db.Column(db.String(120), nullable=False) # Added back from initial prompt
    is_admin = db.Column(db.Boolean, default=False) # <--- This is the line to add

    # Relationships from the original prompt
    daily_reports = db.relationship('DailyReport', backref='franchisee', lazy=True)
    reorder_requests = db.relationship('IngredientReorder', backref='franchisee', lazy=True)
    team_attendances = db.relationship('TeamAttendance', backref='franchisee', lazy=True)


    def __repr__(self):
        return f"Franchisee('{self.email}')"

    def get_id(self):
        return str(self.id)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class DailyReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    franchisee_id = db.Column(db.Integer, db.ForeignKey('franchisee.id'), nullable=False)
    report_date = db.Column(db.Date, nullable=False)
    total_sales = db.Column(db.Float, nullable=False)
    items_sold = db.Column(db.Text, nullable=True)
    expenses = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<DailyReport {self.report_date} - {self.franchisee.email}>'

class IngredientReorder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    franchisee_id = db.Column(db.Integer, db.ForeignKey('franchisee.id'), nullable=False)
    request_date = db.Column(db.Date, nullable=False)
    ingredient_name = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), default='Pending') # e.g., Pending, Approved, Rejected

    def __repr__(self):
        return f'<IngredientReorder {self.ingredient_name} - {self.quantity}>'

class TeamAttendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    franchisee_id = db.Column(db.Integer, db.ForeignKey('franchisee.id'), nullable=False)
    attendance_date = db.Column(db.Date, nullable=False)
    staff_name = db.Column(db.String(120), nullable=False)
    time_in = db.Column(db.Time, nullable=True)
    time_out = db.Column(db.Time, nullable=True)
    
    def __repr__(self):
        return f'<TeamAttendance {self.staff_name} on {self.attendance_date}>'
