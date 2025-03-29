```bash
mongod --dbpath ./data/db
```
本地測試需同時開啟兩個終端機分別執行：
```bash
flask run
ngrok http 5000
```