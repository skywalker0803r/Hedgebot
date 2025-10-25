# 加密貨幣對沖機器人

## 專案描述

本專案提供了一個運行加密貨幣交易策略的框架，主要專注於跨交易所的對沖。它具有一個 Streamlit 網頁介面，便於控制和監控，策略執行則由獨立的後端服務處理，以實現連續操作。

## 功能特色

*   **多交易所支援**: 整合 Bitmart 和 TopOne 交易所。
*   **動態策略載入**: 策略定義在獨立的 Python 檔案中，並由應用程式動態載入。
*   **Streamlit 網頁介面**: 提供一個互動式前端，用於選擇策略、配置參數和控制後端服務。
*   **連續後端執行**: 策略在獨立的 Python 進程中連續運行，以定義的間隔進行輪詢。
*   **保證金不足檢查**: 後端服務在嘗試下單前，會檢查兩個交易所是否有足夠的保證金。
*   **已實作策略**:
    *   **對沖策略 (Hedge Strategy)**: 在 Bitmart 和 TopOne 上以相反方向開倉，持倉指定時間後平倉。
    *   **MACD 策略**: 監控 MACD 指標，金叉（買入訊號）時開倉，死叉（賣出訊號）時平倉。
    *   **RSI 策略**: 監控 RSI 指標，超賣（RSI < 20，買入訊號）時開倉，超買（RSI > 80，賣出訊號）時平倉。

## 設定

### 先決條件

*   Python 3.8+
*   `pip` (Python 套件安裝器)

### 安裝

1.  **複製儲存庫** (如果適用，否則請導航到專案目錄):
    ```bash
    # git clone <repository_url>
    # cd <project_directory>
    ```

2.  **安裝 Python 依賴項**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **配置環境變數**:
    在專案根目錄中創建一個 `.env` 檔案，其中包含您的 Bitmart 和 TopOne API 密鑰和密碼。請將佔位符值替換為您的實際憑證。

    ```
    BITMART_API_KEY="您的Bitmart_api_key"
    BITMART_SECRET_KEY="您的Bitmart_secret_key"
    BITMART_MEMO="您的Bitmart_memo" # 可選，可為空

    TOPONE_API_KEY="您的TopOne_api_key"
    TOPONE_SECRET_KEY="您的TopOne_secret_key"
    ```

## 使用方式

### 運行 Streamlit 應用程式

要啟動網頁介面，請在終端機中導航到專案根目錄並運行：

```bash
streamlit run app.py
```

這將在您的網頁瀏覽器中打開應用程式。

### 使用介面

1.  **選擇策略**: 從下拉選單中選擇可用的策略。
2.  **設定策略參數**: 使用側邊欄控制項調整通用參數，例如 `交易對 (Symbol)`、`Bitmart 方向 (Bitmart Side)`、`保證金 (Margin)`、`槓桿 (Leverage)`、`止盈百分比 (Take Profit %)` 和 `止損百分比 (Stop Loss %)`。
3.  **控制後端服務**: 使用「啟動策略 (Start Strategy)」和「停止策略 (Stop Strategy)」按鈕來控制所選策略在後台的連續執行。
4.  **監控日誌**: 「後端服務日誌 (Backend Service Logs)」部分將顯示運行中策略的即時日誌。您可以點擊「刷新後端日誌 (Refresh Backend Logs)」來更新視圖。

## 策略詳情

策略位於 `strategies/` 目錄中。每個策略都是一個 Python 檔案，其中包含一個名為 `run_<strategy_name>(bitmart_client, topone_client, **kwargs)` 的函數。您可以透過在此目錄中創建一個遵循相同結構的新 `.py` 檔案來新增策略。

## 重要注意事項

*   Streamlit 應用程式 (`app.py`) 作為控制面板和顯示介面。實際的交易策略邏輯在獨立的後端進程 (`backend_service.py`) 中運行。
*   `backend_service.py` 以指定的間隔輪詢交易所並執行策略邏輯。當達到 `最大執行輪次 (Max Execution Rounds)` 或偵測到 `保證金不足 (Insufficient Margin)` 情況時，它將停止。
*   `對沖策略 (hedge_strategy)` 包含一個 `time.sleep(60)` 調用，用於在嘗試平倉前持倉 1 分鐘。
*   請確保您的 API 密鑰具有交易和訪問市場數據所需的權限。

## 未來增強

*   更強大的錯誤處理和重試機制。
*   將日誌即時串流到 Streamlit 前端（目前需要手動刷新）。
*   資料庫整合，用於持久儲存交易歷史和策略表現。
*   更進階的進程間通信，以實現更精細的控制和狀態更新。
*   實作更複雜的交易策略。
