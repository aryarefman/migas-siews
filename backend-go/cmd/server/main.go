package main

import (
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/aryarefman/migas-siews/backend-go/internal/api"
	"github.com/aryarefman/migas-siews/backend-go/internal/detector"
	"github.com/aryarefman/migas-siews/backend-go/internal/models"
)

func main() {
	log.Println("🚀 SIEWS+ 5.0 Go Backend Starting...")

	// Initialize database
	db, err := models.InitDB()
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}
	log.Println("✅ Database connected")

	// Initialize detection pipeline
	pipeline, err := detector.NewPipeline(db)
	if err != nil {
		log.Printf("Warning: Failed to initialize pipeline: %v", err)
		log.Println("Running in degraded mode without detection")
	} else {
		log.Println("✅ Detection pipeline initialized")
		defer pipeline.Close()
	}

	// Initialize shutdown relay (simulation mode by default)
	api.InitRelay(api.RelayConfig{
		SimulationMode: true, // Set to false in production with real hardware
	})

	// Get port from environment or use default
	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}

	// Create and start server
	server := api.NewServer(pipeline, db)

	// Handle graceful shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		log.Printf("🌐 Starting SIEWS+ Go backend on port %s", port)
		if err := server.Run(":" + port); err != nil {
			log.Fatalf("Failed to start server: %v", err)
		}
	}()

	<-quit
	log.Println("Shutting down server...")
}
