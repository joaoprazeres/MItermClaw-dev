package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"strings"

	"golang.org/x/oauth2"
	"google.golang.org/api/gmail/v1"
	"google.golang.org/api/option"
)

var (
	configPath = flag.String("config", "gmail-config.json", "Path to config file")
	action    = flag.String("action", "list", "Action: list, read, unread, draft, send, archive, trash")
	query     = flag.String("query", "", "Search query")
	msgID     = flag.String("id", "", "Message ID")
	to        = flag.String("to", "", "Recipient email")
	subject   = flag.String("subject", "", "Email subject")
	body      = flag.String("body", "", "Email body")
	limit     = flag.Int("limit", 10, "Max messages to fetch")
	full      = flag.Bool("full", false, "Show full message content")
)

type Config struct {
	RefreshToken string `json:"refresh_token"`
	ClientID     string `json:"client_id"`
	ClientSecret string `json:"client_secret"`
}

func loadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var cfg Config
	if err := json.Unmarshal(data, &cfg); err != nil {
		return nil, err
	}
	return &cfg, nil
}

func getClient(cfg *Config) (*gmail.Service, error) {
	ctx := context.Background()

	// Create OAuth2 config
	oauth2Config := &oauth2.Config{
		ClientID:     cfg.ClientID,
		ClientSecret: cfg.ClientSecret,
		Endpoint: oauth2.Endpoint{
			AuthURL:  "https://accounts.google.com/o/oauth2/auth",
			TokenURL: "https://oauth2.googleapis.com/token",
		},
	}

	// Use refresh token to get token source
	token := &oauth2.Token{RefreshToken: cfg.RefreshToken}
	tokenSource := oauth2Config.TokenSource(ctx, token)

	// Create Gmail service
	service, err := gmail.NewService(ctx, option.WithTokenSource(tokenSource))
	if err != nil {
		return nil, fmt.Errorf("unable to create Gmail service: %v", err)
	}

	return service, nil
}

func listMessages(svc *gmail.Service, query string, limit int) error {
	listCall := svc.Users.Messages.List("me")
	if query != "" {
		listCall = listCall.Q(query)
	}
	listCall = listCall.MaxResults(int64(limit))

	msgs, err := listCall.Do()
	if err != nil {
		return err
	}

	if len(msgs.Messages) == 0 {
		fmt.Println("No messages found.")
		return nil
	}

	fmt.Printf("Found %d messages:\n\n", len(msgs.Messages))
	for _, msg := range msgs.Messages {
		fmt.Printf("ID: %s\n", msg.Id)
	}
	return nil
}

func readMessage(svc *gmail.Service, msgID string, full bool) error {
	msg, err := svc.Users.Messages.Get("me", msgID).Format("full").Do()
	if err != nil {
		return err
	}

	fmt.Printf("ID: %s\n", msg.Id)
	fmt.Printf("ThreadID: %s\n", msg.ThreadId)
	fmt.Printf("Subject: %s\n", getHeader(msg.Payload.Headers, "Subject"))
	fmt.Printf("From: %s\n", getHeader(msg.Payload.Headers, "From"))
	fmt.Printf("To: %s\n", getHeader(msg.Payload.Headers, "To"))
	fmt.Printf("Date: %s\n", getHeader(msg.Payload.Headers, "Date"))
	fmt.Printf("LabelIDs: %v\n", msg.LabelIds)

	if full {
		fmt.Println("\n--- Body ---")
		if msg.Payload.Body.Data != "" {
			fmt.Println(decodeBody(msg.Payload.Body.Data))
		}
		if len(msg.Payload.Parts) > 0 {
			for _, part := range msg.Payload.Parts {
				if part.Body.Data != "" {
					fmt.Printf("\n--- %s ---\n", part.MimeType)
					fmt.Println(decodeBody(part.Body.Data))
				}
			}
		}
	}
	return nil
}

func getHeader(headers []*gmail.MessagePartHeader, name string) string {
	for _, h := range headers {
		if h.Name == name {
			return h.Value
		}
	}
	return ""
}

func decodeBody(data string) string {
	// Simple base64url decode
	// In production, use encoding/base64 with RawStdEncoding
	decoded, err := simpleBase64Decode(data)
	if err != nil {
		return data
	}
	return string(decoded)
}

func simpleBase64Decode(encoded string) ([]byte, error) {
	// Handle URL-safe base64
	encoded = strings.ReplaceAll(encoded, "-", "+")
	encoded = strings.ReplaceAll(encoded, "_", "/")
	// Add padding if needed
	padding := 4 - (len(encoded) % 4)
	if padding != 4 {
		encoded += strings.Repeat("=", padding)
	}
	return base64.StdEncoding.DecodeString(encoded)
}

func markRead(svc *gmail.Service, msgID string, read bool) error {
	req := &gmail.ModifyMessageRequest{}
	if read {
		req.RemoveLabelIds = []string{"UNREAD"}
	} else {
		req.AddLabelIds = []string{"UNREAD"}
	}
	_, err := svc.Users.Messages.Modify("me", msgID, req).Do()
	return err
}

func archiveMessage(svc *gmail.Service, msgID string) error {
	// Remove INBOX label to archive
	_, err := svc.Users.Messages.Modify("me", msgID, &gmail.ModifyMessageRequest{
		RemoveLabelIds: []string{"INBOX"},
	}).Do()
	return err
}

func trashMessage(svc *gmail.Service, msgID string) error {
	_, err := svc.Users.Messages.Trash("me", msgID).Do()
	return err
}

func sendEmail(svc *gmail.Service, to, subject, body string) error {
	msg := fmt.Sprintf("To: %s\r\nSubject: %s\r\n\r\n%s", to, subject, body)

	msgBytes := []byte(msg)
	encoded := base64.URLEncoding.EncodeToString(msgBytes)

	message := &gmail.Message{
		Raw: encoded,
	}

	_, err := svc.Users.Messages.Send("me", message).Do()
	return err
}

func main() {
	flag.Parse()

	cfg, err := loadConfig(*configPath)
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	svc, err := getClient(cfg)
	if err != nil {
		log.Fatalf("Failed to create client: %v", err)
	}

	switch *action {
	case "list":
		err = listMessages(svc, *query, *limit)
	case "read":
		if *msgID == "" {
			fmt.Println("Error: --id required for read action")
			os.Exit(1)
		}
		err = readMessage(svc, *msgID, *full)
	case "unread", "read-status":
		if *msgID == "" {
			fmt.Println("Error: --id required")
			os.Exit(1)
		}
		err = markRead(svc, *msgID, *action == "read-status")
	case "archive":
		if *msgID == "" {
			fmt.Println("Error: --id required")
			os.Exit(1)
		}
		err = archiveMessage(svc, *msgID)
	case "trash":
		if *msgID == "" {
			fmt.Println("Error: --id required")
			os.Exit(1)
		}
		err = trashMessage(svc, *msgID)
	case "send":
		if *to == "" || *subject == "" {
			fmt.Println("Error: --to and --subject required for send action")
			os.Exit(1)
		}
		err = sendEmail(svc, *to, *subject, *body)
	default:
		fmt.Printf("Unknown action: %s\n", *action)
		fmt.Println("Actions: list, read, unread, archive, trash, send")
		os.Exit(1)
	}

	if err != nil {
		log.Fatalf("Error: %v", err)
	}
}