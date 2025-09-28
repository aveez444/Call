import os
from flask import Flask, request, Response, jsonify
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather, Dial, Record
from dotenv import load_dotenv

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")

if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER):
    raise RuntimeError("Missing Twilio env vars. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER")

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
app = Flask(__name__)

DEPARTMENTS = {
    "appointments": "+919999999999",
    "emergency": "+911112223334",
    "callback_owner": "+919888888888"
}

# Language texts
LANGUAGES = {
    "en": {
        "welcome": "Welcome to HealthyCare Clinic. For English, press 1. For Hindi, press 2.",
        "no_input": "We did not receive any input. Goodbye.",
        "invalid_selection": "Invalid selection. Goodbye.",
        "return_main": "No input received. Returning to main menu.",
        "main_menu": "For appointment booking press 1. For emergency help press 2. For pathology tests press 3.",
        "appointment_menu": "For appointment booking. For Dental press 1. For General Doctor press 2. For Orthopaedic press 3.",
        "pathology_menu": "Pathology tests. For regular blood test press 1. For full body profile press 2. For heart check up press 3.",
        "emergency_connect": "Connecting you to emergency services. Please hold.",
        "emergency_fail": "Unable to connect to emergency number. Goodbye.",
        "appointment_thanks": "Thank you. You selected {}. Our team will call you soon to schedule a convenient time.",
        "appointment_record": "If you would like to leave a short message with your preferred time or details, please record after the tone. Press hash when finished.",
        "pathology_thanks": "Thank you. You selected {}. Our staff will call you shortly to arrange an appointment and share instructions.",
        "pathology_record": "If you want to leave a message for preferred timing, record after the tone. Press hash when finished.",
        "thankyou_goodbye": "Thank you. Goodbye.",
        "recording_saved": "Your message has been recorded. We will contact you soon. Goodbye."
    },
    "hi": {
        "welcome": "स्वागत है हेल्थीकेयर क्लिनिक में। अंग्रेजी के लिए, 1 दबाएं। हिंदी के लिए, 2 दबाएं।",
        "no_input": "हमें कोई इनपुट प्राप्त नहीं हुआ। अलविदा।",
        "invalid_selection": "अमान्य चयन। अलविदा।",
        "return_main": "कोई इनपुट प्राप्त नहीं हुआ। मुख्य मेनू पर वापस जा रहे हैं।",
        "main_menu": "अपॉइंटमेंट बुकिंग के लिए 1 दबाएं। इमरजेंसी हेल्प के लिए 2 दबाएं। पैथोलॉजी टेस्ट के लिए 3 दबाएं।",
        "appointment_menu": "अपॉइंटमेंट बुकिंग के लिए। डेंटल के लिए 1 दबाएं। जनरल डॉक्टर के लिए 2 दबाएं। ऑर्थोपेडिक के लिए 3 दबाएं।",
        "pathology_menu": "पैथोलॉजी टेस्ट। रेगुलर ब्लड टेस्ट के लिए 1 दबाएं। फुल बॉडी प्रोफाइल के लिए 2 दबाएं। हार्ट चेक अप के लिए 3 दबाएं।",
        "emergency_connect": "आपको इमरजेंसी सर्विसेज से कनेक्ट किया जा रहा है। कृपया प्रतीक्षा करें।",
        "emergency_fail": "इमरजेंसी नंबर से कनेक्ट नहीं हो पा रहे हैं। अलविदा।",
        "appointment_thanks": "धन्यवाद। आपने {} चुना है। हमारी टीम जल्द ही आपको एक सुविधाजनक समय निर्धारित करने के लिए कॉल करेगी।",
        "appointment_record": "यदि आप अपने पसंदीदा समय या विवरण के साथ एक छोटा संदेश छोड़ना चाहते हैं, कृपया टोन के बाद रिकॉर्ड करें। समाप्त करने पर हैश दबाएं।",
        "pathology_thanks": "धन्यवाद। आपने {} चुना है। हमारा स्टाफ जल्द ही आपके साथ एक अपॉइंटमेंट व्यवस्थित करने और निर्देश साझा करने के लिए कॉल करेगा।",
        "pathology_record": "यदि आप पसंदीदा समय के लिए कोई संदेश छोड़ना चाहते हैं, टोन के बाद रिकॉर्ड करें। समाप्त करने पर हैश दबाएं।",
        "thankyou_goodbye": "धन्यवाद। अलविदा।",
        "recording_saved": "आपका संदेश रिकॉर्ड कर लिया गया है। हम जल्द ही आपसे संपर्क करेंगे। अलविदा।"
    }
}

# Doctor and test mappings in both languages
DOCTOR_MAP = {
    "en": {"1": "Dental", "2": "General Doctor", "3": "Orthopaedic"},
    "hi": {"1": "डेंटल", "2": "जनरल डॉक्टर", "3": "ऑर्थोपेडिक"}
}

TEST_MAP = {
    "en": {"1": "regular blood test", "2": "full body profile", "3": "heart check up"},
    "hi": {"1": "रेगुलर ब्लड टेस्ट", "2": "फुल बॉडी प्रोफाइल", "3": "हार्ट चेक अप"}
}

def twiml_response(twiml):
    return Response(str(twiml), mimetype="text/xml")

def get_language(digits):
    """Get language based on user selection"""
    if digits == "1":
        return "en"
    elif digits == "2":
        return "hi"
    return None

# ---------------- Language Selection ----------------
@app.route("/voice", methods=["POST", "GET"])
def voice():
    resp = VoiceResponse()
    base = request.url_root.rstrip("/")

    gather = Gather(num_digits=1, action=f"{base}/handle-language", method="POST", timeout=8)
    gather.say("Welcome to HealthyCare Clinic. For English, press 1. For Hindi, press 2.")
    resp.append(gather)

    resp.say("We did not receive any input. Goodbye.")
    resp.hangup()
    return twiml_response(resp)

@app.route("/handle-language", methods=["POST"])
def handle_language():
    digits = request.values.get("Digits", "")
    resp = VoiceResponse()
    base = request.url_root.rstrip("/")
    
    lang = get_language(digits)
    if lang:
        # Store language selection and proceed to main menu
        gather = Gather(num_digits=1, action=f"{base}/handle-main?lang={lang}", method="POST", timeout=8)
        gather.say(LANGUAGES[lang]["main_menu"])
        resp.append(gather)
        resp.say(LANGUAGES[lang]["return_main"])
        resp.redirect(f"{base}/voice", method="POST")
    else:
        resp.say("Invalid selection. Goodbye.")
        resp.hangup()
    
    return twiml_response(resp)

# ---------------- Handle main selection ----------------
@app.route("/handle-main", methods=["POST"])
def handle_main():
    digits = request.values.get("Digits", "")
    lang = request.args.get("lang", "en")  # Default to English
    resp = VoiceResponse()
    base = request.url_root.rstrip("/")

    if digits == "1":
        gather = Gather(num_digits=1, action=f"{base}/handle-appointment-doctor?lang={lang}", method="POST", timeout=8)
        gather.say(LANGUAGES[lang]["appointment_menu"])
        resp.append(gather)
        resp.say(LANGUAGES[lang]["return_main"])
        resp.redirect(f"{base}/handle-language", method="POST")
        return twiml_response(resp)

    elif digits == "2":
        resp.say(LANGUAGES[lang]["emergency_connect"])
        resp.dial(DEPARTMENTS["emergency"], timeout=30)
        resp.say(LANGUAGES[lang]["emergency_fail"])
        resp.hangup()
        return twiml_response(resp)

    elif digits == "3":
        gather = Gather(num_digits=1, action=f"{base}/handle-pathology?lang={lang}", method="POST", timeout=8)
        gather.say(LANGUAGES[lang]["pathology_menu"])
        resp.append(gather)
        resp.say(LANGUAGES[lang]["return_main"])
        resp.redirect(f"{base}/handle-language", method="POST")
        return twiml_response(resp)

    else:
        resp.say(LANGUAGES[lang]["invalid_selection"])
        resp.hangup()
        return twiml_response(resp)

# ---------------- Appointment doctor handler ----------------
@app.route("/handle-appointment-doctor", methods=["POST"])
def handle_appointment_doctor():
    digits = request.values.get("Digits", "")
    lang = request.args.get("lang", "en")
    resp = VoiceResponse()
    
    doc = DOCTOR_MAP[lang].get(digits)
    if doc:
        resp.say(LANGUAGES[lang]["appointment_thanks"].format(doc))
        resp.say(LANGUAGES[lang]["appointment_record"])
        resp.record(max_length=60, finish_on_key="#", 
                   action=f"{request.url_root.rstrip('/')}/handle-recording?type=appointment&doctor={doc}&lang={lang}", 
                   method="POST")
        resp.say(LANGUAGES[lang]["thankyou_goodbye"])
        resp.hangup()
        return twiml_response(resp)
    else:
        resp.say(LANGUAGES[lang]["invalid_selection"])
        resp.redirect(f"{request.url_root.rstrip('/')}/handle-language", method="POST")
        return twiml_response(resp)

# ---------------- Pathology handler ----------------
@app.route("/handle-pathology", methods=["POST"])
def handle_pathology():
    digits = request.values.get("Digits", "")
    lang = request.args.get("lang", "en")
    resp = VoiceResponse()
    
    test = TEST_MAP[lang].get(digits)
    if test:
        resp.say(LANGUAGES[lang]["pathology_thanks"].format(test))
        resp.say(LANGUAGES[lang]["pathology_record"])
        resp.record(max_length=60, finish_on_key="#", 
                   action=f"{request.url_root.rstrip('/')}/handle-recording?type=pathology&test={test}&lang={lang}", 
                   method="POST")
        resp.say(LANGUAGES[lang]["thankyou_goodbye"])
        resp.hangup()
        return twiml_response(resp)
    else:
        resp.say(LANGUAGES[lang]["invalid_selection"])
        resp.redirect(f"{request.url_root.rstrip('/')}/handle-language", method="POST")
        return twiml_response(resp)

# ---------------- Recording callback ----------------
@app.route("/handle-recording", methods=["POST"])
def handle_recording():
    recording_url = request.values.get("RecordingUrl")
    recording_sid = request.values.get("RecordingSid")
    duration = request.values.get("RecordingDuration")
    caller = request.values.get("From")
    rtype = request.args.get("type")
    extra = request.args.get("doctor") or request.args.get("test")
    lang = request.args.get("lang", "en")

    print(f"Received recording: sid={recording_sid}, url={recording_url}, duration={duration}, from={caller}, type={rtype}, extra={extra}, language={lang}")

    resp = VoiceResponse()
    resp.say(LANGUAGES[lang]["recording_saved"])
    resp.hangup()
    return twiml_response(resp)

@app.route("/make-call", methods=["POST"])
def make_call():
    body = request.get_json(force=True, silent=True) or {}
    to = body.get("to")
    twiml_url = body.get("twiml_url") or request.url_root.rstrip("/") + "/voice"

    if not to:
        return jsonify({"error": "missing 'to' field"}), 400

    numbers = to if isinstance(to, list) else [to]
    results = []

    for n in numbers:
        try:
            call = client.calls.create(
                url=twiml_url,
                to=n,
                from_=TWILIO_FROM_NUMBER
            )
            results.append({"to": n, "status": "queued", "sid": call.sid})
        except Exception as e:
            results.append({"to": n, "status": "error", "error": str(e)})

    return jsonify(results)

# Test endpoint to verify all language texts
@app.route("/test-languages", methods=["GET"])
def test_languages():
    return jsonify(LANGUAGES)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)