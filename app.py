import secrets

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
# Cấu hình MQTT
MQTT_BROKER = "192.168.22.76"
MQTT_PORT = 1883
MQTT_TOPIC = "home/test"
MQTT_SUB = "home/sub"
PING_TOPIC = "home/ping"

# Biến lưu trữ dữ liệu nhận được và ping
received_data = {"None"}
ping_time = {"latency": "Calculating..."}

# MQTT Client
mqtt_client = mqtt.Client()
ping_sent_time = None  # Lưu thời gian gửi tin nhắn ping
RFID = ""
session_time = 1
student_data = ""
student_from_db = ""
student_id = []

#Cấu hình firebase admin SDK
cred = credentials.Certificate('firebase-sdk.json')
firebase_admin.initialize_app(cred,{
    'databaseURL': 'https://smart-school-firebase-default-rtdb.asia-southeast1.firebasedatabase.app/'
})

# Hàm kiểm tra và kết nối lại nếu mất kết nối
def ensure_mqtt_connection():
    while True:
        if not mqtt_client.is_connected():
            try:
                print("Attempting to reconnect to MQTT broker...")
                mqtt_client.reconnect()
                print("Reconnected successfully!")
            except Exception as e:
                print(f"Reconnection failed: {e}")
        time.sleep(5)  # Kiểm tra trạng thái kết nối mỗi 5 giây


# Xử lý khi kết nối thành công đến MQTT broker
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Connected to MQTT Broker with result code {rc}")
        client.subscribe(MQTT_TOPIC)
        client.subscribe(PING_TOPIC)  # Đăng ký topic dùng cho ping
    else:
        print(f"Failed to connect, return code {rc}")

# Xử lý khi nhận được dữ liệu từ MQTT broker
def on_message(client, userdata, msg):
    # fetch_data_firebase()
    fetch_all_data()
    global received_data, ping_time, ping_sent_time,student_data, student_from_db, student_id
    student_id = list(all_student_data.keys())
    if msg.topic == PING_TOPIC:
        # Xử lý phản hồi ping
        if ping_sent_time:
            latency = (time.time() - ping_sent_time) * 1000  # Tính ping (ms)
            ping_time["latency"] = f"{latency:.2f} ms"
            print(f"Ping: {ping_time['latency']}")
            ping_sent_time = None  # Reset thời gian gửi ping
    else:
        # Xử lý dữ liệu thông thường
        RFID = msg.payload.decode()
        # received_data = RFID
        print(f"Received message: {msg.topic} -> {RFID}")
        student_from_db = get_data_by_id('students', RFID)
        if student_from_db:
            checking_date = datetime.now().strftime('%d-%m-%Y')
            student_data = fetch_data_firebase(checking_date, student_from_db['student_id'])
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
            message = "1_" + student_data['student_name'] + "_" + student_from_db['student_id'] + "_checkin"
            mqtt_client.publish(MQTT_SUB, message)
            print(message)
        else:
            print("check out")

            checkout_time = datetime.now().strftime("%H:%M:%S")
            ref_attendance = db.reference(f"students_attendance/{student_data['date']}".strip())
            data_attendance = ref_attendance.child(f"{student_from_db['student_id']}".strip())
            data_attendance.update({'checkout': f'{checkout_time}'})

            message = "1_" + student_data['student_name'] + "_" + student_from_db['student_id'] + "_checkout"
            mqtt_client.publish(MQTT_SUB, message)
            current_date_time = datetime.now()

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
            return {"message": "No data found"}, 404
        return results
    except Exception as e:
        return {"error": str(e)}, 500

def fetch_data_firebase(checking_date, student_id):
    try:
        ref = db.reference(f'recognized_faces/{checking_date}'.strip())
        return ref.child(student_id).get()
    except Exception as e:
        return {"error": str(e)}, 500

all_student_data = []
def fetch_all_data():
    global all_student_data
    try:
        ref = db.reference('students_attendance')
        all_student_data = ref.get()
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
def fetch_data_by_date(date):
    try:
        # Tham chiếu đến ngày cụ thể
        ref = db.reference(f'students_attendance/{date}')
        data = ref.get()
        # print(data)
        # print(date)
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
        admins = admins_ref.get()  # Lấy toàn bộ dữ liệu admin

        # So sánh email và password
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
        # Chuyển đổi ngày sang định dạng ngày/tháng/năm
        formatted_date = datetime.strptime(selected_date, '%Y-%m-%d').strftime('%d-%m-%Y')
        attendance_data = fetch_data_by_date(formatted_date)
        return jsonify({"date": formatted_date, "attendance": attendance_data})
    except ValueError:
        return jsonify({"error": "Invalid date format"}), 400
@app.route('/checkout_all', methods=['POST'])
def checkout_all():
    checkout_data = request.get_json()
    checkout_date = checkout_data.get('dateCheckout')
    if not checkout_date:
        return jsonify ({'message': 'No date provided'}), 400
    formatted_date_checkout = datetime.strptime(checkout_date, '%Y-%m-%d').strftime('%d-%m-%Y')
    checkout_time = datetime.now().strftime('%H:%M:%S')
    print(f'Checkout date: {formatted_date_checkout}')
    ref = db.reference(f'students_attendance/{formatted_date_checkout}')
    data_checkout = ref.get()
    for key, value in data_checkout.items():
        if 'checkin' in value and value['checkin']:
            ref.child(key).update({'state':'1', 'checkout':f'{checkout_time}'})

    print(data_checkout)

if __name__ == "__main__":
    # Khởi động MQTT client trong luồng riêng
    mqtt_thread = threading.Thread(target=start_mqtt)
    mqtt_thread.daemon = True
    mqtt_thread.start()

    # Khởi động luồng kiểm tra kết nối
    reconnect_thread = threading.Thread(target=ensure_mqtt_connection)
    reconnect_thread.daemon = True
    reconnect_thread.start()

    # Khởi động luồng gửi ping
    ping_thread = threading.Thread(target=send_ping)
    ping_thread.daemon = True
    ping_thread.start()


    # Chạy Flask server
    app.run(host='127.0.0.1', port=5003 )
