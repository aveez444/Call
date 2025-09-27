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

# Replace these with real destination numbers in E.164
DEPARTMENTS = {
    "appointments": "+919999999999",   # used only if you want to dial clinic directly
    "emergency": "+911112223334",
    "callback_owner": "+919888888888"  # your system/user to receive callback alerts (optional)
}

def twiml_response(twiml):
    return Response(str(twiml), mimetype="text/xml")


# ---------------- Main entrypoint ----------------
@app.route("/voice", methods=["POST", "GET"])
def voice():
    """Main menu: 1 Appointments, 2 Emergency, 3 Pathology"""
    resp = VoiceResponse()
    base = request.url_root.rstrip("/")  # absolute base URL that Twilio can reach

    gather = Gather(num_digits=1, action=f"{base}/handle-main", method="POST", timeout=8)
    gather.say("Welcome to HealthyCare Clinic. For appointment booking press 1. For emergency help press 2. For pathology tests press 3.", voice="alice", language="en-US")
    resp.append(gather)

    resp.say("We did not receive any input. Goodbye.", voice="alice", language="en-US")
    resp.hangup()
    return twiml_response(resp)


# ---------------- Handle main selection ----------------
@app.route("/handle-main", methods=["POST"])
def handle_main():
    digits = request.values.get("Digits", "")
    resp = VoiceResponse()
    base = request.url_root.rstrip("/")

    if digits == "1":
        # Appointment: ask which doctor
        gather = Gather(num_digits=1, action=f"{base}/handle-appointment-doctor", method="POST", timeout=8)
        gather.say("For appointment booking. For Dental press 1. For General Doctor press 2. For Orthopaedic press 3.", voice="alice", language="en-US")
        resp.append(gather)
        resp.say("No input received. Returning to main menu.", voice="alice", language="en-US")
        resp.redirect(f"{base}/voice", method="POST")
        return twiml_response(resp)

    elif digits == "2":
        # Emergency - dial emergency number immediately
        resp.say("Connecting you to emergency services. Please hold.", voice="alice", language="en-US")
        resp.dial(DEPARTMENTS["emergency"], timeout=30)
        resp.say("Unable to connect to emergency number. Goodbye.", voice="alice", language="en-US")
        resp.hangup()
        return twiml_response(resp)

    elif digits == "3":
        # Pathology submenu
        gather = Gather(num_digits=1, action=f"{base}/handle-pathology", method="POST", timeout=8)
        gather.say("Pathology tests. For regular blood test press 1. For full body profile press 2. For heart check up press 3.", voice="alice", language="en-US")
        resp.append(gather)
        resp.say("No input received. Returning to main menu.", voice="alice", language="en-US")
        resp.redirect(f"{base}/voice", method="POST")
        return twiml_response(resp)

    else:
        resp.say("Invalid selection. Goodbye.", voice="alice", language="en-US")
        resp.hangup()
        return twiml_response(resp)


# ---------------- Appointment doctor handler ----------------
@app.route("/handle-appointment-doctor", methods=["POST"])
def handle_appointment_doctor():
    digits = request.values.get("Digits", "")
    resp = VoiceResponse()
    # Map digits to doctor types
    doctor_map = {"1": "Dental", "2": "General Practitioner", "3": "Orthopaedic"}

    doc = doctor_map.get(digits)
    if doc:
        # Confirm and offer to record additional info (optional)
        resp.say(f"Thank you. You selected {doc}. Our team will call you soon to schedule a convenient time.", voice="alice", language="en-US")
        # Optional: record a short message (caller can leave details)
        resp.say("If you would like to leave a short message with your preferred time or details, please record after the tone. Press hash when finished.", voice="alice", language="en-US")
        resp.record(max_length=60, finish_on_key="#", action=f"{request.url_root.rstrip('/')}/handle-recording?type=appointment&doctor={doc}", method="POST")
        resp.say("Thank you. Goodbye.", voice="alice", language="en-US")
        resp.hangup()
        return twiml_response(resp)
    else:
        resp.say("Invalid selection. Returning to main menu.", voice="alice", language="en-US")
        resp.redirect(f"{request.url_root.rstrip('/')}/voice", method="POST")
        return twiml_response(resp)


# ---------------- Pathology handler ----------------
@app.route("/handle-pathology", methods=["POST"])
def handle_pathology():
    digits = request.values.get("Digits", "")
    resp = VoiceResponse()
    test_map = {"1": "Regular blood test", "2": "Full body profile", "3": "Heart check up"}

    test = test_map.get(digits)
    if test:
        resp.say(f"Thank you. You selected {test}. Our staff will call you shortly to arrange an appointment and share instructions.", voice="alice", language="en-US")
        # Optional: let caller leave a message with preferred timing
        resp.say("If you want to leave a message for preferred timing, record after the tone. Press hash when finished.", voice="alice", language="en-US")
        resp.record(max_length=60, finish_on_key="#", action=f"{request.url_root.rstrip('/')}/handle-recording?type=pathology&test={test}", method="POST")
        resp.say("Thank you. Goodbye.", voice="alice", language="en-US")
        resp.hangup()
        return twiml_response(resp)
    else:
        resp.say("Invalid selection. Returning to main menu.", voice="alice", language="en-US")
        resp.redirect(f"{request.url_root.rstrip('/')}/voice", method="POST")
        return twiml_response(resp)


# ---------------- Recording callback ----------------
@app.route("/handle-recording", methods=["POST"])
def handle_recording():
    # Twilio posts RecordingUrl, RecordingSid, RecordingDuration, From, etc.
    recording_url = request.values.get("RecordingUrl")
    recording_sid = request.values.get("RecordingSid")
    duration = request.values.get("RecordingDuration")
    caller = request.values.get("From")
    # Optional: type and extra info passed as query string
    rtype = request.args.get("type")
    extra = request.args.get("doctor") or request.args.get("test")

    # TODO: persist recording_url + metadata to DB or S3 or notify staff
    print(f"Received recording: sid={recording_sid}, url={recording_url}, duration={duration}, from={caller}, type={rtype}, extra={extra}")

    resp = VoiceResponse()
    resp.say("Your message has been recorded. We will contact you soon. Goodbye.", voice="alice", language="en-US")
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


# ---------------- Run (dev only) ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
