import os
from flask import Flask, request, Response, jsonify
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather, Dial, Record
from dotenv import load_dotenv

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")  # e.g. +17815635109

if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER):
    raise RuntimeError("Missing Twilio env vars. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER")

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
app = Flask(__name__)

# --------------- IVR CONTENT (customize for healthcare) ----------------
# Department numbers (update to your clinic numbers, E.164)
DEPARTMENTS = {
    "appointments": "+91XXXXXXXXXX",
    "nurse": "+91YYYYYYYYYY",
    "pharmacy": "+91ZZZZZZZZZZ",
    "emergency": "+911112223334",   # example emergency contact / forwarding
    "operator": "+1AABBCCDDEE"      # operator / receptionist
}

# Helper to produce TwiML response
def twiml_response(twiml):
    return Response(str(twiml), mimetype="text/xml")

# --------------- Incoming / Outbound voice entrypoint -------------------
# Configure your Twilio phone number's Voice URL to point to /voice (full public URL)
@app.route("/voice", methods=["POST", "GET"])
def voice():
    """Initial language selection"""
    resp = VoiceResponse()
    gather = Gather(num_digits=1, action="/handle-language", method="POST")
    gather.say("Welcome to HealthyCare Clinic. For English press 1. For Hindi press 2. For Marathi press 3.", voice="alice", language="en-US")
    resp.append(gather)
    resp.say("We did not receive any input. Goodbye.", voice="alice", language="en-US")
    resp.hangup()
    return twiml_response(resp)

# --------------- Language handler -> presents language specific menu -----------
@app.route("/handle-language", methods=["POST"])
def handle_language():
    digits = request.values.get("Digits", "")
    resp = VoiceResponse()

    if digits == "1":
        # English menu
        gather = Gather(num_digits=1, action="/handle-menu?lang=en", method="POST")
        gather.say("You are in English. For Appointments press 1. For Nurse advice press 2. For Pharmacy press 3. To repeat press 9. To speak to an operator press 0.", voice="alice", language="en-US")
        resp.append(gather)
        resp.say("No input received. Goodbye.", voice="alice", language="en-US")
        resp.hangup()
    elif digits == "2":
        # Hindi menu
        gather = Gather(num_digits=1, action="/handle-menu?lang=hi", method="POST")
        gather.say("आप हिंदी मेन्यू में हैं। अपॉइंटमेंट के लिए 1, नर्स से सलाह के लिए 2, फार्मेसी के लिए 3, दोहराने के लिए 9, ऑपरेटर के लिए 0 दबाएं।", voice="alice", language="hi-IN")
        resp.append(gather)
        resp.say("कोई इनपुट प्राप्त नहीं हुआ। अलविदा।", voice="alice", language="hi-IN")
        resp.hangup()
    elif digits == "3":
        # Marathi menu
        gather = Gather(num_digits=1, action="/handle-menu?lang=mr", method="POST")
        gather.say("आपण मराठी मेनूमध्ये आहात. अपॉइंटमेंटसाठी 1 दाबा, नर्स सल्ल्यासाठी 2, फार्मसीसाठी 3, पुन्हा ऐकण्यासाठी 9, ऑपरेटरसाठी 0 दाबा.", voice="alice", language="mr-IN")
        resp.append(gather)
        resp.say("कोणतीही निवड मिळाली नाही. अलविदा.", voice="alice", language="mr-IN")
        resp.hangup()
    else:
        resp.say("Invalid selection. Goodbye.", voice="alice", language="en-US")
        resp.hangup()

    return twiml_response(resp)

# --------------- Menu option handler (language-aware) --------------------
@app.route("/handle-menu", methods=["POST"])
def handle_menu():
    lang = request.args.get("lang", "en")
    digits = request.values.get("Digits", "")
    resp = VoiceResponse()

    # map digits to actions
    if digits == "1":
        # Appointments
        resp.say(translate("Connecting you to Appointments. Please hold.", lang), voice="alice", language=lang_to_voice(lang))
        resp.dial(DEPARTMENTS["appointments"], timeout=30)
        resp.say(translate("All agents are busy. Please try again later.", lang), voice="alice", language=lang_to_voice(lang))
        resp.hangup()
    elif digits == "2":
        # Nurse advice
        resp.say(translate("Connecting you to Nurse. Please hold.", lang), voice="alice", language=lang_to_voice(lang))
        resp.dial(DEPARTMENTS["nurse"], timeout=30)
        resp.say(translate("All agents are busy. Please try again later.", lang), voice="alice", language=lang_to_voice(lang))
        resp.hangup()
    elif digits == "3":
        # Pharmacy
        resp.say(translate("Connecting you to Pharmacy. Please hold.", lang), voice="alice", language=lang_to_voice(lang))
        resp.dial(DEPARTMENTS["pharmacy"], timeout=30)
        resp.say(translate("All agents are busy. Please try again later.", lang), voice="alice", language=lang_to_voice(lang))
        resp.hangup()
    elif digits == "9":
        # repeat menu
        gather = Gather(num_digits=1, action=f"/handle-menu?lang={lang}", method="POST")
        gather.say(translate_menu(lang), voice="alice", language=lang_to_voice(lang))
        resp.append(gather)
        resp.say(translate("No input received. Goodbye.", lang), voice="alice", language=lang_to_voice(lang))
        resp.hangup()
    elif digits == "0":
        # operator -> record voicemail if operator not available
        resp.say(translate("Please hold while we connect you to an operator.", lang), voice="alice", language=lang_to_voice(lang))
        resp.dial(DEPARTMENTS["operator"], timeout=30)
        resp.say(translate("No operator is available. Please leave a voicemail after the tone.", lang), voice="alice", language=lang_to_voice(lang))
        # record and post to voicemail-callback for processing/store
        resp.record(max_length=120, action="/voicemail-callback", method="POST")
        resp.say(translate("Thank you. Goodbye.", lang), voice="alice", language=lang_to_voice(lang))
        resp.hangup()
    else:
        resp.say(translate("Invalid option. Goodbye.", lang), voice="alice", language=lang_to_voice(lang))
        resp.hangup()

    return twiml_response(resp)

@app.route("/voicemail-callback", methods=["POST"])
def voicemail_callback():
    # Twilio will send RecordingUrl, RecordingSid, RecordingDuration etc.
    recording_url = request.values.get("RecordingUrl")
    recording_sid = request.values.get("RecordingSid")
    duration = request.values.get("RecordingDuration")
    from_number = request.values.get("From")
    # TODO: persist this to S3 / database or POST to your backend
    # For now just return a simple TwiML thanks
    resp = VoiceResponse()
    resp.say("Thank you for your message. Goodbye.", voice="alice", language="en-US")
    resp.hangup()
    # Example: you could asynchronously fetch recording_url and submit to STT
    print(f"Voicemail recording: sid={recording_sid}, url={recording_url}, duration={duration}, from={from_number}")
    return twiml_response(resp)

# --------------- Utility functions --------------------
def lang_to_voice(lang):
    if lang == "hi":
        return "hi-IN"
    if lang == "mr":
        return "mr-IN"
    return "en-US"

def translate(text, lang):
    # Minimal translations (expand as needed)
    mapping = {
        "Connecting you to Appointments. Please hold.": {
            "hi": "आपको अपॉइंटमेंट से जोड़ रहे हैं। कृपया प्रतीक्षा करें।",
            "mr": "आपल्याला अपॉइंटमेंटशी जोडले जात आहे. कृपया थांबा."
        },
        "All agents are busy. Please try again later.": {
            "hi": "सभी एजेंट व्यस्त हैं। कृपया बाद में प्रयास करें।",
            "mr": "सर्व एजंट व्यस्त आहेत. कृपया नंतर प्रयत्न करा."
        },
        "Connecting you to Nurse. Please hold.": {
            "hi": "आपको नर्स से जोड़ रहे हैं। कृपया प्रतीक्षा करें।",
            "mr": "आपल्याला नर्सशी जोडले जात आहे. कृपया थांबा."
        },
        "Connecting you to Pharmacy. Please hold.": {
            "hi": "आपको फार्मेसी से जोड़ रहे हैं। कृपया प्रतीक्षा करें।",
            "mr": "आपल्याला फार्मसीशी जोडले जात आहे. कृपया थांबा."
        },
        "Please hold while we connect you to an operator.": {
            "hi": "कृपया प्रतीक्षा करें, हम आपको ऑपरेटर से जोड़ रहे हैं।",
            "mr": "कृपया थांबा, आम्ही तुम्हाला ऑपरेटरशी जोडत आहोत."
        },
        "No input received. Goodbye.": {
            "hi": "कोई इनपुट प्राप्त नहीं हुआ। अलविदा।",
            "mr": "कोणतीही निवड प्राप्त झाली नाही. अलविदा."
        },
        "Invalid option. Goodbye.": {
            "hi": "अमान्य विकल्प। अलविदा।",
            "mr": "अवैध पर्याय. अलविदा."
        },
        "Thank you. Goodbye.": {
            "hi": "धन्यवाद। अलविदा।",
            "mr": "धन्यवाद. अलविदा."
        }
    }
    if text in mapping and lang in mapping[text]:
        return mapping[text][lang]
    return text

def translate_menu(lang):
    if lang == "hi":
        return "बिक्री के लिए 1, नर्स के लिए 2, फार्मेसी के लिए 3, मेन्यू दोहराने के लिए 9, ऑपरेटर के लिए 0 दबाएँ।"
    if lang == "mr":
        return "अपॉइंटमेंटसाठी 1 दाबा, नर्ससाठी 2, फार्मसीसाठी 3, पुन्हा ऐकण्यासाठी 9, ऑपरेटरसाठी 0 दाबा."
    return "For Appointments press 1. For Nurse advice press 2. For Pharmacy press 3. To repeat press 9. To speak to an operator press 0."

# --------------- Outbound call endpoint --------------------
@app.route("/make-call", methods=["POST"])
def make_call():
    """
    JSON body example:
    {
      "to": ["+919876543210", "+919812345678"],   # single or list of numbers
      "twiml_url": "https://your-public-domain/voice"  # optional, defaults to /voice
    }
    """
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

# --------------- run app --------------------
if __name__ == "__main__":
    # For development only. In production, use gunicorn/uwsgi.
    app.run(host="0.0.0.0", port=5000, debug=True)