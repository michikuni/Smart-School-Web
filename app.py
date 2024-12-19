from flask import Flask, render_template, request, jsonify
import threading
import paho.mqtt.client as mqtt
import time
import json
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime

from flask_mqtt import logger

app = Flask(__name__)

# Cấu hình MQTT
MQTT_BROKER = "192.168.2.114"
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
            print(student_from_db)
            student_data = fetch_data_firebase(student_from_db['student_id'])
        compare_data()

def compare_data():
    if student_from_db and student_data:
        # print(student_data['state'])
        if student_data['state'] == 0:
            print("check in")
            check_in_date = student_data['date']
            check_in_time = student_data['time']
            students_attendance_add = {
                "checkin": check_in_time,
                "checkout": None,
                "date": check_in_date,
                "state": 1,
                "student_name": student_from_db['student_name']
            }
            students_face_update = {
                "date": check_in_date,
                "state": 1,
                "student_name": student_from_db['student_name'],
                "time": check_in_time
            }
            face_path = "recognized_faces/" + student_from_db['student_id']
            attendance_path = 'students_attendance/' + student_from_db['student_id']
            update_data(attendance_path, students_attendance_add)
            update_data(face_path, students_face_update)
            message = "1_" + student_data['student_name'] + "_" + student_from_db['student_id'] + "_checkin"
            mqtt_client.publish(MQTT_SUB, message)
        else:
            print("check out")
            current_date_time = datetime.now()
            check_in_time = datetime.strptime(student_data['time'], "%H:%M:%S").time()
            check_in_date = datetime.strptime(student_data['date'], "%d-%m-%Y").date()
            check_in_date_time = datetime.combine(check_in_date, check_in_time)
            isSameDay = current_date_time.date() == check_in_date
            isFinishSession = (current_date_time - check_in_date_time).total_seconds() > session_time * 60

            if isSameDay and isFinishSession:
                students_attendance_update = {
                    "checkin": check_in_time.strftime("%H:%M:%S"),
                    "checkout": current_date_time.time().strftime("%H:%M:%S"),
                    "date": check_in_date.strftime("%d-%m-%Y"),
                    "state": 0,
                    "student_name": student_from_db['student_name']
                }
                students_face_update = {
                    "date": check_in_date.strftime("%d-%m-%Y"),
                    "state": 0,
                    "student_name": student_from_db['student_name'],
                    "time": check_in_time.strftime("%H:%M:%S")
                }
                face_path = "recognized_faces/" + student_from_db['student_id']
                attendance_path = 'students_attendance' + "/" + student_from_db['student_id']
                update_data(attendance_path, students_attendance_update)
                update_data(face_path, students_face_update)
                print("check out successful")
                message = "1_" + student_data['student_name'] + "_" + student_from_db['student_id'] + "_checkout"
                mqtt_client.publish(MQTT_SUB, message)
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
        ref = db.reference(f"{path}/{cardId}")  # Đường dẫn tới node "users"
        results = ref.get()  # Lọc theo điều kiện

        if not results:
            return {"message": "No data found"}, 404
        return results
    except Exception as e:
        return {"error": str(e)}, 500
    
def fetch_data_firebase(student_id):
    try:
        ref = db.reference('recognized_faces')
        return ref.child(student_id).get()
    except Exception as e:
        return {"error": str(e)}, 500

all_student_data = []
def fetch_all_data():
    global all_student_data
    try:
        ref = db.reference('students_attendance')
        all_student_data = ref.get()
        print(all_student_data)
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

@app.route('/')
def index():
    return render_template("index.html", students=all_student_data, student_id=student_id)

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
    app.run(host='127.0.0.1', port=5000)
