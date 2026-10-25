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
