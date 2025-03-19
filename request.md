我想要寫一個linebot
實現以下功能

1. 第一次打開時自動註冊帳號
要求填入姓名電話等資訊
2. 設定要到達的目的地 人數
3.自動匹配相近目的地的用戶 四人一組
4.隨機抽取出一位隊長 
發送給隊長三名隊員的資訊
並發送給三名隊員隊長的資訊
5.要求隊長輸入欲選擇的車牌號碼
6.將車牌號碼發送給三名隊員

cd taxi-linebot
git init
git add .
git commit -m "feat: 完成基本註冊與目的地設定功能"
git branch -M main
git remote add origin https://github.com/terrylin5421/taxi-linebot.git
git push -u origin main
家用電腦繼續開發步驟：
git clone https://github.com/terrylin5421/taxi-linebot.git
cd taxi-linebot
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
後續操作檢查清單：
# 待完成功能與設定
- [ ] 申請Google Maps API金鑰（需信用卡）
- [ ] 在Google Cloud啟用Geocoding API
- [ ] 將API金鑰填入.env檔案
- [ ] 實作基於地理位置的配對算法
- [ ] 開發隊長選擇機制
- [ ] 測試多人配對流程

# 注意事項
1. 首次執行前需先啟動MongoDB服務：
```bash
mongod --dbpath ./data/db
本地測試需同時開啟兩個終端機分別執行：
flask run
ngrok http 5000