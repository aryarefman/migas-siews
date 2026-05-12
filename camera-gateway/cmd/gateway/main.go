package main

import (
	"log"
	"net"
	"os"

	"camera-gateway/internal/grpc"
	"camera-gateway/internal/rtsp"
	"camera-gateway/internal/rtmp"

	"google.golang.org/grpc"
)

func main() {
	// Start gRPC server
	lis, err := net.Listen("tcp", ":50051")
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	s := grpc.NewServer()
	grpcServer := grpc.NewCameraServer()
	
	// Register services (to be implemented)
	// pb.RegisterCameraStreamServer(s, grpcServer)

	log.Println("Camera Gateway starting on :50051")
	if err := s.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}

	// Initialize RTSP ingest (to be implemented)
	rtspIngest := rtsp.NewIngest()
	go func() {
		if err := rtspIngest.Start(); err != nil {
			log.Printf("RTSP ingest error: %v", err)
		}
	}()

	// Initialize RTMP ingest (to be implemented)
	rtmpIngest := rtmp.NewIngest()
	go func() {
		if err := rtmpIngest.Start(":1935"); err != nil {
			log.Printf("RTMP ingest error: %v", err)
		}
	}()

	// Wait for interrupt signal
	sigChan := make(chan os.Signal, 1)
	// signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan

	log.Println("Shutting down Camera Gateway...")
}
