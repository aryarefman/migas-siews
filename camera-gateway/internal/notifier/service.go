package notifier

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
	"sync"
	"time"
)

// AlertData represents the data for an alert notification
type AlertData struct {
	CameraID          string
	ZoneName          string
	RiskLevel         string
	Confidence        float64
	ShutdownTriggered bool
	FacilityName      string
	Timestamp         time.Time
	SnapshotURL       string
}

// FonnteRequest represents the request to Fonnte API
type FonnteRequest struct {
	Target      string `json:"target"`
	Message     string `json:"message"`
	CountryCode string `json:"countryCode"`
}

// FonnteResponse represents the response from Fonnte API
type FonnteResponse struct {
	Status string `json:"status"`
	Reason string `json:"reason,omitempty"`
}

// FonnteClient handles communication with Fonnte API
type FonnteClient struct {
	Token   string
	Client  *http.Client
	BaseURL string
}

// NewFonnteClient creates a new Fonnte client
func NewFonnteClient(token string) *FonnteClient {
	return &FonnteClient{
		Token:   token,
		Client:  &http.Client{Timeout: 15 * time.Second},
		BaseURL: "https://api.fonnte.com/send",
	}
}

// Send sends a WhatsApp message via Fonnte API
func (f *FonnteClient) Send(phone, message string) (*FonnteResponse, error) {
	req := FonnteRequest{
		Target:      phone,
		Message:     message,
		CountryCode: "62",
	}

	jsonData, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequest("POST", f.BaseURL, strings.NewReader(string(jsonData)))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Authorization", f.Token)
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := f.Client.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	var result FonnteResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// NotificationService manages WhatsApp notifications
type NotificationService struct {
	fonnteClient     *FonnteClient
	recipients       []string
	cooldownMap      map[string]time.Time
	cooldownDuration time.Duration
	mu               sync.RWMutex
	facilityName     string
}

// NewNotificationService creates a new notification service
func NewNotificationService(fonnteToken, recipientsStr, facilityName string, cooldownMin int) *NotificationService {
	recipients := parseRecipients(recipientsStr)

	return &NotificationService{
		fonnteClient:     NewFonnteClient(fonnteToken),
		recipients:       recipients,
		cooldownMap:      make(map[string]time.Time),
		cooldownDuration: time.Duration(cooldownMin) * time.Minute,
		facilityName:     facilityName,
	}
}

// SendAlert sends an alert notification to all recipients
func (ns *NotificationService) SendAlert(ctx context.Context, data AlertData) error {
	// Check cooldown
	cooldownKey := fmt.Sprintf("%s_%s", data.CameraID, data.ZoneName)
	if ns.isInCooldown(cooldownKey) {
		log.Printf("Notification: Alert in cooldown for %s", cooldownKey)
		return nil
	}

	// Build message
	message := ns.buildAlertMessage(data)

	// Send to all recipients concurrently
	var wg sync.WaitGroup
	errChan := make(chan error, len(ns.recipients))

	for _, recipient := range ns.recipients {
		wg.Add(1)
		go func(phone string) {
			defer wg.Done()

			if ns.fonnteClient == nil || ns.fonnteClient.Token == "" {
				log.Printf("[NOTIFIER] No Fonnte token set. Message would be sent to %s", phone)
				log.Printf("[NOTIFIER] Message: %s", message)
				errChan <- fmt.Errorf("no_token")
				return
			}

			resp, err := ns.fonnteClient.Send(phone, message)
			if err != nil {
				log.Printf("[NOTIFIER] Failed to send to %s: %v", phone, err)
				errChan <- err
				return
			}

			log.Printf("[NOTIFIER] Sent to %s: %v", phone, resp.Status)
		}(recipient)
	}

	wg.Wait()
	close(errChan)

	// Update cooldown
	ns.updateCooldown(cooldownKey)

	// Return first error if any
	select {
	case err := <-errChan:
		return err
	default:
		return nil
	}
}

// SendTestMessage sends a test message to all recipients
func (ns *NotificationService) SendTestMessage(ctx context.Context) error {
	message := fmt.Sprintf("✅ SIEWS+ TEST MESSAGE\n\nFasilitas: %s\nWaktu: %s\n\nIni adalah pesan uji coba dari sistem SIEWS+.",
		ns.facilityName,
		time.Now().Format("02/01/2006 15:04:05 WIB"))

	results := make([]map[string]interface{}, 0)

	for _, recipient := range ns.recipients {
		result := map[string]interface{}{
			"phone": recipient,
		}

		if ns.fonnteClient == nil || ns.fonnteClient.Token == "" {
			log.Printf("[NOTIFIER] Test: No token. Would send to %s", recipient)
			result["status"] = "skipped"
			result["reason"] = "no_token"
			results = append(results, result)
			continue
		}

		resp, err := ns.fonnteClient.Send(recipient, message)
		if err != nil {
			log.Printf("[NOTIFIER] Test failed for %s: %v", recipient, err)
			result["status"] = "error"
			result["reason"] = err.Error()
			results = append(results, result)
			continue
		}

		result["status"] = "ok"
		result["response"] = resp
		results = append(results, result)
	}

	log.Printf("[NOTIFIER] Test message results: %v", results)
	return nil
}

// buildAlertMessage constructs the alert message
func (ns *NotificationService) buildAlertMessage(data AlertData) string {
	shutdownStatus := map[bool]string{true: "AKTIF", false: "TIDAK"}[data.ShutdownTriggered]

	return fmt.Sprintf(
		"🚨 SIEWS+ ALERT — ZONA TERLARANG DILANGGAR\n\n"+
			"Fasilitas : %s\n"+
			"Zona      : %s\n"+
			"Risiko    : %s\n"+
			"Waktu     : %s\n"+
			"Confidence: %.0f%%\n"+
			"Shutdown  : %s\n\n"+
			"Segera periksa area dan ambil tindakan.",
		data.FacilityName,
		data.ZoneName,
		strings.ToUpper(data.RiskLevel),
		data.Timestamp.Format("02/01/2006 15:04:05 WIB"),
		data.Confidence*100,
		shutdownStatus,
	)
}

// isInCooldown checks if an alert is in cooldown period
func (ns *NotificationService) isInCooldown(key string) bool {
	ns.mu.RLock()
	defer ns.mu.RUnlock()

	lastSent, exists := ns.cooldownMap[key]
	if !exists {
		return false
	}

	return time.Since(lastSent) < ns.cooldownDuration
}

// updateCooldown updates the cooldown timestamp for a key
func (ns *NotificationService) updateCooldown(key string) {
	ns.mu.Lock()
	defer ns.mu.Unlock()
	ns.cooldownMap[key] = time.Now()
}

// parseRecipients parses comma-separated recipient string
func parseRecipients(recipientsStr string) []string {
	recipients := strings.Split(recipientsStr, ",")
	var result []string
	for _, r := range recipients {
		r = strings.TrimSpace(r)
		if r != "" {
			result = append(result, r)
		}
	}
	return result
}

// GetStats returns notification service statistics
func (ns *NotificationService) GetStats() map[string]interface{} {
	ns.mu.RLock()
	defer ns.mu.RUnlock()

	return map[string]interface{}{
		"recipients_count":        len(ns.recipients),
		"cooldown_duration":       ns.cooldownDuration.String(),
		"active_cooldowns":        len(ns.cooldownMap),
		"fonnte_token_configured": ns.fonnteClient != nil && ns.fonnteClient.Token != "",
	}
}
