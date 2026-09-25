# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Khóa/Lớp         | K4                         |
| Tên nhóm         | Cheby     |
| Repository         | https://github.com/DuyBach2003/K4-L3A-Day10-Cheby |
| Ngày hoàn thành | 2026-09-25                 |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | Đoàn Duy Bách | 2A202602515 | Thành viên duy nhất — Source, Data model & evaluation set, Observability, Corruption & integration | Toàn bộ `src/ingestion/`, `src/evaluation/testset.py`, `src/observability/`, `src/pipelines/`, sửa `src/retrieval/index.py`, `tests/` |

Nhóm chỉ có 1 thành viên nên toàn bộ các khối việc (4 vai trò gợi ý trong `report/README.md`) do cùng một người thực hiện.

## 2. Tóm tắt kết quả

**Tóm tắt của nhóm:**

Nhóm (1 thành viên) hoàn thành toàn bộ 7 tầng của pipeline: ingestion Crossref (offline snapshot mặc định, live API có retry khi `REFRESH_SOURCE=1`), cleaning, Quality Gate Great Expectations 1.23.1 + Freshness SLA, index ChromaDB với `all-MiniLM-L6-v2`, evaluation 10 câu hỏi, corruption 6 kịch bản và repair từ raw. Cả `script/run_phase1.py` và `script/run_corruption_flow.py` chạy với exit code 0 từ trạng thái `data/` trống.

Baseline tạo 24 dòng sạch, collection `papers-baseline` (24 docs), GX 7/7 expectation pass, freshness 1/24 dòng quá 180 ngày (4.17%) → fresh. Baseline đạt hit rate 1.0, token F1 1.0.

Trên dữ liệu bị tiêm lỗi (22 dòng), hit rate giảm xuống 0.80, token F1 xuống 0.6568, judge accuracy (LLM judge) xuống 0.60. Tác động rõ nhất là **drop latest records** (2 câu hỏi mất hẳn tài liệu gốc) và **inject noise / stale date** (câu trả lời sai nhưng vẫn "tự tin"). GX gate bắt được 3 lỗi (unique `paper_id`, độ dài `title`, độ dài `summary`), freshness chuyển sang stale (31.82%).

Repair rebuild từ `data/raw/crossref_records.json` phục hồi 100% cả 4 metric, dataset fingerprint trùng khớp baseline và rebuild 2 lần cho cùng fingerprint (idempotent).

LLM chạy local bằng Ollama (`qwen2.5:7b`) thay cho API, dùng cho LLM judge và agent demo. Giới hạn chính: judge 7B vẫn chấm đúng cho một câu trả lời lấy từ bài lân cận (eval_001), và RAGAS chưa bật.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref API (REFRESH_SOURCE=1) / snapshot data/raw/crossref_response.json
    -> parse_crossref_payload -> data/raw/crossref_records.json
    -> build_clean_dataframe -> data/clean/papers_clean.{csv,json}
    -> GX 1.x quality gate + freshness (chặn index nếu GX fail)
    -> MiniLM embedding + ChromaDB collection papers-baseline
    -> evaluate_pipeline trên data/eval/test_set.json -> baseline_metrics.json
    -> corrupt_clean_dataframe (6 lỗi, seed 42) -> corruption_log.json
    -> GX + freshness trên corrupted (ALERT) -> index papers-corrupted -> corrupted_metrics.json
    -> gate trip -> auto repair: rebuild từ raw records -> GX pass -> index papers-repaired -> repaired_metrics.json
    -> data/reports/corruption_report.md (Baseline vs Corrupted vs Repaired)
```

### Trách nhiệm của từng khối

| Khối             | Input          | Xử lý chính             | Output/artifact          | Owner          |
| ----------------- | -------------- | -------------------------- | ------------------------ | -------------- |
| Ingestion         | Crossref `/works` hoặc snapshot | Retry 429/5xx (4 lần, backoff mũ, tôn trọng `Retry-After`), fallback snapshot, bóc JATS, dedupe DOI | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | Đoàn Duy Bách |
| Cleaning          | Raw records    | Chuẩn hóa text, parse ngày, `age_days`, `text_for_embedding` 5 phần, dedupe `paper_id`, sort theo ngày | `data/clean/papers_clean.{csv,json}` | Đoàn Duy Bách |
| Embedding/index   | Clean dataframe | MiniLM-L6-v2 normalized, Chroma cosine, 3 collection tách biệt | `data/chroma/`, `data/embeddings/*.json` | Đoàn Duy Bách |
| Evaluation        | Clean dataframe | 10 câu, 4 loại, chọn đều theo thứ tự thời gian | `data/eval/test_set.json`, `data/results/*_metrics.json` | Đoàn Duy Bách |
| Observability     | Dataframe bất kỳ | GX 1.x ephemeral, 7 expectation; freshness SLA 180 ngày / 25% | `data/quality/*.json` | Đoàn Duy Bách |
| Corruption/repair | Clean dataframe / raw records | 6 lỗi seed 42; repair rebuild từ raw | `data/results/corruption_log.json`, `data/clean/papers_clean_{corrupted,repaired}.*` | Đoàn Duy Bách |
| Orchestration     | Settings       | Thứ tự chạy, gate, auto-repair, fingerprint | `data/reports/*.md` | Đoàn Duy Bách |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình             | Giá trị sử dụng |
| ---------------------------- | ------------------- |
| `LLM_PROVIDER`             | `ollama` (chạy local, không cần API key) |
| `LLM_MODEL`                | `qwen2.5:7b` (Ollama 0.34.4, `OLLAMA_BASE_URL=http://localhost:11434`) |
| Embedding model              | `sentence-transformers/all-MiniLM-L6-v2` |
| Số lượng Crossref records | 24 |
| Retrieval`top_k`           | 4 |
| Freshness threshold          | 180 ngày, tối đa 25% dòng stale |
| Random seed, nếu có        | 42 (corruption) |

### Lệnh cài đặt

```bash
python -m pip install -e ".[dev]"
```

### Lệnh chạy

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
python -m pytest -q tests        # 8 test, không cần mạng
```

Live API: `REFRESH_SOURCE=1 python script/run_phase1.py`. Sinh lại test set: `REFRESH_TEST_SET=1`.

### Kết quả tái hiện

| Lệnh             | Trạng thái                                    | Thời điểm chạy gần nhất | Bằng chứng                         |
| ----------------- | ----------------------------------------------- | ----------------------------- | ------------------------------------ |
| Baseline pipeline | Thành công (exit 0) | 2026-09-25 | `data/reports/phase1_report.md`, `data/results/baseline_metrics.json` |
| Corruption flow   | Thành công (exit 0) | 2026-09-25 | `data/reports/corruption_report.md`, `data/results/{corrupted,repaired}_metrics.json` |
| Pytest            | 8 passed | 2026-09-25 | `tests/test_pipeline.py` |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính                | Giá trị                             |
| --------------------------- | ------------------------------------- |
| Source                      | `https://api.crossref.org/works` (chạy bằng snapshot offline `data/raw/crossref_response.json`) |
| Query/filter                | `agentic retrieval augmented generation large language model`; `from-pub-date:<hôm nay − 180 ngày>,has-abstract:true`; `rows=24`, sort `published desc` |
| Thời điểm lấy dữ liệu | Snapshot có sẵn trong repo; pipeline chạy ngày 2026-09-25 |
| Số record nhận được    | 24 items → 24 records hợp lệ |
| Cơ chế retry/backoff      | Tối đa 4 lần cho HTTP 429/500/502/503/504 và lỗi mạng; chờ `Retry-After` hoặc 2^n giây (≤30s); hết lượt thì fallback snapshot |

### Raw và clean schema

| Trường        | Kiểu dữ liệu | Bắt buộc?  | Ý nghĩa   | Xử lý khi thiếu/sai |
| --------------- | --------------- | ------------ | ----------- | ---------------------- |
| `paper_id` | str (DOI lowercase) | Có | Document ID ổn định | Thiếu → bỏ record; trùng → giữ bản đầu |
| `title` | str | Có | Tiêu đề | Thiếu → bỏ record |
| `summary` | str | Có | Abstract đã bỏ tag JATS | Thiếu → bỏ record |
| `authors_joined` | str | Không | "Given Family, ..." | Rỗng nếu không có tác giả |
| `categories_joined`, `primary_category` | str | Không | Subject Crossref | Rỗng / "Uncategorized" |
| `published` | str ISO date | Có | Ngày xuất bản (published → print → online → issued → created) | Không parse được → bỏ record; thiếu tháng/ngày → mặc định 01 |
| `updated` | str ISO date | Không | indexed/deposited/created | Fallback về `published` |
| `age_days` | int | Có | `run_date − published` (ngày) | Tính lại mỗi lần chạy |
| `summary_chars` | int | Có | Độ dài abstract | — |
| `text_for_embedding` | str | Có | Tài liệu 5 phần được embed | — |

### Quy tắc cleaning

| Quy tắc                                 | Quality dimension liên quan | Số record bị tác động | Cách xác minh      |
| ---------------------------------------- | ---------------------------- | -------------------------: | -------------------- |
| Bỏ tag JATS/HTML, unescape entity, gộp whitespace | Validity | 24 (mọi abstract snapshot có `<jats:p>`) | `test_parse_strips_jats_and_dedupes` |
| Bỏ record thiếu DOI/title/abstract/ngày | Completeness | 0 | 24 raw → 24 clean |
| Dedupe theo `paper_id` | Uniqueness | 0 | GX `expect_column_values_to_be_unique(paper_id)` pass |
| Chuẩn hóa ngày về ISO, tính `age_days` | Timeliness | 24 | `data/quality/freshness_report.json` |

`text_for_embedding` gồm 5 dòng `Title / Authors / Published / Categories / Summary`, nên cả câu hỏi về tác giả, ngày và chuyên ngành đều có tín hiệu ngữ nghĩa trong vector. Document ID là DOI viết thường (DOI không phân biệt hoa thường), Chroma record id là `<paper_id>::<row>` để bản trùng lặp vẫn nạp được khi đo tác động của duplicate. `age_days = (run_date.date() − published).days`.

## 6. Evaluation setup

| Thành phần                             | Cấu hình thực tế          |
| ---------------------------------------- | ----------------------------- |
| Số câu hỏi                            | 10 |
| Các`question_type`                    | summary ×3, authors ×3, date ×2, categories ×2 |
| Ground-truth document ID                 | `paper_id` của bài được chọn; ground truth lấy từ clean data (câu đầu abstract / tác giả / ngày / chuyên ngành) |
| Embedding model                          | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store/collection                  | ChromaDB persistent `data/chroma/`, cosine; `papers-baseline`, `papers-corrupted`, `papers-repaired` |
| Retrieval`top_k`                       | 4 |
| LLM provider/model                       | ollama / qwen2.5:7b (local), temperature 0; không có Ollama thì judge tự fallback sang heuristic token-F1 |
| Test set dùng chung cho ba trạng thái | `data/eval/test_set.json` (sha256 `70162f9dc310bb61…`) |

Bài báo được chọn ở 10 vị trí cách đều trong corpus đã sort theo ngày (mới nhất → cũ nhất), nên test set tất định và không chọn lọc có lợi. Test set được sinh một lần ở Phase 1 và tái sử dụng (chỉ sinh lại khi `REFRESH_TEST_SET=1` hoặc khi tham chiếu tới paper không còn trong corpus). Cả ba trạng thái đọc cùng file này, nên mọi chênh lệch metric chỉ đến từ dữ liệu trong index.

## 7. Kết quả baseline

### Artifact checklist

| Artifact                 | Đường dẫn thực tế                | Trạng thái | Ghi chú   |
| ------------------------ | -------------------------------------- | ------------ | ---------- |
| Raw response/records     | `data/raw/`                          | Có | Records tái tạo trùng byte với bản gốc |
| Cleaned dataset          | `data/clean/`                        | Có | 24 dòng |
| Embedding manifest/index | `data/embeddings/`, `data/chroma/` | Có | 3 collection; `persist_path` tương đối |
| Evaluation set           | `data/eval/`                         | Có | 10 câu |
| Baseline metrics         | `data/results/baseline_metrics.json` | Có | Kèm breakdown theo loại câu hỏi |
| Quality/freshness        | `data/quality/`                      | Có | baseline/corrupted/repaired |
| Baseline report          | `data/reports/phase1_report.md`      | Có | |

### Baseline metrics

| Metric                 |       Giá trị | Diễn giải                             |
| ---------------------- | --------------: | --------------------------------------- |
| `retrieval_hit_rate` | 1.0000 | Tài liệu đúng luôn nằm trong top-4 (tiêu đề trong câu hỏi khớp exact lookup) |
| `mean_token_f1`      | 1.0000 | QA trích xuất đúng trường metadata, khớp hoàn toàn ground truth |
| `judge_accuracy`     | 1.0000 | LLM judge (`judge_mode=llm`): 10/10 câu được chấm đúng |
| `mean_judge_score`   | 5.0 | Mọi câu đạt 5/5 |
| Ragas, nếu có        | N/A | Chưa bật `RUN_RAGAS=1` (chậm với LLM 7B chạy local) |

Baseline tuyệt đối là điều dự kiến: QA là extractive trên metadata sạch, nên baseline đóng vai trò mốc tham chiếu để đo phần suy giảm chỉ do dữ liệu.

## 8. Data quality và freshness

### Quality checks

| Check        | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline      | Bằng chứng |
| ------------ | ----------------- | ------------------ | ----------------------- | ------------ |
| `ExpectTableRowCountToBeBetween` | Volume | 5–5000 dòng | Pass (24) | `data/quality/baseline_quality_report.json` |
| `ExpectColumnValuesToNotBeNull` × 3 | Completeness | `paper_id`, `title`, `text_for_embedding` không null | Pass (0 null) | như trên |
| `ExpectColumnValuesToBeUnique` | Uniqueness | `paper_id` duy nhất | Pass (0 trùng) | như trên |
| `ExpectColumnValueLengthsToBeBetween(summary)` | Completeness/Validity | 30–20000 ký tự | Pass | như trên |
| `ExpectColumnValueLengthsToBeBetween(title)` (bổ sung) | Validity | ≥ 8 ký tự | Pass | như trên |

Gate dùng API GX 1.x: `gx.get_context(mode="ephemeral")` → `data_sources.add_pandas` → `add_dataframe_asset` → `add_batch_definition_whole_dataframe` → `batch.validate(suite)`. Ở Phase 1, gate fail thì pipeline dừng trước khi index (`QualityGateError`).

### Freshness

| Thuộc tính               | Giá trị                           |
| -------------------------- | ----------------------------------- |
| Freshness được đo tại | Clean dataset trước khi index (`age_days`) |
| Timestamp mới nhất       | 2026-07-22 (cũ nhất 2026-03-28) |
| Ngưỡng freshness         | `age_days > 180` là stale; stale ratio > 25% → `is_fresh=False` |
| Trạng thái baseline      | Fresh |
| Lý do                     | 1/24 dòng (4.17%) quá 180 ngày: bài 2026-03-28 có age 181 ngày |

## 9. Corruption scenarios và repair

| Corruption         | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế | Cách repair   |
| ------------------ | ---------- | ---------------------: | ------------------------ | --------------------- | -------------- |
| drop_latest_records | Bỏ 20% bài mới nhất | 5 | Latest published lùi lại | eval_001, eval_002 miss (hit=False); latest 2026-07-22 → 2026-06-12 | Rebuild từ raw |
| blank_summary | Abstract = "" | 3 | GX length(summary) fail | GX length(summary) fail 4 dòng (3 + 1 bản duplicate của dòng đã blank); không trúng câu summary nào (eval_008 hỏi categories vẫn đúng) | Rebuild từ raw |
| inject_noise | Chèn token rác vào abstract | 3 | Không có expectation chuyên biệt | GX **không** bắt được (abstract dài hơn sau khi chèn); eval_005 trả lời "??!!" (F1 0), eval_009 F1 0.83 | Rebuild từ raw |
| truncate_title | Cắt title còn 6 ký tự | 3 | GX length(title) fail | GX length(title) fail 4 dòng (3 + 1 bản duplicate); không trúng bài nào trong test set | Rebuild từ raw |
| stale_date | Lùi `published` 365 ngày | 6 | Freshness stale | Stale ratio 31.82% → `is_fresh=False`; eval_007 trả "2025-06-03" thay vì "2026-06-03" | Rebuild từ raw |
| duplicate_rows | Nhân bản dòng | 3 | GX unique(paper_id) fail | GX đếm 6 giá trị trùng; eval_002 lấy cùng 1 doc 2 lần trong top-4 | Rebuild từ raw |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: Có
- Nhận xét: Log ghi seed, số dòng vào/ra (24 → 22), từng loại lỗi với số dòng, danh sách `paper_id` và chi tiết (ví dụ title trước/sau khi cắt).

Repair không vá bảng đã hỏng mà đọc lại `data/raw/crossref_records.json` (raw bất biến) và chạy lại đúng hàm `build_clean_dataframe`, sau đó qua lại GX gate rồi mới index vào `papers-repaired`. Luồng tự kích hoạt khi gate trip. Để chứng minh idempotent, pipeline rebuild 2 lần và so sánh SHA-256 của nội dung đi vào vector store (`paper_id, title, summary, published, text_for_embedding`): repaired = baseline = rebuild lần 2 (`c1257bb4d221…`).

## 10. So sánh baseline, corrupted và repaired

| Metric/signal            | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét   |
| ------------------------ | -------: | --------: | -------: | -----------------------: | --------------: | ------------ |
| `retrieval_hit_rate`   | 1.0000 | 0.8000 | 1.0000 | −0.2000 | 100% | 2 bài bị drop không còn trong index |
| `mean_token_f1`        | 1.0000 | 0.6568 | 1.0000 | −0.3432 | 100% | Date −0.50, summary −0.48, authors −0.33 |
| `judge_accuracy`       | 1.0000 | 0.6000 | 1.0000 | −0.4000 | 100% | LLM judge đánh sai 4 câu: eval_002, 005, 007 (1 điểm), eval_009 (2 điểm, bị nhiễu) |
| `mean_judge_score`     | 5.0 | 3.4 | 5.0 | −1.6 | 100% | |
| Quality checks pass/fail | 7/7 pass | 4/7 (fail) | 7/7 pass | −3 expectation | 100% | unique, length(title), length(summary) |
| Freshness status         | Fresh (4.17%) | Stale (31.82%) | Fresh (4.17%) | +27.65 điểm % | 100% | |

1. **Drop latest + duplicate** → latest published lùi về 2026-06-12, GX unique(paper_id) fail → retrieval hit rate giảm 1.0 → 0.8 (eval_001, eval_002 không còn tài liệu gốc, trả lời bằng bài lân cận mà không báo lỗi).
2. **Stale date** → stale ratio 31.82% vượt SLA 25%, `is_fresh=False` → câu date eval_007 trả về năm 2025 thay vì 2026 (F1 0), dù retrieval vẫn hit. Đây là silent failure điển hình: đúng tài liệu nhưng sai sự thật.
3. **Repair từ raw** → GX 7/7 và `is_fresh=True`, fingerprint trùng baseline → cả 4 metric về đúng giá trị baseline.

### Ghi chú về LLM judge

Lần chạy đầu với `qwen2.5:7b`, judge chấm sai 2 câu summary ở trạng thái repaired dù câu trả lời trùng khớp 100% với ground truth. Lý do: model tự nghi ngờ chính ground truth ("đáp án chưa tóm tắt đủ bài báo"). Nó cũng chấm 4 điểm (đúng) cho câu trả lời sai năm (2025-06-03 so với 2026-06-03). Nhóm đã siết prompt trong `_judge_answer` (`src/evaluation/metrics.py`): coi reference là chuẩn tuyệt đối, cấm dùng kiến thức ngoài, ngày/tên phải khớp tuyệt đối, và đưa thang điểm 1–5 cụ thể. Sau đó nhóm thử lại trên 8 cặp câu hỏi mẫu, rồi chạy lại cả 3 trạng thái. Số liệu trong báo cáo là của lần chạy sau khi sửa prompt, không chỉnh tay.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Manifest `data/embeddings/*.json` lưu `persist_path` là đường dẫn tuyệt đối của máy chạy (`/Users/...`), nên `LocalEmbeddingIndex.load` sẽ hỏng trên máy khác và artifact commit lên repo làm lộ đường dẫn local.
- **Nguyên nhân:** `LocalEmbeddingIndex.build` ghi `str(persist_path)` với `persist_path` tuyệt đối từ `load_settings`.
- **Cách xử lý:** Ghi đường dẫn tương đối so với `project_dir`; khi `load` thì resolve lại theo `project_dir` (vẫn chấp nhận đường dẫn tuyệt đối cũ).
- **Cách xác minh:** Chạy lại 2 pipeline, `LocalEmbeddingIndex.load` cho cả 3 manifest trả về 24/22/24 docs; `grep -r "/Users/" data/` không còn kết quả.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng   | Hướng cải thiện có thể kiểm chứng |
| --------------------- | -------------- | ----------------------------------------- |
| LLM judge 7B local chưa phát hiện câu trả lời lấy từ bài khác: eval_001 bị drop tài liệu gốc (hit=False) nhưng vẫn được 4 điểm vì bài lân cận có câu gần giống | `judge_accuracy` trên corrupted có thể lạc quan hơn thực tế | Truyền thêm `retrieved_doc_ids`/`ground_truth_doc_ids` vào judge hoặc dùng model lớn hơn; so kết quả trên `corrupted_answers.json` |
| Inject noise không có expectation riêng | Noise lọt qua gate hoàn toàn (eval_005 F1 = 0 mà GX không cảnh báo riêng) | Thêm `ExpectColumnValuesToNotMatchRegex(summary, "0xDEADBEEF\|�\|[#@$%^&*]{3,}")` và đo lại trên corrupted |
| Test set chỉ 10 câu, 2/6 lỗi (truncate title, blank summary) không trúng bài nào trong test set | Tác động của 2 lỗi này chỉ thấy qua GX, không thấy qua metric | Mở rộng test set phủ toàn bộ 24 bài hoặc thêm câu hỏi không chứa title |
| Snapshot tĩnh: bài cũ nhất đã 181 ngày | Snapshot sẽ vi phạm SLA sau vài tuần | Chạy `REFRESH_SOURCE=1` định kỳ, cảnh báo khi `is_fresh=False` |

## 13. Checklist trước khi nộp

- [x] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set.
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp với `data/quality/`.
- [x] Các đường dẫn báo cáo và artifact truy cập được.
- [x] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng.
- [x] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.
