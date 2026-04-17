package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"mime/multipart"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
)

// ─── Models ───────────────────────────────────────────────────

type Zone struct {
	ID           uint   `gorm:"primaryKey" json:"id"`
	Name         string `json:"name"`
	VerticesJSON string `json:"vertices_json"`
	Color        string `json:"color"`
	Active       bool   `json:"active"`
	RiskLevel    string `json:"risk_level"`
	CreatedAt    time.Time
}

type Alert struct {
	ID                uint    `gorm:"primaryKey" json:"id"`
	ZoneID            uint    `json:"zone_id"`
	Confidence        float64 `json:"confidence"`
	SnapshotPath      string  `json:"snapshot_path"`
	Timestamp         time.Time
	ShutdownTriggered bool   `json:"shutdown_triggered"`
	PersonName        string `json:"person_name"`
	UniformCode       string `json:"uniform_code"`
}

type Face struct {
	ID           string    `gorm:"primaryKey" json:"id"`
	Name         string    `json:"name"`
	Code         string    `json:"code"`
	Phone        string    `json:"phone"` // Kolom WhatsApp Personel
	ImagePath    string    `json:"image_path"`
	RegisteredAt time.Time `json:"registered_at"`
}

type Setting struct {
	Key   string `gorm:"primaryKey" json:"key"`
	Value string `json:"value"`
}

// ─── WhatsApp Notifier (Go Implementation) ────────────────────

func sendWhatsApp(target, message, token string) {
	if token == "" {
		log.Println("⚠️ WA Skip: No token")
		return
	}
	apiURL := "https://api.fonnte.com/send"
	data := fmt.Sprintf("target=%s&message=%s", target, message)
	
	req, _ := http.NewRequest("POST", apiURL, bytes.NewBufferString(data))
	req.Header.Set("Authorization", token)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		log.Println("❌ WA Error:", err)
		return
	}
	defer resp.Body.Close()
	log.Println("✅ WA Sent to:", target)
}

// ─── State Management ─────────────────────────────────────────

var (
	db        *gorm.DB
	upgrader  = websocket.Upgrader{CheckOrigin: func(r *http.Request) bool { return true }}
	clients   = make(map[*websocket.Conn]bool)
	clientsMu sync.Mutex
)

func initDB() {
	var err error
	db, err = gorm.Open(sqlite.Open("../siews.db"), &gorm.Config{})
	if err != nil {
		log.Fatal(err)
	}
	db.AutoMigrate(&Zone{}, &Alert{}, &Face{}, &Setting{})
}

// ─── AI Client ────────────────────────────────────────────────

type AIResult struct {
	Persons []struct {
		Bbox       []float64 `json:"bbox"`
		Confidence float64   `json:"confidence"`
		FaceName   string    `json:"face_name"`
		OCRCode    string    `json:"ocr_code"`
	} `json:"persons"`
	Hazards []interface{} `json:"hazards"`
}

func callAIWorker(img []byte) (*AIResult, error) {
	buf := new(bytes.Buffer)
	writer := multipart.NewWriter(buf)
	part, _ := writer.CreateFormFile("file", "frame.jpg")
	part.Write(img)
	writer.Close()

	resp, err := http.Post("http://localhost:8003/detect", writer.FormDataContentType(), buf)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var res AIResult
	json.NewDecoder(resp.Body).Decode(&res)
	return &res, nil
}

// ─── Polygon Logic ───────────────────────────────────────────

func pointInPolygon(x, y float64, vertices [][]float64) bool {
	inside := false
	j := len(vertices) - 1
	for i := 0; i < len(vertices); i++ {
		if (vertices[i][1] > y) != (vertices[j][1] > y) &&
			(x < (vertices[j][0]-vertices[i][0])*(y-vertices[i][1])/(vertices[j][1]-vertices[i][1])+vertices[i][0]) {
			inside = !inside
		}
		j = i
	}
	return inside
}

// ─── Logic Loop (The Orchestrator) ───────────────────────────

func loop() {
	ticker := time.NewTicker(500 * time.Millisecond) // Check every 0.5s for responsiveness
	for range ticker.C {
		var zones []Zone
		db.Where("active = ?", true).Find(&zones)
		if len(zones) == 0 { continue }

		// In actual production, we get the current frame from the camera
		// For this setup, we request the latest detection results from AI Worker
		_, err := http.Get("http://localhost:8001/ai_sync_frame") // Simulated hook
		if err != nil {
			// Fallback to static if live fails
			img, err := os.ReadFile("../bus.jpg")
			if err != nil { continue }
			res, err := callAIWorker(img)
			if err != nil { continue }
			processDetections(res, zones)
		}
	}
}

func processDetections(res *AIResult, zones []Zone) {
	for _, p := range res.Persons {
		px := (p.Bbox[0] + p.Bbox[2]) / 2 / 640
		py := p.Bbox[3] / 480
		for _, z := range zones {
			var vertices [][]float64
			json.Unmarshal([]byte(z.VerticesJSON), &vertices)
			if pointInPolygon(px, py, vertices) {
				handleViolation(p.FaceName, p.OCRCode, z, p.Confidence)
			}
		}
	}
}

func handleViolation(name, code string, zone Zone, conf float64) {
	alert := Alert{
		ZoneID:            zone.ID,
		Confidence:        conf,
		Timestamp:         time.Now(),
		PersonName:        name,
		UniformCode:       code,
		ShutdownTriggered: zone.RiskLevel == "high",
	}
	db.Create(&alert)
	broadcast(alert)

	// Get Settings for WA
	var tokenSetting, recipientsSetting Setting
	db.Where("key = ?", "fonnte_token").First(&tokenSetting)
	db.Where("key = ?", "recipients").First(&recipientsSetting)

	if tokenSetting.Value != "" && recipientsSetting.Value != "" {
		msg := fmt.Sprintf("🚨 ALERT SIEWS+\nFasilitas: Migas TW2\nZona: %s\nPersonel: %s\nID Seragam: %s\nRisiko: %s", 
			zone.Name, name, code, zone.RiskLevel)
		go sendWhatsApp(recipientsSetting.Value, msg, tokenSetting.Value)
	}
}

func broadcast(alert Alert) {
	clientsMu.Lock()
	defer clientsMu.Unlock()
	for c := range clients {
		c.WriteJSON(alert)
	}
}

// ─── API Master ──────────────────────────────────────────────

func main() {
	initDB()
	go loop()

	r := gin.Default()
	
	// Robust CORS Middleware
	r.Use(func(c *gin.Context) {
		c.Writer.Header().Set("Access-Control-Allow-Origin", "*")
		c.Writer.Header().Set("Access-Control-Allow-Credentials", "true")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type, Content-Length, Accept-Encoding, X-CSRF-Token, Authorization, accept, origin, Cache-Control, X-Requested-With")
		c.Writer.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS, GET, PUT, DELETE")

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}
		c.Next()
	})

	// Zones API
	r.GET("/polygons", func(c *gin.Context) {
		zones := []Zone{}
		db.Find(&zones)
		
		type ZoneResponse struct {
			ID        uint        `json:"id"`
			Name      string      `json:"name"`
			Vertices  [][]float64 `json:"vertices"`
			Color     string      `json:"color"`
			IsActive  bool        `json:"is_active"`
			RiskLevel string      `json:"risk_level"`
		}
		
		res := []ZoneResponse{}
		for _, z := range zones {
			var v [][]float64
			json.Unmarshal([]byte(z.VerticesJSON), &v)
			res = append(res, ZoneResponse{
				ID:        z.ID,
				Name:      z.Name,
				Vertices:  v,
				Color:     z.Color,
				IsActive:  z.Active,
				RiskLevel: z.RiskLevel,
			})
		}
		c.JSON(200, res)
	})

	r.GET("/stats", func(c *gin.Context) {
		var activeZones, totalAlerts int64
		db.Model(&Zone{}).Where("active = ?", true).Count(&activeZones)
		db.Model(&Alert{}).Count(&totalAlerts)
		c.JSON(200, gin.H{
			"active_zones": activeZones,
			"today_alerts": totalAlerts,
			"camera_status": "online",
		})
	})
    
    r.GET("/faces", func(c *gin.Context) {
        faces := []Face{}
        db.Find(&faces)
        c.JSON(200, faces)
    })

	r.POST("/faces/register", func(c *gin.Context) {
		name := c.Query("name")
		code := c.Query("code")
		phone := c.Query("phone")
		log.Printf("📥 REG-REQ: %s | %s | %s", name, code, phone)
		
		file, err := c.FormFile("file")
		if err != nil {
			log.Println("❌ NO FILE:", err)
			c.JSON(400, gin.H{"error": "No file uploaded"})
			return
		}

		id := fmt.Sprintf("face_%d", time.Now().Unix())
		path := fmt.Sprintf("../static/faces/%s.jpg", id)
		
		if err := c.SaveUploadedFile(file, path); err != nil {
			log.Println("❌ SAVE ERROR:", err)
			c.JSON(500, gin.H{"error": "Failed to save file"})
			return
		}

		face := Face{
			ID:           id,
			Name:         name,
			Code:         code,
			Phone:        phone,
			ImagePath:    fmt.Sprintf("static/faces/%s.jpg", id),
			RegisteredAt: time.Now(),
		}
		if result := db.Create(&face); result.Error != nil {
			log.Println("❌ DB ERROR:", result.Error)
			c.JSON(500, gin.H{"error": "Database write failed"})
			return
		}
		
		log.Println("✅ REGISTERED:", id)
		http.Post("http://localhost:8003/train", "application/json", nil)
		c.JSON(200, face)
	})

	r.GET("/ws/alerts", func(c *gin.Context) {
		conn, _ := upgrader.Upgrade(c.Writer, c.Request, nil)
		clientsMu.Lock()
		clients[conn] = true
		clientsMu.Unlock()
	})

	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{"status": "ok"})
	})

	// Serve Static Files (Snapshots & Faces)
	r.Static("/static", "../static")

	log.Println("🚀 SIEWS+ MASTER BACKEND (GO) ON :8001")
	r.Run(":8001")
}
