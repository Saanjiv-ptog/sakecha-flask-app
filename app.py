from flask import Flask, render_template, request, redirect, url_for, flash, make_response # make_response added here
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import pdfkit # NEW: Import pdfkit
from calendar import monthrange # NEW: Import monthrange for PDF generation logic


# For Flask-Bootstrap
from flask_bootstrap import Bootstrap

# For PDF generation (Note: pdfkit and wkhtmltopdf need external setup)
# import pdfkit # This was already commented out, but we need it active now!


# --- Flask App Configuration ---
app = Flask(__name__)

# This generates a strong, random key automatically.
app.config['SECRET_KEY'] = os.urandom(24).hex()

# --- IMPORTANT DATABASE CONFIGURATION ---
# Using your PostgreSQL URI
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:SKN04JB%@localhost/sakecha_d'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Initialize Extensions ---
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Assuming 'login' is the endpoint name of your login route
bootstrap = Bootstrap(app) # Initialize Flask-Bootstrap

# --- NEW: PDFKit Configuration ---
# IMPORTANT: Adjust this path to where wkhtmltopdf.exe is located on your system.
# The installer usually puts it in 'C:\Program Files\wkhtmltopdf\bin\' on Windows.
WKHTMLTOPDF_PATH = os.environ.get('WKHTMLTOPDF_PATH', None)

if WKHTMLTOPDF_PATH is None:
    # Try common default paths if not set as environment variable
    if os.name == 'nt': # Windows
        WKHTMLTOPDF_PATH = 'C:\\Program Files\\wkhtmltopdf\\bin\\wkhtmltopdf.exe'
    elif os.name == 'posix': # Linux/macOS
        WKHTMLTOPDF_PATH = '/usr/local/bin/wkhtmltopdf'
        if not os.path.exists(WKHTMLTOPDF_PATH):
             WKHTMLTOPDF_PATH = '/usr/bin/wkhtmltopdf'

if WKHTMLTOPDF_PATH and not os.path.exists(WKHTMLTOPDF_PATH):
    print(f"WARNING: wkhtmltopdf not found at '{WKHTMLTOPDF_PATH}'. PDF generation might fail.")
    print("Please install wkhtmltopdf and/or configure WKHTMLTOPDF_PATH in app.py or as an environment variable.")
    config = None # Set config to None if wkhtmltopdf is not found
else:
    # Only create configuration if WKHTMLTOPDF_PATH is not None and exists
    if WKHTMLTOPDF_PATH:
        config = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)
        print(f"wkhtmltopdf configured at: {WKHTMLTOPDF_PATH}")
    else: # This case handles when WKHTMLTOPDF_PATH is None (e.g., if it's in system PATH on some OS)
        print("wkhtmltopdf path not explicitly set, trying to use system PATH.")
        config = None # Let pdfkit try to find it in PATH
# --- END NEW: PDFKit Configuration ---


# --- User Loader for Flask-Login ---
@login_manager.user_loader
def load_user(user_id):
    # user_id comes as a string, so convert it to an integer if your user IDs are integers
    return Franchisee.query.get(int(user_id))

# --- Franchisee Model Definition ---
class Franchisee(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False) # Made nullable=False
    name = db.Column(db.String(120), nullable=False, default='Unnamed Franchisee') # Added name
    location = db.Column(db.String(120), nullable=False, default='Unknown Location') # Added location
    is_admin = db.Column(db.Boolean, default=False) # Added is_admin

    # Relationships for the new models
    daily_reports = db.relationship('DailyReport', backref='franchisee', lazy=True, cascade="all, delete-orphan")
    ingredient_reorders = db.relationship('IngredientReorder', backref='franchisee', lazy=True, cascade="all, delete-orphan")
    # Relationship for TeamAttendance, linking directly to Franchisee as well
    team_attendances = db.relationship('TeamAttendance', backref='franchisee_member', lazy=True, cascade="all, delete-orphan")


    def get_id(self):
        return str(self.id)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<Franchisee {self.username}>'

# --- NEW Database Models ---
class DailyReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    franchisee_id = db.Column(db.Integer, db.ForeignKey('franchisee.id'), nullable=False)
    report_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    total_sales = db.Column(db.Float, nullable=False)
    # The original instruction for PDF generation assumed these columns exist:
    cash_collected = db.Column(db.Float, nullable=False, default=0.0) # Added for PDF report
    banked_in = db.Column(db.Float, nullable=False, default=0.0)      # Added for PDF report
    expenses = db.Column(db.Float, nullable=False, default=0.0)       # Added for PDF report
    description = db.Column(db.Text, nullable=True) # Used 'notes' before, but 'description' is used in PDF template
    notes = db.Column(db.Text, nullable=True) # Keeping 'notes' for compatibility if you use it elsewhere

    # Relationship to TeamAttendance (This already exists)
    # attendance = db.relationship('TeamAttendance', backref='daily_report', lazy=True, cascade="all, delete-orphan")
    # Clarification: DailyReport.attendance is a one-to-many relationship.
    # The PDF template's 'team_attendance' comes from a separate query,
    # but if you intend to link a single daily report to multiple attendance entries,
    # the relationship below (using backref for TeamAttendance) is the right way.
    # If a DailyReport has only ONE TeamAttendance entry, you might define it differently.
    # For now, let's ensure TeamAttendance model has the attendance_date as seen in the PDF generation code.

    def __repr__(self):
        return f'<DailyReport {self.report_date} - {self.total_sales}>'

class TeamAttendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # daily_report_id = db.Column(db.Integer, db.ForeignKey('daily_report.id'), nullable=False) # Keep this if a report is mandatory for attendance
    # Linking directly to franchisee for broader context, as in previous discussion
    franchisee_id = db.Column(db.Integer, db.ForeignKey('franchisee.id'), nullable=False)
    attendance_date = db.Column(db.Date, nullable=False, default=datetime.utcnow) # Added for PDF report filtering
    team_member_name = db.Column(db.String(100), nullable=False)
    is_present = db.Column(db.Boolean, nullable=False)
    remarks = db.Column(db.Text, nullable=True) # Added for PDF report
    # If DailyReport.attendance backref is used, you can access attendance.daily_report
    daily_report_id = db.Column(db.Integer, db.ForeignKey('daily_report.id'), nullable=True) # Make nullable=True if attendance can exist without a direct daily report link, or ensure it's always linked.
    # Add backref for daily_report
    daily_report = db.relationship('DailyReport', backref=db.backref('attendances', lazy=True, cascade="all, delete-orphan"))

    def __repr__(self):
        return f'<TeamAttendance {self.team_member_name} - Present: {self.is_present}>'

class IngredientReorder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    franchisee_id = db.Column(db.Integer, db.ForeignKey('franchisee.id'), nullable=False)
    request_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    ingredient_name = db.Column(db.String(100), nullable=False)
    quantity_needed = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='Pending') # e.g., 'Pending', 'Approved', 'Rejected'

    def __repr__(self):
        return f'<IngredientReorder {self.ingredient_name} - {self.quantity_needed} - {self.status}>'


# --- Routes ---
@app.route('/')
def home():
    return render_template('index.html', title='Home')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        name = request.form.get('name', 'New Franchisee') # Get name from form or set default
        location = request.form.get('location', 'Unspecified') # Get location from form or set default


        if not username or not password:
            flash('Username and password are required!', 'danger')
            return redirect(url_for('register'))

        existing_user = Franchisee.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'warning')
            return redirect(url_for('register'))

        new_franchisee = Franchisee(username=username, name=name, location=location) # Pass name and location
        new_franchisee.set_password(password)

        try:
            db.session.add(new_franchisee)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred during registration: {e}', 'danger')
            return redirect(url_for('register'))

    return render_template('register.html', title='Register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        franchisee = Franchisee.query.filter_by(username=username).first()

        if franchisee and franchisee.check_password(password):
            login_user(franchisee)
            flash('Logged in successfully!', 'success')
            next_page = request.args.get('next')
            # Redirect to admin dashboard if admin, otherwise to home/user dashboard
            if franchisee.is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(next_page or url_for('home')) # Redirect to home for regular users
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html', title='Login')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home')) # Redirect to home after logout

# --- Route for Daily Sales Report Submission ---
@app.route('/submit_daily_report', methods=['GET', 'POST'])
@login_required # Requires user to be logged in
def submit_daily_report():
    if request.method == 'POST':
        try:
            report_date_str = request.form.get('report_date')
            total_sales = float(request.form.get('total_sales'))
            cash_collected = float(request.form.get('cash_collected', 0.0)) # Added
            banked_in = float(request.form.get('banked_in', 0.0))       # Added
            expenses = float(request.form.get('expenses', 0.0))         # Added
            description = request.form.get('description', None)         # Added (was 'notes')

            # Convert date string to date object
            report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()

            # Check if a report for this date already exists for the current user
            existing_report = DailyReport.query.filter_by(
                franchisee_id=current_user.id,
                report_date=report_date
            ).first()

            if existing_report:
                flash(f'A daily report for {report_date_str} already exists. Please update it if needed.', 'warning')
                return redirect(url_for('submit_daily_report'))

            new_report = DailyReport(
                franchisee_id=current_user.id,
                report_date=report_date,
                total_sales=total_sales,
                cash_collected=cash_collected, # Added
                banked_in=banked_in,       # Added
                expenses=expenses,         # Added
                description=description,   # Added
                notes=description          # Keeping notes for now, but description is used in PDF template
            )
            db.session.add(new_report)
            db.session.commit()
            flash('Daily sales report submitted successfully! Now you can add attendance for it.', 'success')
            return redirect(url_for('add_attendance', report_id=new_report.id))

        except ValueError:
            flash('Invalid input for Total Sales, Cash Collected, Banked In, Expenses or Date. Please ensure sales/money is a number and date is valid.', 'danger')
        except Exception as e:
            flash(f'An error occurred: {e}', 'danger')
        return redirect(url_for('submit_daily_report'))
    return render_template('submit_daily_report.html', title='Submit Daily Report')

# --- Route for Add Team Attendance ---
@app.route('/add_attendance', methods=['GET', 'POST'])
@login_required
def add_attendance():
    report_id = request.args.get('report_id', type=int)
    selected_report = None
    if report_id:
        selected_report = DailyReport.query.get(report_id)
        if not selected_report or selected_report.franchisee_id != current_user.id:
            flash('Invalid Daily Report ID or you do not have permission to access it.', 'danger')
            selected_report = None

    franchisee_reports = DailyReport.query.filter_by(franchisee_id=current_user.id).order_by(DailyReport.report_date.desc()).all()

    if request.method == 'POST':
        daily_report_id = request.form.get('daily_report_id', type=int)
        team_member_name = request.form.get('team_member_name')
        is_present = 'is_present' in request.form
        remarks = request.form.get('remarks', None) # Added for PDF

        report_to_link = DailyReport.query.get(daily_report_id)

        if not report_to_link or report_to_link.franchisee_id != current_user.id:
            flash('Invalid Daily Report selected.', 'danger')
            return redirect(url_for('add_attendance'))

        if not team_member_name:
            flash('Team member name cannot be empty.', 'danger')
            return redirect(url_for('add_attendance', report_id=daily_report_id))

        new_attendance = TeamAttendance(
            daily_report_id=report_to_link.id,
            franchisee_id=current_user.id, # Link attendance directly to franchisee
            attendance_date=report_to_link.report_date, # Use the report date for attendance
            team_member_name=team_member_name,
            is_present=is_present,
            remarks=remarks # Added
        )
        db.session.add(new_attendance)
        db.session.commit()
        flash(f'Attendance logged for {team_member_name} for {report_to_link.report_date.strftime("%Y-%m-%d")}.', 'success')
        return redirect(url_for('add_attendance', report_id=daily_report_id))

    return render_template(
        'add_attendance.html',
        title='Add Team Attendance',
        franchisee_reports=franchisee_reports,
        selected_report=selected_report
    )

# --- New Route for Ingredient Reorder Request ---
@app.route('/request_ingredients', methods=['GET', 'POST'])
@login_required
def request_ingredients():
    if request.method == 'POST':
        try:
            ingredient_name = request.form.get('ingredient_name')
            quantity_needed = int(request.form.get('quantity_needed'))

            if not ingredient_name or quantity_needed <= 0:
                flash('Ingredient name and a positive quantity are required.', 'danger')
                return redirect(url_for('request_ingredients'))

            new_reorder = IngredientReorder(
                franchisee_id=current_user.id,
                ingredient_name=ingredient_name,
                quantity_needed=quantity_needed,
                status='Pending' # Default status
            )
            db.session.add(new_reorder)
            db.session.commit()
            flash('Ingredient reorder request submitted successfully!', 'success')
            return redirect(url_for('request_ingredients'))
        except ValueError:
            flash('Invalid quantity. Please enter a whole number.', 'danger')
        except Exception as e:
            flash(f'An error occurred: {e}', 'danger')
        return redirect(url_for('request_ingredients'))
    return render_template('request_ingredients.html', title='Request Ingredients')


# Admin Dashboard Route
@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('You do not have permission to access the admin dashboard.', 'danger')
        return redirect(url_for('home')) # Redirect to a non-admin dashboard or home

    all_daily_reports = DailyReport.query.order_by(DailyReport.report_date.desc()).all()
    all_reorder_requests = IngredientReorder.query.order_by(IngredientReorder.request_date.desc()).all()

    # Top Booths (Total sales for the last 7 days)
    seven_days_ago = datetime.now() - timedelta(days=7)
    top_booths_query = db.session.query(
        Franchisee.name,
        db.func.sum(DailyReport.total_sales).label('total_sales')
    ).join(DailyReport).filter(DailyReport.report_date >= seven_days_ago).group_by(Franchisee.name).order_by(db.func.sum(DailyReport.total_sales).desc()).limit(5).all()
    top_booths = [{'name': booth[0], 'total_sales': booth[1]} for booth in top_booths_query]

    # Total sales for current month
    current_month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total_sales_current_month = db.session.query(db.func.sum(DailyReport.total_sales)).filter(
        DailyReport.report_date >= current_month_start
    ).scalar() or 0.0

    return render_template('admin_dashboard.html',
                           daily_reports=all_daily_reports,
                           reorder_requests=all_reorder_requests,
                           top_booths=top_booths,
                           total_sales_current_month=total_sales_current_month,
                           now=datetime.now) # This is the addition

# --- NEW: PDF Generation Route ---
@app.route('/generate_monthly_report_pdf', methods=['POST'])
@login_required
def generate_monthly_report_pdf():
    if not current_user.is_admin:
        flash('You do not have permission to generate PDF reports.', 'danger')
        return redirect(url_for('dashboard')) # Ensure 'dashboard' is a valid route for non-admins, or change to 'home'

    selected_month = request.form.get('month')
    selected_year = request.form.get('year')

    if not selected_month or not selected_year:
        flash('Please select a month and year.', 'danger')
        return redirect(url_for('admin_dashboard'))

    try:
        month_int = int(selected_month)
        year_int = int(selected_year)
    except ValueError:
        flash('Invalid month or year.', 'danger')
        return redirect(url_for('admin_dashboard'))

    # Calculate start and end dates for the selected month
    num_days = monthrange(year_int, month_int)[1]
    start_date = datetime(year_int, month_int, 1).date()
    end_date = datetime(year_int, month_int, num_days).date()

    # Fetch data for the selected month
    # Ensure Franchisee.name is correctly joined or accessed for ordering
    monthly_daily_reports = DailyReport.query.filter(
        DailyReport.report_date >= start_date,
        DailyReport.report_date <= end_date
    ).join(Franchisee).order_by(DailyReport.report_date.asc(), Franchisee.name.asc()).all() # Order by date and franchisee name for better readability

    monthly_team_attendance = TeamAttendance.query.filter(
        TeamAttendance.attendance_date >= start_date,
        TeamAttendance.attendance_date <= end_date
    ).join(Franchisee).order_by(TeamAttendance.attendance_date.asc(), Franchisee.name.asc()).all() # Corrected join and ordering

    # Calculate total sales for the month
    total_sales_month = sum(report.total_sales for report in monthly_daily_reports)

    # Render HTML template for PDF content
    html_content = render_template('monthly_report_template.html',
                                   month=datetime(year_int, month_int, 1).strftime('%B'),
                                   year=year_int,
                                   daily_reports=monthly_daily_reports,
                                   team_attendance=monthly_team_attendance,
                                   total_sales_month=total_sales_month)

    # Generate PDF
    try:
        if config: # Use the configured path if it exists
            pdf = pdfkit.from_string(html_content, False, configuration=config)
        else: # Otherwise, let pdfkit try to find it in PATH
            pdf = pdfkit.from_string(html_content, False)

        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=Monthly_Report_{selected_month}_{selected_year}.pdf'
        return response
    except Exception as e:
        flash(f'Error generating PDF: {e}', 'danger')
        app.logger.error(f"PDF generation error: {e}") # Log the error for debugging
        return redirect(url_for('admin_dashboard'))
# --- END NEW: PDF Generation Route ---


# --- Main Run Block ---
if __name__ == '__main__':
    with app.app_context():
        # WARNING: This will drop ALL existing tables and recreate them.
        # All your current data will be lost. Use this for development/initial setup.
        print("Attempting to drop and recreate database tables...")
        db.drop_all() # This will drop all tables
        db.create_all() # This will recreate all tables with the new schema
        print("Database tables dropped and recreated.")

        # Create a default admin user if one doesn't exist
        admin_username = 'admin'
        admin_password = 'admin_password' # REMEMBER TO CHANGE THIS IN PRODUCTION!

        admin_user = Franchisee.query.filter_by(username=admin_username).first()
        if not admin_user:
            admin_user = Franchisee(
                username=admin_username,
                name='Headquarters Admin',
                location='Headquarters',
                is_admin=True
            )
            admin_user.set_password(admin_password) # Use the set_password method
            db.session.add(admin_user)
            db.session.commit()
            print(f"Default admin user '{admin_username}' created with password '{admin_password}'.")
        else:
            print(f"Admin user '{admin_username}' already exists.")

    app.run(debug=True)