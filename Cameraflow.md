 ## Flow untuk program nyalakan kamera
 
 Cara pakai:
  
  - Linux: ./siews.sh up -d — auto-detect /dev/video* yang ada, mount ke container
  - Windows: siews.bat up -d — jalankan tanpa device mount, tampilkan instruksi
  
  Kenapa Windows tidak bisa langsung pakai webcam di Docker:
  
  Docker Desktop di Windows menggunakan Hyper-V/WSL2 sebagai layer virtualisasi, sehingga USB
  device tidak bisa di-passthrough langsung. Opsi di Windows:
  
  1. IP Camera (RTSP) — set CAMERA_SOURCE=rtsp://... di backend/.env ✅ paling mudah
  2. usbipd-win — forward USB webcam ke WSL2, lalu jalankan ./siews.sh dari dalam WSL2
  
  File yang dibuat:
  
  - docker-compose.yml — base config (tanpa devices, cross-platform)
  - docker-compose.linux.yml — override khusus Linux (tambah device mapping)
  - siews.sh — launcher Linux/macOS
  - siews.bat — launcher Windows
