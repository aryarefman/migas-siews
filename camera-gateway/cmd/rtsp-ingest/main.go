package main

import (
	"log"
	"os"
	"os/signal"
	"syscall"

	"camera-gateway/internal/rtsp"
)

func main() {
	log.Println("Starting RTSP Ingest Service...")

	ingest := rtsp.NewIngest()
	
	// Configure RTSP sources from environment or config
	sources := []string{
		"rtsp://admin:password@192.168.1.100:554/stream",
	}

	for _, source := range sources {
		go func(url string) {
			if err := ingest.Connect(url); err != nil {
				log.Printf("Failed to connect to %s: %v", url, err)
			}
		}(source)
	}

	// Wait for interrupt signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan

	log.Println("Shutting down RTSP Ingest Service...")
	ingest.Stop()
}
