from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, 
    TextMessage, 
    TextSendMessage,
    TemplateSendMessage,
    ButtonsTemplate,
    PostbackAction,
    PostbackEvent
)
from config import Config
from models import User

app = Flask(__name__)
app.config.from_object(Config)

line_bot_api = LineBotApi(app.config['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(app.config['LINE_CHANNEL_SECRET'])

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
        # 已註冊用戶處理
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f'歡迎回來, {user["name"]}!')
        )

# 用於追蹤用戶註冊狀態
registration_states = {}

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

# 用於追蹤用戶設定狀態
setting_states = {}

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
                        TextSendMessage(text=f'設定完成！目的地：{user["destination"]}，人數：{user["passengers"]}人。')
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
            TextSendMessage(text='請輸入您的目的地：')
        )

if __name__ == "__main__":
    app.run(debug=app.config['DEBUG'])
