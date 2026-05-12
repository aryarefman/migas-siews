package api

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
)

// FaceEntry represents a registered face
type FaceEntry struct {
	ID           string `json:"id"`
	Name         string `json:"name"`
	Code         string `json:"code"`
	Phone        string `json:"phone"`
	ImageURL     string `json:"image_url"`
	RegisteredAt string `json:"registered_at"`
}

// FaceDatabase stores registered faces (in-memory for now, can be migrated to DB)
var FaceDatabase = make(map[string]FaceEntry)
var FaceDatabaseDir = "faces_db"

func init() {
	// Create faces database directory
	if err := os.MkdirAll(FaceDatabaseDir, 0755); err != nil {
		log.Printf("Failed to create faces database directory: %v", err)
	}
}

// extractTextFromImage uses EasyOCR via Python inference service
func extractTextFromImage(imagePath string) (string, error) {
	// Read image file
	imageData, err := os.ReadFile(imagePath)
	if err != nil {
		log.Printf("[OCR] Failed to read image: %v", err)
		return "", err
	}

	// Encode to base64
	imageB64 := base64Encode(imageData)

	// Call Python inference service for OCR
	ocrReq := map[string]string{
		"image_b64": imageB64,
	}

	reqBody, err := json.Marshal(ocrReq)
	if err != nil {
		return "", err
	}

	resp, err := http.Post("http://localhost:8001/ocr", "application/json", bytes.NewReader(reqBody))
	if err != nil {
		log.Printf("[OCR] Failed to call inference service: %v", err)
		return "", nil // Don't fail, just skip OCR
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		log.Printf("[OCR] Inference service returned %d", resp.StatusCode)
		return "", nil
	}

	var result struct {
		Text string `json:"text"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		log.Printf("[OCR] Failed to decode response: %v", err)
		return "", nil
	}

	text := strings.TrimSpace(result.Text)
	log.Printf("[OCR] Extracted text: %s", text)
	return text, nil
}

func base64Encode(data []byte) string {
	return base64.StdEncoding.EncodeToString(data)
}

// RegisterFace handles face registration with OCR integration
func (s *Server) RegisterFace(c *gin.Context) {
	name := c.Query("name")
	code := c.Query("code")
	phone := c.Query("phone")

	if name == "" || phone == "" {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "Name and phone are required"})
		return
	}

	file, err := c.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "No file uploaded"})
		return
	}

	// Generate unique ID
	id := fmt.Sprintf("face_%d", time.Now().UnixNano())

	// Save image
	ext := filepath.Ext(file.Filename)
	filename := id + ext
	filepath := filepath.Join(FaceDatabaseDir, filename)
	if err := c.SaveUploadedFile(file, filepath); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "Failed to save image"})
		return
	}

	// Perform OCR to extract text from image
	ocrText, _ := extractTextFromImage(filepath)

	// If name not provided, try to extract from OCR
	if name == "" && ocrText != "" {
		// Use first line of OCR text as name
		lines := strings.Split(ocrText, "\n")
		if len(lines) > 0 && strings.TrimSpace(lines[0]) != "" {
			name = strings.TrimSpace(lines[0])
		}
	}

	// Store in database
	face := FaceEntry{
		ID:           id,
		Name:         name,
		Code:         code,
		Phone:        phone,
		ImageURL:     "/faces/images/" + filename,
		RegisteredAt: time.Now().UTC().Format(time.RFC3339),
	}
	FaceDatabase[id] = face

	log.Printf("[FACES] Registered face: %s (%s) - OCR: %s", name, id, ocrText)
	c.JSON(http.StatusOK, face)
}

// GetFaces returns all registered faces
func (s *Server) GetFaces(c *gin.Context) {
	faces := make([]FaceEntry, 0, len(FaceDatabase))
	for _, face := range FaceDatabase {
		faces = append(faces, face)
	}
	c.JSON(http.StatusOK, faces)
}

// DeleteFace deletes a registered face
func (s *Server) DeleteFace(c *gin.Context) {
	id := c.Param("id")
	if _, exists := FaceDatabase[id]; !exists {
		c.JSON(http.StatusNotFound, gin.H{"detail": "Face not found"})
		return
	}

	// Delete from database
	delete(FaceDatabase, id)

	// Delete image file
	filename := id + ".jpg" // Assume jpg for now
	filepath := filepath.Join(FaceDatabaseDir, filename)
	os.Remove(filepath)

	log.Printf("[FACES] Deleted face: %s", id)
	c.JSON(http.StatusOK, gin.H{"status": "deleted"})
}

// TrainFaces triggers face recognition training
func (s *Server) TrainFaces(c *gin.Context) {
	// This would trigger the face recognition training process
	// For now, just return success
	log.Printf("[FACES] Training triggered for %d faces", len(FaceDatabase))
	c.JSON(http.StatusOK, gin.H{"status": "training_started", "faces_count": len(FaceDatabase)})
}

// ServeFaceImage serves uploaded face images
func (s *Server) ServeFaceImage(c *gin.Context) {
	filename := c.Param("filename")
	filepath := filepath.Join(FaceDatabaseDir, filename)
	c.File(filepath)
}

// RegisterFaceRoutes registers face-related routes
func (s *Server) RegisterFaceRoutes() {
	faces := s.router.Group("/faces")
	{
		faces.GET("", s.GetFaces)
		faces.POST("/register", s.RegisterFace)
		faces.POST("/train", s.TrainFaces)
		faces.DELETE("/:id", s.DeleteFace)
		faces.GET("/images/:filename", s.ServeFaceImage)
	}
}
