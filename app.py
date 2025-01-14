import secrets
from flask_socketio import SocketIO, emit
from flask import Flask, render_template, request, jsonify, redirect, session, url_for, make_response
import threading
import paho.mqtt.client as mqtt
import time
import json
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime

from flask_mqtt import logger

app = Flask(__name__)
app.secret_key = secrets.token_hex((24))
socketio = SocketIO(app, cors_allowed_origins="*")

# Cấu hình MQTT
MQTT_BROKER = "192.168.22.99"
MQTT_PORT = 1883
MQTT_TOPIC = "home/test"
MQTT_SUB = "home/sub"
PING_TOPIC = "home/ping"

# Biến lưu trữ dữ liệu nhận được và ping
received_data = {"None"}
ping_time = {"latency": "Calculating..."}

# MQTT Client
mqtt_client = mqtt.Client()
ping_sent_time = None
RFID = ""
session_time = 1
student_data = ""
student_from_db = ""
student_id = []

# Cấu hình firebase admin SDK
cred = credentials.Certificate('firebase-sdk.json')
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://smart-school-firebase-default-rtdb.asia-southeast1.firebasedatabase.app/'
})


def start_firebase_listener():
    def stream_handler(event):
        """Xử lý khi có thay đổi trong database"""
        if event.data:
            socketio.emit('database_update', {
                'path': event.path,
                'data': event.data
            })

    ref = db.reference('students_attendance')
    ref.listen(stream_handler)


def ensure_mqtt_connection():
    while True:
        if not mqtt_client.is_connected():
            try:
                print("Attempting to reconnect to MQTT broker...")
                mqtt_client.reconnect()
                print("Reconnected successfully!")
            except Exception as e:
                print(f"Reconnection failed: {e}")
        time.sleep(5)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Connected to MQTT Broker with result code {rc}")
        client.subscribe(MQTT_TOPIC)
        client.subscribe(PING_TOPIC)
    else:
        print(f"Failed to connect, return code {rc}")


def on_message(client, userdata, msg):
    global received_data, ping_time, ping_sent_time, student_data, student_from_db
    checking_date = datetime.now().strftime('%d-%m-%Y')
    all_student_id = str(list(fetch_data_by_date(checking_date).keys()))
    for key in all_student_id:
        all_student_data = fetch_data_firebase(checking_date, key)
        if all_student_data and key:
            socketio.emit('data_update', {
                'student_id': key,
                'student_name': all_student_data['student_name'],
                'state': all_student_data['state'],
                'date': checking_date
            })
    if msg.topic == PING_TOPIC:
        if ping_sent_time:
            latency = (time.time() - ping_sent_time) * 1000
            ping_time["latency"] = f"{latency:.2f} ms"
            print(f"Ping: {ping_time['latency']}")
            ping_sent_time = None
    else:
        RFID = msg.payload.decode()
        print(f"Received message: {msg.topic} -> {RFID}")
        student_from_db = get_data_by_id('students', RFID)
        if student_from_db:
            student_data = fetch_data_firebase(checking_date, student_from_db['student_id'])
            # Emit sự kiện khi có dữ liệu mới
            if student_data:
                socketio.emit('data_update', {
                    'student_id': student_from_db['student_id'],
                    'student_name': student_data['student_name'],
                    'state': student_data['state'],
                    'date': checking_date
                })
        compare_data()

def compare_data():
    if student_from_db and student_data:
        # print(student_data['state'])
        if student_data['state'] != "1":
            print("check in")

            ref_attendance = db.reference(f"students_attendance/{student_data['date']}".strip())
            data_attendance = ref_attendance.child(f"{student_from_db['student_id']}".strip())
            data_attendance.update({'state':'1'})

            ref_recog = db.reference(f"recognized_faces/{student_data['date']}".strip())
            data_recog = ref_recog.child(f"{student_from_db['student_id']}".strip())
            data_recog.update({'state':'1'})
            message = "1_" + student_data['student_name'] + "_" + student_from_db['student_id'] + "_checkin_"
            mqtt_client.publish(MQTT_SUB, message)
            print(message)
        else:
            print("check out")
            checkout_time = datetime.now().strftime("%H:%M:%S")
            ref_attendance = db.reference(f"students_attendance/{student_data['date']}".strip())
            data_attendance = ref_attendance.child(f"{student_from_db['student_id']}".strip())
            data_attendance.update({'checkout': f'{checkout_time}'})
            message = "1_" + student_data['student_name'] + "_" + student_from_db['student_id'] + "_checkout_"
            mqtt_client.publish(MQTT_SUB, message)
            print(message)
    else:
        mqtt_client.publish(MQTT_SUB, "0_Unknown")

def update_data(path, update_values):
    try:
        if not path or not update_values:
            raise ValueError("Invalid input: Path or update_values is missing.")

        # Cập nhật dữ liệu trong Firebase
        ref = db.reference(path)
        if ref.get():  # Kiểm tra nếu dữ liệu đã tồn tại
            ref.update(update_values)
            print("Data updated successfully.")
        else:
            ref.set(update_values)  # Thêm mới nếu không tồn tại
            print("Data added successfully.")
    except Exception as e:
        print(f"Error: {str(e)}")
        return {"error": str(e)}, 500

def get_data_by_id(path, cardId):
    try:
        if not cardId:
            raise ValueError("Missing cardId.")

        # Truy vấn Firebase Realtime Database
        ref = db.reference((f"{path}/{cardId}").strip())  # Đường dẫn tới node "users"
        results = ref.get()  # Lọc theo điều kiện

        if not results:
            def_err = db.reference((f"{path}/00000000").strip())
            return def_err.get()
        return results
    except Exception as e:
        def_err = db.reference((f"{path}/00000000").strip())
        return def_err.get()
all_student_data = []
def fetch_data_firebase(checking_date, student_id):
    try:
        ref = db.reference(f'recognized_faces/{checking_date}'.strip())
        return ref.child(str(student_id).upper()).get()
    except Exception as e:
        return {"error": str(e)}, 500



# Hàm gửi tin nhắn ping
def send_ping():
    global ping_sent_time
    while True:
        if mqtt_client.is_connected():
            ping_sent_time = time.time()
            mqtt_client.publish(PING_TOPIC, "ping")
            print("Ping sent.")
        time.sleep(10)  # Gửi ping mỗi 10 giây


# Khởi động MQTT client trong luồng riêng
def start_mqtt():
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        print(f"Initial connection failed: {e}")

    mqtt_client.loop_start()  # Dùng loop_start() để MQTT chạy trong nền

all_student_id = []
def fetch_data_by_date(date):
    try:
        # Tham chiếu đến ngày cụ thể
        ref = db.reference(f'students_attendance/{date}')
        data = ref.get()
        return data
    except Exception as e:
        return {"error": str(e)}, 500


@app.route('/')
def index():
    return render_template("login.html")


@app.route('/login', methods=['POST'])
def login():
    email = request.form.get("email")
    password = request.form.get("password")
    try:
        admins_ref = db.reference('admin')
        admins = admins_ref.get()

        for admin_id, admin_data in admins.items():
            if admin_data['email'] == email and admin_data['password'] == password:
                session['user'] = email
                return redirect("/home_page")
        return "Invalid email or password", 401
    except Exception as e:
        return f"Error: {str(e)}", 400


@app.route('/home_page')
def home_page():
    if 'user' not in session:
        return redirect(url_for('index'))
    response = make_response(render_template("index.html", user=session['user']))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))


@app.route('/submit_date', methods=['POST'])
def submit_date():
    selected_date = request.form['date']
    try:
        formatted_date = datetime.strptime(selected_date, '%Y-%m-%d').strftime('%d-%m-%Y')
        attendance_data = fetch_data_by_date(formatted_date)
        return jsonify({"date": formatted_date, "attendance": attendance_data})
    except ValueError:
        return jsonify({"error": "Invalid date format"}), 400

@app.route('/submit_student_data', methods=['POST'])
def submit_student_data():
    try:
        name = request.form.get('name')
        studentId = request.form.get('studentId')
        rfid_code = request.form.get('rfidCode').upper()

        if not all([name, studentId, rfid_code]):
            return jsonify({
                'status': 'error',
                'message': 'Vui lòng điền đầy đủ thông tin'
            }), 400

        student_ref = db.reference('students')
        student_ref.child(rfid_code).set({
            'student_name': name,
            'student_id': studentId,
            'rfid_code': rfid_code
        })

        return jsonify({
            'status': 'success',
            'message': 'Đã thêm thông tin học sinh thành công'
        })

    except Exception as e:
        return jsonify({
            'status' : 'error',
            'message' : f'Lỗi: {str(e)}'
        }), 500

@app.route('/checkout_all', methods=['POST'])
def checkout_all():
    checkout_data = request.get_json()
    checkout_date = checkout_data.get('dateCheckout')
    if not checkout_date:
        return jsonify({'message': 'No date provided'}), 400

    formatted_date_checkout = datetime.strptime(checkout_date, '%Y-%m-%d').strftime('%d-%m-%Y')
    checkout_time = datetime.now().strftime('%H:%M:%S')

    ref = db.reference(f'students_attendance/{formatted_date_checkout}')
    data_checkout = ref.get()

    if data_checkout:
        checkout_count = 0
        for key, value in data_checkout.items():
            # Kiểm tra xem đã điểm danh (state = "1") và chưa checkout
            if value.get('state') == "1" and not value.get('checkout'):
                ref.child(key).update({'checkout': f'{checkout_time}'})
                checkout_count += 1

        # Emit sự kiện sau khi checkout all
        if checkout_count > 0:
            socketio.emit('checkout_update', {'success': True})
            return jsonify({
                'message': f'Successfully checked out {checkout_count} students',
                'count': checkout_count
            })
        else:
            return jsonify({
                'message': 'No students eligible for checkout',
                'count': 0
            })
    return jsonify({'message': 'No data found for the selected date'}), 404


if __name__ == "__main__":
    mqtt_thread = threading.Thread(target=start_mqtt)
    mqtt_thread.daemon = True
    mqtt_thread.start()

    reconnect_thread = threading.Thread(target=ensure_mqtt_connection)
    reconnect_thread.daemon = True
    reconnect_thread.start()

    ping_thread = threading.Thread(target=send_ping)
    ping_thread.daemon = True
    ping_thread.start()

    firebase_thread = threading.Thread(target=start_firebase_listener)
    firebase_thread.daemon = True
    firebase_thread.start()

    socketio.run(app, host='127.0.0.1', port=8000, debug=True)