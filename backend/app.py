# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import uuid
from datetime import datetime
import logging
import requests
import os
from io import BytesIO
from pymongo import MongoClient
import certifi

# --- LOGGING SETUP ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
BOT_TOKEN = "7159490173:AAGUTo8A5if89zNz0bUbA2HBTuj7rkgvozE" 

# --- MONGODB CONNECTION ---
# Connection String របស់អ្នក
MONGO_URI = "mongodb+srv://order_esign_db_user:89k2mXpa4oM1aCj9@cluster0.gtzpgxr.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

try:
    # ភ្ជាប់ទៅ MongoDB ដោយប្រើ certifi ដើម្បីជៀសវាងបញ្ហា SSL
    client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client['esign_shop_db']  # ឈ្មោះ Database
    orders_collection = db['orders'] # ឈ្មោះ Collection (Table)
    
    # Test connection
    client.admin.command('ping')
    logger.info("✅ ជោគជ័យ៖ បានភ្ជាប់ទៅ MongoDB Atlas!")
except Exception as e:
    logger.critical(f"❌ បរាជ័យ៖ មិនអាចភ្ជាប់ទៅ MongoDB បានទេ: {e}")

app = Flask(__name__)
CORS(app) 

# --- API Endpoint: Save Order (Insert to MongoDB) ---
@app.route('/api/v1/save_order', methods=['POST'])
def save_order():
    try:
        data = request.json
        if not data:
            return jsonify({"message": "No data received"}), 400
        
        # Generate unique key
        order_key = str(uuid.uuid4())
        
        # Placeholder link
        personalized_link = f"http://yourdomain.com/downloads/{data.get('user_id', 'unknown')}/{order_key}"
        
        # Prepare data structure
        order_data = {
            'order_key': order_key,
            'user_id': data.get('user_id'),
            'username': data.get('username'),
            'udid': data.get('udid'),
            'payment_option': data.get('payment_option'),
            'completion_time': data.get('completion_time'),
            'link': personalized_link,
            'link_primary': personalized_link,
            'link_secondary': "",
            'save_time': datetime.now().isoformat()
        }
        
        # Insert into MongoDB
        orders_collection.insert_one(order_data)
        
        logger.info(f"✅ Order saved to MongoDB. ID: {order_key}")
        
        return jsonify({
            "status": "success",
            "order_id": order_key,
            "link": personalized_link
        }), 200

    except Exception as e:
        logger.critical(f"Error in /save_order: {e}", exc_info=True)
        return jsonify({"message": "Internal server error"}), 500


# --- API Endpoint: Update Link (Update MongoDB) ---
@app.route('/api/v1/update_link/<order_key>', methods=['POST'])
def update_link(order_key):
    # Check if order exists
    if not orders_collection.find_one({'order_key': order_key}):
        return jsonify({"message": "Order not found"}), 404

    data = request.json
    link_primary = data.get('link1')
    link_secondary = data.get('link2', '') 

    if not link_primary or not link_primary.startswith('http'):
        return jsonify({"message": "Invalid Primary Link format"}), 400

    # Update MongoDB
    result = orders_collection.update_one(
        {'order_key': order_key},
        {'$set': {
            'link': link_primary,
            'link_primary': link_primary,
            'link_secondary': link_secondary,
            'link_updated_at': datetime.now().isoformat()
        }}
    )

    if result.modified_count > 0:
        logger.info(f"🔗 Links updated in MongoDB for order {order_key}")
        return jsonify({
            "status": "success",
            "order_key": order_key,
            "link_primary": link_primary
        }), 200
    else:
        return jsonify({"message": "No changes made or error updating"}), 500


# --- API Endpoint: Delete Order (Delete from MongoDB) ---
@app.route('/api/v1/delete_order/<order_key>', methods=['DELETE'])
def delete_order(order_key):
    result = orders_collection.delete_one({'order_key': order_key})
    
    if result.deleted_count > 0:
        logger.info(f"🗑️ Order deleted from MongoDB: {order_key}")
        return jsonify({"status": "success", "message": f"Order {order_key} deleted."}), 200
    else:
        return jsonify({"message": "Order not found"}), 404


# --- API Endpoint: Send Link to User ---
@app.route('/api/v1/send_link', methods=['POST'])
def send_link_to_user_from_admin():
    data = request.json
    user_id = data.get('user_id')
    link_primary = data.get('link_primary') 
    link_secondary = data.get('link_secondary', '') 

    if not user_id or not link_primary:
        return jsonify({"message": "Missing user_id or primary link"}), 400
    
    user_id = str(user_id)
    results = {}
    
    # Check file type
    is_file = link_primary.lower().endswith(('.zip', '.ipa', '.apk', '.exe', '.dmg', '.pdf', '.mobileprovision'))
    
    # --- 1. Send Text Message ---
    secondary_text = f"\n🔗 [ Download Certificate ]({link_secondary})" if link_secondary else ""
    caption_text = (
        f"✅ *Your Order is Ready!*  \n\n"
        f"👉🏻 *Download Link:* 👇🏻 \n"
        f"🔗 [ Install Esign ]({link_primary}) \n\n"
        f"{secondary_text}\n"
        f"📦 _If the main link is a file, we are attempting to attach it below..._\n"
        f"Thank you! 🎉"
    )
    
    try:
        text_response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={'chat_id': user_id, 'text': caption_text, 'parse_mode': 'Markdown'},
            timeout=10
        )
        text_response.raise_for_status()
        results['text_status'] = "✅ Text message sent."
        
        # Update completion time in MongoDB
        # We search by user_id and link to find the specific order if possible, or just update based on user_id
        # Note: Ideally we should pass order_key here, but based on your old logic:
        orders_collection.update_many(
            {'user_id': int(user_id), 'link_primary': link_primary},
            {'$set': {'completion_time': datetime.now().isoformat()}}
        )

    except Exception as e:
        results['text_status'] = f"❌ Failed to send text: {str(e)}"
        logger.error(f"❌ Failed to send text to {user_id}: {e}")
    
    # --- 2. Send File ---
    file_sent = False
    if is_file:
        # Direct URL Method
        try:
            logger.info(f"🔄 Sending file via URL: {link_primary}")
            resp = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                data={'chat_id': user_id, 'document': link_primary, 'caption': '📥 Here is your file attachment.'},
                timeout=60
            )
            if resp.status_code == 200:
                results['file_status'] = "✅ File sent via Direct URL"
                file_sent = True
        except Exception as e:
            logger.warning(f"⚠️ Direct URL failed: {e}")

        # Re-upload Method
        if not file_sent:
            try:
                logger.info("🔄 Downloading to re-upload...")
                file_resp = requests.get(link_primary, timeout=120, stream=True)
                if file_resp.status_code == 200:
                    filename = link_primary.split('/')[-1].split('?')[0] or "download.zip"
                    files = {'document': (filename, BytesIO(file_resp.content), 'application/octet-stream')}
                    resp = requests.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                        data={'chat_id': user_id, 'caption': '📥 File (Re-uploaded)'},
                        files=files,
                        timeout=120
                    )
                    if resp.status_code == 200:
                        results['file_status'] = "✅ File sent via Re-upload"
            except Exception as e:
                logger.error(f"❌ Re-upload failed: {e}")
    
    return jsonify({"status": "success", "details": results}), 200


# --- Admin Endpoint: Get All Orders (Fetch from MongoDB) ---
@app.route('/admin/orders')
def view_orders():
    try:
        # Fetch all orders excluding the MongoDB internal _id object
        cursor = orders_collection.find()
        
        # Convert to Dictionary format to match frontend expectation { "order_key": {data}, ... }
        orders_dict = {}
        for doc in cursor:
            # Convert ObjectId to string just in case
            if '_id' in doc:
                doc['_id'] = str(doc['_id'])
            
            key = doc.get('order_key')
            if key:
                orders_dict[key] = doc
                
        return jsonify(orders_dict)
    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        return jsonify({}), 500


# --- Route for HTML Page ---
@app.route('/admin')
def admin_panel():
    return render_template('index.html') 

if __name__ == '__main__':
    print("🚀 Starting Flask Backend with MongoDB...")

    app.run(debug=True, host='0.0.0.0', port=5000)