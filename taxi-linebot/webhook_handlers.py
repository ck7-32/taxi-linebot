# --- webhook_handlers.py ---
import logging
from flask import Blueprint, request, abort, current_app
from linebot import WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent, TextMessage, LocationMessage, PostbackEvent, TextSendMessage
)
from pymongo import ReturnDocument, GEOSPHERE # GEOSPHERE might be needed if re-initializing index here
from datetime import datetime
import re  # 新增 re 模組引入

# Import db, line_bot_api, handler from app setup
from app import db, line_bot_api, handler
# Import logic and templates
import matching_logic
from matching_logic import process_pending_matches, show_loading_indicator
import message_templates

logger = logging.getLogger(__name__)
webhook_bp = Blueprint('webhook', __name__)

# --- Webhook Route ---
@webhook_bp.route("/callback", methods=['POST'])
def callback():
    if line_bot_api is None or handler is None:
        logger.critical("Line Bot API/Handler not initialized.")
        abort(500)
    if db is None:
        logger.critical("DB connection not available.")
        # Don't try to reply if API might be down
        abort(500)

    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    logger.info(f"Request body: {body}")

    if not signature:
        logger.error("Missing X-Line-Signature")
        abort(400)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature.")
        abort(400)
    except LineBotApiError as e:
        logger.error(f"Line API Error: {e.status_code} {e.error.message}")
        abort(500) # Internal server error on API failure
    except Exception as e:
        logger.exception(f"Unhandled exception in handler: {e}")
        abort(500)

    return 'OK'

# --- Helper to get/create user ---
def get_or_create_user(user_id):
    """Finds user or creates a basic record, returning the user dict."""
    if db is None: return None # Should not happen if check in callback works
    return db.users.find_one_and_update(
        {'line_user_id': user_id},
        {'$setOnInsert': {
            'line_user_id': user_id, 'created_at': datetime.now(), 'state': None,
            'name': None, 'phone': None, 'destination': None, 'location': None,
            'address': None, 'passengers': None
        }},
        upsert=True, return_document=ReturnDocument.AFTER
    )

# --- Helper to reply messages (avoids repeating checks) ---
def reply_message_wrapper(reply_token, message):
    if line_bot_api is None:
        logger.error("Cannot reply, Line API not available.")
        return
    try:
        line_bot_api.reply_message(reply_token, message)
    except Exception as e:
        logger.error(f"Failed to reply (token {reply_token[:6]}...): {e}")

# --- Line Event Handlers ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    reply_token = event.reply_token

    if db is None:
        reply_message_wrapper(reply_token, TextSendMessage(text="抱歉，系統資料庫異常，請稍後再試。"))
        return

    user_data = get_or_create_user(user_id)
    user_name = user_data.get('name', '朋友')
    is_registered = user_name and user_data.get('phone')

    # 檢查是否為隊長正在等待輸入車牌
    active_match_as_leader = db.matches.find_one({
        'leader_id': user_id,
        'status': message_templates.STATE_AWAITING_PLATE
    })

    if active_match_as_leader:
        license_plate = text.upper().replace("-", "").replace(" ", "")

        if re.fullmatch(r"^[A-Z0-9]{2,4}[A-Z0-9]{3,4}$", license_plate):
            match_id = active_match_as_leader['group_id']
            members = active_match_as_leader.get('members', [])
            other_members = [m for m in members if m != user_id]

            # 更新資料庫中的配對記錄
            db.matches.update_one(
                {'group_id': match_id},
                {'$set': {
                    'license_plate': license_plate,
                    'status': message_templates.MATCH_STATUS_ACTIVE
                }}
            )
            logger.info(f"Leader {user_id} provided license plate {license_plate} for match {match_id}")

            # 通知隊長成功
            reply_message_wrapper(reply_token, TextSendMessage(text=f"✅ 車牌號碼 {license_plate} 已登記並通知隊員。"))

            # 通知其他成員
            leader_name = user_data.get('name', '隊長')
            plate_message = message_templates.create_license_plate_notification(leader_name, license_plate)
            if line_bot_api:
                for member_id in other_members:
                    try:
                        line_bot_api.push_message(member_id, plate_message)
                    except Exception as e:
                        logger.error(f"Failed to send license plate notification to member {member_id} for match {match_id}: {e}")
            return

        else:
            # 格式無效
            reply_message_wrapper(reply_token, TextSendMessage(text="⚠️ 車牌號碼格式似乎不正確，請重新輸入 (例如 ABC-1234)。"))
            return

    # --- State Machine ---
    if current_state == message_templates.STATE_AWAITING_REG_NAME:
        db.users.update_one({'line_user_id': user_id}, {'$set': {'name': text, 'state': message_templates.STATE_AWAITING_REG_PHONE}})
        reply_message_wrapper(reply_token, TextSendMessage(text='好的，請輸入您的手機號碼 (例如 09xxxxxxxx)：'))

    elif current_state == message_templates.STATE_AWAITING_REG_PHONE:
        if text.isdigit() and len(text) == 10 and text.startswith('09'):
            db.users.update_one({'line_user_id': user_id}, {'$set': {'phone': text, 'state': message_templates.STATE_NONE}})
            # Need the name that was just potentially set
            updated_user = get_or_create_user(user_id)
            messages = message_templates.create_registration_success(updated_user.get('name', '朋友'))
            reply_message_wrapper(reply_token, messages)
        else:
            reply_message_wrapper(reply_token, TextSendMessage(text='⚠️ 手機號碼格式似乎不正確，請輸入有效的10位數字號碼 (例如 0912345678)。'))

    elif current_state == message_templates.STATE_AWAITING_PASSENGERS:
        try:
            passengers = int(text)
            if 1 <= passengers <= 4:
                db.users.update_one({'line_user_id': user_id}, {'$set': {'passengers': passengers, 'state': message_templates.STATE_NONE}})
                address = user_data.get('address', '您設定的位置')
                messages = message_templates.create_settings_complete(address, passengers)
                reply_message_wrapper(reply_token, messages)
            else:
                reply_message_wrapper(reply_token, TextSendMessage(text='⚠️ 人數輸入無效，請輸入 1 到 4 之間的數字。'))
        except ValueError:
            reply_message_wrapper(reply_token, TextSendMessage(text='⚠️ 請輸入數字 1 到 4。'))

    elif current_state == message_templates.STATE_AWAITING_FEEDBACK:
        try:
            db.feedbacks.insert_one({
                'line_user_id': user_id, 'name': user_name or '未知用戶',
                'feedback': text, 'created_at': datetime.now()
            })
            db.users.update_one({'line_user_id': user_id}, {'$set': {'state': message_templates.STATE_NONE}})
            reply_message_wrapper(reply_token, TextSendMessage(text='感謝您的寶貴意見！我們會參考並持續改進服務品質。💪'))
        except Exception as e:
            logger.error(f"Error saving feedback for {user_id}: {e}")
            reply_message_wrapper(reply_token, TextSendMessage(text='抱歉，儲存您的意見時發生錯誤，請稍後再試。'))

    # --- Default State & Keywords ---
    else:
        if not is_registered:
            message = message_templates.create_ask_for_registration()
            reply_message_wrapper(reply_token, message)
            return

        lower_text = text.lower()
        if lower_text in ['使用說明', '幫助', 'help', '?']:
            handle_postback_action(event, user_id, 'action=help')
        elif lower_text in ['客服', '聯繫客服', '意見', '回饋', 'feedback']:
            db.users.update_one({'line_user_id': user_id}, {'$set': {'state': message_templates.STATE_AWAITING_FEEDBACK}})
            reply_message_wrapper(reply_token, TextSendMessage(text='📝 我們很重視您的意見，請分享您的問題、建議或遇到的困難：'))
        elif lower_text in ['設定', '目的地', '重設', 'set destination']:
             handle_postback_action(event, user_id, 'action=set_destination')
        elif lower_text in ['配對', '開始', '找人', 'start matching']:
             handle_postback_action(event, user_id, 'action=start_matching')
        else:
            message = message_templates.create_main_menu(user_name)
            reply_message_wrapper(reply_token, message)


@handler.add(MessageEvent, message=LocationMessage)
def handle_location(event):
    user_id = event.source.user_id
    reply_token = event.reply_token

    if db is None:
        reply_message_wrapper(reply_token, TextSendMessage(text="抱歉，系統資料庫異常，請稍後再試。"))
        return

    user_data = get_or_create_user(user_id)
    is_registered = user_data.get('name') and user_data.get('phone')

    if is_registered and user_data.get('state') == message_templates.STATE_AWAITING_DESTINATION:
        lat = event.message.latitude
        lon = event.message.longitude
        addr = event.message.address or f"經緯度: {lat:.5f}, {lon:.5f}"
        update_data = {
            'destination': [lon, lat], 'location': {'type': 'Point', 'coordinates': [lon, lat]},
            'address': addr, 'state': message_templates.STATE_AWAITING_PASSENGERS
        }
        db.users.update_one({'line_user_id': user_id}, {'$set': update_data})
        messages = message_templates.create_ask_for_passengers(addr)
        reply_message_wrapper(reply_token, messages)
    elif not is_registered:
        reply_message_wrapper(reply_token, TextSendMessage(text="請先完成註冊才能設定目的地喔！"))
    else: # Registered but not in correct state
        reply_message_wrapper(reply_token, TextSendMessage(text="如果您想設定目的地，請先點選主選單的 '設定目的地' 按鈕。"))

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data
    handle_postback_action(event, user_id, data) # Call common handler


# --- Common Handler for Postbacks and Keywords ---
def handle_postback_action(event, user_id, data):
    reply_token = event.reply_token

    if db is None:
        reply_message_wrapper(reply_token, TextSendMessage(text="抱歉，系統資料庫異常，請稍後再試。"))
        return

    user_data = get_or_create_user(user_id)
    is_registered = user_data.get('name') and user_data.get('phone')
    user_name = user_data.get('name', '朋友')

    action = data.split('&')[0]

    if action == 'action=register':
        if is_registered:
            reply_message_wrapper(reply_token, TextSendMessage(text=f"您已經註冊過了，{user_name}！"))
        else:
            db.users.update_one({'line_user_id': user_id}, {'$set': {'state': message_templates.STATE_AWAITING_REG_NAME}})
            reply_message_wrapper(reply_token, TextSendMessage(text='📝 開始註冊囉！請先輸入您的姓名或暱稱：'))

    elif action == 'action=set_destination':
        if not is_registered:
            reply_message_wrapper(reply_token, TextSendMessage(text="請先完成註冊才能設定目的地喔！"))
        else:
            db.users.update_one({'line_user_id': user_id}, {'$set': {'state': message_templates.STATE_AWAITING_DESTINATION}})
            message = message_templates.create_ask_for_destination()
            reply_message_wrapper(reply_token, message)

    elif action == 'action=start_matching':
        if not is_registered:
            reply_message_wrapper(reply_token, TextSendMessage(text="請先完成註冊才能開始配對喔！"))
            return

        # Check requirements directly
        if not (user_data.get('destination') and user_data.get('passengers')):
            reply_message_wrapper(reply_token, TextSendMessage(text='⚠️ 請先透過「設定目的地」完成地點和人數設定，才能開始配對。'))
        elif db.pending_matches.find_one({'line_user_id': user_id}):
             reply_message_wrapper(reply_token, TextSendMessage(text="您目前已經在配對佇列中了，請稍候..."))
        elif db.matches.find_one({'members': user_id, 'status': message_templates.MATCH_STATUS_ACTIVE}):
             reply_message_wrapper(reply_token, TextSendMessage(text="您目前已經在一個進行中的共乘隊伍裡了！"))
        else:
            # Add to pending
            db.pending_matches.insert_one({
                'line_user_id': user_id, 'destination': user_data['destination'],
                'passengers': user_data['passengers'], 'timestamp': datetime.now()
            })
            logger.info(f"User {user_id} added to pending list.")

            # 顯示 LINE 官方載入指示器（30秒）
            show_loading_indicator(user_id, seconds=30)

            # 立即回覆確認訊息（Flex Message）
            interval_minutes = current_app.config['MATCH_INTERVAL_MINUTES']
            message = message_templates.create_searching_flex(interval_minutes)
            reply_message_wrapper(reply_token, message)

    elif action == 'action=help':
        message = message_templates.create_help()
        reply_message_wrapper(reply_token, message)

    elif action == 'action=cancel_pending_match':
        result = db.pending_matches.delete_one({'line_user_id': user_id})
        if result.deleted_count > 0:
            logger.info(f"User {user_id} cancelled pending match request.")
            reply_message_wrapper(reply_token, TextSendMessage(text="✅ 已取消本次的配對搜尋。"))
        else:
            reply_message_wrapper(reply_token, TextSendMessage(text="⚠️ 您目前沒有在等待配對的請求，或請求已被處理。"))

    elif action == 'action=cancel_successful_match':
        try:
            match_id = data.split('&match_id=')[1]
            match = db.matches.find_one({'group_id': match_id, 'status': message_templates.MATCH_STATUS_ACTIVE})

            if match and user_id in match.get('members', []):
                # Remove member
                db.matches.update_one({'group_id': match_id}, {'$pull': {'members': user_id}})
                logger.info(f"User {user_id} left match {match_id}")
                reply_message_wrapper(reply_token, TextSendMessage(text="✅ 您已成功退出此次共乘。"))

                # Check remaining and notify others
                updated_match = db.matches.find_one({'group_id': match_id})
                remaining_members = updated_match.get('members', []) if updated_match else []

                if len(remaining_members) <= 1:
                    logger.info(f"Match {match_id} cancelled due to insufficient members.")
                    db.matches.update_one({'group_id': match_id}, {'$set': {'status': message_templates.MATCH_STATUS_CANCELLED, 'members': remaining_members}})
                    for member_id in remaining_members:
                        if line_bot_api: line_bot_api.push_message(member_id, message_templates.create_match_cancelled_message(match_id))
                else:
                    leaver_name = user_data.get('name', '一位夥伴')
                    for member_id in remaining_members:
                        if line_bot_api: line_bot_api.push_message(member_id, message_templates.create_member_left_message(match_id, leaver_name, len(remaining_members)))

            elif match and user_id not in match.get('members', []):
                reply_message_wrapper(reply_token, TextSendMessage(text="您已不在這個共乘隊伍中了。"))
            else:
                reply_message_wrapper(reply_token, TextSendMessage(text="❌ 找不到指定的配對記錄，或該配對已結束/取消。"))
        except IndexError:
             logger.error(f"Failed to parse match_id from postback data: {data}")
             reply_message_wrapper(reply_token, TextSendMessage(text="❌ 操作失敗，無法識別配對資訊。"))
        except Exception as e:
             logger.exception(f"Error handling cancel_successful_match: {e}")
             reply_message_wrapper(reply_token, TextSendMessage(text="處理退出共乘時發生錯誤。"))

    elif action == 'action=feedback':
        if not is_registered:
            reply_message_wrapper(reply_token, TextSendMessage(text="請先完成註冊才能提供意見喔！"))
        else:
            db.users.update_one({'line_user_id': user_id}, {'$set': {'state': message_templates.STATE_AWAITING_FEEDBACK}})
            reply_message_wrapper(reply_token, TextSendMessage(text="📝 我們很重視您的意見，請分享您的問題、建議或遇到的困難："))

    else:
        logger.warning(f"Received unknown postback action: {data} from user {user_id}")
        reply_message_wrapper(reply_token, TextSendMessage(text="收到未知指令。"))