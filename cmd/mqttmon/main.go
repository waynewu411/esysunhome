package main

import (
	"encoding/json"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
)

var f mqtt.MessageHandler = func(client mqtt.Client, msg mqtt.Message) {
	// Parse the message
	var payload map[string]interface{}
	if err := json.Unmarshal(msg.Payload(), &payload); err != nil {
		fmt.Printf("Failed to parse message: %v\n", err)
		return
	}

	// Get the inner val field
	valStr, ok := payload["val"].(string)
	if !ok {
		fmt.Printf("Topic: %s - No val field\n", msg.Topic())
		return
	}

	// Parse inner JSON
	var val map[string]interface{}
	if err := json.Unmarshal([]byte(valStr), &val); err != nil {
		fmt.Printf("Topic: %s - Failed to parse val: %v\n", msg.Topic(), err)
		return
	}

	// Extract device info
	deviceID, _ := val["deviceId"].(float64)
	batterySoc, _ := val["batterySoc"].(float64)
	batteryPower, _ := val["batteryPower"].(float64)
	pvPower, _ := val["pvPower"].(float64)
	gridPower, _ := val["gridPower"].(float64)
	loadPower, _ := val["loadPower"].(float64)
	dailyGen, _ := val["dailyPowerGeneration"].(float64)
	code, _ := val["code"].(float64)

	fmt.Printf("\n=== %s ===\n", msg.Topic())
	fmt.Printf("  Device ID: %.0f\n", deviceID)
	fmt.Printf("  Battery SOC: %.0f%%\n", batterySoc)
	fmt.Printf("  Battery Power: %.0fW\n", batteryPower)
	fmt.Printf("  PV Power: %.0fW\n", pvPower)
	fmt.Printf("  Grid Power: %.0fW\n", gridPower)
	fmt.Printf("  Load Power: %.0fW\n", loadPower)
	fmt.Printf("  Daily Gen: %.3fkWh\n", dailyGen)
	fmt.Printf("  Mode: %.0f\n", code)
}

func main() {
	// Configuration
	mqttServer := "abroadtcp.esysunhome.com"
	mqttPort := 1883
	mqttUser := "app"
	mqttPass := "tKQyP52RUZWMPQBtKnMh"
	deviceSN := "6CC84075B7AC"

	// Topics to subscribe (can add multiple)
	topics := []string{
		fmt.Sprintf("/APP/%s/NEWS", deviceSN),
		// Add more topics here if needed
		fmt.Sprintf("/ESY/PVVC/%s/UP", deviceSN),
		fmt.Sprintf("/TIMEER/%s/NEWS", deviceSN),
	}

	opts := mqtt.NewClientOptions().
		AddBroker(fmt.Sprintf("tcp://%s:%d", mqttServer, mqttPort)).
		SetClientID("esysunhome-go-" + fmt.Sprintf("%d", time.Now().Unix())).
		SetUsername(mqttUser).
		SetPassword(mqttPass).
		SetCleanSession(true)

	opts.SetOnConnectHandler(func(client mqtt.Client) {
		fmt.Println("Connected to MQTT broker")
		for _, topic := range topics {
			fmt.Printf("Subscribing to: %s\n", topic)
			client.Subscribe(topic, 0, f)
		}
	})
	opts.SetConnectionLostHandler(func(client mqtt.Client, err error) {
		fmt.Printf("Connection lost: %v\n", err)
	})

	client := mqtt.NewClient(opts)

	// Connect
	fmt.Printf("Connecting to %s:%d...\n", mqttServer, mqttPort)
	if token := client.Connect(); token.Wait() && token.Error() != nil {
		fmt.Printf("Failed to connect: %v\n", token.Error())
		os.Exit(1)
	}

	fmt.Println("Connected! Waiting for messages...")
	fmt.Println("Press Ctrl+C to exit")

	// Wait for interrupt signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	<-sigChan

	// Disconnect
	fmt.Println("\nDisconnecting...")
	client.Disconnect(250)
}
