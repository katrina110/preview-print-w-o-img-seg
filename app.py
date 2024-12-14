import os
from flask import Flask, request, render_template, jsonify, send_from_directory
import cv2
import numpy as np
import fitz  # PyMuPDF
from docx import Document
from io import BytesIO
import pythoncom
from win32com import client

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
app.config['STATIC_FOLDER'] = os.path.join(os.getcwd(), 'static', 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'jpg', 'jpeg', 'png', 'docx', 'doc'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['STATIC_FOLDER'], exist_ok=True)

images = []  # Store images globally for simplicity
total_pages = 0  # Keep track of total pages
selected_previews = []  # Store paths to selected preview images


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def pdf_to_images(pdf_path):
    document = fitz.open(pdf_path)
    pdf_images = []
    for page_num in range(len(document)):
        page = document.load_page(page_num)
        pix = page.get_pixmap(alpha=False)
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, 3))
        pdf_images.append(cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    document.close()
    return pdf_images


def docx_to_images(docx_path):
    try:
        pythoncom.CoInitialize()  # Initialize COM
        word = client.Dispatch("Word.Application")
        word.visible = False
        doc = word.Documents.Open(docx_path)

        pdf_path = docx_path.replace('.docx', '.pdf')
        doc.SaveAs(pdf_path, FileFormat=17)
        doc.Close()

        images = pdf_to_images(pdf_path)
        os.remove(pdf_path)
        return images
    except Exception as e:
        print(f"Error during DOCX to PDF conversion: {e}")
        return []


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    global images, total_pages
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)

        if filepath.endswith('.pdf'):
            images = pdf_to_images(filepath)
            total_pages = len(images)
        elif filepath.endswith(('.jpg', '.jpeg', '.png')):
            images = [cv2.imread(filepath)]
            total_pages = 1
        elif filepath.endswith(('.docx', '.doc')):
            images = docx_to_images(filepath)
            total_pages = len(images)
        else:
            return jsonify({"error": "Unsupported file format"}), 400

        return jsonify({
            "message": "File uploaded successfully!",
            "fileName": file.filename,
            "totalPages": total_pages
        }), 200

    return jsonify({"error": "Invalid file format"}), 400


@app.route('/generate_preview', methods=['POST'])
def generate_preview():
    global images, selected_previews
    data = request.json
    page_from = int(data.get('pageFrom', 1))
    page_to = int(data.get('pageTo', 1))
    num_copies = int(data.get('numCopies', 1))
    page_size = data.get('pageSize', 'A4')
    color_option = data.get('colorOption', 'Color')

    try:
        selected_images = images[page_from-1:page_to]

        previews = []
        for idx, img in enumerate(selected_images):
            processed_img = img.copy()

            if page_size == 'Short':
                processed_img = cv2.resize(processed_img, (800, 1000))
            elif page_size == 'Long':
                processed_img = cv2.resize(processed_img, (800, 1200))
            elif page_size == 'A4':
                processed_img = cv2.resize(processed_img, (800, 1100))

            if color_option == 'Grayscale':
                processed_img = cv2.cvtColor(processed_img, cv2.COLOR_BGR2GRAY)
                processed_img = cv2.cvtColor(processed_img, cv2.COLOR_GRAY2BGR)

            for _ in range(num_copies):
                preview_path = os.path.join(app.config['STATIC_FOLDER'], f"preview_{idx + 1}_{page_size}_{color_option}.jpg")
                cv2.imwrite(preview_path, processed_img)
                previews.append(f"/uploads/preview_{idx + 1}_{page_size}_{color_option}.jpg")

        selected_previews = previews  # Save for rendering in result.html
        return jsonify({"previews": previews}), 200

    except Exception as e:
        return jsonify({"error": f"Failed to generate previews: {e}"}), 500


@app.route('/result', methods=['GET'])
def result():
    global selected_previews
    return render_template('result.html', previews=selected_previews)


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['STATIC_FOLDER'], filename)


if __name__ == "__main__":
    app.run(debug=True)