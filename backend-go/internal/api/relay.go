package api

import (
	"log"
)

// Mock hardware control for testing
func MockRelayControl(zoneName string, action string) error {
	log.Printf("[RELAY MOCK] Zone: %s, Action: %s", zoneName, action)
	return nil
}
