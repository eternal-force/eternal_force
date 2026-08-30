# 需求矩陣表

追蹤功能需求與其實作範圍、驗收標準的對應關係，供日後回溯「為什麼這樣做」與「改動影響哪些檔案」使用。
新需求請依序附加在表格最後，編號遞增、不重複使用舊編號。

| 編號 | 需求描述 | 提出日期 | 影響範圍 | 驗收標準 | 狀態 |
|---|---|---|---|---|---|
| REQ-001 | 新增上課紀錄表單移除「上課時長」欄位 | 2026-08-26 | `app/models.py`(`ClassRecord`)、`app/forms.py`、`app/services.py`、`app/classes/routes.py`、`app/templates/classes/form.html`、`app/templates/students/detail.html` | 新增/編輯上課紀錄表單不再出現「上課時長」欄位；上課紀錄列表不再顯示時長欄位；既有資料庫欄位保留(未刪除)以避免破壞既有資料，僅前端與 API 不再讀寫。 | 已完成 |
| REQ-002 | 新增上課紀錄表單新增「上課教練」欄位，從角色為教練(coach)且啟用中的帳號以下拉選單選擇，為必填 | 2026-08-26 | `app/models.py`(`ClassRecord.coach_id`)、`app/forms.py`(`ClassRecordForm.coach_id`)、`app/services.py`(`list_active_coaches`、`_validate_coach`)、`app/classes/routes.py`、`app/templates/classes/form.html`、`app/templates/students/detail.html` | 新增/編輯上課紀錄表單顯示教練下拉選單，選項來源為 `role='coach'` 且 `status='active'` 的帳號；未選擇教練時顯示「請選擇上課教練」並擋下送出；後端(HTML 表單與 `/api` JSON 端點)皆會驗證教練 id 合法性，避免竄改請求繞過。 | 已完成 |
| REQ-003 | 訓練菜單新增方式參考 CMG 專案(`C:\Users\HW-X54\Projects\CMG`)的訓練項目編輯器，項目需可填公斤數/組數/次數/備註，且項目填寫完成後可收合以節省畫面空間 | 2026-08-26 | `app/models.py`(`ClassExercise.weight_kg/sets/reps/note`)、`app/services.py`(`_build_class_exercises` 數值驗證)、`app/classes/routes.py`、`app/templates/classes/_exercise_row.html`(新增)、`app/templates/classes/form.html`、`app/static/js/main.js`、`app/static/css/style.css`、`app/templates/students/detail.html` | 訓練菜單每個項目可填公斤數/組數/次數/備註(皆選填，但填了必須是非負數字，否則顯示錯誤訊息並擋下送出)；每個項目列可點「收合」摘要顯示(分類·名稱·組數x次數·公斤數)，點列頭可再展開編輯；編輯模式載入既有項目時預設以收合狀態顯示；新增下一個項目時，已填寫名稱的前一列會自動收合。 | 已完成 |

## 補充說明

- REQ-001：資料庫的 `class_records.duration_minutes` 欄位刻意保留未刪除，因專案目前僅用 `flask init-db`(`db.create_all()`)建表，沒有 Alembic / Flask-Migrate 等版本化遷移工具，刪除欄位需要手動 `ALTER TABLE`，風險與效益不成比例，故僅停用讀寫、不動既有 schema。
- REQ-002／REQ-003：這兩項變更皆對既有的 Supabase(PostgreSQL)資料表新增欄位(`class_records.coach_id`、`class_exercises.weight_kg`/`sets`/`reps`/`note`)。由於同樣沒有遷移工具，已直接對目前連線中的資料庫執行等冪的 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`；若日後切換到新的資料庫(例如正式環境 Render 上的 Supabase 專案)，`flask init-db` 建立的全新資料表會直接包含這些欄位，但**既有**資料庫仍需比照手動補跑一次相同的 `ALTER TABLE`陳述式，否則會出現「欄位不存在」的錯誤。長期建議依 README 既有規劃導入 Flask-Migrate / Alembic，避免每次改 schema 都要手動介入。
- 上課教練下拉選單目前資料來源是「角色為教練且帳號狀態為啟用中」的使用者；若系統中尚無任何教練帳號，選單會是空的，需先透過「帳號管理 → 新增教練」建立至少一位教練帳號，新增上課紀錄功能才可用。
