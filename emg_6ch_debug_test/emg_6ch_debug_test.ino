/*
 * emg_6ch_debug_test.ino
 * -----------------------------------------------------------
 * DEBUG-ONLY SKETCH — KHÔNG dùng để thu thập dữ liệu thật.
 * Mục đích: kiểm tra nhanh cả 6 cảm biến A10-09 trước khi chuyển
 * sang firmware logging (emg_6ch_logger_v1_1.ino), và quan sát:
 *   - Mỗi kênh có phản hồi hợp lý khi co cơ không
 *   - Baseline lúc nghỉ (rest) của từng kênh, và độ ồn (noise) quanh nó
 *   - Cross-talk: khi chỉ co 1 vị trí cơ, kênh khác có "ăn theo" không
 *
 * Output dạng bảng người đọc được (KHÔNG phải CSV protocol của Logger),
 * tốc độ in được throttle để mắt người theo dõi kịp — không chạy 500Hz.
 *
 * Gửi ký tự 'r' qua Serial Monitor để reset lại baseline + min/max
 * (hữu ích khi vừa di chuyển điện cực hoặc đổi cử chỉ test).
 * -----------------------------------------------------------
 */

#include <Arduino.h>

// ---------- CONFIG ----------
#define NUM_CHANNELS 6
const int adcPins[NUM_CHANNELS] = {1, 2, 4, 5, 6, 7};  // GPIO an toàn ADC1
const char* chLabel[NUM_CHANNELS] = {"CH1", "CH2", "CH3", "CH4", "CH5", "CH6"};

const uint32_t WARMUP_READS      = 50;
const uint32_t BASELINE_SAMPLES  = 200;   // ~ lấy baseline nghỉ lúc khởi động
const uint32_t PRINT_INTERVAL_MS = 100;   // throttle in ra ~10Hz cho dễ đọc
const int      BAR_MAX_WIDTH     = 30;    // độ rộng thanh bar ASCII

// ---------- STATE ----------
uint16_t raw[NUM_CHANNELS];
uint16_t baseline[NUM_CHANNELS];
uint16_t runMin[NUM_CHANNELS];
uint16_t runMax[NUM_CHANNELS];

uint32_t lastPrintMs = 0;

// ---------- HELPERS ----------
void computeBaseline() {
  Serial.println("Dang do baseline nghi (giu yen tay, khong co co)...");
  uint32_t sums[NUM_CHANNELS] = {0};

  for (uint32_t s = 0; s < BASELINE_SAMPLES; s++) {
    for (int i = 0; i < NUM_CHANNELS; i++) {
      sums[i] += analogRead(adcPins[i]);
    }
    delay(2);  // ~2ms/sample -> tổng ~400ms lấy baseline
  }

  for (int i = 0; i < NUM_CHANNELS; i++) {
    baseline[i] = sums[i] / BASELINE_SAMPLES;
    runMin[i] = baseline[i];
    runMax[i] = baseline[i];
  }

  Serial.print("Baseline: ");
  for (int i = 0; i < NUM_CHANNELS; i++) {
    Serial.printf("%s=%u  ", chLabel[i], baseline[i]);
  }
  Serial.println();
  Serial.println("Neu cac gia tri baseline chenh lech qua lon giua cac kenh (vd >300),");
  Serial.println("co the do vi tri dat dien cuc khac nhau -> binh thuong, se xu ly offline.");
  Serial.println();
}

void resetTracking() {
  Serial.println();
  Serial.println(">>> RESET: do lai baseline va min/max <<<");
  computeBaseline();
}

void printHeader() {
  Serial.println("--------------------------------------------------------------------------------------------------------");
  Serial.print("  ");
  for (int i = 0; i < NUM_CHANNELS; i++) {
    Serial.printf("%-6s ", chLabel[i]);
  }
  Serial.println(" | Gui 'r' de reset baseline");
  Serial.println("--------------------------------------------------------------------------------------------------------");
}

void printBar(int16_t delta) {
  // Bar đơn giản: delta dương kéo dài sang phải, giúp thấy trực quan kênh nào đang "kích hoạt"
  int width = constrain(abs(delta) / 10, 0, BAR_MAX_WIDTH);
  Serial.print(delta >= 0 ? '+' : '-');
  for (int i = 0; i < width; i++) Serial.print('#');
}

// ---------- SETUP ----------
void setup() {
  Serial.begin(921600);
  delay(2000);

  analogReadResolution(12);
  for (int i = 0; i < NUM_CHANNELS; i++) {
    analogSetPinAttenuation(adcPins[i], ADC_11db);
  }

  // Warmup ADC
  for (uint32_t w = 0; w < WARMUP_READS; w++) {
    for (int i = 0; i < NUM_CHANNELS; i++) analogRead(adcPins[i]);
  }

  Serial.println();
  Serial.println("=== EMG 6-CHANNEL DEBUG TEST ===");
  Serial.println("Muc dich: kiem tra cam bien truoc khi chuyen sang firmware logging.");
  Serial.println();

  computeBaseline();
  printHeader();
}

// ---------- LOOP ----------
void loop() {
  // Đọc lệnh reset từ Serial
  if (Serial.available() > 0) {
    char c = Serial.read();
    if (c == 'r' || c == 'R') {
      resetTracking();
      printHeader();
    }
  }

  // Đọc 6 kênh liên tục (không throttle phần đọc, chỉ throttle phần IN)
  for (int i = 0; i < NUM_CHANNELS; i++) {
    raw[i] = analogRead(adcPins[i]);
    if (raw[i] < runMin[i]) runMin[i] = raw[i];
    if (raw[i] > runMax[i]) runMax[i] = raw[i];
  }

  uint32_t now = millis();
  if (now - lastPrintMs >= PRINT_INTERVAL_MS) {
    lastPrintMs = now;

    // Dòng 1: giá trị raw hiện tại + delta so với baseline
    Serial.print("  ");
    for (int i = 0; i < NUM_CHANNELS; i++) {
      int16_t delta = (int16_t)raw[i] - (int16_t)baseline[i];
      Serial.printf("%5d  ", raw[i]);
    }
    Serial.print(" | ");
    for (int i = 0; i < NUM_CHANNELS; i++) {
      int16_t delta = (int16_t)raw[i] - (int16_t)baseline[i];
      Serial.printf("%s:", chLabel[i]);
      printBar(delta);
      Serial.print("  ");
    }
    Serial.println();
  }
}

/*
 * CÁCH DÙNG ĐỂ KIỂM TRA CROSS-TALK:
 * 1. Gắn đủ 6 cảm biến, giữ tay yên, chạy sketch -> quan sát baseline + noise ở rest.
 * 2. Co CHỈ 1 vị trí cơ tương ứng 1 kênh -> quan sát bar của kênh đó phải nổi bật.
 *    Nếu kênh khác cũng nhảy đáng kể theo -> nghi ngờ cross-talk (dây tín hiệu đi
 *    gần nhau, thiếu star ground, hoặc REF chung đặt sai vị trí).
 * 3. Gửi 'r' để rebaseline khi đổi tư thế / dịch điện cực.
 */
