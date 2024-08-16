from flask import Blueprint, render_template, request, jsonify
import os
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import threading

cc_batch_demo_bp = Blueprint('cc_batch_demo', __name__, template_folder='templates')

@cc_batch_demo_bp.route('/', methods=['GET', 'POST'])
def home():
    return render_template('cc_batch_demo_home.html')

def keep_browser_alive(driver):
    try:
        # Keep the browser session alive by scrolling every minute
        while True:
            # Scroll down by a fixed amount (e.g., 100 pixels)
            driver.execute_script("window.scrollBy(0, 100);")
            time.sleep(60)  # Scroll every minute to keep the session alive
    except:
        pass  # If there's an exception, just exit the thread

@cc_batch_demo_bp.route('/process_excel', methods=['POST'])
def process_excel():
    if 'excel_file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file part'})

    file = request.files['excel_file']

    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No selected file'})

    if file and file.filename.endswith('.xlsx'):
        # Save the uploaded file
        filepath = os.path.join(os.getcwd(), file.filename)
        file.save(filepath)
        
        # Process the Excel file
        df = pd.read_excel(filepath)

        # Start the browser automation process
        try:
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
            url = "https://www.calculator.net/grade-calculator.html"  # Replace with the actual URL
            driver.get(url)
            
            # Calculate the number of extra rows needed
            extra_rows_needed = max(0, -(-len(df) // 3 - 8 // 3))

            # Add extra rows if needed
            for _ in range(extra_rows_needed):
                add_more_rows = driver.find_element(By.LINK_TEXT, "+ add more rows")
                add_more_rows.click()

            # Fill the form with data from the Excel file
            for index, row in df.iterrows():
                d_input = driver.find_element(By.NAME, f'd{index + 1}')
                s_input = driver.find_element(By.NAME, f's{index + 1}')
                w_input = driver.find_element(By.NAME, f'w{index + 1}')
                
                d_input.send_keys(str(row[0]))  # Column A
                s_input.send_keys(str(row[1]))  # Column B
                w_input.send_keys(str(row[2]))  # Column C
            
            # Delete the uploaded file after processing
            os.remove(filepath)

            # Start a new thread to keep the browser alive
            keep_alive_thread = threading.Thread(target=keep_browser_alive, args=(driver,))
            keep_alive_thread.daemon = True  # Make it a daemon thread so it will close when the main program exits
            keep_alive_thread.start()

            # Send the response to the client
            return jsonify({'status': 'success', 'message': 'All your data was input into the grade calculator website.'})

        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})

    return jsonify({'status': 'error', 'message': 'Invalid file format'})