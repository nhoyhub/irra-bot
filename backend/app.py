# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
from flask_cors import CORS
import uuid
from datetime import datetime
import logging
import requests
from pymongo import MongoClient
import certifi

# --- LOGGING ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
BOT_TOKEN = "7159490173:AAGUTo8A5if89zNz0bUbA2HBTuj7rkgvozE"
MONGO_URI = "mongodb+srv://order_esign_db_user:89k2mXpa4oM1aCj9@cluster0.gtzpgxr.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# --- MONGODB CONNECTION ---
try:
    client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client['esign_shop_db']
    orders_collection = db['orders']
    client.admin.command('ping')
    logger.info("✅ Connected to MongoDB Atlas!")
except Exception as e:
    logger.critical(f"❌ MongoDB Failed: {e}")

app = Flask(__name__)
# Allow all origins for local HTML testing
CORS(app, resources={r"/*": {"origins": "*"}})

@app.route('/')
def home():
    return "Backend is Running! Open index.html to view dashboard."

# --- API: Save Order ---
@app.route('/api/v1/save_order', methods=['POST'])
def save_order():
    try:
        data = request.json
        order_key = str(uuid.uuid4())
        
        user_id = data.get('user_id')
        personalized_link = f"http://yourdomain.com/downloads/{user_id}/{order_key}"
        
        # Get completion_time from Bot
        completion_time = data.get('completion_time')
        
        order_data = {
            'order_key': order_key,
            'user_id': user_id,
            'username': data.get('username'),
            'udid': data.get('udid'),
            'payment_option': data.get('payment_option'),
            'completion_time': completion_time,  
            'link': personalized_link,
            'link_primary': personalized_link,
            'link_secondary': "",
            'save_time': datetime.now().isoformat()
        }
        
        orders_collection.insert_one(order_data)
        logger.info(f"✅ Order Saved: {order_key} for User {user_id}")
        return jsonify({"status": "success", "order_id": order_key}), 200
    except Exception as e:
        logger.error(f"❌ DB Save Error: {e}")
        return jsonify({"message": str(e)}), 500

# --- API: Update Link ---
@app.route('/api/v1/update_link/<order_key>', methods=['POST'])
def update_link(order_key):
    try:
        data = request.json
        link1 = data.get('link1')
        link2 = data.get('link2', '')

        result = orders_collection.update_one(
            {'order_key': order_key},
            {'$set': {'link': link1, 'link_primary': link1, 'link_secondary': link2}}
        )
        if result.modified_count > 0:
            return jsonify({"status": "success"}), 200
        else:
            return jsonify({"status": "no change or not found"}), 404
    except Exception as e:
        return jsonify({"message": str(e)}), 500

# --- API: Delete Order ---
@app.route('/api/v1/delete_order/<order_key>', methods=['DELETE'])
def delete_order(order_key):
    orders_collection.delete_one({'order_key': order_key})
    return jsonify({"status": "success"}), 200

# --- API: Send Link to Telegram User (NEW UI) ---
@app.route('/api/v1/send_link', methods=['POST'])
def send_link():
    data = request.json
    user_id = data.get('user_id')
    link_primary = data.get('link_primary')
    link_secondary = data.get('link_secondary', '')

    if not user_id or not link_primary:
        return jsonify({"message": "Missing Data"}), 400

    # 🎨 NEW UI WITH SOCIAL MEDIA LINKS
    msg_text = (
        "🎉 <b>ការបញ្ជាទិញជោគជ័យ | ORDER COMPLETED</b>\n"
        "──────────────────────\n\n"
        "🙏 អរគុណសម្រាប់ការគាំទ្រ! ខាងក្រោមនេះគឺជាលីងសម្រាប់ដំឡើងរបស់អ្នក៖\n"
        "<i>(Thank you for your support! Here are your download links)</i>\n\n"
        
        "👇 <b>DOWNLOAD HERE:</b>\n"
        f"📱 <a href='{link_primary}'><b>Click to Install Esign App</b></a>\n"
    )
    
    if link_secondary:
        msg_text += f"📂 <a href='{link_secondary}'><b>Click to Download Certificate</b></a>\n"
    
    # 👇 UPDATE YOUR LINKS BELOW 👇
    msg_text += (
        "\n──────────────────────\n"
        "👤 <b>Follow Us & Support:</b>\n"
        "💬 <a href='https://t.me/irra_11'>Telegram Owner</a>\n"
        "🌐 <a href='https://www.irra.store'>Website</a>\n"
    )

    try:
        # 1. Send Message (HTML Mode)
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json={
            'chat_id': user_id, 
            'text': msg_text, 
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        })
        
        if resp.status_code != 200:
            print(f"❌ Telegram Error: {resp.text}")
            return jsonify({"message": f"Telegram Error: {resp.text}"}), 400

        # 2. Try Send File (If it is a file)
        if link_primary.lower().endswith(('.zip', '.ipa', '.pdf', '.mobileprovision')):
            try:
                requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                    data={'chat_id': user_id, 'document': link_primary}
                )
            except:
                pass 

        return jsonify({"status": "success", "message": "Sent successfully!"}), 200

    except Exception as e:
        return jsonify({"message": str(e)}), 500

# --- API: Get Orders for Admin Panel ---
@app.route('/admin/orders')
def get_orders():
    try:
        cursor = orders_collection.find()
        orders_dict = {}
        for doc in cursor:
            if '_id' in doc: doc['_id'] = str(doc['_id'])
            key = doc.get('order_key')
            if key: orders_dict[key] = doc
        return jsonify(orders_dict)
    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        return jsonify({}), 500

if __name__ == '__main__':
    print("🚀 Flask Backend Running on port 5000...")
    app.run(debug=True, host='0.0.0.0', port=5000)