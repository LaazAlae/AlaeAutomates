from flask import Blueprint, render_template

# Create a Blueprint for the Excel Macros page
excel_macros_bp = Blueprint('excel_macros', __name__, template_folder='templates')

@excel_macros_bp.route('/')
def home():
    # Render the template when the route is accessed
    return render_template('excel_macros_home.html')