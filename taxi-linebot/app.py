from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, 
    TextMessage, 
    LocationMessage,
    TextSendMessage,
    TemplateSendMessage,
    ButtonsTemplate,
    PostbackAction,
    PostbackEvent,
    URIAction,
    MessageAction
)
from config import Config
from models import User
import requests

app = Flask(__name__)
app.config.from_object(Config)

line_bot_api = LineBotApi(app.config['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(app.config['LINE_CHANNEL_SECRET'])

# 用於追蹤用戶狀態
registration_states = {}
setting_states = {}

@app.route("/", methods=['POST'])
@app.route("/callback", methods=['POST'])
def callback():
    # 取得請求標頭中的X-Line-Signature
    signature = request.headers['X-Line-Signature']

    # 取得請求主體
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # 驗證簽章
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user = User.find_by_line_user_id(user_id)
    
    if not user:
        # 處理註冊流程
        if user_id in registration_states:
            step = registration_states[user_id]['step']
            
            if step == 'name':
                # 儲存姓名並要求電話
                registration_states[user_id]['name'] = event.message.text
                registration_states[user_id]['step'] = 'phone'
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text='請輸入您的電話號碼：')
                )
            elif step == 'phone':
                # 完成註冊
                name = registration_states[user_id]['name']
                phone = event.message.text
                
                # 建立新用戶
                new_user = User(
                    line_user_id=user_id,
                    name=name,
                    phone=phone
                )
                new_user.save()
                
                # 清除註冊狀態
                del registration_states[user_id]
                
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f'註冊成功！歡迎使用共乘計程車服務，{name}。')
                )
        else:
            # 新用戶註冊流程
            line_bot_api.reply_message(
                event.reply_token,
                TemplateSendMessage(
                    alt_text='註冊表單',
                    template=ButtonsTemplate(
                        title='歡迎使用共乘計程車服務',
                        text='請先完成註冊',
                        actions=[
                            PostbackAction(
                                label='開始註冊',
                                data='action=register'
                            )
                        ]
                    )
                )
            )
    else:
        # 處理設定流程
        if user_id in setting_states:
            step = setting_states[user_id]['step']
            
            if step == 'destination':
                # 儲存目的地並要求人數
                setting_states[user_id]['destination'] = event.message.text
                setting_states[user_id]['step'] = 'passengers'
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text='請輸入乘車人數（1-4人）：')
                )
            elif step == 'passengers':
                # 完成設定
                try:
                    passengers = int(event.message.text)
                    if passengers < 1 or passengers > 4:
                        raise ValueError
                    
                    # 更新用戶資料
                    user['destination'] = setting_states[user_id]['destination']
                    user['passengers'] = passengers
                    db.users.update_one(
                        {'line_user_id': user_id},
                        {'$set': {
                            'destination': user['destination'],
                            'passengers': user['passengers']
                        }}
                    )
                    
                    # 清除設定狀態
                    del setting_states[user_id]
                    
                    line_bot_api.reply_message(
                        event.reply_token,
                        [
                            TextSendMessage(text=f'✓ 設定完成！\n目的地：{user["destination"]}\n人數：{user["passengers"]}人'),
                            TextSendMessage(text='⏳ 正在為您尋找共乘夥伴...\n配對成功將立即通知您！')
                        ]
                    )
                except ValueError:
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text='人數輸入無效，請輸入1到4之間的數字。')
                    )
        else:
            # 已註冊用戶處理
            line_bot_api.reply_message(
                event.reply_token,
                TemplateSendMessage(
                    alt_text='主選單',
                    template=ButtonsTemplate(
                        title='共乘計程車服務',
                        text='請選擇功能',
                        actions=[
                            PostbackAction(
                                label='設定目的地',
                                data='action=set_destination'
                            ),
                            PostbackAction(
                                label='開始配對',
                                data='action=start_matching'
                            )
                        ]
                    )
                )
            )

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data
    
    if data == 'action=register':
        # 開始註冊流程
        registration_states[user_id] = {'step': 'name'}
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text='請輸入您的姓名：')
        )
    elif data == 'action=set_destination':
        # 開始設定目的地流程
        setting_states[user_id] = {'step': 'destination'}
        line_bot_api.reply_message(
            event.reply_token,
            TemplateSendMessage(
                alt_text='設定目的地方式',
                template=ButtonsTemplate(
                    title='設定目的地',
                    text='請選擇設定方式：',
                    actions=[
                        PostbackAction(
                            label='傳送位置',
                            data='action=send_location'
                        ),
                        PostbackAction(
                            label='輸入地址',
                            data='action=enter_address'
                        )
                    ]
                )
            )
        )
    elif data == 'action=send_location':
        line_bot_api.reply_message(
            event.reply_token,
            TemplateSendMessage(
                alt_text="請分享您的位置",
                template=ButtonsTemplate(
                    text="請點擊下方按鈕來分享您的位置",
                    actions=[
                        URIAction(label="分享位置", uri="line://nv/location")
                    ]
                )
            )
        )
    elif data == 'action=enter_address':
        setting_states[user_id] = {'step': 'destination'}
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text='請輸入您的目的地地址：')
        )

@handler.add(LocationMessage)
def handle_location_message(event):
    user_id = event.source.user_id
    user = User.find_by_line_user_id(user_id)
    
    if user and user_id in setting_states:
        # 從位置訊息取得經緯度
        latitude = event.message.latitude
        longitude = event.message.longitude
        
        # 使用Geocoding API取得地址
        maps_api_key = app.config['GOOGLE_MAPS_API_KEY']
        response = requests.get(
            f'https://maps.googleapis.com/maps/api/geocode/json?latlng={latitude},{longitude}&key={maps_api_key}'
        )
        
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'OK':
                address = data['results'][0]['formatted_address']
                
                # 更新用戶資料庫記錄
                db.users.update_one(
                    {'line_user_id': user_id},
                    {'$set': {
                        'destination': address,
                        'location': {
                            'type': 'Point',
                            'coordinates': [longitude, latitude]
                        }
                    }}
                )
                
                # 進入下一步設定乘車人數
                setting_states[user_id]['step'] = 'passengers'
                
                # 回傳確認訊息並要求輸入人數
                line_bot_api.reply_message(
                    event.reply_token,
                    [
                        TextSendMessage(text=f"📍 已設定目的地：\n{address}\n🌐 座標：{latitude:.6f}, {longitude:.6f}"),
                        TextSendMessage(text="請輸入乘車人數（1-4人）：")
                    ]
                )
                return
        
        # 處理API錯誤情況
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="無法取得地址資訊，請稍後再試或改用文字輸入")
        )

if __name__ == "__main__":
    app.run(debug=app.config['DEBUG'])
