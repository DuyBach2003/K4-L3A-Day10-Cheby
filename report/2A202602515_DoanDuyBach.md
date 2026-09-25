# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Đoàn Duy Bách             |
| MSSV               | 2A202602515                     |
| Khóa/Lớp         | K4                         |
| Tên nhóm         | Cheby              |
| Vai trò chính    | Thành viên duy nhất — phụ trách toàn bộ pipeline |
| Repository         | https://github.com/DuyBach2003/K4-L3A-Day10-Cheby |
| Ngày hoàn thành | 2026-09-25                 |

## 2. Vai trò và phạm vi công việc

Tôi làm bài một mình nên sở hữu toàn bộ các khối việc. Tôi có dùng Claude Code (AI assistant) để hỗ trợ viết code và báo cáo, theo chính sách AI tại `docs/RULES.md` mục 3. Mọi số liệu bên dưới lấy từ artifact sinh ra khi chạy pipeline thật.

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái |
| ------------------ | --------------------- | ---------------- | ----------------- | ---------- |
| Raw ingestion | `crossref.py`: `parse_crossref_payload`, `fetch_source_records`, `load_raw_records` | Crossref `/works` hoặc snapshot | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | Hoàn thành |
| Cleaning | `cleaning.py`: `build_clean_dataframe`, `build_text_for_embedding` | `PaperRecord` list | `data/clean/papers_clean.{csv,json}` | Hoàn thành |
| Quality & freshness | `quality.py`: `run_data_quality_checks`, `build_freshness_report` | Dataframe | `data/quality/*.json` | Hoàn thành |
| Evaluation set | `testset.py`: `build_test_set` | Clean dataframe | `data/eval/test_set.json` | Hoàn thành |
| Corruption | `corruption.py`: `corrupt_clean_dataframe` | Clean dataframe | `data/results/corruption_log.json`, `data/clean/papers_clean_corrupted.*` | Hoàn thành |
| Orchestration & repair | `phase1.py`, `corruption_flow.py` | Settings | Metrics 3 trạng thái, `data/chroma/` (3 collection) | Hoàn thành |
| Reporting | `reporting.py` | Metrics, quality, freshness, log | `data/reports/phase1_report.md`, `data/reports/corruption_report.md` | Hoàn thành |
| Test tự động | `tests/test_pipeline.py` | Raw snapshot | 8 test pytest | Hoàn thành |
| Agent demo bằng LLM | `phase1._run_agent_demo` | Ollama `qwen2.5:7b` chạy local | `data/results/agent_demo_answers.json` | Hoàn thành (agent tự gọi tool, trả lời đúng 2/2 câu demo) |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Sửa code starter | `src/retrieval/index.py` | Manifest lưu `persist_path` tương đối, `load` resolve theo `project_dir` |
| Mở rộng metric | `src/evaluation/metrics.py` | Thêm `by_question_type` và `judge_mode` vào summary; siết prompt LLM judge |
| LLM local | Ollama + `qwen2.5:7b`, `src/retrieval/embeddings.py` | Chạy judge/agent không cần API key; nạp MiniLM từ cache local để mạng chập chờn không làm hỏng pipeline |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Parse snapshot, bóc `<jats:p>` ở 24/24 abstract | `crossref.py` | 24 records, trùng byte với file raw gốc | `git diff data/raw` rỗng sau khi chạy lại |
| Quality Gate GX 1.x | `quality.py` | Baseline 7/7 pass; corrupted 4/7 | `data/quality/*_quality_report.json` |
| 6 lỗi có seed | `corruption.py` | 24 → 22 dòng | `data/results/corruption_log.json` |
| Auto repair + fingerprint | `corruption_flow.py` | Fingerprint repaired = baseline = rebuild lần 2 | Log `[repair] ... matches_baseline=True deterministic=True` |

Output cụ thể: bảng đối chiếu trong `data/reports/corruption_report.md` — hit rate 1.0 → 0.8 → 1.0, token F1 1.0 → 0.6568 → 1.0, kèm bảng các câu trả lời sai trên dữ liệu lỗi.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Dữ liệu hỏng không làm RAG báo lỗi mà chỉ làm câu trả lời sai. Pipeline cần (1) phát hiện dữ liệu hỏng trước khi index, (2) đo được mức ảnh hưởng lên agent, và (3) phục hồi về đúng trạng thái sạch theo cách lặp lại được.

### Cách triển khai

- **Ingestion:** mặc định đọc snapshot để chạy offline ổn định; `REFRESH_SOURCE=1` mới gọi API. Gặp 429/5xx thì retry tối đa 4 lần (tôn trọng `Retry-After`, nếu không thì backoff 2^n giây), hết lượt thì fallback về snapshot.
- **Cleaning:** DOI viết thường làm `paper_id` (DOI không phân biệt hoa thường), ngày chuẩn hóa ISO, `age_days = run_date − published`, sort theo ngày giảm dần để thứ tự ổn định.
- **Gate:** 4 expectation bắt buộc + `title` ≥ 8 ký tự. Ở Phase 1, gate fail thì raise `QualityGateError` và không index. Freshness được tách riêng vì đây là SLA cảnh báo, không phải lỗi schema.
- **Corruption:** drop 20% bài mới nhất trước, sau đó chia các dòng còn lại (không chồng lấn) cho blank/noise/truncate/stale để quy được tác động về đúng loại lỗi; duplicate lấy ngẫu nhiên; cuối cùng rebuild `text_for_embedding` để lỗi thực sự đi vào vector.
- **Repair:** đọc lại `crossref_records.json` và gọi đúng `build_clean_dataframe`, rồi qua lại gate trước khi index vào `papers-repaired`.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `data/raw/crossref_response.json` (payload Crossref) |
| Output | Clean schema 15 cột (`paper_id`, `title`, `summary`, `authors_joined`, `categories_joined`, `primary_category`, `author_count`, `published`, `updated`, `age_days`, `abs_url`, `pdf_url`, `comment`, `summary_chars`, `text_for_embedding`), 3 Chroma collection, metrics JSON, báo cáo Markdown |
| Module phụ thuộc | `core/config.py`, `core/utils.py`, `retrieval/index.py`, `evaluation/metrics.py` |
| Module sử dụng output | `retrieval/qa.py` (dùng metadata `authors_joined`, `published`, `categories_joined`, `summary`) |
| Điều kiện lỗi cần xử lý | API 429/5xx/timeout; record thiếu DOI/title/abstract/ngày; DOI trùng; test set cũ tham chiếu paper không còn trong corpus |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
python -m pytest -q tests
```

- **Kết quả mong đợi:** exit 0; baseline gate pass; corrupted gate fail và metric giảm; repaired về bằng baseline.
- **Kết quả thực tế:** đúng như mong đợi; pytest `8 passed`.
- **Artifact/log:** `data/results/*.json`, `data/quality/*.json`, `data/reports/*.md`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Khi gate phát hiện dữ liệu hỏng, cần chọn cách sửa.
- **Các phương án đã cân nhắc:** (a) vá trực tiếp bảng hỏng: dedupe, xóa dòng summary rỗng, lọc token rác; (b) bỏ bảng hỏng và rebuild từ raw snapshot bất biến bằng cùng code cleaning.
- **Phương án đã chọn:** (b).
- **Lý do:** Vá tại chỗ không khôi phục được dữ liệu đã mất (5 bài bị drop, ngày bị lùi, title bị cắt) và mỗi lần vá có thể cho kết quả khác nhau. Rebuild từ raw thì tất định: cùng input, cùng hàm, cùng output, nên chạy lại bao nhiêu lần cũng được.
- **Bằng chứng quyết định phù hợp:** fingerprint SHA-256 của repaired trùng baseline (`c1257bb4d221…`), rebuild lần 2 cho cùng fingerprint; 4 metric phục hồi 100%.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Manifest `data/embeddings/papers_embeddings.json` chứa `"persist_path": "/Users/<user>/Desktop/.../data/chroma"`.
- **Lệnh hoặc bước tái hiện:** chạy `python script/run_phase1.py`, sau đó `grep -rl "/Users/" data/`.
- **Nguyên nhân gốc:** `LocalEmbeddingIndex.build` ghi `str(persist_path)`, mà `persist_path` là đường dẫn tuyệt đối từ `load_settings()`; `LocalEmbeddingIndex.load` lại dùng nguyên giá trị này.
- **Cách xử lý:** ghi `persist_path` tương đối so với `project_dir`; khi load, nếu là đường dẫn tương đối thì ghép với `project_dir`.
- **Cách xác minh sau khi sửa:** xóa `data/`, chạy lại 2 pipeline; `LocalEmbeddingIndex.load` cho 3 manifest trả 24/22/24 docs; `grep` không còn kết quả.
- **Điều học được:** artifact được commit cũng là một phần của contract. Đường dẫn tuyệt đối vừa làm lộ thông tin máy cá nhân, vừa làm pipeline hỏng trên máy người chấm.

### Blocker phụ: LLM judge local chấm sai

- **Triệu chứng:** Với `qwen2.5:7b`, trạng thái repaired có token F1 = 1.0 nhưng judge accuracy chỉ 0.8. Judge cho eval_005 1 điểm với lý do "the answer does not reflect the content of the paper", dù câu trả lời trùng khớp đáp án.
- **Nguyên nhân gốc:** prompt cũ không nói rõ reference là chuẩn, nên model 7B tự đánh giá lại chất lượng của chính đáp án. Ngược lại, nó lại dễ dãi với câu sai năm (cho 4 điểm).
- **Cách xử lý:** siết prompt `_judge_answer`: reference là ground truth tuyệt đối, cấm dùng kiến thức ngoài, ngày/tên phải khớp tuyệt đối, có thang điểm cụ thể, và `correct` chỉ khi điểm ≥ 4.
- **Cách xác minh:** thử lại 8 cặp mẫu (khớp → 5, sai năm → 1, sai tác giả → 1, rác → 1, nhiễu → 2), rồi chạy lại cả 2 pipeline: baseline/repaired judge accuracy 1.0, corrupted 0.6.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. Payload Crossref được lưu nguyên vẹn (`crossref_response.json`), sau đó parse thành `PaperRecord` (`crossref_records.json`), clean thành dataframe có `text_for_embedding`, qua GX gate, rồi được MiniLM-L6-v2 embed (vector normalize) và nạp vào ChromaDB (cosine), mỗi trạng thái một collection riêng.
2. Mỗi câu hỏi có `ground_truth_doc_ids`. Retrieval hit = tài liệu đúng nằm trong top-4 kết quả trả về. Answer quality = token F1 giữa câu trả lời và `ground_truth` (câu đầu abstract / tác giả / ngày / chuyên ngành), cộng thêm LLM judge (`qwen2.5:7b` chạy local) chấm 1–5 so với ground truth.
3. Quality checks kiểm tra tính hợp lệ về cấu trúc của từng batch: số dòng, null, trùng lặp, độ dài. Freshness đo tuổi dữ liệu so với thời điểm chạy. Một batch có thể hợp lệ hoàn toàn mà vẫn cũ: bài lỗi `stale_date` không vi phạm expectation nào nhưng đẩy stale ratio lên 31.82%.
4. Nếu đổi test set thì metric thay đổi có thể do câu hỏi, không phải do dữ liệu. Dùng cùng `test_set.json` thì chênh lệch chỉ đến từ nội dung index.
5. Repair thành công khi: `repaired_quality_report.json` có `success=True` (7/7), `repaired_freshness_report.json` có `is_fresh=True`, fingerprint trùng baseline, và `repaired_metrics.json` bằng `baseline_metrics.json`.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.8000 | 1.0000 | Chỉ drop records làm miss (eval_001, eval_002) |
| `mean_token_f1` | 1.0000 | 0.6568 | 1.0000 | Giảm nhiều hơn hit rate: lấy đúng tài liệu vẫn có thể trả lời sai |
| `judge_accuracy` | 1.0000 | 0.6000 | 1.0000 | LLM judge, khắt khe hơn token F1: eval_009 (F1 0.83 nhưng bị nhiễu) chỉ được 2 điểm |
| `mean_judge_score` | 5.0 | 3.4 | 5.0 | |
| Quality checks | 7/7 | 4/7 | 7/7 | Fail: unique(paper_id), length(title), length(summary) |
| Freshness status | Fresh (4.17%) | Stale (31.82%) | Fresh (4.17%) | |

### Kết luận từ số liệu

1. Stale date (6 dòng lùi 365 ngày) → stale ratio 31.82% > 25%, `is_fresh=False` → eval_007 vẫn hit đúng tài liệu nhưng trả "2025-06-03" thay vì "2026-06-03" (F1 = 0).
2. Rebuild từ raw → GX 7/7 và `is_fresh=True`, fingerprint trùng baseline → hit rate, token F1, judge đều về đúng giá trị baseline.

Corruption ảnh hưởng rõ nhất là **drop latest records**: đây là lỗi duy nhất làm giảm retrieval hit rate, và agent vẫn trả lời bằng bài lân cận mà không báo gì (eval_002 trả tác giả của một bài khác). Nguy hiểm hơn nữa là không expectation nào của GX bắt được lỗi này; nó chỉ lộ ra qua freshness (latest published lùi từ 2026-07-22 về 2026-06-12).

Kết quả khác kỳ vọng: **inject noise** hoàn toàn không bị GX bắt, vì chèn rác làm abstract dài hơn chứ không ngắn đi. Nó lại gây hại nặng: eval_005 trả lời "??!!" (F1 = 0). Tôi đã kiểm tra lại 4 dòng fail `length(summary)`: đó là 3 dòng bị blank cộng 1 bản duplicate của một dòng blank, không có dòng nào thuộc nhóm noise. Ngoài ra, truncate title và blank summary không trúng bài nào trong test set nên chỉ thấy được qua GX, không thấy qua metric.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Raw snapshot bất biến là thứ giúp repair trở nên tất định; không có nó thì chỉ còn cách vá tay.
2. Quality check và freshness bắt các loại lỗi khác nhau; mỗi expectation chỉ bắt được đúng loại lỗi nó được thiết kế cho, nên noise lọt qua hoàn toàn.
3. Retrieval hit rate cao không đảm bảo câu trả lời đúng: dữ liệu sai trong đúng tài liệu vẫn tạo ra câu trả lời sai một cách tự tin.

### Nếu có thêm thời gian

Thêm expectation `ExpectColumnValuesToNotMatchRegex` cho `summary` (bắt `0xDEADBEEF`, ký tự U+FFFD, chuỗi ký hiệu lặp), rồi chạy lại corruption flow và kiểm tra `corrupted_quality_report.json` có thêm expectation fail với đúng 3 dòng noise. Đồng thời đưa `ground_truth_doc_ids` vào prompt của judge, để judge không chấm đúng cho câu trả lời lấy từ bài khác (trường hợp eval_001).

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Đoàn Duy Bách
**Ngày xác nhận:** 2026-09-25
