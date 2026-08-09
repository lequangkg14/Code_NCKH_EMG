// ==== Cấu hình 6 kênh EMG — dùng ADC1 (GPIO1-GPIO10) để tránh xung đột với WiFi ====
const int EMG_PIN[6] = {5, 6, 7, 9, 10, 11}; // GPIO1..GPIO6, đều là ADC1

const unsigned long SAMPLE_INTERVAL_US = 2000; // 500Hz
unsigned long lastSampleTime = 0;

const int WINDOW_SIZE = 30;
int buffer[6][WINDOW_SIZE];
int indexBuffer[6] = {0, 0, 0, 0, 0, 0};
long sum[6] = {0, 0, 0, 0, 0, 0};

// Baseline riêng từng kênh (nếu offset lệch nhau thì chỉnh lại từng giá trị)
int baseline[6] = {1300, 1300, 1300, 1300, 1300, 1300};

int thresholdHigh = 250;
int thresholdLow  = 120;

bool muscleActive[6] = {false, false, false, false, false, false};

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);

  for (int i = 0; i < 6; i++) {
    analogSetPinAttenuation(EMG_PIN[i], ADC_11db);
    for (int j = 0; j < WINDOW_SIZE; j++) buffer[i][j] = 0;
  }

  Serial.println("Đã cấu hình xong 6 kênh EMG.");
}

void loop() {
  unsigned long currentMicros = micros();
  if (currentMicros - lastSampleTime >= SAMPLE_INTERVAL_US) {
    lastSampleTime = currentMicros;

    int envelope[6];

    for (int i = 0; i < 6; i++) {
      int raw = analogRead(EMG_PIN[i]);
      int rectified = abs(raw - baseline[i]);

      sum[i] -= buffer[i][indexBuffer[i]];
      buffer[i][indexBuffer[i]] = rectified;
      sum[i] += rectified;
      indexBuffer[i] = (indexBuffer[i] + 1) % WINDOW_SIZE;

      envelope[i] = sum[i] / WINDOW_SIZE;

      if (!muscleActive[i] && envelope[i] > thresholdHigh) {
        muscleActive[i] = true;
      } else if (muscleActive[i] && envelope[i] < thresholdLow) {
        muscleActive[i] = false;
      }
    }

    // In CSV: env1..env6,state1..state6
    for (int i = 0; i < 6; i++) {
      Serial.print(envelope[i]);
      Serial.print(",");
    }
    for (int i = 0; i < 6; i++) {
      Serial.print(muscleActive[i] ? 1 : 0);
      if (i < 5) Serial.print(",");
    }
    Serial.println();
  }
}