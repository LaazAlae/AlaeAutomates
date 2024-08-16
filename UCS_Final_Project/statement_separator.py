import os
import re
import fitz  # PyMuPDF
import pandas as pd
from difflib import get_close_matches
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, send_file
import zipfile
from werkzeug.utils import secure_filename



# Blueprint for the statement separator functionality
statement_separator_bp = Blueprint('statement_separator', __name__)



us_states = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI",
    "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC",
    "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT",
    "VT", "VA", "WA", "WV", "WI", "WY", "DC"
]

# Global variables to hold state during processing
pending_decisions = []
dnm_pages = []
natio_single_pages = []
natio_multi_pages = []
foreign_pages = []

@statement_separator_bp.route('/clear_results', methods=['POST'])
def clear_results():
    result_folder = os.path.join(os.getcwd(), "results")
    if os.path.exists(result_folder):
        for file in os.listdir(result_folder):
            file_path = os.path.join(result_folder, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
            elif os.path.isdir(file_path):
                for sub_file in os.listdir(file_path):
                    os.remove(os.path.join(file_path, sub_file))
    return jsonify({'status': 'success'})

@statement_separator_bp.route('/process_pdf', methods=['GET', 'POST'])
def process_pdf_endpoint():
    if request.method == 'POST':
        # Clear results folder before processing new upload
        clear_results()  # Using the new clear_results function

        pdf_file = request.files['pdf_file']
        excel_file = request.files['excel_file']

        start_markers = ["914.949.9618", "302.703.8961", "www.unitedcorporate.com", "AR@UNITEDCORPORATE.COM"]
        end_marker = "STATEMENT OF OPEN INVOICE(S)"

        result_folder = os.path.join(os.getcwd(), "results")
        pdf_path = os.path.join(result_folder, secure_filename(pdf_file.filename))
        excel_path = os.path.join(result_folder, secure_filename(excel_file.filename))

        pdf_file.save(pdf_path)
        excel_file.save(excel_path)

        global pending_decisions, dnm_pages, natio_single_pages, natio_multi_pages, foreign_pages
        pending_decisions.clear()
        dnm_pages.clear()
        natio_single_pages.clear()
        natio_multi_pages.clear()
        foreign_pages.clear()

        # Check if the PDF contains readable text
        doc = fitz.open(pdf_path)
        has_text = any(page.get_text().strip() for page in doc)

        if not has_text:
            return jsonify({"status": "error", "message": "The PDF you uploaded doesn't contain readable text. If you can't highlight the text in your PDF manually, the program won't be able to read it."})

        dnm_pages, natio_single_pages, natio_multi_pages, foreign_pages = extract_text_between_markers(
            pdf_path, excel_path, start_markers, end_marker)

        save_pages_to_txt(dnm_pages, natio_single_pages, natio_multi_pages, foreign_pages)

        if len(pending_decisions) > 0:
            return jsonify({
                "status": "review", 
                "statements": pending_decisions,
                "pdf_path": pdf_path
            })
        else:
            create_pdfs_based_on_txt(pdf_path, dnm_pages, natio_single_pages, natio_multi_pages, foreign_pages)
            return redirect(url_for('statement_separator.results_page'))

    else:
        return render_template('statement_separator.html')

def save_pages_to_txt(dnm_pages, natio_single_pages, natio_multi_pages, foreign_pages):
    folder_path = os.path.join(os.getcwd(), "results")
    os.makedirs(folder_path, exist_ok=True)

    files_and_pages = {
        "DNM_pages.txt": dnm_pages,
        "NatioSingle_pages.txt": natio_single_pages,
        "NatioMulti_pages.txt": natio_multi_pages,
        "Foreign_pages.txt": foreign_pages
    }

    for filename, pages in files_and_pages.items():
        with open(os.path.join(folder_path, filename), 'w') as f:
            f.write(','.join(map(str, pages)))
        print(f"DEBUG: Saved {filename} with pages: {pages}")

def load_pages_from_txt():
    folder_path = os.path.join(os.getcwd(), "results")

    files_and_pages = {
        "DNM_pages.txt": [],
        "NatioSingle_pages.txt": [],
        "NatioMulti_pages.txt": [],
        "Foreign_pages.txt": []
    }

    for filename in files_and_pages.keys():
        path = os.path.join(folder_path, filename)
        if os.path.exists(path):
            with open(path, 'r') as f:
                pages = f.read().strip()
                if pages:
                    files_and_pages[filename] = list(map(int, pages.split(',')))
            print(f"DEBUG: Loaded {filename} with pages: {files_and_pages[filename]}")
        else:
            print(f"DEBUG: {filename} not found, no pages loaded.")

    return files_and_pages["DNM_pages.txt"], files_and_pages["NatioSingle_pages.txt"], files_and_pages["NatioMulti_pages.txt"], files_and_pages["Foreign_pages.txt"]

@statement_separator_bp.route('/review_statement', methods=['POST'])
def review_statement():
    global pending_decisions, dnm_pages, natio_single_pages, natio_multi_pages, foreign_pages
    data = request.get_json()
    action = data.get('action')
    statement = data.get('statement')

    pdf_path = data.get('pdf_path')

    if pdf_path is None:
        return jsonify({"error": "pdf_path is None"}), 500

    if action == 'y':
        new_pages = list(range(statement['page_num'], statement['page_num'] + statement['total_pages_in_statement']))
        dnm_pages.extend(new_pages)
    elif action == 'n':
        if "email" in "\n".join(statement['filtered_lines']).lower():
            new_pages = list(range(statement['page_num'], statement['page_num'] + statement['total_pages_in_statement']))
            dnm_pages.extend(new_pages)
        else:
            found_us_state = any(state in line for line in statement['filtered_lines'][1:] for state in us_states)
            if found_us_state:
                new_pages = list(range(statement['page_num'], statement['page_num'] + statement['total_pages_in_statement']))
                if statement['total_pages_in_statement'] == 1:
                    natio_single_pages.extend(new_pages)
                else:
                    natio_multi_pages.extend(new_pages)
            else:
                new_pages = list(range(statement['page_num'], statement['page_num'] + statement['total_pages_in_statement']))
                foreign_pages.extend(new_pages)

    # Save the updated page lists to text files after each decision
    save_pages_to_txt(dnm_pages, natio_single_pages, natio_multi_pages, foreign_pages)

    # Pop the current decision
    if pending_decisions:
        pending_decisions.pop(0)

    # Check if there are more decisions to review
    if pending_decisions:
        return jsonify({"status": "continue", "remaining_statements": len(pending_decisions)})
    else:
        create_pdfs_based_on_txt(pdf_path, dnm_pages, natio_single_pages, natio_multi_pages, foreign_pages)
        return jsonify({"status": "finished"})

@statement_separator_bp.route('/results', endpoint='results_page')
def statement_results_page():
    folder_path = os.path.join(os.getcwd(), "results")

    pdf_files = {
        "DNM.pdf": 0,
        "NatioSingle.pdf": 0,
        "NatioMulti.pdf": 0,
        "Foreign.pdf": 0
    }

    for filename in pdf_files.keys():
        pdf_path = os.path.join(folder_path, filename)
        if os.path.exists(pdf_path):
            with fitz.open(pdf_path) as pdf:
                pdf_files[filename] = pdf.page_count

    return render_template('results.html',
                           count_dnm=pdf_files["DNM.pdf"],
                           count_natio_single=pdf_files["NatioSingle.pdf"],
                           count_natio_multi=pdf_files["NatioMulti.pdf"],
                           count_foreign=pdf_files["Foreign.pdf"])

import time

@statement_separator_bp.route('/download/<pdf_type>')
def download_pdf(pdf_type):
    folder_path = os.path.join(os.getcwd(), "results")
    pdf_filename = f"{pdf_type}.pdf"
    pdf_path = os.path.join(folder_path, pdf_filename)
    
    print(f"DEBUG: Attempting to download {pdf_filename} from {pdf_path}")

    # Ensure the filename casing is consistent
    if pdf_type.lower() == 'natio_single':
        pdf_filename = "NatioSingle.pdf"
    elif pdf_type.lower() == 'natio_multi':
        pdf_filename = "NatioMulti.pdf"
    elif pdf_type.lower() == 'dnm':
        pdf_filename = "DNM.pdf"
    elif pdf_type.lower() == 'foreign':
        pdf_filename = "Foreign.pdf"
    
    pdf_path = os.path.join(folder_path, pdf_filename)
    print(f"DEBUG: Adjusted file path: {pdf_path}")

    if os.path.exists(pdf_path):
        print(f"DEBUG: File found. Proceeding with download.")
        return send_file(pdf_path, as_attachment=True)
    else:
        print(f"ERROR: {pdf_filename} not found at {pdf_path}")
        # Recheck the existence of the folder and files
        if os.path.exists(folder_path):
            print(f"DEBUG: Results folder exists. Checking contents...")
            print(f"DEBUG: Contents: {os.listdir(folder_path)}")
        else:
            print(f"ERROR: Results folder does not exist.")
        return redirect(url_for('statement_separator.results_page'))

@statement_separator_bp.route('/download_all')
def download_all():
    folder_path = os.path.join(os.getcwd(), "results")
    
    # Define the allowed files
    allowed_files = {"DNM.pdf", "NatioSingle.pdf", "NatioMulti.pdf", "Foreign.pdf"}



    zip_filename = "All_Statements.zip"
    zip_path = os.path.join(folder_path, zip_filename)
    
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file in allowed_files:
                    zipf.write(os.path.join(root, file), file)
    
    print(f"DEBUG: Created ZIP file {zip_filename} containing all PDFs")
    return send_file(zip_path, as_attachment=True)

def create_pdfs_based_on_txt(pdf_path, dnm_pages, natio_single_pages, natio_multi_pages, foreign_pages):
    folder_path = os.path.join(os.getcwd(), "results")
    
    if not os.path.exists(pdf_path):
        print(f"ERROR: PDF file does not exist at {pdf_path}")
        return
    
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    
    pdf_output_files = {
        "DNM.pdf": dnm_pages,
        "NatioSingle.pdf": natio_single_pages,
        "NatioMulti.pdf": natio_multi_pages,
        "Foreign.pdf": foreign_pages
    }
    
    for pdf_name, pages in pdf_output_files.items():
        output_pdf = fitz.open()
        for page_num in pages:
            if 0 <= page_num - 1 < total_pages:
                output_pdf.insert_pdf(doc, from_page=page_num - 1, to_page=page_num - 1)
        
        if output_pdf.page_count > 0:
            file_path = os.path.join(folder_path, pdf_name)
            print(f"DEBUG: Attempting to save {pdf_name} to {file_path}")
            output_pdf.save(file_path)
            print(f"DEBUG: Saved {pdf_name} to {file_path}")
            output_pdf.close()

            # Recheck the existence right after saving
            if os.path.exists(file_path):
                print(f"DEBUG: {pdf_name} successfully exists at {file_path}")
            else:
                print(f"ERROR: {pdf_name} was expected but not found at {file_path} after saving")
        
        else:
            print(f"DEBUG: No pages were added to {pdf_name}, not saving.")
            output_pdf.close()
    
    doc.close()

    # Recheck all expected files before proceeding
    for pdf_name in pdf_output_files.keys():
        pdf_path = os.path.join(folder_path, pdf_name)
        if os.path.exists(pdf_path):
            print(f"DEBUG: {pdf_name} is ready for download.")
        else:
            print(f"ERROR: {pdf_name} not found after creation.")

def extract_text_between_markers(pdf_path, excel_path, start_markers, end_marker):
    df = pd.read_excel(excel_path)
    company_names = df.iloc[:, 0].dropna().tolist()

    us_states_with_spaces = [state[0] + " " + state[1] for state in us_states]
    us_states_all = us_states + us_states_with_spaces
    
    doc = fitz.open(pdf_path)
    pending_decisions.clear()  # Clear previous pending decisions
    dnm_pages.clear()
    natio_single_pages.clear()
    natio_multi_pages.clear()
    foreign_pages.clear()
    print("DEBUG: Cleared global lists before starting new extraction.")

    page_num = 0
    while page_num < len(doc):
        page = doc.load_page(page_num)
        text = page.get_text()
        print(f"DEBUG: Processing Page {page_num + 1} - Text Length: {len(text)}")

        page_number_match = re.search(r'Page\s*(\d+)\s*of\s*(\d+)', text, re.IGNORECASE)
        if page_number_match:
            current_page = int(page_number_match.group(1))
            total_pages_in_statement = int(page_number_match.group(2))
            page_number_text = page_number_match.group(0).strip()
            print(f"DEBUG: Found page number: {page_number_text}")
        else:
            current_page, total_pages_in_statement, page_number_text = 1, 1, "Page number not found"
            print("DEBUG: Page number not found in the text.")

        start_idx, end_idx = -1, -1
        for marker in start_markers:
            idx = text.find(marker)
            if idx != -1 and (start_idx == -1 or idx < start_idx):
                start_idx = idx

        end_idx = text.find(end_marker)
        
        if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
            extracted_text = text[start_idx + len(start_markers[0]):end_idx].strip()
            for marker in start_markers:
                extracted_text = extracted_text.replace(marker, '').strip()
            
            lines = extracted_text.splitlines()
            
            filtered_lines = []
            for line_counter, line in enumerate(lines, 1):
                if line.strip() and "Statement Date:" not in line and "Total Due:" not in line and "www.unitedcorporate.com" not in line:
                    filtered_lines.append(f"{line_counter}: {line}")

            company_name_in_statement = lines[0].strip() if lines else ""
            print(f"DEBUG: Company name in statement: {company_name_in_statement}")

            if company_name_in_statement in company_names:
                dnm_pages.extend(range(page_num + 1, page_num + 1 + total_pages_in_statement))
                print(f"DEBUG: Exact match found, adding pages {list(range(page_num + 1, page_num + 1 + total_pages_in_statement))} to DNM.")
            else:
                close_matches = get_close_matches(company_name_in_statement, company_names, n=1, cutoff=0.8)
                if close_matches:
                    pending_decisions.append({
                        "page_num": page_num + 1,
                        "company_name_in_statement": company_name_in_statement,
                        "close_match": close_matches[0] if close_matches else None,
                        "filtered_lines": filtered_lines,
                        "page_number_text": page_number_text,
                        "total_pages_in_statement": total_pages_in_statement,
                    })
                    print(f"DEBUG: Close match found: {close_matches[0]} - Added to pending decisions.")
                else:
                    if "email" in text.lower():
                        dnm_pages.extend(range(page_num + 1, page_num + 1 + total_pages_in_statement))
                        print(f"DEBUG: 'email' found in text, adding pages {list(range(page_num + 1, page_num + 1 + total_pages_in_statement))} to DNM.")
                    else:
                        found_us_state = any(state in line for line in lines[1:] for state in us_states_all)
                        if found_us_state:
                            if total_pages_in_statement == 1:
                                natio_single_pages.extend(range(page_num + 1, page_num + 1 + total_pages_in_statement))
                                print(f"DEBUG: US state found, adding page {page_num + 1} to NatioSingle.")
                            else:
                                natio_multi_pages.extend(range(page_num + 1, page_num + 1 + total_pages_in_statement))
                                print(f"DEBUG: US state found, adding pages {list(range(page_num + 1, page_num + 1 + total_pages_in_statement))} to NatioMulti.")
                        else:
                            foreign_pages.extend(range(page_num + 1, page_num + 1 + total_pages_in_statement))
                            print(f"DEBUG: No US state found, adding pages {list(range(page_num + 1, page_num + 1 + total_pages_in_statement))} to Foreign.")

            if total_pages_in_statement > 1:
                page_num += total_pages_in_statement - current_page

        page_num += 1

    print("DEBUG: Extraction complete.")
    return dnm_pages, natio_single_pages, natio_multi_pages, foreign_pages

# Main app setup
from flask import Flask

app = Flask(__name__)
app.register_blueprint(statement_separator_bp, url_prefix='/statement_separator')

if __name__ == '__main__':
    app.run(debug=True) 