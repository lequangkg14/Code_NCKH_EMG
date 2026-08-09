# EMG Logger - Sprint 1

Phần mềm Python nhận dữ liệu EMG 6 kênh qua Serial từ ESP32-S3 và lưu thành
CSV theo protocol frozen của dự án: `SEQ,TIME_US,CH1,CH2,CH3,CH4,CH5,CH6`.

## Cài đặt

```bash
pip install -r requirements.txt
```

## Chạy

```bash
python main.py
```

## Cách dùng

1. Cắm ESP32-S3, bấm **Refresh** để load danh sách COM port, chọn port đúng,
   bấm **Connect**.
2. Điền **Subject ID**, **Session ID**, **Donning position**, chọn **Gesture**,
   kiểm tra **Trial #** (tự tăng sau mỗi lần ghi).
3. Bấm **START** — phần mềm tự chạy timeline 8 giây:
   - 0–2s: Rest
   - 2–3s: Get ready (cue)
   - 3–6s: Hold (giữ gesture)
   - 6–8s: Relax
   Toàn bộ 8s được ghi liên tục vào 1 file CSV, các mốc thời gian
   (`cue_on_us`, `hold_start_us`, `hold_end_us`) lấy từ `TIME_US` thực tế
   nhận được từ ESP32 (không dùng đồng hồ máy tính) và lưu vào `metadata.json`.
4. Bấm **STOP** nếu cần huỷ trial giữa chừng — file vẫn được lưu nhưng
   đánh dấu `status: "aborted"` trong metadata để lọc ra khi xử lý dữ liệu.

## Output

```
Dataset/
  Subject_XX/
    Session_YY_posZ/
      metadata.json
      raw/
        S{subj}_Se{sess}_{gesture}_T{trial}.csv
```

`metadata.json` được cập nhật (append) sau mỗi trial, chứa danh sách trial
với marker thời gian và trạng thái (complete/aborted).

## Giới hạn Sprint 1 (chưa làm, để dành sprint sau)

- Chưa có realtime plot 6 kênh (PyQtGraph).
- Chưa check packet loss / jitter tự động (dựa vào `SEQ`) — hiện chỉ hiển
  thị sample rate thô mỗi giây.
- Chưa có `calibrateBaseline()` — trường `baseline_calibration` trong
  metadata hiện để trống, cần điền tay hoặc nối vào khi firmware có tính năng này.
