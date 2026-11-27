# Decisions Log

## 2026-09-21 — Initial code steward
**What:** 莊詔允 is the initial code steward for the team.
**Why:** volunteered

## 2026-10-23 — CP1 team charter, problem, design and evaluation plan
**What:**
- **Disagreement resolution:** 意見分歧時採投票表決；2:2 平手時，當週事務由當時的 code steward 決定，整體專案的重大決策由蘇祐生做最後定奪。
- **Definition of done:** 程式碼需經 code steward approve 並成功 merge 進 final project repo 的 main branch；決策需全員達成共識並記錄在 DECISION.md。
- **Communication outside class:** 平時以 LINE 群組溝通；每 2 週於週六晚上透過 Google Meet 開會追蹤進度，每次約 30~60 分鐘。
- **Problem:** 新人不熟悉專案文件與程式碼時找不到即時解答而須頻繁求助 Mentor，Mentor 則需反覆回答相似的基礎問題。
- **Tool design:** 新人提問 → AI 依專案資料生成解答 → Mentor 審核並透過對話修正 → 經確認的解答保留供後續新人檢索複用。
- **Human-AI boundary:** AI 生成初始解答並同步推播給新人與 Mentor；Mentor 審核並校正 AI 的幻覺與錯誤；新人對 AI 解答存疑時可主動求助 Mentor。
- **Evaluation plan:** 以交付第一項 task 的時間與詢問 Mentor 的次數衡量（與受試者平常交付相似難度 task 相比）；最低門檻為提問次數至少降低 40%，且 50% 以上受試者上手時間至少縮短 40%。透過前測／後測問卷與訪談收集資料，受試者為蘇祐生與許懷仁實驗室中新加入的專案人員，以 Email 邀請。

**Why:** 三位實驗室成員的訪談顯示，新人難以判斷哪些程式與自己的任務相關，而直接問 Mentor 成本高且重複、一般 LLM 缺乏專案背景且未經審核；因此設計結合 Mentor 審核與解答複用的工具，並以上手時間與對 Mentor 的依賴程度作為可量化的評估指標。團隊運作規則則讓決策、完成標準與溝通方式有明確依據。

## 2026-11-21 — 資料庫 schema 版本管理與 SQLite WAL
**What:** 用 SQLite 的 `PRAGMA user_version` 記錄 schema 版本，啟動時依序執行 migration，舊的資料庫檔案會自動升級、資料不會遺失；如果資料庫版本比程式碼新，server 拒絕啟動。SQLite 開啟 WAL 模式。相關 PR：#12、#13。
**Why:** 組員本機已經有 scaffold 時期的資料庫，升級時不能要求大家刪檔重來；WAL 讓新人頁面的輪詢讀取和 Mentor 的審核寫入不會互相卡住。改用 ORM/Alembic 或 PostgreSQL 對這個 demo 太重，所以不採用。
**Led by:** Vincent (A)

## 2026-11-21 — AI 失敗時仍保存題目，不編造答案
**What:** 後端呼叫 AI 時若逾時（`CP2_AI_TIMEOUT`，預設 30 秒）、拋出例外或回傳格式錯誤，題目照樣存下來，標成 `ai_status="failed"`、附上錯誤代碼 `ai_error`，草稿位置顯示固定的說明文字；API 不回 5xx，也不產生假答案。AI 的回傳一律是 `pending`，只有 Mentor 能核准。相關 PR：#12。
**Why:** 工具的核心是「每一題都經過 Mentor 審核」，AI 失敗不該讓新人的問題消失，也不能讓新人看到沒人寫過的答案。錯誤代碼讓 Mentor 和 B 知道失敗原因。
**Led by:** Vincent (A)

## 2026-11-21 — 以 client_request_id 防止重複送出
**What:** `POST /api/questions` 接受選填的 `client_request_id`。同一個 key 再送一次會回傳原本那題（HTTP 200），不會重複建立；同一個 key 用在不同問題回 409。兩個請求同時送出時也只會建立一筆。相關 PR：#12（前端在 #18 接上）。
**Why:** 網路不穩或逾時後重送，不應該讓 Mentor 佇列出現重複的題目。用 body 欄位而不是 `Idempotency-Key` header，是因為不必改 CORS 設定，前端也比較好接。
**Led by:** Vincent (A)

## 2026-11-21 — 審核歷史只新增不修改，暫不開放修改已核准答案
**What:** 新增 `reviews` 表，每次核准都在同一個交易裡更新題目並新增一筆歷史，用 `version` 為每題的審核編號；審核前用 `BEGIN IMMEDIATE` 取得寫入鎖。狀態規則集中在 `TRANSITIONS`，目前只有 `pending → approved`；已核准的題目再審核仍回 409。相關 PR：#13。
**Why:** 先把審核紀錄完整留下，之後要做「修改答案」時不必再改 schema；同一個交易保證不會只更新一半，寫入鎖讓兩個 Mentor 同時審核時剛好一個成功、一個 409。修改已核准答案需要團隊先決定規則（誰能改、新人看哪一版），前端也還沒有畫面，所以暫不開放。
**Led by:** Vincent (A)

## 2026-11-23 — 只擋原封不動的 AI 失敗說明，佔位答案仍可核准
**What:** Mentor 核准時，如果答案和 AI 失敗的固定說明文字完全一樣（前後空白不計），後端回 422；demo 用的佔位答案（placeholder）仍然可以直接核准。待審佇列（`status=pending`）不設預設筆數上限。相關 PR：#12（D 在 #12 的 review 中提出）。
**Why:** 失敗說明不是答案，原封不動核准會讓新人看到一則「Mentor 審核過」、卻沒有人寫過的回答。佔位答案在接上真正的 AI 前是 demo 流程的一部分，先保留；之後是否也要擋，等團隊決定。佇列不設上限，是為了讓等最久的題目不會被擠出畫面。
**Led by:** Vincent (A)

## 2026-11-24 — 本輪 code review 與 merge 流程
**What:** 本輪由 code steward（Vincent）負責 merge；steward 自己的 PR 交給其他組員 review（#12、#13 由 D 提出 review 意見、B approve）。merge 一律用一般 merge commit，堆疊 PR 依賴的分支在下游 PR merge 前不刪除；merge 前確認 PR head 和 approve 的版本一致、CI 通過，並在本機把 PR 和最新的 `main` 合起來跑過測試。
**Why:** 依 CP1 的 definition of done，程式碼要經 steward approve 並 merge；steward 不審自己的程式，避免球員兼裁判。保留 merge commit 和分支，堆疊 PR 改 base 時不會出錯，也方便追蹤每個 PR 的內容。
**Led by:** Vincent (A, code steward)

## 2026-11-27 — 用 CP2_AI 切換 AI，改用 Claude 並保留 Gemini
**What:** 後端用環境變數 `CP2_AI` 選擇草稿來源：`placeholder`（預設）、`claude` 或 `gemini`。`claude` 透過 Anthropic API（`claude-opus-5-5`）呼叫，接在 B 的 `RagGenerator` pipeline 上，B 的檢索、prompt 和引用檢查不變；`gemini` 保留 B 原本的 adapter。兩種模式都會檢索 Mentor 核准過的答案。值打錯時 server 拒絕啟動。demo 用的 API key 尚待取得（TODO）。相關 PR：#24。
**Why:** 課堂提供 Claude 的使用資源，所以改用 Claude 產生草稿。做法上只多接一個呼叫函式，不必改寫 B 已經 merge 的程式，B 的 Gemini adapter 也保留下來，可以比較或備援。預設維持佔位答案，CI 和沒有 key 的組員不受影響；值打錯就停止啟動，避免 demo 時在沒人發現的情況下退回佔位答案。
**Led by:** Vincent (A)

## 2026-11-27 — 中文引用格式問題先列為 minor issue
**What:** #16 review 時發現：接在中文字後面的引用標記（例如「資料夾[1]」）不會被辨識為引用。這次先列為 minor issue，不擋 #16 merge，由 B 之後修正（review 中已附一行修法）。
**Why:** 修正只要改一行，且不影響英文答案和其他功能；先讓 AI 功能整合進 `main`，避免卡住後續的接線和 demo 準備。
**Led by:** Vincent (A, code steward)
