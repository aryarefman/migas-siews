## Ditulis untuk improving feature 12Mei 2026 - 17 Mei 2026

### Object Detection Problem

  Kenapa threshold perlu ada sama sekali?
  
  Model YOLO selalu menghasilkan confidence score untuk setiap deteksi. Tanpa threshold, semua
  prediksi — termasuk yang 5% confidence — akan dianggap valid. Threshold adalah "filter
  kepercayaan minimum".
  
  ────────────────────────────────────────────────────────────────────────────────────────────
  
  Pendekatan otomasi yang bisa dilakukan:
  
  1. Adaptive Threshold berdasarkan False Positive feedback (paling praktis)
  Kamu sudah punya tombol "FALSE POS" di dashboard. Setiap kali user klik itu, sistem bisa
  otomatis naikkan threshold untuk class tersebut. Sebaliknya kalau deteksi benar terus,
  threshold bisa turun sedikit. Ini semacam online learning dari feedback user.
  
  2. Scene Calibration (otomatis saat startup)
  Saat tidak ada orang di frame (misal jam malam), sistem rekam baseline — noise level, warna
  background, lighting. Deteksi yang terlalu mirip baseline dianggap false positive.
  
  3. Temporal Consistency (sudah bisa langsung)
  Smoke/fire yang nyata akan muncul di beberapa frame berturut-turut. Kalau hanya muncul 1-2
  frame lalu hilang, itu noise. Require N consecutive frames sebelum trigger alert.
  
  ────────────────────────────────────────────────────────────────────────────────────────────
  
  Rekomendasi saya: kombinasi 1 + 3 — paling efektif, tidak butuh data training tambahan.
  
  Mau saya implement? Kalau iya, saya akan:
  
  - Simpan feedback FALSE POS ke DB → auto-adjust threshold per class
  - Tambah temporal consistency (require 3 frame berturut-turut untuk fire/smoke alert)
