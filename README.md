# eternal_force

學生上課 / 購買堂數管理系統（健身教學工作室用）。以 Python Flask 開發，依 SSDLC（安全軟體開發生命週期）流程建置，介面支援 RWD（手機／平板／桌面）。

規格來源：`student-mgmt-scenarios.md`（學生資料、購買紀錄、上課紀錄、堂數統計、CRUD API）。

## 功能

- 管理者登入（單一帳號，本系統對外唯一入口）
- 學生資料建立／列表（搜尋、在籍狀態篩選）／明細／編輯／停用／重新啟用
- 購買紀錄新增／查詢／編輯／刪除，堂數即時重新計算
- 上課紀錄新增／查詢／編輯／刪除，堂數即時重新計算
- 堂數統計：總購買堂數／已上堂數／剩餘堂數（剩餘可為負數，超上時以紅字警示）
- JSON REST API（`/api/...`，登入保護），對應規格書「四、建議 API 清單」

## 技術棧

- Flask 3、Flask-SQLAlchemy、Flask-Login、Flask-WTF（CSRF + 表單驗證）、Flask-Limiter
- PostgreSQL（正式環境）／SQLite in-memory（自動化測試）
- Jinja2 伺服器端渲染樣板 + 自寫 RWD CSS（無前端框架依賴）
- pytest

## 專案結構

```
app/
  config.py, extensions.py, models.py, services.py, forms.py, commands.py
  auth/ students/ purchases/ classes/ api/   # 各功能 Blueprint
  templates/  static/css/style.css  static/js/main.js
tests/           # pytest：models / auth / students / purchases / classes / api / security
wsgi.py          # 應用程式進入點
requirements.txt / requirements-dev.txt
.env.example / .flaskenv
```

## 本機安裝與執行

### 1. 建立虛擬環境並安裝套件

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows PowerShell / cmd
pip install -r requirements-dev.txt
```

### 2. 準備資料庫

> 目前本機尚未安裝 PostgreSQL，`.env` 已先設定為 SQLite 檔案資料庫（`instance/eternal_force.sqlite`）以便立即開始開發；之後裝好 PostgreSQL 後，只要把 `.env` 的 `DATABASE_URL` 換成 `postgresql+psycopg2://...` 連線字串即可，不需要改任何程式碼（models 只用可攜的欄位型別）。

若要改用 PostgreSQL：先在本機建立一個空資料庫（`createdb eternal_force`），複製環境變數範本並依實際帳密調整：

```bash
copy .env.example .env
```

編輯 `.env`：
- `SECRET_KEY`：正式環境務必換成隨機字串（`python -c "import secrets; print(secrets.token_hex(32))"`）
- `DATABASE_URL`：PostgreSQL 連線字串

### 3. 建立資料表與管理者帳號

```bash
flask init-db
flask create-admin
```

`create-admin` 會互動式詢問帳號與密碼（密碼輸入不會顯示在畫面上，長度需至少 8 碼）。請自行在終端機執行這個指令輸入密碼，不要把密碼貼給任何人（含 AI 助理）。

> 若使用 `.env` 預設的相對路徑 SQLite（`sqlite:///eternal_force.sqlite`），Flask-SQLAlchemy 會把檔案實際建立在 `instance/eternal_force.sqlite`，這是 Flask 的標準行為（相對路徑的 sqlite URI 會相對於 `instance/` 資料夾解析），不是路徑設定錯誤。

### 4. 啟動伺服器

```bash
flask run
```

開啟 http://127.0.0.1:5000 ，用剛建立的管理者帳號登入。

## 執行測試

```bash
pytest
```

測試使用 SQLite in-memory（`app/config.py` 的 `TestConfig`），不需要先啟動 PostgreSQL 就能跑完整測試。涵蓋範圍：

- `test_models.py`：堂數統計計算（US-4.1，含剩餘堂數為負數的情境）
- `test_auth.py`：未登入導向登入頁、帳密錯誤、登入/登出、API 未登入回傳 401 JSON
- `test_students.py`：姓名必填、搜尋/狀態篩選、明細頁彙總、軟刪除（停用）/重新啟用
- `test_purchases.py`：購買堂數需正整數、新增/編輯/刪除後堂數統計即時更新
- `test_classes.py`：到課日期/時間必填、編輯不影響已上堂數、刪除後統計更新
- `test_api.py`：`/api/students`、`/api/students/{id}/summary` 等 JSON 契約
- `test_security.py`：CSRF 缺 token 擋下、XSS payload 於畫面正確跳脫、搜尋字串含 SQL 特殊字元不出錯

## SSDLC 對應說明

| 階段 | 對應內容 |
|---|---|
| 需求 / 威脅建模 | 依 `student-mgmt-scenarios.md` 的 User Story 與驗收標準逐條落地；額外辨識「系統存有學生個資」的威脅，補上未在原規格明訂的登入存取控制；後續變更需求與驗收標準記錄於 [`docs/requirements-matrix.md`](docs/requirements-matrix.md) |
| 設計 | Blueprint 分層（auth/students/purchases/classes/api）＋共用 `services.py` 業務邏輯層，避免 HTML 表單與 JSON API 各自實作一份驗證規則造成邏輯漂移 |
| 實作安全控制 | 見下表 |
| 測試 | pytest 涵蓋各 User Story 驗收標準＋專門的安全測試（CSRF/XSS/SQL injection 探測） |
| 部署強化 | production config 關閉 debug、secrets 走環境變數、建議搭配 HTTPS reverse proxy + gunicorn |

### 安全控制對照

| 風險 | 控制措施 |
|---|---|
| 未授權存取個資 | Flask-Login 強制所有頁面與 `/api/*` 登入才能存取 |
| 密碼外洩 | `werkzeug.security` PBKDF2 雜湊儲存，不存明碼 |
| 暴力破解登入 | Flask-Limiter 對 `/login` 限制 10 次/分鐘 |
| CSRF | Flask-WTF `CSRFProtect` 全域啟用，所有表單帶 hidden token |
| XSS | Jinja2 預設 autoescape，使用者輸入一律經樣板跳脫後輸出 |
| SQL Injection | 全程 SQLAlchemy ORM／參數化查詢，無字串拼接 SQL |
| Session 竊取 | `HttpOnly`、`SameSite=Lax`，正式環境強制 `Secure` cookie |
| 機密外洩 | `SECRET_KEY`／`DATABASE_URL` 走環境變數，`.env` 已列入 `.gitignore` |
| 錯誤訊息洩漏堆疊 | production 關閉 debug，自訂 404/500 錯誤頁 |
| 缺少安全 headers | 全站 `X-Content-Type-Options` / `X-Frame-Options` / 基本 CSP |
| 誤刪資料 | 刪除動作一律 POST + 前端二次確認對話框 |

### `/api/*` 的 CSRF 例外說明

`/api/*` 僅供已登入管理者本人（同一瀏覽器 session）作為系統內部工具使用，因此在 `create_app()` 中對該 blueprint 執行 `csrf.exempt()`，改以「必須帶有效登入 session，否則回傳 JSON 401」把關。若未來要開放給瀏覽器以外的第三方用戶端呼叫，建議改用獨立的 API Token 驗證機制，而非沿用管理者登入 session。

## 規格書「五、待確認事項」決策紀錄

1. **多角色權限**：不做，維持單一管理者帳號。
2. **剩餘堂數為負數**：不阻擋新增上課紀錄，畫面以紅字＋警示文字標示（見學生列表卡片與明細頁）。
3. **購買金額欄位**：保留為選填欄位（`purchase_records.price`）。
4. **學生刪除**：採**軟刪除**——刪除動作實際上是把 `status` 改為 `inactive`，保留歷史購買/上課紀錄；可再次「重新啟用」。購買紀錄／上課紀錄本身的刪除則是硬刪除（規格只要求刪除前確認，無保留歷史需求）。
5. **上課紀錄與購買紀錄的扣款關聯**：不做，採規格書寫的簡單相減（總購買 − 已上 = 剩餘）。

## API

對應規格書「四、建議 API 清單」，所有端點皆需登入 session；日期格式 `YYYY-MM-DD`，時間格式 `HH:MM`。

| Method | Endpoint | 說明 |
|---|---|---|
| GET/POST | `/api/students` | 學生列表（`?search=`、`?status=`）／新增學生 |
| GET/PUT/PATCH/DELETE | `/api/students/{id}` | 學生明細／編輯／軟刪除（停用） |
| GET | `/api/students/{id}/summary` | `{total_purchased, total_attended, remaining}` |
| GET/POST | `/api/students/{id}/purchases` | 購買紀錄列表／新增 |
| PUT/PATCH/DELETE | `/api/purchases/{id}` | 編輯／刪除購買紀錄 |
| GET/POST | `/api/students/{id}/classes` | 上課紀錄列表／新增 |
| PUT/PATCH/DELETE | `/api/classes/{id}` | 編輯／刪除上課紀錄 |

## 部署備註

- 正式環境使用 `wsgi.py`（例如 `gunicorn wsgi:app`），並放在有 HTTPS 的反向代理（Nginx/Caddy）之後。
- 務必設定 `FLASK_ENV=production`、隨機 `SECRET_KEY`、`SESSION_COOKIE_SECURE=true`。
- 目前以 `flask init-db`（`db.create_all()`）建表；若日後需要 schema 演進（新增欄位等），建議導入 Flask-Migrate / Alembic 做版本化遷移。
- 資料庫使用 Supabase PostgreSQL；正式環境與本機開發應各自使用獨立的 Supabase 專案，避免本機測試操作影響正式資料。

### 部署到 Render

專案根目錄的 `render.yaml` 已定義好 Web Service（`gunicorn wsgi:app`、健康檢查走 `/healthz`）。步驟：

1. 把專案 push 到 GitHub（或其他 Render 支援的 Git 服務）。
2. Render 後台「New +」→「Blueprint」，選擇這個 repo，Render 會自動讀取 `render.yaml` 建立服務。
3. 部署前到 Render 的環境變數設定裡補上 `DATABASE_URL`（正式環境 Supabase 專案的連線字串；`render.yaml` 裡故意不寫死，需在後台手動貼上）。`SECRET_KEY` 由 Render 自動產生、`FLASK_ENV`/`SESSION_COOKIE_SECURE` 已在 `render.yaml` 設好，不用另外調整。
4. 部署完成後，第一次要對正式資料庫建表：在 Render 服務的 Shell 分頁執行 `flask init-db`，需要建立管理者帳號的話再執行 `flask create-admin`；若要把訓練項目種子資料也建起來，執行 `flask seed-exercise-catalog`。

## RWD 驗證備註

`app/static/css/style.css` 採 mobile-first 設計，斷點與版面切換邏輯與參考專案（CMG）的 `index.css` 一致：預設單欄卡片式排版，於 `min-width: 640px` 起學生列表切換為多欄 grid，於 `min-width: 640/700/720px` 起購買/上課紀錄由「堆疊卡片」切換為「表格式列」，導覽列在窄螢幕收合為漢堡選單。已在本機以 ~1045px 寬度視窗實測登入、新增學生、新增購買/上課紀錄、堂數統計即時更新（含剩餘堂數為負時的紅字警示）等主要流程皆正常、無版面溢出；受限於本次開發環境的瀏覽器自動化視窗大小調整不完全可靠，建議額外用瀏覽器 DevTools 裝置模擬（iPhone/iPad 尺寸）或實機再次確認窄螢幕（<640px）的呈現。
