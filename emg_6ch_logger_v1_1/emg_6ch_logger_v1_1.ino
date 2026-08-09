/*
===========================================================
 ESP32-S3 EMG Data Acquisition Firmware
 Version : 1.1 (sua tu ban goc cua Quang: fix pin + gop buffer)
 Purpose : Record RAW EMG Dataset - Phase 1, khong filter
===========================================================
*/
#define NUM_CHANNELS 6

// ======= Chan ADC1 da xac nhan an toan (tranh WiFi + strapping pin) =======
const uint8_t EMG_PIN[NUM_CHANNELS] = {5, 6, 7, 9, 10, 11};

// ======= Sampling =======
const uint32_t SAMPLE_RATE = 500;               // Hz
const uint32_t SAMPLE_INTERVAL_US = 1000000UL / SAMPLE_RATE;

uint32_t sequence = 0;
uint32_t nextSampleTime;

char lineBuf[128];  // gop 1 dong roi gui 1 lan, giam so lan goi Serial.print

void setup()
{
  Serial.begin(921600);
  analogReadResolution(12);
  for (int i = 0; i < NUM_CHANNELS; i++)
  {
    pinMode(EMG_PIN[i], INPUT);
    analogSetPinAttenuation(EMG_PIN[i], ADC_11db);
  }

  // "khoi dong" ADC vai lan cho on dinh truoc khi bat dau gui data that
  for (int w = 0; w < 50; w++)
  {
    for (int i = 0; i < NUM_CHANNELS; i++) analogRead(EMG_PIN[i]);
  }

  delay(200);
  Serial.println("# ESP32-S3 EMG DAQ READY");
  Serial.println("# Format: SEQ,TIME_US,CH1,CH2,CH3,CH4,CH5,CH6");

  nextSampleTime = micros();
}

void loop()
{
  while ((int32_t)(micros() - nextSampleTime) >= 0)
  {
    nextSampleTime += SAMPLE_INTERVAL_US;

    uint32_t timestamp = micros();
    int adc[NUM_CHANNELS];

    for (int i = 0; i < NUM_CHANNELS; i++)
    {
      adc[i] = analogRead(EMG_PIN[i]);
    }

    int n = snprintf(lineBuf, sizeof(lineBuf),
                      "%lu,%lu,%d,%d,%d,%d,%d,%d",
                      (unsigned long)sequence, (unsigned long)timestamp,
                      adc[0], adc[1], adc[2], adc[3], adc[4], adc[5]);

    if (n > 0)
    {
      Serial.write(lineBuf, n);
      Serial.write('\n');
    }

    sequence++;
  }
}
