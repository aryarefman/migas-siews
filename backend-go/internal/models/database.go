package models

import (
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"gorm.io/driver/postgres"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

var DB *gorm.DB

// InitDB initializes the database connection
func InitDB() (*gorm.DB, error) {
	var db *gorm.DB
	var err error

	databaseURL := os.Getenv("DATABASE_URL")

	// Default to SQLite if no DATABASE_URL is set
	if databaseURL == "" {
		databaseURL = "siews.db"
	}

	// Check if it's a SQLite database (file path or sqlite:// prefix)
	if len(databaseURL) >= 8 && databaseURL[:8] == "sqlite://" {
		// Remove "sqlite://" prefix for SQLite driver
		databaseURL = databaseURL[10:]
	}

	// Check if it looks like a SQLite file (not a connection string)
	if !strings.Contains(databaseURL, "host=") && !strings.Contains(databaseURL, "user=") {
		// SQLite
		db, err = gorm.Open(sqlite.Open(databaseURL), &gorm.Config{
			Logger: logger.Default.LogMode(logger.Warn),
		})
	} else {
		// PostgreSQL
		db, err = gorm.Open(postgres.Open(databaseURL), &gorm.Config{
			Logger: logger.Default.LogMode(logger.Warn),
		})
	}

	if err != nil {
		return nil, fmt.Errorf("failed to connect to database: %w", err)
	}

	// Configure connection pool
	sqlDB, err := db.DB()
	if err == nil {
		sqlDB.SetMaxIdleConns(10)
		sqlDB.SetMaxOpenConns(100)
		sqlDB.SetConnMaxLifetime(time.Hour)
	}

	// Auto migrate models
	err = db.AutoMigrate(
		&Zone{},
		&Alert{},
		&DetectionLog{},
		&ShutdownLog{},
		&Setting{},
		&VideoJob{},
		&ZoneOccupancy{},
	)
	if err != nil {
		return nil, fmt.Errorf("failed to migrate database: %w", err)
	}

	// Seed default settings
	seedDefaultSettings(db)

	DB = db
	log.Println("Database connected and migrated successfully")
	return db, nil
}

// seedDefaultSettings seeds default settings if not present
func seedDefaultSettings(db *gorm.DB) {
	defaults := map[string]string{
		"camera_source":        "0",
		"facility_name":        "Offshore Platform A",
		"confidence_threshold": "0.5",
		"detection_interval":   "3",
		"notify_cooldown":      "300",
		"fonnte_token":         "",
		"recipients":           "",
	}

	for key, value := range defaults {
		var setting Setting
		if db.Where("key = ?", key).First(&setting).Error != nil {
			db.Create(&Setting{Key: key, Value: value})
		}
	}
}

// ============================================================================
// Database Models
// ============================================================================

// Zone represents a restricted zone with polygon coordinates
type Zone struct {
	ID             uint          `gorm:"primaryKey" json:"id"`
	Name           string        `gorm:"size:100;not null" json:"name"`
	VerticesJSON   string        `gorm:"type:text;not null" json:"vertices_json"` // JSON array of [x, y] normalized floats
	Color          string        `gorm:"size:7;default:#FF0000" json:"color"`
	Active         bool          `gorm:"default:true" json:"active"`
	RiskLevel      string        `gorm:"size:10;default:high" json:"risk_level"` // "low" | "high"
	ZoneType       string        `gorm:"size:20;default:restricted" json:"zone_type"`
	DwellThreshold int           `gorm:"default:10" json:"dwell_threshold_sec"`
	CreatedAt      time.Time     `json:"created_at"`
	Alerts         []Alert       `gorm:"foreignKey:ZoneID" json:"alerts,omitempty"`
	ShutdownLogs   []ShutdownLog `gorm:"foreignKey:ZoneID" json:"shutdown_logs,omitempty"`
}

// Alert represents a safety violation alert
type Alert struct {
	ID                uint           `gorm:"primaryKey" json:"id"`
	ZoneID            uint           `gorm:"not null" json:"zone_id"`
	Confidence        float64        `json:"confidence"`
	SnapshotPath      string         `gorm:"size:255" json:"snapshot_path"`
	Timestamp         time.Time      `json:"timestamp"`
	ShutdownTriggered bool           `gorm:"default:false" json:"shutdown_triggered"`
	Resolved          bool           `gorm:"default:false" json:"resolved"`
	ViolationType     string         `gorm:"size:30;default:restricted_area" json:"violation_type"` // "restricted_area" | "missing_ppe" | "no_harness" | "fire_smoke" | "multiple"
	FalsePositive     bool           `gorm:"default:false" json:"false_positive"`
	PPEDetail         string         `gorm:"type:text" json:"ppe_detail"` // JSON object
	PersonsCount      int            `gorm:"default:0" json:"persons_count"`
	Zone              *Zone          `gorm:"foreignKey:ZoneID" json:"zone,omitempty"`
	DetectionLogs     []DetectionLog `gorm:"foreignKey:AlertID" json:"detection_logs,omitempty"`
}

// DetectionLog represents per-object crop logging for each alert
type DetectionLog struct {
	ID              uint      `gorm:"primaryKey" json:"id"`
	AlertID         *uint     `json:"alert_id"`
	ClassName       string    `gorm:"size:50;not null" json:"class_name"` // e.g. "no_helmet", "fire"
	Confidence      float64   `json:"confidence"`
	CropPath        string    `gorm:"size:255" json:"crop_path"`
	FrameNumber     int       `json:"frame_number"`
	BBoxJSON        string    `gorm:"type:text" json:"bbox_json"` // JSON array [x1, y1, x2, y2]
	IsFalsePositive bool      `gorm:"default:false" json:"is_false_positive"`
	CreatedAt       time.Time `json:"created_at"`
	Alert           *Alert    `gorm:"foreignKey:AlertID" json:"alert,omitempty"`
}

// ShutdownLog records shutdown events
type ShutdownLog struct {
	ID            uint      `gorm:"primaryKey" json:"id"`
	ZoneID        uint      `gorm:"not null" json:"zone_id"`
	TriggerSource string    `gorm:"size:20;default:auto" json:"trigger_source"` // "auto" or "manual"
	TriggeredAt   time.Time `json:"triggered_at"`
	Zone          *Zone     `gorm:"foreignKey:ZoneID" json:"zone,omitempty"`
}

// Setting represents a key-value system setting
type Setting struct {
	ID    uint   `gorm:"primaryKey" json:"id"`
	Key   string `gorm:"size:50;uniqueIndex;not null" json:"key"`
	Value string `gorm:"type:text;default:" json:"value"`
}

// VideoJob tracks async video upload processing jobs
type VideoJob struct {
	ID              uint       `gorm:"primaryKey" json:"id"`
	Filename        string     `gorm:"size:255;not null" json:"filename"`
	FilePath        string     `gorm:"size:255;not null" json:"file_path"`
	Status          string     `gorm:"size:20;default:pending" json:"status"` // "pending" | "processing" | "done" | "failed"
	Progress        int        `gorm:"default:0" json:"progress"`             // 0-100 percent
	TotalFrames     int        `gorm:"default:0" json:"total_frames"`
	ProcessedFrames int        `gorm:"default:0" json:"processed_frames"`
	ResultJSON      string     `gorm:"type:text" json:"result_json"` // JSON array of frame detections
	ErrorMessage    string     `gorm:"type:text" json:"error_message"`
	CreatedAt       time.Time  `json:"created_at"`
	CompletedAt     *time.Time `json:"completed_at"`
}

// ZoneOccupancy tracks zone dwell-time events
type ZoneOccupancy struct {
	ID         uint       `gorm:"primaryKey" json:"id"`
	ZoneID     uint       `gorm:"not null" json:"zone_id"`
	TrackID    string     `gorm:"size:16;not null;index" json:"track_id"` // 8-char hex UUID
	EntryTime  time.Time  `gorm:"not null" json:"entry_time"`
	ExitTime   *time.Time `json:"exit_time"`
	DwellSec   float64    `gorm:"default:0.0" json:"dwell_sec"`
	AlertLevel string     `gorm:"size:10;default:none" json:"alert_level"` // "none" | "warning" | "critical"
	Zone       *Zone      `gorm:"foreignKey:ZoneID" json:"zone,omitempty"`
}

// ============================================================================
// Helper Functions
// ============================================================================

// GetSetting retrieves a setting value by key
func GetSetting(db *gorm.DB, key string) string {
	var setting Setting
	if db.Where("key = ?", key).First(&setting).Error == nil {
		return setting.Value
	}
	return ""
}

// UpdateSetting updates or creates a setting
func UpdateSetting(db *gorm.DB, key, value string) error {
	var setting Setting
	if db.Where("key = ?", key).First(&setting).Error != nil {
		return db.Create(&Setting{Key: key, Value: value}).Error
	}
	return db.Model(&setting).Update("value", value).Error
}

// GetAllSettings returns all settings as a map
func GetAllSettings(db *gorm.DB) map[string]string {
	settings := make(map[string]string)
	var rows []Setting
	db.Find(&rows)
	for _, s := range rows {
		settings[s.Key] = s.Value
	}
	return settings
}
