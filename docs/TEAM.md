# Danh Sách Thành Viên & Báo Cáo Phân Công Nhóm

- **Tên Nhóm:** `Cheby`
- **Mã Nhóm / Lớp:** `K4-L3-DAY10`
- **Tên Repository Nộp Bài:** `K4-L3A-Day10-Cheby` (https://github.com/DuyBach2003/K4-L3A-Day10-Cheby)
- **Quy mô nhóm:** 1 thành viên (làm cá nhân, đảm nhận toàn bộ 4 vai trò gợi ý)

---

## # Thành viên

| STT | Họ và tên | MSSV | Email | Vai trò & Phân công công việc | Báo cáo cá nhân |
|---:|---|---|---|---|---|
| 1 | Đoàn Duy Bách | 2A202602515 | bachtipch@gmail.com | Toàn bộ 4 vai trò: Pipeline Integrator (`core/`, `pipelines/`), Data Foundation (`crossref.py`, `cleaning.py`, `corruption.py`), RAG & Vector Index (`retrieval/`), Observability & Evaluation (`quality.py`, `reporting.py`, `testset.py`) | `report/2A202602515_DoanDuyBach.md` |

### Phân công theo Checkpoint

| Checkpoint | Nội dung | Người thực hiện | Bằng chứng |
|---|---|---|---|
| CP0 | Môi trường, `.env`, ingestion raw data | Đoàn Duy Bách | `src/ingestion/crossref.py`, `data/raw/` |
| CP1 | Cleaning, GX 1.x Quality Gate, Freshness SLA | Đoàn Duy Bách | `src/ingestion/cleaning.py`, `src/observability/quality.py`, `data/quality/baseline_quality_report.json` |
| CP2 | Test set, ChromaDB index `papers-baseline` | Đoàn Duy Bách | `src/evaluation/testset.py`, `data/eval/test_set.json`, `data/chroma/` |
| CP3 | Baseline end-to-end, báo cáo pha 1 | Đoàn Duy Bách | `src/pipelines/phase1.py`, `data/results/baseline_metrics.json`, `data/reports/phase1_report.md` |
| CP4 | Tiêm 6 lỗi, đo suy giảm | Đoàn Duy Bách | `src/ingestion/corruption.py`, `data/results/corruption_log.json`, `data/results/corrupted_metrics.json` |
| CP5 | Idempotent repair, báo cáo 3 trạng thái | Đoàn Duy Bách | `src/pipelines/corruption_flow.py`, `data/results/repaired_metrics.json`, `data/reports/corruption_report.md` |
| CP6 | Demo, nộp bài | Đoàn Duy Bách | Repo trên GitHub, link nộp LMS |

---

## # Cá nhân

### ## DoanDuyBach-2A202602515
- **Vai trò:** Thành viên duy nhất, phụ trách toàn bộ pipeline từ ingestion đến báo cáo đối chiếu.
- **Công việc chi tiết đã hoàn thành:**
  - `src/ingestion/crossref.py`: parse payload Crossref (bóc tag JATS, dedupe DOI, chuẩn hóa ngày), gọi API có retry cho 429/5xx và fallback về snapshot offline, lưu 2 raw artifacts.
  - `src/ingestion/cleaning.py`: chuẩn hóa text, tính `age_days`, sinh `text_for_embedding` 5 phần, khử trùng lặp theo `paper_id`.
  - `src/observability/quality.py`: Quality Gate GX 1.x (ephemeral context, `add_pandas`) với 4 expectation bắt buộc + 1 kiểm tra độ dài title; Freshness SLA 180 ngày / 25%.
  - `src/evaluation/testset.py`: 10 câu hỏi tất định thuộc 4 loại `summary`, `authors`, `date`, `categories`.
  - `src/ingestion/corruption.py`: 6 kịch bản lỗi có seed, ghi `corruption_log.json`.
  - `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`: điều phối, chặn index khi gate fail, tự động repair từ raw khi gate trip, kiểm tra idempotent bằng fingerprint.
  - `src/observability/reporting.py`: báo cáo Markdown pha 1 và bảng đối chiếu 3 trạng thái.
  - `src/retrieval/index.py`: sửa manifest để lưu đường dẫn Chroma tương đối (tránh hardcode đường dẫn tuyệt đối).
  - `tests/test_pipeline.py`: 8 test pytest cho ingestion, cleaning, GX gate, corruption, test set.
  - Cài Ollama + `qwen2.5:7b` chạy local để LLM judge và agent demo hoạt động không cần API key; siết prompt judge.
- **Kết quả:** Baseline hit rate 1.0 / token F1 1.0 / judge accuracy 1.0 → Corrupted 0.8 / 0.6568 / 0.6 → Repaired 1.0 / 1.0 / 1.0.
- **Điều học được / Đóng góp chính:**
  - Silent failure: agent vẫn trả lời đủ 10/10 câu trên dữ liệu hỏng, chỉ Quality Gate và Freshness SLA mới báo lỗi.
  - Repair đúng nghĩa là rebuild từ raw bất biến bằng cùng code cleaning, không vá tay dữ liệu hỏng; fingerprint trùng baseline chứng minh tính idempotent.
- **Công cụ hỗ trợ:** Có sử dụng Claude Code (AI assistant) để hỗ trợ viết code và báo cáo theo chính sách AI tại `docs/RULES.md` mục 3; mọi kết quả đã được chạy lại và kiểm chứng trên artifact thực tế.
