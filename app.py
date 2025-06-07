import os # Make sure this is at the top of your app.py

from flask import Flask, render_template, request, redirect, url_for, flash, make_response, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import pdfkit
from calendar import monthrange
from sqlalchemy import inspect # Import inspect for checking table existence


# For Flask-Bootstrap
from flask_bootstrap import Bootstrap

# --- Flask App Configuration ---
app = Flask(__name__)

# Get SECRET_KEY from environment variable, fallback to a local-only key for local development
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_super_secret_key_for_local_development_ONLY')

# Get database URI from environment variable, fallback to SQLite for local development
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///sakecha.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Recommended to set to False for Flask-SQLAlchemy

# --- Initialize Extensions ---
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
bootstrap = Bootstrap(app)

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

# --- Franchisee Model Definition ---
# Moved here to ensure it's defined before it's used in load_user or other parts of the app
class Franchisee(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=False, default='Unnamed Franchisee')
    location = db.Column(db.String(120), nullable=False, default='Unknown Location')
    is_admin = db.Column(db.Boolean, default=False)

    # Relationships for the new models
    daily_reports = db.relationship('DailyReport', backref='franchisee', lazy=True, cascade="all, delete-orphan")
    ingredient_reorders = db.relationship('IngredientReorder', backref='franchisee', lazy=True, cascade="all, delete-orphan")
    team_attendances = db.relationship('TeamAttendance', backref='franchisee_member', lazy=True, cascade="all, delete-orphan")

    def get_id(self):
        return str(self.id)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256') # Ensure hashing method is specified

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
    cash_collected = db.Column(db.Float, nullable=False, default=0.0)
    banked_in = db.Column(db.Float, nullable=False, default=0.0)
    expenses = db.Column(db.Float, nullable=False, default=0.0)
    description = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<DailyReport {self.report_date} - {self.total_sales}>'

class TeamAttendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    franchisee_id = db.Column(db.Integer, db.ForeignKey('franchisee.id'), nullable=False)
    attendance_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    team_member_name = db.Column(db.String(100), nullable=False)
    is_present = db.Column(db.Boolean, nullable=False)
    remarks = db.Column(db.Text, nullable=True)
    daily_report_id = db.Column(db.Integer, db.ForeignKey('daily_report.id'), nullable=True)
    daily_report = db.relationship('DailyReport', backref=db.backref('attendances', lazy=True, cascade="all, delete-orphan"))

    def __repr__(self):
        return f'<TeamAttendance {self.team_member_name} - Present: {self.is_present}>'

class IngredientReorder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    franchisee_id = db.Column(db.Integer, db.ForeignKey('franchisee.id'), nullable=False)
    request_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    ingredient_name = db.Column(db.String(100), nullable=False)
    quantity_needed = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='Pending')

    def __repr__(self):
        return f'<IngredientReorder {self.ingredient_name} - {self.quantity_needed} - {self.status}>'

# --- User Loader for Flask-Login ---
@login_manager.user_loader
def load_user(user_id):
    # user_id comes as a string, so convert it to an integer if your user IDs are integers
    return Franchisee.query.get(int(user_id))

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
        name = request.form.get('name', 'New Franchisee')
        location = request.form.get('location', 'Unspecified')


        if not username or not password:
            flash('Username and password are required!', 'danger')
            return redirect(url_for('register'))

        existing_user = Franchisee.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'warning')
            return redirect(url_for('register'))

        new_franchisee = Franchisee(username=username, name=name, location=location)
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
            if franchisee.is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(next_page or url_for('home'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html', title='Login')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

# --- Route for Daily Sales Report Submission ---
@app.route('/submit_daily_report', methods=['GET', 'POST'])
@login_required
def submit_daily_report():
    if request.method == 'POST':
        try:
            report_date_str = request.form.get('report_date')
            total_sales = float(request.form.get('total_sales'))
            cash_collected = float(request.form.get('cash_collected', 0.0))
            banked_in = float(request.form.get('banked_in', 0.0))
            expenses = float(request.form.get('expenses', 0.0))
            description = request.form.get('description', None)

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
                cash_collected=cash_collected,
                banked_in=banked_in,
                expenses=expenses,
                description=description,
                notes=description
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
        remarks = request.form.get('remarks', None)

        report_to_link = DailyReport.query.get(daily_report_id)

        if not report_to_link or report_to_link.franchisee_id != current_user.id:
            flash('Invalid Daily Report selected.', 'danger')
            return redirect(url_for('add_attendance'))

        if not team_member_name:
            flash('Team member name cannot be empty.', 'danger')
            return redirect(url_for('add_attendance', report_id=daily_report_id))

        new_attendance = TeamAttendance(
            daily_report_id=report_to_link.id,
            franchisee_id=current_user.id,
            attendance_date=report_to_link.report_date,
            team_member_name=team_member_name,
            is_present=is_present,
            remarks=remarks
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
                flash('Ingredient name and a positive quantity are required!', 'danger')
                return redirect(url_for('request_ingredients'))

            new_reorder = IngredientReorder(
                franchisee_id=current_user.id,
                ingredient_name=ingredient_name,
                quantity_needed=quantity_needed,
                request_date=datetime.utcnow().date(),
                status='Pending'
            )
            db.session.add(new_reorder)
            db.session.commit()
            flash('Ingredient reorder request submitted successfully!', 'success')
            return redirect(url_for('view_reorder_history'))

        except ValueError:
            flash('Quantity needed must be a valid number.', 'danger')
        except Exception as e:
            flash(f'An error occurred: {e}', 'danger')
        return redirect(url_for('request_ingredients'))
    return render_template('request_ingredients.html', title='Request Ingredients')

# --- Route for Viewing Reorder History (for Franchisee) ---
@app.route('/reorder_history')
@login_required
def view_reorder_history():
    reorders = IngredientReorder.query.filter_by(franchisee_id=current_user.id).order_by(IngredientReorder.request_date.desc()).all()
    return render_template('reorder_history.html', title='Reorder History', reorders=reorders)

# --- Route for Viewing Daily Reports (for Franchisee) ---
@app.route('/my_daily_reports')
@login_required
def my_daily_reports():
    reports = DailyReport.query.filter_by(franchisee_id=current_user.id).order_by(DailyReport.report_date.desc()).all()
    return render_template('my_daily_reports.html', title='My Daily Reports', reports=reports)

# --- Admin Dashboard and Functionality ---
@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))

    # Fetch all franchisees
    franchisees = Franchisee.query.all()

    # Fetch all daily reports for admin overview
    all_daily_reports = DailyReport.query.order_by(DailyReport.report_date.desc()).all()

    # Fetch all ingredient reorders
    all_reorders = IngredientReorder.query.order_by(IngredientReorder.request_date.desc()).all()

    # Fetch all team attendances
    all_attendances = TeamAttendance.query.order_by(TeamAttendance.attendance_date.desc()).all()


    return render_template(
        'admin_dashboard.html',
        title='Admin Dashboard',
        franchisees=franchisees,
        all_daily_reports=all_daily_reports,
        all_reorders=all_reorders,
        all_attendances=all_attendances
    )

@app.route('/admin/manage_franchisees')
@login_required
def manage_franchisees():
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))
    franchisees = Franchisee.query.all()
    return render_template('manage_franchisees.html', title='Manage Franchisees', franchisees=franchisees)

@app.route('/admin/add_franchisee', methods=['GET', 'POST'])
@login_required
def add_franchisee():
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        name = request.form.get('name')
        location = request.form.get('location')
        is_admin = 'is_admin' in request.form

        if not username or not password:
            flash('Username and password are required!', 'danger')
            return redirect(url_for('add_franchisee'))

        existing_user = Franchisee.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists.', 'warning')
            return redirect(url_for('add_franchisee'))

        new_franchisee = Franchisee(username=username, name=name, location=location, is_admin=is_admin)
        new_franchisee.set_password(password)
        db.session.add(new_franchisee)
        db.session.commit()
        flash('Franchisee added successfully!', 'success')
        return redirect(url_for('manage_franchisees'))
    return render_template('add_franchisee.html', title='Add Franchisee')

@app.route('/admin/edit_franchisee/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_franchisee(id):
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))

    # Fixed typo: Franchisee.query.get_or_404
    franchisee = Franchisee.query.get_or_404(id)
    if request.method == 'POST':
        franchisee.username = request.form.get('username')
        franchisee.name = request.form.get('name')
        franchisee.location = request.form.get('location')
        franchisee.is_admin = 'is_admin' in request.form
        new_password = request.form.get('password')
        if new_password:
            franchisee.set_password(new_password)
        db.session.commit()
        flash('Franchisee updated successfully!', 'success')
        return redirect(url_for('manage_franchisees'))
    return render_template('edit_franchisee.html', title='Edit Franchisee', franchisee=franchisee)

@app.route('/admin/delete_franchisee/<int:id>', methods=['POST'])
@login_required
def delete_franchisee(id):
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))
    franchisee = Franchisee.query.get_or_404(id)
    db.session.delete(franchisee)
    db.session.commit()
    flash('Franchisee deleted successfully!', 'success')
    return redirect(url_for('manage_franchisees'))

@app.route('/admin/daily_reports')
@login_required
def admin_daily_reports():
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))
    reports = DailyReport.query.order_by(DailyReport.report_date.desc()).all()
    return render_template('admin_daily_reports.html', title='All Daily Reports', reports=reports)

@app.route('/admin/edit_daily_report/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_daily_report(id):
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))

    report = DailyReport.query.get_or_404(id)
    if request.method == 'POST':
        report.report_date = datetime.strptime(request.form.get('report_date'), '%Y-%m-%d').date()
        report.total_sales = float(request.form.get('total_sales'))
        report.cash_collected = float(request.form.get('cash_collected'))
        report.banked_in = float(request.form.get('banked_in'))
        report.expenses = float(request.form.get('expenses'))
        report.description = request.form.get('description')
        report.notes = request.form.get('notes')
        db.session.commit()
        flash('Daily report updated successfully!', 'success')
        return redirect(url_for('admin_daily_reports'))
    return render_template('edit_daily_report.html', title='Edit Daily Report', report=report)

@app.route('/admin/delete_daily_report/<int:id>', methods=['POST'])
@login_required
def delete_daily_report(id):
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))
    report = DailyReport.query.get_or_404(id)
    db.session.delete(report)
    db.session.commit()
    flash('Daily report deleted successfully!', 'success')
    return redirect(url_for('admin_daily_reports'))


@app.route('/admin/ingredient_reorders')
@login_required
def admin_ingredient_reorders():
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))
    reorders = IngredientReorder.query.order_by(IngredientReorder.request_date.desc()).all()
    return render_template('admin_ingredient_reorders.html', title='Ingredient Reorders', reorders=reorders)

@app.route('/admin/update_reorder_status/<int:id>', methods=['POST'])
@login_required
def update_reorder_status(id):
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))
    reorder = IngredientReorder.query.get_or_404(id)
    new_status = request.form.get('status')
    if new_status in ['Pending', 'Processing', 'Completed', 'Cancelled']:
        reorder.status = new_status
        db.session.commit()
        flash(f'Reorder {reorder.id} status updated to {new_status}.', 'success')
    else:
        flash('Invalid status.', 'danger')
    return redirect(url_for('admin_ingredient_reorders'))

@app.route('/admin/delete_reorder/<int:id>', methods=['POST'])
@login_required
def delete_reorder(id):
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))
    reorder = IngredientReorder.query.get_or_404(id)
    db.session.delete(reorder)
    db.session.commit()
    flash('Ingredient reorder deleted successfully!', 'success')
    return redirect(url_for('admin_ingredient_reorders'))

@app.route('/admin/team_attendances')
@login_required
def admin_team_attendances():
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))
    attendances = TeamAttendance.query.order_by(TeamAttendance.attendance_date.desc()).all()
    return render_template('admin_team_attendances.html', title='All Team Attendances', attendances=attendances)

@app.route('/admin/edit_attendance/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_attendance(id):
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))

    attendance = TeamAttendance.query.get_or_404(id)
    if request.method == 'POST':
        attendance.team_member_name = request.form.get('team_member_name')
        attendance.is_present = 'is_present' in request.form
        attendance.remarks = request.form.get('remarks')
        db.session.commit()
        flash('Attendance record updated successfully!', 'success')
        return redirect(url_for('admin_team_attendances'))
    return render_template('edit_attendance.html', title='Edit Attendance', attendance=attendance)

@app.route('/admin/delete_attendance/<int:id>', methods=['POST'])
@login_required
def delete_attendance(id):
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))
    attendance = TeamAttendance.query.get_or_404(id)
    db.session.delete(attendance)
    db.session.commit()
    flash('Attendance record deleted successfully!', 'success')
    return redirect(url_for('admin_team_attendances'))

# --- PDF Generation Routes ---

@app.route('/admin/daily_report_pdf/<int:report_id>')
@login_required
def daily_report_pdf(report_id):
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))

    report = DailyReport.query.get_or_404(report_id)
    franchisee = Franchisee.query.get_or_404(report.franchisee_id)
    attendances = TeamAttendance.query.filter_by(daily_report_id=report_id).all()

    # Render HTML template to a string
    rendered_html = render_template('daily_report_pdf_template.html',
                                    report=report,
                                    franchisee=franchisee,
                                    attendances=attendances,
                                    current_date=datetime.now().strftime("%Y-%m-%d %H:%M"))

    if config is None:
        flash("PDF generation is not configured. wkhtmltopdf not found.", "danger")
        return redirect(url_for('admin_daily_reports'))

    try:
        # Generate PDF from HTML string
        pdf = pdfkit.from_string(rendered_html, False, configuration=config) # False means return PDF as string

        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=daily_report_{report.report_date}.pdf'
        return response
    except Exception as e:
        flash(f"Error generating PDF: {e}. Ensure wkhtmltopdf is correctly installed and configured.", "danger")
        return redirect(url_for('admin_daily_reports'))


@app.route('/admin/monthly_report_pdf')
@login_required
def monthly_report_pdf():
    if not current_user.is_admin:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home'))

    # Get month and year from request arguments, or default to current month/year
    year = request.args.get('year', type=int, default=datetime.now().year)
    month = request.args.get('month', type=int, default=datetime.now().month)

    # Validate month and year
    if not (1 <= month <= 12) or year < 2000: # Arbitrary sensible year start
        flash('Invalid month or year.', 'danger')
        return redirect(url_for('admin_dashboard'))

    # Calculate start and end dates for the month
    start_date = datetime(year, month, 1).date()
    end_date = datetime(year, month, monthrange(year, month)[1]).date()

    # Fetch daily reports for the selected month across all franchisees
    monthly_reports = DailyReport.query.filter(
        DailyReport.report_date >= start_date,
        DailyReport.report_date <= end_date
    ).order_by(DailyReport.report_date.asc()).all()

    # Group reports by franchisee for easier display
    reports_by_franchisee = {}
    for report in monthly_reports:
        franchisee_name = report.franchisee.name if report.franchisee else "Unknown"
        if franchisee_name not in reports_by_franchisee:
            reports_by_franchisee[franchisee_name] = []
        reports_by_franchisee[franchisee_name].append(report)

    # Render HTML template to a string
    rendered_html = render_template('monthly_report_pdf_template.html',
                                    year=year,
                                    month_name=datetime(year, month, 1).strftime('%B'),
                                    reports_by_franchisee=reports_by_franchisee,
                                    current_date=datetime.now().strftime("%Y-%m-%d %H:%M"))

    if config is None:
        flash("PDF generation is not configured. wkhtmltopdf not found.", "danger")
        return redirect(url_for('admin_dashboard'))

    try:
        # Generate PDF from HTML string
        pdf = pdfkit.from_string(rendered_html, False, configuration=config)

        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=monthly_report_{year}_{month:02d}.pdf'
        return response
    except Exception as e:
        flash(f"Error generating PDF: {e}. Ensure wkhtmltopdf is correctly installed and configured.", "danger")
        return redirect(url_for('admin_dashboard'))

# --- Database Initialization (Run once on app startup) ---
# Use app.app_context() for database operations
with app.app_context():
    inspector = inspect(db.engine) # Use sqlalchemy.inspect
    # Check if the 'franchisee' table exists as a robust way to know if tables are created
    if not inspector.has_table("franchisee"):
        db.create_all()
        current_app.logger.info("Database tables created for the first time.")

        # Create default admin user only if it doesn't exist
        admin_user = Franchisee.query.filter_by(username='admin').first()
        if not admin_user:
            # Use ADMIN_PASSWORD from environment variable, or a fallback (less secure)
            admin_password = os.environ.get('ADMIN_PASSWORD', 'default_admin_password_for_initial_setup')
            # Ensure the password is hashed correctly for the Franchisee model
            new_admin = Franchisee(username='admin', name='Admin User', location='Headquarters', is_admin=True)
            new_admin.set_password(admin_password) # Use the set_password method
            db.session.add(new_admin)
            db.session.commit()
            current_app.logger.info("Default admin user 'admin' created.")
        else:
            current_app.logger.info("Admin user 'admin' already exists.")
    else:
        current_app.logger.info("Database tables already exist.")


# --- Main Application Run ---
if __name__ == '__main__':
    # This block is for local development only
    app.run(debug=True)