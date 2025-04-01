# --- message_templates.py ---
from linebot.models import (
    TextSendMessage, TemplateSendMessage, ButtonsTemplate,
    PostbackAction, URIAction, FlexSendMessage
)
from datetime import datetime

# 直接在此定義狀態常量，避免 import models
STATE_NONE = None
STATE_AWAITING_REG_NAME = 'awaiting_reg_name'
STATE_AWAITING_REG_PHONE = 'awaiting_reg_phone'
STATE_AWAITING_DESTINATION = 'awaiting_destination'
STATE_AWAITING_PASSENGERS = 'awaiting_passengers'
STATE_AWAITING_FEEDBACK = 'awaiting_feedback'

MATCH_STATUS_ACTIVE = 'active'
MATCH_STATUS_CANCELLED = 'cancelled'

# --- Template Generation Functions ---

def create_ask_for_registration():
    return TemplateSendMessage(
        alt_text='歡迎註冊',
        template=ButtonsTemplate(
            title='👋 歡迎使用共乘計程車',
            text='首次使用請先完成註冊，只需兩步！',
            actions=[
                PostbackAction(label='📝 開始註冊', data='action=register'),
                PostbackAction(label='❓ 了解更多', data='action=help')
            ]
        )
    )

def create_registration_success(user_name: str):
    return [
        TextSendMessage(text=f'✅ 註冊成功！歡迎使用共乘計程車服務，{user_name}。'),
        create_main_menu(user_name)
    ]

def create_main_menu(user_name: str):
    return TemplateSendMessage(
        alt_text='功能選單',
        template=ButtonsTemplate(
            title='共乘計程車服務',
            text=f'Hi {user_name}, 請選擇功能：',
            actions=[
                PostbackAction(label='設定目的地', data='action=set_destination'),
                PostbackAction(label='開始配對', data='action=start_matching'),
                PostbackAction(label='使用說明', data='action=help'),
                PostbackAction(label='意見回饋', data='action=feedback')
            ]
        )
    )

def create_help():
    help_text = """
📱 共乘計程車服務使用說明：

1️⃣ **註冊**：(首次使用) 輸入姓名和手機完成綁定。
2️⃣ **設定目的地**：點選按鈕，分享您要去的地點。
3️⃣ **設定人數**：輸入包含您在內的總搭乘人數 (1-4人)。
4️⃣ **開始配對**：系統將根據目的地和時間，為您尋找附近的共乘夥伴。
5️⃣ **配對通知**：成功找到夥伴後，您會收到通知，包含共乘資訊和地圖連結。
6️⃣ **取消**：
   - 搜尋中可「取消搜尋」。
   - 配對成功後可「退出共乘」。

💡 **小提示**：
- 目的地越精確，找到的夥伴可能越少，但也越順路。
- 配對可能需要幾分鐘，請耐心等候。
- 如果長時間未配對成功，可能是附近暫無合適夥伴，可稍後再試。

❓ **需要協助或建議？**
- 輸入「客服」或「意見」與我們聯繫。
    """
    return TextSendMessage(text=help_text.strip())

def create_ask_for_destination():
    return TemplateSendMessage(
        alt_text='設定目的地',
        template=ButtonsTemplate(
            title='設定目的地',
            text='請點擊下方按鈕分享您的「目的地」位置：',
            actions=[
                # 使用 Line 內建位置分享
                URIAction(label="📍 分享位置 (目的地)", uri="line://nv/location")
            ]
        )
    )

def create_ask_for_passengers(address: str):
    return [
        TextSendMessage(text=f"📍 已設定目的地：\n{address}"),
        TextSendMessage(text="請問包含您自己，總共有幾位要搭乘？ (請輸入 1-4 的數字)")
    ]

def create_settings_complete(address: str, passengers: int):
    return [
        TextSendMessage(text=f"✓ 設定完成！\n目的地：{address}\n人數：{passengers}人"),
        TemplateSendMessage(
            alt_text='準備開始配對',
            template=ButtonsTemplate(
                title='準備開始',
                text='您已完成設定，是否要開始尋找共乘夥伴？',
                actions=[
                    PostbackAction(label='🚀 開始配對', data='action=start_matching'),
                    PostbackAction(label='✏️ 重新設定', data='action=set_destination'),
                ]
            )
        )
    ]

def create_searching_flex(interval_minutes: int):
     return FlexSendMessage(
         alt_text='📬 正在為您尋找共乘夥伴...',
         contents={ # 保持原來的 Flex 結構
             "type": "bubble",
             "body": {
                 "type": "box", "layout": "vertical",
                 "contents": [
                     {"type": "text", "text": "📬 正在為您尋找共乘夥伴...", "weight": "bold", "size": "md", "wrap": True},
                     {"type": "text", "text": f"⏳ 請稍候，系統每 {interval_minutes} 分鐘進行一次配對...", "size": "sm", "color": "#999999", "margin": "md", "wrap": True},
                     {"type": "box", "layout": "horizontal", "margin": "lg",
                      "contents": [
                          {"type": "text", "text": "🚗💨", "flex": 0, "margin": "sm"},
                          {"type": "box", "layout": "vertical", "flex": 1, "contents": [
                              {"type": "filler"},
                              {"type": "box", "layout": "vertical", "height": "6px", "backgroundColor": "#DEE2E6", "cornerRadius": "sm", "contents": [
                                  {"type": "box", "layout": "horizontal", "height": "100%", "width": "30%", "backgroundColor": "#0D6EFD", "cornerRadius": "sm"}
                              ]},
                              {"type": "filler"}
                          ]}
                      ]}
                 ]
             },
             "footer": {
                 "type": "box", "layout": "vertical", "contents": [{
                     "type": "button", "style": "secondary", "height": "sm",
                     "action": {"type": "postback", "label": "😫 取消搜尋", "data": "action=cancel_pending_match"}
                 }]
             }
         }
     )

def create_match_success_flex(profile_name: str, group_size: int, match_data: dict):
    match_id = match_data['group_id']
    current_passengers = match_data['total_passengers']
    match_time_str = match_data['created_at'].strftime("%Y-%m-%d %H:%M:%S")
    dest_coords = match_data.get('destination_coords')
    map_uri = None
    if dest_coords and len(dest_coords) == 2:
        # Google Maps URI: latitude,longitude
        map_uri = f"https://www.google.com/maps?q={dest_coords[1]},{dest_coords[0]}"

    bubble = {
        "type": "bubble",
        "header": {"type": "box","layout": "vertical","paddingAll": "md", "contents": [{"type": "text","text": "🎉 配對成功！","weight": "bold","size": "xl","color": "#1DB446","align": "center"}]},
        "body": {"type": "box","layout": "vertical","contents": [
            {"type": "text", "text": f"Hi {profile_name}, 您已加入共乘隊伍！", "wrap": True, "size": "md", "margin": "md"},
            {"type": "separator", "margin": "lg"},
            {"type": "box","layout": "vertical","margin": "lg","spacing": "sm","contents": [
                {"type": "box","layout": "baseline","spacing": "sm","contents": [
                    {"type": "text", "text": "目的地", "color": "#aaaaaa", "size": "sm", "flex": 2},
                    {"type": "text", "text": "座標附近", "wrap": True, "color": "#666666", "size": "sm", "flex": 5}]},
                {"type": "box","layout": "baseline","spacing": "sm","contents": [
                    {"type": "text", "text": "隊伍人數", "color": "#aaaaaa", "size": "sm", "flex": 2},
                    {"type": "text", "text": f"{group_size} 人 (共 {current_passengers} 乘客)", "wrap": True, "color": "#666666", "size": "sm", "flex": 5}]},
                {"type": "box","layout": "baseline","spacing": "sm","contents": [
                    {"type": "text", "text": "配對時間", "color": "#aaaaaa", "size": "sm", "flex": 2},
                    {"type": "text", "text": match_time_str, "wrap": True, "color": "#666666", "size": "sm", "flex": 5}]},
                {"type": "box","layout": "baseline","spacing": "sm","contents": [
                    {"type": "text", "text": "配對ID", "color": "#aaaaaa", "size": "sm", "flex": 2},
                    {"type": "text", "text": match_id[:8], "wrap": True, "color": "#666666", "size": "sm", "flex": 5}]},
            ]},
            {"type": "separator", "margin": "lg"},
        ]},
        "footer": {"type": "box","layout": "vertical","spacing": "sm","contents": [],"flex": 0}
    }
    if map_uri:
        bubble["footer"]["contents"].append({
             "type": "button", "style": "primary", "height": "sm",
             "action": {"type": "uri", "label": "📍 查看目的地地圖", "uri": map_uri}
         })
    bubble["footer"]["contents"].append({
        "type": "button", "style": "secondary", "height": "sm",
        "action": {"type": "postback", "label": "😭 我要退出共乘", "data": f"action=cancel_successful_match&match_id={match_id}"}
    })
    return FlexSendMessage(alt_text=f'🎉 配對成功！與 {group_size-1} 位夥伴同行', contents=bubble)

def create_timeout_message(timeout_minutes: int):
    return TextSendMessage(text=f"⏳ 抱歉，已超過 {timeout_minutes} 分鐘，目前找不到合適的共乘夥伴。\n\n您可以稍後再試一次，或嘗試調整目的地。")

def create_match_cancelled_message(match_id: str):
     return TextSendMessage(text=f"⚠️ 您所在的共乘隊伍 (ID: {match_id[:8]}) 因有成員退出導致人數不足，此共乘已自動取消。\n\n您可以重新發起配對。")

def create_member_left_message(match_id: str, leaver_name: str, remaining_count: int):
     return TextSendMessage(text=f"ℹ️ 通知：共乘夥伴「{leaver_name}」已退出隊伍 (ID: {match_id[:8]})。目前隊伍尚有 {remaining_count} 人。")