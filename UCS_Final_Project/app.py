from flask import Flask, render_template
from invoice_processor import invoice_processor_bp
from statement_separator import statement_separator_bp
from excel_macros import excel_macros_bp
from cc_batch_demo import cc_batch_demo_bp

app = Flask(__name__)

# Set the secret key to some random bytes. Keep this really secret in production!
app.secret_key = 'yarabitouf'  # Replace with a strong, unique key

# Register Blueprints
app.register_blueprint(invoice_processor_bp, url_prefix='/invoice_processor')
app.register_blueprint(statement_separator_bp, url_prefix='/statement_separator')
app.register_blueprint(excel_macros_bp, url_prefix='/excel_macros')
app.register_blueprint(cc_batch_demo_bp, url_prefix='/cc_batch_demo')

@app.route('/')
def home():
    return render_template('home.html')

if __name__ == '__main__':
    app.run(debug=True, port=3311)