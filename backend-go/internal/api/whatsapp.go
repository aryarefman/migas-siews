package api

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

// ============================================================================
// Fonnte WhatsApp Client
// ============================================================================

// FonnteClient handles WhatsApp API integration via Fonnte
type FonnteClient struct {
	token      string
	baseURL    string
	httpClient *http.Client
}

// NewFonnteClient creates a new Fonnte client
func NewFonnteClient() *FonnteClient {
	token := os.Getenv("FONNTE_TOKEN")
	if token == "" {
		token = "" // Will be empty if not set
	}

	return &FonnteClient{
		token:   token,
		baseURL: "https://api.fonnte.com",
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// SendMessageRequest for Fonnte API
type SendMessageRequest struct {
	Target      string `json:"target"`
	Message     string `json:"message"`
	CountryCode string `json:"country_code"`
}

// SendMessageResponse from Fonnte API
type SendMessageResponse struct {
	Status bool   `json:"status"`
	Reason string `json:"reason"`
}

// SendMessage sends a WhatsApp message via Fonnte
func (c *FonnteClient) SendMessage(target, message string) error {
	if c.token == "" {
		return fmt.Errorf("FONNTE_TOKEN not set")
	}

	req := SendMessageRequest{
		Target:      target,
		Message:     message,
		CountryCode: "62", // Indonesia
	}

	reqBody, err := json.Marshal(req)
	if err != nil {
		return fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequest("POST", c.baseURL+"/send", bytes.NewReader(reqBody))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Authorization", c.token)
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("Fonnte API returned %d: %s", resp.StatusCode, string(body))
	}

	var result SendMessageResponse
	if err := json.Unmarshal(body, &result); err != nil {
		return fmt.Errorf("failed to decode response: %w", err)
	}

	if !result.Status {
		return fmt.Errorf("Fonnte API error: %s", result.Reason)
	}

	return nil
}

// SendAlertMessage sends an alert message to default recipients
func (c *FonnteClient) SendAlertMessage(alertType, zoneName, riskLevel string, confidence float64, shutdownTriggered bool) error {
	recipients := os.Getenv("DEFAULT_RECIPIENTS")
	if recipients == "" {
		return fmt.Errorf("DEFAULT_RECIPIENTS not set")
	}

	facility := os.Getenv("FACILITY_NAME")
	if facility == "" {
		facility = "Offshore Platform A"
	}

	// Format time in WIB (UTC+7)
	loc, _ := time.LoadLocation("Asia/Jakarta")
	wibTime := time.Now().In(loc).Format("02/01/2006 15:04:05 WIB")

	shutdownStatus := "TIDAK"
	if shutdownTriggered {
		shutdownStatus = "AKTIF"
	}

	message := fmt.Sprintf(
		"🚨 SIEWS+ ALERT — ZONA TERLARANG DILANGGAR\n\n"+
			"Fasilitas : %s\n"+
			"Zona      : %s\n"+
			"Risiko    : %s\n"+
			"Waktu     : %s\n"+
			"Confidence: %.0f%%\n"+
			"Shutdown  : %s\n\n"+
			"Segera periksa area dan ambil tindakan.",
		facility, zoneName, riskLevel, wibTime, confidence*100, shutdownStatus,
	)

	// Send to first recipient (can be expanded to send to all)
	return c.SendMessage(recipients, message)
}

// SendTestMessage sends a test message to recipients
func (c *FonnteClient) SendTestMessage(recipients, facility string) error {
	if c.token == "" {
		return fmt.Errorf("FONNTE_TOKEN not set")
	}

	if recipients == "" {
		return fmt.Errorf("no recipients configured")
	}

	// Format time in WIB
	loc, _ := time.LoadLocation("Asia/Jakarta")
	wibTime := time.Now().In(loc).Format("02/01/2006 15:04:05 WIB")

	message := fmt.Sprintf(
		"✅ SIEWS+ TEST MESSAGE\n\n"+
			"Fasilitas: %s\n"+
			"Waktu: %s\n\n"+
			"Ini adalah pesan uji coba dari sistem SIEWS+ 5.0.\n"+
			"Jika Anda menerima pesan ini, notifikasi WhatsApp berfungsi dengan baik.",
		facility, wibTime,
	)

	return c.SendMessage(recipients, message)
}
