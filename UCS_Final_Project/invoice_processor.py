from flask import Blueprint, request, redirect, url_for, render_template, send_from_directory, jsonify
import fitz  # PyMuPDF
import re
import os
import logging
from werkzeug.utils import secure_filename
import zipfile
import shutil

invoice_processor_bp = Blueprint('invoice_processor', __name__)

# Configuration
UPLOAD_FOLDER = os.path.abspath('uploads')
RESULT_FOLDER = os.path.abspath('separate_results')
ALLOWED_EXTENSIONS = {'pdf'}

# Setting up logging
logging.basicConfig(level=logging.INFO)

@invoice_processor_bp.route('/clear_results', methods=['POST'])
def clear_results():
    result_folder = os.path.abspath('separate_results')
    logging.info(f"Attempting to clear contents of {result_folder}")
    
    if os.path.exists(result_folder):
        for file in os.listdir(result_folder):
            file_path = os.path.join(result_folder, file)
            if os.path.isfile(file_path):
                logging.info(f"Deleting file: {file_path}")
                os.remove(file_path)
            elif os.path.isdir(file_path):
                logging.info(f"Deleting directory and its contents: {file_path}")
                shutil.rmtree(file_path)
    
    logging.info("Finished clearing results folder.")
    return jsonify({'status': 'success'})

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def extract_invoice_numbers_and_split(input_pdf, output_folder):
    doc = fitz.open(input_pdf)
    pattern = r'\b[P|R]\d{6,8}\b'  # Modified regex to match 6, 7, or 8 digits
    invoices_found = False
    try:
        pages_by_invoice = {}
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text()
            invoice_numbers = re.findall(pattern, text)
            if invoice_numbers:
                invoices_found = True
            for invoice_number in invoice_numbers:
                if invoice_number not in pages_by_invoice:
                    pages_by_invoice[invoice_number] = []
                pages_by_invoice[invoice_number].append(page_num)

        if not invoices_found:
            return False  # No invoices found

        for invoice_number, page_nums in pages_by_invoice.items():
            output_pdf = fitz.open()
            for page_num in page_nums:
                output_pdf.insert_pdf(doc, from_page=page_num, to_page=page_num)
            output_filename = os.path.join(output_folder, f"{invoice_number}.pdf")
            output_pdf.save(output_filename)
            output_pdf.close()
    finally:
        doc.close()
    return True

@invoice_processor_bp.route('/', methods=['GET', 'POST'])
def upload_file():
    message = ''
    success = False
    zip_filename = ''
    
    logging.info("Received a request to the upload_file route.")
    
    if request.method == 'POST':
        logging.info("Request method is POST.")
        
        if 'file' not in request.files:
            logging.info("No file part in the request.")
            return render_template('invoice_processor.html', message="No file part in the request", success=success, zip_filename=zip_filename)
        
        file = request.files['file']
        if file.filename == '':
            logging.info("No selected file.")
            return render_template('invoice_processor.html', message="No selected file", success=success, zip_filename=zip_filename)
        
        if file and allowed_file(file.filename, ALLOWED_EXTENSIONS):
            logging.info(f"File {file.filename} is allowed and will be processed.")
            
            if not os.path.exists(UPLOAD_FOLDER):
                os.makedirs(UPLOAD_FOLDER)
                logging.info(f"Created upload folder: {UPLOAD_FOLDER}")
            
            filename = secure_filename(file.filename)
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(file_path)
            logging.info(f"Saved file to {file_path}")
            
            if not os.path.exists(RESULT_FOLDER):
                os.makedirs(RESULT_FOLDER)
                logging.info(f"Created result folder: {RESULT_FOLDER}")
            
            result_folder = os.path.join(RESULT_FOLDER, filename.rsplit('.', 1)[0], 'separateInvoices')
            os.makedirs(result_folder, exist_ok=True)
            logging.info(f"Created result subfolder: {result_folder}")
            
            invoices_found = extract_invoice_numbers_and_split(file_path, result_folder)
            logging.info(f"Invoices found: {invoices_found}")
            
            if not invoices_found:
                message = 'The PDF you chose does not contain any invoice'
                logging.info(message)
            else:
                zip_filename = f"{filename.rsplit('.', 1)[0]}.zip"
                zip_path = os.path.join(RESULT_FOLDER, zip_filename)
                
                if not os.path.isfile(zip_path):
                    logging.info(f"Creating zip file: {zip_filename}")
                    with zipfile.ZipFile(zip_path, 'w') as zipf:
                        for root, dirs, files in os.walk(result_folder):
                            for file in files:
                                zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), result_folder))
                    logging.info(f"Created zip file at {zip_path}")
                
                success = True
                message = 'Invoices separated successfully. Find PDF files in your downloads.'
                logging.info(message)
        else:
            logging.info("File is not allowed or not a PDF.")
            message = 'The file is not a valid PDF or is not allowed.'
    
    logging.info("Rendering template with message and status.")
    return render_template('invoice_processor.html', message=message, success=success, zip_filename=zip_filename)

@invoice_processor_bp.route('/downloads/<filename>')
def download_file(filename):
    zip_path = os.path.join(RESULT_FOLDER, filename)
    if os.path.exists(zip_path):
        return send_from_directory(RESULT_FOLDER, filename, as_attachment=True)
    else:
        return redirect(url_for('invoice_processor.upload_file'))

@invoice_processor_bp.route('/delete_separate_results', methods=['POST'])
def delete_separate_results():
    try:
        if os.path.exists(RESULT_FOLDER):
            shutil.rmtree(RESULT_FOLDER)
            logging.info(f"Deleted contents of {RESULT_FOLDER}")
            os.makedirs(RESULT_FOLDER)
            logging.info(f"Recreated empty result folder: {RESULT_FOLDER}")
        return jsonify({'status': 'success'})
    except Exception as e:
        logging.error(f"Error deleting contents of {RESULT_FOLDER}: {e}")
        return jsonify({'status': 'error'}), 500