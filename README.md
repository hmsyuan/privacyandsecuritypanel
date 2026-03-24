# Privacy & Security Panel（Google Cloud 試作版）

這個專案提供一個「一目了然」的戰情平台雛型，聚焦在個資保護與資安新聞，先試作以下 4 個來源：

- Council of Europe: https://www.coe.int
- EDPB: https://www.edpb.europa.eu/edpb_en
- EDPS: https://www.edps.europa.eu/_en
- noyb: https://noyb.eu/en

## 功能

- 每日排程爬蟲（UTC 01:00）抓取資料
- 僅保留近 30 天新聞
- 以來源分欄顯示，快速掌握各單位動態
- SQLite 儲存，可再升級到 Cloud SQL / BigQuery

## 本地執行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/crawler.py      # 先抓資料
python src/app.py          # 啟動網站 (http://localhost:8080)
```

## Google Cloud 建議部署架構

### 1) 網站
- Cloud Run 部署 Flask（`src/app.py`）

### 2) 每日爬蟲
- Cloud Scheduler (每天) -> Pub/Sub -> Cloud Run Job
- Job 內執行 `python src/crawler.py`

### 3) 資料庫（正式環境）
- 建議改為 Cloud SQL (PostgreSQL)
- 若要做關鍵字分析與儀表板可加 BigQuery + Looker Studio

## 限制（目前試作）

- 各站 HTML 結構不同，爬蟲目前用通用解析 + 文章頁日期推測
- 未加入重試退避、代理、captcha 處理
- 未加語意分類（例如 GDPR、ePrivacy、data breach 等標籤）

## 下一步可加

- 分類與風險等級（法規更新、執法裁罰、漏洞事件）
- Slack / Email 告警
- 中文摘要（LLM 摘要）
- 多租戶權限與審計紀錄
