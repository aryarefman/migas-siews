package main

import (
	"log"
	"os"
	"os/signal"
	"syscall"

	"camera-gateway/internal/rtmp"
)

func main() {
	log.Println("Starting RTMP Ingest Service...")

	ingest := rtmp.NewIngest()
	
	// Start RTMP server on default port
	addr := ":1935"
	go func() {
		if err := ingest.Start(addr); err != nil {
			log.Fatalf("RTMP server failed: %v", err)
		}
	}()

	log.Printf("RTMP Ingest Service listening on %s", addr)

	// Wait for interrupt signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan

	log.Println("Shutting down RTMP Ingest Service...")
	ingest.Stop()
}
