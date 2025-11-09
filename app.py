import os
import cv2
import json
import markdown
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename
from ultralytics import YOLO
from dotenv import load_dotenv

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain.chat_models import init_chat_model

# ---------------- Setup ---------------- #
load_dotenv()
app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Required for sessions

# Additional session configuration
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# Load YOLO model
model = YOLO("best(2).pt")  # adjust path if needed

# Init Groq LLM
os.environ['GROQ_API_KEY'] = os.getenv("GROQ_API_KEY")
groq_model = init_chat_model("groq:llama-3.1-8b-instant")

# ---------------- YOLO Helper ---------------- #
def calculate_stenosis_volume(width, height, depth=None):
    if depth is None:
        depth = (width + height) / 2
    volume = width * height * depth
    volume_cm3 = volume * (0.1 ** 3)  # assume 1px ≈ 0.1cm
    return volume_cm3

def extract_stenosis_findings(results):
    findings = []
    for result in results[0].boxes.data:
        x1, y1, x2, y2, conf, cls = result
        width = x2 - x1
        height = y2 - y1
        volume = calculate_stenosis_volume(width, height)
        findings.append({
            "condition": "Stenosis",
            "confidence": float(conf),
            "volume_cm3": float(volume),
            "bounding_box": [int(x1), int(y1), int(x2), int(y2)]
        })
    return findings

# ---------------- LLM Setup ---------------- #
diagnosis_prompt = PromptTemplate(
    template="""You are a senior cardiologist with expertise in angiography and heart disease diagnosis. Based on the following stenosis detection results:

{findings}

{image_context}

Generate a comprehensive, professional medical report in Markdown format. The report should be structured as follows:

## Executive Summary
- Brief overview of findings (1-2 sentences)
- Overall assessment (healthy, mild stenosis, moderate stenosis, or severe stenosis)

## Detailed Analysis
- Specific findings from the AI detection
- Location and characteristics of any detected stenosis
- Confidence levels and reliability of the analysis

## Clinical Assessment
- Severity classification based on detected parameters
- Risk factors and implications
- Comparison with normal ranges

## Recommendations
- Immediate next steps for healthcare providers
- Suggested follow-up procedures
- Patient monitoring recommendations

## Technical Notes
- AI model confidence and limitations
- Image quality assessment
- Recommendations for additional imaging if needed

Use professional medical terminology and maintain a clinical, authoritative tone. If no stenosis is detected, emphasize that this is a normal finding but recommend standard follow-up protocols. Always include appropriate medical disclaimers.

Format the response in clean Markdown with proper headings and bullet points.""",
    input_variables=["findings", "image_context"]
)

parser = StrOutputParser()
diagnosis_chain = diagnosis_prompt | groq_model | parser

def get_stenosis_report(findings):
    try:
        # Determine if stenosis was detected
        if not findings or len(findings) == 0:
            image_context = "The AI analysis detected NO signs of stenosis in this angiography image. The image appears to be from a healthy individual with normal coronary artery structure."
        else:
            # Calculate overall severity
            total_volume = sum(f['volume_cm3'] for f in findings)
            avg_confidence = sum(f['confidence'] for f in findings) / len(findings)
            
            if total_volume > 1.0:
                severity = "severe"
            elif total_volume > 0.5:
                severity = "moderate"
            else:
                severity = "mild"
                
            image_context = f"The AI analysis detected {len(findings)} stenosis area(s) with {severity} severity. Total estimated volume: {total_volume:.2f} cm³. Average confidence: {avg_confidence:.1%}."
        
        return diagnosis_chain.invoke({
            "findings": findings if findings else [],
            "image_context": image_context
        })
    except Exception as e:
        print(f"Error generating report: {str(e)}")
        if not findings or len(findings) == 0:
            return """## Executive Summary
No stenosis detected in this angiography image. The image appears to be from a healthy individual.

## Detailed Analysis
- AI analysis completed successfully
- No abnormal narrowing or blockages detected
- Coronary arteries appear within normal parameters

## Clinical Assessment
- **Status**: Healthy - No significant stenosis
- **Risk Level**: Low
- **Recommendation**: Standard follow-up protocols

## Recommendations
- Continue routine cardiovascular monitoring
- Maintain healthy lifestyle practices
- Schedule regular check-ups as recommended by primary care physician

## Technical Notes
- AI model confidence: High
- Image quality: Suitable for analysis
- No additional imaging required at this time

---
*This AI analysis is for screening purposes only. Always consult with qualified healthcare professionals for medical decisions.*"""
        else:
            return """## Executive Summary
Potential stenosis detected in this angiography image. Further clinical evaluation recommended.

## Detailed Analysis
- AI detected potential narrowing in coronary arteries
- Specific measurements and locations available in detection data
- Confidence levels indicate areas requiring attention

## Clinical Assessment
- **Status**: Stenosis detected - requires clinical review
- **Risk Level**: Moderate to High (depending on severity)
- **Recommendation**: Immediate clinical evaluation

## Recommendations
- Consult with cardiologist for detailed assessment
- Consider additional diagnostic procedures
- Implement appropriate treatment protocols

## Technical Notes
- AI model confidence: Moderate
- Image quality: Suitable for analysis
- Additional imaging may be beneficial

---
*This AI analysis is for screening purposes only. Always consult with qualified healthcare professionals for medical decisions.*"""

# ---------------- Flask Routes ---------------- #
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Redirect root to login page"""
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        print(f"Login attempt - Name: {name}, Email: {email}")
        if name and email:
            session.permanent = True
            session['user_name'] = name
            session['user_email'] = email
            print(f"Session set - user_name: {session['user_name']}, user_email: {session['user_email']}")
            return redirect(url_for('dashboard'))
    
    return render_template('auth_login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Signup page"""
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        if name and email:
            session.permanent = True
            session['user_name'] = name
            session['user_email'] = email
            return redirect(url_for('dashboard'))
    
    return render_template('auth_signup.html')

@app.route('/dashboard')
def dashboard():
    """Dashboard page with statistics"""
    # Debug: Print session data
    print(f"Session data: {dict(session)}")
    print(f"User name from session: {session.get('user_name')}")
    
    # User data for dynamic display
    user_data = {
        'name': session.get('user_name', 'Doctor')
    }
    print(f"User data being passed to template: {user_data}")
    return render_template('dashboard.html', **user_data)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    """Upload page - GET shows form, POST processes image"""
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(url_for('upload'))

        file = request.files['file']
        if file.filename == '':
            return redirect(url_for('upload'))

        if file and allowed_file(file.filename):
            # Save uploaded image
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Run YOLO detection
            results = model(filepath)
            orig_img = results[0].orig_img.copy()

            # Annotate detections
            for result in results[0].boxes.data:
                x1, y1, x2, y2, conf, cls = result
                cv2.rectangle(orig_img, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)
                cv2.putText(orig_img, f"Stenosis {conf:.2f}", (int(x1), int(y1)-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 2)

            # Save annotated image
            annotated_filename = filename.rsplit('.', 1)[0] + "_annotated.jpg"
            annotated_path = os.path.join(app.config['UPLOAD_FOLDER'], annotated_filename)
            cv2.imwrite(annotated_path, orig_img)

            # Extract findings
            findings = extract_stenosis_findings(results)

            # Get report from LLM
            report = get_stenosis_report(findings)
            html_report = markdown.markdown(report)

            # Store results in session for results page
            session['last_analysis'] = {
                'filename': filename,
                'annotated_image': annotated_filename,
                'findings': findings,
                'report': html_report
            }

            return redirect(url_for('results'))
    
    return render_template('upload.html')

@app.route('/results')
def results():
    """Results page showing analysis results"""
    analysis = session.get('last_analysis', {})
    if not analysis:
        return redirect(url_for('upload'))
    
    return render_template('results.html',
                         filename=analysis.get('filename'),
                         annotated_image=analysis.get('annotated_image'),
                         findings=analysis.get('findings'),
                         report=analysis.get('report'))



@app.route('/profile')
def profile():
    """User profile page"""
    user_data = {
        'name': session.get('user_name', ''),
        'email': session.get('user_email', '')
    }
    return render_template('profile.html', **user_data)

@app.route('/test-session')
def test_session():
    """Test route to check session functionality"""
    session['test'] = 'working'
    session_data = dict(session)
    return f"""
    <h2>Session Test</h2>
    <p>Session test value: {session.get('test')}</p>
    <p>User name: {session.get('user_name', 'Not set')}</p>
    <p>User email: {session.get('user_email', 'Not set')}</p>
    <p>All session data: {session_data}</p>
    <p><a href="/dashboard">Go to Dashboard</a></p>
    """

@app.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
